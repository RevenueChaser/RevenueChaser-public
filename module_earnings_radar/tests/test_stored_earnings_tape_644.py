"""The Earnings Radar board reads the stored ``/earnings/{ticker}`` tape (#644).

The earnings set's evening fetch has stored that answer as ``earnings_tape`` since the builder's D2 of 10 Nov 2026
(``rcdata/build/options/tables.EARNINGS_TAPE``), but the table had no need and no reader, so the board asked
``/earnings/{t}`` live for **every** scored name — one request each, on a board that scores up to the day's cap.
This reads it instead, under the same rules the board's other stored inputs follow: the newest session the tape
holds **for that name** (a name is only in the set on the two evenings before its report), a one-session freshness
gate, and a name whose event is today or the next trading day always live, because UW still moves its expected
move, estimate and report time during the day.

Offline: the reader's one store call is patched, as in ``test_stored_calendar_273`` and ``test_er_options_o1``;
``test_the_served_rows_come_newest_report_first`` drives a real ``options.duckdb`` through the fixture so the
serving function's own SQL and its ordering are covered, because the order is what ``rows[0]`` relies on.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core import calendar
from RevenueChaser.module_earnings_radar import stored_inputs
from RevenueChaser.rcdata.tests.conftest import market_roots  # noqa: F401  (fixture)

# 2026-10-14 is a Wednesday. The evening fetch is the 13th; the name reports on the 16th (Friday), past today and
# tomorrow, so its tape is the store's to answer.
SESSION = date(2026, 10, 13)
REPORT = date(2026, 10, 16)
NOW = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)       # 17:00 New York
TODAY = date(2026, 10, 14)
TOMORROW = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(calendar, "_now", lambda: NOW)


def _row(ticker="AAA", *, report_date=REPORT, session_date=SESSION, **over):
    row = {"session_date": session_date, "ticker": ticker, "report_date": report_date,
           "report_time": "premarket", "ending_fiscal_quarter": date(2026, 9, 30), "report_source": "uw",
           "actual_eps": 1.10, "street_mean_est": 1.00, "price": 50.0,
           "expected_move": 2.5, "expected_move_perc": 0.052,
           "post_earnings_move_1d": 0.04, "long_straddle_1d": 0.10}
    row.update(over)
    return row


def _served(monkeypatch, rows):
    """``read.earnings_tape`` serving ``rows`` in its own order: by ticker, then report date descending."""
    ordered = sorted(rows, key=lambda r: (r["ticker"], -r["report_date"].toordinal()))
    monkeypatch.setattr(stored_inputs.market_read, "earnings_tape", lambda *a, **k: list(ordered))


# ── what the reader serves ────────────────────────────────────────────────────────────────────────────────────

def test_a_names_tape_is_served_under_uws_own_field_names(monkeypatch):
    """The scoring reads one shape whether the rows are stored or live, so the reader hands back UW's names."""
    _served(monkeypatch, [_row()])
    out = stored_inputs.earnings_tape(["AAA"])
    assert list(out) == ["AAA"]
    row = out["AAA"][0]
    assert row["report_date"] == "2026-10-16" and row["report_time"] == "premarket"
    assert row["ending_fiscal_quarter"] == "2026-09-30"
    assert row["actual_eps"] == 1.10 and row["street_mean_est"] == 1.00 and row["price"] == 50.0
    assert row["expected_move_perc"] == 0.052
    assert row["post_earnings_move_1d"] == 0.04 and row["long_straddle_1d"] == 0.10
    # The build's own name for UW's ``source``; the scoring does not read it, but it is not dropped either.
    assert row["source"] == "uw"


def test_a_null_double_is_no_signal_never_a_zero(monkeypatch):
    """Every rule treats a missing move or straddle as "no signal"; a 0.0 would be a real reading."""
    _served(monkeypatch, [_row(post_earnings_move_1d=None, long_straddle_1d=None, actual_eps=None)])
    row = stored_inputs.earnings_tape(["AAA"])["AAA"][0]
    assert row["post_earnings_move_1d"] is None and row["long_straddle_1d"] is None
    assert row["actual_eps"] is None


def test_the_rows_of_one_name_keep_the_newest_report_first(monkeypatch):
    """``rows[0]`` is the upcoming event, and the edge and straddle medians take the newest completed prints: the
    order is load-bearing, not cosmetic."""
    older = _row(report_date=date(2026, 7, 17))
    oldest = _row(report_date=date(2026, 4, 17))
    _served(monkeypatch, [oldest, _row(), older])
    days = [r["report_date"] for r in stored_inputs.earnings_tape(["AAA"])["AAA"]]
    assert days == ["2026-10-16", "2026-07-17", "2026-04-17"]


def test_each_name_gets_its_own_newest_session(monkeypatch):
    """A name is only in the earnings set on the two evenings before its report, so one ``max(session_date)`` over
    the table would serve the names reporting next and silently drop every other one."""
    # Both names' newest session is inside the one-session freshness gate, so neither is dropped for lag: AAA's
    # is today's evening fetch, BBB's yesterday's. A single ``max(session_date)`` would be AAA's and drop BBB.
    _served(monkeypatch, [_row("AAA", session_date=TODAY), _row("AAA", session_date=date(2026, 10, 12)),
                          _row("BBB", session_date=SESSION, report_date=date(2026, 10, 19))])
    out = stored_inputs.earnings_tape(["AAA", "BBB"])
    assert set(out) == {"AAA", "BBB"}
    assert len(out["AAA"]) == 1, "the older evening's copy of the same report is not served beside it"


def test_a_name_the_tape_does_not_hold_is_absent(monkeypatch):
    _served(monkeypatch, [_row("AAA")])
    assert set(stored_inputs.earnings_tape(["AAA", "ZZZ"])) == {"AAA"}


# ── when the reader serves nothing ────────────────────────────────────────────────────────────────────────────

def test_an_empty_table_serves_nothing(monkeypatch):
    _served(monkeypatch, [])
    assert stored_inputs.earnings_tape(["AAA"]) == {}


def test_a_store_error_is_nothing_stored_not_a_failed_fetch(monkeypatch):
    def _boom(*_a, **_kw):
        raise RuntimeError("no options file")

    monkeypatch.setattr(stored_inputs.market_read, "earnings_tape", _boom)
    assert stored_inputs.earnings_tape(["AAA"]) == {}


def test_no_names_asked_is_no_read_at_all(monkeypatch):
    def _never(*_a, **_kw):
        raise AssertionError("the reader read the store for no names")

    monkeypatch.setattr(stored_inputs.market_read, "earnings_tape", _never)
    assert stored_inputs.earnings_tape([]) == {}


@pytest.mark.parametrize("session, served", [(SESSION, True), (date(2026, 10, 9), False)])
def test_a_session_past_the_one_session_gate_is_not_served(monkeypatch, session, served):
    """The same freshness gate the calendar and the screener rows apply (``calendar_max_lag``)."""
    assert stored_inputs.calendar_max_lag() == 1
    _served(monkeypatch, [_row(session_date=session)])
    assert (stored_inputs.earnings_tape(["AAA"]) != {}) is served


@pytest.mark.parametrize("day", [TODAY, TOMORROW])
def test_a_name_reporting_today_or_tomorrow_stays_live(monkeypatch, day):
    """UW moves the expected move, the estimate and the report time during the day for a name about to report, so
    its whole tape is live — the rule ``calendar_items`` and ``screener_rows`` already keep."""
    _served(monkeypatch, [_row(report_date=day), _row(report_date=date(2026, 7, 17))])
    assert stored_inputs.earnings_tape(["AAA"]) == {}


# ── the serving function's own ordering, against a real file ──────────────────────────────────────────────────

def test_the_served_rows_come_newest_report_first(market_roots):  # noqa: F811
    from RevenueChaser.rcdata import ops, read
    from RevenueChaser.rcdata.tests import screener_fixture
    screener_fixture.write_tape([
        screener_fixture.tape_row("AAA", session_date=SESSION, report_date=date(2026, 4, 17)),
        screener_fixture.tape_row("AAA", session_date=SESSION, report_date=REPORT),
        screener_fixture.tape_row("BBB", session_date=SESSION, report_date=date(2026, 10, 19)),
    ])
    ops.record_check("uw/option_screener", "changed", run_id="r1")
    rows = read.earnings_tape(["AAA", "BBB"])
    assert [(r["ticker"], str(r["report_date"])) for r in rows] == [
        ("AAA", "2026-10-16"), ("AAA", "2026-04-17"), ("BBB", "2026-10-19")]
    assert read.earnings_tape(["ZZZ"]) == []
    assert [str(r["report_date"]) for r in read.earnings_tape(["AAA"], session_date=SESSION)] == \
        ["2026-10-16", "2026-04-17"]


# ── the pipeline: the stored tape replaces the per-name request ───────────────────────────────────────────────

CAL = {"AAPL": {"earnings_date": "2026-10-16", "full_name": "Apple", "expected_move_perc": 0.05}}


class _UW:
    """Counts the ``/earnings/{t}`` reads; every other answer is empty."""

    def __init__(self):
        self.calls: list[str] = []

    def __getattr__(self, name):
        return lambda *a, **k: {} if name in ("ticker_info", "aggregate_flow") else []

    def earnings_rows(self, ticker):
        self.calls.append(ticker)
        return [{"report_date": "2026-10-16", "report_time": "premarket", "company_name": "Apple",
                 "street_mean_est": 2.0, "price": 60.0, "expected_move_perc": 0.06}]


def _pipeline(monkeypatch, stored: dict):
    from RevenueChaser.module_earnings_radar.pipeline import EarningsPipeline
    monkeypatch.setattr(stored_inputs, "earnings_tape", lambda tickers, today=None: stored)
    uw = _UW()
    p = EarningsPipeline(["AAPL"], uw=uw, cal_meta=CAL)
    p._screener_cache = {"AAPL": {"close": 100.0}}
    p._warm_earnings_tape(["AAPL"])
    return p, uw


def _tape(**over):
    return [{"report_date": "2026-10-16", "report_time": "premarket", "street_mean_est": 1.0, "price": 50.0,
             "expected_move_perc": 0.052, "actual_eps": None, "source": "uw", **over}]


def test_a_stored_tape_makes_no_earnings_request(monkeypatch, rawstore_tmp_db):
    p, uw = _pipeline(monkeypatch, {"AAPL": _tape()})
    earn, hist = p._earnings_rows("AAPL")
    assert uw.calls == [], "the board asked /earnings/{t} although the tape held the name"
    assert earn is hist[0] and earn["price"] == 50.0
    assert p._tape_stored == {"AAPL"} and p._tape_live == set()


def test_a_name_the_tape_lacks_is_asked_live(monkeypatch, rawstore_tmp_db):
    p, uw = _pipeline(monkeypatch, {})
    earn, hist = p._earnings_rows("AAPL")
    assert uw.calls == ["AAPL"]
    assert earn["price"] == 60.0 and len(hist) == 1
    assert p._tape_live == {"AAPL"} and p._tape_stored == set()


def test_a_client_without_the_one_request_method_still_gets_both_reads(monkeypatch, rawstore_tmp_db):
    """A fake without ``earnings_rows`` falls back to the two legacy calls, each returning what it did before:
    the event dict and the history list, not one concatenated list."""
    class _Legacy(_UW):
        earnings_rows = None       # the attribute is there but not callable, so ``getattr`` finds nothing to call

        def earnings_data(self, ticker):
            self.calls.append(f"data:{ticker}")
            return {"price": 70.0}

        def earnings_history(self, ticker):
            self.calls.append(f"history:{ticker}")
            return [{"report_date": "2026-07-17", "actual_eps": 1.0}]

    from RevenueChaser.module_earnings_radar.pipeline import EarningsPipeline
    monkeypatch.setattr(stored_inputs, "earnings_tape", lambda tickers, today=None: {})
    uw = _Legacy()
    p = EarningsPipeline(["AAPL"], uw=uw, cal_meta=CAL)
    p._warm_earnings_tape(["AAPL"])
    earn, hist = p._earnings_rows("AAPL")
    assert uw.calls == ["data:AAPL", "history:AAPL"]
    assert earn == {"price": 70.0}
    assert [h["report_date"] for h in hist] == ["2026-07-17"]


def test_the_run_counts_which_names_came_from_the_tape(monkeypatch, rawstore_tmp_db):
    """The board's ``input_sources`` note already says stored-versus-live per input; the tape joins it, so a run
    where the set was not built shows up as live rather than looking the same."""
    p, _uw = _pipeline(monkeypatch, {"AAPL": _tape()})
    p._earnings_rows("AAPL")
    p._earnings_rows("ZZZ")
    assert p._tape_stored == {"AAPL"} and p._tape_live == {"ZZZ"}
