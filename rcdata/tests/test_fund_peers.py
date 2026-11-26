"""``peer_group`` (build plan PR 12): each Tier A company's ``K`` nearest companies on the GICS ladder (sub-industry,
then industry, industry group, sector), the closest annual revenue first within a rung."""
from __future__ import annotations

from datetime import date

import duckdb

from revenuechaser.rcdata.build import ticker_history
from revenuechaser.rcdata.build.fundamentals import tables

from . import fund_fixture as fx

# (cik, tickers, gsector, ggroup, gind, gsubind, annual revenue or None)
COMPANIES = [
    ("1", ["AAA", "AAA-B"], "45", "4510", "451030", "45103020", 100.0),
    ("2", ["BBB"], "45", "4510", "451030", "45103020", 1_000.0),
    ("3", ["CCC"], "45", "4510", "451030", "45103020", 120.0),
    ("8", ["HHH"], "45", "4510", "451030", "45103020", None),           # no revenue: last in its rung
    ("4", ["DDD"], "45", "4510", "451030", "45103010", 100.0),          # same industry
    ("5", ["EEE"], "45", "4510", "451020", "45102010", 100.0),          # same industry group
    ("6", ["FFF"], "45", "4520", "452010", "45201010", 100.0),          # same sector
    ("7", ["GGG"], "20", "2010", "201010", "20101010", 100.0),          # another sector
]


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    tables.create(con, "fundamental_company")
    tables.create(con, "fundamental_fact")
    for cik, tickers, gsector, ggroup, gind, gsubind, revenue in COMPANIES:
        for t in tickers:
            con.execute("INSERT INTO fundamental_company (ticker, cik, gsector, ggroup, gind, gsubind) "
                        "VALUES (?, ?, ?, ?, ?, ?)", [t, cik, gsector, ggroup, gind, gsubind])
        if revenue is not None:
            for year, value in ((2024, revenue / 2), (2025, revenue)):          # the newest year counts
                con.execute("INSERT INTO fundamental_fact (cik, field, period_type, fiscal_year, period_end, value, "
                            "accn, filed, derived, preliminary, source) VALUES (?, 'revenue', 'annual', ?, ?, ?, "
                            "'a', DATE '2026-01-01', false, false, 'sec/companyfacts')",
                            [cik, year, f"{year}-12-31", value])
    return con


def test_the_ladder_fills_from_the_sub_industry_out_by_revenue():
    con = _con()
    assert tables._peers(con, k=5) > 0
    rows = con.execute("SELECT rank, peer_ticker, level, peer_revenue FROM peer_group WHERE cik = '1' "
                       "ORDER BY rank").fetchall()
    assert rows == [(1, "CCC", "gsubind", 120.0), (2, "BBB", "gsubind", 1_000.0), (3, "HHH", "gsubind", None),
                    (4, "DDD", "gind", 100.0), (5, "EEE", "ggroup", 100.0)]
    assert con.execute("SELECT DISTINCT ticker, revenue FROM peer_group WHERE cik = '1'").fetchall() == [
        ("AAA", 100.0)]                                                  # the company's shortest ticker
    assert con.execute("SELECT count(*) FROM peer_group WHERE cik = '7'").fetchone() == (0,)   # alone in its sector


def test_the_company_is_not_named_by_a_symbol_it_used_to_go_by(monkeypatch):
    """#1545: AAA is the shorter of the company's two tickers, so the old rule named it AAA -- but the spine holds
    a closed ``tic`` period saying AAA was what the security now called AAA-B went by. A symbol the company left
    behind never names it, and the shortest of what is left does."""
    con = _con()
    monkeypatch.setattr(ticker_history, "periods",
                        lambda con=None: [ticker_history.Period("AAA", date(2020, 1, 1), date(2025, 6, 1),
                                                                "AAA-B", "012141", "01")])
    assert tables._peers(con, k=5) > 0
    assert con.execute("SELECT DISTINCT ticker FROM peer_group WHERE cik = '1'").fetchall() == [("AAA-B",)]
    # The peers of the other companies name it by that ticker too: one name per company, everywhere.
    assert con.execute("SELECT DISTINCT peer_ticker FROM peer_group WHERE peer_cik = '1'").fetchall() == [("AAA-B",)]


def test_a_company_all_of_whose_symbols_are_old_keeps_the_shortest(monkeypatch):
    """A name beats none: the drop never leaves a company out of ``peer_group`` altogether (#1545)."""
    con = _con()
    monkeypatch.setattr(ticker_history, "periods",
                        lambda con=None: [ticker_history.Period(t, date(2020, 1, 1), date(2025, 6, 1), "ZZZ",
                                                                "012141", "01") for t in ("AAA", "AAA-B")])
    assert tables._peers(con, k=5) > 0
    assert con.execute("SELECT DISTINCT ticker FROM peer_group WHERE cik = '1'").fetchall() == [("AAA",)]


def test_the_build_serves_it():
    fx.spine()
    fx.run(tables.NAME, "2026-10-28")
    assert fx.q("SELECT ticker, peer_ticker, rank, level FROM peer_group WHERE cik = '789019'") == [
        ("MSFT", "ORCL", 1, "gsubind")]
