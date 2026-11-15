"""Asymmetric Growth board, end to end (#202): a ticker with EDGAR annual data stays on the board.

Its statements are seeded in the served ``fundamentals.duckdb`` (the only source since #642 PR 6; the legacy
double-encoded ``edgar_financials.meta`` case went with that store), then a store-only Refresh renders the board.
"""
from __future__ import annotations

from RevenueChaser.rcdata.tests import universe_store
import time

import pytest

_ANNUAL = [
    {"fiscal_year": "2023", "revenue": 800.0, "gross_profit": 400.0, "operating_cash_flow": 120.0,
     "capex": 20.0, "total_debt": 50.0, "cash": 200.0, "total_assets": 1000.0,
     "rd_expense": 100.0, "diluted_shares": 100.0},
    {"fiscal_year": "2024", "revenue": 850.0, "gross_profit": 500.0, "operating_cash_flow": 150.0,
     "capex": 25.0, "total_debt": 50.0, "cash": 250.0, "total_assets": 1050.0,
     "rd_expense": 130.0, "diluted_shares": 101.0},
    {"fiscal_year": "2025", "revenue": 1080.0, "gross_profit": 700.0, "operating_cash_flow": 250.0,
     "capex": 40.0, "total_debt": 60.0, "cash": 400.0, "total_assets": 1200.0,
     "rd_expense": 200.0, "diluted_shares": 102.0},
]
_QUOTE = {"regularMarketPrice": 100.0, "fiftyTwoWeekHigh": 105.0, "fiftyDayAverage": 90.0,
          "averageDailyVolume10Day": 160.0, "averageDailyVolume3Month": 100.0}








def test_refresh_with_no_stored_universe_says_so_and_calls_nothing(dashboard, provider_routes):
    before = provider_routes.request_count
    r = dashboard.view("module_asymmetric_growth", refresh=True)
    assert r.status_code == 200
    assert "No stored universe yet" in r.text and "Fetch Universe" in r.text
    assert "Click Refresh to retry" not in r.text
    assert dashboard.yf_calls() == [], "a Refresh reached the Yahoo screener"
    assert provider_routes.request_count == before
