"""Fit inputs of the Implied Probability smile (review N3, N4, N10, N13; avo's D1, 18 Nov 2026)."""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np

from RevenueChaser.module_oipd import config, engine, opd_math, uw_chain

_ASOF = "2026-11-17"
_EXPIRY = (date.fromisoformat(_ASOF) + timedelta(days=45)).isoformat()
_SPOT, _R, _IV = 100.0, 0.04, 0.25


def _c(cp, K, bid, ask, root="TST"):
    return {"root": root, "expiry": _EXPIRY, "option_type": cp, "strike": K, "bid": bid, "ask": ask,
            "mid": (bid + ask) / 2 if bid and ask else None, "iv": 0.9}


def _chain(root="TST", strikes=np.arange(80.0, 121.0, 2.0)):
    T = 45 / 365.0
    F = _SPOT * math.exp(_R * T)
    out = []
    for K in strikes:
        for cp in ("C", "P"):
            p = opd_math.black76_price(F, K, T, _R, _IV, cp)
            out.append(_c(cp, float(K), round(p * 0.98, 4), round(p * 1.02, 4), root))
    return out


class TestFitInputs:
    def test_only_the_out_of_the_money_leg_so_each_strike_counts_once(self):
        got = uw_chain.fit_inputs(_chain(), 100.0, config.MAX_REL_SPREAD)
        assert all((c["option_type"] == "C") == (c["strike"] >= 100.0) for c in got)
        strikes = [c["strike"] for c in got]
        assert len(strikes) == len(set(strikes)) == 21

    def test_one_sided_crossed_and_wide_quotes_stay_out(self):
        rows = [_c("C", 110.0, 0.0, 1.0), _c("C", 112.0, 1.2, 1.0), _c("C", 114.0, 0.5, 2.0),
                _c("C", 116.0, 1.0, 1.1)]
        assert [c["strike"] for c in uw_chain.fit_inputs(rows, 100.0, 0.5)] == [116.0]

    def test_the_fit_counts_distinct_strikes(self):
        entry, err = engine._fit_expiry(_EXPIRY, _chain(), _SPOT, _R, _ASOF)
        assert err is None and entry["n"] == 21
        assert abs(entry["atm_iv"] - _IV) < 0.01


class TestOneRoot:
    def test_spx_and_spxw_on_one_date_keep_the_larger_chain_and_warn(self):
        chain = _chain("SPXW") + _chain("SPX", np.arange(90.0, 111.0, 5.0))
        payload = engine._fit_payload("SPX", chain, {"spot": _SPOT, "as_of": _ASOF}, [])
        assert len(payload["expiries"]) == 1 and payload["expiries"][0]["n"] == 21
        assert any("SPXW" in w and "left out SPX" in w for w in payload["warnings"])

    def test_one_root_passes_through(self):
        chain = _chain()
        assert uw_chain.one_root(chain) == (chain, [])


class TestModelVersion:
    def test_golden(self):
        # A changed fit knob changes the hash: bump SELECTION_VERSION in the same change, then this value.
        assert config.model_version() == "oipd-1+0230df43"

    def test_the_density_grid_is_in_the_version(self, monkeypatch):
        before = config.model_version()
        monkeypatch.setattr(config, "GRID", {**config.GRID, "grid_n": 401})
        assert config.model_version() != before

    def test_the_density_flag_threshold_is_in_the_version(self, monkeypatch):
        before = config.model_version()
        monkeypatch.setattr(config, "CLIP_FLAG_PCT", config.CLIP_FLAG_PCT * 2)
        assert config.model_version() != before

    def test_the_payload_carries_it(self):
        payload = engine._fit_payload("TST", _chain(), {"spot": _SPOT, "as_of": _ASOF}, [])
        assert payload["model_version"] == config.model_version()

    def test_the_curve_uses_the_configured_grid(self, monkeypatch):
        monkeypatch.setattr(config, "GRID", {**config.GRID, "grid_n": 401})
        seen = {}
        real = opd_math.ProbCurve

        def spy(*a, **k):
            seen.update(k)
            return real(*a, **k)
        monkeypatch.setattr(opd_math, "ProbCurve", spy)
        engine._fit_expiry(_EXPIRY, _chain(), _SPOT, _R, _ASOF)
        assert seen["grid_n"] == 401


class TestTrustworthyFan:
    def test_a_runaway_wing_is_flagged(self):
        got = opd_math.density_check(0.1, 0.1, 0.0, 0.01, config.CLIP_FLAG_PCT, 3.0, config.TAIL_FLAG_RATIO)
        assert got["flag"] and "ATM-IV width" in got["note"]
        ok = opd_math.density_check(0.1, 0.1, 0.0, 0.01, config.CLIP_FLAG_PCT, 1.1, config.TAIL_FLAG_RATIO)
        assert not ok["flag"]

    def test_a_flagged_expiry_stays_out_of_the_fan_but_on_the_board(self, monkeypatch):
        monkeypatch.setattr(config, "TAIL_FLAG_RATIO", 0.1)       # every fit is now "too wide"
        payload = engine._fit_payload("TST", _chain(), {"spot": _SPOT, "as_of": _ASOF}, [])
        assert len(payload["expiries"]) == 1 and payload["expiries"][0]["density_flag"]
        assert payload["fan"] is None and payload["error"] is None
        assert any("left out of the fan" in w for w in payload["warnings"])

    def test_a_chain_without_bids_says_so(self):
        chain = [{**c, "bid": 0.0} for c in _chain()]
        payload = engine._fit_payload("SPX", chain, {"spot": None, "as_of": _ASOF}, [])
        assert payload["expiries"] == [] and "no two-sided quote" in payload["error"]


def test_the_board_follows_the_shared_theme():
    from RevenueChaser.core.reporting_common import THEME_CSS
    from RevenueChaser.module_oipd.report import render_oipd_dashboard
    page = render_oipd_dashboard({"ticker": "TST", "asof": _ASOF, "spot": 100.0, "n_contracts": 10,
                                  "horizon_days": 30, "risk_free": 0.04, "error": None, "warnings": [],
                                  "expiries": []})
    assert THEME_CSS in page and "#05111F" not in page and "height:34px" not in page
