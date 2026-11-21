"""``audit_flag``: Audit Analytics' restatements, late filings and officer changes of our companies, one row per
event (#1181, step C of the WRDS plan; fundamentals serving version 6).

The rule is tested on the three staging tables directly, then once through the real build against the fake WRDS
worker (never WRDS). The coding the tests use is the measured one: a flag column is 0 or 1 (20 Nov 2026).
"""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from RevenueChaser.rcdata import read, serving
from RevenueChaser.rcdata.build.fundamentals import companyfacts, filings, tables, wrds_fund
from RevenueChaser.rcdata.build.spine import wrds as spine_wrds
from RevenueChaser.rcdata.needs import catalog

from . import fund_fixture as fx

AUDIT = wrds_fund.AUDIT
MSFT, HEI = "789019", "46619"
AS_OF = date(2026, 11, 20)
RESTATEMENTS, LATE, OFFICERS = "feed39_financial_restatements", "feed20_nt", "feed17_director_and_officer_chan"
SHOWN = "cik, kind, event_key, person_key, file_date, form, effective_date, period_start, period_end, action, flags"


def _con(rows: dict[str, list[dict]]) -> duckdb.DuckDBPyConnection:
    """A scratch connection with the three staged feeds (``rows``: part -> rows, a row's missing columns NULL) and
    our companies: MSFT, and HEI under two tickers."""
    con = duckdb.connect()
    con.execute("CREATE TABLE fundamental_company (ticker TEXT, cik TEXT)")
    con.executemany("INSERT INTO fundamental_company VALUES (?, ?)", [("MSFT", MSFT), ("HEI", HEI), ("HEI-A", HEI)])
    for part, (_, schema, _) in AUDIT.PARTS.items():
        cols = schema + wrds_fund.PROVENANCE
        con.execute(f"CREATE TEMP TABLE {AUDIT.STAGING[part]} ({', '.join(f'{c} {t}' for c, t in cols)})")
        for row in rows.get(part, []):
            full = {**{c: None for c, _ in schema}, **row, "source_as_of": AS_OF, "fetched_at": 1.0, "run_id": "w1"}
            con.execute(f"INSERT INTO {AUDIT.STAGING[part]} VALUES ({', '.join('?' for _ in cols)})",
                        [full[c] for c, _ in cols])
    return con


def _served(con) -> list[tuple]:
    return con.execute(f"SELECT {SHOWN} FROM audit_flag ORDER BY cik, kind, event_key, person_key").fetchall()


def test_a_restatement_is_served_with_its_span_and_the_flags_that_are_one():
    con = _con({RESTATEMENTS: [{
        "restatement_notification_key": "9001", "company_fkey": "789019", "file_date": "2025-08-01",
        "form_fkey": "8-K", "res_begin_date": "2024-07-01", "res_end_date": "2025-03-31", "res_accounting": "1",
        "res_fraud": "0", "res_adverse": "1", "res_sec_investigation": "1", "res_clerical_errors": "0",
        "res_other": "0", "res_improves": "0", "quarterly_restated_only": "1", "res_board_approval": "Y",
        "res_auditor_letter": "ND"}]})
    assert tables._audit_flags(con) == 1
    assert _served(con) == [(MSFT, "restatement", "9001", None, date(2025, 8, 1), "8-K", None, date(2024, 7, 1),
                             date(2025, 3, 31), None,
                             ["accounting", "adverse", "quarterly_only", "sec_investigation"])]
    assert con.execute("SELECT source, source_as_of, run_id FROM audit_flag").fetchall() == [
        (AUDIT.name, AS_OF, "w1")]


def test_a_zero_and_an_empty_flag_are_no_flag():
    """The measured coding is 0 / 1. A zero is not a flag, and neither is a value that is no number at all: the two
    Y / N / ND columns are staged but never read as a flag."""
    con = _con({RESTATEMENTS: [{"restatement_notification_key": "1", "company_fkey": MSFT,
                                "file_date": "2025-08-01", "res_fraud": "0", "res_adverse": None,
                                "res_accounting": "ND", "res_board_approval": "Y", "res_auditor_letter": "Y"}],
                OFFICERS: [{"do_change_key": "5", "do_off_pers_key": "1", "company_fkey": MSFT,
                            "file_date": "2026-09-24", "is_ceo": "0", "is_cfo": "1.0"}]})
    tables._audit_flags(con)
    assert [(r[1], r[-1]) for r in _served(con)] == [("officer_change", ["cfo"]), ("restatement", [])]


def test_an_officer_change_names_one_person_per_row_by_number_with_its_action_and_roles():
    con = _con({OFFICERS: [
        {"do_change_key": "5001", "do_off_pers_key": "2", "company_fkey": MSFT, "file_date": "2026-09-24",
         "form_fkey": "8-K", "action": "Resigned", "is_cfo": "1", "is_c_level": "1"},
        {"do_change_key": "5001", "do_off_pers_key": "1", "company_fkey": MSFT, "file_date": "2026-09-24",
         "form_fkey": "8-K", "eff_date": "2026-10-01", "action": "Appointed", "is_cfo": "1", "is_c_level": "1",
         "interim": "1", "is_bdmem_pers": "1", "is_ceo": "1", "is_chair": "1", "is_coo": "1",
         "is_president": "1"}]})
    tables._audit_flags(con)
    assert _served(con) == [
        (MSFT, "officer_change", "5001", "1", date(2026, 9, 24), "8-K", date(2026, 10, 1), None, None, "Appointed",
         ["board_member", "c_level", "ceo", "cfo", "chair", "coo", "interim", "president"]),
        (MSFT, "officer_change", "5001", "2", date(2026, 9, 24), "8-K", None, None, None, "Resigned",
         ["c_level", "cfo"])]


def test_a_late_filing_carries_the_period_it_is_late_for_when_that_is_a_day():
    """How ``pe_date_num`` is written is not measured: eight leading digits that are a day are one, anything else
    is no period and the row is served without it."""
    con = _con({LATE: [
        {"nt_notify_key": "7001", "company_fkey": HEI, "file_date": "2026-09-15", "form_fkey": "NT 10-Q",
         "pe_date_num": "20260731"},
        {"nt_notify_key": "7002", "company_fkey": HEI, "file_date": "2026-09-16", "form_fkey": "NT 10-K",
         "pe_date_num": "20260731.0"},
        {"nt_notify_key": "7003", "company_fkey": HEI, "file_date": "2026-09-17", "pe_date_num": "20261331"},
        {"nt_notify_key": "7004", "company_fkey": HEI, "file_date": "2026-09-18", "pe_date_num": "n/a"},
        {"nt_notify_key": "7005", "company_fkey": HEI, "file_date": "2026-09-19"}]})
    tables._audit_flags(con)
    assert [(r[2], r[5], r[8], r[10]) for r in _served(con)] == [
        ("7001", "NT 10-Q", date(2026, 7, 31), []), ("7002", "NT 10-K", date(2026, 7, 31), []),
        ("7003", None, None, []), ("7004", None, None, []), ("7005", None, None, [])]


def test_only_our_companies_are_served_and_two_tickers_of_one_company_are_one_row():
    """``company_fkey`` meets the CIK with or without leading zeros; 4661 is another company, not a prefix."""
    con = _con({LATE: [
        {"nt_notify_key": "1", "company_fkey": "0000046619", "file_date": "2026-09-15"},
        {"nt_notify_key": "2", "company_fkey": "46619", "file_date": "2026-09-01"},
        {"nt_notify_key": "3", "company_fkey": "4661", "file_date": "2026-09-02"},
        {"nt_notify_key": "4", "company_fkey": "999999", "file_date": "2026-09-03"},
        {"nt_notify_key": "5", "company_fkey": None, "file_date": "2026-09-04"}]})
    assert tables._audit_flags(con) == 2
    assert [(r[0], r[2]) for r in _served(con)] == [(HEI, "1"), (HEI, "2")]


def test_a_row_with_no_filing_day_or_no_key_is_left_out():
    con = _con({RESTATEMENTS: [
        {"restatement_notification_key": "1", "company_fkey": MSFT, "file_date": None, "res_fraud": "1"},
        {"restatement_notification_key": None, "company_fkey": MSFT, "file_date": "2025-08-01", "res_fraud": "1"}]})
    assert tables._audit_flags(con) == 0


def test_the_table_takes_no_fourth_kind():
    con = _con({})
    tables._audit_flags(con)
    with pytest.raises(duckdb.ConstraintException):
        con.execute("INSERT INTO audit_flag (cik, kind, event_key, file_date, source) "
                    "VALUES ('1', 'rumour', '1', DATE '2026-01-01', 'x')")


def test_the_table_is_declared_everywhere_a_served_table_has_to_be():
    assert "audit_flag" in tables.TABLES
    assert read.KIND_OF_TABLE["audit_flag"] == "fundamentals"
    assert read.DATASET_OF_TABLE["audit_flag"] == AUDIT.name                    # one source writes it
    need = catalog.NEEDS["fundamentals.audit_flags"]
    assert (need.table, need.day_column, need.key_column) == ("audit_flag", "file_date", "cik")
    assert need.reader is read.audit_flags
    assert AUDIT.feeds == ("audit_flag",)
    assert "audit_flag" in companyfacts.DATASET.feeds and "audit_flag" in filings.DATASET.feeds   # cut to the companies
    assert set(AUDIT.SERVED) == set(AUDIT.PARTS)
    for part, spec in AUDIT.SERVED.items():
        asked = {c for c, _ in AUDIT.PARTS[part][1]}
        assert set(spec["flags"]) <= asked, part
        assert list(spec["flags"].values()) == sorted(spec["flags"].values()), part     # ``flags`` reads in order
    # The two Y / N / ND columns are mostly "not disclosed" (measured): staged, never a flag.
    assert not {"res_board_approval", "res_auditor_letter"} & set(AUDIT.SERVED[RESTATEMENTS]["flags"])


@pytest.fixture
def fake(monkeypatch):
    fx.spine()
    conn = fx.FakeFundWrds()
    monkeypatch.setattr(spine_wrds, "_factory", lambda: conn)
    spine_wrds.reset()
    yield conn
    spine_wrds.reset()


def test_the_real_build_serves_the_snapshots_events_and_the_reader_returns_them(fake):
    check = fx.run(AUDIT.name, mode="backfill", to="2026-10-27")
    assert check["result"] == "changed", check["note"]
    assert fx.q(f"SELECT {SHOWN} FROM audit_flag ORDER BY cik, kind, event_key, person_key") == [
        (HEI, "late_filing", "7001", None, date(2026, 9, 15), "NT 10-Q", None, None, date(2026, 7, 31), None, []),
        (HEI, "officer_change", "5002", "3", date(2025, 2, 3), "8-K", None, None, None, "Retired", ["ceo"]),
        (MSFT, "officer_change", "5001", "1", date(2026, 9, 24), "8-K", date(2026, 10, 1), None, None, "Appointed",
         ["cfo"]),
        (MSFT, "officer_change", "5001", "2", date(2026, 9, 24), "8-K", None, None, None, "Resigned", ["cfo"]),
        (MSFT, "restatement", "9001", None, date(2025, 8, 1), "8-K", None, date(2024, 7, 1), date(2025, 3, 31),
         None, ["accounting"])]
    assert fx.q("SELECT kind, version FROM serving_schema_version") == [("fundamentals", 7)]
    rows = read.audit_flags("0000789019")
    assert [(r["kind"], r["event_key"], r["person_key"]) for r in rows] == [
        ("officer_change", "5001", "1"), ("officer_change", "5001", "2"), ("restatement", "9001", None)]
    assert rows[0]["flags"] == ["cfo"] and rows[0]["source"] == AUDIT.name
    assert [r["cik"] for r in read.audit_flags(kind="late_filing")] == [HEI]
    assert [r["event_key"] for r in read.audit_flags(start="2026-09-20")] == ["5001", "5001"]
    assert [r["event_key"] for r in read.audit_flags(HEI, end="2025-12-31")] == ["5002"]


def test_a_file_built_before_the_table_existed_answers_no_rows(fake):
    fx.run(AUDIT.name, mode="backfill", to="2026-10-27")
    con = duckdb.connect(str(serving.live_path("fundamentals")))
    try:
        con.execute("DROP TABLE audit_flag")
    finally:
        con.close()
    assert read.audit_flags(MSFT) == []
