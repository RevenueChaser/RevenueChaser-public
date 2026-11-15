"""The Welcome board's incremental build into ``boards/welcome.duckdb`` (welcome plan §4, DECISIONS S16).

Three parts, each upserted from what changed since its own mark, nothing deleted: the market snapshot (SPX, VIX,
MOVE, US 10-year), the earnings of today and the next trading day, and the last run of every job.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta

from RevenueChaser.core import rawstore
from RevenueChaser.module_welcome import build as wb
from RevenueChaser.rcdata.tests import market_fixture

NY = wb.NY
NOW = datetime(2026, 11, 10, 8, 0, tzinfo=NY).timestamp()          # Tue 10 Nov, before the open
DAYS = [date(2026, 10, 12) + timedelta(days=i) for i in range(29)]
SESSIONS = [d for d in DAYS if d.weekday() < 5 and d <= date(2026, 11, 9)]


def _series(series_id, sessions, values, source="test", fetched_at=1.0):
    """One series in the builder's ``market_series`` (#643 PR 5)."""
    rows = market_fixture.rows(series_id, list(sessions), list(values), source=source)
    for r in rows:
        r["fetched_at"] = fetched_at
    market_fixture.write_series(rows)


def _prices(sessions, base=6000.0):
    _series("SPX", sessions, [base + i for i in range(len(sessions))])


def _vol(symbol, sessions, base):
    _series(symbol, sessions, [base + i for i in range(len(sessions))])
    # Two sources for the same sessions: the newest fetch wins, as it did on the old table.
    _series(symbol, sessions, [base + i + 0.5 for i in range(len(sessions))], source="uw", fetched_at=2.0)


def _ten_year(sessions):
    _series("DGS10", sessions, [4.0 + i / 100 for i in range(len(sessions))])


def _snap():
    return {r["series"]: r for r in rawstore.query("SELECT * FROM welcome_snapshot", db="welcome")}


def test_the_snapshot_keeps_the_last_close_its_change_and_a_20_day_line():
    _prices(SESSIONS)
    _vol("VIX", SESSIONS, 15.0)
    _ten_year(SESSIONS)
    out = wb.build(now=NOW)
    snap = _snap()
    spx = snap["SPX"]
    assert spx["session_date"] == SESSIONS[-1] and spx["close"] == 6000.0 + len(SESSIONS) - 1
    assert spx["change"] == 1.0 and len(json.loads(spx["spark"])) == wb.SPARK_DAYS
    assert snap["VIX"]["close"] == 15.0 + len(SESSIONS) - 1 + 0.5               # the newer source
    assert snap["US10Y"]["close"] == 4.0 + (len(SESSIONS) - 1) / 100
    assert "MOVE" not in snap and out["snapshot"] == 3


def test_a_second_build_with_no_new_session_writes_no_snapshot_row():
    _prices(SESSIONS[:-1])
    wb.build(now=NOW)
    assert wb.build(now=NOW + 60)["snapshot"] == 0
    _prices(SESSIONS)
    assert wb.build(now=NOW + 120)["snapshot"] == 1
    rows = rawstore.query("SELECT session_date FROM welcome_snapshot WHERE series = 'SPX' ORDER BY 1", db="welcome")
    assert [r["session_date"] for r in rows] == SESSIONS[-2:]                    # both days kept, none deleted


def _earnings():
    return {r["ticker"]: r for r in rawstore.query("SELECT * FROM welcome_earnings", db="welcome")}


TUE, WED = date(2026, 11, 10), date(2026, 11, 11)


def _run(run_id, job, status, finished, registry=None, error=None):
    return {"run_id": run_id, "job_id": run_id, "module": job, "lane": "fast", "trigger": "manual",
            "source": "dashboard", "pid": 1, "registry_name": registry, "params": "{}", "queued_at": NOW - 5,
            "started_at": NOW - 4, "finished_at": finished, "status": status, "error": error, "message": None,
            "counts": None}


def test_a_corrected_close_for_the_stored_session_is_written():
    _ten_year(SESSIONS)
    wb.build(now=NOW)
    _series("DGS10", [SESSIONS[-1]], [4.5], source="fred_revised", fetched_at=5.0)
    assert wb.build(now=NOW + 60)["snapshot"] == 1
    assert _snap()["US10Y"]["close"] == 4.5


def test_a_series_the_builder_does_not_hold_writes_no_row_and_stops_no_other():
    """A missing market file is no rows, not a failure: the three series that are there still build (#643 PR 5)."""
    _prices(SESSIONS)                                           # SPX only; VIX, MOVE and DGS10 have no rows
    assert wb.build(now=NOW)["snapshot"] == 1
    assert set(_snap()) == {"SPX"}
