"""#150 / #645 (owner, 10 Nov 2026, option A): the AG Fetch asks Yahoo for nothing. A name with stored SEC EDGAR
annual figures is scored from them alone; a name without them gets no card. Synthetic stores, no network.

The constants below are shared by other AG test files (``_QUOTE``, ``_ANNUAL``, ``_YF_ANNUAL``, ``_edgar``)."""
from __future__ import annotations

import copy
from datetime import date

import pytest

from RevenueChaser.core.providers import yfinance as yfinance_client
from RevenueChaser.module_asymmetric_growth import engine
from RevenueChaser.rcdata.tests import fund_store

_QUOTE = {"regularMarketPrice": 100.0, "fiftyTwoWeekHigh": 105.0, "fiftyDayAverage": 90.0,
          "averageDailyVolume10Day": 160.0, "averageDailyVolume3Month": 100.0, "earningsTimestampStart": 1.8e9}
_ANNUAL = [{"fiscal_year": y, "revenue": r, "gross_profit": r * 0.6, "operating_cash_flow": r * 0.3,
            "capex": r * 0.05, "total_debt": 10.0, "cash": 200.0, "total_assets": 1000.0,
            "rd_expense": r * 0.2, "diluted_shares": 100.0 + i}
           for i, (y, r) in enumerate([(2021, 100.0), (2022, 130.0), (2023, 190.0)])]
_YF_ANNUAL = [dict(r, capital_expenditure=r["capex"]) for r in _ANNUAL]


def _edgar(ticker, annual=_ANNUAL, is_us=True, **meta):
    return {"ticker": ticker, "annual": copy.deepcopy(annual), "quarterly": [],
            "meta": {"source": "sec_edgar", "entity_name": f"{ticker} Corp", "is_us": is_us, "available": True,
                     **meta}}


@pytest.fixture
def no_yahoo(monkeypatch):
    """Any Yahoo call fails the test; an EDGAR miss never goes online."""
    def boom(*a, **k):
        raise AssertionError("Yahoo was asked")
    for name in ("get_info", "get_financials"):
        monkeypatch.setattr(yfinance_client, name, boom)
    monkeypatch.setattr(engine.sec_edgar, "_cik_map", lambda: {})


def test_a_name_with_edgar_annual_is_scored_from_edgar_alone(rawstore_tmp_db, no_yahoo):
    fund_store.put_edgar([_edgar("AAA")])
    fin = engine._cached_financials("AAA")
    assert fin["source"] == "sec_edgar" and fin["annual"][-1]["fiscal_year"] == "2023"
    assert fin["info"] == {"country": "United States", "longName": "AAA Corp"}
    assert "market_cap" not in fin            # the card's cap is the universe row's (the prices store)


def test_a_name_without_edgar_annual_gets_no_financials(rawstore_tmp_db, no_yahoo):
    assert engine._cached_financials("BBB") is None
    assert engine._cached_financials("BBB", preload=engine._preload(["BBB"], False)) is None


def test_a_20f_filer_is_foreign(rawstore_tmp_db, no_yahoo):
    fund_store.put_edgar([_edgar("CCC", is_us=False)])
    assert engine._cached_financials("CCC")["info"]["country"] == "Foreign"


def test_the_card_cap_is_the_universe_rows(rawstore_tmp_db, no_yahoo):
    fund_store.put_edgar([_edgar("AAA")])
    preload = engine._preload(["AAA"], False)
    preload["as_of"] = date(2024, 6, 1)        # the 2023 year is the fresh one on this day
    card = engine.enrich_and_score("AAA", {"ticker": "AAA", "market_cap": 7e8, "price": 12.0}, preload=preload)
    assert card["market_cap"] == 7e8 and card["source"] == "sec_edgar" and card["name"] == "AAA Corp"
