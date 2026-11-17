"""Fundamentals re-review of 18 Nov 2026 (``claude-coordinator`` ``reviews/2026-11-18_0024_revenuechaser_fundamentals-
rereview/final.md``): the bugs fixed without a decision.

F4: the Period label names the basis the Rule of 40 read. G-b: gross margin is unknown under the $10M revenue mark
(completes avo C1). G-c: the old-period note is added once. F9: momentum-only names are their own funnel step (``screen_common.funnel_steps`` reads ``screen_drops``, as
for Swing's direction rule). The
gate window's "(UNKNOWN)" is in ``test_fundamentals_unknown_151``.
"""
from __future__ import annotations

from RevenueChaser.module_fundamentals import screeners
from RevenueChaser.module_fundamentals.pipeline import build_payload
from RevenueChaser.module_fundamentals.report import render_fundamental_dashboard
from RevenueChaser.module_fundamentals.screeners import OLD_PERIOD_NOTE
from RevenueChaser.module_fundamentals.tests.test_fundamentals_gates_148 import _m, _row

_MOM = dict(dist_52w_pct=0.95, rs_6m=0.1, above_200d=True)
_RO40 = dict(rev_growth_ttm=0.30, fcf_margin=0.20, ro40=50.0, ttm_revenue=5e8)


def _rule(gate: dict, rid: str) -> dict:
    return next(r for r in gate["rules"] if r["id"] == rid)


def test_gross_margin_is_unknown_under_the_revenue_mark():
    m = _m(ttm_revenue=5e6, gross_margin=0.5, roic=0.2, net_debt_ebitda=1.0)
    rule = _rule(screeners.evaluate_quality(m), "gross_margin")
    assert rule["passed"] is None and "under $10M" in rule["label"]
    # The control: above the mark the same margin decides.
    assert _rule(screeners.evaluate_quality({**m, "ttm_revenue": 5e8}), "gross_margin")["passed"] is True


def test_the_old_period_note_is_added_once():
    m = _m(rev_growth_ttm=0.3, ttm_revenue=5e8, roic=0.2, gross_margin=0.5, net_debt_ebitda=1.0, old_period=True)
    assert all(r["label"].count(OLD_PERIOD_NOTE) == 1 for r in screeners.evaluate_quality(m)["rules"])


def test_a_fiscal_year_basis_labels_the_card_with_its_years(monkeypatch):
    """C1 of the TTM filings is a trailing-year Rule of 40. When Quality cannot read that trailing year, D1 puts the
    card on the fiscal year; the label used to keep naming the quarters."""
    from RevenueChaser.core.providers import sec_edgar as se
    from RevenueChaser.module_fundamentals.tests import ttm_filings_148 as ft
    from RevenueChaser.module_fundamentals.tests.test_fundamentals_w3_386 import _compute
    (name,) = [k for k in ft.CASES if k.startswith("C1 ")]
    facts = ft.CASES[name]
    annual, quarterly = se.extract_annual(facts), se.extract_quarterly(facts)
    from RevenueChaser.module_fundamentals import pipeline
    real = pipeline._quality_metrics
    monkeypatch.setattr(pipeline, "_quality_metrics", lambda *a, **k: {**real(*a, **k), "quality_basis": "FY"})
    row, _drops = _compute(monkeypatch, annual, edgar=lambda t, no_fetch=False: (annual, quarterly, {}))
    assert row is not None
    assert row["metrics"]["ro40_basis"].startswith("FY")
    assert row["period"].startswith("FY") and "Q" not in row["period"]


def test_momentum_only_names_are_their_own_funnel_step():
    stats: dict = {}
    build_payload([_row("M", _m(**_MOM)), _row("T", _m(**_RO40, **_MOM))], top_n=10, run_stats=stats)
    assert [(k, names) for k, _label, names in stats["screen_drops"]] == [("momentum_only", ["M"])]
    assert stats["passed_screens"] == 1      # the funnel takes the step out of "passed none of the three"


def test_the_stale_text_says_the_store_is_behind_not_that_a_refetch_failed():
    p = build_payload([_row("T", _m(**_RO40, **_MOM))], top_n=10, run_stats={"stale_ohlc": 3})
    html = render_fundamental_dashboard(p)
    assert "Prices store behind" in html and "refetch failed" not in html
