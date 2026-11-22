"""The Fundamentals board cleanup of the 16 Nov 2026 plan (claude-coordinator
``plans/2026-11-16_1712_revenuechaser_fundamentals-issues-plan.md`` step 3, decisions E, F, G, H): the liquidity
label, the Rule of 40 barrier both ways, the old-year mark, no empty theme row, 44 px targets and a debounced search.
"""
from __future__ import annotations

from revenuechaser.module_fundamentals import config
from revenuechaser.module_fundamentals.pipeline import build_payload
from revenuechaser.module_fundamentals.report import _summary_html, render_fundamental_dashboard
from revenuechaser.module_fundamentals.screeners import evaluate_rule_of_40, is_distorted


def test_a_rule_of_40_below_minus_the_barrier_is_unknown_and_distorted_too():
    """RLAY -1,483 and ROIV -9,255 were plain fails on the live board."""
    low = {"ro40": -config.RO40_BARRIER - 1, "ro40_basis": "TTM", "rev_growth_ttm": 0.1, "ttm_revenue": 2e9}
    gate = evaluate_rule_of_40(low)
    assert gate["rules"][0]["passed"] is None and "beyond ±150" in gate["rules"][0]["label"]
    assert is_distorted(low)
    plain = {**low, "ro40": -100.0}
    assert evaluate_rule_of_40(plain)["rules"][0]["passed"] is False and not is_distorted(plain)


def test_the_price_floor_count_is_called_the_liquidity_filter_not_hygiene():
    html = _summary_html({"hygiene": 1960})
    assert "liquidity filter (price, dollar volume) 1,960" in html and "hygiene" not in html


def test_the_card_marks_an_old_anchor_year_and_shows_no_theme_row():
    html = render_fundamental_dashboard(build_payload([], run_stats={}))
    assert "OLD YEAR" in html and "return !!c.old_period" in html       # avo C1: the build decides, 470 days
    assert "tagsRow" not in html and 'class="tags' not in html


def test_touch_targets_are_44_px_and_the_search_waits_for_a_pause():
    html = render_fundamental_dashboard(build_payload([], run_stats={}))
    assert ".tab{padding:0 14px;height:44px" in html and ".gate{flex:1;min-height:44px" in html
    assert 'oninput="renderSoon()"' in html and "setTimeout(render, 150)" in html
