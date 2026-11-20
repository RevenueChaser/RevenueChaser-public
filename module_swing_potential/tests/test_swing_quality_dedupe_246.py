"""Swing #246 finding 7: a rule two methods share scores once, not twice.

The 40/30/30 quality used to add up each gate's known passes over that gate's own rule total, so a fact both
Minervini and Weinstein test earned points twice. Two pairs are the same fact said twice, and of each pair the
weaker twin now leaves the quality count (``config.Q_SHARED_RULES``):

  * Minervini ``price_above_150_200`` (above the 150- AND the 200-day MA) implies Weinstein ``price_above_30w``
    (the 30-week MA *is* ``sma150``)                            -> the Weinstein rule is dropped
  * Weinstein ``overhead_breakout`` (>= 98 % of the 52-week high) implies Minervini ``within_52w_high`` (>= 75 %)
    -> the Minervini rule is dropped

Each screener still evaluates, shows and decides on every one of its own rules; only the quality count changes.
Offline, synthetic indicators, no network.
"""
from __future__ import annotations

import itertools

from RevenueChaser.module_swing_potential import config
from RevenueChaser.module_swing_potential.ranking import counted_passes, quality_403030
from RevenueChaser.module_swing_potential.screeners import (
    evaluate_minervini,
    evaluate_qullamaggie,
    evaluate_weinstein,
)

# The implication pairs the dedupe rests on: (stronger gate, stronger rule, weaker gate, weaker rule).
PAIRS = (
    ("minervini", "price_above_150_200", "weinstein", "price_above_30w"),
    ("weinstein", "overhead_breakout", "minervini", "within_52w_high"),
)


def _ind(**over) -> dict:
    """Every indicator a candidate needs; all three method gates pass on these values."""
    ind = {
        "price": 100.0, "sma50": 95.0, "sma150": 90.0, "sma200": 80.0,
        "sma200_prev_1m": 78.0, "sma150_prev_1m": 88.0, "ema10": 96.0,
        "ema20": 92.0, "ema10_prev": 90.0, "ema20_prev": 88.0,
        "above_52w_low_pct": 1.5, "within_52w_high_pct": 0.99, "vol_ratio": 2.0,
        "rs_vs_spy_3m": 0.05, "rs_vs_spy_12m": 0.1, "move_max_1_3m": 0.35,
        "adr_pct": 0.04, "range_recent": 0.02, "range_before": 0.03,
        "atr14": 2.0, "ret_3m": 0.10,
    }
    ind.update(over)
    return ind


def _gates(ind: dict, rs_rating: float | None = 90.0) -> dict:
    return {"minervini": evaluate_minervini(ind, rs_rating),
            "weinstein": evaluate_weinstein(ind),
            "qullamaggie": evaluate_qullamaggie(ind)}


def _rule(gate: dict, rule_id: str) -> dict:
    return next(r for r in gate["rules"] if r["id"] == rule_id)


def test_the_counted_total_of_each_gate_is_its_rules_minus_its_shared_twins():
    """``Q_RULE_TOTALS`` is not a hand-kept number: it is each gate's rule count less its dropped twins."""
    gates = _gates(_ind())
    for key, gate in gates.items():
        shared = config.Q_SHARED_RULES.get(key, ())
        ids = [r["id"] for r in gate["rules"]]
        assert set(shared) <= set(ids), f"{key}: a shared rule id that gate does not have: {shared}"
        assert config.Q_RULE_TOTALS[key] == len(ids) - len(shared), key
    # Every pair names a rule that exists on both sides, and the dropped one is the weaker twin.
    for strong_gate, strong_rule, weak_gate, weak_rule in PAIRS:
        assert strong_rule in [r["id"] for r in gates[strong_gate]["rules"]]
        assert weak_rule in config.Q_SHARED_RULES[weak_gate]
        assert strong_rule not in config.Q_SHARED_RULES.get(strong_gate, ())


def test_the_dropped_twin_is_the_one_its_stronger_rule_implies():
    """Over a grid of inputs: whenever the stronger rule is a known pass, so is the weaker twin it replaces."""
    seen = {p: 0 for p in PAIRS}
    for price, sma150, sma200, high_pct in itertools.product(
            (80.0, 100.0), (90.0, 110.0), (85.0, 105.0), (0.70, 0.80, 0.99)):
        gates = _gates(_ind(price=price, sma150=sma150, sma200=sma200, within_52w_high_pct=high_pct))
        for pair in PAIRS:
            strong_gate, strong_rule, weak_gate, weak_rule = pair
            strong = _rule(gates[strong_gate], strong_rule)["passed"]
            weak = _rule(gates[weak_gate], weak_rule)["passed"]
            if strong is True:
                seen[pair] += 1
                assert weak is True, f"{strong_rule} passed but {weak_rule} did not: {price}/{sma150}/{sma200}/{high_pct}"
    assert all(count > 0 for count in seen.values()), seen      # the grid really exercised both implications


def test_quality_counts_a_shared_fact_once_and_tops_out_at_100():
    gates = _gates(_ind())
    counts = {key: counted_passes(key, gate) for key, gate in gates.items()}
    assert counts == {"minervini": 7, "weinstein": 4, "qullamaggie": 7}
    assert quality_403030(counts["minervini"], counts["weinstein"], counts["qullamaggie"]) == 100


def test_the_gates_own_pass_and_score_still_see_every_rule():
    """The dedupe is only the quality count: each screener is unchanged, twins and all."""
    gates = _gates(_ind())
    assert gates["minervini"]["passed"] is True and gates["minervini"]["score"] == "8/8"
    assert gates["weinstein"]["passed"] is True and gates["weinstein"]["score"] == "5/5"
    assert gates["qullamaggie"]["passed"] is True and gates["qullamaggie"]["score"] == "7/7"
    assert [g["total"] for g in gates.values()] == [8, 5, 7]
    assert counted_passes("weinstein", gates["weinstein"]) == 4      # ... while quality counts four of the five


def test_an_unknown_rule_is_still_never_counted():
    gates = _gates(_ind(ema10=None))                                 # two Qullamaggie rules go unknown
    q = gates["qullamaggie"]
    assert [r["passed"] for r in q["rules"] if r["id"] == "price_above_ema10"] == [None]
    assert counted_passes("qullamaggie", q) < 7
