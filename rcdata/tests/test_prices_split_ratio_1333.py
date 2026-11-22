"""``split_ratio_unexplained`` (#1333, drafts P-D and P-E): an applied split whose ratio the served raw closes
across its ex-date do not show.

The rule reads two served tables only -- ``corporate_action`` and ``price_bar_daily`` -- so these tests build them
on a bare connection instead of driving the whole prices build. The named rows are the audit's own cases of
21 Nov 2026: SCCO's Alpaca stock dividend of 3 Nov (ratio 2.0106, the close moved 179.36 -> 173.49) and HON's
29 Jun (ratio 0.5, the close did not move)."""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from revenuechaser.rcdata.build.prices import serving as prices_serving


def _world(actions: list[tuple], bars: list[tuple]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute("CREATE TABLE corporate_action (security_id TEXT, ex_date DATE, action TEXT, ratio DOUBLE, "
                "applied BOOLEAN)")
    con.execute("CREATE TABLE price_bar_daily (security_id TEXT, session_date DATE, close DOUBLE)")
    con.executemany("INSERT INTO corporate_action VALUES (?, ?, ?, ?, ?)", actions)
    con.executemany("INSERT INTO price_bar_daily VALUES (?, ?, ?)", bars)
    return con


def _bars(sid: str, days_closes: list[tuple[str, float]]) -> list[tuple]:
    return [(sid, date.fromisoformat(d), c) for d, c in days_closes]


def test_an_alpaca_stock_dividend_the_close_does_not_show_is_named():
    """SCCO, 3 Nov 2026: ``ACTION_RATIO``'s ``1 + rate`` over a raw rate of 1.0106 gives 2.0106, which halves every
    adjusted close before it, while the close moved 3 %. The ratio expects x0.4974 and the bars show x0.967."""
    con = _world([("SCCO", date(2026, 11, 3), "stock_dividend", 2.0106, True)],
                 _bars("SCCO", [("2026-11-02", 179.36), ("2026-11-03", 173.49)]))
    found = prices_serving.split_ratio_unexplained(con)
    assert [(k, key) for k, key, _ in found] == [("split_ratio_unexplained", "SCCO:2026-11-03")]
    assert "ratio 2.0106" in found[0][2] and "x0.9673" in found[0][2]
    # Named only: the rule writes nothing and drops nothing, so the action is still applied after it ran.
    assert con.execute("SELECT applied FROM corporate_action").fetchone() == (True,)


def test_a_split_the_close_did_not_move_across_is_named():
    """HON, 29 Jun 2026, ratio 0.5: a reverse split would double the raw close and it stood still."""
    con = _world([("HON", date(2026, 6, 29), "split", 0.5, True)],
                 _bars("HON", [("2026-06-26", 100.0), ("2026-06-30", 100.0)]))
    assert [key for _, key, _ in prices_serving.split_ratio_unexplained(con)] == ["HON:2026-06-29"]


def test_a_split_the_raw_close_steps_by_is_not_named():
    """The rule's other side: a 1-for-2 reverse split (ratio 0.5) whose raw close doubles is right, and a 2-for-1
    (ratio 2.0) whose raw close halves is right. Neither is named, at any size of the day's own return within the
    factor."""
    con = _world([("REV", date(2026, 6, 29), "split", 0.5, True),
                  ("FWD", date(2026, 6, 29), "split", 2.0, True),
                  ("NOISY", date(2026, 6, 29), "split", 2.0, True)],
                 _bars("REV", [("2026-06-26", 100.0), ("2026-06-30", 200.0)])
                 + _bars("FWD", [("2026-06-26", 100.0), ("2026-06-30", 50.0)])
                 # a 2-for-1 and a 20 % fall of its own on the day: x0.4 against the x0.5 the ratio expects
                 + _bars("NOISY", [("2026-06-26", 100.0), ("2026-06-30", 40.0)]))
    assert prices_serving.split_ratio_unexplained(con) == []


def test_a_second_split_between_the_two_bars_leaves_both_alone():
    """Two applied splits in one span: the move is the product of the ratios, so the rule has nothing to say about
    either one and names neither."""
    con = _world([("TWO", date(2026, 6, 29), "split", 2.0, True), ("TWO", date(2026, 7, 1), "split", 2.0, True)],
                 _bars("TWO", [("2026-06-26", 100.0), ("2026-07-02", 25.0)]))
    assert prices_serving.split_ratio_unexplained(con) == []


def test_a_split_with_no_bar_on_both_sides_within_the_window_is_not_named():
    """No served bar within GAP_DAYS on one side (before the series starts, or a halt): the rule cannot read the
    move, so it says nothing -- the same bound ``split_only_crsp`` uses."""
    con = _world([("HALT", date(2026, 6, 29), "split", 0.5, True)],
                 _bars("HALT", [("2026-06-10", 100.0), ("2026-07-20", 100.0)]))
    assert prices_serving.split_ratio_unexplained(con) == []


def test_an_action_the_factors_did_not_apply_is_not_named():
    """The rule is about a ratio the served bars are adjusted by: an unapplied action adjusts nothing."""
    con = _world([("SKIP", date(2026, 6, 29), "split", 0.5, False),
                  ("CASH", date(2026, 6, 29), "cash_dividend", None, True)],
                 _bars("SKIP", [("2026-06-26", 100.0), ("2026-06-30", 100.0)])
                 + _bars("CASH", [("2026-06-26", 100.0), ("2026-06-30", 100.0)]))
    assert prices_serving.split_ratio_unexplained(con) == []


def test_the_kind_is_registered_with_its_tolerance_named():
    """``ops.sync_issues`` writes a kind only when ``ISSUE_KINDS`` describes it, and the Settings board shows that
    text, so the tolerance the rule uses is named there."""
    assert "split_ratio_unexplained" in prices_serving.ISSUE_KINDS
    assert "SPLIT_MOVE_FACTOR" in prices_serving.ISSUE_KINDS["split_ratio_unexplained"]
    assert prices_serving.SPLIT_MOVE_FACTOR == pytest.approx(1.5)
