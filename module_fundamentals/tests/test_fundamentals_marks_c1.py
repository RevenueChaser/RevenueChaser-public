"""avo C1 and F1 (17 Nov 2026): a marked input makes the rule that reads it unknown, and the card shows ROIC.

C1: a distorted growth (beyond ±200 %), a micro revenue base (under $10M) or a period that ended more than
``fiscal_year.STALE_DAYS`` ago no longer passes a rule; the rule is unknown and its label says why.
F1: the card carries ROIC and the old-period flag; P/E and P/B left it.
"""
from __future__ import annotations

from datetime import date

from revenuechaser.module_fundamentals import pipeline, screeners
from revenuechaser.module_fundamentals.tests.test_fundamentals_gates_148 import _m, _row


def _rule(gate: dict, rid: str) -> dict:
    return next(r for r in gate["rules"] if r["id"] == rid)


def test_a_distorted_growth_no_longer_passes_growth_or_roic():
    m = _m(rev_growth_ttm=3.0, ttm_revenue=5e8, gross_margin=0.5, net_debt_ebitda=1.0)
    rule = _rule(screeners.evaluate_quality(m), "growth_or_roic")
    assert rule["passed"] is None and "distorted" in rule["label"]


def test_a_micro_revenue_base_leaves_the_rule_of_40_unknown():
    m = _m(rev_growth_ttm=0.3, fcf_margin=0.2, ro40=50.0, ttm_revenue=5e6)
    rule = screeners.evaluate_rule_of_40(m)["rules"][0]
    assert rule["passed"] is None and "under $10M" in rule["label"]


def test_an_old_period_leaves_every_quality_rule_unknown():
    m = _m(rev_growth_ttm=0.3, ttm_revenue=5e8, roic=0.2, gross_margin=0.5, net_debt_ebitda=1.0, old_period=True)
    assert all(r["passed"] is None for r in screeners.evaluate_quality(m)["rules"])
    assert screeners.evaluate_rule_of_40({**m, "fcf_margin": 0.2, "ro40": 50.0})["rules"][0]["passed"] is None


def test_the_period_is_old_after_470_days(monkeypatch):
    monkeypatch.setattr(pipeline, "_today", lambda: date(2026, 11, 17))
    assert pipeline._old_period("2025-06-30") is True          # 505 days
    assert pipeline._old_period("2025-12-31") is False         # 321 days
    assert pipeline._old_period(None) is False


def test_the_card_carries_roic_and_the_old_flag_not_pe_or_pb():
    row = _row("AAA", _m(rev_growth_ttm=0.3, fcf_margin=0.2, ro40=50.0, ttm_revenue=5e8, roic=0.2,
                         pe=15.0, pb=2.0))
    c = pipeline.build_payload([row], run_stats={})["candidates"][0]
    assert c["roic"] == 0.2 and c["old_period"] is False
    assert "pe" not in c and "pb" not in c


def test_a_short_history_is_scored_with_momentum_unknown(monkeypatch):
    """avo E1: under 252 bars the name is scored on its filings; the Momentum inputs are unknown, not dropped."""
    from revenuechaser.module_fundamentals.tests.test_fundamentals_w3_386 import _annual_pair, _patch_row
    _patch_row(monkeypatch, _annual_pair())
    monkeypatch.setattr(pipeline, "ohlc_drop_reason", lambda df: "short_bars")
    drops: list = []
    row = pipeline._compute_row({"ticker": "T"}, None, spine={}, drops=drops)
    assert row is not None and drops == []
    m = row["metrics"]
    assert (m["dist_52w_pct"], m["rs_6m"], m["above_200d"]) == (None, None, None)
    assert all(r["passed"] is None for r in screeners.evaluate_momentum(m)["rules"])
