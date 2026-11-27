"""Tests for core/gex — the chain-based exposure profile and its three levels (lane A of #1431)."""
from revenuechaser.core.gex import chain_profile, strike_exposure

SPOT = 100.0


def _row(strike, option_type, gamma, oi, expiry="2026-12-18"):
    return {"strike": strike, "option_type": option_type, "gamma": gamma,
            "open_interest": oi, "expiry": expiry}


def _chain():
    """Two expiries at 105, one strike a side elsewhere, plus three rows that must be skipped."""
    return [
        _row(105, "call", 0.02, 300),                       # 60,000
        _row(105, "call", 0.01, 100, "2027-01-15"),          # 10,000
        _row(110, "call", 0.03, 100),                        # 30,000
        _row(95, "put", 0.04, 200),                          # -80,000
        _row(90, "put", 0.01, 100),                          # -10,000
        _row(100, "call", None, 500),                        # no gamma
        _row(100, "put", 0.05, None),                        # no open interest
        _row(100, "future", 0.05, 500),                      # not an option side
    ]


class TestStrikeExposure:
    def test_uw_formula_and_signs(self):
        rows = strike_exposure([_row(105, "call", 0.02, 300), _row(95, "put", 0.04, 200)], SPOT)
        assert rows[0] == {"strike": 95.0, "call": 0.0, "put": -0.04 * 200 * SPOT ** 2,
                           "net": -0.04 * 200 * SPOT ** 2}
        assert rows[1]["call"] == 0.02 * 300 * SPOT ** 2

    def test_sums_expiries_and_skips_unusable_rows(self):
        rows = strike_exposure(_chain(), SPOT)
        assert [r["strike"] for r in rows] == [90.0, 95.0, 105.0, 110.0]
        assert rows[2]["call"] == 70_000.0

    def test_no_spot_and_no_rows(self):
        assert strike_exposure(_chain(), None) == []
        assert strike_exposure([], SPOT) == []


class TestChainProfile:
    def test_levels(self):
        prof = chain_profile(_chain(), SPOT)
        assert prof["call_wall"] == 105.0            # 70,000 beats 110's 30,000
        assert prof["put_wall"] == 95.0              # -80,000 beats 90's -10,000
        # cumulative net: -10,000 / -90,000 / -20,000 / +10,000 -> the one crossing sits in 105..110
        assert round(prof["flip"], 2) == 108.33

    def test_level_with_no_strike_on_its_side_stays_none(self):
        prof = chain_profile([_row(105, "call", 0.02, 300)], SPOT)
        assert prof["call_wall"] == 105.0
        assert prof["put_wall"] is None
        assert prof["flip"] is None

    def test_empty_without_usable_rows(self):
        assert chain_profile(_chain(), None) == {}
        assert chain_profile([_row(100, "call", None, 500)], SPOT) == {}
