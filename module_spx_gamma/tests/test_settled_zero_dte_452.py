"""#452: a Fetch run after the close must not let the settled same-day 0DTE drive any panel.

PR 419 stopped the settled rows at the charm pin, the Iron Butterfly, the dealer book and the 0DTE skew. The Fable
delta review of that PR (S3) named five readers still on them: the front-expiry share, the session hedge flow, the
0DTE concentration levels, the prediction engine's near-DTE geometry, and the all-expiry grid the Fetch writes
(``snapshot.py`` 4b), which carries the as-of expiry too. One flag in ``normalize_snapshot`` now answers all of
them; the raw day keeps the full record.

The real UW check of 5 Nov 2026 is the case: a Fetch of 4 Nov run on the morning of 5 Nov, whose 4 Nov series had
settled, gave Iron Butterfly legs IVs of 182-558 %.
"""
from __future__ import annotations

from RevenueChaser.module_spx_gamma import render
from RevenueChaser.module_spx_gamma.engines.prediction_engine import _near_dte_rows
from RevenueChaser.module_spx_gamma.expiry_table import front_expiry_share, session_hedge_flow
from RevenueChaser.module_spx_gamma.normalize import normalize_snapshot

from .conftest import make_raw

DAY = "2026-08-14"                        # a Friday, so the target Friday is 2026-08-21
AFTER_THE_CLOSE = "2026-08-15T12:00:00Z"  # the next morning: the 14 Aug expiry had settled

ROWS = [{"expiry": DAY, "net_gex": 100.0, "net_charm": 5.0, "dte": 0.0},
        {"expiry": "2026-08-21", "net_gex": 25.0, "net_charm": -1.0, "dte": 7.0}]


def _live() -> dict:
    return normalize_snapshot(make_raw(), DAY)


def _settled() -> dict:
    raw = make_raw()
    raw["_meta"] = {"api_snapshot_time": AFTER_THE_CLOSE}
    return normalize_snapshot(raw, DAY)


# ── the two expiry-row panels
def test_front_expiry_share_counts_a_settled_expiry_in_neither_part():
    assert front_expiry_share(ROWS, DAY)["expiry"] == DAY
    share = front_expiry_share(ROWS, DAY, settled=True)
    assert share["expiry"] == "2026-08-21"
    assert share["total_net_gex"] == 25.0 and share["share_pct"] == 100.0


def test_the_session_flow_starts_at_the_next_session_once_the_0dte_settled():
    assert [r["expiry"] for r in session_hedge_flow(ROWS, DAY, 7784.0)] == [DAY, "2026-08-21"]
    assert [r["expiry"] for r in session_hedge_flow(ROWS, DAY, 7784.0, settled=True)] == ["2026-08-21"]


def test_the_board_shows_both_panels_on_the_live_expiries_only():
    settled = _settled()
    assert settled["front_expiry_share"]["expiry"] == "2026-08-21"
    assert [r["expiry"] for r in settled["session_flow"]] == ["2026-08-21"]
    live = _live()
    assert live["front_expiry_share"]["expiry"] == DAY            # an intraday Fetch is unchanged
    assert [r["expiry"] for r in live["session_flow"]] == [DAY, "2026-08-21"]


# ── the 0DTE levels
def test_a_settled_0dte_leaves_no_0dte_concentration_level():
    live = _live()["levels"]
    assert live["zero_dte_concentration"] is not None and live["zero_dte_put_concentration"] is not None
    settled = _settled()["levels"]
    for key in ("zero_dte_concentration", "zero_dte_put_concentration", "zero_dte_cumulative_crossing"):
        assert settled[key] is None, key


# ── the prediction geometry
def test_the_pin_and_trigger_geometry_drops_the_settled_rows():
    assert any(str(r.get("expiry")) == DAY for r in _near_dte_rows(_live()))
    assert not any(str(r.get("expiry")) == DAY for r in _near_dte_rows(_settled()))


def test_a_settled_day_predicts_what_a_day_without_those_rows_predicts():
    """The settled 0DTE sets neither ``active_pin`` nor ``upside_trigger``: the prediction is the one the same day
    gives when its 0DTE grid file is absent altogether (``make_raw``'s ``strike_expiry_all`` holds no 14 Aug)."""
    without = make_raw()
    without["strike_expiry"] = {}
    assert _settled()["prediction"] == normalize_snapshot(without, DAY)["prediction"]


# ── the two readers found beside the five
def test_matrix_gex_leaves_out_the_settled_session():
    live, settled = _live()["matrix_gex"], _settled()["matrix_gex"]
    assert settled == 10000.0                      # the 21 Aug row alone
    assert live > settled                          # live: plus the 14 Aug row's 54,537.26


def test_the_week_map_starts_at_the_next_session():
    assert DAY in _live()["week_gamma"]["expiries"]
    assert DAY not in _settled()["week_gamma"]["expiries"]


# ── the board says why the panels read n/a
def test_the_banner_says_the_0dte_had_settled():
    assert "had settled when the Fetch ran" not in (render.data_quality_notice(_live()) or "")
    settled = _settled()
    assert settled["zero_dte_settled"] is True
    notice = render.data_quality_notice(settled) or ""
    assert f"The {DAY} 0DTE had settled when the Fetch ran" in notice
    assert "0DTE had settled when the Fetch ran" in render.render_html(settled)
