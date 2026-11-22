"""avo D1 (17 Nov 2026): one period per card, the trailing year else the fiscal year, for every rule.

Review N1: Quality used to fall back to the fiscal year whenever the trailing year left a figure undefined that the
year had, so a company that turned to a loss kept its older, profitable leverage ratio. Now the trailing year stands.
Fixtures: the G6 test's records (``test_quality_ttm_g6``).
"""
from __future__ import annotations

import copy

import pytest

from revenuechaser.module_fundamentals import pipeline, screeners
from revenuechaser.module_fundamentals.tests.test_quality_ttm_g6 import ANNUAL, QUARTERLY


def _loss_quarters():
    quarterly = copy.deepcopy(QUARTERLY)
    quarterly[1]["ytd"]["ebit"]["val"] = -300.0     # TTM EBIT 200 - 300 - 80 = -180, EBITDA -128; net debt 150
    return quarterly


def test_a_trailing_loss_with_net_debt_is_read_on_the_trailing_year_and_fails_leverage():
    q = pipeline._quality_metrics(ANNUAL, _loss_quarters())
    assert (q["quality_basis"], q["quality_period_end"]) == ("TTM", "2026-06-30")   # was FY, ratio 1.6
    assert q["net_debt_ebitda"] is None and q["net_cash"] is False
    rule = next(r for r in screeners.evaluate_quality(q)["rules"] if r["id"] == "net_debt_ebitda")
    assert rule["passed"] is False


def test_quality_reads_the_year_when_the_rule_of_40_does():
    q = pipeline._quality_metrics(ANNUAL, QUARTERLY, trailing=False)
    assert (q["quality_basis"], q["quality_period_end"]) == ("FY", "2025-12-31")
    assert q["net_debt_ebitda"] == pytest.approx(1.6)
