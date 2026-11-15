"""ROIC is unknown when invested capital is a sliver of total assets (#831).

Measured 15 Nov 2026 on 1,091 scored names: 5 passed Quality's growth-or-ROIC half on ROIC alone with invested
capital under 5% of total assets (MANH 17,044%, MCK 634%, CAH 405%, LQDT 216%, EXTR 135%).
"""
from __future__ import annotations

from RevenueChaser.module_fundamentals.pipeline import _quality_of


def _rec(**kw):
    return {"ebit": 279.0, "total_debt": 0.0, "total_equity": 201.0, "cash": 199.0, **kw}


def test_roic_is_unknown_below_the_floor():
    # MANH's TTM row: invested capital 2 of 751 total assets (0.27%).
    assert _quality_of(_rec(total_assets=751.0))["roic"] is None


def test_roic_is_scored_at_or_above_the_floor():
    out = _quality_of(_rec(total_equity=299.0, total_assets=751.0))   # ic 100, 13% of assets
    assert abs(out["roic"] - 279.0 * 0.79 / 100.0) < 1e-9


def test_no_total_assets_keeps_the_old_rule():
    assert _quality_of(_rec())["roic"] is not None
    assert _quality_of(_rec(total_equity=100.0))["roic"] is None       # ic <= 0, as before
