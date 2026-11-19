"""#385 FIN-3: comps peers come from the spine universe, not a static list.

The ladder is the spine's ``industry`` at the nearest market cap, widening to the spine's ``sector`` until
there are ``k = 8`` peers (the leave-one-out measurement over 3,365 names: k=8 was the best of 3/5/8/12 on
EV/EBITDA, EV/Revenue and P/E). ``sub_industry`` is not a rung: the identity master writes it NULL.

Also here, because they come from the same multiples table: a non-positive denominator reads ``NM`` (never 0,
and the row stays), a Financial Services target is P/E only, and the tax rate is provision / pretax with the
sector default as the fallback.

Offline: a temp DuckDB spine, injected ``.info`` payloads, no provider call and no store write.
"""
from __future__ import annotations

import copy

import pytest

import RevenueChaser.module_financials.run as fm
from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.core import universe as spine
from RevenueChaser.module_financials import peers as peer_ladder
from RevenueChaser.module_financials.engines import _inputs
from RevenueChaser.module_financials.engines.comps_engine import NM, run_comps
from RevenueChaser.module_financials.engines.dcf_engine import run_dcf
from RevenueChaser.module_financials.engines.three_statement_engine import run_three_statement
from RevenueChaser.module_financials.reporting.html_builder import build_report_html


def _seed(rows):
    """The spine rows a peer ladder reads: ticker, market cap, sector, industry."""
    universe_store.replace([{
        "ticker": r["ticker"], "cik": "", "name": r["ticker"], "market_cap": r["market_cap"],
        "price": 10.0, "sector": r.get("sector") or "Energy", "industry": r.get("industry", "Oil & Gas E&P"),
        "industry_group": None, "sub_industry": None, "quote": {"symbol": r["ticker"]},
        "ggroup": r.get("ggroup"), "gind": r.get("gind"), "gsubind": r.get("gsubind"),
    } for r in rows])


def _ladder(ticker="TEST"):
    return peer_ladder.select_peers(ticker, spine.classification_universe_rows())




# ── the peers are the universe's, and there are 8 of them ──────────────────────────────────────────────






def test_exactly_eight_peers_when_the_industry_has_enough(rawstore_tmp_db):
    # 10 names in the target's industry; the two furthest by market cap stay out.
    _seed([{"ticker": "TEST", "market_cap": 1.0e9}] +
          [{"ticker": f"I{i}", "market_cap": 1.0e9 + d} for i, d in
           enumerate([1e6, -1e6, 2e6, -2e6, 3e6, -3e6, 4e6, -4e6, 5e6, -5e6], start=1)])
    got = _ladder()
    assert len(got) == 8 == peer_ladder.PEER_K
    assert got == [f"I{i}" for i in range(1, 9)]  # nearest market cap first, the 5M pair dropped
    assert set(got) == {f"I{i}" for i in range(1, 9)}


def test_the_ladder_widens_to_the_sector_when_the_industry_is_short(rawstore_tmp_db):
    _seed([{"ticker": "TEST", "market_cap": 1.0e9},
           {"ticker": "OIL1", "market_cap": 1.05e9}, {"ticker": "OIL2", "market_cap": 0.95e9}] +
          [{"ticker": f"GAS{i}", "market_cap": 1.0e9 + i * 1e6, "industry": "Oil & Gas Integrated"}
           for i in range(1, 7)] +
          [{"ticker": "BANK", "market_cap": 1.0e9, "sector": "Financial Services", "industry": "Banks"}])
    got = _ladder()
    assert len(got) == 8
    assert got[:2] == ["OIL1", "OIL2"]                      # the industry rung first
    assert set(got[2:]) == {f"GAS{i}" for i in range(1, 7)}  # then the sector rung fills the rest
    assert "BANK" not in got                                # another sector is never a peer


def test_the_ladder_ignores_the_finer_gics_codes(rawstore_tmp_db):
    """K6 pin: the universe rows now carry ``ggroup`` / ``gind`` / ``gsubind``; the ladder stays industry text,
    then sector. A same-sub-industry name in another industry text is not pulled ahead of the industry rung."""
    _seed([{"ticker": "TEST", "market_cap": 1.0e9, "ggroup": "1010", "gind": "101020", "gsubind": "10102020"},
           {"ticker": "OIL1", "market_cap": 1.3e9, "ggroup": "1010", "gind": "101010", "gsubind": "10101010"},
           {"ticker": "SUB1", "market_cap": 1.0e9, "industry": "Oil & Gas Integrated",
            "ggroup": "1010", "gind": "101020", "gsubind": "10102020"},
           {"ticker": "SUB2", "market_cap": 1.01e9, "sector": "Utilities", "industry": "Gas Utilities",
            "ggroup": "1010", "gind": "101020", "gsubind": "10102020"}])
    got = peer_ladder.select_peers("TEST", spine.classification_universe_rows(), k=2)
    assert got == ["OIL1", "SUB1"]       # industry rung (OIL1), then the sector rung (SUB1); never SUB2


def test_the_target_is_never_its_own_peer(rawstore_tmp_db):
    _seed([{"ticker": "TEST", "market_cap": 1.0e9},
           {"ticker": "OIL1", "market_cap": 1.001e9}, {"ticker": "OIL2", "market_cap": 0.999e9}])
    got = _ladder()
    assert got == ["OIL1", "OIL2"]
    assert "TEST" not in got


# ── non-positive denominators read NM, and the row stays ──────────────────────────────────────────────
def test_a_peer_with_non_positive_ebitda_reads_nm_and_leaves_the_percentile(financials):
    def fetch(t):
        return {"enterpriseValue": 900.0, "ebitda": -10.0 if t == "NEG" else 100.0,
                "totalRevenue": 300.0, "trailingPE": 18.0}

    res = run_comps(financials, ["AAA", "NEG", "BBB"], fetch_info=fetch)
    rows = {r["ticker"]: r for r in res["peers"]}
    assert rows["NEG"]["ev_ebitda"] == NM == "NM"          # not 0, not a negative multiple
    assert len(res["peers"]) == 3                           # the row is not dropped
    assert res["multiples"]["ev_ebitda"]["count"] == 2      # and it is not in the percentile
    assert res["multiples"]["ev_ebitda"]["p50"] == pytest.approx(9.0)


# ── a loss-making target gets no implied value, and the run says why (review MUST-1) ──────────────────
def test_a_loss_making_target_gets_no_implied_value_and_says_why(financials):
    """A negative EBITDA or net income times the peer median is a negative EV, not a value.

    Unbounded, the board read "Per Share $-1.04": a loss is not a valuation. The implied value is absent
    (``None``, which the board prints as N/A) and the run's warnings say which metric was not positive.
    A multiple whose metric IS positive is computed as usual.
    """
    f = copy.deepcopy(financials)
    f["annual"][-1]["ebitda"] = -50.0
    f["annual"][-1]["net_income"] = -120.0

    def fetch(t):
        return {"enterpriseValue": 900.0, "ebitda": 100.0, "totalRevenue": 300.0, "trailingPE": 18.0}

    res = run_comps(f, ["AAA", "BBB"], fetch_info=fetch)
    implied = res["implied"]
    assert implied["ev_ebitda"] is None and implied["per_share_ev_ebitda"] is None
    assert implied["equity_pe"] is None and implied["per_share_pe"] is None
    assert implied["ev_revenue"] == pytest.approx(3000.0)                 # revenue is positive: a real value
    assert implied["per_share_ev_revenue"] == pytest.approx(2.86)         # (3000 - 140 net debt) / 1000 shares
    assert ("comps: implied EV/EBITDA not computed — the target's EBITDA is not positive"
            in res["warnings"])
    assert ("comps: implied P/E not computed — the target's net income is not positive" in res["warnings"])

    html = build_report_html({"ticker": "TEST", "financials": f, "modules": {"comps": res},
                              "warnings": res["warnings"]})
    assert "$-" not in html                                             # no negative valuation reaches the board


# ── a Financial Services target is a P/E comp ─────────────────────────────────────────────────────────
def test_a_financial_services_target_gets_pe_only(financials):
    fin = dict(financials, sector="Financial Services")

    def fetch(t):
        return {"enterpriseValue": 900.0, "ebitda": 100.0, "totalRevenue": 300.0, "trailingPE": 12.0}

    res = run_comps(fin, ["BNK1", "BNK2"], fetch_info=fetch)
    assert res["pe_only"] is True
    assert res["multiples"]["pe"]["count"] == 2
    assert res["multiples"]["ev_ebitda"]["count"] == 0
    assert res["multiples"]["ev_revenue"]["count"] == 0
    assert res["implied"]["ev_ebitda"] is None and res["implied"]["ev_revenue"] is None
    assert all(r["ev_ebitda"] is None and r["ev_revenue"] is None for r in res["peers"])


# ── tax: provision / pretax, else the sector default ──────────────────────────────────────────────────
def _without_statement_tax(financials):
    f = copy.deepcopy(financials)
    for rec in f["annual"]:
        rec.pop("pretax_income", None)
        rec.pop("tax_provision", None)
    return f


def test_tax_is_the_median_in_band_year_and_the_sector_default_where_the_statements_lack_it(financials):
    """#89: the median of the in-band years, not the latest year alone."""
    median = sorted((40.0 / 190.0, 45.0 / 215.0, 50.0 / 240.0))[1]
    both = run_three_statement(financials)["assumptions"]
    assert both["tax_rate"] == pytest.approx(median)
    assert both["tax_rate_source"] == "statements (median of 3 years)"

    without = _without_statement_tax(financials)
    fallback = run_three_statement(without)["assumptions"]
    assert fallback["tax_rate"] == pytest.approx(0.21)
    assert fallback["tax_rate_source"] == "default"

    # The DCF reads the same rule (one helper, two engines).
    assert run_dcf(financials)["assumptions"]["tax_rate"] == pytest.approx(median)
    assert run_dcf(without)["assumptions"]["tax_rate"] == pytest.approx(0.21)

    # Every year implausible is a rate nobody measured, so the labelled default stands (FIN-9 B). This rides the
    # median test rather than standing alone: it is the one tax case the median rule does not change, so a test
    # of its own would pass on the merge-base and prove nothing about #89.
    none_in_band = copy.deepcopy(financials)
    for rec in none_in_band["annual"]:
        rec["pretax_income"], rec["tax_provision"] = 100.0, -50.0
    for engine in (run_dcf, run_three_statement):
        got = engine(none_in_band)["assumptions"]
        assert got["tax_rate"] == pytest.approx(0.21)
        assert got["tax_rate_source"] == "default"


# ── a measured rate outside a plausible band is unknown, not a rate (review MUST-1) ───────────────────
def _with_statement_tax(financials, pretax, provision):
    """The latest year reports this pretax income and this tax provision; the earlier years are untouched."""
    f = copy.deepcopy(financials)
    f["annual"][-1]["pretax_income"] = pretax
    f["annual"][-1]["tax_provision"] = provision
    f["annual"][-1].pop("tax_rate", None)
    return f


@pytest.mark.parametrize("pretax, provision, what", [
    (240.0, -30.0, "a tax benefit: yfinance reports a negative Tax Provision, so the ratio is negative"),
    (240.0, 300.0, "a one-off or a valuation-allowance release: the ratio is above 1"),
])
def test_a_measured_rate_outside_the_band_is_left_out_of_the_median(financials, pretax, provision, what):
    """Both engines: an implausible ratio is not a rate, so it is not one of the years the median rests on (#89).

    Unbounded, it would flip the DCF's NOPAT sign and drive the after-tax cost of debt negative (lowering WACC
    and raising the valuation), and make the 3-statement tax line a permanent cash inflow. Before #89 the latest
    year was the whole measurement, so such a year sent the run to the default; now the other years still measure.
    """
    fin = _with_statement_tax(financials, pretax, provision)
    want = (40.0 / 190.0 + 45.0 / 215.0) / 2        # the two earlier years, the latest one dropped
    for engine in (run_dcf, run_three_statement):
        got = engine(fin)["assumptions"]
        assert got["tax_rate"] == pytest.approx(want), what
        assert got["tax_rate_source"] == "statements (median of 2 years)", what


@pytest.mark.parametrize("provision, rate", [(0.0, 0.0), (144.0, 0.60)])
def test_the_band_edges_are_kept_as_measured_rates(financials, provision, rate):
    """0.0 and 0.60 are inside the band: a zero-tax year is a real rate, not a missing one — so it is one of the
    years the median rests on, and a run of that one year alone reads it back."""
    one = {"pretax_income": 240.0, "tax_provision": provision}
    assert _inputs.statement_tax_rate(one) == pytest.approx(rate)
    assert _inputs.median_tax_rate([one]) == (pytest.approx(rate), 1)

    fin = _with_statement_tax(financials, 240.0, provision)
    want = sorted((rate, 40.0 / 190.0, 45.0 / 215.0))[1]
    for engine in (run_dcf, run_three_statement):
        got = engine(fin)["assumptions"]
        assert got["tax_rate"] == pytest.approx(want)
        assert got["tax_rate_source"] == "statements (median of 3 years)"


def test_a_rate_the_user_typed_is_never_banded(financials):
    """The band judges a measured ratio, not the user: a typed rate is their number, even outside the band."""
    for engine in (run_dcf, run_three_statement):
        got = engine(financials, {"tax_rate": 0.75})["assumptions"]
        assert got["tax_rate"] == pytest.approx(0.75)
        assert got["tax_rate_source"] == "assumption"
