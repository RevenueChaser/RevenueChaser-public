"""#256, docs/module_earnings_radar/redesign.md R5: the lean reads a window of sessions and a slice of strikes. Offline.

Before this, R5's lean read whatever ``flow-recent`` returned: every strike, every expiry, and as many sessions
back as the newest prints happened to span. redesign.md R5 locks two local filters ("Window: last 1-3 sessions",
"Strike filter = R4 EM-band + earnings-expiry proximity ... slice locally"). The slice is pure and takes the prints
the pipeline already fetched, so it costs no request; R8's retail share and the card's tape buckets keep reading the
whole answer.
"""
from datetime import date

import pytest

from revenuechaser.core.config import R5_LEAN_BAND_SLACK, R5_LEAN_EXPIRY_DAYS, R5_LEAN_SESSIONS
from revenuechaser.module_earnings_radar import lean

ED = date(2026, 8, 14)


def _print(day, hour=16, strike=100.0, expiry="2026-08-21", **kw):
    """One print, timestamped in UTC the way UW serves it (16:00 UTC = 12:00 New York)."""
    return {"executed_at": f"{day}T{hour:02d}:00:00Z", "strike": strike, "expiry": expiry,
            "premium": 50_000.0, "size": 50, "option_type": "call", **kw}


class TestWindow:
    def test_only_the_newest_sessions_the_tape_served_are_kept(self):
        rows = [_print("2026-08-13"), _print("2026-08-12"), _print("2026-08-11"), _print("2026-08-10")]
        kept = lean.select(rows, earnings_date=ED, sessions=3)
        assert [p["executed_at"][:10] for p in kept] == ["2026-08-13", "2026-08-12", "2026-08-11"]

    def test_a_quiet_name_spends_no_window_on_days_without_prints(self):
        """Sessions are days the tape served, not calendar days: a gap costs nothing."""
        rows = [_print("2026-08-13"), _print("2026-07-20"), _print("2026-06-15")]
        assert len(lean.select(rows, earnings_date=ED, sessions=3)) == 3

    def test_the_newest_print_sets_the_window_not_the_clock(self):
        """A Fetch of a past day must slice the same way as tonight's."""
        rows = [_print("2026-08-12"), _print("2026-08-11"), _print("2026-08-05")]
        kept = lean.select(rows, earnings_date=ED, sessions=2)
        assert [p["executed_at"][:10] for p in kept] == ["2026-08-12", "2026-08-11"]

    def test_the_new_york_date_decides(self):
        """01:00 UTC on 13 Aug is still the 12 Aug session in New York."""
        rows = [_print("2026-08-13", hour=1), _print("2026-08-12", hour=16)]
        assert len(lean.select(rows, earnings_date=ED, sessions=1)) == 2

    def test_a_print_without_a_timestamp_is_kept(self):
        rows = [_print("2026-08-13"), {"strike": 100.0, "expiry": "2026-08-21", "premium": 1.0}]
        assert len(lean.select(rows, earnings_date=ED, sessions=1)) == 2

    def test_the_default_window_is_three_sessions(self):
        rows = [_print(f"2026-08-{d:02d}") for d in (13, 12, 11, 10)]
        assert len(lean.select(rows, earnings_date=ED)) == R5_LEAN_SESSIONS == 3


class TestStrikeBand:
    def test_a_strike_outside_the_expected_move_band_is_dropped(self):
        # spot 100, move 5% x slack 1.5 -> 92.5 .. 107.5
        rows = [_print("2026-08-13", strike=105.0), _print("2026-08-13", strike=150.0)]
        kept = lean.select(rows, spot=100.0, expected_move_pct=0.05, earnings_date=ED)
        assert [p["strike"] for p in kept] == [105.0]

    def test_the_band_is_the_expected_move_widened_by_the_slack(self):
        edge = 100.0 * (1 + 0.05 * R5_LEAN_BAND_SLACK)
        rows = [_print("2026-08-13", strike=edge), _print("2026-08-13", strike=edge + 0.01)]
        kept = lean.select(rows, spot=100.0, expected_move_pct=0.05, earnings_date=ED)
        assert [p["strike"] for p in kept] == [pytest.approx(edge)]

    def test_no_expected_move_keeps_every_strike(self):
        """The band is unknown, which is not the same as empty."""
        rows = [_print("2026-08-13", strike=1.0), _print("2026-08-13", strike=900.0)]
        assert len(lean.select(rows, spot=100.0, expected_move_pct=None, earnings_date=ED)) == 2

    def test_no_spot_keeps_every_strike(self):
        rows = [_print("2026-08-13", strike=1.0), _print("2026-08-13", strike=900.0)]
        assert len(lean.select(rows, spot=None, expected_move_pct=0.05, earnings_date=ED)) == 2

    def test_a_print_without_a_strike_is_kept(self):
        rows = [_print("2026-08-13", strike=None)]
        assert len(lean.select(rows, spot=100.0, expected_move_pct=0.05, earnings_date=ED)) == 1


class TestExpiryProximity:
    def test_an_expiry_before_the_report_cannot_express_the_event(self):
        rows = [_print("2026-08-13", expiry="2026-08-13"), _print("2026-08-13", expiry="2026-08-21")]
        kept = lean.select(rows, earnings_date=ED)
        assert [p["expiry"] for p in kept] == ["2026-08-21"]

    def test_a_leap_is_a_position_not_an_earnings_bet(self):
        rows = [_print("2026-08-13", expiry="2027-06-18")]
        assert lean.select(rows, earnings_date=ED) == []

    def test_the_last_expiry_kept_is_the_report_day_plus_the_window(self):
        last = date.fromordinal(ED.toordinal() + R5_LEAN_EXPIRY_DAYS)
        rows = [_print("2026-08-13", expiry=last.isoformat()),
                _print("2026-08-13", expiry=date.fromordinal(last.toordinal() + 1).isoformat())]
        kept = lean.select(rows, earnings_date=ED)
        assert [p["expiry"] for p in kept] == [last.isoformat()]

    def test_the_report_day_itself_is_in(self):
        rows = [_print("2026-08-13", expiry=ED.isoformat())]
        assert len(lean.select(rows, earnings_date=ED)) == 1

    def test_no_earnings_date_keeps_every_expiry(self):
        rows = [_print("2026-08-13", expiry="2026-08-13"), _print("2026-08-13", expiry="2027-06-18")]
        assert len(lean.select(rows, earnings_date=None)) == 2

    def test_a_print_without_an_expiry_is_kept(self):
        rows = [_print("2026-08-13", expiry=None)]
        assert len(lean.select(rows, earnings_date=ED)) == 1


class TestEmptyAndJunk:
    def test_no_prints_is_no_prints(self):
        assert lean.select(None, earnings_date=ED) == [] and lean.select([], earnings_date=ED) == []

    def test_a_non_dict_row_is_dropped_not_raised(self):
        assert lean.select(["nope", None, _print("2026-08-13")], earnings_date=ED) != []

    def test_an_unparseable_timestamp_or_expiry_is_kept(self):
        rows = [_print("2026-08-13", expiry="not-a-day"), {"executed_at": "nope", "strike": 100.0}]
        assert len(lean.select(rows, spot=100.0, expected_move_pct=0.05, earnings_date=ED)) == 2
