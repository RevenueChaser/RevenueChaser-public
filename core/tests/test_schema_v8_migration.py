"""Schema 7 -> 8 (#164): the stack adds tables and columns, nothing is rewritten.

The v7 store is built from a v7 MANIFEST (without the v8 tables and columns) and filled
through ``write_rows``; then the real MANIFEST is restored and ``ensure_all_tables``
runs again, the way the dashboard's first store call does after the merge.
"""
from __future__ import annotations

import datetime as _dt

import duckdb
import pytest

from revenuechaser.core import rawstore

V8_EDGAR_COLUMNS = {"edgar_financials": ("fetched_at",)}
_ANNUAL = [{"fy": 2025, "revenue": 1.5e9}, {"fy": 2024, "revenue": 1.2e9}]
_META = {"cik": "0000320193", "name": "Apple Inc."}


def _forget_reconciliation():
    # A second ensure in the same process is a no-op unless the memos are reset.
    rawstore._TABLE_READY.clear()
    rawstore._ENSURED.clear()


def _snapshot(path):
    """{table: sorted [(column, type)]} of one store file, read-only."""
    con = duckdb.connect(str(path), read_only=True)
    try:
        rows = con.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'main' ORDER BY table_name, ordinal_position").fetchall()
    finally:
        con.close()
    out: dict[str, list] = {}
    for t, c, ty in rows:
        out.setdefault(t, []).append((c, ty))
    return out


def _columns(path, table):
    return {c for c, _ in _snapshot(path).get(table, [])}




def _migrate():
    _forget_reconciliation()
    rawstore.ensure_all_tables()


def test_the_v8_tables_still_migrate_under_the_current_label():
    """The v8 tables below still migrate whatever the label says; it reads 13 since the Relatedness v2 columns
    (#401)."""
    assert rawstore.schema_version() == "13"










# Column types the v8 tables must keep: a JSON column read back as TEXT (or a DATE as TEXT)
# changes what get() returns and how writers must serialise.




# ── price_bars_daily (#164b) ─────────────────────────────────────────────────
def _bar(ticker, d, close, **kw):
    row = {"ticker": ticker, "session_date": d, "open": close, "high": close, "low": close,
           "close": close, "adj_close": close, "volume": 100.0, "split_ratio": None,
           "source": "yfinance", "fetched_at": 1.0}
    row.update(kw)
    return row






# ── catalyst_events, orphan_designations, orphan_lookups (#164c) ─────────────
def _event(**kw):
    row = {"ticker": "AMGN", "event_date": "2026-11-15", "date_precision": "day",
           "kind": "trial_readout", "title": "Phase 3 topline", "source": "ctgov",
           "source_event_id": "NCT01234567:primary_completion",
           "source_url": "https://clinicaltrials.gov/study/NCT01234567",
           "confidence": "sponsor_entered", "nct_id": "NCT01234567", "fetched_at": 1.0}
    row.update(kw)
    return row




def _designation(**kw):
    row = {"ticker": "AMGN", "generic_name": "blinatumomab",
           "designation": "Treatment of acute lymphoblastic leukemia",
           "date_designated": "2008-11-20", "designation_status": "Designated",
           "approval_status": None, "marketing_approval_date": "2014-12-03",
           "trade_name": "Blincyto",
           "approvals": [{"marketing_approval_date": "2014-12-03", "trade_name": "Blincyto"},
                         {"marketing_approval_date": "2017-07-11", "trade_name": "Blincyto"}],
           "sponsor": "Amgen Inc.", "fetched_at": 1.0}
    row.update(kw)
    return row


_DESIGNATION_KEY = ("AMGN", "blinatumomab", "Treatment of acute lymphoblastic leukemia", "2008-11-20")








def _lookup(ticker, match, **kw):
    row = {"ticker": ticker, "session_date": "2026-10-06", "sec_name": f"{ticker} Inc.", "query": ticker, "match": match,
           "provider_status": "ok", "n_rows": 0, "candidates": [], "error": None,
           "fetched_at": 1.0}
    row.update(kw)
    return row




# ── forecast_ledger (#164d): forecast-only, append-only, first write wins ────
def _forecast(**kw):
    row = {"source": "spx_gamma", "forecast_date": "2026-10-01", "subject": "SPX",
           "target_type": "pin_prob", "target_date": "2026-10-02", "frozen_at": 1.0,
           "run_id": None, "model_version": "v1", "rank": None, "score": 0.42,
           "bucket": None, "probs": {"5700": 0.3, "5750": 0.5}, "market_cap": None,
           "sector": None, "shown_price": 5730.5, "stop": None, "target": None}
    row.update(kw)
    return row


_FORECAST_KEY = ("spx_gamma", "2026-10-01", "SPX", "pin_prob", "2026-10-02")


def test_forecast_ledger_keeps_the_first_write_for_a_key(rawstore_tmp_db):
    rawstore.write_rows("forecast_ledger", [_forecast()])
    rawstore.write_rows("forecast_ledger", [_forecast(model_version="v2", score=0.9)])
    assert rawstore.count("forecast_ledger") == 1
    row = rawstore.get("forecast_ledger", _FORECAST_KEY)
    assert row["model_version"] == "v1" and row["score"] == 0.42


def test_forecast_ledger_first_write_wins_within_one_bulk_batch(rawstore_tmp_db):
    # 70 rows take the bulk path; the duplicate of row 0 comes last.
    rows = [_forecast(subject=f"T{i:03d}", target_type="pick", target_date="2026-10-01")
            for i in range(70)]
    rows.append({**rows[0], "score": 99.0})
    rawstore.write_rows("forecast_ledger", rows)
    assert rawstore.count("forecast_ledger") == 70
    first = rawstore.get("forecast_ledger", ("spx_gamma", "2026-10-01", "T000", "pick", "2026-10-01"))
    assert first["score"] == 0.42


def test_forecasts_differing_only_in_target_date_both_persist(rawstore_tmp_db):
    rawstore.write_rows("forecast_ledger", [_forecast(), _forecast(target_date="2026-10-03")])
    assert rawstore.count("forecast_ledger") == 2


def test_forecast_round_trips_probs_and_dates(rawstore_tmp_db):
    rawstore.write_rows("forecast_ledger", [_forecast(stop=5600.0, target=5800.0)])
    row = rawstore.get("forecast_ledger", _FORECAST_KEY)
    assert row["probs"] == {"5700": 0.3, "5750": 0.5}
    assert row["forecast_date"] == _dt.date(2026, 10, 1)
    assert row["target_date"] == _dt.date(2026, 10, 2)
    assert (row["stop"], row["target"]) == (5600.0, 5800.0)


