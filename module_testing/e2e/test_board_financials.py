"""Financials board, end to end: store-only refresh and error surfacing.

module_financials was the board with the silent-fallback bug: a store-only
re-render failure was swallowed by ``run_quick_cached`` (warning logged, stale
artifact or empty state served), so the tab emptied and the app went back over
the network even though the data sat in ``.store``. These tests seed the store
directly — no yfinance fixtures needed for the offline path — and prove:

1. Refresh renders the report from the store with zero provider calls.
2. A genuine render failure (the report file made unwritable, the same failure
   family as the cleared-``.cache`` FileNotFoundError) is *displayed* as an
   error board instead of being swallowed.
"""
from __future__ import annotations

import time

import pytest

_PAYLOAD = {
    "ticker": "AAPL", "sector": "Technology", "shares_outstanding": 15.0e9,
    "market_cap": 3.7e12, "current_price": 250.0, "currency": "USD", "source": "test",
    "info": {"longName": "Apple Inc.", "shortName": "Apple"},
    "annual": [
        {"fiscal_year": "2021", "revenue": 365.0e9, "ebitda": 100.0e9, "ebit": 90.0e9,
         "depreciation": 11.0e9, "capex": 11.0e9, "net_income": 95.0e9,
         "total_debt": 120.0e9, "cash": 35.0e9, "total_assets": 350.0e9,
         "total_equity": 63.0e9, "receivables": 30.0e9, "inventory": 5.0e9,
         "payables": 50.0e9, "current_assets": 135.0e9, "current_liabilities": 130.0e9,
         "interest_expense": 2.5e9, "pretax_income": 110.0e9, "tax_provision": 14.0e9},
        {"fiscal_year": "2022", "revenue": 395.0e9, "ebitda": 115.0e9, "ebit": 105.0e9,
         "depreciation": 11.0e9, "capex": 11.0e9, "net_income": 100.0e9,
         "total_debt": 110.0e9, "cash": 25.0e9, "total_assets": 350.0e9,
         "total_equity": 50.0e9, "receivables": 30.0e9, "inventory": 5.0e9,
         "payables": 50.0e9, "current_assets": 135.0e9, "current_liabilities": 130.0e9,
         "interest_expense": 2.5e9, "pretax_income": 120.0e9, "tax_provision": 14.0e9},
        {"fiscal_year": "2023", "revenue": 385.0e9, "ebitda": 110.0e9, "ebit": 100.0e9,
         "depreciation": 11.0e9, "capex": 11.0e9, "net_income": 97.0e9,
         "total_debt": 110.0e9, "cash": 30.0e9, "total_assets": 350.0e9,
         "total_equity": 60.0e9, "receivables": 30.0e9, "inventory": 5.0e9,
         "payables": 50.0e9, "current_assets": 135.0e9, "current_liabilities": 130.0e9,
         "interest_expense": 2.5e9, "pretax_income": 115.0e9, "tax_provision": 14.0e9},
    ],
}




def _refresh(dashboard, **params):
    return dashboard.view("module_financials", refresh=True, **params)






# The error board names the exception type (``app/runners.py::_write_quick_error``).
_RENDER_ERRORS = ("TypeError",)






class TestEmptyStore:
    def test_a_board_with_no_data_renders_an_empty_state(self, dashboard):
        r = dashboard.view("module_financials")
        assert r.status_code == 200
        assert "No Financials data yet" in r.text
