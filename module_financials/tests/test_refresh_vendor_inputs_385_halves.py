"""#385 FIN-5: a Refresh chooses the statements and the valuation per part, not per payload.

``core.vendor_data.read_financials`` returns a payload when *either* half of what a Fetch stored exists, so taking
it whole replaces a complete raw cache with half a payload:

- an intraday Fetch (ET 09:30-16:30) stores statements but no ``vendor_valuation`` row (that row needs a closed
  session), so ``.info`` reads empty and the model loses the market cap, beta, price and share count;
- an EDGAR-backed AG name has a valuation row but no statement rows (#150), so ``annual`` reads empty and the board
  says the financial data is missing although the raw cache is complete.

The Refresh therefore takes each part from the stored rows when that part exists and from the cache payload when it
does not. The annual window is the Fetch's as well: ``get_financials`` serves the newest six fiscal years, and the
store keeps every period, so a Refresh must read the same six back (at year seven the NWC/revenue averages, which
take every year, would otherwise differ from the Fetch's).

Offline: a temp DuckDB, an injected ``get_financials``; a Refresh runs with every provider patched to raise.
"""
from __future__ import annotations

import copy
from datetime import datetime, timezone

import pytest

import RevenueChaser.module_financials.run as fm
from RevenueChaser.core import rawstore
from RevenueChaser.module_asymmetric_growth import engine as agh

# 2026-10-08 is a Thursday. 15:00 UTC = 11:00 ET: an intraday run, inside the session, before the close.
INTRADAY = datetime(2026, 10, 8, 15, 0, tzinfo=timezone.utc).timestamp()
# 20:35 UTC = 16:35 ET: the session is complete, so the valuation row is written.
COMPLETE = datetime(2026, 10, 8, 20, 35, tzinfo=timezone.utc).timestamp()

_INFO = {"longName": "Test Corp.", "currency": "USD", "sector": "Technology", "sharesOutstanding": 1000.0,
         "marketCap": 100_000.0, "currentPrice": 100.0, "beta": 1.2, "enterpriseValue": 1.0e9}
# What an older raw cache would hold if the stored rows did not win: every number is different.
_DECOY_INFO = {"longName": "Decoy Corp.", "currency": "USD", "sharesOutstanding": 1.0, "marketCap": 5.0,
               "currentPrice": 5.0, "beta": 0.1, "enterpriseValue": 5.0e9}
_PEER_INFO = {"enterpriseValue": 9.0e9, "ebitda": 1.0e9, "totalRevenue": 4.0e9, "trailingPE": 18.0}


def _annual(first_year: int, years: int) -> list[dict]:
    """``years`` fiscal years from ``first_year``; revenue is a function of the year (rising 100 a year) so two
    ranges that share a year carry the same numbers."""
    out = []
    for year in range(first_year, first_year + years):
        rev = 100.0 * (year - 2000)
        out.append({
            "fiscal_year": str(year), "period_end": f"{year}-12-31", "revenue": rev,
            "ebitda": rev * 0.3, "ebit": rev * 0.25, "depreciation": rev * 0.05,
            "capex": rev * 0.05, "capital_expenditure": rev * 0.05, "net_income": rev * 0.19,
            "total_debt": 260.0, "cash": 120.0, "total_assets": rev * 1.8, "total_equity": rev,
            "receivables": rev * 0.1, "inventory": rev * 0.075, "payables": rev * 0.05,
            "current_assets": rev * 0.31, "current_liabilities": rev * 0.17,
            "interest_expense": 16.0, "pretax_income": rev * 0.24, "tax_provision": rev * 0.05,
        })
    return out


def _payload(annual: list[dict], info: dict | None = None) -> dict:
    """What ``yfinance.get_financials`` returns (``_payload`` in ``core/providers/yfinance.py``): its exact keys,
    the scalars derived from ``.info`` as the provider derives them."""
    info = copy.deepcopy(_INFO if info is None else info)
    return {
        "ticker": "TEST", "info": info, "sector": "Technology",
        "annual": copy.deepcopy(annual),
        "shares_outstanding": info.get("sharesOutstanding"), "market_cap": info.get("marketCap"),
        "enterprise_value": info.get("enterpriseValue"), "beta": info.get("beta"),
        "current_price": info.get("currentPrice"), "currency": info.get("currency", "USD"), "source": "yfinance",
    }


def _failing(*_a, **_kw):
    raise AssertionError("a store-only Refresh called a provider")


def _refresh(monkeypatch, tmp_path) -> dict:
    """The store-only Refresh, with every provider patched to raise."""
    monkeypatch.setattr(fm, "OUTPUT_DIR", tmp_path)
    # #286: the comps peer read is no longer a provider call, and #645 took the last one off this board. What a
    # store-only Refresh must still not do is reach a provider through any other peer path.
    monkeypatch.setattr(fm.comps_engine, "_default_fetch_many", _failing)
    monkeypatch.setattr(agh, "score_ticker", _failing)
    return fm.run("TEST", modules=["dcf"], output="none", no_fetch=True)


# ── T1: an intraday Fetch stores statements only ──────────────────────────────────────────────────────────────


# ── T2: the mirror — a valuation row but no statement rows (an EDGAR-backed AG name) ──────────────────────────


# ── T3: both halves stored — the statements are the stored rows, the valuation is the last Fetch's ────────────


# ── T4: the Refresh reads the same six years the Fetch serves ─────────────────────────────────────────────────


# ── T5: neither half stored and no cache ──────────────────────────────────────────────────────────────────────
def test_with_neither_half_stored_and_no_cache_the_no_data_error_still_raises(rawstore_tmp_db, tmp_path,
                                                                              monkeypatch):
    """Nothing stored anywhere is still ``_NoCachedData``: the caller falls back to a Fetch."""
    monkeypatch.setattr(fm, "OUTPUT_DIR", tmp_path)
    with pytest.raises(fm._NoCachedData):
        fm.run("TEST", modules=["dcf"], output="none", no_fetch=True)


# ── T6: the valuation is the LAST Fetch's session snapshot (FIN-5, #385 review) ─────────────────────────────


# ── T7: a cache with no `.info` falls back to the stored valuation ──────────────────────────────────────────


# ── T8: as many years as the Fetch modelled (Financials review N4) ──────────────────────────────────────────
