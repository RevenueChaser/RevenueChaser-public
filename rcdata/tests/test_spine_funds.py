"""``funds/index_holdings``: the four file formats parse (cash and futures lines dropped), one request per file, a
failed file is an issue while the others go on, and a short file does not count."""
from __future__ import annotations

import pytest

from revenuechaser.rcdata import caps, ops
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.spine import funds, security
from revenuechaser.rcdata.needs import catalog

from . import spine_fixture as fx


@pytest.fixture
def env(monkeypatch, http_mock):
    from revenuechaser.core.providers import sec_edgar
    from revenuechaser.rcdata.build.spine import sec_tickers
    monkeypatch.setattr(funds, "FLOOR", {"sp500": 4, "sp400": 2, "sp600": 2, "ndx": 1})
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    http_mock.add("company_tickers_exchange.json", fx.SEC_FILE)
    base.run_request({"dataset": sec_tickers.NAME, "params": {"as_of": "2026-10-27"}})
    http_mock.requests.clear()
    fx.add_fund_routes(http_mock)
    return http_mock


def test_ssga_drops_the_cash_line_and_reads_the_cusip():
    rows = funds.parse_ssga(fx.ssga_xlsx(fx.SP500))
    assert [r["ticker_raw"] for r in rows] == ["MSFT", "ETN", "FDX", "NVR", "WFC"]
    assert rows[0]["cusip"] == "594918104" and rows[0]["weight"] == 1.0


def test_ishares_keeps_stock_lines_only_and_reads_the_market_weight():
    """A swap and a warrant are filed under Asset Class Equity: only ``Type`` EQUITY is a holding of the stock."""
    rows = funds.parse_ishares(fx.ishares_csv(fx.SP400, drop_dash=True))
    assert [r["ticker_raw"] for r in rows] == ["HEI", "HEIA"] and rows[0]["cusip"] is None
    assert rows[0]["weight"] == 1.0


def test_the_sector_funds_ishares_file_has_no_type_column_and_is_read_as_that_shape():
    """iShares serves two shapes (both measured 30 Oct 2026): the core funds (IVV, IJH, IJR, IAK) carry ``Type``
    and ``Market Weight``, the sector and industry funds (SOXX, IBB, ITA, ITB, IGV) carry neither — their holdings
    are the ``Asset Class`` Equity lines and the weight is ``Weight (%)``. The caller names the shape."""
    rows = funds.parse_ishares(fx.ishares_csv(fx.SP500, typed=False), typed=False)
    assert [r["ticker_raw"] for r in rows] == [t for t, _c, _n in fx.SP500]
    assert rows[0]["weight"] == 1.0 and rows[0]["cusip"] is None
    assert not {"XTSLA", "WFFUT", "IXTZ6", "USD"} & {r["ticker_raw"] for r in rows}


def test_a_core_funds_file_that_lost_its_type_column_is_a_source_error_not_the_other_shape():
    """IVV, IJH and IJR are read as the typed shape, so a file of theirs without ``Type`` fails loudly: read the
    other way, a swap or a warrant filed under Asset Class Equity would become a holdings line and could vote."""
    with pytest.raises(base.SourceError, match="Type"):
        funds.parse_ishares(fx.ishares_csv(fx.SP500, typed=False))


def test_a_sector_funds_file_that_gained_a_type_column_is_a_source_error_too():
    """The guard runs both ways: the untyped shape needs ``Weight (%)``, which the typed file does not have."""
    with pytest.raises(base.SourceError, match=r"Weight \(%\)"):
        funds.parse_ishares(fx.ishares_csv(fx.SP500), typed=False)


def test_the_ishares_file_is_the_product_pages_latest_holdings_csv():
    """The old ``1467271812596.ajax?fileType=csv`` link answers the HTML product page since Oct 2026."""
    url = next(f for f in funds.FILES if f.fund == "IVV").url()
    assert url == "https://www.ishares.com/us/products/239726/ishares-core-sp-500-etf/latest-holdings.csv"


def test_the_vanguard_files_are_gone():
    """Vanguard's creation baskets answer 401 to every keyless request since 30 Oct 2026, the old profile API 404;
    avo, 22 Nov 2026 22:38: "Bunlar büyük ihtimalle kapanmışlar ... Bunu kaldırabiliriz." Each S&P index is voted
    from SSGA and iShares, and no request goes to Vanguard."""
    assert "vanguard" not in funds.PROVIDERS and not hasattr(funds, "parse_vanguard")
    for idx in ("sp500", "sp400", "sp600"):
        assert sorted(f.provider for f in funds.FILES if f.index_slug == idx) == ["ishares", "ssga"]
    assert "vanguard" not in catalog.NEEDS["identity.membership"].providers


@pytest.mark.parametrize("parse, body", [(funds.parse_ssga, None), (funds.parse_ishares, b"Name,Weight\n"),
                                         (funds.parse_nasdaq, b"{}")])
def test_a_file_of_another_shape_is_a_source_error(parse, body):
    if body is None:
        from openpyxl import Workbook
        import io
        wb, buf = Workbook(), io.BytesIO()
        wb.active.append(["nothing here"])
        wb.save(buf)
        body = buf.getvalue()
    with pytest.raises(base.SourceError):
        parse(body)


def test_invesco_keeps_stock_and_adr_lines_and_reads_the_cusip():
    rows = funds.parse_invesco(fx.invesco_json([("MSFT", "594918104", "MICROSOFT CORP")], adr=True))
    assert rows == [{"ticker_raw": "MSFT", "cusip": "594918104", "name": "MICROSOFT CORP", "weight": 1.0},
                    {"ticker_raw": "PDD", "cusip": "722304102", "name": "PDD Holdings Inc", "weight": 1.0},
                    {"ticker_raw": "ASML", "cusip": "N07059210", "name": "ASML Holding NV", "weight": 1.0}]
    with pytest.raises(base.SourceError):
        funds.parse_invesco(b'{"cusip": "QQQ"}')


def test_ndx_is_voted_by_the_nasdaq_list_and_invescos_qqq():
    """The Nasdaq list API times out on homesrv (28 Oct 2026); QQQ tracks the Nasdaq-100 and answers the same 101."""
    ndx = {(f.provider, f.fund, f.url()) for f in funds.FILES if f.index_slug == "ndx"}
    assert ndx == {("nasdaq", "NDX", "https://api.nasdaq.com/api/quote/list-type/nasdaq100"),
                   ("invesco", "QQQ", "https://dng-api.invesco.com/cache/v1/accounts/en_US/shareclasses/QQQ/holdings/"
                                      "fund?idType=ticker&productType=ETF")}
    assert caps.cap_for("invesco") is None             # no published limit: no cap (master plan Order 5, rule 3)
    assert [r["ticker_raw"] for r in funds.parse_nasdaq(fx.nasdaq_json(["MSFT", "NVDA"]))] == ["MSFT", "NVDA"]


def test_dias_file_is_the_one_dow_file_so_dow_membership_is_that_file_with_no_vote():
    """SP5 (avo, 22 Nov 2026): ``dow`` membership is written from DIA's file alone. DIA is a unit trust and files no
    N-PORT, so ``etf_class`` reads the same lines. With one counting file ``held*2 > files`` is "the file holds it":
    exactly one ``dow`` file keeps it that way by construction."""
    dow = [f for f in funds.FILES if f.index_slug == "dow"]
    assert [(f.provider, f.fund) for f in dow] == [("ssga", "DIA")]
    assert dow[0].url().endswith("holdings-daily-us-en-dia.xlsx")
    assert "dow" in funds.INDEXES and funds.FLOOR["dow"] == 24
    assert all(f"'{i}'" in security.VOTE_SQL for i in funds.INDEXES)


#: avo, 22 Nov 2026 22:42-22:43 ("Russell için ulaşabileceğim bütün endeksleri ekle"): one iShares file per index,
#: so, like ``dow``, a member is "the file holds it". (slug, fund, product id, typed shape, floor), read 20 Nov 2026.
SINGLE_FILE = [
    ("russell1000", "IWB", "239707", True, 816), ("russell2000", "IWM", "239710", False, 1567),
    ("russell3000", "IWV", "239714", False, 2059), ("russell_microcap", "IWC", "239716", False, 1080),
    ("russell_midcap", "IWR", "239718", True, 656), ("russell_top200", "IWL", "239721", False, 160),
    ("russell1000_growth", "IWF", "239706", True, 297), ("russell1000_value", "IWD", "239708", True, 694),
    ("russell2000_growth", "IWO", "239709", False, 890), ("russell2000_value", "IWN", "239712", True, 1111),
    ("russell_midcap_growth", "IWP", "239717", True, 216), ("russell_midcap_value", "IWS", "239719", False, 572),
    ("russell_top200_growth", "IWY", "239720", False, 80), ("russell_top200_value", "IWX", "239722", False, 121),
    ("nasdaq100_top30", "QTOP", "339775", False, 24)]


@pytest.mark.parametrize("slug, fund, pid, typed, floor", SINGLE_FILE)
def test_each_russell_and_nasdaq_top30_index_is_one_ishares_file(slug, fund, pid, typed, floor):
    files = [f for f in funds.FILES if f.index_slug == slug]
    assert [(f.provider, f.fund) for f in files] == [("ishares", fund)]
    assert f"/us/products/{pid}/" in files[0].url() and files[0].url().endswith("/latest-holdings.csv")
    assert slug in funds.INDEXES and funds.FLOOR[slug] == floor
    assert slug not in funds.CHECKED                # no per-name issues for these (they would flood the list)
    # The fund's own shape is read, and the other shape is refused rather than reshaped.
    rows = files[0].parse(fx.ishares_csv(fx.SP500, typed=typed))
    assert [r["ticker_raw"] for r in rows] == [t for t, _, _ in fx.SP500]
    with pytest.raises(base.SourceError):
        files[0].parse(fx.ishares_csv(fx.SP500, typed=not typed))


#: Group A (avo, 22 Nov 2026 23:17, "hepsini istiyorum, evet"): S&P and Dow Jones indexes from their funds' SSGA
#: xlsx and iShares CSV, read once from homesrv on 22 Nov 2026. (slug, files, floor = 80 % of the shorter file).
WIDE = [
    ("sp100", [("ishares", "OEF")], 80), ("sp500_growth", [("ishares", "IVW"), ("ssga", "SPYG")], 122),
    ("sp500_value", [("ishares", "IVE"), ("ssga", "SPYV")], 347), ("sp500_ex_sp100", [("ishares", "XOEF")], 322),
    ("sp400_growth", [("ishares", "IJK"), ("ssga", "MDYG")], 196),
    ("sp400_value", [("ishares", "IJJ"), ("ssga", "MDYV")], 238),
    ("sp600_growth", [("ishares", "IJT"), ("ssga", "SLYG")], 278),
    ("sp600_value", [("ishares", "IJS"), ("ssga", "SLYV")], 371),
    ("sp900_growth", [("ishares", "IUSG")], 319), ("sp900_value", [("ishares", "IUSV")], 586),
    ("sp1500", [("ssga", "SPTM")], 1212), ("sp_total_market", [("ishares", "ITOT")], 1941),
    ("sp_hy_dividend_aristocrats", [("ssga", "SDY")], 125), ("sp500_high_dividend", [("ssga", "SPYD")], 64),
    ("dj_us", [("ishares", "IYY")], 752), ("dj_us_select_dividend", [("ishares", "DVY")], 78),
    ("dj_us_select_reit", [("ssga", "RWR")], 78)]
#: Each iShares fund's product id and CSV shape as its file answered on 22 Nov 2026.
ISHARES_SHAPE = {"OEF": ("239723", False), "IVW": ("239725", True), "IVE": ("239728", True),
                 "XOEF": ("344551", False), "IJK": ("239762", True), "IJJ": ("239764", True),
                 "IJT": ("239773", True), "IJS": ("239775", True), "IUSG": ("239713", True),
                 "IUSV": ("239715", True), "ITOT": ("239724", False), "IYY": ("239513", False),
                 "DVY": ("239500", False)}


@pytest.mark.parametrize("slug, want, floor", WIDE)
def test_each_group_a_index_is_its_funds_files(slug, want, floor):
    """Where SSGA and iShares both track the index, both files vote (a name must be in both, as for sp500); a
    one-file index is exactly that one file, so, like dow, a member is "the file holds it"."""
    files = [f for f in funds.FILES if f.index_slug == slug]
    assert sorted((f.provider, f.fund) for f in files) == want
    assert slug in funds.INDEXES and funds.FLOOR[slug] == floor and slug not in funds.CHECKED
    assert f"'{slug}'" in security.VOTE_SQL
    for f in files:
        if f.provider == "ssga":
            assert f.url().endswith(f"holdings-daily-us-en-{f.fund.lower()}.xlsx")
            assert [r["ticker_raw"] for r in f.parse(fx.ssga_xlsx(fx.SP500))] == ["MSFT", "ETN", "FDX", "NVR", "WFC"]
            continue
        pid, typed = ISHARES_SHAPE[f.fund]
        assert f"/us/products/{pid}/" in f.url() and f.url().endswith("/latest-holdings.csv")
        assert funds.ISHARES_PRODUCTS[f.fund][2] is typed           # the typed flag, as etf_holdings carries it
        assert [r["ticker_raw"] for r in f.parse(fx.ishares_csv(fx.SP500, typed=typed))] == [
            t for t, _, _ in fx.SP500]
        with pytest.raises(base.SourceError):
            f.parse(fx.ishares_csv(fx.SP500, typed=not typed))


def test_every_ishares_entry_carries_its_typed_flag_and_the_fund_file_reads_that_shape():
    """``funds.ISHARES_PRODUCTS`` is (product id, page slug, typed), like ``etf_holdings.ISHARES_PRODUCTS``: several
    index funds (OEF, ITOT, IYY, DVY, XOEF and the untyped Russell files) serve the CSV shape with no ``Type``."""
    assert all(len(v) == 3 and isinstance(v[2], bool) for v in funds.ISHARES_PRODUCTS.values())
    assert funds.ISHARES_PRODUCTS["IVV"][2] and not funds.ISHARES_PRODUCTS["OEF"][2]
    for f in funds.FILES:
        if f.provider == "ishares":
            typed = funds.ISHARES_PRODUCTS[f.fund][2]
            assert f.parse(fx.ishares_csv(fx.SP500, typed=typed))
            with pytest.raises(base.SourceError):
                f.parse(fx.ishares_csv(fx.SP500, typed=not typed))


def test_no_fund_file_is_fetched_twice():
    assert len({f.raw_name() for f in funds.FILES}) == len(funds.FILES)


#: Group B (avo, 22 Nov 2026 23:17): one slug per sector or industry fund that ``funds/etf_holdings`` already reads
#: daily, so no file is fetched twice. (slug, fund, floor = 80 % of the lines of its file of 20 Nov 2026 on homesrv.)
DERIVED = [
    ("sp500_energy", "XLE", 19), ("sp500_materials", "XLB", 21), ("sp500_industrials", "XLI", 68),
    ("sp500_consumer_discretionary", "XLY", 40), ("sp500_consumer_staples", "XLP", 29),
    ("sp500_health_care", "XLV", 51), ("sp500_financials", "XLF", 64), ("sp500_information_technology", "XLK", 63),
    ("sp500_communication_services", "XLC", 20), ("sp500_utilities", "XLU", 27), ("sp500_real_estate", "XLRE", 26),
    ("sp_biotech", "XBI", 133), ("sp_oil_gas_exploration", "XOP", 42), ("sp_metals_mining", "XME", 32),
    ("sp_regional_banks", "KRE", 135), ("sp_homebuilders", "XHB", 28), ("sp_retail", "XRT", 60),
    ("sp_insurance", "KIE", 44), ("sp_banks", "KBE", 87), ("sp_capital_markets", "KCE", 54),
    ("sp_pharmaceuticals", "XPH", 48), ("sp_transportation", "IYT", 35),
    ("dj_us_aerospace_defense", "ITA", 40), ("dj_us_home_construction", "ITB", 33), ("dj_us_insurance", "IAK", 47),
    ("dj_us_medical_equipment", "IHI", 39), ("dj_us_health_care_providers", "IHF", 48)]


def test_the_sector_and_industry_indexes_are_read_from_etf_holdings_files_not_fetched_again():
    """Group B: each slug is exactly one fund, which ``funds/etf_holdings`` fetches daily (its ``DAILY``), and which
    this dataset does not fetch itself."""
    from revenuechaser.rcdata.build.spine import etf_holdings
    assert [tuple(d) for d in funds.DERIVED] == [tuple(d) for d in DERIVED]
    own = {f.fund for f in funds.FILES}
    for slug, fund, floor in DERIVED:
        assert fund in etf_holdings.DAILY and fund not in own
        assert slug in funds.INDEXES and funds.FLOOR[slug] == floor and slug not in funds.CHECKED
        assert f"'{slug}'" in security.VOTE_SQL
        assert not [f for f in funds.FILES if f.index_slug == slug]
    assert len({d[1] for d in DERIVED}) == len({d[0] for d in DERIVED}) == len(DERIVED)


#: Group C (avo, 22 Nov 2026 23:17): ProShares' S&P dividend funds, one CSV each (NOBL, REGL measured by the
#: inventory, TDV read once on 22 Nov 2026 with the builder's own headers), floor 80 % of the ticker lines.
PROSHARES = [("sp500_dividend_aristocrats", "NOBL", 54), ("sp400_dividend_aristocrats", "REGL", 51),
             ("sp_technology_dividend_aristocrats", "TDV", 29)]
#: The browser headers avo approved for Nasdaq's screener (22 Nov 2026).
NASDAQ_BROWSER = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/130.0 Safari/537.36",
                  "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
                  "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}


def test_proshares_keeps_the_lines_with_a_ticker_and_reads_the_description():
    rows = funds.parse_proshares(fx.proshares_csv("NOBL", fx.SP500))
    assert [r["ticker_raw"] for r in rows] == [t for t, _, _ in fx.SP500]           # the cash line has no ticker
    assert rows[0] == {"ticker_raw": "MSFT", "cusip": None, "name": "MICROSOFT CORP", "weight": None}
    with pytest.raises(base.SourceError, match="Security Ticker"):
        funds.parse_proshares(b"PORTFOLIO HOLDINGS INFORMATION,,,,\r\nnothing,here\r\n")


@pytest.mark.parametrize("slug, fund, floor", PROSHARES)
def test_each_proshares_index_is_exactly_its_one_csv(slug, fund, floor):
    files = [f for f in funds.FILES if f.index_slug == slug]
    assert [(f.provider, f.fund) for f in files] == [("proshares", fund)]
    assert files[0].url() == f"https://accounts.profunds.com/etfdata/ByFund/{fund}-psdlyhld.csv"
    assert slug in funds.INDEXES and funds.FLOOR[slug] == floor and slug not in funds.CHECKED
    assert [r["ticker_raw"] for r in files[0].parse(fx.proshares_csv(fund, fx.SP400))] == ["HEI", "HEI.A"]


def test_the_nasdaq_screener_drops_warrants_rights_and_units_and_keeps_lp_units():
    rows = funds.parse_nasdaq_screener(fx.nasdaq_screener_json(fx.SCREENER_ROWS))
    assert [r["ticker_raw"] for r in rows] == ["MSFT", "AACG", "PAA"]
    assert rows[0] == {"ticker_raw": "MSFT", "cusip": None, "name": "Microsoft Corporation Common Stock",
                       "weight": None}
    with pytest.raises(base.SourceError, match="data.rows"):
        funds.parse_nasdaq_screener(fx.nasdaq_json(["MSFT"]))                    # the list API's shape


def test_the_nasdaq_composite_is_exactly_the_screeners_one_file_asked_with_the_approved_headers():
    """``nasdaq`` (Nasdaq Composite, the listed Nasdaq stocks): one file, so no vote; ``index_registry`` adds the
    spine's listed Nasdaq names to it as before. The screener answers with avo's approved browser headers."""
    files = [f for f in funds.FILES if f.index_slug == "nasdaq"]
    assert [(f.provider, f.fund) for f in files] == [("nasdaq", "COMP")]
    assert files[0].url() == ("https://api.nasdaq.com/api/screener/stocks?tableonly=true&exchange=NASDAQ"
                              "&download=true")
    assert files[0].headers() == NASDAQ_BROWSER
    assert "nasdaq" in funds.INDEXES and funds.FLOOR["nasdaq"] == 2875 and "nasdaq" not in funds.CHECKED
    ndx = [f for f in funds.FILES if f.provider == "nasdaq" and f.fund != "COMP"]
    assert [f.headers() for f in ndx] == [NASDAQ_BROWSER]               # the nasdaq100 list too: without them no answer
    others = [f for f in funds.FILES if f.provider != "nasdaq"]
    assert all(f.headers() == {"Accept": "*/*"} for f in others)         # every other file asks as before


def test_proshares_is_a_provider_with_words_and_in_the_membership_need():
    from revenuechaser.rcdata.needs import screen
    assert "proshares" in funds.PROVIDERS and "proshares" in screen.PROVIDERS
    assert "proshares" in catalog.NEEDS["identity.membership"].providers
    assert caps.cap_for("proshares") is None             # no published limit: one request a file and run


def test_the_per_name_issues_stay_on_the_sp_ndx_and_dow_indexes():
    assert funds.CHECKED == ("sp500", "sp400", "sp600", "ndx", "dow")


def test_tickers_are_written_the_sec_way():
    assert funds.norm_ticker("BRK.B") == "BRK-B" and funds.norm_ticker("BRK/B") == "BRK-B"
    assert funds.norm_ticker("CASH_USD") is None and funds.norm_ticker("-") is None


def test_one_request_per_file_a_failed_file_is_an_issue_and_the_others_count(env):
    row = base.run_request({"dataset": funds.NAME, "params": {"as_of": "2026-10-27"}})
    assert row["result"] == "changed" and row["calls"] == 51            # the 404s are not retried
    n, issues = ops.open_issues(funds.NAME, limit=100)
    # the two SmallCap files, the 14 single-file indexes the fixture does not answer (it answers IWM only), the
    # 23 files of group A and the 4 of group C
    assert n == 43 and {"ssga-SPSM.xlsx", "ishares-IJR.csv", "ssga-SPYG.xlsx", "proshares-NOBL.csv",
                        "nasdaq-COMP.json"} <= {i["key"] for i in issues}
    assert "ishares-IWM.csv" not in {i["key"] for i in issues}
    assert row["coverage"] == round(8 / 51, 4) and "failed files" in row["note"]
    screener = env.calls("api/screener/stocks")
    assert len(screener) == 1 and all(screener[0].headers.get(k) == v for k, v in NASDAQ_BROWSER.items())
    assert all(env.calls("list-type/nasdaq100")[0].headers.get(k) == v for k, v in NASDAQ_BROWSER.items())
    assert not env.calls("holdings-daily-us-en-xlk") and not env.calls("products/239501/")   # B: never fetched here
    assert row["calls"] == len(env.calls())


def test_every_file_failing_fails_the_run(env, http_mock):
    http_mock.routes[:] = [r for r in http_mock.routes if "company_tickers" in r[0]]
    row = base.run_request({"dataset": funds.NAME, "params": {"as_of": "2026-10-27"}})
    assert row["result"] == "failed" and "every fund file failed" in row["note"]


def test_a_day_already_fetched_is_not_fetched_again(env):
    base.run_request({"dataset": funds.NAME, "params": {"as_of": "2026-10-27"}})
    env.requests.clear()
    base.run_request({"dataset": funds.NAME, "params": {"as_of": "2026-10-27"}})
    assert {str(r.url).split("/")[2] for r in env.requests} <= {"www.ssga.com", "www.ishares.com", "api.nasdaq.com",
                                                                "accounts.profunds.com"}
    assert len(env.requests) == 43                         # only the ones that failed are asked again
