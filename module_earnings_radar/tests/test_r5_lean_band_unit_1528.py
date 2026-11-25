"""#1528: the expected move reaches R5's lean band as a fraction, not as percent. Offline.

``_expected_move_pct`` serves the implied earnings move in **percent** (8% comes back as ``8.0``), while the
lean's strike band is ``spot x (1 +/- move x slack)`` and wants a **fraction**. Handing the percent over made
the band 1200% wide for an 8% move, so ``low`` went negative and every strike passed: R5's lean read the whole
tape instead of the band around spot. The conversion now has its own name (``_lean_move_frac``) and the slice's
parameter carries its unit (``expected_move_frac``).
"""
from datetime import date

import pytest

from revenuechaser.core.config import R5_LEAN_BAND_SLACK
from revenuechaser.module_earnings_radar import lean
from revenuechaser.module_earnings_radar.pipeline import _expected_move_pct, _lean_move_frac

ED = date(2026, 8, 14)


def _print(strike, day="2026-08-13", expiry="2026-08-21"):
    return {"executed_at": f"{day}T16:00:00Z", "strike": strike, "expiry": expiry,
            "premium": 50_000.0, "size": 50, "option_type": "call"}


class TestConversion:
    def test_the_percent_the_pipeline_carries_becomes_a_fraction(self):
        """UW's 0.08 ratio is 8.0 percent on the card, and 0.08 again for the band."""
        assert _expected_move_pct({"expected_move_perc": 0.08}) == pytest.approx(8.0)
        assert _lean_move_frac(_expected_move_pct({"expected_move_perc": 0.08})) == pytest.approx(0.08)

    def test_no_expected_move_is_unknown_not_zero(self):
        assert _lean_move_frac(0.0) is None
        assert _lean_move_frac(None) is None
        assert _lean_move_frac("") is None


class TestBand:
    def test_an_eight_percent_move_drops_a_strike_thirty_percent_away(self):
        # 8% x slack 1.5 -> 88.0 .. 112.0, so the 130 strike is no earnings bet on this report.
        frac = _lean_move_frac(_expected_move_pct({"expected_move_perc": 0.08}))
        kept = lean.select([_print(105.0), _print(130.0)], spot=100.0, expected_move_frac=frac, earnings_date=ED)
        assert [p["strike"] for p in kept] == [105.0]

    def test_the_band_edge_is_the_move_widened_by_the_slack(self):
        frac = _lean_move_frac(_expected_move_pct({"expected_move_perc": 0.08}))
        edge = 100.0 * (1 + 0.08 * R5_LEAN_BAND_SLACK)
        kept = lean.select([_print(edge), _print(edge + 0.01)], spot=100.0, expected_move_frac=frac,
                           earnings_date=ED)
        assert [p["strike"] for p in kept] == [pytest.approx(edge)]

    def test_the_low_edge_stays_above_zero(self):
        """A percent band made ``low`` negative, which is how every strike passed."""
        frac = _lean_move_frac(_expected_move_pct({"expected_move_perc": 0.08}))
        kept = lean.select([_print(1.0)], spot=100.0, expected_move_frac=frac, earnings_date=ED)
        assert kept == []
