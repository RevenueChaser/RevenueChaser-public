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


def test_nasdaq():
    assert [r["ticker_raw"] for r in funds.parse_nasdaq(fx.nasdaq_json(["MSFT", "NVDA"]))] == ["MSFT", "NVDA"]


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


def test_the_per_name_issues_stay_on_the_sp_ndx_and_dow_indexes():
    assert funds.CHECKED == ("sp500", "sp400", "sp600", "ndx", "dow")


def test_tickers_are_written_the_sec_way():
    assert funds.norm_ticker("BRK.B") == "BRK-B" and funds.norm_ticker("BRK/B") == "BRK-B"
    assert funds.norm_ticker("CASH_USD") is None and funds.norm_ticker("-") is None


def test_one_request_per_file_a_failed_file_is_an_issue_and_the_others_count(env):
    row = base.run_request({"dataset": funds.NAME, "params": {"as_of": "2026-10-27"}})
    assert row["result"] == "changed" and row["calls"] == 24            # the 404s are not retried
    n, issues = ops.open_issues(funds.NAME, limit=100)
    # the two SmallCap files and the 14 single-file indexes the fixture does not answer (it answers IWM only)
    assert n == 16 and {"ssga-SPSM.xlsx", "ishares-IJR.csv"} <= {i["key"] for i in issues}
    assert "ishares-IWM.csv" not in {i["key"] for i in issues}
    assert row["coverage"] == round(8 / 24, 4) and "failed files" in row["note"]
    assert row["calls"] == len(env.calls())


def test_every_file_failing_fails_the_run(env, http_mock):
    http_mock.routes[:] = [r for r in http_mock.routes if "company_tickers" in r[0]]
    row = base.run_request({"dataset": funds.NAME, "params": {"as_of": "2026-10-27"}})
    assert row["result"] == "failed" and "every fund file failed" in row["note"]


def test_a_day_already_fetched_is_not_fetched_again(env):
    base.run_request({"dataset": funds.NAME, "params": {"as_of": "2026-10-27"}})
    env.requests.clear()
    base.run_request({"dataset": funds.NAME, "params": {"as_of": "2026-10-27"}})
    assert {str(r.url).split("/")[2] for r in env.requests} <= {"www.ssga.com", "www.ishares.com"}
    assert len(env.requests) == 16                         # only the ones that failed are asked again
