"""#150 (#232 folded in): the AG header says how many names were SCORED of how many were screened, and why
the others have no card. Synthetic store, no network.

The ledger's freeze guard computes attempted = universe_total - excluded_types and reads score_errors
(``freeze.py::_score_error_problem``): those three inputs keep their meaning.
"""
from __future__ import annotations

import copy

import pytest

from revenuechaser.rcdata.tests import fund_store
from revenuechaser.core import funnel
from revenuechaser.module_asymmetric_growth import engine, freeze
from revenuechaser.module_asymmetric_growth.report import render_asymmetric_growth_hunter_html
from revenuechaser.module_asymmetric_growth.tests.test_ag_info_only_150 import _ANNUAL, _QUOTE, _edgar




def _row(t, quote=True):
    return {"ticker": t, "quote": dict(_QUOTE) if quote else {}, "market_cap": 5e9}




def _steps(result):
    return {s["key"]: s for s in result["funnel_steps"]}


















# ── the board ───────────────────────────────────────────────────────────────

_THR = {"rev_growth": 0.2, "gross_margin": 0.4, "net_debt_assets": 0.1, "runway": 2.0, "dist_52w": 0.1,
        "vol_ratio": 1.4, "rd_intensity": 0.15, "dilution": 0.2, "accelerating": True, "fcf": True,
        "above_sma50": True}


def _html(result_extra=None, **summary):
    r = {"asof": "2026-08-23T00:00:00", "universe_total": 5000, "universe_generated_at": "2026-08-24T10:00:00+00:00",
         "universe_refreshed_by": "Asymmetric Growth",
         "summary": {"scanned": 3000, "excluded_types": 1000, "pts_9": 0, "pts_8_7": 0, "pts_6_5": 0, "pts_lt5": 3000,
                     "disruptive_themed": 0, "tech_breakthrough": 0, **summary},
         "thresholds": _THR, "cards": []}
    r.update(result_extra or {})
    return render_asymmetric_growth_hunter_html(r)


def _steps_for(**over):
    S = funnel.step
    return [S("universe", "Universe, all market caps", 5000, "start"),
            S("excluded_types", "Excluded security types", 1000, "drop", by_design=True),
            S("no_annual", "No annual financials", 400, "drop", by_design=False, tickers=["AAA", "BBB"]),
            S("foreign", "Non-US filers", 600, "drop", by_design=True),
            S("scored", "Scored", 3000, "result")]


def test_the_header_tile_is_the_scored_count_with_the_screened_count(rawstore_tmp_db):
    page = _html({"funnel_steps": _steps_for()})
    assert "Scanned Universe" not in page
    assert '<div class="v">3000</div><div class="l">Scored</div>' in page
    assert "of 4000 screened" in page and "5000 in universe" in page


def test_the_funnel_rows_name_every_reason_and_list_the_names(rawstore_tmp_db):
    page = _html({"funnel_steps": _steps_for()})
    for label in ("Universe, all market caps", "Excluded security types", "No annual financials", "Non-US filers"):
        assert label in page
    assert "AAA" in page and "BBB" in page


def test_a_run_without_a_funnel_keeps_the_old_tile(rawstore_tmp_db):
    page = _html()
    assert "Scanned Universe" in page and '<div class="v">5000</div>' in page


def test_funnel_text_is_escaped(rawstore_tmp_db):
    steps = _steps_for()
    steps[2]["label"] = "<img src=x onerror=alert(1)>"
    steps[2]["tickers"] = ["<script>alert(2)</script>"]
    page = _html({"funnel_steps": steps})
    assert "<img src=x" not in page and "<script>alert(2)" not in page
    assert "&lt;img src=x" in page




def test_a_funnel_that_does_not_add_up_is_not_shown(rawstore_tmp_db):
    steps = _steps_for()
    steps[-1]["count"] = 2999
    page = _html({"funnel_steps": steps})
    assert "funnel-panel" not in page and "Scanned Universe" in page


# ── #383 C16: the shared funnel panel (byte-identical to the board's old markup) ──

_GOLDEN_STEPS = [
    funnel.step("universe", "Universe", 3, "start"),
    funnel.step("no_annual", "No annual financials", 2, "drop", by_design=False, tickers=["AAA", "BBB"]),
    funnel.step("scored", "Scored", 1, "result"),
]
_GOLDEN_PANEL = (
    '<details class="rules" id="funnel-panel"><summary>Universe to scored: where names drop out</summary>'
    '<div class="rules-body"><table><tr><th>Step</th><th>Names</th><th></th></tr>'
    '<tr><td>Universe</td><td>3</td><td></td></tr>'
    '<tr><td>No annual financials<div class="note">AAA, BBB</div></td><td>&minus;2</td><td>needs a look</td></tr>'
    '<tr><td>Scored</td><td>1</td><td></td></tr></table></div></details>')


def test_the_ag_funnel_panel_is_byte_identical_to_today(rawstore_tmp_db):
    """#383 C16: the shared ``funnel_panel_html`` keeps the exact markup AG rendered before the move."""
    from revenuechaser.core import funnel as f
    from revenuechaser.module_asymmetric_growth.report import _universe_tile_and_funnel
    assert f.funnel_panel_html(_GOLDEN_STEPS) == _GOLDEN_PANEL
    _, panel = _universe_tile_and_funnel({"universe_total": 3, "funnel_steps": _GOLDEN_STEPS}, {})
    assert panel == _GOLDEN_PANEL
