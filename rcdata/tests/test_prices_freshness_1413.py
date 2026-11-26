"""#1413 / prices plan v4 step 3: the newest stock session, the half-cent floor of the difference report, and the
WRDS history's ``source_as_of``.

On homesrv (23 Nov 2026) the served file's newest session read 2026-11-20 with the ``index:SPX`` row and 2026-11-19
without it: ``prices/serving``'s check reported the store a session fresher than its stock bars."""
from __future__ import annotations

from datetime import date

import duckdb

from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.prices import serving as prices_serving, stage, wrds_history


def test_the_serving_check_reports_the_newest_stock_session_not_the_index_row(monkeypatch):
    con = duckdb.connect()
    con.execute("CREATE TABLE price_bar_daily (security_id TEXT, session_date DATE)")
    con.executemany("INSERT INTO price_bar_daily VALUES (?, ?)",
                    [("001690:01", date(2026, 11, 19)), ("index:SPX", date(2026, 11, 20))])
    monkeypatch.setattr(stage, "compare_live", lambda *a, **k: (0, 0))
    monkeypatch.setattr(stage, "count", lambda *a, **k: 2)
    ctx = base.RunContext(run_id="t", dataset=prices_serving.NAME, as_of=date(2026, 11, 20))
    assert prices_serving.DATASET.check(ctx, con)["source_as_of"] == "2026-11-19"


def test_every_newest_session_site_reads_the_one_stock_rule():
    """One rule, not three copies: the unfiltered ``max(session_date)`` is the bug this replaces."""
    text = open(prices_serving.__file__, encoding="utf-8").read()
    assert "SELECT max(session_date) FROM price_bar_daily\"" not in text
    assert text.count("NEWEST_STOCK_SQL") >= 4                         # the constant and its three readers


def _report(alpaca: float, compustat: float) -> dict:
    con = duckdb.connect()
    con.execute("CREATE TABLE _hist_all (source TEXT, security_id TEXT, session_date DATE, close DOUBLE)")
    con.execute("CREATE TABLE _alp (security_id TEXT, session_date DATE, close DOUBLE)")
    con.execute("CREATE TABLE _hret (source TEXT, security_id TEXT, session_date DATE, own_return DOUBLE, "
                "ours DOUBLE)")
    con.execute("INSERT INTO _hist_all VALUES (?, 'X', '2026-11-19', ?)", [wrds_history.COMPUSTAT, compustat])
    con.execute("INSERT INTO _alp VALUES ('X', '2026-11-19', ?)", [alpaca])
    rows = con.execute(prices_serving._report_parts()).fetchall()
    return {r[0]: r[3] for r in rows}


def test_a_sub_half_cent_close_difference_is_no_difference():
    """Plan v2 step 2: a 1 bp tolerance alone counts a penny stock's rounding (0.0012 vs 0.0013) as a difference;
    ``alpaca_close_differs`` already has the half-cent floor, the report did not."""
    assert _report(alpaca=0.0013, compustat=0.0012)["compustat_vs_alpaca"] == 0
    assert _report(alpaca=1.00, compustat=1.02)["compustat_vs_alpaca"] == 1      # two cents: still a difference


def test_the_wrds_check_reports_the_newest_staged_session_not_the_fetch_day(monkeypatch):
    con = duckdb.connect()
    con.execute("CREATE TABLE stg_wrds_secd (datadate DATE, source_as_of DATE)")
    con.execute("CREATE TABLE stg_wrds_dsf (dlycaldt DATE, source_as_of DATE)")
    con.execute("CREATE TABLE stg_wrds_divid (datadate DATE, source_as_of DATE)")
    con.execute("INSERT INTO stg_wrds_secd VALUES ('2026-11-19', '2026-11-23')")
    con.execute("INSERT INTO stg_wrds_dsf VALUES ('2025-12-31', '2026-11-23')")
    monkeypatch.setattr(stage, "compare_live", lambda *a, **k: (0, 0))
    ctx = base.RunContext(run_id="t", dataset=wrds_history.NAME)
    assert wrds_history.DATASET.check(ctx, con)["source_as_of"] == "2026-11-19"
