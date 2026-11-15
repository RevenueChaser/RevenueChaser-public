"""ROIC is unknown when invested capital is a sliver of total assets (#831).

Measured 15 Nov 2026 on 1,091 scored names: 5 passed Quality's growth-or-ROIC half on ROIC alone with invested
capital under 5% of total assets (MANH 17,044%, MCK 634%, CAH 405%, LQDT 216%, EXTR 135%).
"""
from __future__ import annotations

from RevenueChaser.module_fundamentals.pipeline import _quality_of


def _rec(**kw):
    return {"ebit": 279.0, "total_debt": 0.0, "total_equity": 201.0, "cash": 199.0, **kw}


def test_roic_is_unknown_below_the_floor_and_unchanged_elsewhere():
    # MANH's TTM row: invested capital 2 of 751 total assets (0.27%).
    assert _quality_of(_rec(total_assets=751.0))["roic"] is None
    # At or above the floor it is scored as before (ic 100, 13% of assets).
    out = _quality_of(_rec(total_equity=299.0, total_assets=751.0))
    assert abs(out["roic"] - 279.0 * 0.79 / 100.0) < 1e-9
    # No total assets: the old rule (ic > 0) holds.
    assert _quality_of(_rec())["roic"] is not None
    assert _quality_of(_rec(total_equity=100.0))["roic"] is None
