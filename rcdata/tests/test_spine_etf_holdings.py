"""``funds/etf_holdings``: the rotation board's ETFs read whole — the issuer's own file where there is one (the
SPDR workbooks and the iShares CSVs, both parsers already the index job's), TickerInside's fund file for the rest
(#1365, 22 Nov 2026; they were UW's until then), no top-10 cap and no membership vote."""
from __future__ import annotations

from pathlib import Path

import pytest

from revenuechaser.core.providers import sec_edgar, tickerinside, unusual_whales
from revenuechaser.rcdata import ops, serving
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.spine import etf_holdings as etf, sec_tickers

from . import spine_fixture as fx

AS_OF = "2026-10-27"
# The daily funds (the board's, the peer sets' and ring 1 of #354 C6), and the three TickerInside index files a run
# reads before its first fund file: ``status.json``, ``manifest.json`` and ``sha256sums.txt.gz``.
N = 151
INDEX = 3


@pytest.fixture
def env(monkeypatch, http_mock):
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(unusual_whales, "BASE", "https://uw.test/api")
    monkeypatch.setattr(tickerinside, "BASE", "https://tickerinside.test/api/v1")
    monkeypatch.setenv("UNUSUAL_WHALES_API_KEY", "uw-test-key")
    monkeypatch.setattr(etf, "SWEEP_PER_RUN", 0)     # these tests are the daily funds; the sweep has its own file
    http_mock.add("company_tickers_exchange.json", fx.SEC_FILE)
    base.run_request({"dataset": sec_tickers.NAME, "params": {"as_of": AS_OF}})
    http_mock.requests.clear()
    fx.add_etf_routes(http_mock)
    return http_mock


def _served(where: str = "") -> list[tuple]:
    with serving.open_read("spine") as con:
        return con.execute(f"SELECT as_of, etf, provider, ticker, cusip, name, weight FROM {etf.TABLE} "
                           + (f"WHERE {where} " if where else "") + "ORDER BY etf, weight DESC").fetchall()


# ── The fund list and the URLs (the issuer of each fund was confirmed by fetching it once, 30 Oct 2026) ───────

def test_the_funds_are_the_rotation_boards_sector_and_theme_etfs_but_the_commodity_trusts():
    """The board's own 52 are the dataset's, less GLD, SLV and USO (commodity trusts: no equity to hold), plus the
    ten the relatedness peer sets need that the board does not run, plus ring 1 of #354 C6 but AMLP (no fund file).

    The ``52`` is deliberate: adding an ETF to the board's sector or theme groups fails this test, which is where
    the decision whether the new fund has a keyless holdings file or is read from TickerInside belongs."""
    from revenuechaser.core.rotation_reference import SEED_ROTATION_ETFS as ROTATION_ETFS
    board = {t for t, info in ROTATION_ETFS.items() if info["group"] in ("sector", "theme")}
    assert len(board) == 52
    assert {f.etf for f in etf.FILES} == (board - {"GLD", "SLV", "USO"}) | etf.EXTRA | (set(etf.RING1) - {"AMLP"})
    assert len(etf.FILES) == N and len({f.etf for f in etf.FILES}) == N


def test_ring_one_is_the_133_funds_measured_in_354_c6():
    """#354 C6 (21 Nov 2026, the live spine and the 2026q3 N-PORT set): the five rules of the ETF review pass 133
    funds. Plan step B1 reads them all daily."""
    assert len(etf.RING1) == len(set(etf.RING1)) == 133
    assert etf.RING1[:5] == ("VUG", "XLK", "QQQM", "IVW", "SMH") and etf.RING1[-1] == "WCLD"


def test_a_ring_one_fund_with_an_issuer_file_keeps_it_and_is_not_asked_from_tickerinside_too():
    """SB1: ``FILES`` is a concatenation, so a fund in both groups would be fetched twice a day and typed twice. The
    issuer's own file stays the fund's (26 of ring 1: the SPDR and iShares funds); the measured union is the
    acceptance, not 133 + 31."""
    issuer = set(etf.SSGA_FUNDS) | set(etf.ISHARES_PRODUCTS)
    ring = set(etf.RING1)
    assert len(ring & issuer) == 26 and not (issuer & set(etf.TI_FUNDS))
    assert len(ring | issuer) == 138, "the measured distinct union of ring 1 and the 31 issuer funds"
    by_etf = {f.etf: f.provider for f in etf.FILES}
    assert by_etf["XLK"] == "ssga" and by_etf["SOXX"] == "ishares" and by_etf["VUG"] == "tickerinside"
    assert [f.etf for f in etf.FILES].count("XLK") == 1


def test_amlp_is_the_one_ring_one_fund_left_to_the_n_port_parquet():
    """TickerInside serves AMLP (a multi-asset fund) as ``etf/amlp.json``, not ``fund/amlp.json`` (its
    ``funds.json``, 22 Nov 2026): asking the fund path would fail every day. It stays the N-PORT Parquet's."""
    assert "AMLP" in etf.RING1 and "AMLP" not in etf.DAILY


def test_every_peer_set_etf_and_every_rotation_equity_etf_is_a_daily_fund():
    """Review of 9 Nov 2026, section 10: a relatedness peer set can never be "no holdings" by omission. Every ETF
    of ``etf_sets.json``, and every Rotation ``sector`` or ``theme`` ETF that holds stocks, is fetched daily."""
    import json
    from revenuechaser.core.rotation_reference import SEED_ROTATION_ETFS as ROTATION_ETFS
    from revenuechaser.module_relatedness.validation import peer_sets
    _version, sets = peer_sets.read_etf_list()
    board = {t for t, info in ROTATION_ETFS.items() if info["group"] in ("sector", "theme")}
    daily = {f.etf for f in etf.FILES}
    assert not (set(sets) | (board - {"GLD", "SLV", "USO"})) - daily


def test_the_spdr_funds_are_the_issuers_daily_holdings_workbooks():
    urls = {f.etf: f.url() for f in etf.FILES if f.provider == "ssga"}
    assert len(urls) == 21
    assert urls["XLK"] == ("https://www.ssga.com/us/en/intermediary/library-content/products/fund-data/etfs/us/"
                           "holdings-daily-us-en-xlk.xlsx")
    assert urls["KIE"].endswith("holdings-daily-us-en-kie.xlsx")
    assert {"KBE", "KCE", "XPH"} <= set(urls), "SPDR peer-set funds, each workbook fetched once on 9 Nov 2026"


def test_iak_is_an_ishares_fund_not_a_spdr():
    """Measured 30 Oct 2026: the SPDR path answers 404 for IAK (KIE is the SPDR insurance fund), and iShares'
    own product screener gives IAK product 239515 (239516 is the Medical Devices fund)."""
    by_etf = {f.etf: f.provider for f in etf.FILES}
    assert by_etf["IAK"] == "ishares" and by_etf["KIE"] == "ssga"
    assert etf.ISHARES_PRODUCTS["IAK"][0] == "239515"


def test_each_ishares_fund_is_read_as_the_shape_it_serves():
    """The shape is the fund's, not the file's: IAK carries ``Type``, the five sector funds do not. A file that
    changes shape is a failed file for that fund, not a quietly different read."""
    typed = {name: shape[2] for name, shape in etf.ISHARES_PRODUCTS.items()}
    assert typed == {"IAK": True, "SOXX": False, "IBB": False, "ITA": False, "ITB": False, "IGV": False,
                     "IYT": False, "IHI": False, "IHF": False, "ICLN": True}
    iak = next(f for f in etf.FILES if f.etf == "IAK")
    soxx = next(f for f in etf.FILES if f.etf == "SOXX")
    assert len(iak.parse(fx.ishares_csv(fx.SP500))) == len(fx.SP500)
    assert len(soxx.parse(fx.ishares_csv(fx.SP500, typed=False))) == len(fx.SP500)
    with pytest.raises(base.SourceError, match="Type"):
        iak.parse(fx.ishares_csv(fx.SP500, typed=False))


def test_the_ishares_funds_are_their_product_pages_latest_holdings_csv():
    urls = {f.etf: f.url() for f in etf.FILES if f.provider == "ishares"}
    assert urls == {
        "SOXX": "https://www.ishares.com/us/products/239705/ishares-semiconductor-etf/latest-holdings.csv",
        "IBB": "https://www.ishares.com/us/products/239699/ishares-biotechnology-etf/latest-holdings.csv",
        "ITA": "https://www.ishares.com/us/products/239502/ishares-u-s-aerospace-defense-etf/"
               "latest-holdings.csv",
        "ITB": "https://www.ishares.com/us/products/239512/ishares-u-s-home-construction-etf/"
               "latest-holdings.csv",
        "IGV": "https://www.ishares.com/us/products/239771/ishares-expanded-tech-software-sector-etf/"
               "latest-holdings.csv",
        "IAK": "https://www.ishares.com/us/products/239515/ishares-u-s-insurance-etf/latest-holdings.csv",
        # Product ids from the issuer's product screener, each file fetched once (9 Nov 2026).
        "IYT": "https://www.ishares.com/us/products/239501/ishares-u-s-transportation-etf/latest-holdings.csv",
        "IHI": "https://www.ishares.com/us/products/239516/ishares-u-s-medical-devices-etf/latest-holdings.csv",
        "IHF": "https://www.ishares.com/us/products/239510/ishares-u-s-healthcare-providers-etf/"
               "latest-holdings.csv",
        "ICLN": "https://www.ishares.com/us/products/239738/ishares-global-clean-energy-etf/latest-holdings.csv"}


def test_icln_is_typed_with_its_weight_in_the_percent_column():
    """ICLN's file (9 Nov 2026) has a third shape: the ``Type`` column, but the weight under ``Weight (%)`` and no
    ``Market Weight``. A file of IAK's shape is a failed ICLN file, not a quiet read."""
    icln = next(f for f in etf.FILES if f.etf == "ICLN")
    rows = icln.parse(fx.ishares_csv(fx.SP500, typed=True, weight_col="Weight (%)"))
    assert len(rows) == len(fx.SP500) and rows[0]["weight"] is not None
    with pytest.raises(base.SourceError, match="Weight"):
        icln.parse(fx.ishares_csv(fx.SP500))


def test_the_funds_with_no_keyless_issuer_file_are_read_from_tickerinside_not_uw():
    """#1365, avo 22 Nov 2026: UW leaves (#1283) and D3 of #354 says holdings never come from it. These 28 funds
    have no keyless issuer file in this tree, so they are TickerInside's one fund file each, and so are the 92 funds
    of ring 1 with no issuer file here (plan step B1)."""
    ti = {f.etf: f.url() for f in etf.FILES if f.provider == "tickerinside"}
    assert len(ti) == 120
    assert set(ti) >= {"SMH", "PAVE", "AIQ", "LIT", "URA", "NLR", "AIRR", "SKYY", "WCLD", "ARKQ", "ROBO", "JETS",
                       "TAN", "PBW", "GDX", "OIH", "CIBR", "HACK", "REMX",
                       "CLOU", "DTCR", "QTUM", "FINX", "GRID", "DRIV", "BLOK", "ESPO", "COPX"}
    assert ti["SMH"].endswith("/api/v1/fund/smh.json")
    assert not [f for f in etf.FILES if f.provider == "uw"], "no daily fund is asked from UW any more"


# ── UW's answer ──────────────────────────────────────────────────────────────────────────────────────────────

def test_the_uw_answer_is_read_whole_not_capped_at_ten():
    """The top-10 cap is the Rotation board's own (``module_sector_rotation/etf_holdings.py``); this dataset keeps
    every line, by weight, and drops a line with no ticker."""
    many = [(f"T{i}", None, f"NAME {i}") for i in range(12)]
    rows = etf.parse_uw(fx.uw_holdings_json(many))
    assert len(rows) == 12
    assert [r["ticker_raw"] for r in rows[:3]] == ["T0", "T1", "T2"] and rows[0]["cusip"] is None
    assert rows[0]["weight"] == 10.0 and rows[0]["name"] == "NAME 0"


def test_a_repeated_uw_ticker_keeps_the_newer_row():
    rows = etf.parse_uw(fx.uw_holdings_json(fx.SP500, repeat=("MSFT",)))
    msft = [r for r in rows if r["ticker_raw"] == "MSFT"]
    assert len(msft) == 1 and msft[0]["weight"] == 0.001


def test_a_uw_row_with_a_cusip_keeps_it_normalised_and_one_without_has_none():
    """The live answer carries ``cusip`` (SMH, 1 Nov 2026) though the schema does not name it: kept when it is a
    CUSIP, as the issuer parsers keep theirs, so the peer sets can match by CUSIP; None when absent or no CUSIP."""
    rows = etf.parse_uw(fx.uw_holdings_json(fx.SP500, cusips=True))
    assert {(r["ticker_raw"], r["cusip"]) for r in rows} == {(t, c) for t, c, _n in fx.SP500}
    assert {r["cusip"] for r in etf.parse_uw(fx.uw_holdings_json(fx.SP500))} == {None}
    odd = b'{"data": [{"ticker": "A", "cusip": "N/A", "weight": "1"}, {"ticker": "B", "cusip": null, "weight": "1"}]}'
    assert {r["cusip"] for r in etf.parse_uw(odd)} == {None}


@pytest.mark.parametrize("body", [b"{}", b'{"data": {"holdings": []}}', b"not json"])
def test_a_uw_answer_of_another_shape_is_a_source_error(body):
    with pytest.raises(base.SourceError):
        etf.parse_uw(body)


# ── ARK's own holdings CSV (ARKQ; the issuer file of #339, read 1 Nov 2026) ─────────────────────────────────────

ARK_FILE = Path(__file__).parent / "fixtures" / "ark_arkq_holdings.csv"


def test_the_ark_file_is_the_issuers_own_csv():
    ark = etf.EtfFile("ARKQ", "ark", "csv")
    assert ark.url() == ("https://assets.ark-funds.com/fund-documents/funds-etf-csv/"
                         "ARK_AUTONOMOUS_TECH._&_ROBOTICS_ETF_ARKQ_HOLDINGS.csv")
    assert ark.raw_name() == "ark-ARKQ.csv"


def test_the_real_ark_file_reads_its_stock_lines_with_their_cusips():
    """A trimmed copy of the real file of 30 Oct 2026: the equity lines with ticker, CUSIP and weight; the
    money-market line (no ticker, the made-up identifier ``X9USDGSFT``) and the disclaimer line are no holding."""
    rows = etf.parse_ark(ARK_FILE.read_bytes(), "ARKQ")
    assert [r["ticker_raw"] for r in rows] == ["TSLA", "NVDA", "SYM", "KMTUY", "ESLT", "BYDDY"]
    assert rows[0] == {"ticker_raw": "TSLA", "cusip": "88160R101", "name": "TESLA INC", "weight": 12.55}
    assert rows[4]["cusip"] == "M3760D101", "a CINS CUSIP (Israel) is kept"
    assert not any(r["cusip"] == "X9USDGSFT" for r in rows)


def test_a_us_bloomberg_exchange_code_is_dropped_and_nothing_else_is_guessed():
    """``SYM UQ`` is Symbotic on Nasdaq: the real file of 30 Oct 2026 wrote it so. Without the rule the shared
    ``norm_ticker`` reads it as the share class ``SYM-UQ``. A foreign listing keeps what the file wrote in
    ``ticker_raw`` and gets **no** ticker, whether its code is a number (``6954 JT``) or letters (``KOG NO``,
    ``ABBN SE``, which ``norm_ticker`` alone would serve as the US share classes ``KOG-NO`` and ``ABBN-SE``)."""
    head = b"date,fund,company,ticker,cusip,shares,market value ($),weight (%)\n"
    body = (b'10/30/2026,ARKQ,SYMBOTIC INC,SYM UQ,87151X101,"1","$1.00",1.80%\n'
            b'10/30/2026,ARKQ,FANUC CORP,6954 JT,J13440102,"1","$1.00",1.00%\n'
            b'10/30/2026,ARKQ,KONGSBERG GRUPPEN,KOG NO,R3796D109,"1","$1.00",0.90%\n'
            b'10/30/2026,ARKQ,ABB LTD-REG,ABBN SE,H0010V101,"1","$1.00",0.80%\n'
            b'10/30/2026,ARKQ,DEERE & CO,DE UN,244199105,"1","$1.00",0.50%\n')
    rows = etf.parse_ark(head + body, "ARKQ")
    assert [r["ticker_raw"] for r in rows] == ["SYM", "6954 JT", "KOG NO", "ABBN SE", "DE"]
    assert [etf.served_ticker(r) for r in rows] == ["SYM", None, None, None, "DE"]
    assert [r["cusip"] for r in rows[1:4]] == ["J13440102", "R3796D109", "H0010V101"]


def test_a_foreign_listing_reaches_the_parquet_but_not_the_served_table(env, http_mock):
    _source_empty(http_mock, "ARKQ")
    body = fx.ark_csv([("TSLA", "88160R101", "TESLA INC"), ("KOG NO", "R3796D109", "KONGSBERG GRUPPEN")])
    http_mock.routes.insert(0, ("_ARKQ_HOLDINGS.csv", lambda r: (200, body, {}), 200, {}))
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert [r[3] for r in _served("etf = 'ARKQ'")] == ["TSLA"]
    import duckdb
    part = etf.parquet_dir() / f"date={AS_OF}" / "part-0.parquet"
    kept = duckdb.connect().execute(f"SELECT ticker, ticker_raw, cusip FROM read_parquet('{part.as_posix()}') "
                                    "WHERE etf = 'ARKQ' AND cusip = 'R3796D109'").fetchall()
    assert kept == [(None, "KOG NO", "R3796D109")]


@pytest.mark.parametrize("body, match", [
    (b"<html><body>Not found</body></html>", "header"),
    (b"date,fund,company,ticker,weight (%)\n10/30/2026,ARKQ,TESLA INC,TSLA,12.55%\n", "cusip"),
    (ARK_FILE.read_bytes().replace(b",ARKQ,", b",ARKK,"), "ARKK"),
])
def test_an_ark_file_of_another_shape_or_fund_is_a_source_error(body, match):
    """A moved URL answers a page, a changed file loses a column, and a file of another fund is no holding of
    this one: each fails the fund loudly instead of being read some other way."""
    with pytest.raises(base.SourceError, match=match):
        etf.parse_ark(body, "ARKQ")


# ── A run ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_a_run_reads_every_fund_once_and_serves_its_whole_holdings(env):
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert row["result"] == "changed" and row["calls"] == N + INDEX and row["coverage"] == 1.0
    assert len(env.calls()) == N + INDEX, "one request per fund, no retry"
    served = _served()
    assert len(served) == N * len(fx.SP500)
    assert {r[2] for r in served} == {"ssga", "ishares", "tickerinside"}
    xlk = _served("etf = 'XLK'")
    assert {(r[3], r[4]) for r in xlk} == {(t, c) for t, c, _n in fx.SP500}, "the SPDR file's CUSIPs are kept"
    assert str(xlk[0][0]) == AS_OF
    smh = _served("etf = 'SMH'")            # TickerInside: by weight, and it serves neither CUSIP nor name
    assert [r[3] for r in smh] == [t for t, _c, _n in fx.SP500] and {r[4] for r in smh} == {None}
    assert {r[5] for r in smh} == {None}
    assert smh[0][6] == 10.0 and smh[-1][6] == 6.0


def test_the_cash_and_futures_lines_of_a_file_are_not_holdings(env):
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    tickers = {r[3] for r in _served()}
    assert not tickers & {"USD", "XTSLA", "WFFUT", "IXTZ6", "CASH_USD"}


def test_a_moved_issuer_url_is_a_source_failed_issue_and_the_other_funds_go_on(monkeypatch, env):
    monkeypatch.setattr(etf, "ISHARES_PRODUCTS", {**etf.ISHARES_PRODUCTS, "IGV": ("999999", "moved")})
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert row["result"] == "changed" and row["coverage"] == round((N - 1) / N, 4)
    n, issues = ops.open_issues(etf.NAME)
    assert n == 1 and [i["key"] for i in issues] == ["ishares-IGV.csv"] and "failed files" in row["note"]
    assert not _served("etf = 'IGV'") and len(_served("etf = 'IBB'")) == len(fx.SP500)


def test_every_fund_failing_fails_the_run(env, http_mock):
    http_mock.routes[:] = [r for r in http_mock.routes if "company_tickers" in r[0]]
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert row["result"] == "failed" and "every fund file failed" in row["note"]


def test_a_fund_already_fetched_is_not_fetched_again(env):
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    env.requests.clear()
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert env.requests == []


def test_an_answer_with_no_holding_in_it_is_a_failed_file_not_the_funds_whole_day(env, http_mock):
    """The raw file is the resume marker, so an empty answer kept once would be that fund's day: a fund file with an
    empty ``holdings`` object, and a header with no equity line, are the same nothing."""
    _source_empty(http_mock, "SMH")
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert row["result"] == "changed" and row["coverage"] == round((N - 1) / N, 4)
    n, issues = ops.open_issues(etf.NAME)
    assert n == 1 and [i["key"] for i in issues] == ["tickerinside-SMH.json"]
    assert "no holding line" in (issues[0]["detail"] or "") and not _served("etf = 'SMH'")


def test_a_failed_fund_is_fetched_again_in_the_same_day_and_joins_the_others(monkeypatch, env, http_mock):
    """The day's real pattern: one fund fails, the run is repeated, the 58 raw files are resumed and only the
    missing one is asked. Its rows join the day's partition instead of replacing it."""
    good = etf.ISHARES_PRODUCTS
    monkeypatch.setattr(etf, "ISHARES_PRODUCTS", {**good, "IGV": ("999999", "moved", False)})
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert len(_served()) == (N - 1) * len(fx.SP500)
    monkeypatch.setattr(etf, "ISHARES_PRODUCTS", good)      # not monkeypatch.undo(): it would undo the env too
    http_mock.requests.clear()
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert len(http_mock.requests) == 1, "only the fund that failed is asked again"
    assert len(_served()) == N * len(fx.SP500) and len(_served("etf = 'IGV'")) == len(fx.SP500)
    assert row["coverage"] == 1.0 and row["result"] == "changed"


def test_a_second_day_is_a_second_partition_and_both_are_served(env):
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": "2026-10-28"}})
    days = {str(r[0]) for r in _served()}
    assert days == {AS_OF, "2026-10-28"} and len(_served()) == 2 * N * len(fx.SP500)
    assert row["rows"] == N * len(fx.SP500), "the check row counts the newest day"


def test_no_daily_fund_needs_a_key_at_all(monkeypatch, env):
    """#1365: every daily source is keyless, so a run without ``UNUSUAL_WHALES_API_KEY`` reads all the funds and
    opens no ``missing_key`` issue. Before, the 28 UW funds were skipped and the key was an issue."""
    monkeypatch.delenv("UNUSUAL_WHALES_API_KEY")
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert row["result"] == "changed" and row["calls"] == N + INDEX and row["coverage"] == 1.0
    assert ops.open_issues(etf.NAME)[0] == 0
    assert len(_served()) == N * len(fx.SP500) and not _served("provider = 'uw'")
    assert {r[2] for r in _served("etf = 'SMH'")} == {"tickerinside"}


# ── The source rule: the source first, the issuer file when it holds nothing (#339, #1365) ──────────────────

def _source_empty(http_mock, fund: str) -> None:
    """``fund``'s TickerInside file, answered with an empty ``holdings`` object: the shape of a fund it knows
    nothing about."""
    body = fx.tickerinside_fund_json([], fund)
    http_mock.routes.insert(0, (f"/fund/{fund.lower()}.json", lambda r: (200, body, {}), 200, {}))


def test_the_funds_with_an_issuer_file_behind_the_source_are_arkq_only():
    """Step 0 of #339: ARKQ has ARK's CSV; AIRR and SKYY (First Trust), WCLD (WisdomTree) and ROBO (ETC) serve
    their holdings in HTML only, so they have no fallback and are TickerInside's alone."""
    assert {etf_name: f.raw_name() for etf_name, f in etf.FALLBACKS.items()} == {"ARKQ": "ark-ARKQ.csv"}
    assert {f.etf for f in etf.FILES if f.provider == "tickerinside"} >= set(etf.FALLBACKS)
    assert "ark" in etf.PROVIDERS and "tickerinside" in etf.PROVIDERS


def test_the_source_with_holdings_serves_the_day_and_the_issuer_file_is_not_asked(env):
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert row["calls"] == N + INDEX and not [r for r in env.requests if "ark-funds" in str(r.url)]
    assert {r[2] for r in _served("etf = 'ARKQ'")} == {"tickerinside"} and "ARKQ served by" not in (row["note"] or "")


def test_an_empty_source_answer_falls_back_to_the_issuer_file_and_the_note_says_so(env, http_mock):
    """ARKQ's fund file holds nothing. ARK's own CSV serves the fund, the raw file's name says which source served
    the day, and no issue is opened (the fund is served)."""
    _source_empty(http_mock, "ARKQ")
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert row["result"] == "changed" and row["coverage"] == 1.0 and row["calls"] == N + INDEX + 1
    assert ops.open_issues(etf.NAME)[0] == 0
    arkq = _served("etf = 'ARKQ'")
    assert {r[2] for r in arkq} == {"ark"} and {(r[3], r[4]) for r in arkq} == {(t, c) for t, c, _n in fx.SP500}
    day = etf.raw_dir() / AS_OF
    assert (day / "ark-ARKQ.csv").exists() and not (day / "tickerinside-ARKQ.json").exists()
    assert "ARKQ served by ark-ARKQ.csv" in row["note"] and "no holding line" in row["note"]


def test_a_fund_the_issuer_file_served_is_resumed_without_asking_the_source_again(env, http_mock):
    _source_empty(http_mock, "ARKQ")
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    http_mock.requests.clear()
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert http_mock.requests == []


def test_both_sources_failing_is_one_source_failed_issue_naming_both(env, http_mock):
    _source_empty(http_mock, "ARKQ")
    http_mock.routes.insert(0, ("_ARKQ_HOLDINGS.csv", lambda r: (200, b"<html>moved</html>", {}), 200, {}))
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert row["coverage"] == round((N - 1) / N, 4) and not _served("etf = 'ARKQ'")
    n, issues = ops.open_issues(etf.NAME)
    assert n == 1 and issues[0]["kind"] == "source_failed" and issues[0]["key"] == "tickerinside-ARKQ.json"
    assert "no holding line" in issues[0]["detail"] and "ark-ARKQ.csv" in issues[0]["detail"]
    assert "failed files: tickerinside-ARKQ.json" in row["note"]


def test_a_fund_with_no_issuer_file_still_fails_alone_on_an_empty_answer(env, http_mock):
    _source_empty(http_mock, "WCLD")
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert row["calls"] == N + INDEX and row["coverage"] == round((N - 1) / N, 4)
    assert [i["key"] for i in ops.open_issues(etf.NAME)[1]] == ["tickerinside-WCLD.json"]


def test_the_issuer_file_host_has_board_words_and_no_invented_cap():
    from revenuechaser.rcdata import caps
    from revenuechaser.rcdata.needs import screen
    assert "ark" not in caps.DAY_CAPS and screen.PROVIDERS["ark"].name == "ARK"     # ARK publishes no limit (rule 3)


# ── TickerInside, the source of the funds with no keyless issuer file (#1365) ────────────────────────────────

def test_a_run_asks_each_tickerinside_fund_for_its_one_file_and_nothing_else(env):
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    paths = [str(r.url) for r in env.requests if "tickerinside" in str(r.url)]
    funds = [p for p in paths if "/fund/" in p]
    assert len(funds) == len(etf.TI_FUNDS) == 120
    assert {p.rsplit("/", 1)[1] for p in funds} == {f"{t.lower()}.json" for t in etf.TI_FUNDS}
    assert sorted(p.rsplit("/", 1)[1] for p in paths if "/fund/" not in p) == [
        "manifest.json", "sha256sums.txt.gz", "status.json"], "the index files, once a run, and nothing else"


def test_no_run_ever_asks_for_the_history_or_the_flows(env):
    """The licence's one hard line: the history and flows files are not CC BY 4.0 and may not be collected on a
    schedule (https://tickerinside.com/legal/#history). Our history is the SEC's (#354 C7)."""
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    asked = " ".join(str(r.url) for r in env.requests)
    assert "/history" not in asked and "/quarterly" not in asked and "/flows" not in asked


def test_the_parquet_keeps_the_day_the_source_puts_on_the_list_and_which_layer_served_it(env):
    """A TickerInside row is either an issuer file of that day or a fund's newest SEC filing, which can be months
    old, so the file's own date rides along. It is Parquet only: serving it is a serving bump and its own PR."""
    import duckdb
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    part = etf.parquet_dir() / f"date={AS_OF}" / "part-0.parquet"
    rows = duckdb.connect().execute(
        f"SELECT DISTINCT provider, holdings_as_of, source_layer FROM read_parquet('{part.as_posix()}') "
        "ORDER BY provider").fetchall()
    assert ("tickerinside", "2026-11-19", "issuer") in rows
    assert [r for r in rows if r[0] == "ssga"] == [("ssga", None, None)], "an issuer file states neither"
    with serving.open_read("spine") as con:
        served = [c[0] for c in con.execute(f"SELECT * FROM {etf.TABLE} LIMIT 0").description]
    assert "holdings_as_of" not in served and "source_layer" not in served


def test_a_share_class_and_a_foreign_line_of_a_fund_file_are_read_as_the_site_keys_them(env, http_mock):
    """The live files write a US class with its dot (``BRK.B``) and a line listed abroad with its market
    (``7203.JP``). The class is served as our dash form; the foreign line stays in the Parquet with no ticker."""
    import duckdb
    body = fx.tickerinside_fund_json(fx.SP500[:1], "SMH", extra_keys=("BRK.B", "7203.JP", "JPM.PFD"))
    http_mock.routes.insert(0, ("/fund/smh.json", lambda r: (200, body, {}), 200, {}))
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert {r[3] for r in _served("etf = 'SMH'")} == {fx.SP500[0][0], "BRK-B"}
    part = etf.parquet_dir() / f"date={AS_OF}" / "part-0.parquet"
    kept = duckdb.connect().execute(f"SELECT ticker_raw, ticker FROM read_parquet('{part.as_posix()}') "
                                    "WHERE etf = 'SMH' AND ticker IS NULL ORDER BY ticker_raw").fetchall()
    assert kept == [("7203.JP", None), ("JPM.PFD", None)]


def test_the_source_is_paced_out_of_politeness_and_has_no_invented_day_cap():
    """TickerInside publishes no request window and no quota, so ``caps`` holds no number for it (rule 3: no
    invented limit) and the pacer lives in the dataset, labelled politeness."""
    from revenuechaser.rcdata import caps
    assert "tickerinside" not in caps.DAY_CAPS and "tickerinside" not in caps.WINDOWS
    assert etf.TI_PACE == (2, 1.0)


# ── The manifest: a fund file whose sha256 did not change is not fetched again (plan step B1) ───────────────

DAY2 = "2026-10-28"


def _ti_fund_calls(http_mock) -> list[str]:
    return sorted(str(r.url).rsplit("/", 1)[1] for r in http_mock.requests if "/fund/" in str(r.url))


def test_a_fund_file_whose_sha256_is_unchanged_is_not_fetched_and_its_last_file_serves_the_day(env, http_mock):
    """``sha256sums.txt.gz`` (listed and checked by ``manifest.json``) gives every file's sha256. Equal to the bytes
    we hold from the fund's last day means the same file: the raw is copied into the new day, with no request, and
    the day still holds every fund. Only the changed file (SMH here) is asked."""
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert len(_ti_fund_calls(http_mock)) == len(etf.TI_FUNDS)      # the first day has nothing to compare
    smh = fx.tickerinside_fund_json(fx.SP500[:2], "SMH", as_of="2026-11-20")
    bodies = {f.etf: fx.tickerinside_fund_json(fx.SP500, f.etf) for f in etf.FILES if f.provider == "tickerinside"}
    http_mock.routes.insert(0, ("/fund/smh.json", smh, 200, {}))
    fx.add_tickerinside_index(http_mock, {**bodies, "SMH": smh}, first=True)
    http_mock.requests.clear()
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": DAY2}})
    assert _ti_fund_calls(http_mock) == ["smh.json"]
    assert row["calls"] == N - len(etf.TI_FUNDS) + 1 + INDEX and row["coverage"] == 1.0
    assert len(_served(f"as_of = DATE '{DAY2}' AND etf = 'SMH'")) == 2
    assert len(_served(f"as_of = DATE '{DAY2}' AND etf = 'VUG'")) == len(fx.SP500), "the kept file serves the day"
    meta = base.read_raw_json(etf._meta(etf.raw_dir() / DAY2 / "tickerinside-VUG.json"))
    assert meta["as_of"] == DAY2 and meta["same_as"] == AS_OF
    assert f"{len(etf.TI_FUNDS) - 1} of {len(etf.TI_FUNDS)}" in row["note"]


def test_a_file_list_that_does_not_match_the_manifest_saves_nothing_and_every_fund_is_fetched(env, http_mock):
    """The list is trusted only when its sha256 is the manifest's ``list_sha256``; otherwise the run reads every
    fund file, as before the manifest, and the note says why."""
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    fx.add_tickerinside_index(http_mock, {}, list_sha256="0" * 64, first=True)
    http_mock.requests.clear()
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": DAY2}})
    assert len(_ti_fund_calls(http_mock)) == len(etf.TI_FUNDS) and row["coverage"] == 1.0
    assert "every fund file fetched" in row["note"]


def test_a_fund_tickerinside_kept_at_an_older_issuer_file_is_one_build_issue(env, http_mock):
    """``status.json`` names the funds whose issuer file the site could not refresh and serves from an older one
    (``kept_previous``: CLOU, DTCR and FINX, Global X, since 13 Nov on 21 Nov 2026). Ours become one issue; a fund
    we do not read (ACHP) is not named."""
    status = fx.tickerinside_index({}, kept=("CLOU", "ACHP", "FINX"))["/status.json"]
    http_mock.routes.insert(0, ("/status.json", status, 200, {}))
    row = base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF}})
    assert row["coverage"] == 1.0
    n, issues = ops.open_issues(etf.NAME)
    assert n == 1 and issues[0]["kind"] == "source_stale" and issues[0]["key"] == "tickerinside-kept_previous"
    assert "CLOU since 2026-11-13" in issues[0]["detail"] and "FINX" in issues[0]["detail"]
    assert "ACHP" not in issues[0]["detail"]


def test_a_named_request_reads_no_index(env, http_mock):
    """A scoped request asks its names only: no index file, no stale-fund issue."""
    base.run_request({"dataset": etf.NAME, "params": {"as_of": AS_OF, "names": ["VUG"]}})
    assert [str(r.url).rsplit("/", 1)[1] for r in http_mock.requests] == ["vug.json"]
