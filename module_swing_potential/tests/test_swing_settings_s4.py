"""Swing thresholds as editable board settings (#384 SW-S4).

The defaults stay ``module_swing_potential/config.py``'s and are read at call time; only a value a user saved
lives in ``board_settings``, and Reset deletes it. ``test_defaults_reproduce_the_pre_change_output`` pins the
board's output at defaults against a golden captured from the code **before** this slice (so the change cannot
move a single pick), and the tests after it are the ones that failed before the slice existed.

``settings`` is imported inside the tests that exercise it: that keeps the golden pin runnable against the tree
the golden came from (the module did not exist yet).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from RevenueChaser.core import board_settings as bs
from RevenueChaser.core import rawstore
from RevenueChaser.core.tests.panel_client import panel_test_client
from RevenueChaser.module_swing_potential import config, freeze, pipeline, ranking, screeners

B = "module_swing_potential"
_GOLDEN = Path(__file__).with_name("golden_swing_defaults_s4.json")


def _settings():
    from RevenueChaser.module_swing_potential import settings
    return settings


# The keys the SPEC registers, in the order the Settings card shows them.
_KEYS = ("MIN_PRICE", "MIN_DOLLAR_VOLUME", "RS_MIN", "VOL_CONFIRM", "BREAKOUT_HIGH_PCT",
         "MOVE_MIN", "ADR_MIN", "W_PROX", "W_CONS", "STOP_ATR", "TARGET_R",
         "OPERATING_ONLY")                                  # PR 2: the type filter


# ── the fixed fixture the golden and the override tests share ───────────────
def _ind(**over):
    ind = {
        "price": 100.0, "sma50": 95.0, "sma150": 90.0, "sma200": 80.0,
        "sma200_prev_1m": 78.0, "sma150_prev_1m": 88.0,
        "above_52w_low_pct": 1.5, "within_52w_high_pct": 0.99,
        "vol_ratio": 2.0, "rs_vs_spy_3m": 0.05, "rs_vs_spy_12m": 0.10,
        "ema10": 96.0, "ema20": 92.0, "ema10_prev": 90.0, "ema20_prev": 88.0,
        "move_max_1_3m": 0.35, "adr_pct": 0.04, "atr14": 2.0,
        "change_pct": 0.01, "ret_3m": 0.10, "mom_12_1": 0.30, "consistency_6m": 0.8,
    }
    ind.update(over)
    return ind


def _rows():
    """Four names: AAA passes everything, BBB sits just above three thresholds, CCC fails direction, DDD fails
    the Weinstein volume rule and the Qullamaggie ADR rule."""
    return [
        {"ticker": "AAA", "name": "Alpha", "ind": _ind(), "market_cap": 1e9, "sector": "Technology",
         "industry": "Software - Application", "themes": ["Software"], "earnings_date": 1790000000.0},
        {"ticker": "BBB", "name": "Beta",
         "ind": _ind(vol_ratio=1.6, adr_pct=0.032, move_max_1_3m=0.26, rs_vs_spy_12m=0.04,
                     mom_12_1=0.20, consistency_6m=0.6),
         "market_cap": 5e9, "sector": "Healthcare", "industry": "Biotechnology", "themes": []},
        {"ticker": "CCC", "name": "Gamma", "ind": _ind(ret_3m=-0.02), "market_cap": 2e9,
         "sector": "Industrials", "industry": "Machinery", "themes": ["Industrials"]},
        {"ticker": "DDD", "name": "Delta", "ind": _ind(vol_ratio=1.2, adr_pct=0.02), "market_cap": 3e9,
         "sector": "Energy", "industry": "Oil & Gas", "themes": []},
    ]




# ── defaults unchanged (golden) ─────────────────────────────────────────────


# ── the SPEC ────────────────────────────────────────────────────────────────
def test_the_spec_registers_exactly_the_editable_thresholds(rawstore_tmp_db):
    assert B in bs.boards()
    rows = {r["key"]: r for r in bs.describe(B)}
    assert set(rows) == set(_KEYS)
    assert bs.defaults(B) == {k: getattr(config, k) for k in _KEYS}   # a default is config's, not a copy
    assert rows["MIN_PRICE"]["lo"] == config.MIN_PRICE_LO
    assert rows["MIN_PRICE"]["hi"] == config.MIN_PRICE_HI
    assert rows["TARGET_R"]["label"]
    for key, r in rows.items():
        if key == "OPERATING_ONLY":                 # PR 2: the type filter is a closed 0/1 choice
            assert r["choices"] == [0, 1] and r["lo"] is None and r["hi"] is None
            continue
        assert r["choices"] is None and r["lo"] is not None and r["hi"] is not None


def test_a_default_is_read_from_config_at_call_time(rawstore_tmp_db, monkeypatch):
    assert bs.get(B, "RS_MIN") == config.RS_MIN
    monkeypatch.setattr(config, "RS_MIN", 82)
    assert bs.get(B, "RS_MIN") == 82                       # not copied at import or on first read
    assert bs.values(B)["overridden"] == []


# ── effective(): the one resolver ───────────────────────────────────────────
def test_effective_at_defaults_is_the_config(rawstore_tmp_db):
    e = _settings().effective()
    assert (e.min_price, e.min_dollar_volume) == (config.MIN_PRICE, config.MIN_DOLLAR_VOLUME)
    assert (e.rs_min, e.vol_confirm, e.breakout_high_pct) == (
        config.RS_MIN, config.VOL_CONFIRM, config.BREAKOUT_HIGH_PCT)
    assert (e.move_min, e.adr_min) == (config.MOVE_MIN, config.ADR_MIN)
    assert (e.w_prox, e.w_cons) == (config.W_PROX, config.W_CONS)
    assert (e.stop_atr, e.target_r) == (config.STOP_ATR, config.TARGET_R)
    assert e.custom is False and e.overridden == ()




def test_a_store_error_falls_back_to_the_defaults(rawstore_tmp_db, monkeypatch):
    def broken(board):
        raise RuntimeError("store locked")
    monkeypatch.setattr(bs, "values", broken)
    e = _settings().effective()
    assert (e.min_price, e.rs_min, e.stop_atr) == (config.MIN_PRICE, config.RS_MIN, config.STOP_ATR)
    assert e.custom is False and e.overridden == ()
    assert freeze.effective_config()["RS_MIN"] == config.RS_MIN      # the freeze reads defaults, never raises


# ── the pipeline reads the effective values ─────────────────────────────────








# ── bounds and cross-rules ──────────────────────────────────────────────────
@pytest.mark.parametrize("change,needle", [
    ({"MIN_PRICE": 0.4}, "MIN_PRICE must be between 0.5 and 100"),
    ({"MIN_PRICE": 101}, "MIN_PRICE must be between 0.5 and 100"),
    ({"MIN_DOLLAR_VOLUME": -1}, "MIN_DOLLAR_VOLUME must be between 0 and 50000000"),
    ({"MIN_DOLLAR_VOLUME": 50_000_001}, "MIN_DOLLAR_VOLUME must be between 0 and 50000000"),
    ({"RS_MIN": 101}, "RS_MIN must be between 0 and 100"),
    ({"VOL_CONFIRM": 0.4}, "VOL_CONFIRM must be between 0.5 and 10"),
    ({"BREAKOUT_HIGH_PCT": 1.01}, "BREAKOUT_HIGH_PCT must be between 0.5 and 1"),
    ({"MOVE_MIN": 3.5}, "MOVE_MIN must be between 0 and 3"),
    ({"ADR_MIN": 0.3}, "ADR_MIN must be between 0 and 0.25"),
    ({"W_PROX": 1.1}, "W_PROX must be between 0 and 1"),
    ({"W_CONS": -0.1}, "W_CONS must be between 0 and 1"),
    ({"STOP_ATR": 0.4}, "STOP_ATR must be between 0.5 and 10"),
    ({"TARGET_R": 25}, "TARGET_R must be between 0.5 and 20"),
    ({"RS_MIN": "abc"}, "RS_MIN must be a number"),
    ({"NOPE": 1}, "unknown setting 'NOPE'"),
])
def test_validate_every_bound_names_its_rule(rawstore_tmp_db, change, needle):
    msgs = bs.validate(B, change)
    assert any(needle in m for m in msgs), msgs


def test_cross_rule_the_weights_leave_momentum_the_largest_tilt(rawstore_tmp_db):
    msgs = bs.validate(B, {"W_PROX": 0.8, "W_CONS": 0.4})
    assert any("W_PROX + W_CONS must not exceed 1" in m for m in msgs), msgs
    assert bs.validate(B, {"W_PROX": 0.5, "W_CONS": 0.5}) == []
    assert bs.validate(B, {"W_PROX": 0.0, "W_CONS": 0.0}) == []
    # TARGET_R < STOP_ATR is allowed: a sub-1R target is a choice, not an error
    assert bs.validate(B, {"STOP_ATR": 4.0, "TARGET_R": 1.0}) == []




# ── only an override is stored; Reset deletes it ────────────────────────────




# ── the model version ───────────────────────────────────────────────────────
def test_model_version_is_unchanged_at_defaults(rawstore_tmp_db):
    """The literal from before this slice: an unconfigured board versions exactly what it did (the version, 5
    since the Weinstein volume window of PR 6, moved with the model; the settings slice still moves nothing)."""
    assert freeze.model_version() == "5+c94564a9"




def test_the_model_version_still_hashes_the_non_editable_thresholds(rawstore_tmp_db, monkeypatch):
    before = freeze.model_version()
    monkeypatch.setattr(config, "ABOVE_52W_LOW", 1.3)
    assert freeze.effective_config()["ABOVE_52W_LOW"] == 1.3
    assert freeze.model_version() != before


# ── the Settings board: card, page and the generic route ────────────────────


def test_the_save_button_reads_only_its_own_board_fields():
    """Two boards share the page now, so a Save may not pick up the other card's inputs (#384 SW-S4)."""
    from RevenueChaser.module_settings import report
    assert "document.querySelectorAll('#settings-' + board + ' [data-setting]')" in report.JS


@pytest.fixture
def client(rawstore_tmp_db, monkeypatch):
    from RevenueChaser.app import dashboard
    submitted = []
    monkeypatch.setattr(dashboard.jobs, "submit",
                        lambda module, params=None: submitted.append((module, params)) or "job123")
    dashboard.app.config["TESTING"] = True
    c = panel_test_client(dashboard.app)
    c.submitted = submitted
    return c








