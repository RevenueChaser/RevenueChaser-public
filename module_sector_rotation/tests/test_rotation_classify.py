"""Tests for the rotation engine: quadrant classification and the A1 own-history model."""
from datetime import date

import pytest

from revenuechaser.module_sector_rotation.engine import (
    MIN_WEEKS,
    classify_quadrant,
    classify_rrg,
    cross_section,
    jdk_series,
    week_cut,
)


class TestClassifyQuadrant:
    def test_strict_boundaries(self):
        assert classify_quadrant(1.0, 1.0) == "LEADING"
        assert classify_quadrant(0.0, 0.0) == "LEADING"
        assert classify_quadrant(0.5, -0.5) == "WEAKENING"
        assert classify_quadrant(-0.5, 0.5) == "IMPROVING"
        assert classify_quadrant(-0.5, -0.5) == "LAGGING"

    def test_negative_near_zero_not_leading(self):
        # -0.0001 ratio with positive momentum must be IMPROVING, never LEADING
        assert classify_quadrant(-0.0001, 0.5) == "IMPROVING"
        assert classify_quadrant(-1e-12, -1e-12) == "LAGGING"

    def test_alias_matches_classify_rrg(self):
        for rz in (-1.0, 0.0, 1.0):
            for mz in (-1.0, 0.0, 1.0):
                assert classify_quadrant(rz, mz) == classify_rrg(rz, mz)


class TestJdkSeries:
    """A1 (avo 17 Nov 2026): each ETF against its own history; pure."""

    @staticmethod
    def _series(n, drift, wiggle):
        import math
        return [100 * (1 + drift) ** i * (1 + 0.01 * math.sin(i / wiggle)) for i in range(n)]

    def test_too_short_is_none(self):
        spy = [100.0] * (MIN_WEEKS - 1)
        assert jdk_series(self._series(MIN_WEEKS - 1, 0.002, 3), spy)[-1] is None

    def test_points_sit_around_100(self):
        spy = self._series(120, 0.001, 5)
        pts = [p for p in jdk_series(self._series(120, 0.001, 3), spy) if p]
        assert len(pts) >= 120 - MIN_WEEKS + 1
        assert all(90 < r < 110 and 90 < m < 110 for r, m in pts)

    def test_a_rising_relative_line_is_right_of_100(self):
        import math
        spy = [100.0] * 120
        etf = [100 * (1 + 0.004 * math.sin(i / 2)) for i in range(110)] + [100 * 1.03 ** k for k in range(1, 11)]
        r, m = jdk_series(etf, spy)[-1]
        assert r > 100 and classify_rrg(r - 100, m - 100) in ("LEADING", "WEAKENING")

    def test_one_etf_does_not_move_another(self):
        """The old pooled z moved every dot when one ETF was added; A1 scores each alone."""
        spy = self._series(120, 0.001, 5)
        a, b = self._series(120, 0.002, 3), self._series(120, -0.003, 4)
        alone = cross_section({"XLK": a}, spy, date(2026, 8, 14))
        both = cross_section({"XLK": a, "XLE": b}, spy, date(2026, 8, 14))
        assert alone[0].rs_ratio == [s for s in both if s.ticker == "XLK"][0].rs_ratio

    def test_the_axes_are_the_values_less_100(self):
        """The quadrant is the end of the ETF's own banded path (#597), not the signs of the last point alone."""
        from revenuechaser.module_sector_rotation.engine import jdk_series, quadrant_path
        spy = self._series(120, 0.001, 5)
        etf = self._series(120, 0.002, 3)
        s = cross_section({"XLK": etf}, spy, date(2026, 8, 14))[0]
        assert s.rs_ratio_z == pytest.approx(s.rs_ratio - 100, abs=1e-6)
        assert s.rs_momentum_z == pytest.approx(s.rs_momentum - 100, abs=1e-6)
        assert s.rrg_quadrant == quadrant_path(jdk_series(etf, spy))[-1]

    def test_a_macro_series_is_not_on_the_map(self):
        spy = self._series(120, 0.001, 5)
        assert cross_section({"US10Y": self._series(120, 0.002, 3)}, spy, date(2026, 8, 14)) == []


class TestWeekCut:
    def test_a_friday_closes_its_week(self):
        assert week_cut(date(2026, 8, 14)) == date(2026, 8, 14)

    def test_a_tuesday_counts_only_the_weeks_before(self):
        assert week_cut(date(2026, 8, 11)) == date(2026, 8, 9)

    def test_a_thursday_before_a_good_friday_closes_its_week(self):
        assert week_cut(date(2026, 4, 2)) == date(2026, 4, 2)
