"""#597 item 1: the quadrant hysteresis band.

A dot sitting on an axis flipped quadrant every week on noise. With the band an axis keeps its side until the value
crosses 100 by more than ``QUADRANT_BAND``, and the quadrant of a session is walked from the ETF's own weekly path,
so a live Fetch and a backfill of that session agree.
"""
from datetime import date

import pytest

from RevenueChaser.module_sector_rotation import engine
from RevenueChaser.module_sector_rotation.engine import (
    MIN_WEEKS,
    QUADRANT_BAND,
    classify_rrg,
    classify_sticky,
    cross_section,
    quadrant_path,
)

ALL = ("LEADING", "WEAKENING", "IMPROVING", "LAGGING")


class TestClassifySticky:
    @pytest.mark.parametrize("rz", (-1.0, -0.3, -0.01, 0.0, 0.01, 0.3, 1.0))
    @pytest.mark.parametrize("mz", (-1.0, -0.3, -0.01, 0.0, 0.01, 0.3, 1.0))
    def test_without_a_previous_quadrant_it_is_the_strict_rule(self, rz, mz):
        assert classify_sticky(rz, mz) == classify_rrg(rz, mz)

    @pytest.mark.parametrize("previous", ALL)
    @pytest.mark.parametrize("rz", (-1.0, -0.01, 0.0, 0.01, 1.0))
    @pytest.mark.parametrize("mz", (-1.0, -0.01, 0.0, 0.01, 1.0))
    def test_a_zero_band_is_the_strict_rule_whatever_came_before(self, previous, rz, mz):
        assert classify_sticky(rz, mz, previous, band=0) == classify_rrg(rz, mz)

    def test_a_dot_on_the_axis_keeps_its_quadrant(self):
        # Leading, then the ratio dips a hair under 100: noise, not a rotation out of Leading.
        assert classify_sticky(-0.1, 0.5, "LEADING", band=0.25) == "LEADING"
        # Lagging, then the ratio pokes a hair over 100: still Lagging.
        assert classify_sticky(0.1, -0.5, "LAGGING", band=0.25) == "LAGGING"

    def test_a_real_crossing_still_changes_the_quadrant(self):
        assert classify_sticky(-0.3, 0.5, "LEADING", band=0.25) == "IMPROVING"
        assert classify_sticky(0.3, -0.5, "LAGGING", band=0.25) == "WEAKENING"

    def test_the_band_is_read_on_each_axis_on_its_own(self):
        # the ratio crosses, the momentum only wobbles: one axis moves, the other keeps its side
        assert classify_sticky(-0.4, -0.1, "LEADING", band=0.25) == "IMPROVING"
        assert classify_sticky(-0.1, -0.4, "LEADING", band=0.25) == "WEAKENING"

    def test_the_band_edge_crosses(self):
        assert classify_sticky(-0.25, 0.5, "LEADING", band=0.25) == "IMPROVING"
        assert classify_sticky(0.25, -0.5, "LAGGING", band=0.25) == "WEAKENING"

    def test_the_default_band_is_positive_and_under_one_standard_deviation(self):
        """The axes are deviations over their own 52-week standard deviation, so 1.0 is a whole deviation: the old
        1.0 proposal was the retired pooled-z scale."""
        assert 0 < QUADRANT_BAND < 1.0


class TestQuadrantPath:
    @staticmethod
    def _wobble(n, rz=0.1, mz=1.0):
        """``n`` weeks whose ratio alternates either side of 100 by ``rz``, momentum steady above it."""
        return [(100 + (rz if i % 2 == 0 else -rz), 100 + mz) for i in range(n)]

    def test_a_wobble_on_the_axis_is_one_quadrant(self):
        path = quadrant_path(self._wobble(12), band=0.25)
        assert set(path) == {"LEADING"}

    def test_the_same_wobble_flips_every_week_without_a_band(self):
        path = quadrant_path(self._wobble(12), band=0)
        assert path[:4] == ["LEADING", "IMPROVING", "LEADING", "IMPROVING"]
        assert sum(path[i] != path[i - 1] for i in range(1, len(path))) == 11

    def test_the_first_week_is_classified_strictly(self):
        assert quadrant_path([(99.9, 100.5)], band=0.25) == ["IMPROVING"]

    def test_a_gap_is_blank_and_keeps_the_memory(self):
        pts = [(100.5, 100.5), None, (99.9, 100.5)]
        assert quadrant_path(pts, band=0.25) == ["LEADING", "", "LEADING"]

    def test_a_short_warm_up_prefix_is_blank(self):
        assert quadrant_path([None, None, (100.5, 100.5)], band=0.25) == ["", "", "LEADING"]

    def test_a_real_move_is_followed(self):
        pts = [(99.0, 99.0)] * 4 + [(101.0, 101.0)] * 4
        assert quadrant_path(pts, band=0.25) == ["LAGGING"] * 4 + ["LEADING"] * 4


class TestCrossSectionReadsThePath:
    def test_the_quadrant_is_the_banded_path_not_the_last_point_alone(self, monkeypatch):
        """The last week sits a hair inside the band on the other side of 100: the strict signs say LAGGING, the
        path says the ETF never left LEADING."""
        path = [(101.0, 101.0)] * (MIN_WEEKS - 1) + [(99.9, 99.9)]
        monkeypatch.setattr(engine, "jdk_series", lambda closes, spy: path)
        closes = [100.0] * MIN_WEEKS
        snap = cross_section({"XLK": closes}, closes, date(2026, 8, 14))[0]
        assert classify_rrg(snap.rs_ratio_z, snap.rs_momentum_z) == "LAGGING"
        assert snap.rrg_quadrant == "LEADING"

    def test_the_stored_axes_are_still_the_values_less_100(self, monkeypatch):
        path = [(101.0, 101.0)] * (MIN_WEEKS - 1) + [(99.9, 99.9)]
        monkeypatch.setattr(engine, "jdk_series", lambda closes, spy: path)
        closes = [100.0] * MIN_WEEKS
        snap = cross_section({"XLK": closes}, closes, date(2026, 8, 14))[0]
        assert snap.rs_ratio == pytest.approx(99.9)
        assert snap.rs_ratio_z == pytest.approx(-0.1)
        assert snap.rs_momentum_z == pytest.approx(-0.1)
