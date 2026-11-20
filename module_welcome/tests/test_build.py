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


# ── #643 PR 5b: the earnings card reads the options screener ───────────────────────────────────────────────────

SCREENER_SESSION = date(2026, 11, 9)          # Monday's sweep; NOW is Tuesday 10 Nov before the open


def _screener(rows):
    from RevenueChaser.rcdata.tests import screener_fixture
    screener_fixture.write(rows)


def _screener_row(ticker, day, **over):
    from RevenueChaser.rcdata.tests import screener_fixture
    session = over.pop("session_date", SCREENER_SESSION)
    return screener_fixture.row(ticker, session_date=session, report_date=day, **over)


def _fresh():
    return {r["job"]: r for r in rawstore.query("SELECT * FROM welcome_freshness", db="welcome")}


def test_the_earnings_card_is_written_from_the_screeners_newest_session():
    _screener([_screener_row("AAA", TUE), _screener_row("BBB", WED, report_session="afterhours"),
               _screener_row("CCC", date(2026, 11, 20))])          # outside the two days
    out = wb.build(now=NOW)
    rows = _earnings()
    assert out["earnings"] == 2 and set(rows) == {"AAA", "BBB"}
    assert rows["AAA"]["earnings_date"] == TUE and rows["AAA"]["report_session"] == "premarket"
    assert rows["BBB"]["earnings_date"] == WED and rows["BBB"]["report_session"] == "afterhours"
    assert rows["AAA"]["expected_move_perc"] == 0.05 and rows["AAA"]["full_name"] == "AAA Inc"
    assert rows["AAA"]["source_session"] == SCREENER_SESSION and rows["AAA"]["retired_at"] is None


def test_the_implied_move_stands_in_where_the_calendar_has_no_expected_move():
    _screener([_screener_row("AAA", TUE, expected_move_perc=None, implied_move_perc=0.031)])
    wb.build(now=NOW)
    assert _earnings()["AAA"]["expected_move_perc"] == 0.031


def test_a_name_the_screener_row_does_not_name_takes_the_spines_name():
    from RevenueChaser.rcdata.tests import universe_store
    universe_store.put([{"ticker": "AAA", "name": "Alpha Industries"}])
    _screener([_screener_row("AAA", TUE, full_name=None)])
    wb.build(now=NOW)
    assert _earnings()["AAA"]["full_name"] == "Alpha Industries"


def test_a_name_the_newest_session_no_longer_lists_is_retired_not_deleted():
    _screener([_screener_row("AAA", TUE), _screener_row("BBB", TUE)])
    wb.build(now=NOW)
    _screener([_screener_row("AAA", TUE, session_date=date(2026, 11, 10))])     # a newer sweep, without BBB
    wb.build(now=NOW + 60)
    rows = _earnings()
    assert rows["AAA"]["retired_at"] is None
    assert rows["BBB"]["retired_at"] == NOW + 60, "the row stays, marked retired"


def test_without_a_built_screener_session_the_card_keeps_what_it_has():
    """A missing options file is no rows the way an empty old table was: nothing is written, nothing retired."""
    _screener([_screener_row("AAA", TUE)])
    wb.build(now=NOW)
    from RevenueChaser.rcdata import serving
    serving.live_path("options").unlink()
    assert wb.build(now=NOW + 60)["earnings"] == 0
    assert _earnings()["AAA"]["retired_at"] is None


# ── #643 PR 6: the freshness card is one row per builder file ──────────────────────────────────────────────────

def _build_run(run_id, dataset, status, finished, error=None):
    """One finished builder run in the ops ledger, at the time the test wants it (``start_run`` stamps now)."""
    from RevenueChaser.rcdata import ops
    ops.start_run(run_id, dataset, "queue")
    ops.finish_run(run_id, status, error)
    with ops.connect(ops.ops_path()) as con:
        con.execute("UPDATE job_runs2 SET started_at = ?, finished_at = ? WHERE run_id = ?",
                    (finished - 60.0, finished, run_id))
        con.commit()


def test_the_freshness_rows_are_the_builder_files_not_the_dashboard_jobs():
    _build_run("r1", "sec/company_tickers_exchange", "ok", NOW - 3600)
    _build_run("r2", "uw/option_screener", "failed", NOW - 1800, error="HTTP 503")
    out = wb.build(now=NOW)
    rows = _fresh()
    assert out["freshness"] == 2 and set(rows) == {"spine", "options"}
    assert rows["spine"]["last_status"] == "ok" and rows["spine"]["last_ok_at"] == NOW - 3600
    assert rows["options"]["last_status"] == "error" and rows["options"]["last_error"] == "HTTP 503"
    assert rows["options"]["last_failed_at"] == NOW - 1800 and rows["options"]["last_ok_at"] is None


def test_a_later_good_run_of_the_same_file_clears_its_error_and_keeps_the_failure_time():
    _build_run("r1", "uw/option_screener", "failed", NOW - 3600, error="HTTP 503")
    _build_run("r2", "uw/option_screener", "ok", NOW - 60)
    wb.build(now=NOW)
    row = _fresh()["options"]
    assert row["last_status"] == "ok" and row["last_error"] is None
    assert row["last_ok_at"] == NOW - 60 and row["last_failed_at"] == NOW - 3600


def test_a_skipped_run_is_a_file_that_built_nothing_due_not_an_error():
    _build_run("r1", "sec/company_tickers_exchange", "skipped", NOW - 120)
    wb.build(now=NOW)
    assert _fresh()["spine"]["last_status"] == "ok"


def test_every_serving_file_has_a_name_on_the_card():
    """A new builder file cannot reach the card unnamed: the labels cover ``serving.KINDS`` exactly."""
    from RevenueChaser.rcdata import serving
    assert set(wb.FILE_LABELS) == set(serving.KINDS)
