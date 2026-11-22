"""The Implied Probability fit discounts at the stored 10-year yield, not a constant (#644, avo 10 Nov 2026).

The rate of a chain's session is ``macro.dgs10`` (``core/risk_free``); the 4% constant is only the fallback, and the
board says which it stood on. The model version hashes the **rule**, never the day's value, so a new FRED
observation does not invent a new model.
"""
from __future__ import annotations

import pytest

from revenuechaser.module_oipd import config, engine, report
from revenuechaser.rcdata import ops, serving
from revenuechaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401  (fixtures)


def _serve_dgs10(points):
    with serving.build("market") as b:
        b.con.execute("CREATE TABLE market_series (series_id TEXT, obs_date DATE, source TEXT, value DOUBLE, "
                      "frequency TEXT, session_date DATE, source_as_of DATE, fetched_at DOUBLE, run_id TEXT)")
        for day, value in points:
            b.con.execute("INSERT INTO market_series VALUES ('DGS10', ?, 'fred', ?, 'daily', ?, ?, 1.0, 'r1')",
                          [day, value, day, day])
        b.swap({"market_series": len(points)})
    ops.record_check("market_series", "changed", run_id="r1")


# ── the session's rate ────────────────────────────────────────────────────────────────────────────────────────

def test_the_sessions_stored_yield_is_the_rate(market_roots):  # noqa: F811
    _serve_dgs10([("2026-11-17", 4.11), ("2026-11-18", 4.13)])
    rate, source, as_of, warning = engine.session_risk_free("2026-11-18")
    assert rate == pytest.approx(4.13 / 100) and (source, as_of, warning) == ("dgs10", "2026-11-18", None)


def test_a_session_whose_yield_is_not_held_falls_back_and_says_so(market_roots):  # noqa: F811
    _serve_dgs10([("2026-10-01", 4.11)])
    rate, source, as_of, warning = engine.session_risk_free("2026-11-18")
    assert (rate, source, as_of) == (config.RISK_FREE_RATE, "default", None)
    assert warning and "2026-11-18" in warning and "default" in warning


# ── the payload and the board ─────────────────────────────────────────────────────────────────────────────────

def test_the_payload_carries_the_rates_source_and_day():
    meta = {"as_of": "2026-11-18", "spot": None, "risk_free": 0.0413,
            "risk_free_source": "dgs10", "risk_free_as_of": "2026-11-18"}
    payload = engine._fit_payload("TST", [], meta, [])
    assert payload["risk_free"] == 0.0413
    assert payload["risk_free_source"] == "dgs10" and payload["risk_free_as_of"] == "2026-11-18"


def test_a_payload_without_a_stored_rate_is_labelled_default():
    payload = engine._fit_payload("TST", [], {"as_of": "2026-11-18", "spot": None}, [])
    assert payload["risk_free"] == config.RISK_FREE_RATE and payload["risk_free_source"] == "default"
    assert engine._empty_payload("TST", "x")["risk_free_source"] == "default"


def test_the_banner_names_the_yields_day():
    assert report._rate_line({"risk_free": 0.0413, "risk_free_source": "dgs10",
                              "risk_free_as_of": "2026-11-18"}) == "r = 4.13% · DGS10 2026-11-18"
    assert report._rate_line({"risk_free": 0.04, "risk_free_source": "default"}) == "r = 4.00% · default"
    assert report._rate_line({"risk_free": None}) == "r = —"


def test_the_build_discounts_at_the_sessions_yield(monkeypatch, market_roots):  # noqa: F811
    _serve_dgs10([("2026-11-18", 4.13)])
    # One contract, not an empty list: ``build`` returns the empty payload before it ever fits a chain of none.
    chain = [{"expiry": "2026-12-18", "option_type": "C", "strike": 100.0, "open_interest": 10.0}]
    monkeypatch.setattr(engine, "list_names", lambda: ["TST"])
    monkeypatch.setattr(engine, "stored_chain", lambda t, s=None: ("2026-11-18", chain, 100.0, None))
    seen = {}

    def spy(ticker, contracts, meta, warnings, svi=None):
        seen.update(meta)
        return {"ticker": ticker, "warnings": warnings}
    monkeypatch.setattr(engine, "_fit_payload", spy)
    engine.build("TST")
    assert seen["risk_free"] == pytest.approx(4.13 / 100) and seen["risk_free_source"] == "dgs10"
    assert seen["risk_free_as_of"] == "2026-11-18"


# ── the model version ─────────────────────────────────────────────────────────────────────────────────────────

def test_the_model_version_hashes_the_rule_and_not_the_days_rate(monkeypatch):
    """The fit's rate now moves with FRED, so the hashed knob is the rule that picks it, never a value."""
    assert config.fit_config()["risk_free"] == config.RISK_FREE_SOURCE
    assert "macro.dgs10" in config.RISK_FREE_SOURCE and "0.04" in config.RISK_FREE_SOURCE
    before = config.model_version()
    monkeypatch.setattr(config, "RISK_FREE_SOURCE", config.RISK_FREE_SOURCE + "x")
    assert config.model_version() != before
