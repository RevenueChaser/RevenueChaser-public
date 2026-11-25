"""Ownership names a symbol by the day its row is dated (K-E step 2, PR 3; decisions C2 and D1 of 24 Nov 2026).

FINRA, FTD, IBKR and Reg SHO write the symbol a security traded under on the row's day, and a Form 4 the symbol its
filer wrote. Compustat's ``tic`` periods in the spine's ``security_history`` say which security that symbol was on
that day: an old symbol inside its period is the security's current ticker (``spine:renamed``), a reused ticker's
row from before its current holder took it goes to the holder of that day (``spine:reused``) or, with no holder
known and more than the grace window early, to no one. The periods are the live spine's own (24 Nov 2026).
"""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from revenuechaser.rcdata import serving
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.ownership import common, finra, form4, ftd, ibkr, regsho

from . import ownership_fixture as ox

D = date
SRC = "wrds/sec_idhist"
TIC = [  # (current ticker, gvkey, old or current symbol, valid_from, valid_to)
    ("BNY", "002019", "BK", D(1986, 12, 14), D(2026, 5, 21)), ("BNY", "002019", "BNY", D(2026, 5, 21), None),
    ("IFLN", "178901", "PHB", D(2007, 11, 15), D(2026, 2, 23)), ("IFLN", "178901", "IFLN", D(2026, 2, 23), None),
    # Barrick held GOLD from 2019 to 2025 and is B since; Gold.com (A-Mark) took GOLD on 2025-12-02.
    ("B", "002055", "GOLD", D(2019, 1, 2), D(2025, 5, 9)), ("B", "002055", "B", D(2025, 5, 9), None),
    ("GOLD", "019172", "AMRK", D(2013, 11, 12), D(2025, 12, 2)), ("GOLD", "019172", "GOLD", D(2025, 12, 2), None),
    # Indivior took SUPN on 2026-11-03; Supernus, its holder before, carries no period the spine links.
    ("SUPN", "022410", "INDV", D(2023, 6, 12), D(2026, 11, 3)), ("SUPN", "022410", "SUPN", D(2026, 11, 3), None),
    # KRMA became CPTL on 2026-07-22, and the spine's ETF list still holds KRMA too.
    ("CPTL", "027661", "KRMA", D(2016, 7, 8), D(2026, 7, 22)), ("CPTL", "027661", "CPTL", D(2026, 7, 22), None),
]
HISTORY = [(t, "tic", v, f, to, g, "01", SRC) for t, g, v, f, to in TIC]
STOCKS = ("MSFT", "BNY", "BNY-PA", "B", "GOLD", "SUPN")
CIKS = {"MSFT": "789019", "BNY": "1390777", "BNY-PA": "1390777", "B": "756894", "GOLD": "1591588",
        "SUPN": "1625297"}
ETFS = ("IFLN", "CPTL", "KRMA")


@pytest.fixture
def spine():
    ox.make_spine(tickers=STOCKS, ciks=CIKS, history=HISTORY, etfs=ETFS)


def _named(rows: list[tuple[str, date]], naming=common.BY_SYMBOL._replace(date="day")) -> dict:
    """``{(symbol, day): (ticker, ticker_source)}`` of a table of ``rows`` named again from the spine."""
    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE t (symbol TEXT, day DATE, ticker TEXT, ticker_source TEXT)")
        con.executemany("INSERT INTO t VALUES (?, ?, NULL, NULL)", rows)
        common.restate(con, "t", naming, [], "x")
        got = con.execute("SELECT symbol, day, ticker, ticker_source FROM t").fetchall()
    finally:
        con.close()
    assert len(got) == len(rows)            # a row matches one map row, never two
    return {(s, d): (t, src) for s, d, t, src in got}


def test_an_old_symbol_inside_its_period_is_the_current_ticker(spine):
    got = _named([("PHB", D(2025, 6, 30)), ("BK", D(2026, 5, 15)), ("BK", D(2026, 6, 15)), ("PHB", D(2007, 1, 2))])
    assert got[("PHB", D(2025, 6, 30))] == ("IFLN", common.RENAMED)
    assert got[("BK", D(2026, 5, 15))] == ("BNY", common.RENAMED)
    assert got[("BK", D(2026, 6, 15))] == (None, None)      # after the period BK names no one
    assert got[("PHB", D(2007, 1, 2))] == (None, None)      # before it too


def test_a_symbol_the_spine_still_lists_is_the_new_ticker_inside_its_old_period(spine):
    got = _named([("KRMA", D(2025, 6, 30))])
    assert got[("KRMA", D(2025, 6, 30))] == ("CPTL", common.RENAMED)


def test_a_reused_ticker_names_the_holder_of_the_day(spine):
    got = _named([("GOLD", D(2024, 6, 28)), ("GOLD", D(2025, 8, 15)), ("GOLD", D(2026, 1, 15))])
    assert got[("GOLD", D(2024, 6, 28))] == ("B", common.REUSED)        # Barrick's
    assert got[("GOLD", D(2025, 8, 15))] == (None, None)                # nobody's: between the two holders
    assert got[("GOLD", D(2026, 1, 15))] == ("GOLD", common.EXACT)      # Gold.com's


def test_a_row_before_its_holder_took_the_ticker_with_no_holder_known_is_named_no_one(spine):
    got = _named([("SUPN", D(2025, 6, 30)), ("SUPN", D(2026, 11, 13))])
    assert got[("SUPN", D(2025, 6, 30))] == (None, None)                # Supernus's, not Indivior's
    assert got[("SUPN", D(2026, 11, 13))] == ("SUPN", common.EXACT)


def test_a_row_a_few_days_before_the_start_keeps_the_new_holder(spine):
    """Compustat's change day can trail the source's: IBKR lists a new ticker 1-3 days early."""
    got = _named([("SUPN", D(2026, 11, 1)), ("GOLD", D(2025, 11, 28)), ("SUPN", D(2026, 10, 26))])
    assert got[("SUPN", D(2026, 11, 1))] == ("SUPN", common.EXACT)
    assert got[("GOLD", D(2025, 11, 28))] == ("GOLD", common.EXACT)
    assert got[("SUPN", D(2026, 10, 26))] == (None, None)               # 8 days early: past the window


def test_a_ticker_with_no_history_and_an_undated_naming_are_named_as_today(spine):
    assert _named([("MSFT", D(1990, 1, 2))])[("MSFT", D(1990, 1, 2))] == ("MSFT", common.EXACT)
    undated = _named([("GOLD", D(2024, 6, 28)), ("PHB", D(2025, 6, 30))], common.BY_SYMBOL)
    assert undated == {("GOLD", D(2024, 6, 28)): ("GOLD", common.EXACT), ("PHB", D(2025, 6, 30)): (None, None)}


def test_a_form4_old_symbol_with_the_issuers_cik_is_the_current_ticker(spine):
    """BNY's CIK holds two tickers, so the CIK alone names no one; the old symbol BK inside its period does, but
    only for BNY's own CIK."""
    con = duckdb.connect()
    try:
        con.execute("CREATE TABLE t (issuer_cik TEXT, symbol TEXT, filed DATE, ticker TEXT, ticker_source TEXT)")
        con.executemany("INSERT INTO t VALUES (?, ?, ?, NULL, NULL)", [
            ("1390777", "BK", D(2025, 3, 3)), ("1390777", "BK", D(2026, 6, 15)), ("789019", "BK", D(2025, 3, 3)),
            ("789019", "MSFT", D(2025, 3, 3))])
        common.restate(con, "t", common.BY_ISSUER._replace(date="filed"), [], "x")
        got = con.execute("SELECT issuer_cik, symbol, filed, ticker, ticker_source FROM t ORDER BY ALL").fetchall()
    finally:
        con.close()
    assert got == [("1390777", "BK", D(2025, 3, 3), "BNY", common.RENAMED),
                   ("1390777", "BK", D(2026, 6, 15), None, None),
                   ("789019", "BK", D(2025, 3, 3), "MSFT", common.ISSUER_CIK),
                   ("789019", "MSFT", D(2025, 3, 3), "MSFT", common.EXACT)]


@pytest.mark.parametrize("mod, col", [(finra, "settlement_date"), (ftd, "settlement_date"), (ibkr, "session_date"),
                                      (regsho, "list_date"), (form4, "filed")])
def test_each_source_names_its_rows_by_its_own_date(mod, col):
    assert mod.NAMING.date == col and col in dict(mod.SERVED)


def test_a_finra_build_names_an_old_etf_symbol_by_its_settlement_date(monkeypatch, http_mock, spine):
    monkeypatch.setenv("RC_FINRA_API_BASE", "https://finra.test")
    day = "2025-06-30"
    ox.Finra({day: [ox.finra_row("PHB", day, 5_000), ox.finra_row("GOLD", day, 7_000),
                    ox.finra_row("MSFT", day, 9_000)]}).install(http_mock)
    assert base.run_request({"dataset": finra.NAME, "params": {"as_of": "2025-07-10"}})["result"] == "changed"
    with serving.open_read("ownership") as con:
        assert con.execute("SELECT symbol, ticker, ticker_source FROM finra_short_interest ORDER BY symbol"
                           ).fetchall() == [("GOLD", None, None), ("MSFT", "MSFT", common.EXACT),
                                            ("PHB", "IFLN", common.RENAMED)]
