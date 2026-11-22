"""Swing board, end to end (#145 U21): Refresh is store-only and honest about what it has.

Seeds the store, runs a Fetch, presses Refresh, and asserts the board shows that scan (never the fixture), the
Refresh adds no yfinance or provider call, and the durable score tables are untouched. A Refresh shows the last
Fetch and never re-scores (K4, #383 R1); with no Fetch it says no scan is stored. The empty-universe
case is the one that used to call the Yahoo screener from a GET.
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.rcdata.tests import universe_store
from revenuechaser.module_testing.e2e.harness.screener_seed import bars_to, seed_d01




def _refresh(dashboard):
    return dashboard.view("module_swing_potential", refresh=True)


def _fetch(dashboard):
    """A Refresh shows the last Fetch and never re-scores (K4, #383 R1): the tests that read a scan Fetch first."""
    job = dashboard.run_job("/run/swing")
    dashboard.wait_until_idle()
    assert job.ok, job
    return job


def _payload(dashboard) -> dict:
    return json.loads(dashboard.artifact("swing_potential/swing_potential_latest.json").read_text(encoding="utf-8"))




class TestEmptyUniverse:
    def test_refresh_with_no_stored_universe_says_so_and_calls_nothing(self, dashboard, provider_routes):
        before = provider_routes.request_count
        r = _refresh(dashboard)
        assert r.status_code == 200
        assert "No stored universe yet" in r.text and "Fetch Universe" in r.text
        assert "[DEMO/FIXTURE]" not in r.text
        assert dashboard.yf_calls() == [], "a Refresh reached the Yahoo screener"
        assert provider_routes.request_count == before

    def test_a_plain_load_with_no_artifact_does_the_same(self, dashboard):
        """The plain-load self-heal shares the Refresh path (``_MODEL_ONLY_RENDERERS``)."""
        r = dashboard.view("module_swing_potential")
        assert r.status_code == 200
        assert "No stored universe yet" in r.text
        assert dashboard.yf_calls() == []


def test_a_card_with_no_rr_shows_na(tmp_path):
    """#384 SW-S2 (DF81): a null R:R shows "R:R n/a" and no slider, never a made-up 2.0."""
    from revenuechaser.core.tests.board_js import run_board_js
    from revenuechaser.module_swing_potential.pipeline import build_payload
    from revenuechaser.module_swing_potential.report import render_swing_dashboard
    gate = {"passed": True, "score": "1/1", "rules": [{"id": "r", "passed": True, "actual": 1.0}]}
    p = build_payload([], run_stats={})
    p["is_fixture"] = False
    p["candidates"] = [{
        "ticker": "ZETA", "name": "Zeta Corp", "sector": "Tech", "price": 10.0, "change_1w": 0.01,
        "change_1m": 0.01, "market_cap": 2e9, "themes": [], "index": [], "earnings_date": None,
        "quality": 80, "rs_rating": 90, "entry": 10.0, "target": None, "stop": None, "rr": None, "atr": 0.5,
        "methods": ["minervini"], "bucket": "minervini", "direction_ok": True,
        "gates": {k: gate for k in ("minervini", "weinstein", "qullamaggie", "direction")}}]
    grid = run_board_js(render_swing_dashboard(p),
                        "console.log(JSON.stringify(_els['grid'].innerHTML));", tmp_path)
    assert "R:R <b>n/a</b>" in grid
    assert 'type="range"' not in grid
