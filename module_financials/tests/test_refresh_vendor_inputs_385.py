"""#385 FIN-5: the Refresh and the model inputs read the Fetch's own stored vendor rows.

A Fetch stores what it fetched in ``vendor_financials`` / ``vendor_valuation`` (#297). The store-only Refresh reads
those rows back through ``core.vendor_data.read_financials`` — read-only, zero network — so the model inputs are the
rows the Fetch stored, not a raw cache payload and never a new request. Quick Remarks is handed the payload the run
already has, so a Fetch makes ONE ``get_financials`` call and a Refresh makes none.

Offline: a temp DuckDB, an injected ``get_financials``; the Refresh runs with a provider that raises on any call.
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone

import pytest

import revenuechaser.module_financials.run as fm
from revenuechaser.core import rawstore
from revenuechaser.module_asymmetric_growth import engine as agh
from revenuechaser.module_financials.engines import quick_remarks_engine as qr

# 2026-10-08 is a Thursday: 20:35 UTC = 16:35 ET (a complete session, so the valuation row is written).
COMPLETE = datetime(2026, 10, 8, 20, 35, tzinfo=timezone.utc).timestamp()
_PEER_INFO = {"enterpriseValue": 9.0e9, "ebitda": 1.0e9, "totalRevenue": 4.0e9, "trailingPE": 18.0}


def _payload(financials: dict) -> dict:
    """What ``yfinance.get_financials`` returns for the fixture: the years, each with its fiscal period end."""
    out = copy.deepcopy(financials)
    for rec in out["annual"]:
        rec["period_end"] = f"{rec['fiscal_year']}-12-31"
        # yfinance serves the cash-flow line under its canonical name, not the fixture's short one.
        rec.setdefault("capital_expenditure", rec.get("capex"))
    out["info"] = {"longName": "Test Corp.", "currency": "USD", "sector": "Technology",
                   "sharesOutstanding": 1000.0, "marketCap": 100_000.0, "currentPrice": 100.0,
                   "beta": 1.2, "enterpriseValue": 1.0e9}
    out["source"] = "yfinance"
    return out


def _failing(*_a, **_kw):
    raise AssertionError("a store-only Refresh called a provider")


# ── the reader ───────────────────────────────────────────────────────────────────────────────────────────────


# ── the Refresh's model inputs are those rows ───────────────────────────────────────────────────────────────


# ── Quick Remarks: no second get_financials ─────────────────────────────────────────────────────────────────


def test_a_refresh_with_nothing_stored_still_raises_the_no_data_error(rawstore_tmp_db, tmp_path, monkeypatch):
    """Neither vendor rows nor a raw payload: the caller falls back to a Fetch, which is not this path's job."""
    monkeypatch.setattr(fm, "OUTPUT_DIR", tmp_path)
    with pytest.raises(fm._NoCachedData):
        fm.run("ZZZZ", modules=["dcf"], output="none", no_fetch=True)
