"""Swing board review of 17 Nov 2026 (claude-coordinator reviews/2026-11-17_1432_revenuechaser_swing-board-review.md).

F2: a Fetch with no SPY baseline says so on the board instead of silently scoring RS as unknown.
F5: ``OPERATING_ONLY`` changes who is scanned (so every percentile): a saved value versions the ledger rows, and the
default board keeps its hash.
F15: a stale name scored above the stale-drop cap carries ``ohlc_stale`` onto its card (an "Old price" chip).
F17: the scan never reads a bar dated after the latest complete session.
F6: a #116 price-hygiene flag (flag only) is carried onto its card (a "Check price" chip).
F11: the page uses the shared light/dark theme and 44 px controls; the rules table stacks on a phone.
B2, C2, D1 (avo 17 Nov): Qullamaggie needs the prior move and a tightening; Minervini 30 % above the low;
Weinstein's volume spike counts only on an up day.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pandas as pd
import pytest

from revenuechaser.core import calendar as cal
from revenuechaser.core import screen_common as sc
from revenuechaser.core.tests import screen_parity as scn
from revenuechaser.core.tests.d01_seed import write_d01
from revenuechaser.module_swing_potential import freeze, indicators, pipeline, screeners
from revenuechaser.module_swing_potential import settings as S
from revenuechaser.module_swing_potential.report import render_swing_dashboard


def _run_payload(**overrides) -> dict:
    p = S.effective().payload()
    p["overrides"] = dict(overrides)
    p["overridden"] = list(overrides)
    p["custom"] = bool(overrides)
    return {"settings": p}


def test_operating_only_overridden_moves_the_model_version(rawstore_tmp_db):
    default = freeze.model_version(_run_payload())
    assert default == freeze.model_version()                         # the default hash does not move
    assert "OPERATING_ONLY" not in freeze.effective_config(_run_payload())
    assert freeze.model_version(_run_payload(OPERATING_ONLY=0)) != default


@pytest.fixture
def scenario(rawstore_tmp_db, monkeypatch):
    scn.seed()
    scn.patch(monkeypatch)


def test_a_fetch_without_an_spy_baseline_says_so(scenario, monkeypatch):
    def no_spy(now=None):
        empty = pd.DataFrame()
        empty.attrs["fetch_failed"] = True
        return empty
    monkeypatch.setattr(sc, "load_spy", no_spy)
    payload = pipeline.run_scan()
    assert payload["summary"]["spy_missing"] is True
    assert payload["passing"]["weinstein"] == 0                     # RS vs SPY unknown: 5 of 5 cannot pass
    assert "SPY has no bar of the latest session" in render_swing_dashboard(payload)


def test_a_fetch_with_an_spy_baseline_says_nothing(scenario):
    payload = pipeline.run_scan()
    assert payload["summary"]["spy_missing"] is False
    assert "SPY has no bar of the latest session" not in render_swing_dashboard(payload)


# ── F15: above the stale-drop cap, a stale name is scored; its card says so ─────────────────────
def test_a_stale_scored_name_is_marked_on_its_card(scenario, monkeypatch):
    real = sc.load_bars

    def stale(ticker, now=None):
        nominal, adjusted = real(ticker, now)
        if ticker == "UP1":
            nominal = nominal.copy()
            nominal.attrs["stale"] = True
        return nominal, adjusted
    monkeypatch.setattr(sc, "load_bars", stale)
    payload = pipeline.run_scan()
    marked = {c["ticker"]: c.get("ohlc_stale") for c in payload["candidates"]}
    assert marked.get("UP1") is True
    assert all(v is None for t, v in marked.items() if t != "UP1")


# ── F17: a bar dated after the latest complete session is never read ─────────────────────────────
def _write(ticker: str, days: list) -> None:
    write_d01([{"ticker": ticker, "session_date": d, "open": 10.0, "high": 10.1, "low": 9.9, "close": 10.0,
                "adj_close": None, "volume": 1.0e6, "split_ratio": None, "adj_source": None, "source": "uw",
                "fetched_at": 0.0, "run_id": "seed", "run_at": 0.0} for d in days], [])


def test_bar_reads_stop_at_the_latest_complete_session(rawstore_tmp_db, monkeypatch):
    session, later = date(2026, 10, 14), date(2026, 10, 15)
    monkeypatch.setattr(cal, "_now", lambda: datetime(2026, 10, 14, 21, 45, tzinfo=timezone.utc))
    days = [d.date() for d in pd.bdate_range(end=session, periods=300)] + [later]
    _write("AAA", days)
    nominal, adjusted = sc.load_bars_many(["AAA"])["AAA"]
    assert nominal.index[-1].date() == session and adjusted.index[-1].date() == session
    assert nominal.attrs["stale"] is False


# ── avo's decisions of 17 Nov 2026 (B2, C2, D1) ─────────────────────────────────────────────────
def _q(**over) -> dict:
    from revenuechaser.module_swing_potential.tests.test_gates import _PASS
    return screeners.evaluate_qullamaggie({**_PASS, **over})


def test_b2_qullamaggie_needs_the_prior_move():
    assert _q()["passed"] is True
    assert _q(move_max_1_3m=0.10)["passed"] is False            # 6 of 7 known passes, but the move is required


def test_b2_qullamaggie_needs_a_tightening():
    g = _q(range_recent=0.04)                                    # the last 10 days are wider than the 20 before
    assert g["passed"] is False and g["score"] == "6/7"
    assert _q(range_recent=None)["passed"] is False              # unknown is never a pass


def test_b2_the_tightening_is_measured_from_the_bars():
    from revenuechaser.module_swing_potential.tests.test_swing import _ohlcv
    df = _ohlcv()
    df.loc[df.index[-10:], "High"] = df["Close"].iloc[-10:] * 1.002     # a tight last 10 sessions
    df.loc[df.index[-10:], "Low"] = df["Close"].iloc[-10:] * 0.998
    ind = indicators.compute_indicators(df)
    assert ind["range_recent"] == pytest.approx(0.004) and ind["range_before"] == pytest.approx(0.02)


def test_c2_minervini_wants_30_percent_above_the_low():
    from revenuechaser.module_swing_potential.tests.test_gates import _PASS
    g = screeners.evaluate_minervini({**_PASS, "above_52w_low_pct": 1.27}, rs_rating=85.0)
    rule = next(r for r in g["rules"] if r["id"] == "above_52w_low")
    assert rule["passed"] is False and "30%" in rule["label"]


def test_d1_a_volume_spike_on_a_down_day_does_not_confirm():
    from revenuechaser.module_swing_potential.tests.test_swing import _ohlcv
    df = _ohlcv()
    df["Volume"] = 1_000_000.0
    df.iloc[-1, df.columns.get_loc("Volume")] = 4_000_000.0
    df.iloc[-1, df.columns.get_loc("Close")] = df["Close"].iloc[-2] * 0.97     # the spike day closes down
    assert indicators.compute_indicators(df)["vol_ratio"] < 1.5


# ── F6: a #116 price-hygiene flag reaches the card (the name is still scored) ───────────────────
def test_a_price_flag_is_carried_onto_the_card(scenario, monkeypatch):
    real = pipeline.build_payload

    def flagged(results, top_n=None, run_stats=None, eff=None):
        return real(results, top_n=top_n, run_stats={**(run_stats or {}), "price_flags": {"bad_wick": ["UP1"]}},
                    eff=eff)
    monkeypatch.setattr(pipeline, "build_payload", flagged)
    payload = pipeline.run_scan()
    flags = {c["ticker"]: c.get("price_flag") for c in payload["candidates"]}
    assert flags.get("UP1") == "bad_wick"
    assert all(v is None for t, v in flags.items() if t != "UP1")


# ── F11: the page is on the shared theme (light and dark) with 44 px controls ───────────────────
def test_the_swing_page_has_no_palette_of_its_own_and_ships_the_theme():
    import re
    from pathlib import Path
    from revenuechaser.module_swing_potential import report
    assert not re.findall(r"#[0-9a-fA-F]{6}|rgba\(", report.CSS), "colours should be theme tokens, not literals"
    assert not re.findall(r"height:3\dpx", report.CSS), "controls are at least 44 px tall"
    src = Path(report.__file__).read_text(encoding="utf-8")
    assert "{THEME_CSS}" in src and "{THEME_JS}" in src
