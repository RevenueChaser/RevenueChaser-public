"""DF45 (#45): the two sides of the comps card are on different bases, and the card says which.

Updated with #286 (20 Nov 2026): the peer side is no longer Yahoo's trailing twelve months but the store's newest
annual record, with EBITDA and enterprise value derived from it. The label moved with the figures — a card that
still said "trailing twelve months (Yahoo)" would be the one number on the page that is wrong. The target's
shares side is the prices store's since #645 (``market_meta.shares_source``), named as not stored when it has none.
"""
from __future__ import annotations

from RevenueChaser.module_financials.engines.comps_engine import PEERS_SOURCE, run_comps
from RevenueChaser.module_financials.reporting.html_builder import build_report_html


def _fetch(t):
    return {"enterpriseValue": 900.0, "ebitda": 100.0, "totalRevenue": 300.0, "trailingPE": 18.0}


def test_the_comps_result_names_each_sides_basis(financials):
    res = run_comps(financials, ["AAA", "BBB"], fetch_info=_fetch)
    latest = financials["annual"][-1]["fiscal_year"]
    assert res["basis"] == {"peers": "newest stored fiscal year", "peers_source": PEERS_SOURCE,
                            "target_fiscal_year": latest, "target_shares": "not stored"}


def test_the_board_says_which_basis_each_side_is_on(financials):
    res = run_comps(financials, ["AAA", "BBB"], fetch_info=_fetch)
    html = build_report_html({"ticker": "TEST", "financials": financials, "modules": {"comps": res},
                              "warnings": res["warnings"]})
    latest = financials["annual"][-1]["fiscal_year"]
    assert "peer multiples are newest stored fiscal year" in html and f"fiscal year {latest}" in html
    # The ampersand of "D&A" renders escaped or not depending on the template's autoescape; the claim under
    # test is that the card says the peer EBITDA is derived, not how jinja spells one character.
    assert "EBITDA = EBIT + D" in html, "the card must say the peer EBITDA is derived, not a vendor's"


def test_a_stored_comps_result_from_before_the_label_still_renders(financials):
    res = run_comps(financials, ["AAA", "BBB"], fetch_info=_fetch)
    res.pop("basis")
    html = build_report_html({"ticker": "TEST", "financials": financials, "modules": {"comps": res},
                              "warnings": res["warnings"]})
    assert "Comps Analysis" in html and "newest stored fiscal year" not in html
