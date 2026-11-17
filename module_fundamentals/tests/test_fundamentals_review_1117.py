"""Fundamentals board review, 17 Nov 2026: the fiscal-year Rule of 40 gets the trailing year's guards, and the
summary says when SPY has no bar of the latest session.

The trailing-year point refuses a negative revenue or capex and a non-positive base (``_negative_fields``,
``nonpositive_revenue``, ``nonpositive_prior_ttm``); the fiscal-year branch did not, so a negative capex was added
into free cash flow and a negative prior year made a growth figure. Plain records, no quarters: the FY branch.
"""
from __future__ import annotations

import pytest

from RevenueChaser.module_fundamentals import report as fu_report
from RevenueChaser.module_fundamentals.pipeline import _ttm_metrics


def _year(revenue, ocf=30.0, capex=10.0) -> dict:
    return {"revenue": revenue, "operating_cash_flow": ocf, "capex": capex}


def test_a_clean_pair_of_years_still_scores():
    m = _ttm_metrics([], [_year(100.0), _year(150.0, ocf=40.0, capex=10.0)])
    assert m["ro40_basis"] == "FY"
    assert m["rev_growth_ttm"] == pytest.approx(0.5)
    assert m["fcf_margin"] == pytest.approx(0.2)
    assert m["ro40"] == pytest.approx(70.0)


def test_a_negative_capex_leaves_the_margin_and_the_rule_unknown():
    m = _ttm_metrics([], [_year(100.0), _year(150.0, ocf=40.0, capex=-50.0)])
    assert m["fcf_margin"] is None          # was (40 + 50) / 150 = 60 %: the artefact passed the Rule of 40
    assert m["ro40"] is None


def test_a_negative_prior_year_gives_no_growth():
    m = _ttm_metrics([], [_year(-20.0), _year(150.0)])
    assert m["rev_growth_ttm"] is None      # was (150 + 20) / -20 = -850 %
    assert m["ro40"] is None


def test_two_negative_years_give_no_growth_and_no_margin():
    m = _ttm_metrics([], [_year(-50.0), _year(-20.0, ocf=-5.0, capex=1.0)])
    assert m["rev_growth_ttm"] is None      # was (-20 + 50) / -50 = -60 %
    assert m["fcf_margin"] is None
    assert m["ro40"] is None


def test_the_summary_says_when_spy_has_no_bar_of_the_latest_session():
    base = {"regime": "RISK_ON", "filtered_universe": 1500, "passing": {"rule_of_40": 40}, "top_n": 10}
    assert "SPY has no bar of the latest session" in fu_report._summary_html({**base, "spy_missing": True})
    assert "SPY has no bar" not in fu_report._summary_html(base)
