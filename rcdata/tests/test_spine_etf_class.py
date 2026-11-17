"""``etf_class``: what each ETF of ``my_universe`` is, read from its N-PORT holdings (#1031).

avo's decisions of 17 Nov 2026: two classes for a fund with no concentration (``broad`` and ``diversified``); swap,
leveraged and option funds labelled and hidden by default; crypto its own class by the registered name; and no
label typed by hand, so a fund with no report is ``unclassified``. The rule's numbers were measured on the live
universe that day (N-PORT 2026q3); the cases here are the ones the two reviews found.
"""
from __future__ import annotations

import json
from datetime import date

import duckdb
import pytest

from RevenueChaser.rcdata import read, serving
from RevenueChaser.rcdata.build import DATASETS, base, dirty
from RevenueChaser.rcdata.build.spine import etf, etf_class, my_universe, security

from .test_spine_my_universe_build import built  # noqa: F401  (the real spine build, as a fixture)

# A small benchmark: Financials 50 (Banks 25: diversified 20, regional 5; Financial Services 15; Insurance 10),
# Information Technology 35 (Software 14, Semiconductors 14, Hardware 7), Health Care 15 (Pharma 10.5, Equipment 4.5).
BENCH_G = {"40101010": 20.0, "40101015": 5.0, "40201020": 15.0, "40301040": 10.0, "45103010": 14.0,
           "45301020": 14.0, "45202030": 7.0, "35202010": 10.5, "35101010": 4.5}
BENCH = etf_class.benchmark_of(BENCH_G)


def _p(g=None, equity=99.0, country=None, coded=None, name="Some Fund", **kw) -> dict:
    g = dict(g or {})
    return {"name": name, "lev": False, "opt": False, "fof": False, "mm": False, "asset_class": None,
            "equity": equity, "preferred": 0.0, "debt": 0.0, "cash": 0.0, "derivative": 0.0, "commodity": 0.0,
            "fund": 0.0, "real_estate": 0.0, "coded": sum(g.values()) if coded is None else coded, "g": g,
            "country": country if country is not None else {"US": equity}, **kw}


def _no_report(name="Some Fund", **kw) -> dict:
    return {"name": name, "lev": False, "opt": False, "fof": False, "mm": False, "asset_class": None,
            "no_report": True, "why": "no N-PORT report: the fund has no series", **kw}


# ── The rule, on hand-made profiles ───────────────────────────────────────────────────────────────────────────

def test_a_cap_weighted_sector_fund_stays_a_sector_fund():
    """XLV read "Pharma 67 %" under a bare 60 % cut: a sector fund is that concentrated because its sector is."""
    r = etf_class.classify(_p({"35202010": 69.3, "35101010": 29.7}), BENCH)
    assert (r["primary"], r["code"]) == ("sector", "35")
    assert r["ggroup"] == "3520" and r["ggroup_share"] == pytest.approx(70.0)       # stored, though it did not win
    assert r["structure"] == "plain" and r["hidden_by_default"] is False


def test_a_fund_far_over_the_benchmark_inside_its_sector_takes_the_finer_level():
    banks = etf_class.classify(_p({"40101010": 49.5, "40101015": 49.5}), BENCH)
    assert (banks["primary"], banks["code"]) == ("industry_group", "4010")           # KBE: banks, both kinds
    assert "+50 over the benchmark" in banks["reason"]
    regional = etf_class.classify(_p({"40101015": 99.0}), BENCH)
    assert (regional["primary"], regional["code"]) == ("sub_industry", "40101015")   # KRE: the most specific wins


def test_a_level_that_is_all_of_its_parent_in_the_benchmark_is_not_a_finer_label():
    """Energy has one industry group: "group 1010" says nothing "sector 10" did not."""
    bench = etf_class.benchmark_of({"10102020": 60.0, "40101010": 40.0})
    r = etf_class.classify(_p({"10102020": 99.0}), bench)
    assert (r["primary"], r["code"]) == ("sector", "10")


def test_a_label_must_rest_on_half_of_all_equity_not_only_on_the_coded_part():
    """The second reviewer's finding: 100 % of the coded part is no label when only 36 % of the fund is coded."""
    r = etf_class.classify(_p({"45301020": 36.0}, equity=99.0), BENCH)
    assert r["primary"] == "low_coverage" and r["gsector"] == "45" and r["coded_pct"] == pytest.approx(36.36, abs=0.01)


def test_a_covered_call_or_leveraged_fund_keeps_its_exposure_and_is_hidden_by_default():
    r = etf_class.classify(_p({"45103010": 60.0, "45301020": 39.0}, opt=True), BENCH)
    assert r["primary"] == "sector" and r["structure"] == "option_income" and r["hidden_by_default"] is True
    lev = etf_class.classify(_p(equity=20.0, derivative=5.0, cash=70.0, lev=True), BENCH)
    assert lev["primary"] == "synthetic" and lev["structure"] == "leveraged" and lev["hidden_by_default"] is True


def test_derivative_lines_make_a_fund_synthetic_whatever_its_flags_say():
    """MAGS and the buffer funds carry no leveraged flag; their holdings are swaps and options."""
    r = etf_class.classify(_p(equity=5.0, derivative=85.0, cash=10.0), BENCH)
    assert r["primary"] == "synthetic" and r["is_synthetic"] is True and r["hidden_by_default"] is True
    assert etf_class.classify(_p(equity=5.0, derivative=9.9, debt=85.0), BENCH)["primary"] == "bond"


@pytest.mark.parametrize("bucket, primary", [("debt", "bond"), ("cash", "cash"), ("commodity", "commodity"),
                                             ("fund", "fund_of_funds"), ("real_estate", "real_estate")])
def test_a_fund_under_half_equity_is_its_largest_bucket(bucket, primary):
    r = etf_class.classify(_p(equity=1.0, **{bucket: 97.0}), BENCH)
    assert r["primary"] == primary and r["asset_class"] == primary


def test_no_bucket_at_sixty_percent_is_multi_asset_and_preferred_shares_are_their_own_class():
    assert etf_class.classify(_p(equity=40.0, debt=45.0, cash=14.0), BENCH)["primary"] == "multi_asset"
    assert etf_class.classify(_p(equity=99.0, preferred=98.0), BENCH)["primary"] == "preferred"


def test_a_single_country_fund_is_a_country_and_a_spread_one_is_international():
    r = etf_class.classify(_p(country={"JP": 95.0, "US": 4.0}), BENCH)
    assert (r["primary"], r["code"], r["geo"], r["country"]) == ("country", "JP", "country", "JP")
    r = etf_class.classify(_p(country={"JP": 30.0, "GB": 30.0, "DE": 29.0, "US": 10.0}), BENCH)
    assert r["primary"] == "international" and r["code"] is None


def test_china_and_hong_kong_count_together_and_a_place_of_incorporation_does_not_count():
    """CQQQ read "KY 61 %": the Cayman Islands is where the holding company is registered."""
    r = etf_class.classify(_p(country={"KY": 60.0, "CN": 29.0, "HK": 10.0}), BENCH)
    assert (r["primary"], r["code"]) == ("country", "CN+HK")


def test_a_global_single_industry_fund_is_its_industry_before_it_is_international():
    """GDX, URA and LIT read "international" when geography was tested first."""
    r = etf_class.classify(_p({"45301020": 80.0}, country={"TW": 40.0, "NL": 30.0, "US": 29.0}), BENCH)
    assert (r["primary"], r["code"], r["geo"]) == ("industry_group", "4530", "international")


def test_a_fund_shaped_like_the_benchmark_is_broad_and_any_other_unconcentrated_one_is_diversified():
    assert etf_class.classify(_p(BENCH_G, equity=100.0), BENCH)["primary"] == "broad"
    glob = etf_class.classify(_p(BENCH_G, equity=100.0, country={"US": 60.0, "JP": 40.0}), BENCH)
    assert glob["primary"] == "broad_global"
    r = etf_class.classify(_p({"45103010": 55.0, "35202010": 44.0}), BENCH)
    assert r["primary"] == "diversified" and r["benchmark_distance"] == pytest.approx(0.5, abs=0.001)


def test_with_no_benchmark_in_the_build_nothing_relative_to_it_is_decided():
    assert etf_class.classify(_p({"40101015": 99.0}), None)["primary"] == "sector"
    r = etf_class.classify(_p(BENCH_G, equity=100.0), None)
    assert r["primary"] == "diversified" and r["benchmark_distance"] is None


def test_crypto_is_its_own_class_by_the_registered_name_and_a_miners_fund_is_not_one():
    trust = etf_class.classify(_no_report("iShares Bitcoin Trust ETF", asset_class="commodity"), BENCH)
    assert trust["primary"] == "crypto" and trust["asset_class"] == "crypto"
    futures = etf_class.classify(_p(equity=0.0, derivative=40.0, cash=60.0, name="ProShares Bitcoin Strategy ETF"),
                                 BENCH)
    assert futures["primary"] == "crypto" and futures["hidden_by_default"] is True
    miners = etf_class.classify(_p({"45103010": 99.0}, name="Valkyrie Bitcoin Miners ETF"), BENCH)
    assert miners["primary"] == "industry_group" and miners["asset_class"] == "equity"
    assert etf_class.classify(_no_report("SPDR Gold Shares", asset_class="commodity"), BENCH)["primary"] == "commodity"


def test_a_fund_with_no_report_is_unclassified_and_says_why_it_is_never_guessed():
    r = etf_class.classify(_no_report("SPDR S&P 500 ETF Trust"), BENCH)
    assert r["primary"] == etf_class.UNCLASSIFIED and "no series" in r["reason"]
    assert r["gsector"] is None and r["equity_pct"] is None


# ── The rows, from the Parquet and the spine tables ───────────────────────────────────────────────────────────

def _plain(schema):
    return [(c, t.replace(" PRIMARY KEY", "")) for c, t in schema]


def _ctx(as_of=date(2026, 11, 17)) -> base.RunContext:
    return base.RunContext(run_id="run-test", dataset=security.NAME, as_of=as_of)


SECURITIES = [{"ticker": "JPM", "cusip": "46625H100", "gsubind": "40101010"},
              {"ticker": "RF", "cusip": "7591EP100", "gsubind": "40101015"},
              {"ticker": "XOM", "cusip": None, "isin": "US30231G1022", "gsubind": "10102010"},
              {"ticker": "MSFT", "cusip": None, "gsubind": "45103010"}]
FUNDS = [("IVV", "iShares Core S&P 500 ETF", "S1"), ("KRE", "SPDR S&P Regional Banking ETF", "S2"),
         ("CIBR", "First Trust NASDAQ Cybersecurity ETF", None), ("SPY", "SPDR S&P 500 ETF Trust", None),
         ("TNA", "Direxion Daily Small Cap Bull 3X Shares", "S5")]


def _con() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    base.rows_table(con, "security", _plain(security.SECURITY), [{"tier": "A", **s} for s in SECURITIES])
    base.rows_table(con, etf.TABLE, _plain(etf.SCHEMA), [
        {"ticker": t, "name": n, "series_id": s, "is_lev_inverse": t == "TNA"} for t, n, s in FUNDS])
    base.rows_table(con, my_universe.TABLE, _plain(my_universe.SCHEMA),
                    [{"ticker": t, "kind": my_universe.ETF} for t, _, _ in FUNDS])
    return con


def _line(accession, pct, asset_cat="EC", issuer_type="CORP", country="US", **ids) -> dict:
    return {"accession": accession, "issuer_name": ids.pop("issuer_name", "A Company"), "cusip": None, "isin": None,
            "ticker": None, "pct_of_net_assets": pct, "asset_cat": asset_cat, "issuer_type": issuer_type,
            "country": country, **ids}


HOLDINGS = [
    # IVV, the benchmark: banks 20 (diversified 15, regional 5), energy 40, software 39; by CUSIP, ISIN and ticker
    _line("A1", 15.0, cusip="46625H100"), _line("A1", 5.0, cusip="7591EP100"),
    _line("A1", 40.0, cusip="30231G102", isin="US30231G1022"),          # Exxon: the CUSIP finds no spine row
    _line("A1", 39.0, ticker="MSFT"),
    # KRE: regional banks, and a money-market line
    _line("A2", 98.0, cusip="7591EP100"), _line("A2", 2.0, asset_cat="STIV"),
    # CIBR, linked by its registered name: software
    _line("A3", 99.0, ticker="MSFT"),
    # TNA: a held fund the report calls equity, and swaps
    _line("A5", 60.0, issuer_type="RF", issuer_name="iShares Russell 2000 ETF"), _line("A5", 30.0, asset_cat="DE"),
    _line("A5", 10.0, asset_cat="STIV"),
]


@pytest.fixture
def nport():
    """The ``sec/nport`` Parquet of one quarter, as its dataset writes it (only the columns this build reads)."""
    def write(holdings=HOLDINGS, quarter="2026q3"):
        folder = base.parquet_root() / "sec" / "nport" / f"quarter={quarter}"
        folder.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect()
        base.rows_table(con, "f", [("accession", "TEXT"), ("series_id", "TEXT"), ("series_name", "TEXT"),
                                   ("report_date", "DATE"), ("filed", "DATE")], [
            {"accession": "A0", "series_id": "S1", "series_name": "iShares Core S&P 500 ETF",
             "report_date": date(2026, 3, 31), "filed": date(2026, 5, 28)},          # an older report: not read
            {"accession": "A1", "series_id": "S1", "series_name": "iShares Core S&P 500 ETF",
             "report_date": date(2026, 6, 30), "filed": date(2026, 8, 27)},
            {"accession": "A2", "series_id": "S2", "series_name": "SPDR S&P Regional Banking ETF",
             "report_date": date(2026, 6, 30), "filed": date(2026, 8, 27)},
            {"accession": "A3", "series_id": "S3", "series_name": "First Trust Nasdaq Cybersecurity ETF",
             "report_date": date(2026, 6, 30), "filed": date(2026, 8, 27)},
            {"accession": "A5", "series_id": "S5", "series_name": "Direxion Daily Small Cap Bull 3X Shares",
             "report_date": date(2026, 7, 31), "filed": date(2026, 9, 28)}])
        base.rows_table(con, "h", [("accession", "TEXT"), ("issuer_name", "TEXT"), ("cusip", "TEXT"),
                                   ("isin", "TEXT"), ("ticker", "TEXT"), ("pct_of_net_assets", "DOUBLE"),
                                   ("asset_cat", "TEXT"), ("issuer_type", "TEXT"), ("country", "TEXT")],
                        list(holdings))
        con.execute(f"COPY f TO {base.sql_path(folder / 'fund.parquet')} (FORMAT PARQUET)")
        con.execute(f"COPY h TO {base.sql_path(folder / 'holdings.parquet')} (FORMAT PARQUET)")
        con.close()
    return write


@pytest.fixture
def live_etf_class():
    """A live ``spine.duckdb`` holding ``etf_class`` rows, as an earlier build left them."""
    def write(rows):
        path = serving.live_path("spine")
        path.parent.mkdir(parents=True, exist_ok=True)
        con = duckdb.connect(str(path))
        try:
            base.rows_table(con, etf_class.TABLE, _plain(etf_class.SCHEMA), list(rows))
            base.rows_table(con, etf_class.CHANGES, _plain(etf_class.CHANGES_SCHEMA),
                            [{"ticker": r["ticker"], "change": "entered", "now": r["primary"],
                              "as_of": date(2026, 8, 30)} for r in rows])
        finally:
            con.close()
    return write


def _rows(**kw):
    rows, changes, issues = etf_class.rows(_ctx(), _con(), **kw)
    return {r["ticker"]: r for r in rows}, changes, issues


def test_every_universe_etf_gets_one_row_with_its_source_and_its_reports_day(nport):
    nport()
    rows, changes, issues = _rows(manual=[])
    assert sorted(rows) == ["CIBR", "IVV", "KRE", "SPY", "TNA"] and not issues
    kre = rows["KRE"]
    assert (kre["primary"], kre["code"]) == ("sub_industry", "40101015")
    assert kre["source"] == "sec/nport 2026q3" and kre["as_of"] == date(2026, 6, 30)
    assert kre["since"] == date(2026, 11, 17) and kre["manual"] is False and kre["equity_pct"] == 98.0
    assert {(c["ticker"], c["change"]) for c in changes} == {(t, "entered") for t in rows}


def test_a_holding_gets_its_gics_by_cusip_then_isin_then_ticker(nport):
    """Exxon Mobil's CUSIP found no spine row in 55 funds (17 Nov 2026); the ISIN and the ticker did."""
    nport()
    ivv = _rows(manual=[])[0]["IVV"]
    assert ivv["coded_pct"] == 100.0 and ivv["gsector"] == "10" and ivv["gsector_share"] == pytest.approx(40.4, abs=0.1)
    assert ivv["primary"] == "broad"                              # it is the benchmark: distance 0


def test_a_sector_label_carries_the_gics_name_and_a_finer_code_has_none_yet(nport):
    nport()
    rows = _rows(manual=[])[0]
    assert rows["CIBR"]["primary"] == "sector" and rows["CIBR"]["label"] == "Information Technology"
    assert rows["KRE"]["label"] is None


def test_a_fund_with_no_series_is_linked_by_its_registered_name_and_a_unit_trust_stays_unclassified(nport):
    nport()
    rows = _rows(manual=[])[0]
    assert rows["CIBR"]["as_of"] == date(2026, 6, 30)             # "NASDAQ" against "Nasdaq": the same name
    spy = rows["SPY"]
    assert spy["primary"] == etf_class.UNCLASSIFIED and spy["source"] is None and "no series" in spy["reason"]


def test_a_held_fund_is_not_a_stock_whatever_the_report_calls_it(nport):
    """TMF, TNA and BNDW passed "equity at or over half" with no coded holding: they hold funds."""
    nport()
    tna = _rows(manual=[])[0]["TNA"]
    assert tna["equity_pct"] == 0.0 and tna["primary"] == "synthetic" and tna["structure"] == "leveraged"
    assert tna["hidden_by_default"] is True


def test_with_no_nport_parquet_the_live_rows_are_carried_forward_not_rewritten(live_etf_class):
    """A build on a machine without the folder must not turn 2,000 labels into ``unclassified``."""
    live_etf_class([{"ticker": "KRE", "primary": "sub_industry", "code": "40101015", "reason": "as built",
                     "source": "sec/nport 2026q3", "since": date(2026, 8, 30), "manual": False}])
    rows, changes, _ = _rows(manual=[])
    assert rows["KRE"]["primary"] == "sub_industry" and rows["KRE"]["since"] == date(2026, 8, 30)
    assert rows["SPY"]["primary"] == etf_class.UNCLASSIFIED and "no N-PORT Parquet" in rows["SPY"]["reason"]
    assert [(c["ticker"], c["change"]) for c in changes if c["ticker"] == "KRE"] == [("KRE", "entered")]


def test_a_fund_within_ten_points_of_the_cut_keeps_its_live_label(nport, live_etf_class):
    """XLF's largest group sat at 59.6 %: a fund on a cut must not flip every quarter."""
    live = [{"ticker": "CIBR", "primary": "sector", "code": "45", "since": date(2026, 8, 30), "manual": False}]
    live_etf_class(live)
    nport([h for h in HOLDINGS if h["accession"] != "A3"]
          + [_line("A3", 55.0, ticker="MSFT"), _line("A3", 44.0, cusip="46625H100")])
    rows, changes, _ = _rows(manual=[])
    assert (rows["CIBR"]["primary"], rows["CIBR"]["code"]) == ("sector", "45")
    assert "kept" in rows["CIBR"]["reason"] and rows["CIBR"]["since"] == date(2026, 8, 30)
    assert not [c for c in changes if c["ticker"] == "CIBR" and c["change"] == "changed"]


def test_a_fund_that_fell_past_the_lower_cut_changes_and_the_change_is_written(nport, live_etf_class):
    live_etf_class([{"ticker": "CIBR", "primary": "sector", "code": "45", "since": date(2026, 8, 30),
                     "manual": False},
                    {"ticker": "GONE", "primary": "bond", "since": date(2026, 8, 30), "manual": False}])
    nport([h for h in HOLDINGS if h["accession"] != "A3"]
          + [_line("A3", 45.0, ticker="MSFT"), _line("A3", 54.0, cusip="46625H100")])
    rows, changes, _ = _rows(manual=[])
    assert rows["CIBR"]["primary"] == "diversified" and rows["CIBR"]["since"] == date(2026, 11, 17)
    new = {(c["ticker"], c["change"], c["was"], c["now"]) for c in changes if c["as_of"] == date(2026, 11, 17)}
    assert ("CIBR", "changed", "sector 45", "diversified") in new and ("GONE", "left", "bond", None) in new
    assert len([c for c in changes if c["as_of"] == date(2026, 8, 30)]) == 2      # the live rows, carried forward


# ── The manual file ───────────────────────────────────────────────────────────────────────────────────────────

def test_the_manual_file_ships_empty_so_every_label_is_the_rules():
    assert etf_class.load_manual() == []
    assert json.loads(etf_class.MANUAL_FILE.read_text(encoding="utf-8"))["version"] == 1


def test_a_manual_line_corrects_a_label_and_keeps_what_the_rule_said(nport):
    nport()
    rows, _, issues = _rows(manual=[{"ticker": "CIBR", "primary": "industry", "code": "451030",
                                     "reason": "avo: a software fund"}])
    r = rows["CIBR"]
    assert (r["primary"], r["code"], r["manual"]) == ("industry", "451030", True) and not issues
    assert "avo: a software fund" in r["reason"] and "the rule said: 45 100%" in r["reason"]


def test_a_manual_line_naming_no_universe_etf_is_an_issue_not_a_row(nport):
    nport()
    rows, _, issues = _rows(manual=[{"ticker": "NOPE", "primary": "bond", "code": "", "reason": "x"}])
    assert "NOPE" not in rows and [(k, key) for k, key, _ in issues] == [("etf_class_manual_unknown", "NOPE")]
    assert set(etf_class.ISSUES) <= set(security.ISSUE_KINDS)


def test_a_manual_line_without_a_reason_is_refused(tmp_path):
    path = tmp_path / "manual.json"
    path.write_text(json.dumps({"set": [{"ticker": "XLK", "primary": "sector"}]}), encoding="utf-8")
    with pytest.raises(ValueError, match="reason"):
        etf_class.load_manual(path)


# ── The build and the reader ──────────────────────────────────────────────────────────────────────────────────

def test_the_spine_build_serves_both_tables_at_version_7_and_the_reader_reads_them(built):  # noqa: F811
    built()
    assert serving.SERVING_SCHEMA_VERSION["spine"] == 7
    assert etf_class.TABLE in security.TABLES and etf_class.CHANGES in security.TABLES
    with serving.open_read("spine") as con:
        cols = [d[0] for d in con.execute(f"SELECT * FROM {etf_class.TABLE} LIMIT 0").description]
        changes = con.execute(f"SELECT ticker, change FROM {etf_class.CHANGES} ORDER BY 1").fetchall()
    assert cols == [c for c, _ in etf_class.SCHEMA]
    assert changes == [("SOXL", "entered"), ("SOXX", "entered"), ("XLK", "entered")]
    rows = {r["ticker"]: r for r in read.etf_class()}
    assert sorted(rows) == ["SOXL", "SOXX", "XLK"]                 # one row per ETF of my_universe
    assert rows["XLK"]["primary"] == etf_class.UNCLASSIFIED        # this build has no N-PORT Parquet
    assert rows["SOXL"]["structure"] == "leveraged"                # the etf row's flag, report or not
    assert [r["ticker"] for r in read.etf_class(include_hidden=False)] == ["SOXX", "XLK"]
    assert [r["ticker"] for r in read.etf_class(["xlk"])] == ["XLK"]


def test_the_table_follows_my_universe_so_it_may_shrink_and_the_build_reads_the_nport_folder():
    assert etf_class.TABLE in serving.SHRINKS_BY_CHOICE
    assert base.parquet_root() / "sec" / "nport" in dirty.read_dirs(DATASETS[security.NAME])
