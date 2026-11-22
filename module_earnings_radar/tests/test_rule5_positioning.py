"""Tests for R5 positioning (the institutional lean + the none/fuel squeeze tag).

Pin: the institutional lean (bullish minus bearish print-side premium, review S4) scales with the sided premium
and is Thin under $25k; retail-call euphoria is NOT scored here (it lives in R8); unavailable is None when no
signal exists; the squeeze is a ``none`` / ``fuel`` **tag** that scores nothing, there is no peer Z ladder and a
low short interest is never bearish (#256, docs/module_earnings_radar/redesign.md R5).
"""
import pytest

from revenuechaser.module_earnings_radar.rules.rule5_positioning import score as r5_score
from revenuechaser.core.config import R5_FUEL_FEE_PCT, R5_FUEL_SI_PCT, RULE_WEIGHTS


class TestRule5Positioning:
    def test_institutional_bullish_lean(self):
        r = r5_score(institutional_net_delta=100_000.0)
        assert r.available
        assert r.score == 20.0
        assert "institutional bullish lean" in r.reasons
        assert r.coverage == pytest.approx(0.5)

    def test_institutional_bearish_lean(self):
        r = r5_score(institutional_net_delta=-100_000.0)
        assert r.score == -20.0
        assert "institutional bearish lean" in r.reasons

    def test_a_thin_lean_is_present_and_scores_nothing(self):
        r = r5_score(institutional_net_delta=24_999.0)
        assert r.available and r.score == 0.0 and r.coverage == pytest.approx(0.5)
        assert r.reasons == ["thin institutional lean"]

    def test_no_signal_unavailable_not_zero(self):
        """No flow, no short interest, no peer stats -> unavailable (None, never 0)."""
        r = r5_score()
        assert not r.available
        assert r.score is None
        assert r.coverage == 0.0

    def test_weight_config_is_consistent(self):
        assert RULE_WEIGHTS["rule1_drivers"] == 0.0
        # R5 is a TAG (no direction vote): the composite totals only R2+R3+R7+R8.
        assert abs(sum(w for w in RULE_WEIGHTS.values() if w > 0) - 0.65) < 1e-9

    def test_positioning_weight_is_zero_tag(self):
        # R5 no longer votes direction; its read is a drawer tag.
        assert RULE_WEIGHTS["rule5_positioning"] == 0.0
        assert RULE_WEIGHTS["rule8_sentiment"] == 0.10


class TestInstitutionalFlowScale:
    def test_scaled_by_imbalance(self):
        # net = 100k, sided total = 1m -> imbalance 0.1 -> +2.0
        r = r5_score(institutional_net_delta=100_000.0,
                     institutional_call_premium=550_000.0, institutional_put_premium=450_000.0)
        assert r.score == 2.0
        assert r.raw_metrics["inst_flow_imbalance"] == pytest.approx(0.1)

    def test_full_call_imbalance(self):
        r = r5_score(institutional_net_delta=100_000.0,
                     institutional_call_premium=100_000.0, institutional_put_premium=0.0)
        assert r.score == 20.0

    def test_fallback_flat_when_no_premiums(self):
        r = r5_score(institutional_net_delta=100_000.0)
        assert r.score == 20.0

    def test_zero_net_flow_is_not_a_signal(self):
        r = r5_score(institutional_net_delta=0.0)
        assert not r.available
        assert r.score is None


class TestNoRetailEuphoriaInR5:
    """Retail-call euphoria is scored by R8 only — R5 must not double-fade it."""

    def test_retail_share_args_are_not_accepted(self):
        import inspect
        params = inspect.signature(r5_score).parameters
        assert "retail_net_delta" not in params


class TestSqueezeTag:
    """#256: a ``none`` / ``fuel`` tag off the short interest or the borrow fee. No Z ladder, no points."""

    def test_high_short_interest_is_fuel_and_scores_nothing(self):
        r = r5_score(short_interest_pct_float=25.0)
        assert r.available
        assert r.score == 0.0
        assert r.raw_metrics["squeeze_tag"] == "fuel"
        assert any("squeeze fuel" in reason and "25.0%" in reason for reason in r.reasons)

    def test_expensive_borrow_alone_is_fuel(self):
        r = r5_score(borrow_fee=R5_FUEL_FEE_PCT)
        assert r.raw_metrics["squeeze_tag"] == "fuel"
        assert any("borrow fee 10.0%" in reason for reason in r.reasons)

    def test_low_short_interest_is_present_as_none_never_bearish(self):
        """The old ladder scored -10 for a quiet short book; redesign.md R5 rules that out."""
        r = r5_score(short_interest_pct_float=3.0)
        assert r.available
        assert r.score == 0.0
        assert r.coverage == pytest.approx(0.5)
        assert r.raw_metrics["squeeze_tag"] == "none"
        assert not any("no squeeze pressure" in reason for reason in r.reasons)

    def test_the_cut_is_inclusive(self):
        assert r5_score(short_interest_pct_float=R5_FUEL_SI_PCT).raw_metrics["squeeze_tag"] == "fuel"
        assert r5_score(short_interest_pct_float=R5_FUEL_SI_PCT - 0.1).raw_metrics["squeeze_tag"] == "none"

    def test_days_to_cover_is_shown_but_tags_nothing(self):
        r = r5_score(days_to_cover=12.0)
        assert not r.available
        assert r.score is None
        assert r.raw_metrics["days_to_cover"] == 12.0
        assert "squeeze_tag" not in r.raw_metrics

    def test_no_short_figures_is_missing_not_none_tag(self):
        r = r5_score(institutional_net_delta=100_000.0)
        assert r.coverage == pytest.approx(0.5)
        assert "squeeze_tag" not in r.raw_metrics

    def test_lean_and_squeeze_give_full_coverage(self):
        r = r5_score(short_interest_pct_float=25.0, borrow_fee=12.0, institutional_net_delta=100_000.0)
        assert r.coverage == 1.0
        assert r.score == 20.0  # the lean alone; the tag adds no point

    def test_no_peer_z_metrics_are_published(self):
        r = r5_score(short_interest_pct_float=25.0, borrow_fee=12.0, days_to_cover=5.0)
        assert not any(k.startswith("z_") or k == "squeeze_z_score" for k in r.raw_metrics)

    def test_no_sector_or_ticker_argument_is_accepted(self):
        import inspect
        params = inspect.signature(r5_score).parameters
        assert "sector" not in params and "ticker" not in params


class TestSqueezeTagWording:
    def test_outstanding_basis_is_named(self):
        r = r5_score(short_interest_pct_float=25.0, si_basis="outstanding")
        assert any("of shares outstanding" in reason for reason in r.reasons)

    def test_finra_day_rides_a_short_interest_reason(self):
        r = r5_score(short_interest_pct_float=25.0, short_as_of="2026-10-31")
        assert any("FINRA settled 31 Oct" in reason for reason in r.reasons)
        assert r.raw_metrics["si_as_of"] == "2026-10-31"

    def test_a_fee_only_read_does_not_claim_finras_day(self):
        """The borrow fee is IBKR's own, of today: it must not carry FINRA's settlement date."""
        r = r5_score(borrow_fee=12.0, short_as_of="2026-10-31")
        assert r.raw_metrics["squeeze_tag"] == "fuel"
        assert not any("FINRA" in reason for reason in r.reasons)
        assert "si_as_of" not in r.raw_metrics
