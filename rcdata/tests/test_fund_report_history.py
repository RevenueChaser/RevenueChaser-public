"""``earnings_report_history``: the day each past quarter was reported (#1181, step A of the WRDS plan).

Compustat's ``rdq`` wherever it has one (F3; avo, 20 Nov 2026: "WRDS'e gecelim tamamen"), UW's report day only for a
quarter Compustat has no date for. The rule is tested on the two staging tables directly, then once through the
real build against the fake WRDS worker (never WRDS).
"""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from RevenueChaser.core.providers import sec_edgar
from RevenueChaser.rcdata import read, serving
from RevenueChaser.rcdata.build.fundamentals import companyfacts, tables, uw_earnings, wrds_fund
from RevenueChaser.rcdata.build.spine import wrds as spine_wrds
from RevenueChaser.rcdata.needs import catalog

from . import fund_fixture as fx

MSFT, HEI, ORCL = "789019", "46619", "1341439"
AS_OF = date(2026, 11, 16)


def _con(fundq: list[tuple], uw: list[tuple], links: list[tuple] | None = None) -> duckdb.DuckDBPyConnection:
    """A scratch file with the two staging tables and the company links the rule reads.

    ``fundq`` rows are ``(gvkey, datadate, rdq)``; ``uw`` rows ``(cik, period_end, report_date)``; ``links``
    ``(ticker, cik, gvkey)``."""
    con = duckdb.connect()
    con.execute("CREATE TABLE fundamental_company (ticker TEXT, cik TEXT, gvkey TEXT)")
    con.executemany("INSERT INTO fundamental_company VALUES (?, ?, ?)",
                    links or [("MSFT", MSFT, "012141"), ("HEI", HEI, "005567"), ("HEI-A", HEI, "005567"),
                              ("ORCL", ORCL, "012142")])
    cols = ", ".join(f'"{c}" {t}' for c, t in wrds_fund.FUNDQ.schema + wrds_fund.PROVENANCE)
    con.execute(f"CREATE TEMP TABLE {wrds_fund.FUNDQ.staging} ({cols})")
    for gvkey, datadate, rdq in fundq:
        con.execute(f"INSERT INTO {wrds_fund.FUNDQ.staging} (gvkey, datadate, rdq, source_as_of, fetched_at, run_id) "
                    "VALUES (?, ?, ?, ?, 1.0, 'w1')", [gvkey, datadate, rdq, AS_OF])
    cols = ", ".join(f'"{c}" {t}' for c, t in uw_earnings.SCHEMA)
    con.execute(f"CREATE TEMP TABLE {uw_earnings.STAGING} ({cols})")
    for cik, period_end, report_date in uw:
        con.execute(f"INSERT INTO {uw_earnings.STAGING} (cik, ticker, period_end, report_date, eps_reported, source, "
                    "source_as_of, fetched_at, run_id) VALUES (?, 'X', ?, ?, 1.0, ?, ?, 2.0, 'u1')",
                    [cik, period_end, report_date, uw_earnings.NAME, AS_OF])
    return con


def _served(con) -> list[tuple]:
    return con.execute("SELECT cik, period_end, report_date, gvkey, source FROM earnings_report_history "
                       "ORDER BY cik, period_end").fetchall()


def test_compustats_report_day_is_served_with_its_company_and_source():
    con = _con([("012141", "2025-09-30", "2025-10-29")], [])
    assert tables._report_history(con) == 1
    assert _served(con) == [(MSFT, date(2025, 9, 30), date(2025, 10, 29), "012141", wrds_fund.FUNDQ.name)]
    assert con.execute("SELECT source_as_of, run_id FROM earnings_report_history").fetchall() == [(AS_OF, "w1")]


def test_compustat_wins_where_both_have_the_quarter():
    """F3: where Compustat has a value it is the one served, also when UW names another day."""
    con = _con([("012141", "2025-09-30", "2025-10-29")], [(MSFT, "2025-09-30", "2025-10-28")])
    tables._report_history(con)
    assert _served(con) == [(MSFT, date(2025, 9, 30), date(2025, 10, 29), "012141", wrds_fund.FUNDQ.name)]


def test_uw_fills_a_quarter_compustat_has_no_date_for():
    """``rdq`` is empty on 9.12% of the linked companies' quarters (#1181): there UW's day is served, as UW's."""
    con = _con([("012141", "2025-09-30", None), ("012141", "2025-06-30", "2025-07-30")],
               [(MSFT, "2025-09-30", "2025-10-29"), (MSFT, "2015-09-30", "2015-10-22")])
    tables._report_history(con)
    assert _served(con) == [
        (MSFT, date(2015, 9, 30), date(2015, 10, 22), None, uw_earnings.NAME),      # older than the ten years
        (MSFT, date(2025, 6, 30), date(2025, 7, 30), "012141", wrds_fund.FUNDQ.name),
        (MSFT, date(2025, 9, 30), date(2025, 10, 29), None, uw_earnings.NAME)]


def test_a_uw_quarter_ending_days_from_compustats_is_the_same_quarter():
    """A 52/53-week year: Compustat writes the month end, UW the real last day. One quarter, so one row."""
    con = _con([("012141", "2025-09-30", "2025-10-29")], [(MSFT, "2025-09-27", "2025-10-29")])
    tables._report_history(con)
    assert [r[1] for r in _served(con)] == [date(2025, 9, 30)]
    con = _con([("012141", "2025-09-30", "2025-10-29")],
               [(MSFT, f"2025-09-{30 - wrds_fund.PERIOD_DAYS - 1:02d}", "2025-10-29")])
    tables._report_history(con)
    assert len(_served(con)) == 2                                   # one day past the window: another quarter


def test_a_company_outside_the_universe_and_a_row_without_a_day_serve_nothing():
    con = _con([("099999", "2025-09-30", "2025-10-29")],                      # a gvkey no company links to
               [("555", "2025-09-30", "2025-10-29"), (MSFT, "2025-09-30", None)])
    assert tables._report_history(con) == 0


def test_two_compustat_companies_of_one_cik_keep_the_earlier_day():
    """One CIK linked to two gvkeys that hold the same quarter: one row, the day the results were first public."""
    con = _con([("000002", "2025-09-30", "2025-10-30"), ("000001", "2025-09-30", "2025-10-29"),
                ("000003", "2025-09-30", "2025-10-29")], [],
               links=[("AAA", "1", "000001"), ("AAB", "1", "000002"), ("AAC", "1", "000003")])
    tables._report_history(con)
    assert _served(con) == [("1", date(2025, 9, 30), date(2025, 10, 29), "000001", wrds_fund.FUNDQ.name)]


def test_two_tickers_of_one_company_are_one_row():
    con = _con([("005567", "2025-04-30", "2025-05-28")], [])                  # HEI and HEI-A share cik and gvkey
    tables._report_history(con)
    assert _served(con) == [(HEI, date(2025, 4, 30), date(2025, 5, 28), "005567", wrds_fund.FUNDQ.name)]


def test_the_table_is_declared_everywhere_a_served_table_has_to_be():
    assert "earnings_report_history" in tables.TABLES
    assert read.KIND_OF_TABLE["earnings_report_history"] == "fundamentals"
    assert read.DATASET_OF_TABLE["earnings_report_history"] is None            # two sources write it
    need = catalog.NEEDS["fundamentals.report_history"]
    assert (need.table, need.day_column, need.key_column) == ("earnings_report_history", "period_end", "cik")
    assert need.reader is read.earnings_report_history
    assert "earnings_report_history" in wrds_fund.FUNDQ.feeds
    assert "earnings_report_history" not in wrds_fund.FUNDA.feeds              # the annual table has no ``rdq``
    assert "earnings_report_history" in uw_earnings.DATASET.feeds


@pytest.fixture
def fake(monkeypatch, http_mock):
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec_edgar, "SEC_DATA_BASE", "https://data.sec.test")
    fx.spine()
    fx.sec_routes(http_mock, {"789019": fx.msft_facts(), "46619": fx.hei_facts()})
    fx.run(companyfacts.NAME, mode="backfill", to="2026-10-26")
    conn = fx.FakeFundWrds()
    monkeypatch.setattr(spine_wrds, "_factory", lambda: conn)
    spine_wrds.reset()
    yield conn
    spine_wrds.reset()


def test_the_real_build_serves_the_snapshots_report_days_and_the_reader_returns_them(fake):
    check = fx.run(wrds_fund.FUNDQ.name, mode="backfill", to="2026-10-27")
    assert check["result"] == "changed", check["note"]
    assert fx.q("SELECT cik, period_end, report_date, gvkey, source FROM earnings_report_history "
                "ORDER BY cik, period_end") == [
        (HEI, date(2025, 4, 30), date(2025, 5, 28), "005567", wrds_fund.FUNDQ.name),
        (MSFT, date(2025, 6, 30), date(2025, 7, 30), "012141", wrds_fund.FUNDQ.name),
        (MSFT, date(2025, 9, 30), date(2025, 10, 29), "012141", wrds_fund.FUNDQ.name)]
    assert fx.q("SELECT kind, version FROM serving_schema_version") == [("fundamentals", serving.SERVING_SCHEMA_VERSION["fundamentals"])]
    rows = read.earnings_report_history(MSFT, start="2025-10-01")
    assert [(r["period_end"], r["report_date"], r["source"]) for r in rows] == [
        (date(2025, 9, 30), date(2025, 10, 29), wrds_fund.FUNDQ.name)]
    assert read.earnings_report_history("0000789019", end="2025-08-01")[0]["report_date"] == date(2025, 7, 30)


def test_a_file_built_before_the_table_existed_answers_no_rows(fake):
    fx.run(wrds_fund.FUNDQ.name, mode="backfill", to="2026-10-27")
    con = duckdb.connect(str(serving.live_path("fundamentals")))
    try:
        con.execute("DROP TABLE earnings_report_history")
    finally:
        con.close()
    assert read.earnings_report_history(MSFT) == []
