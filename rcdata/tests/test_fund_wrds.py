"""The fundamentals layer's WRDS datasets against a fake worker (never WRDS): ``wrds/fundq`` and ``wrds/funda``, a
monthly snapshot whose changes against the one before are the revision table; both a check of the SEC values (the
agreement notes), attended, one login per process."""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from RevenueChaser.core.providers import sec_edgar
from RevenueChaser.rcdata import ops
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.fundamentals import common, companyfacts, tables, wrds_fund
from RevenueChaser.rcdata.build.spine import wrds as spine_wrds

from . import fund_fixture as fx

GVKEYS = "gvkey IN ('005567', '010581', '012141', '012142')"
COMPUSTAT = "indfmt = 'INDL' AND datafmt = 'STD' AND popsrc = 'D' AND consol = 'C'"


@pytest.fixture
def fake(monkeypatch, http_mock):
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec_edgar, "SEC_DATA_BASE", "https://data.sec.test")
    fx.spine()
    fx.sec_routes(http_mock, {"789019": fx.msft_facts(), "46619": fx.hei_facts()})
    fx.run(companyfacts.NAME, mode="backfill", to="2026-10-26")
    conn, logins = fx.FakeFundWrds(), []

    def factory():
        logins.append(1)
        return conn
    monkeypatch.setattr(spine_wrds, "_factory", factory)
    spine_wrds.reset()
    yield conn, logins
    spine_wrds.reset()


def test_one_login_the_tier_a_gvkeys_and_the_compustat_filters(fake):
    conn, logins = fake
    for name in (wrds_fund.FUNDQ.name, wrds_fund.FUNDA.name):
        check = fx.run(name, mode="backfill", to="2026-10-27")
        assert check["result"] == "changed", check["note"]
    assert logins == [1] and ops.calls_today("wrds") == 2
    fundq, funda = conn.queries
    assert "FROM comp.fundq" in fundq and GVKEYS in fundq and COMPUSTAT in fundq
    assert "datadate >= DATE '2016-10-27'" in fundq                     # ten years
    assert "FROM comp.funda" in funda and GVKEYS in funda and COMPUSTAT in funda


def test_a_scheduled_run_is_skipped_without_a_login(fake):
    conn, logins = fake
    row = base.run_request({"dataset": wrds_fund.FUNDQ.name, "requested_by": "schedule",
                            "params": {"as_of": "2026-10-27"}})
    assert row["result"] == "skipped" and logins == [] and conn.queries == []


def test_the_monthly_snapshots_make_the_revision_table(fake):
    conn, _ = fake
    check = fx.run(wrds_fund.FUNDQ.name, mode="backfill", to="2026-10-27")
    # MSFT's Sep-2025 quarter agrees with the SEC on all three; HEI's revenue does not.
    assert "revenue 1 of 2, net income 1 of 1, diluted EPS 1 of 1 agree" in check["note"]
    assert fx.q("SELECT count(*) FROM fundamental_revision") == [(0,)]
    check = fx.run(wrds_fund.FUNDQ.name, "2026-11-10")
    assert len(conn.queries) == 1 and "snapshot of 2026-10-27 is current" in check["note"]
    conn.month = 2
    check = fx.run(wrds_fund.FUNDQ.name, "2026-11-27")
    assert len(conn.queries) == 2
    assert fx.q("SELECT cik, gvkey, source, datadate, item, old_value, new_value, old_as_of, new_as_of "
                "FROM fundamental_revision ORDER BY datadate") == [
        ("789019", "012141", wrds_fund.FUNDQ.name, date(2025, 6, 30), "revtq", 0.075, None, date(2026, 10, 27),
         date(2026, 11, 27)),
        ("789019", "012141", wrds_fund.FUNDQ.name, date(2025, 9, 30), "niq", 0.027, 0.0272, date(2026, 10, 27),
         date(2026, 11, 27))]                                    # the new quarter is not a revision
    assert "2 revision(s) in the snapshot of 2026-11-27 against 2026-10-27" in check["note"]


def test_funda_agrees_with_the_sec(fake):
    check = fx.run(wrds_fund.FUNDA.name, mode="backfill", to="2026-10-27")
    assert "revenue 1 of 1, net income 1 of 1, diluted EPS 1 of 1 agree" in check["note"]




def test_funda_is_compared_with_the_value_the_year_first_reported_277():
    # MSFT FY2017: 96,571 M served (the ASC 606 restatement in the FY2018 10-K), 89,950 M first reported, which is
    # what Compustat's funda keeps. The annual check compares the first-reported value; a fact with none, its own.
    con = duckdb.connect()
    tables.create(con, "fundamental_fact")
    con.execute("CREATE TABLE fundamental_company (cik TEXT, gvkey TEXT, sic TEXT, gsector TEXT, us_gaap BOOLEAN)")
    con.execute("INSERT INTO fundamental_company VALUES ('1', 'g1', '7372', '45', true), "
                "('2', 'g2', '7372', '45', true)")
    con.execute("CREATE TABLE stg (gvkey TEXT, datadate DATE, revt DOUBLE)")
    con.execute("INSERT INTO stg VALUES ('g1', DATE '2017-06-30', 89950), ('g2', DATE '2017-06-30', 500)")
    for cik, value, first in (("1", 96_571e6, 89_950e6), ("2", 500e6, None)):
        con.execute("INSERT INTO fundamental_fact (cik, field, period_type, period_end, value, unit, accn, filed, "
                    "derived, preliminary, source, first_value) VALUES (?, 'revenue', 'annual', DATE '2017-06-30', "
                    "?, 'USD', 'a', DATE '2018-08-03', false, false, 'sec/companyfacts', ?)", [cik, value, first])
    assert wrds_fund.agreement(con, "stg", "revt", "revenue", "annual", None, first_reported=True) == (2, 2)
    assert wrds_fund.agreement(con, "stg", "revt", "revenue", "annual", None) == (2, 1)


def test_a_held_raw_snapshot_is_typed_again_not_asked_again_503():
    # A raw-only Monday run, then Tuesday: the answer Monday holds is Tuesday's, with no WRDS query.
    monday, tuesday = date(2026, 11, 9), date(2026, 11, 10)
    raw = wrds_fund.FUNDA.raw_path(monday)
    assert wrds_fund.FUNDA.held(tuesday) == []
    base.write_raw_json(common.meta_path(raw), {"as_of": monday.isoformat(), "rows": 1})
    assert wrds_fund.FUNDA.held(tuesday) == []                              # a sidecar alone is no answer
    raw.write_bytes(b"")
    assert wrds_fund.FUNDA.held(tuesday) == [raw]
    assert wrds_fund.FUNDA.held(date(2026, 12, 9)) == []                    # older than SNAPSHOT_DAYS: asked again
    seg = wrds_fund.SEGMENTS
    first = seg.raw_path(monday, "wrds_segmerged")
    base.write_raw_json(common.meta_path(first), {"as_of": monday.isoformat()})
    first.write_bytes(b"")
    assert seg.held(tuesday) == []                                          # every part, or none


def _agreement_store(rows: list[tuple]) -> duckdb.DuckDBPyConnection:
    """A store with one SEC fact per row ``(cik, sic, field, value[, gsector[, us_gaap]])`` on 2024-12-31, its
    gvkey ``g<cik>``. ``gsector`` defaults to the SIC's own sector family, ``us_gaap`` to True."""
    con = duckdb.connect()
    tables.create(con, "fundamental_fact")
    con.execute("CREATE TABLE fundamental_company (cik TEXT, gvkey TEXT, sic TEXT, gsector TEXT, us_gaap BOOLEAN)")
    for row in rows:
        cik, sic, field, value = row[:4]
        gsector = row[4] if len(row) > 4 else ("40" if 6000 <= int(sic) <= 6799 else "20")
        us_gaap = row[5] if len(row) > 5 else True
        con.execute("INSERT INTO fundamental_company VALUES (?, ?, ?, ?, ?)",
                    [cik, f"g{cik}", sic, gsector, us_gaap])
        con.execute("INSERT INTO fundamental_fact (cik, field, period_type, period_end, value, unit, accn, filed, "
                    "derived, preliminary, source) VALUES (?, ?, 'annual', DATE '2024-12-31', ?, 'USD', 'a', "
                    "DATE '2025-02-01', false, false, 'sec/companyfacts')", [cik, field, value])
    return con


def test_a_bank_is_left_out_of_the_revenue_agreement_277():
    # JPM 2024: served revenue is net (177,556 M), Compustat's revt gross. A bank year is not a disagreement.
    con = _agreement_store([("19617", "6021", "revenue", 177_556e6), ("789019", "7372", "revenue", 245_122e6)])
    con.execute("CREATE TABLE stg (gvkey TEXT, datadate DATE, revt DOUBLE)")
    con.execute("INSERT INTO stg VALUES ('g19617', DATE '2024-12-31', 278906), ('g789019', DATE '2024-12-31', 245122)")
    assert wrds_fund.agreement(con, "stg", "revt", "revenue", "annual", None, financials=False) == (1, 1)
    assert wrds_fund.agreement(con, "stg", "revt", "revenue", "annual", None) == (2, 1)


def test_the_whole_financials_sector_is_left_out_of_the_revenue_agreement_277():
    """Measured 21 Nov 2026: GICS sector 40 agrees on 51.5% of its annual revenue pairs against ~86% for the rest,
    and the always-disagreeing names include an insurer, a broker and a mortgage REIT, whose SEC SIC is outside
    ``BANK_SIC``. The rule is the sector, not the SIC band."""
    con = _agreement_store([("1", "6311", "revenue", 50e6),      # life insurer: sector 40, SIC above 6199
                            ("2", "6798", "revenue", 30e6),      # mortgage REIT carried as sector 40
                            ("3", "6211", "revenue", 20e6),      # broker-dealer
                            ("4", "7372", "revenue", 245_122e6)])
    con.execute("CREATE TABLE stg (gvkey TEXT, datadate DATE, revt DOUBLE)")
    con.execute("INSERT INTO stg VALUES ('g1', DATE '2024-12-31', 120), ('g2', DATE '2024-12-31', 67), "
                "('g3', DATE '2024-12-31', 29), ('g4', DATE '2024-12-31', 245122)")
    assert wrds_fund.agreement(con, "stg", "revt", "revenue", "annual", None, financials=False) == (1, 1)
    assert wrds_fund.agreement(con, "stg", "revt", "revenue", "annual", None) == (4, 1)


def test_a_bank_sic_without_a_gics_sector_is_still_left_out_277():
    # The spine has no GICS for the filer: BANK_SIC stays the fallback, and an unknown sector is never a reason.
    con = _agreement_store([("1", "6021", "revenue", 50e6, None), ("2", "7372", "revenue", 100e6, None)])
    con.execute("CREATE TABLE stg (gvkey TEXT, datadate DATE, revt DOUBLE)")
    con.execute("INSERT INTO stg VALUES ('g1', DATE '2024-12-31', 140), ('g2', DATE '2024-12-31', 100)")
    assert wrds_fund.agreement(con, "stg", "revt", "revenue", "annual", None, financials=False) == (1, 1)


def test_a_non_us_gaap_filer_is_left_out_of_every_item_277():
    """AZUL and LKFT disagreed in all ten of their years because our side reads another taxonomy's total
    (``us_gaap`` False), not because Compustat or the extraction is wrong. NULL is unknown and stays compared."""
    con = _agreement_store([("1", "4512", "net_income", 50e6, "20", False),
                            ("2", "3711", "net_income", 90e6, "20", True),
                            ("3", "3711", "net_income", 40e6, "20", None)])
    con.execute("CREATE TABLE stg (gvkey TEXT, datadate DATE, ni DOUBLE)")
    con.execute("INSERT INTO stg VALUES ('g1', DATE '2024-12-31', 180), ('g2', DATE '2024-12-31', 90), "
                "('g3', DATE '2024-12-31', 40)")
    assert wrds_fund.agreement(con, "stg", "ni", "net_income", "annual", None) == (2, 2)
    # and out of the revenue count too, where the sector rule is on as well
    assert wrds_fund.agreement(con, "stg", "ni", "net_income", "annual", None, financials=False) == (2, 2)


def test_total_debt_is_compared_as_long_term_plus_current_277():
    con = _agreement_store([("1", "3711", "total_debt", 150e6), ("2", "3711", "total_debt", 90e6),
                            ("3", "3711", "total_debt", 40e6)])
    con.execute("CREATE TABLE stg (gvkey TEXT, datadate DATE, dltt DOUBLE, dlc DOUBLE)")
    con.execute("INSERT INTO stg VALUES ('g1', DATE '2024-12-31', 120, 30), ('g2', DATE '2024-12-31', 80, 30), "
                "('g3', DATE '2024-12-31', 40, NULL)")                # g3: no current item, not compared
    assert wrds_fund.agreement(con, "stg", ("dltt", "dlc"), "total_debt", "annual", None) == (2, 1)
