"""#597 item 2: the early-turn flag scored against the stored snapshots.

The flag claims a bottom turn: momentum above 100 while the ratio is still below it, so the ratio should follow.
``early_turn.brier`` reads the stored weeks and says how often it did, as a hit rate and as a Brier score against
the base rate of the same pool. Pure: these tests pass stored rows, nothing is read or fetched.
"""
from datetime import date, timedelta

import pytest

from revenuechaser.module_sector_rotation import early_turn
from revenuechaser.module_sector_rotation.early_turn import (
    PRIOR_WEEKS,
    band_scan,
    brier,
    caption,
    flagged_weeks,
    is_early_turn,
    points_from_prices,
    weekly_points,
)
from revenuechaser.module_sector_rotation.tests.bars_seed import ny, pin_clock, seed

FRIDAY = date(2026, 8, 7)              # a Friday: the last session of its ISO week


def weeks(n: int, start: date = FRIDAY) -> list[date]:
    return [start + timedelta(weeks=i) for i in range(n)]


def history(series: dict[str, list[tuple | None]], days: list[date] | None = None) -> dict:
    """``store.load_range`` shape from ``{ticker: [(rz, mz) | None per week]}``."""
    length = max(len(v) for v in series.values())
    days = days or weeks(length)
    out: dict[str, list[dict]] = {}
    for i, day in enumerate(days):
        rows = []
        for ticker, points in series.items():
            p = points[i] if i < len(points) else None
            if p is None:
                continue
            rows.append({"as_of_date": day.isoformat(), "ticker": ticker,
                         "rs_ratio_z": p[0], "rs_momentum_z": p[1]})
        if rows:
            out[day.isoformat()] = rows
    return out


class TestTheRule:
    def test_momentum_up_twice_with_the_ratio_still_low_is_an_early_turn(self):
        assert is_early_turn(-0.5, 0.5, [0.4, 0.3]) is True

    def test_a_ratio_already_above_100_is_not_an_early_turn(self):
        assert is_early_turn(0.5, 0.5, [0.4, 0.3]) is False

    def test_momentum_below_100_now_is_not_an_early_turn(self):
        assert is_early_turn(-0.5, -0.1, [0.4, 0.3]) is False

    def test_one_prior_week_below_100_breaks_it(self):
        assert is_early_turn(-0.5, 0.5, [0.4, -0.1]) is False

    def test_too_few_prior_weeks_is_not_met_by_absence(self):
        assert is_early_turn(-0.5, 0.5, [0.4]) is False
        assert is_early_turn(-0.5, 0.5, []) is False

    def test_a_missing_prior_value_is_not_read_as_positive(self):
        assert is_early_turn(-0.5, 0.5, [0.4, None]) is False

    def test_a_missing_value_now_is_not_flagged(self):
        assert is_early_turn(None, 0.5, [0.4, 0.3]) is False
        assert is_early_turn(-0.5, None, [0.4, 0.3]) is False

    def test_the_rule_wants_two_prior_weeks(self):
        assert PRIOR_WEEKS == 2

    def test_flagged_weeks_marks_the_first_week_that_has_its_priors(self):
        series = [(99.0, 100.4), (99.1, 100.3), (99.2, 100.5), (99.3, 99.7)]
        assert flagged_weeks(series) == [False, False, True, False]


class TestWeeklyPoints:
    def test_two_sessions_standing_for_one_week_are_one_point_the_later_one(self):
        # Friday 7 Aug closes its week; Wednesday 12 Aug stands for that same completed week.
        rows = {"2026-08-07": [{"ticker": "ITA", "rs_ratio_z": -0.9, "rs_momentum_z": 0.1}],
                "2026-08-12": [{"ticker": "ITA", "rs_ratio_z": -0.5, "rs_momentum_z": 0.4}]}
        wks, points = weekly_points(rows)
        assert wks == ["2026-08-09"], "the week is named by the Sunday that ends it"
        assert points["ITA"] == [(99.5, 100.4)]

    def test_a_midweek_session_stands_for_the_week_before_its_own(self):
        """Wednesday 5 Aug's snapshot was computed from the week ending Sunday 2 Aug, not from its own week."""
        rows = {"2026-08-05": [{"ticker": "ITA", "rs_ratio_z": -0.9, "rs_momentum_z": 0.1}],
                "2026-08-07": [{"ticker": "ITA", "rs_ratio_z": -0.5, "rs_momentum_z": 0.4}]}
        wks, points = weekly_points(rows)
        assert wks == ["2026-08-02", "2026-08-09"]
        assert points["ITA"] == [(99.1, 100.1), (99.5, 100.4)]

    def test_a_week_without_a_row_is_a_gap(self):
        rows = history({"ITA": [(-0.5, 0.4), None, (-0.3, 0.5)]})
        wks, _ = weekly_points(rows)
        assert len(wks) == 2, "a week nothing is stored of is not a week"
        rows["2026-08-14"] = [{"ticker": "XLE", "rs_ratio_z": -0.1, "rs_momentum_z": -0.1}]
        wks, points = weekly_points(rows)
        assert points["ITA"] == [(99.5, 100.4), None, (99.7, 100.5)]


class TestBrier:
    # A: flagged in week 2 and the ratio crosses in week 3 (a hit). B: flagged in week 2 and never crosses (a miss).
    HIT = [(-1.0, 0.5), (-0.8, 0.5), (-0.5, 0.6), (0.5, 0.6), (0.6, 0.5), (0.7, 0.4)]
    MISS = [(-1.0, 0.4), (-0.9, 0.3), (-0.8, 0.2), (-0.9, -0.3), (-1.0, -0.4), (-1.1, -0.5)]

    def result(self, **kw):
        return brier(history({"A": self.HIT, "B": self.MISS}), horizon_weeks=2, **kw)

    def test_a_flag_followed_by_leading_is_a_hit_and_one_that_is_not_is_a_miss(self):
        r = self.result()
        assert (r["flags"], r["hits"]) == (2, 1)
        assert r["hit_rate"] == pytest.approx(0.5)

    def test_the_brier_score_is_the_miss_rate_of_reading_the_flag_as_certain(self):
        assert self.result()["brier"] == pytest.approx(0.5)

    def test_the_score_is_compared_with_the_base_rate_of_the_same_pool(self):
        r = self.result()
        assert r["pool"] == 3, "every left-of-100 week whose priors and horizon are known"
        assert r["base_rate"] == pytest.approx(1 / 3, abs=1e-4)
        assert r["brier_base"] == pytest.approx(5 / 18, abs=1e-4)
        assert r["skill"] == pytest.approx(-0.8, abs=1e-3), "worse than the base rate here"

    def test_it_says_what_it_scored(self):
        r = self.result()
        assert r["horizon_weeks"] == 2 and r["predicted"] == "LEADING"
        assert r["band"] == early_turn.engine.QUADRANT_BAND
        assert (r["weeks"], r["first_week"], r["last_week"]) == (6, "2026-08-09", "2026-09-13")

    def test_a_flag_whose_horizon_has_not_run_out_is_pending_never_a_miss(self):
        # C is flagged in the last week: nothing can have followed it yet.
        late = [(-1.0, 0.5), (-0.9, 0.4), (-0.8, 0.3)]
        r = brier(history({"C": late}), horizon_weeks=2)
        assert (r["flags"], r["flags_pending"], r["pool"]) == (0, 1, 0)
        assert r["brier"] is None and r["hit_rate"] is None

    def test_an_empty_history_scores_nothing_and_does_not_raise(self):
        r = brier({})
        assert (r["weeks"], r["pool"], r["flags"]) == (0, 0, 0)
        assert r["brier"] is None and r["base_rate"] is None and r["skill"] is None

    def test_a_longer_horizon_can_turn_a_miss_into_a_hit(self):
        # one flag (week 2), the ratio crosses three weeks later: a miss at 2 weeks, a hit at 3
        slow = [(-1.0, 0.5), (-0.9, 0.5), (-0.8, 0.6), (-0.7, -0.6), (-0.6, -0.5), (0.5, 0.5),
                (0.6, 0.5), (0.7, 0.5)]
        two = brier(history({"D": slow}), horizon_weeks=2)
        three = brier(history({"D": slow}), horizon_weeks=3)
        assert (two["flags"], two["hits"]) == (1, 0)
        assert (three["flags"], three["hits"]) == (1, 1)


class TestCaption:
    def test_no_flag_scored_says_nothing_on_the_card(self):
        assert caption({}) == ""
        assert caption(brier({})) == ""

    def test_the_line_names_the_hits_the_horizon_and_the_score(self):
        line = caption(brier(history({"A": TestBrier.HIT, "B": TestBrier.MISS}), horizon_weeks=2))
        assert "1/2 reached Leading within 2w" in line
        assert "hit 50% vs base 33%" in line

    def test_each_number_stands_against_the_one_it_is_fair_to_read_it_against(self):
        """A Brier beside the base *rate* read as if the flag beat it; a Brier belongs beside a Brier."""
        line = caption(brier(history({"A": TestBrier.HIT, "B": TestBrier.MISS}), horizon_weeks=2))
        assert "Brier 0.50 vs 0.28" in line
        assert "base 0.33" not in line, "the base rate is not the thing a Brier is compared with"


class TestBandScan:
    @staticmethod
    def _wobble(n=12):
        return [(0.1 if i % 2 == 0 else -0.1, 1.0) for i in range(n)]

    def test_a_band_removes_the_one_week_round_trips_of_an_axis_hugging_dot(self):
        rows = history({"ITA": self._wobble()})
        table = {r["band"]: r for r in band_scan(rows, bands=(0.0, 0.25))}
        assert table[0.0]["changes"] == 11 and table[0.0]["round_trips"] > 0
        assert table[0.25]["changes"] == 0 and table[0.25]["round_trips"] == 0

    def test_a_wider_band_never_adds_quadrant_changes(self):
        rows = history({"ITA": self._wobble(), "XLE": [(0.3 * (1 if i < 6 else -1), 0.5) for i in range(12)]})
        table = band_scan(rows, bands=(0.0, 0.1, 0.25, 0.5, 1.0))
        changes = [r["changes"] for r in table]
        assert changes == sorted(changes, reverse=True)

    def test_it_reports_the_mean_stay_and_what_it_read(self):
        rows = history({"ITA": self._wobble()})
        row = band_scan(rows, bands=(0.25,))[0]
        assert row["mean_weeks_in_quadrant"] == pytest.approx(12.0)
        assert (row["weeks"], row["tickers"]) == (12, 1)


class TestTheWeeklyPairCanComeFromAnywhere:
    """The stored snapshots were three weeks long when this was measured on homesrv (20 Nov 2026), so the band and
    the score take weekly points from the prices store too."""

    def test_a_weekly_pair_is_scored_instead_of_the_stored_rows(self):
        rows = history({"A": TestBrier.HIT, "B": TestBrier.MISS})
        from_rows = brier(rows, horizon_weeks=2)
        from_pair = brier(horizon_weeks=2, weekly=weekly_points(rows))
        assert from_pair == from_rows

    def test_the_band_table_takes_a_weekly_pair_too(self):
        rows = history({"ITA": [(0.1 if i % 2 == 0 else -0.1, 1.0) for i in range(12)]})
        assert band_scan(bands=(0.25,), weekly=weekly_points(rows)) == band_scan(rows, bands=(0.25,))


class TestPointsFromPrices:
    """Rebuilt from the stored daily bars: no snapshot history needed and nothing written."""

    def test_every_series_lines_up_with_the_benchmark_weeks(self, rawstore_tmp_db, monkeypatch):
        pin_clock(monkeypatch, ny(2026, 8, 14, 18))
        base = date(2026, 8, 14)
        seed("SPY", base, closes=lambda i: 100.0 + i)
        seed("XLK", base, closes=lambda i: 100.0 + i * 1.01)
        weeks, points = points_from_prices(base, weeks=40)
        assert weeks[-1] == "2026-08-16", "the week of Friday 14 Aug is named by the Sunday that ends it"
        assert len(weeks) == 40
        assert len(points["XLK"]) == 40 and points["XLK"][-1] is not None

    def test_a_ticker_the_store_has_too_little_history_of_is_left_out(self, rawstore_tmp_db, monkeypatch):
        pin_clock(monkeypatch, ny(2026, 8, 14, 18))
        base = date(2026, 8, 14)
        seed("SPY", base, closes=lambda i: 100.0 + i)
        seed("XLE", base, start=date(2026, 1, 5), closes=lambda i: 100.0 + i)
        weeks, points = points_from_prices(base, weeks=40)
        assert weeks, "the benchmark has its weeks"
        assert "XLE" not in points

    def test_an_empty_prices_store_measures_nothing(self, rawstore_tmp_db, monkeypatch):
        pin_clock(monkeypatch, ny(2026, 8, 14, 18))
        assert points_from_prices(date(2026, 8, 14)) == ([], {})

    def test_the_week_names_follow_the_closes_they_label(self, rawstore_tmp_db, monkeypatch):
        from revenuechaser.module_sector_rotation.engine import weekly_closes, weekly_week_keys
        pin_clock(monkeypatch, ny(2026, 8, 14, 18))
        base = date(2026, 8, 14)
        seed("SPY", base, closes=lambda i: 100.0 + i)
        from revenuechaser.module_sector_rotation.engine import bar_points
        pts = bar_points(["SPY"], date(2025, 3, 3), base)["SPY"]
        assert len(weekly_week_keys(pts, base)) == len(weekly_closes(pts, base))
        assert weekly_week_keys(pts, base)[-1] == tuple(date(2026, 8, 14).isocalendar())[:2]


class TestTheCardReadsThePricesStore:
    """The live board file held 3 snapshots, so a card scored off them showed nothing (homesrv, 20 Nov 2026)."""

    def test_the_card_scores_the_weeks_rebuilt_from_the_prices_store(self, monkeypatch):
        from revenuechaser.module_sector_rotation import report
        from revenuechaser.module_sector_rotation import store as rotation_store
        pair = weekly_points(history({"A": TestBrier.HIT, "B": TestBrier.MISS}))
        asked = {}

        def _points(as_of, weeks=0, **kw):
            asked["as_of"], asked["weeks"] = as_of, weeks
            return pair

        monkeypatch.setattr(early_turn, "points_from_prices", _points)
        monkeypatch.setattr(rotation_store, "load_range",
                            lambda *a, **k: pytest.fail("the card must not score off the stored snapshots"))
        out = report._early_turn_score(date(2026, 11, 19))
        assert asked == {"as_of": date(2026, 11, 19), "weeks": report.SCORE_WEEKS}
        assert out == brier(weekly=pair)

    def test_a_prices_store_that_cannot_answer_leaves_the_card_without_a_line(self, monkeypatch):
        from revenuechaser.module_sector_rotation import report

        def _raise(*a, **k):
            raise RuntimeError("no prices store")

        monkeypatch.setattr(early_turn, "points_from_prices", _raise)
        assert report._early_turn_score(date(2026, 11, 19)) == {}
        assert caption(report._early_turn_score(date(2026, 11, 19))) == ""
