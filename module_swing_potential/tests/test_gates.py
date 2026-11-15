"""Swing screener gates + prefilter — table-driven, no network.

Pin: prefilter thresholds (7-A since #383 R3 C12: price >= $5 and $vol >= $250K on D04's quote; the trend rules are
gone) and the auditable rules[] checklist contract for Minervini / Weinstein / Qullamaggie.
"""
import pytest

from RevenueChaser.module_swing_potential.pipeline import prefilter
from RevenueChaser.module_swing_potential.screeners import (
    evaluate_minervini,
    evaluate_qullamaggie,
    evaluate_weinstein,
)
















# ── auditable rules[] checklist contract ──
_PASS = {
    "price": 100.0, "sma50": 95.0, "sma150": 90.0, "sma200": 80.0,
    "sma200_prev_1m": 78.0, "sma150_prev_1m": 88.0,
    "above_52w_low_pct": 1.5, "within_52w_high_pct": 0.99,
    "vol_ratio": 2.0, "rs_vs_spy_3m": 0.05, "rs_vs_spy_12m": 0.1,
    "ema10": 96.0, "ema20": 92.0, "ema10_prev": 90.0, "ema20_prev": 88.0,
    "move_max_1_3m": 0.35, "adr_pct": 0.04, "ret_3m": 0.10,
}


@pytest.mark.parametrize("name,gate,expected_score", [
    ("minervini", lambda: evaluate_minervini(_PASS, rs_rating=85.0), "8/8"),
    ("weinstein", lambda: evaluate_weinstein(_PASS), "5/5"),
    ("qullamaggie", lambda: evaluate_qullamaggie(_PASS), "6/6"),
])
def test_gate_rules_checklist(name, gate, expected_score):
    g = gate()
    assert g["name"]
    assert g["passed"] is True
    assert g["score"] == expected_score
    assert len(g["rules"]) >= 5
    for r in g["rules"]:
        assert r["id"] and r["label"] and r["unit"] and r["threshold"]
        assert isinstance(r["passed"], bool)
        assert "actual" in r
