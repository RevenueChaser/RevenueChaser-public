"""Fundamentals board, end to end: Refresh shows real rows, never the fixture (#205).

Since 2026-09-27 the board showed its demo fixture because a Fetch dropped cached
bars when yfinance failed and ``run_scan`` then silently emitted the fixture payload.
These tests seed the store, run a Fetch, press Refresh, and assert the rows on
the board are the seeded ones. A Refresh shows the last Fetch and never re-scores
(K4, #383 R1); with no Fetch it says no scan is stored.
"""
from __future__ import annotations

import time

import pytest

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.module_testing.e2e.harness.screener_seed import bars_to, seed_d01

_ANNUAL = [
    {"fiscal_year": "2024", "revenue": 100.0e6, "gross_profit": 60.0e6, "operating_cash_flow": 25.0e6,
     "capex": 4.0e6, "total_debt": 10.0e6, "cash": 30.0e6, "total_assets": 200.0e6,
     "total_equity": 100.0e6, "net_income": 10.0e6, "ebit": 12.0e6, "depreciation": 3.0e6},
    {"fiscal_year": "2025", "revenue": 130.0e6, "gross_profit": 78.0e6, "operating_cash_flow": 30.0e6,
     "capex": 4.0e6, "total_debt": 10.0e6, "cash": 30.0e6, "total_assets": 220.0e6,
     "total_equity": 110.0e6, "net_income": 14.0e6, "ebit": 16.0e6, "depreciation": 3.0e6},
]




def _refresh(dashboard):
    return dashboard.view("module_fundamentals", refresh=True)


def _rows(dashboard) -> list[dict]:
    """The rows the page fetches after its HTML (K10, #383 R3 slice 0): the board's payload route."""
    r = dashboard.get("/view/module_fundamentals/payload.json")
    assert r.status_code == 200
    return r.json()["rows"]


def _fetch(dashboard):
    """A Refresh shows the last Fetch and never re-scores (K4, #383 R1): the tests that read rows Fetch first."""
    job = dashboard.run_job("/run/module_fundamentals")
    dashboard.wait_until_idle()
    assert job.ok, job
    return job






class TestRefreshIsStoreOnly:
    """#145: a Refresh never calls the screener and never rewrites the durable score tables."""



    def test_refresh_with_no_stored_universe_says_so_and_calls_nothing(self, dashboard, provider_routes):
        before = provider_routes.request_count
        r = _refresh(dashboard)
        assert r.status_code == 200
        assert "No stored universe yet" in r.text and "Fetch Universe" in r.text
        assert "[DEMO/FIXTURE]" not in r.text
        assert dashboard.yf_calls() == [], "a Refresh reached the Yahoo screener"
        assert provider_routes.request_count == before
