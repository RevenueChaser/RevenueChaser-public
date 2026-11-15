"""Earnings Radar board -> result history (#278 G1 writer). Offline; the store is a temp DuckDB.

An Earnings Fetch records its run through ``core/history.record_run``: one ``result_runs`` header plus one
``earnings_cards_history`` row per scored card, in one transaction on history.duckdb. Earnings is a run board: every
run's rows are kept, unless the run's inputs are stale (B1): then the header is kept and says why, and no rows.
"""
from __future__ import annotations

import json
import zlib
from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core import ledger, rawstore
from RevenueChaser.module_earnings_radar.models import TradeCard
from RevenueChaser.module_earnings_radar.pipeline import nrc_from_card

# 2026-10-06 is a Tuesday: 22:00 UTC = 18:00 ET (session complete); 14:00 UTC = 10:00 ET (intraday).
COMPLETE = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc).timestamp()
INTRADAY = datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc).timestamp()
HEALTHY = {"calls": 400, "failed": 0, "failures": [], "auth_error": None, "breaker_open": False, "skipped_calls": 0}


def _card(ticker, **kw):
    c = TradeCard(ticker=ticker, earnings_date=date(2026, 10, 8), earnings_time="AMC", fiscal_quarter="Q3 2026",
                  final_action="BUY_CALL_SPREAD", direction_score=40.0, r2_score=30.0, r3_score=20.0,
                  r4_score=10.0, r7_score=5.0, r8_score=-3.0, volatility_edge_score=12.5, confidence_score=62.0,
                  expected_move_pct=7.5, data_completeness=0.8, pre_score=14.2, filter_status="passed",
                  trade_read="Lean long", attention_score=55.0, edge_ratio=1.4, key_thesis="strong beat history",
                  rotation_quadrant="LEADING",
                  rule_audit={"rule2_guidance": {"available": True, "contribution": 6.0},
                              "rule7_accounting": {"available": False, "contribution": None}},
                  raw_packet_json=json.dumps({"screener": {"close": 50}, "ohlc": [1, 2], "current_price": 50.0}))
    for k, v in kw.items():
        setattr(c, k, v)
    return c






def _unpack(cell):
    """A compressed JSON cell as the raw query returns it (zlib bytes) or already decoded."""
    if isinstance(cell, (bytes, bytearray)):
        return json.loads(zlib.decompress(cell))
    return cell if not isinstance(cell, str) else json.loads(cell)




@pytest.fixture
def store(rawstore_tmp_db):
    ledger.take_notes()
    return rawstore_tmp_db




















# ── degraded inputs: the run is kept, partial, with its rows (design C rule E) ──

def _health(**kw):
    return {**HEALTHY, **kw}












def _session_events(n, day=date(2026, 10, 8), when="AMC", source="UW"):
    return [{"ticker": f"T{i}", "earnings_date": day, "earnings_time": when, "source": source} for i in range(n)]


















# ── a card from the real pipeline (not a hand-filled one) ────────────────────

def _real_card(**uw):
    from RevenueChaser.module_earnings_radar.tests.test_pipeline_score import _FakeUW, _make_pipeline

    class UW(_FakeUW):
        def term_structure(self, ticker):
            return [{"expiry": "2026-10-16", "volatility": "0.9", "dte": 8},
                    {"expiry": "2026-11-20", "volatility": "0.6", "dte": 43}]

        def spot_exposures_by_strike(self, ticker):
            return [{"strike": "150", "call_gamma_oi": "10", "put_gamma_oi": "-5", "price": "150.0", "time": "t",
                     "ticker": "AAPL", "expiry": "x", "call_gamma_ask": "1"}]

        def stock_earnings(self, ticker):
            return [{"actual_eps": "1.1", "estimate": "1.0", "report_date": "2026-07-30"}]

    scr = {"AAPL": {"close": "150.0", "call_volume": "5000", "put_volume": "4000", "total_open_interest": "90000"}}
    cal = {"AAPL": {"earnings_date": "2026-10-08", "full_name": "Apple", "sector": "Technology",
                    "expected_move_perc": 0.05}}
    bars = [{"close": str(100 + i), "open": "1", "high": "1", "low": "1", "volume": 1, "start_time": f"d{i}"}
            for i in range(270)]
    p = _make_pipeline(UW(etf_ohlc=bars, **uw), scr, cal)
    p._shorts_cache = {"AAPL": {"si_pct": 4.2}}
    return p._score("AAPL")








def test_a_strike_row_is_cut_to_the_13_fields_the_gex_profile_reads():
    from RevenueChaser.module_earnings_radar.pipeline import _strike_fields
    full = {"strike": "1", **{f"{s}_{g}{b}": "0" for g in ("gamma", "charm", "vanna") for b in ("_oi", "_vol")
                              for s in ("call", "put")}, "extra": "x", "call_gamma_ask": "1"}
    (row,) = _strike_fields({"data": [full, "junk"]})
    assert len(row) == 13 and "extra" not in row and "call_gamma_ask" not in row and row["strike"] == "1"
    assert _strike_fields(None) == [] and _strike_fields([{"strike": "2"}]) == [{"strike": "2"}]




