"""``ibkr/iv_history``'s check reads the age of its newest day (#1335 draft G-3).

The append stopped on 13 Nov 2026, no call was made after the 16th, and the check was still green on the 21st
with its served table five sessions behind. It counted **names with a year**, and every one of those names still
had its (stale) year: coverage of names and freshness of days are two questions, and it answered only the first.
After Unusual Whales ends on 9 Dec 2026 this is the only implied-volatility source."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from RevenueChaser.core import calendar
from RevenueChaser.core.providers import ibkr_tws as ibkr
from RevenueChaser.rcdata import ops
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.options import ibkr_iv
from RevenueChaser.rcdata.needs import catalog as needs_catalog

from .ibkr_fixture import FakeGateway
from .options_fixture import SESSION

AFTER_CLOSE = datetime(2026, 10, 26, 21, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(calendar, "_now", lambda: AFTER_CLOSE)


def _gateway(monkeypatch, last_bar: date) -> FakeGateway:
    gw = FakeGateway(last_bar=last_bar)
    monkeypatch.setattr(ibkr, "CONNECT", gw.connect)
    return gw


def _run():
    return base.run_request({"dataset": ibkr_iv.NAME, "params": {}}, sleep=lambda s: None)


def test_the_note_names_the_newest_served_day_and_how_far_behind_it_is(monkeypatch):
    """A table up to the newest complete session: full coverage as before, and now the day as well."""
    _gateway(monkeypatch, SESSION)
    row = _run()
    assert row["coverage"] == 1.0
    assert f"newest IBKR day {SESSION}, 0 sessions behind {SESSION}" in row["note"]
    assert "list names have their IBKR year" in row["note"]           # the old half is still said
    kinds = [i["kind"] for i in ops.open_issues(ibkr_iv.NAME)[1]]
    assert ibkr_iv.STALE_ISSUE not in kinds


def test_a_table_five_sessions_behind_is_no_longer_a_quiet_pass(monkeypatch):
    """The live shape of 21 Nov 2026: every list name has its year, and the newest day in it is old. The note says
    the lag and the build raises ``iv_history_stale``."""
    stale = SESSION - timedelta(days=7)                               # 19 Oct 2026, a Monday: five sessions back
    _gateway(monkeypatch, stale)
    row = _run()
    assert row["coverage"] == 1.0                                     # the old check's answer, unchanged
    assert f"newest IBKR day {stale}, 5 sessions behind {SESSION} (max 1)" in row["note"]
    issues = [i for i in ops.open_issues(ibkr_iv.NAME)[1] if i["kind"] == ibkr_iv.STALE_ISSUE]
    assert len(issues) == 1 and "the daily append is not running" in issues[0]["detail"]
    assert str(stale) in issues[0]["detail"]


class _Issues:
    """A ctx that only records what ``_freshness`` raises."""

    def __init__(self) -> None:
        self.raised: list[tuple] = []

    def issue(self, kind: str, key, detail) -> None:
        self.raised.append((kind, key, detail))


def _table(rows: list[tuple]) -> "duckdb.DuckDBPyConnection":
    import duckdb
    con = duckdb.connect()
    con.execute("CREATE TABLE iv_daily (ticker TEXT, session_date DATE, source TEXT)")
    con.executemany("INSERT INTO iv_daily VALUES (?, ?, ?)", rows)
    return con


def test_a_table_with_no_ibkr_row_at_all_is_named_too():
    """The worst case of the same question, which the old check could not say either. UW's rows in the same table
    are not IBKR's: the source column decides, so UW going on does not cover an IBKR stop."""
    ctx = _Issues()
    con = _table([("SPX", SESSION, "uw")])
    said = ibkr_iv.IBKRIVHistory._freshness(ctx, con, SESSION)
    assert said == "no IBKR day served"
    assert [k for k, _, _ in ctx.raised] == [ibkr_iv.STALE_ISSUE]
    assert "no implied volatility is served" in ctx.raised[0][2]


def test_the_lag_and_its_unit_come_from_the_needs_catalog():
    """Freshness has one owner (``rcdata/needs/__init__.py``, avo 29 Oct 2026), so the check and the boards cannot
    disagree about what "behind" means: this module names the need, and the bound is the catalog's."""
    spec = needs_catalog.NEEDS[ibkr_iv.IV_NEED]
    assert ibkr_iv.IV_NEED == "options.iv" and spec.max_lag == 1 and spec.max_lag_unit == "sessions"
    assert ibkr_iv.STALE_ISSUE == "iv_history_stale"
    # and the rows' own source value is the short provider name, not the Parquet folder
    assert ibkr_iv.ROW_SOURCE == "ibkr" and ibkr_iv.SOURCE == "ibkr/iv_history"
