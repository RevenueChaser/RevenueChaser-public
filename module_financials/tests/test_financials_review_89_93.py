"""The parked Financials wave review items (#89-#93): the tax proxy, the comp set and what the board discloses.

- #89 lives with the other tax tests (``test_comps_peers_385.py``): the rate is the median of the in-band years.
- #90 a peer is only a peer inside ``PEER_CAP_RATIO_BAND`` of the target's market cap; a short ladder is reported.
- #91 the peer set says which rung picked each name, and the board says how many came from the sector.
- #92 the per-share bridge dates its net debt and its share count, and says what it does not subtract.
- #93 a past year's FCFF is taxed at that year's own reported rate, not at today's.

Offline: a temp DuckDB spine, injected ``.info`` payloads, no provider call and no store write.
"""
from __future__ import annotations

import copy

import pytest

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.core import universe as spine
from RevenueChaser.module_financials import peers as peer_ladder
from RevenueChaser.module_financials.config import PEER_CAP_RATIO_BAND
from RevenueChaser.module_financials.engines._inputs import NO_MINORITY_BRIDGE
from RevenueChaser.module_financials.engines.comps_engine import run_comps
from RevenueChaser.module_financials.engines.dcf_engine import _historical_fcff, run_dcf
from RevenueChaser.module_financials.reporting.html_builder import build_report_html


def _seed(rows):
    """The spine rows a peer ladder reads: ticker, market cap, sector, industry."""
    universe_store.replace([{
        "ticker": r["ticker"], "cik": "", "name": r["ticker"], "market_cap": r["market_cap"],
        "price": 10.0, "sector": r.get("sector") or "Energy", "industry": r.get("industry", "Oil & Gas E&P"),
        "industry_group": None, "sub_industry": None, "quote": {"symbol": r["ticker"]},
        "ggroup": None, "gind": None, "gsubind": None,
    } for r in rows])


# ── #90: a peer of a very different size is not a peer ────────────────────────────────────────────────
def test_a_peer_outside_the_cap_band_is_not_picked(rawstore_tmp_db):
    """A $900B name is not a comp for a $1B one, however near it is in the ranking (#90).

    Before this, the industry rung ranked by absolute distance only, so an industry with two members (or a
    conglomerate whose industry label does not describe its revenue) could put a 900x name in the table.
    """
    _seed([{"ticker": "TEST", "market_cap": 1.0e9},
           {"ticker": "NEAR", "market_cap": 2.0e9},        # 2x: inside
           {"ticker": "EDGEHI", "market_cap": 1.0e10},     # 10x: the edge, inside
           {"ticker": "EDGELO", "market_cap": 1.0e8},      # 0.1x: the edge, inside
           {"ticker": "HUGE", "market_cap": 9.0e11},       # 900x: out
           {"ticker": "TINY", "market_cap": 1.0e6}])       # 0.001x: out
    got = peer_ladder.select_peers("TEST", spine.classification_universe_rows())
    # Nearest first by absolute distance: EDGELO is 0.9e9 away, NEAR 1.0e9, EDGEHI 9.0e9.
    assert got == ["EDGELO", "NEAR", "EDGEHI"]
    assert "HUGE" not in got and "TINY" not in got


def test_the_band_is_the_configured_one(rawstore_tmp_db):
    """The band is a named constant, read here so the test and the ladder cannot drift apart."""
    low, high = PEER_CAP_RATIO_BAND
    assert (low, high) == (0.1, 10.0)
    assert peer_ladder.in_cap_band(1.0e9, high * 1.0e9) and peer_ladder.in_cap_band(1.0e9, low * 1.0e9)
    assert not peer_ladder.in_cap_band(1.0e9, high * 1.0e9 * 1.01)
    assert not peer_ladder.in_cap_band(1.0e9, low * 1.0e9 * 0.99)
    assert not peer_ladder.in_cap_band(1.0e9, None)        # unknown is never "close enough"


def test_the_sector_rung_is_banded_too_and_the_ladder_may_come_up_short(rawstore_tmp_db):
    _seed([{"ticker": "TEST", "market_cap": 1.0e9},
           {"ticker": "OIL1", "market_cap": 1.1e9}] +
          [{"ticker": f"GAS{i}", "market_cap": 5.0e11, "industry": "Oil & Gas Integrated"} for i in range(1, 7)])
    got = peer_ladder.select_peers("TEST", spine.classification_universe_rows())
    assert got == ["OIL1"]                                  # the sector rung is all out of band, so 1 of 8


# ── #91: say where the peers come from ────────────────────────────────────────────────────────────────
def test_the_peer_set_says_which_rung_picked_each_name(rawstore_tmp_db):
    _seed([{"ticker": "TEST", "market_cap": 1.0e9},
           {"ticker": "OIL1", "market_cap": 1.05e9},
           {"ticker": "GAS1", "market_cap": 1.1e9, "industry": "Oil & Gas Integrated"}])
    got = peer_ladder.peer_set("TEST", spine.classification_universe_rows())
    assert [(p["ticker"], p["rung"]) for p in got] == [("OIL1", "industry"), ("GAS1", "sector")]
    assert got[0]["market_cap"] == pytest.approx(1.05e9)    # the market-cap column's number


def test_a_sector_peer_is_marked_in_the_table_and_the_market_cap_column_shows(financials):
    """The rung rides the comps row and the peer table shows the cap, so a weaker comp is visible (#91)."""
    res = run_comps(financials, ["OIL1", "GAS1"],
                    fetch_info=lambda t: {"enterpriseValue": 900.0, "ebitda": 100.0, "totalRevenue": 500.0,
                                          "marketCap": 850.0, "netIncomeToCommon": 50.0},
                    rungs={"OIL1": "industry", "GAS1": "sector"})
    assert [p["rung"] for p in res["peers"]] == ["industry", "sector"]

    html = build_report_html({"ticker": "TEST", "financials": financials, "modules": {"comps": res},
                              "warnings": []})
    assert "Market Cap" in html                 # the new column header
    assert ">sector<" in html                   # the marker beside GAS1
    assert "$850" in html                       # the peer's market cap, formatted


def test_a_typed_peer_list_has_no_rung(financials):
    """A peer list the caller typed came from no rung, so nothing is claimed about it."""
    res = run_comps(financials, ["AAA"], fetch_info=lambda t: {"marketCap": 100.0, "trailingPE": 10.0})
    assert res["peers"][0]["rung"] is None


# ── #92: the per-share bridge says what it is and when ───────────────────────────────────────────────
def test_the_dcf_dates_its_net_debt_and_warns_about_the_bridge(financials):
    res = run_dcf(financials)
    assert res["valuation"]["net_debt_fy"] == "2023"
    assert NO_MINORITY_BRIDGE in res["warnings"]
    assert "minority interest and preferred stock are not" in NO_MINORITY_BRIDGE


def test_no_bridge_warning_when_there_is_no_per_share_value(financials):
    """No net debt, no per-share value, so nothing to disclose about it."""
    fin = copy.deepcopy(financials)
    fin["annual"][-1].pop("cash")
    res = run_dcf(fin)
    assert res["valuation"]["per_share_gordon"] is None
    assert NO_MINORITY_BRIDGE not in res["warnings"]


def test_the_comps_bridge_dates_its_net_debt_too(financials):
    res = run_comps(financials, ["AAA"],
                    fetch_info=lambda t: {"enterpriseValue": 900.0, "ebitda": 100.0, "totalRevenue": 500.0,
                                          "marketCap": 850.0, "netIncomeToCommon": 50.0})
    assert res["implied"]["net_debt_fy"] == "2023"
    assert NO_MINORITY_BRIDGE in res["warnings"]


def test_the_board_shows_the_bridge_line(financials):
    res = run_dcf(financials)
    html = build_report_html({"ticker": "TEST", "financials": financials, "modules": {"dcf": res},
                              "warnings": []})
    assert "Net Debt (FY2023)" in html
    assert "as of FY2023" in html
    assert "Minority interest and preferred stock are <b>not</b> subtracted" in html


# ── #93: a past year is taxed at its own rate ────────────────────────────────────────────────────────
def test_a_past_year_is_taxed_at_its_own_reported_rate(financials):
    """Each year's NOPAT uses that year's provision / pretax where it is believable, not today's rate (#93)."""
    rows = _historical_fcff(financials["annual"], tax_rate=0.21)
    for rec, row in zip(financials["annual"], rows):
        own = rec["tax_provision"] / rec["pretax_income"]
        assert row["tax_rate"] == pytest.approx(own)
        assert row["tax_rate_source"] == "statements"
        assert row["nopat"] == pytest.approx(rec["ebit"] * (1 - own))


def test_a_year_without_a_believable_rate_takes_the_models(financials):
    """A year the band rejects, or one with no tax lines, is restated at the model's rate — and says so."""
    annual = copy.deepcopy(financials["annual"])
    annual[0].pop("tax_provision")                        # not reported
    annual[1]["tax_provision"] = -30.0                    # a tax benefit: outside the band
    rows = _historical_fcff(annual, tax_rate=0.30)
    assert [r["tax_rate_source"] for r in rows] == ["model", "model", "statements"]
    assert rows[0]["nopat"] == pytest.approx(annual[0]["ebit"] * 0.70)
    assert rows[2]["tax_rate"] == pytest.approx(50.0 / 240.0)


def test_a_peer_row_without_a_market_cap_still_renders(financials):
    """A comps result built without the column's field (an older payload, or a hand-built one) must not raise:
    the cell reads N/A. The money, number, price and percent filters formatted Jinja's ``Undefined`` — a key the
    payload does not carry at all — and lost the whole page rather than the one cell."""
    html = build_report_html({"ticker": "TEST", "financials": financials, "warnings": [], "modules": {"comps": {
        "ticker": "TEST", "warnings": [], "pe_only": False,
        "peers": [{"ticker": "AAA", "pe": 10.0, "ev_ebitda": 9.0, "ev_revenue": 2.0}],
        "multiples": {k: {"p25": None, "p50": None, "p75": None, "count": 0}
                      for k in ("ev_ebitda", "ev_revenue", "pe")},
        "implied": {}}}})
    assert "Market Cap" in html and "N/A" in html
