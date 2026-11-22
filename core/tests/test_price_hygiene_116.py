"""#116: the shared price-hygiene gates (``core/price_hygiene.py``), one test per gate and the first-reason order."""
from __future__ import annotations

import pandas as pd

from revenuechaser.core import price_hygiene as ph


def _frame(closes, highs=None, lows=None, days=None):
    days = days if days is not None else pd.bdate_range("2026-01-05", periods=len(closes))
    closes = [float(c) for c in closes]
    return pd.DataFrame({"Open": closes, "High": highs or [c * 1.01 for c in closes],
                         "Low": lows or [c * 0.99 for c in closes], "Close": closes,
                         "Volume": [1e6] * len(closes)}, index=pd.DatetimeIndex(days))


def _walk(n=60):
    return [100 + (i % 3) for i in range(n)]          # moves, never 5 equal closes in a row


def test_a_clean_series_has_no_reason():
    assert ph.evaluate(_frame(_walk())) is None


def test_locked_needs_five_identical_closes():
    assert ph.locked(_frame(_walk(10) + [50] * 5)) == "locked"
    assert ph.locked(_frame(_walk(10) + [50] * 4)) is None


def test_a_jump_the_adjusted_series_repeats_is_unexplained_and_a_split_is_not():
    jump = _walk(20) + [200] + _walk(5)                  # a one-day spike that comes straight back
    assert ph.unexplained_jump(_frame(jump), _frame(jump)) == "unexplained_jump"
    split = _frame(_walk(20) + [50.5, 51, 50])           # nominal halves; adjusted is smooth
    assert ph.unexplained_jump(split, _frame(_walk(23))) is None


def test_two_moves_over_25_percent_repeat():
    one = _walk(20) + [130, 131, 130] + _walk(5)
    assert ph.repeat_jump(_frame(one)) is None           # 30 % up, then 23 % back: one move over 25 %
    two = _walk(20) + [130, 131, 130] + [170, 171, 170]
    assert ph.repeat_jump(_frame(two)) == "repeat_jump"


def test_a_gap_of_more_than_ten_sessions_breaks_the_series():
    days = list(pd.bdate_range("2026-01-05", periods=10)) + list(pd.bdate_range("2026-02-03", periods=10))
    assert ph.broken_series(_frame(_walk(20), days=days)) == "broken_series"
    days = list(pd.bdate_range("2026-01-05", periods=10)) + list(pd.bdate_range("2026-01-30", periods=10))
    assert ph.broken_series(_frame(_walk(20), days=days)) is None          # 9 sessions missing; the case above misses 11


def test_a_wick_half_again_beyond_the_body_is_a_bad_print():
    closes = _walk(10)
    highs = [c * 1.01 for c in closes]
    highs[4] = closes[4] * 1.6
    assert ph.bad_wick(_frame(closes, highs=highs)) == "bad_wick"


def test_the_first_reason_in_order_wins():
    closes = _walk(10) + [50] * 6 + _walk(5)
    highs = [c * 1.01 for c in closes]
    highs[2] = closes[2] * 2
    assert ph.evaluate(_frame(closes, highs=highs)) == "locked"            # before unexplained_jump and bad_wick
    assert ph.evaluate(pd.DataFrame()) is None


def test_a_jump_that_holds_is_a_real_move_and_only_a_spike_that_reverses_is_flagged_891():
    held = _walk(20) + [150, 151, 150, 152, 151]         # +50 % and it stays: news, not a bad print
    assert ph.unexplained_jump(_frame(held), _frame(held)) is None
    late = _walk(20) + [150, 151, 150] + _walk(3)        # back only on the third session: still a move
    assert ph.unexplained_jump(_frame(late), _frame(late)) is None
    back = _walk(20) + [150, 145, 102] + _walk(3)        # back within two sessions: a bad print
    assert ph.unexplained_jump(_frame(back), _frame(back)) == "unexplained_jump"


def test_locked_and_repeat_jump_read_only_the_last_60_sessions_891():
    old_lock = _walk(5) + [50] * 6 + [50 + (i % 3) for i in range(ph.RECENT)]
    assert ph.locked(_frame(old_lock)) is None
    assert ph.locked(_frame(_walk(80) + [50] * 5)) == "locked"
    old_jumps = _walk(20) + [130, 131, 130] + [170, 171, 170] + [170 + (i % 3) for i in range(ph.RECENT)]
    assert ph.repeat_jump(_frame(old_jumps)) is None


def test_a_spike_and_a_wick_older_than_60_sessions_are_not_flagged_891():
    """The 16 Nov measurement: over the whole bar window ``unexplained_jump`` flagged 8.5 % of the universe and
    ``bad_wick`` 12.2 %, mostly for prints a year or more old. Both now read the last ``RECENT`` sessions only."""
    tail = [100 + (i % 3) for i in range(ph.RECENT)]
    old_spike = _walk(20) + [200] + _walk(5) + tail
    assert ph.unexplained_jump(_frame(old_spike), _frame(old_spike)) is None
    new_spike = _walk(80) + [200] + _walk(5)
    assert ph.unexplained_jump(_frame(new_spike), _frame(new_spike)) == "unexplained_jump"
    closes = _walk(10) + tail
    highs = [c * 1.01 for c in closes]
    highs[4] = closes[4] * 1.6                          # a wick 70 sessions back
    assert ph.bad_wick(_frame(closes, highs=highs)) is None
    highs[-3] = closes[-3] * 1.6                        # and one 3 sessions back
    assert ph.bad_wick(_frame(closes, highs=highs)) == "bad_wick"
