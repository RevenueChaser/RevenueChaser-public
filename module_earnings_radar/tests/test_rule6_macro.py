"""R6 — Macro (veto-only). Table-driven, no network.

Pin: unavailable is None (never 0); a beta above ``R6_RATE_VETO`` vetoes and one above ``R6_RATE_HIGH`` is a
reason only; regulatory_risk='low' is not a signal; yield_beta needs >=20 paired returns and nonzero yield
variance. The cases are written off the constants, never off a literal 2 / 4, so a recalibration (#635) does
not silently turn a veto case into a badge case.
"""
from datetime import date, timedelta

import pytest

from RevenueChaser.core.config import R6_RATE_HIGH, R6_RATE_VETO
from RevenueChaser.module_earnings_radar.rules.rule6_macro import score, yield_beta

EXTREME = R6_RATE_VETO + 1.0        # above the veto cut
HIGH = (R6_RATE_HIGH + R6_RATE_VETO) / 2.0      # between the two cuts: reason only
MILD = R6_RATE_HIGH / 2.0           # below both


def _series(n=22, duration=10.0, y0=4.00, dy_pp=0.10, p0=100.0):
    """n dated (stock, yield-percent) points whose OLS beta ≈ -duration.

    Yield *changes* must vary (constant Δy makes var(Δy)=0 and beta undefined).
    """
    stock, yld = {}, {}
    price = p0
    y = y0
    start = date(2026, 1, 5)
    for i in range(n):
        d = (start + timedelta(days=i)).isoformat()
        stock[d] = price
        yld[d] = y
        step = 0.0 if dy_pp == 0 else dy_pp * (0.5 + (i % 3) * 0.5)
        price *= 1.0 + (-duration * (step / 100.0))
        y += step
    return stock, yld


def test_no_signals_unavailable_not_zero():
    r = score()
    assert r.available is False
    assert r.score is None
    assert r.coverage == 0
    assert r.flags == []


def test_extreme_rate_sensitivity_is_badge_not_veto_without_overlap():
    """A beta above the veto cut alone is a badge (reason), never NO_TRADE — a rate event
    (FOMC/CPI) must overlap the earnings window for the veto (design doc)."""
    r = score(rate_sensitivity=EXTREME)
    assert r.available is True
    assert r.flags == []                    # no veto
    assert r.raw_metrics.get("rate_badge") is True
    assert any("extreme rate sensitivity" in x for x in r.reasons)


def test_extreme_rate_sensitivity_veto_with_overlap():
    r = score(rate_sensitivity=EXTREME, rate_event_overlap=True, beta_tstat=3.1)
    assert r.raw_metrics.get("beta_tstat") == 3.1   # the card carries the t value (#635)
    assert r.available is True
    assert r.flags == ["extreme rate sensitivity"]
    assert any("macro veto" in x for x in r.reasons)


def test_extreme_beta_noisy_tstat_never_vetoes():
    """|t| < 2 on the beta -> noisy -> no veto even with an overlap."""
    r = score(rate_sensitivity=EXTREME, rate_event_overlap=True, beta_tstat=1.2)
    assert r.available is True
    assert r.flags == []
    assert r.raw_metrics.get("noisy_beta") is True


def test_extreme_beta_without_tstat_is_badge_only():
    """#635 (owner, 10 Nov 2026: "olmasın, sadece rozet"): a beta with no t statistic has no evidence it is
    real, so it is noisy by definition - badge, never a veto, even on a CPI/FOMC overlap."""
    r = score(rate_sensitivity=EXTREME + 3.7, rate_event_overlap=True, beta_tstat=None)
    assert r.flags == []
    assert r.raw_metrics.get("noisy_beta") is True
    assert r.raw_metrics.get("beta_tstat") is None
    assert r.raw_metrics.get("rate_badge") is True


def test_overlap_without_extreme_beta_no_veto():
    r = score(rate_sensitivity=R6_RATE_HIGH, rate_event_overlap=True)
    assert r.available is True
    assert r.flags == []
    assert any("rate event overlap" in x for x in r.reasons)


def test_no_overlap_answer_keeps_the_badge_only():
    """E5d (#372): ``None`` means the stored calendar does not span the window. It is not an overlap, so the
    extreme duration stays a badge and nothing is said about an overlap that was never established."""
    r = score(rate_sensitivity=EXTREME, rate_event_overlap=None)
    assert r.available is True
    assert r.flags == []
    assert r.raw_metrics.get("rate_badge") is True
    assert not any("rate event" in x for x in r.reasons)


def test_a_stored_overlap_with_an_extreme_beta_is_the_veto():
    r = score(rate_sensitivity=EXTREME, rate_event_overlap=True, beta_tstat=3.1)
    assert r.flags == ["extreme rate sensitivity"]
    assert any("macro veto" in x for x in r.reasons)


def test_high_but_not_extreme_rate_sensitivity():
    r = score(rate_sensitivity=HIGH)
    assert r.available is True
    assert r.flags == []
    assert r.score == -15.0
    assert any("high rate sensitivity" in x for x in r.reasons)


def test_mild_rate_sensitivity_no_penalty():
    r = score(rate_sensitivity=MILD)
    assert r.available is True
    assert r.flags == []
    assert r.score == 0.0


def test_high_regulatory_risk_veto():
    r = score(regulatory_risk="High regulatory exposure")
    assert r.available is True
    assert r.flags == ["regulatory: High regulatory exposure"]
    assert r.score == -20.0


def test_sanction_regulatory_risk_veto():
    r = score(regulatory_risk="sanction risk")
    assert r.available is True
    assert len(r.flags) == 1
    assert "sanction" in r.flags[0]


def test_low_regulatory_risk_is_not_a_signal():
    r = score(regulatory_risk="low")
    assert r.available is False
    assert r.score is None
    assert r.flags == []


def test_consensus_crowded():
    r = score(consensus_long=True)
    assert r.available is True
    assert r.score == -15.0


def test_fx_tailwind_inflating_growth():
    r = score(constant_currency_growth=0.05, reported_growth=0.10)
    assert r.available is True
    assert r.score == -10.0


def test_fx_tailwind_small_no_penalty():
    r = score(constant_currency_growth=0.10, reported_growth=0.11)
    assert r.available is True
    assert r.score == 0.0


def test_geopolitical_and_fx():
    r = score(geopolitical_risk="Tensions", fx_exposure=0.40)
    assert r.available is True
    assert r.score == -30.0  # -20 geo + -10 fx


def test_geopolitical_low_is_not_a_signal():
    r = score(geopolitical_risk="none")
    assert r.available is False
    assert r.score is None


class TestYieldBeta:
    def test_duration_ten_recovers(self):
        stock, yld = _series(n=25, duration=10.0)
        b = yield_beta(stock, yld)
        assert b == pytest.approx(-10.0, abs=0.05)

    def test_too_few_observations_is_none(self):
        stock, yld = _series(n=10, duration=10.0)
        assert yield_beta(stock, yld) is None

    def test_empty_is_none(self):
        assert yield_beta({}, {"2026-01-01": 4.0}) is None
        assert yield_beta({"2026-01-01": 100.0}, {}) is None

    def test_zero_yield_variance_is_none(self):
        stock, yld = _series(n=25, duration=10.0, dy_pp=0.0)
        assert yield_beta(stock, yld) is None

    def test_unpaired_dates_ignored(self):
        stock, yld = _series(n=25, duration=5.0)
        yld["1999-01-01"] = 3.0
        stock["1999-12-31"] = 1.0
        b = yield_beta(stock, yld)
        assert b == pytest.approx(-5.0, abs=0.05)


# The |beta| of every card of the one run that is still on disk (``earnings_radar_latest.html``, 10 Nov 2026:
# 35 cards, the 33 whose R6 reason printed a figure), read read-only on homesrv on 20 Nov 2026 and filed on
# #635. It is the only measured distribution of this rule's input that exists — the per-card history went with
# #860 — so the thresholds are checked against it rather than against a number someone liked.
MEASURED_ABS_BETA = (
    2.5, 2.8, 3.1, 3.3, 3.5, 3.8, 6.2, 6.4, 6.4, 6.6, 7.4, 7.6, 8.3, 10.1, 10.1, 12.6, 14.1, 15.7, 15.7,
    16.0, 16.7, 16.8, 16.8, 17.9, 21.6, 22.4, 22.9, 23.4, 24.4, 25.8, 27.3, 33.6, 47.4,
)


def _share_above(cut: float) -> float:
    return sum(1 for b in MEASURED_ABS_BETA if b > cut) / len(MEASURED_ABS_BETA)


class TestTheThresholdsSitInTheTail:
    """#635 item 1: the badge has to land on a tail of the beta's own scale, not on the body.

    The old pair (2.0 / 4.0) was on another scale: it marked 100% and 82% of a run's names, and that is how
    one Fetch went from 0 to 8 ``NO_TRADE``. Both cases read the source constants, so both are red on the base.
    """

    def test_the_veto_cut_marks_a_tail_not_the_body(self):
        share = _share_above(R6_RATE_VETO)
        assert share <= 0.15, f"R6_RATE_VETO={R6_RATE_VETO} vetoes {share:.0%} of the measured run"
        median = sorted(MEASURED_ABS_BETA)[len(MEASURED_ABS_BETA) // 2]
        assert R6_RATE_VETO > median

    def test_the_high_cut_marks_at_most_the_upper_quartile(self):
        share = _share_above(R6_RATE_HIGH)
        assert share <= 0.30, f"R6_RATE_HIGH={R6_RATE_HIGH} badges {share:.0%} of the measured run"
        # A cut above every measured name would say nothing either: the badge stays reachable, below the veto.
        assert share > 0.0
        assert R6_RATE_HIGH < R6_RATE_VETO
        median = sorted(MEASURED_ABS_BETA)[len(MEASURED_ABS_BETA) // 2]
        assert R6_RATE_HIGH > median
