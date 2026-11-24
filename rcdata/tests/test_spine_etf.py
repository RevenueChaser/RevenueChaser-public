"""``etf``: the ETF universe, one row per ticker, built by ``spine/security`` from Alpha Vantage's listing status,
the N-CEN data sets and the spine's own ``etp`` rows (#346, avo's decisions of 1 Nov 2026).

No threshold and no ``active`` column: every ETF is stored, thresholds are a board's settings at read time.
"""
from __future__ import annotations

from datetime import date

import pytest

from revenuechaser.core.providers import sec_edgar
from revenuechaser.rcdata import serving
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.spine import av_listing, etf, ncen, sec_tickers, sec_tickers_mf, security

from . import spine_fixture as fx

# The equity file's ETP rows: SPY a unit investment trust (its trust files N-CEN as an S-6 registrant, ``NCEN_Q2``),
# GLD a commodity trust (files no N-CEN), FNGU a bank's note (typed etp by its Cboe venue in this fixture).
SEC_FILE = {"fields": ["cik", "name", "ticker", "exchange"],
            "data": [[789019, "MICROSOFT CORP", "MSFT", "Nasdaq"],
                     [884394, "SPDR S&P 500 ETF TRUST", "SPY", "NYSE"],
                     [1222333, "SPDR GOLD TRUST", "GLD", "NYSE"],
                     [927971, "BANK OF MONTREAL /CAN/", "FNGU", "CBOE"]]}
AV = ("symbol,name,exchange,assetType,ipoDate,delistingDate,status\r\n"
      "A,Agilent Technologies Inc,NYSE,Stock,1999-11-18,null,Active\r\n"
      "XLK,TECHNOLOGY SELECT SECTOR SPDR FUND ,NYSE ARCA,ETF,1998-12-16,null,Active\r\n"
      "SOXX,ISHARES SEMICONDUCTOR ETF ,NASDAQ,ETF,2001-07-10,null,Active\r\n"
      "SPY,SPDR S&P 500 ETF TRUST ,NYSE ARCA,ETF,1993-01-22,null,Active\r\n"
      "GLD,SPDR GOLD SHARES ,NYSE ARCA,ETF,2004-11-18,null,Active\r\n"
      "BNKU,Bank of Montreal,NYSE ARCA,ETF,2019-04-03,null,Active\r\n"
      "QYLD,GLOBAL X NASDAQ 100 COVERED CALL ETF ,NASDAQ,ETF,2013-12-12,null,Active\r\n"
      "NEWE,NEW EXAMPLE ETF ,NYSE ARCA,ETF,2026-10-01,null,Active\r\n"
      "TAPR,Barclays Bank PLC,BATS,ETF,2014-07-15,null,Active\r\n")


@pytest.fixture
def built(monkeypatch, http_mock):
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setenv("RC_HTTP_CONTACT", "ops@example.org")
    monkeypatch.setenv("RC_ALPHAVANTAGE_BASE", "https://av.test")
    monkeypatch.setenv("ALPHAVANTAGE_API_KEY", "av-test-key")
    monkeypatch.setattr(av_listing, "MIN_ETFS", 1)           # the fixture's list is a few rows, the real one 5,907
    http_mock.add("company_tickers_exchange.json", SEC_FILE)
    fx.add_ncen_routes(http_mock)
    http_mock.add("state=delisted", "{}")
    http_mock.add("av.test/query", AV)
    base.run_request({"dataset": ncen.NAME, "params": {"mode": "backfill", "to": "2026-11-02"}})
    base.run_request({"dataset": av_listing.NAME, "params": {"as_of": "2026-11-02"}})
    return base.run_request({"dataset": sec_tickers.NAME, "params": {"as_of": "2026-11-02"}})


def _etf() -> dict[str, dict]:
    with serving.open_read("spine") as con:
        cur = con.execute("SELECT * FROM etf ORDER BY ticker")
        cols = [d[0] for d in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}


def test_the_universe_is_av_etfs_and_ncen_etfs_and_the_spines_etp_rows_with_their_source(built):
    rows = _etf()
    assert {t: r["source"] for t, r in rows.items()} == {
        "XLK": "both", "SOXX": "both", "SOXL": "ncen", "CCOI": "ncen", "SPY": "av", "GLD": "av", "BNKU": "av",
        "QYLD": "av", "NEWE": "av", "FNGU": "etp", "LEVX": "ncen", "TAPR": "both"}
    assert "A" not in rows and "MSFT" not in rows             # AV stocks and the spine's common rows are not ETFs


def test_the_columns_are_the_plans_and_there_is_no_active_column(built):
    with serving.open_read("spine") as con:
        cols = [d[0] for d in con.execute("SELECT * FROM etf LIMIT 0").description]
    assert cols == ["ticker", "name", "series_id", "cik", "source", "is_etn", "is_cef", "asset_class", "focus",
                    "country", "is_index", "is_lev_inverse", "is_money_market", "is_option_income", "is_fund_of_funds",
                    "inception", "aum", "aum_as_of", "aum_source", "adv_usd_20d", "expense_ratio",
                    "gvkey", "iid", "cusip", "figi", "composite_figi", "identity_source", "source_as_of",
                    "fetched_at", "run_id"]


def test_ncen_fills_the_flags_the_newest_filings_aum_and_av_the_inception(built):
    xlk, soxx, soxl = (_etf()[t] for t in ("XLK", "SOXX", "SOXL"))
    assert (xlk["name"], xlk["series_id"], xlk["cik"]) == ("Technology Select Sector SPDR Fund", "S000006408",
                                                           "1064641")
    assert xlk["is_index"] is True and xlk["is_lev_inverse"] is False and xlk["is_money_market"] is False
    assert (xlk["aum"], xlk["aum_as_of"]) == (80_000_000_000.0, date(2026, 4, 30))     # the July filing, not April's
    assert xlk["inception"] == date(1998, 12, 16)
    assert (soxx["aum"], soxx["aum_as_of"]) == (15_000_000_000.0, date(2026, 3, 31))   # daily first, then monthly
    assert soxl["is_lev_inverse"] is True and soxl["inception"] is None
    assert xlk["aum_source"] == soxx["aum_source"] == etf.NCEN_SERIES    # no Compustat bar in this fixture


def test_the_funds_own_shares_times_close_is_the_aum_and_ncen_only_fills_the_rest(request):
    """#357: SPY (a unit trust, no N-CEN assets) gets a figure, XLK's replaces N-CEN's series average, and SOXX,
    which Compustat does not price here, keeps N-CEN's."""
    from .test_spine_etf_adv import put_secd, series
    put_secd(series("131855", "01", "SPY", 3, 1.0, close=700.0, cshoc=1e9)
             + series("131856", "01", "XLK", 3, 1.0, close=200.0, cshoc=5e8))
    request.getfixturevalue("built")
    spy, xlk, soxx = (_etf()[t] for t in ("SPY", "XLK", "SOXX"))
    assert (spy["aum"], spy["aum_as_of"], spy["aum_source"]) == (7e11, date(2026, 11, 2), etf.SHARES_X_CLOSE)
    assert (xlk["aum"], xlk["aum_as_of"], xlk["aum_source"]) == (1e11, date(2026, 11, 2), etf.SHARES_X_CLOSE)
    assert (soxx["aum"], soxx["aum_as_of"], soxx["aum_source"]) == (15e9, date(2026, 3, 31), etf.NCEN_SERIES)
    assert _etf()["QYLD"]["aum"] is None and _etf()["QYLD"]["aum_source"] is None


def test_a_row_without_ncen_has_unknown_flags_not_false_ones(built):
    qyld = _etf()["QYLD"]
    assert qyld["is_index"] is None and qyld["is_fund_of_funds"] is None and qyld["aum"] is None
    assert qyld["is_option_income"] is True                   # the name rule needs no N-CEN


def test_option_income_is_a_name_rule(built):
    rows = _etf()
    assert rows["CCOI"]["is_option_income"] is True and rows["CCOI"]["is_fund_of_funds"] is True
    assert rows["XLK"]["is_option_income"] is False


@pytest.mark.parametrize("name,etn", [
    ("iPath Bloomberg Commodity Index Total Return ETN", True), ("Bank of Montreal", True),
    ("BANK OF MONTREAL /CAN/", True), ("UBS AG London Branch", True), ("Barclays Bank PLC", True),
    ("Deutsche Bank AG London", True), ("Credit Suisse AG Nassau Branch", True),
    ("ETRACS 2xMonthly Pay Leveraged Preferred Stock Index ETN due September 25 2048", True),
    ("Abacus Global Management Inc. 9.875% Fixed Rate Senior Notes due 2028", True),
    ("F/M US TREASURY 10 YEAR NOTE ETF", False), ("Invesco AAA CLO Floating Rate Note ETF", False),
    ("Credit Suisse High Yield Bond Fund", False), ("INVESCO KBW BANK ETF", False),
    ("DIREXION DAILY REGIONAL BANKS BULL 3X SHARES", False)])
def test_the_etn_name_rule(name, etn):
    """Names from Alpha Vantage's list of 1 Nov 2026: the notes and the banks' products, and the funds whose names
    carry a bank or the word note and are not one."""
    assert etf.is_etn(name) is etn


@pytest.mark.parametrize("name,income", [
    ("Global X Nasdaq 100 Covered Call ETF", True), ("JPMorgan Equity Premium Income ETF", True),
    ("Invesco S&P 500 BuyWrite ETF", True), ("Example Buy-Write Income ETF", True),
    ("WisdomTree PutWrite Strategy Fund", True), ("Example Put-Write ETF", True),
    ("REX IncomeMax Option Strategy ETF", True), ("Example Managed Floor ETF", True),
    ("Example Defined Protection ETF", True), ("Example Structured Protection ETF", True),
    ("Vanguard Dividend Appreciation ETF", False), ("Schwab U.S. Dividend Equity ETF", False),
    ("FT Vest U.S. Equity Buffer ETF - March", True), ("Innovator Defined Outcome Buffered ETF", True),
    ("Calamos Autocallable Income ETF", True), ("Example Target Outcome ETF", True),
    ("Example Option Income Strategy ETF", True), ("Technology Select Sector SPDR Fund", False)])
def test_the_option_income_name_rule(name, income):
    """The plan's words plus avo's of 1 Nov 2026 (premium income, buy-write, put-write, option strategy, managed
    floor, defined or structured protection); a plain dividend fund stays false."""
    assert etf.is_option_income(name) is income


@pytest.mark.parametrize("name,lev", [
    ("Tradr 2X Long IBM Daily ETF", True), ("Defiance Daily Target 2X Long RIOT ETF", True),
    ("ProShares UltraPro QQQ", True), ("ProShares Ultra S&P500", True),
    ("ProShares UltraShort 20+ Year Treasury", True), ("ProShares UltraPro Short QQQ", True),
    ("Innovator U.S. Equity Ultra Buffer ETF - January", False), ("Angel Oak UltraShort Income ETF", False),
    ("Invesco S&P Ultra Dividend Revenue ETF", False), ("YieldMax Ultra Option Income Strategy ETF", False),
    ("Direxion Daily Semiconductor Bear 3X Shares", True),
    ("Direxion Daily Regional Banks Bull 3X Shares", True), ("ProShares Short S&P500", True),
    ("MicroSectors FANG+ Index -3X Inverse Leveraged ETNs", True), ("Simplify 1.5x Example ETF", True),
    ("AXS 1.25X NVDA Bear Daily ETF", True), ("Tradr 1X Short Innovation 100 Monthly ETF", True),
    ("1x Short VIX Futures ETF", True), ("GraniteShares 1x Short TSLA Daily ETF", True),
    ("ProShares S&P 500 Dividend Aristocrats ETF", False), ("iShares Short Treasury Bond ETF", False),
    ("JPMorgan Ultra-Short Income ETF", False), ("iShares Ultra Short-Term Bond ETF", False),
    ("SPDR Blackstone Senior Loan ETF", False), ("Invesco Senior Loan ETF", False),
    ("VanEck BDC Income ETF", False), ("Vanguard Short-Term Bond ETF", False),
    ("Technology Select Sector SPDR Fund", False)])
def test_the_leveraged_or_inverse_name_rule(name, lev):
    """Review S1 of PR 349: 185 leveraged ``IS_ETF=Y`` series lack N-CEN's flag. "Short" counts only in a
    leveraged or inverse context, never a short-duration bond fund's."""
    assert etf.is_lev_inverse(name) is lev


def test_lev_inverse_is_ncens_flag_or_the_name_rule(built):
    rows = _etf()
    assert rows["SOXL"]["is_lev_inverse"] is True              # N-CEN's flag
    assert rows["XLK"]["is_lev_inverse"] is False
    assert rows["LEVX"]["is_lev_inverse"] is True              # N-CEN has no flag; its name has the leverage
    assert rows["QYLD"]["is_lev_inverse"] is None              # not in N-CEN and no leverage in its name


def test_an_ncen_etf_is_never_flagged_a_note(built):
    """Review N3: N-CEN's ``IS_ETF=Y`` is a registered fund's own word, so it overrules the name rule (TAPR, a
    fund AV names "Barclays Bank PLC")."""
    rows = _etf()
    assert rows["TAPR"]["is_etn"] is False and rows["TAPR"]["source"] == "both"


def test_etns_are_flagged_and_kept(built):
    rows = _etf()
    assert rows["BNKU"]["is_etn"] is True and rows["FNGU"]["is_etn"] is True
    assert rows["XLK"]["is_etn"] is False and rows["GLD"]["is_etn"] is False


def test_an_etp_trust_that_files_no_ncen_is_a_commodity_and_a_uit_that_files_one_is_not(built):
    rows = _etf()
    assert rows["GLD"]["asset_class"] == "commodity"
    assert rows["SPY"]["asset_class"] is None                 # SPY's trust files N-CEN as an S-6 registrant
    assert rows["FNGU"]["asset_class"] is None                # a note, not a trust
    assert {r["asset_class"] for t, r in rows.items() if t not in ("GLD",)} == {None}


def test_a_crypto_trust_is_crypto_and_a_metal_trust_stays_commodity(monkeypatch, http_mock):
    """avo, 23 Nov 2026: the trust rule called every 1933-Act trust ``commodity``, so the bitcoin and ether trusts
    (IBIT, ETHA) came out commodity. Their name says crypto (``etf.CRYPTO_NAME``); a gold trust is still commodity."""
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    http_mock.add("company_tickers_exchange.json", {**SEC_FILE, "data": SEC_FILE["data"] + [
        [1980994, "ISHARES BITCOIN TRUST", "IBIT", "Nasdaq"], [2000045, "ISHARES ETHEREUM TRUST", "ETHA", "Nasdaq"]]})
    fx.add_ncen_routes(http_mock)
    base.run_request({"dataset": ncen.NAME, "params": {"mode": "backfill", "to": "2026-11-02"}})
    base.run_request({"dataset": sec_tickers.NAME, "params": {"as_of": "2026-11-02"}})
    rows = _etf()
    assert {t: rows[t]["asset_class"] for t in ("IBIT", "ETHA", "GLD")} == {
        "IBIT": "crypto", "ETHA": "crypto", "GLD": "commodity"}


def test_a_currency_a_vix_and_a_digital_holdings_trust_get_their_own_class(monkeypatch, http_mock):
    """avo, 23 Nov 2026 ("Evet düzenle"): FXE, UUP, UVXY and EZBC came out ``commodity``; they track a currency, VIX
    futures and bitcoin. Gold stays commodity."""
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    http_mock.add("company_tickers_exchange.json", {**SEC_FILE, "data": SEC_FILE["data"] + [
        [1328598, "Invesco CurrencyShares Euro Trust", "FXE", "NYSE"],
        [1383151, "Invesco DB US Dollar Index Bullish Fund", "UUP", "NYSE"],
        [1415311, "ProShares Ultra VIX Short-Term Futures ETF 2x Shares", "UVXY", "NYSE"],
        [1992870, "Franklin Templeton Digital Holdings Trust", "EZBC", "Cboe"]]})
    fx.add_ncen_routes(http_mock)
    base.run_request({"dataset": ncen.NAME, "params": {"mode": "backfill", "to": "2026-11-02"}})
    base.run_request({"dataset": sec_tickers.NAME, "params": {"as_of": "2026-11-02"}})
    rows = _etf()
    assert {t: rows[t]["asset_class"] for t in ("FXE", "UUP", "UVXY", "EZBC", "GLD")} == {
        "FXE": "currency", "UUP": "currency", "UVXY": "volatility", "EZBC": "crypto", "GLD": "commodity"}


def test_trust_class_reads_the_name():
    assert etf.trust_class(("Invesco CurrencyShares Japanese Yen Trust",)) == "currency"
    assert etf.trust_class(("ProShares Short VIX Short-Term Futures ETF -1x Shares",)) == "volatility"
    assert etf.trust_class(("iShares Bitcoin Trust", None)) == "crypto"
    assert etf.trust_class(("SPDR Gold Shares",)) == "commodity"
    assert etf.trust_class(("United States Oil Fund LP",)) == "commodity"
    assert set(etf.TRUST_CLASSES) <= set(etf.ASSET_CLASSES)


def test_a_trust_is_an_etf_row_with_no_series_no_note_no_cef_and_a_commodity_or_crypto_class():
    """``etf.TRUST_SQL`` is the one definition ``my_universe`` reads (avo, 23 Nov 2026, option a)."""
    import duckdb
    con = duckdb.connect()
    con.execute("CREATE TABLE etf (ticker TEXT, series_id TEXT, is_etn BOOLEAN, is_cef BOOLEAN, asset_class TEXT)")
    con.executemany("INSERT INTO etf VALUES (?, ?, ?, ?, ?)", [
        ("GLD", None, False, False, "commodity"), ("IBIT", None, None, None, "crypto"),
        ("DBC", "S1", False, False, "commodity"),           # a 40-Act commodity fund: a series, so a fund
        ("SPY", None, False, False, None),                  # a unit investment trust: no class here
        ("OILX", None, True, False, "commodity"), ("CEFX", None, False, True, "commodity"),
        ("SOXX", None, False, False, "equity"), ("FXE", None, False, False, "currency"),
        ("UVXY", None, False, False, "volatility")])
    got = {r[0] for r in con.execute(f"SELECT ticker FROM etf WHERE {etf.TRUST_SQL}").fetchall()}
    assert got == {"GLD", "IBIT", "FXE", "UVXY"}


def test_the_columns_later_prs_fill_stay_null(built):
    for r in _etf().values():
        assert (r["focus"], r["country"], r["adv_usd_20d"], r["expense_ratio"]) == (None, None, None, None)


def test_with_fewer_than_four_quarters_held_no_etp_row_is_called_a_commodity(monkeypatch, http_mock):
    """Review M1 of PR 349: one or two quarters hold a fraction of the filers, so a 1940-Act trust that filed in
    another quarter would read as "files no N-CEN". GLD's call waits for the four quarters."""
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    http_mock.add("company_tickers_exchange.json", SEC_FILE)
    fx.add_ncen_routes(http_mock, quarters=("2026q3", "2026q2"))
    base.run_request({"dataset": ncen.NAME, "params": {"as_of": "2026-11-02"}})
    base.run_request({"dataset": sec_tickers.NAME, "params": {"as_of": "2026-11-02"}})
    assert ncen.quarters_held() == 2
    assert {r["asset_class"] for r in _etf().values()} == {None}


def test_without_ncen_no_etp_row_is_called_a_commodity(monkeypatch, http_mock):
    """No N-CEN quarter held: whether a trust files one is unknown, so the rule says nothing."""
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    http_mock.add("company_tickers_exchange.json", SEC_FILE)
    base.run_request({"dataset": sec_tickers.NAME, "params": {"as_of": "2026-11-02"}})
    rows = _etf()
    assert set(rows) == {"SPY", "GLD", "FNGU"} and {r["source"] for r in rows.values()} == {"etp"}
    assert {r["asset_class"] for r in rows.values()} == {None}


def test_the_spine_note_counts_etfs_without_the_etns(built):
    assert "12 in etf: 10 ETFs, 2 ETNs flagged, 0 CEFs flagged" in built["note"]


def test_the_spine_serves_etf_at_the_current_schema_version(built):
    """4 brought ``etf`` itself (#346); 5 the two ``my_universe`` tables beside it (avo, 4 Nov 2026)."""
    # 4 is the bump ``etf`` came with; the file is read against the constant below, so any later number is fine.
    assert serving.SERVING_SCHEMA_VERSION["spine"] >= 4 and "etf" in security.TABLES
    with serving.open_read("spine") as con:
        assert con.execute("SELECT version FROM serving_schema_version").fetchone() == (serving.SERVING_SCHEMA_VERSION["spine"],)


def test_a_cef_that_av_calls_an_etf_is_flagged_kept_and_not_counted():
    """avo, 1 Nov 2026: Alpha Vantage lists closed-end funds as ``ETF`` (DHY, CIK); a row the spine types ``cef``
    stays in ``etf`` with ``is_cef`` and is not counted as an ETF, like a note. Built from the staging tables
    directly: the spine types a CEF from OpenFIGI, which this file's fixture does not route."""
    import duckdb
    from revenuechaser.rcdata.build.spine import stage
    con = duckdb.connect()
    stage.create(con, av_listing.STAGING, av_listing.SCHEMA)
    stage.create(con, ncen.STAGING, ncen.SCHEMA)
    stage.create(con, ncen.FILERS, ncen.FILER)
    stage.create(con, "stg_sec_mf", sec_tickers_mf.SCHEMA)
    con.executemany(f"INSERT INTO {av_listing.STAGING} (ticker, symbol, name, asset_type, status) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [("DHY", "DHY", "Credit Suisse High Yield Bond Fund", "ETF", "Active"),
                     ("XLK", "XLK", "TECHNOLOGY SELECT SECTOR SPDR FUND", "ETF", "Active")])
    con.execute("CREATE TABLE security (ticker TEXT, cik TEXT, name TEXT, security_type TEXT, type_source TEXT, "
                "source_as_of DATE, fetched_at DOUBLE)")
    con.execute("INSERT INTO security VALUES ('DHY', '1061630', 'CREDIT SUISSE HIGH YIELD BOND FUND', 'cef', "
                "'openfigi', NULL, NULL), ('MSFT', '789019', 'MICROSOFT CORP', 'common', 'openfigi', NULL, NULL)")
    ctx = base.RunContext(run_id="r", dataset=security.NAME)
    rows = {r["ticker"]: r for r in etf.rows(ctx, con)}
    assert set(rows) == {"DHY", "XLK"}
    assert rows["DHY"]["is_cef"] is True and rows["XLK"]["is_cef"] is False
    assert rows["DHY"]["source"] == "av" and rows["DHY"]["is_etn"] is False
    assert ("2 in etf: 1 ETFs, 0 ETNs flagged, 1 CEFs flagged; "
            "0 with a 20-session dollar volume" in ctx.notes)



def test_a_label_on_a_security_the_spine_knows_is_no_fund_gives_no_etf_row_and_one_issue_each():
    """avo, 23 Nov 2026: Alpha Vantage labels some operating companies and listed notes ``ETF`` (PAM, an ADR, at
    84 bn; PFX; SPAC units), and the spine's ``etp`` type reaches notes and baby bonds through Compustat's ``tpci``
    ``R`` and the note name rule (OXLCG, ECCU). Where the spine types the ticker a non-fund and the SEC holds no fund
    record for it (no ``sec/company_tickers_mf`` row, no N-CEN series), the label is ignored: no ``etf`` row, one
    ``etf_label_not_a_fund`` issue. A plain fund ``etp`` (SPY, GLD), a CEF, an ETN by its issuer and a ticker the
    SEC's fund file or N-CEN holds all stay."""
    import duckdb
    from revenuechaser.rcdata.build.spine import stage
    con = duckdb.connect()
    stage.create(con, av_listing.STAGING, av_listing.SCHEMA)
    stage.create(con, ncen.STAGING, ncen.SCHEMA)
    stage.create(con, ncen.FILERS, ncen.FILER)
    stage.create(con, "stg_sec_mf", sec_tickers_mf.SCHEMA)
    con.executemany(f"INSERT INTO {av_listing.STAGING} (ticker, symbol, name, asset_type, status) "
                    "VALUES (?, ?, ?, ?, ?)",
                    [(t, t, n, "ETF", "Active") for t, n in (
                        ("PAM", "Pampa Energia SA"), ("PFX", "PhenixFIN Corp"),
                        ("CRAQU", "Cal Redwood Acquisition Corp. Units"), ("SPY", "SPDR S&P 500 ETF Trust"),
                        ("GLD", "SPDR Gold Shares ETF"), ("DHY", "Credit Suisse High Yield Bond Fund"),
                        ("XLK", "TECHNOLOGY SELECT SECTOR SPDR FUND"), ("MFCO", "Example Fund Co ETF"),
                        ("NCCO", "Example N-CEN Co ETF"))])
    con.execute("CREATE TABLE security (ticker TEXT, cik TEXT, name TEXT, security_type TEXT, type_source TEXT, "
                "source_as_of DATE, fetched_at DOUBLE)")
    con.executemany("INSERT INTO security VALUES (?, ?, ?, ?, ?, NULL, NULL)", [
        ("PAM", "1469395", "Pampa Energy Inc.", "adr", "openfigi"),
        ("PFX", "1490349", "PhenixFIN Corp", "common", "openfigi"),
        ("CRAQU", "2058359", "Cal Redwood Acquisition Corp.", "spac", "name_rule(Acquisition/Merger Corp)"),
        ("OXLCG", "1495222", "Oxford Lane Capital Corp.", "etp", "compustat_tpci(R)"),
        ("ABXL", "1814287", "Abacus Global Management Inc. 9.875% Senior Notes due 2028", "etp", "name_rule(note)"),
        ("SPY", "884394", "SPDR S&P 500 ETF TRUST", "etp", "name_rule(ETF/ETN)"),
        ("GLD", "1222333", "SPDR GOLD TRUST", "etp", "name_rule(commodity, currency or crypto pool)"),
        ("FNGU", "927971", "BANK OF MONTREAL /CAN/", "etp", "name_rule(ETN issuer)"),
        ("DHY", "1061630", "CREDIT SUISSE HIGH YIELD BOND FUND", "cef", "openfigi"),
        # a common-typed ticker the SEC's fund file or N-CEN holds is a fund: the SEC's word wins
        ("MFCO", "3000010", "EXAMPLE FUND CO", "common", "openfigi"),
        ("NCCO", "3000011", "EXAMPLE N-CEN CO", "common", "openfigi")])
    con.execute("INSERT INTO stg_sec_mf (ticker, cik, series_id, class_id) "
                "VALUES ('MFCO', '3000010', 'S000000010', 'C000000010')")
    con.execute(f"INSERT INTO {ncen.STAGING} (ticker, cik, series_id, fund_name, is_etf) "
                "VALUES ('NCCO', '3000011', 'S000000011', 'Example N-CEN Co Fund', false)")
    ctx = base.RunContext(run_id="r", dataset=security.NAME)
    issues: list = []
    rows = {r["ticker"]: r for r in etf.rows(ctx, con, issues)}
    gone = {"PAM", "PFX", "CRAQU", "OXLCG", "ABXL"}
    assert not gone & set(rows)
    assert {"SPY", "GLD", "FNGU", "DHY", "XLK", "MFCO", "NCCO"} <= set(rows)
    assert sorted(k for kind, k, _ in issues if kind == "etf_label_not_a_fund") == sorted(gone)
    pam = next(d for kind, k, d in issues if kind == "etf_label_not_a_fund" and k == "PAM")
    assert "adr" in pam and "openfigi" in pam


def test_a_fund_record_under_another_cik_does_not_make_a_stock_ticker_a_fund():
    """CORZ (Grok xReview, 23 Nov 2026; avo "Ok yap"): N-CEN files Tradr's "2X Long CORZ Daily ETF" under the
    ticker CORZ, Core Scientific's. A fund record counts only under the security's own CIK, so the stock's ticker gets
    no etf row. KCCA (carbon allowances) is a commodity fund by its name, whatever its collateral says."""
    import duckdb
    from revenuechaser.rcdata.build.spine import stage
    con = duckdb.connect()
    stage.create(con, av_listing.STAGING, av_listing.SCHEMA)
    stage.create(con, ncen.STAGING, ncen.SCHEMA)
    stage.create(con, ncen.FILERS, ncen.FILER)
    stage.create(con, "stg_sec_mf", sec_tickers_mf.SCHEMA)
    con.execute("CREATE TABLE security (ticker TEXT, cik TEXT, name TEXT, security_type TEXT, type_source TEXT, "
                "source_as_of DATE, fetched_at DOUBLE)")
    con.executemany("INSERT INTO security VALUES (?, ?, ?, ?, ?, NULL, NULL)", [
        ("CORZ", "1839341", "Core Scientific, Inc./tx", "common", "openfigi"),
        ("NCCO", "3000011", "EXAMPLE N-CEN CO", "common", "openfigi")])
    con.executemany(f"INSERT INTO {ncen.STAGING} (ticker, cik, series_id, fund_name, is_etf) VALUES (?, ?, ?, ?, ?)", [
        ("CORZ", "0001587982", "S000095067", "Tradr 2X Long CORZ Daily ETF", True),
        ("NCCO", "0003000011", "S000000011", "Example N-CEN Co Fund", True),     # its own CIK, zero-padded
        ("KCCA", "1592900", "S000071111", "KraneShares California Carbon Allowance Strategy ETF", True)])
    issues: list = []
    rows = {r["ticker"]: r for r in etf.rows(base.RunContext(run_id="r", dataset=security.NAME), con, issues)}
    assert "CORZ" not in rows and "NCCO" in rows
    assert [k for kind, k, _ in issues if kind == "etf_label_not_a_fund"] == ["CORZ"]
    assert rows["KCCA"]["asset_class"] == "commodity"


def test_the_not_a_fund_issue_kind_is_registered():
    assert "etf_label_not_a_fund" in security.ISSUE_KINDS

# ── ETF identity in the spine (#1334 K-A, SP1, SP7; plan v4 step 7, spine 11) ───────────────────────────────

def _ti_files(day: str = "2026-11-02") -> None:
    """TickerInside's ``identifiers.json`` and ``funds.json`` as ``funds/etf_holdings`` keeps them for the day."""
    from revenuechaser.rcdata.build.spine import etf_holdings
    folder = etf_holdings.raw_dir() / day
    folder.mkdir(parents=True, exist_ok=True)
    (folder / etf_holdings.TI_META["identifiers"]).write_bytes(fx.tickerinside_identifiers())
    (folder / etf_holdings.TI_META["funds"]).write_bytes(fx.tickerinside_funds())


@pytest.fixture
def identity(request):
    from .test_spine_etf_adv import put_secd, series
    put_secd(series("131856", "01", "XLK", 3, 1.0, close=200.0, cshoc=5e8, cusip="81369Y803")
             + series("131855", "01", "SPY", 3, 1.0, close=700.0, cshoc=1e9, cusip="78462F103")
             # a series that carried XLK long ago: a reused ticker's, never this fund's (the recency rule)
             + series("099001", "01", "XLK", 3, 1.0, last=date(2026, 9, 1), cusip="00000X000"))
    _ti_files()
    return request.getfixturevalue("built")


def _open_issues() -> set[tuple[str, str]]:
    from revenuechaser.rcdata import ops
    return {(i["kind"], i["key"]) for i in ops.open_issues(security.NAME, limit=500)[1]}


def test_an_etf_takes_its_gvkey_iid_and_cusip_from_the_series_the_spine_already_chose(identity):
    rows = _etf()
    assert (rows["XLK"]["gvkey"], rows["XLK"]["iid"], rows["XLK"]["cusip"]) == ("131856", "01", "81369Y803")
    assert (rows["SPY"]["gvkey"], rows["SPY"]["iid"], rows["SPY"]["cusip"]) == ("131855", "01", "78462F103")
    assert rows["SOXX"]["gvkey"] is None and rows["SOXX"]["cusip"] is None      # Compustat prices no SOXX here
    assert "compustat_secd" in rows["XLK"]["identity_source"]


def test_tickerinside_gives_the_figi_expense_ratio_and_asset_class_where_its_cik_agrees(identity):
    rows = _etf()
    xlk, spy = rows["XLK"], rows["SPY"]
    assert (xlk["figi"], xlk["composite_figi"], xlk["expense_ratio"], xlk["asset_class"]) == (
        "BBG000BJ7007", "BBG000BJ7007", 0.08, "equity")
    assert (spy["figi"], spy["expense_ratio"], spy["asset_class"]) == ("BBG000BDTBL9", 0.0945, "equity")
    assert "tickerinside" in xlk["identity_source"]
    # cik and series_id are filled only where empty: N-CEN's own stay
    assert (xlk["cik"], xlk["series_id"]) == ("1064641", "S000006408")


def test_a_tickerinside_row_under_another_cik_fills_nothing_and_is_an_issue(identity):
    soxx = _etf()["SOXX"]
    assert (soxx["cik"], soxx["series_id"]) == ("1100663", "S000004348")
    assert (soxx["figi"], soxx["composite_figi"], soxx["expense_ratio"], soxx["asset_class"]) == (None,) * 4
    assert ("etf_cik_conflict", "SOXX") in _open_issues()


def test_an_empty_cik_and_series_id_are_filled_and_an_unmapped_category_is_null_and_an_issue(identity):
    newe, qyld = _etf()["NEWE"], _etf()["QYLD"]
    assert (newe["cik"], newe["series_id"], newe["figi"], newe["asset_class"]) == (
        "1777777", "S000077777", "BBG01NEWE001", None)
    assert ("etf_category_unmapped", "something-new") in _open_issues()
    assert (qyld["cik"], qyld["figi"], qyld["expense_ratio"], qyld["asset_class"]) == (
        None, "BBG005QFDDX1", 0.6, "equity")


def test_the_commodity_rule_wins_over_the_category(identity):
    """S7b: GLD, SLV and USO are grantor trusts; a category of TickerInside's never takes that away."""
    gld = _etf()["GLD"]
    assert gld["asset_class"] == "commodity" and gld["expense_ratio"] == 0.4


def test_every_tickerinside_category_of_20_nov_2026_but_unclassified_is_mapped():
    """The 103 category ids of ``funds.json`` (20 Nov 2026), so only a new one, or ``unclassified``, is an issue."""
    assert len(etf.CATEGORY_ASSET_CLASS) == 102 and "unclassified" not in etf.CATEGORY_ASSET_CLASS
    assert set(etf.CATEGORY_ASSET_CLASS.values()) <= set(etf.ASSET_CLASSES)
    assert etf.CATEGORY_ASSET_CLASS["precious-metals"] == "commodity"
    assert etf.CATEGORY_ASSET_CLASS["core-bond"] == "bond" and etf.CATEGORY_ASSET_CLASS["bitcoin"] == "crypto"


def test_without_tickerinside_files_the_identity_columns_stay_null_but_compustats(request):
    from .test_spine_etf_adv import put_secd, series
    put_secd(series("131856", "01", "XLK", 3, 1.0, close=200.0, cshoc=5e8, cusip="81369Y803"))
    request.getfixturevalue("built")
    xlk = _etf()["XLK"]
    assert (xlk["gvkey"], xlk["figi"], xlk["expense_ratio"], xlk["identity_source"]) == (
        "131856", None, None, "compustat_secd")


# ── asset_class from the fund's newest N-PORT report: the third source, below the trust rule and the category ───

@pytest.mark.parametrize("mix, lev, mm, cls", [
    ({"equity": 95.0, "cash": 5.0}, False, False, "equity"),
    ({"debt": 80.0, "equity": 15.0}, False, False, "bond"),
    ({"commodity": 70.0, "cash": 30.0}, False, False, "commodity"),
    ({"cash": 99.0}, False, True, "cash"),                  # a money market fund (N-CEN) holds cash
    ({"cash": 93.0, "derivative": 5.0}, False, False, None),  # T-bills behind futures: what it tracks is unread
    ({"equity": 40.0, "debt": 30.0, "commodity": 10.0}, False, False, "multi_asset"),
    ({"equity": 30.0, "debt": 20.0, "fund": 50.0}, False, False, None),   # half unread: no mix to call
    ({"fund": 100.0}, False, False, None),                  # a fund of funds: its funds' class is not read here
    ({"equity": 85.0, "derivative": 12.0}, False, False, None),   # synthetic: options or swaps carry the exposure
    ({"equity": 100.0}, True, False, None),                 # leveraged or inverse: never read off the collateral
    ({"equity": 60.0, "debt": 40.0}, False, False, "equity"),     # the cut is inclusive
])
def test_the_nport_mix_rule(mix, lev, mm, cls):
    assert etf.nport_class(mix, lev=lev, mm=mm) == cls


@pytest.mark.parametrize("mix, lev, cls", [
    ({"debt": 90.0, "derivative": 40.0, "d:DE": 40.0}, False, "equity"),    # a buffer fund's SPY options
    ({"cash": 60.0, "derivative": 200.0, "d:DE": 200.0}, True, "equity"),   # a 2x single-stock swap
    ({"cash": 90.0, "derivative": 30.0, "d:DIR": 25.0, "d:DE": 5.0}, False, "bond"),
    ({"cash": 90.0, "derivative": 50.0, "d:DCO": 50.0}, True, "commodity"),
    ({"cash": 90.0, "derivative": 50.0, "d:DFE": 50.0}, False, "currency"),
])
def test_a_synthetic_or_leveraged_fund_takes_the_class_of_its_largest_contracts(mix, lev, cls):
    """avo, 23 Nov 2026 ("opsiyon 1"): the N-PORT asset_cat of the contracts it holds most."""
    assert etf.nport_class(mix, lev=lev) == cls


def test_a_crypto_fund_on_fx_contracts_is_crypto():
    """SOLT and XRPT: N-PORT files their crypto futures as foreign exchange (DFE); the name says crypto."""
    assert etf.nport_class({"cash": 90.0, "derivative": 200.0, "d:DFE": 200.0}, lev=True, crypto=True) == "crypto"
    assert etf.nport_class({"equity": 95.0}, crypto=True) == "equity"     # a crypto-miners stock fund holds shares
    assert etf.nport_class({"cash": 90.0, "derivative": 50.0, "d:DO": 50.0}, crypto=True) is None   # "other": unread


@pytest.mark.parametrize("mix, cls", [
    ({"equity": 96.0, "derivative": 2.0}, "equity"),        # a covered-call fund holds the shares it writes on
    ({"debt": 100.0, "derivative": 1.0}, None),             # a buffer fund's T-bills: its exposure is the options
    ({"equity": 51.0, "debt": 48.0}, None),                 # a put-write fund's collateral is no multi_asset mix
])
def test_an_option_income_fund_is_read_only_where_it_holds_the_shares(mix, cls):
    assert etf.nport_class(mix, opt=True) == cls


def _nport(reports, lines, quarter="2026q3") -> None:
    """The ``sec/nport`` Parquet of one quarter, as its dataset writes it (only the columns this build reads)."""
    import duckdb
    folder = base.parquet_root() / "sec" / "nport" / f"quarter={quarter}"
    folder.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    base.rows_table(con, "f", [("accession", "TEXT"), ("series_id", "TEXT"), ("series_name", "TEXT"),
                               ("report_date", "DATE"), ("filed", "DATE")],
                    [{"accession": a, "series_id": s, "series_name": s, "report_date": d, "filed": d}
                     for a, s, d in reports])
    base.rows_table(con, "h", [("accession", "TEXT"), ("issuer_name", "TEXT"), ("cusip", "TEXT"), ("isin", "TEXT"),
                               ("ticker", "TEXT"), ("pct_of_net_assets", "DOUBLE"), ("asset_cat", "TEXT"),
                               ("issuer_type", "TEXT"), ("country", "TEXT")],
                    [{"accession": a, "issuer_name": "A Company", "cusip": None, "isin": None, "ticker": None,
                      "pct_of_net_assets": p, "asset_cat": c, "issuer_type": i, "country": "US"}
                     for a, p, c, i in lines])
    for t, n in (("f", "fund"), ("h", "holdings")):
        con.execute(f"COPY {t} TO {base.sql_path(folder / (n + '.parquet'))} (FORMAT PARQUET)")
    con.close()


@pytest.fixture
def with_nport(request):
    """N-PORT reports for the identity fixture's funds. XLK (TickerInside: equity) reports bonds; SOXX (no
    TickerInside class: its CIK conflicts) reported bonds a quarter ago and shares now; TAPR holds a mix; CCOI holds
    funds; SOXL (leveraged) holds shares."""
    day, older = date(2026, 6, 30), date(2026, 3, 31)
    _nport([("B1", "S000004348", older)], [("B1", 90.0, "DBT", "CORP")], quarter="2026q2")
    _nport([("A1", "S000006408", day), ("A2", "S000004348", day), ("A3", "S000099101", day),
            ("A4", "S000099001", day), ("A5", "S000024908", day)],
           [("A1", 95.0, "DBT", "CORP"), ("A2", 97.0, "EC", "CORP"), ("A2", 3.0, "STIV", "RF"),
            ("A3", 40.0, "EC", "CORP"), ("A3", 35.0, "DBT", "UST"), ("A3", 20.0, "STIV", "RF"),
            ("A4", 95.0, "EC", "RF"), ("A5", 100.0, "EC", "CORP"), ("A5", 100.0, "DE", None)])
    return request.getfixturevalue("identity")


def test_nport_fills_only_what_the_earlier_sources_left_null(with_nport):
    rows = _etf()
    assert rows["XLK"]["asset_class"] == "equity"            # TickerInside's category is never overwritten
    assert rows["GLD"]["asset_class"] == "commodity"         # the trust rule neither
    assert rows["SOXX"]["asset_class"] == "equity"           # the newest report, not the quarter before
    assert rows["TAPR"]["asset_class"] == "multi_asset"
    assert rows["CCOI"]["asset_class"] is None               # held funds: unread
    assert rows["SOXL"]["asset_class"] == "equity"           # leveraged: the class of its equity swaps
    assert rows["SPY"]["asset_class"] == "equity"            # TickerInside's, as before



def test_a_series_the_sec_fund_file_lists_under_a_new_ticker_takes_that_ticker(built, http_mock):
    """N-CEN is annual and keeps the ticker of its filing day. SEC's fund file is current: a series it lists under one
    other ETF ticker was renamed, and the etf row moves to that ticker (SPLG -> SPYM, 24 Nov 2026). A series the file
    still lists under N-CEN's ticker, or does not list at all, keeps N-CEN's."""
    mf = {"fields": ["cik", "seriesId", "classId", "symbol"],
          "data": [[1415726, "S000099001", "C000990011", "CCOP"],          # CCOI's series, renamed
                   [1424958, "S000024908", "C000249081", "SOXL"]]}         # SOXL's series, unchanged
    http_mock.add("company_tickers_mf.json", mf)
    base.run_request({"dataset": sec_tickers_mf.NAME, "params": {"as_of": "2026-11-02"}})
    base.run_request({"dataset": sec_tickers.NAME, "params": {"as_of": "2026-11-02"}})
    rows = _etf()
    assert "CCOI" not in rows
    assert (rows["CCOP"]["series_id"], rows["CCOP"]["source"]) == ("S000099001", "ncen")
    assert rows["CCOP"]["name"] == "Example Covered Call Option Income ETF"
    assert rows["SOXL"]["series_id"] == "S000024908"
    assert rows["LEVX"]["source"] == "ncen"                                 # not in the fund file: N-CEN's ticker
