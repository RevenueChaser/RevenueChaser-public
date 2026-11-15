"""#150 (U13): AG asks Yahoo for ``.info`` only when EDGAR has the annual figures, and reads the stores
in bulk. The cards are the same as before (no board change). Synthetic stores, no network."""
from __future__ import annotations

import copy
import time

import pytest

from RevenueChaser.rcdata.tests import fund_store
from RevenueChaser.core import rawstore
from RevenueChaser.module_asymmetric_growth import engine

_QUOTE = {"regularMarketPrice": 100.0, "fiftyTwoWeekHigh": 105.0, "fiftyDayAverage": 90.0,
          "averageDailyVolume10Day": 160.0, "averageDailyVolume3Month": 100.0, "earningsTimestampStart": 1.8e9}
_ANNUAL = [{"fiscal_year": y, "revenue": r, "gross_profit": r * 0.6, "operating_cash_flow": r * 0.3,
            "capex": r * 0.05, "total_debt": 10.0, "cash": 200.0, "total_assets": 1000.0,
            "rd_expense": r * 0.2, "diluted_shares": 100.0 + i}
           for i, (y, r) in enumerate([(2021, 100.0), (2022, 130.0), (2023, 190.0)])]
_YF_ANNUAL = [dict(r, capital_expenditure=r["capex"]) for r in _ANNUAL]


class _Yahoo:
    """Counts the two provider calls; hands back what the real ones would."""

    def __init__(self, monkeypatch):
        self.info_calls, self.full_calls = [], []
        monkeypatch.setattr(engine.sec_edgar, "_cik_map", lambda: {})  # an EDGAR miss never goes online
        monkeypatch.setattr(engine.yfinance_client, "get_info", self._info)
        monkeypatch.setattr(engine.yfinance_client, "get_financials", self._full)

    def _info(self, ticker):
        self.info_calls.append(ticker)
        return {"ticker": ticker, "info": {"country": "United States", "exchange": "NMS",
                                           "industry": "Software", "longName": f"{ticker} Inc"},
                "annual": [], "market_cap": 5e9, "current_price": 100.0, "info_only": True,
                "source": "yfinance"}

    def _full(self, ticker):
        self.full_calls.append(ticker)
        return {"ticker": ticker, "info": {"country": "United States", "exchange": "NMS",
                                           "industry": "Software", "longName": f"{ticker} Inc"},
                "annual": copy.deepcopy(_YF_ANNUAL), "market_cap": 5e9, "current_price": 100.0,
                "source": "yfinance"}


def _edgar(ticker, annual=_ANNUAL, is_us=True):
    return {"ticker": ticker, "annual": copy.deepcopy(annual), "quarterly": [],
            "meta": {"source": "sec_edgar", "entity_name": f"{ticker} Corp", "is_us": is_us, "available": True}}


# ── the provider call ───────────────────────────────────────────────────────

def test_a_name_with_edgar_annual_costs_one_info_call(rawstore_tmp_db, monkeypatch):
    fund_store.put_edgar([_edgar("AAA")])
    yahoo = _Yahoo(monkeypatch)
    fin = engine._cached_financials("AAA")
    assert (yahoo.info_calls, yahoo.full_calls) == (["AAA"], [])
    assert fin["source"] == "sec_edgar" and fin["annual"][-1]["fiscal_year"] == "2023"


def test_a_name_without_edgar_annual_keeps_the_full_call(rawstore_tmp_db, monkeypatch):
    yahoo = _Yahoo(monkeypatch)
    fin = engine._cached_financials("BBB")
    assert (yahoo.info_calls, yahoo.full_calls) == ([], ["BBB"])
    assert fin["annual"]












# ── the bulk reads ──────────────────────────────────────────────────────────





class _Counter:
    def __init__(self, monkeypatch):
        self.n = 0
        real = rawstore.query

        def counting(*a, **k):
            self.n += 1
            return real(*a, **k)
        monkeypatch.setattr(rawstore, "query", counting)








# ── review M1 (and L1): a stale full row's .info is refreshed once a day, and the Refresh sees it ──



def _fetch(ticker="AAA", no_fetch=False):
    return engine._cached_financials(ticker, no_fetch=no_fetch, preload=engine._preload([ticker], no_fetch))




