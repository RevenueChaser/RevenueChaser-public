"""``etf``: where the fund file, N-CEN, Compustat and TickerInside disagree (review of 24 Nov 2026, avo's 1A-4A).

- a rename by the SEC fund file is taken only where Compustat agrees or is silent (H1, M5);
- two etf rows on one series, and a series the fund file gives another, are issues and nothing is overwritten;
- a trust takes TickerInside's trust class, else its name's, and ``TRUST_SQL`` is the trust rule itself (M1, M2);
- the option-income guard holds on the derivative path (L1), and a German bank's note is an ETN (L2).

Built from the staging tables directly, as ``test_spine_etf.py``'s not-a-fund tests are.
"""
from __future__ import annotations

from datetime import date

import duckdb

from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.spine import av_listing, etf, etf_holdings, ncen, sec_tickers_mf, security, stage

from .test_spine_etf_adv import put_secd, series

DAY = date(2026, 11, 2)


def _con(ncen_rows=(), mf_rows=(), av=(), sec=(), filers=()) -> duckdb.DuckDBPyConnection:
    """The staging tables ``etf.rows`` reads: N-CEN ``(ticker, series_id, name)``, the fund file ``(ticker,
    series_id, is_etf)``, Alpha Vantage ``(ticker, name)``, ``security`` ``(ticker, cik, name, type)``, filer CIKs."""
    con = duckdb.connect()
    stage.create(con, av_listing.STAGING, av_listing.SCHEMA)
    stage.create(con, ncen.STAGING, ncen.SCHEMA)
    stage.create(con, ncen.FILERS, ncen.FILER)
    stage.create(con, "stg_sec_mf", sec_tickers_mf.SCHEMA)
    con.execute("CREATE TABLE security (ticker TEXT, cik TEXT, name TEXT, security_type TEXT, type_source TEXT, "
                "source_as_of DATE, fetched_at DOUBLE)")
    for t, s, name in ncen_rows:
        con.execute(f"INSERT INTO {ncen.STAGING} (ticker, cik, series_id, fund_name, is_etf, filing_date, accession) "
                    "VALUES (?, '1000', ?, ?, TRUE, DATE '2026-03-01', 'a-' || ?)", [t, s, name, s])
    for t, s, is_etf in mf_rows:
        con.execute("INSERT INTO stg_sec_mf (ticker, cik, series_id, class_id, is_etf) VALUES (?, '1000', ?, ?, ?)",
                    [t, s, "C-" + t, is_etf])
    for t, name in av:
        con.execute(f"INSERT INTO {av_listing.STAGING} (ticker, symbol, name, asset_type, status) "
                    "VALUES (?, ?, ?, 'ETF', 'Active')", [t, t, name])
    for t, cik, name, typ in sec:
        con.execute("INSERT INTO security VALUES (?, ?, ?, ?, 'name_rule(ETF/ETN)', NULL, NULL)", [t, cik, name, typ])
    for cik in filers:
        con.execute(f"INSERT INTO {ncen.FILERS} (cik) VALUES (?)", [cik])
    return con


def _rows(con, issues: list | None = None) -> dict[str, dict]:
    ctx = base.RunContext(run_id="r", dataset=security.NAME, as_of=DAY)
    return {r["ticker"]: r for r in etf.rows(ctx, con, [] if issues is None else issues)}


def _priced(*tickers: str) -> None:
    """Compustat prices each ticker on its newest day, each under its own series."""
    put_secd([r for i, t in enumerate(tickers) for r in series(f"0700{i:02d}", "01", t, 3, 1e6)])


# ── The rename rule: the fund file's ticker, where Compustat agrees or is silent ────────────────────────────

def test_the_fund_files_ticker_is_taken_only_where_compustat_agrees_or_is_silent():
    """H1 (avo's 1A, 24 Nov 2026): the fund file lists Franklin's FLGB as FLUK, a ticker Compustat has never priced,
    while it still prices FLGB. N-CEN's ticker stays and the disagreement is one issue. SPLG -> SPYM (Compustat
    prices only SPYM), APLZ -> APLX (Compustat prices both) and a rename Compustat knows nothing of are taken; so is
    S4's GLOW -> BMDL, because GLOW is S5's ticker: Compustat's GLOW is that fund's, not S4's."""
    _priced("FLGB", "SPYM", "APLZ", "APLX", "GLOW")
    con = _con(ncen_rows=[("FLGB", "S1", "Franklin FTSE United Kingdom ETF"), ("SPLG", "S2", "SPDR 500 ETF"),
                          ("APLZ", "S3", "Tradr 2X Long APLD Daily ETF"), ("GLOW", "S4", "WestEnd Bond ETF"),
                          ("GLOW", "S5", "WestEnd Global Equity ETF"), ("OLDQ", "S6", "Quiet ETF")],
               mf_rows=[("FLUK", "S1", True), ("SPYM", "S2", True), ("APLX", "S3", True), ("APLZ", "S7", True),
                        ("BMDL", "S4", True), ("GLOW", "S5", True), ("NEWQ", "S6", True)])
    issues: list = []
    rows = _rows(con, issues)
    assert {t: r["series_id"] for t, r in rows.items()} == {
        "FLGB": "S1", "SPYM": "S2", "APLX": "S3", "BMDL": "S4", "GLOW": "S5", "NEWQ": "S6"}
    (kind, key, detail), = [i for i in issues if i[0] == "etf_ticker_sources_disagree"]
    assert key == "S1" and "FLUK" in detail and "FLGB" in detail and "Compustat" in detail


def test_a_rename_onto_another_series_ticker_is_refused_and_each_series_keeps_its_row():
    """M5: the target is already S11's ETF ticker, so S10 keeps N-CEN's; partitioned by the fund file's ticker, the
    two series used to fall into one row and one of them vanished."""
    con = _con(ncen_rows=[("OLDA", "S10", "Fund Ten ETF"), ("TAKEN", "S11", "Fund Eleven ETF")],
               mf_rows=[("TAKEN", "S10", True)])
    issues: list = []
    rows = _rows(con, issues)
    assert {t: r["series_id"] for t, r in rows.items()} == {"OLDA": "S10", "TAKEN": "S11"}
    assert [(k, key) for k, key, _ in issues if k == "etf_ticker_sources_disagree"] == [
        ("etf_ticker_sources_disagree", "S10")]


def test_only_an_etf_ticker_of_the_fund_file_keeps_ncens_ticker():
    """M5: a mutual-fund class of the same series in the fund file (VFIAX) is no ETF ticker; the ETF class (VOO)
    is the series' ticker."""
    con = _con(ncen_rows=[("VFIAX", "S12", "Vanguard 500 Index Fund")],
               mf_rows=[("VFIAX", "S12", False), ("VOO", "S12", True)])
    assert set(_rows(con)) == {"VOO"}


# ── Series checks: issues only, nothing overwritten ─────────────────────────────────────────────────────────

def test_a_shared_series_and_a_series_the_fund_file_gives_another_are_issues(monkeypatch):
    """2A and 3A: RPSA (N-CEN) and RSPA (Alpha Vantage, its series from TickerInside) are one fund; CONI's N-CEN
    series is not the one the fund file lists for CONI. Both stay as they are."""
    monkeypatch.setattr(etf_holdings, "tickerinside_meta", lambda as_of=None: (
        {"RSPA": {"cik": None, "composite_figi": "BBG0RSPA", "series_id": "S30"}}, {}))
    con = _con(ncen_rows=[("RPSA", "S30", "Equal Weight ETF"), ("CONI", "S40", "GraniteShares 2x Short COIN")],
               mf_rows=[("CONI", "S41", True)], av=[("RSPA", "EQUAL WEIGHT ETF"), ("CONI", "GRANITESHARES")])
    issues: list = []
    rows = _rows(con, issues)
    assert (rows["RSPA"]["series_id"], rows["RPSA"]["series_id"], rows["CONI"]["series_id"]) == ("S30", "S30", "S40")
    got = {(k, key): d for k, key, d in issues if k in ("etf_series_id_shared", "etf_series_file_disagrees")}
    assert set(got) == {("etf_series_id_shared", "S30"), ("etf_series_file_disagrees", "CONI")}
    assert "RPSA" in got[("etf_series_id_shared", "S30")] and "RSPA" in got[("etf_series_id_shared", "S30")]
    assert "S40" in got[("etf_series_file_disagrees", "CONI")] and "S41" in got[("etf_series_file_disagrees", "CONI")]


def test_the_new_issue_kinds_are_registered():
    assert {"etf_ticker_sources_disagree", "etf_series_id_shared", "etf_series_file_disagrees"} <= set(
        security.ISSUE_KINDS)


# ── Trusts: TickerInside's trust class, the coin names, and the trust rule as the one definition ───────────

def test_a_trust_takes_tickerinsides_trust_class_else_its_name_and_the_new_coins_are_crypto():
    """M2 (avo's 4A): the name rule used to lock ``commodity`` before TickerInside was read. A category that maps to
    a trust class wins; any other leaves the name rule. NEAR is a coin only before a fund word."""
    assert etf.trust_class(("Example Gold Trust",), "bitcoin") == "crypto"
    assert etf.trust_class(("Example Gold Trust",), "us-large-blend") == "commodity"
    assert etf.trust_class(("Invesco CurrencyShares Euro Trust",), None) == "currency"
    for name in ("Grayscale Sui Staking ETF", "Canary HBAR ETF", "Canary Staked INJ ETF", "Canary Staked TRX ETF",
                 "VanEck BNB ETF", "Cryptex Digital Market Cap ETF",
                 "Common Shares of Beneficial Interest of Bitwise NEAR ETF"):
        assert etf.trust_class((name,)) == "crypto", name
    assert not etf.CRYPTO_NAME.search("USGI NEAR-TERM TAX FREE FUND")
    assert not etf.CRYPTO_NAME.search("Nearshore Opportunities ETF")
    for name in ("SPDR Gold Shares", "iShares Core S&P 500 ETF", "Vanguard Total Bond Market ETF"):
        assert not etf.is_etn(name) and not etf.CRYPTO_NAME.search(name), name


def test_the_trust_rule_reads_tickerinsides_category(monkeypatch):
    """An etp trust whose name says nothing takes TickerInside's crypto category; FBEQ, an Alpha Vantage row with
    no etp row, takes its commodity category as before but is no trust (M1)."""
    monkeypatch.setattr(ncen, "quarters_held", lambda: ncen.BACKFILL_QUARTERS)
    monkeypatch.setattr(etf_holdings, "tickerinside_meta", lambda as_of=None: (
        {"COIN1": {"cik": "2000001", "composite_figi": "BBG0C1", "series_id": None},
         "FBEQ": {"cik": None, "composite_figi": "BBG0FB", "series_id": None}},
        {"COIN1": {"category": "bitcoin", "expense_ratio": 0.2},
         "FBEQ": {"category": "precious-metals", "expense_ratio": 0.3}}))
    con = _con(av=[("COIN1", "Example Digital Trust"), ("FBEQ", "Franklin US Equity Index ETF")],
               sec=[("COIN1", "2000001", "EXAMPLE DIGITAL TRUST", "etp")])
    rows = _rows(con)
    assert (rows["COIN1"]["asset_class"], rows["FBEQ"]["asset_class"]) == ("crypto", "commodity")
    base.rows_table(con, "etf", [(c, t.replace(" PRIMARY KEY", "")) for c, t in etf.SCHEMA], list(rows.values()))
    assert {t for (t,) in con.execute(f"SELECT ticker FROM etf WHERE {etf.TRUST_SQL}").fetchall()} == {"COIN1"}


def test_trust_sql_is_the_trust_rule_not_a_class_alone():
    """M1: a class of TRUST_CLASSES is not enough. A trust is a security etp row whose CIK files no N-CEN, with no
    N-CEN row or series, no note and no CEF."""
    con = _con(sec=[("GLD", "1222333", "SPDR GOLD TRUST", "etp"), ("IBIT", "1980994", "ISHARES BITCOIN TRUST", "etp"),
                    ("FILR", "1555555", "A FILER'S POOL", "etp"), ("DBC", "1383062", "INVESCO DB", "etp"),
                    ("BOTH", "1777777", "ON BOTH", "etp")],
               filers=["1555555"])
    con.execute("CREATE TABLE etf (ticker TEXT, series_id TEXT, source TEXT, is_etn BOOLEAN, is_cef BOOLEAN, "
                "asset_class TEXT)")
    con.executemany("INSERT INTO etf VALUES (?, ?, ?, ?, ?, ?)", [
        ("GLD", None, "av", False, False, "commodity"), ("IBIT", None, "etp", None, None, "crypto"),
        ("FBEQ", None, "av", False, False, "commodity"),        # TickerInside's class, no etp row: no trust
        ("FILR", None, "av", False, False, "commodity"),        # its CIK files N-CEN: a 40-Act fund
        ("DBC", "S1", "av", False, False, "commodity"),         # a series
        ("BOTH", None, "both", False, False, "commodity"),      # an N-CEN row
        ("SPY", None, "av", False, False, None)])
    assert {t for (t,) in con.execute(f"SELECT ticker FROM etf WHERE {etf.TRUST_SQL}").fetchall()} == {"GLD", "IBIT"}


# ── L1, L2 ─────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_option_income_guard_holds_on_the_derivative_path_too():
    """L1: ACEI, 11.8 % rate contracts over Treasuries, came out ``bond``; an option-income fund is equity or
    nothing. Equity contracts are still equity."""
    mix = {"derivative": 11.8, "d:DIR": 11.8, "debt": 110.0}
    assert etf.nport_class(mix, opt=True) is None
    assert etf.nport_class(mix) == "bond"
    assert etf.nport_class({"derivative": 40.0, "d:DE": 40.0}, opt=True) == "equity"


def test_a_deutsche_bank_aktiengesellschaft_note_is_an_etn():
    """L2: the SEC writes the issuer of ADZCF, DEENF and OLOXF as DEUTSCHE BANK AKTIENGESELLSCHAFT."""
    assert etf.is_etn("DEUTSCHE BANK AKTIENGESELLSCHAFT")

