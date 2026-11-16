"""Fundamentals board -> result history (#278 G1, third writer after AG #332 and Swing). Offline; temp DuckDB store.

A Fundamentals Fetch records its run through ``core/history.record_run``: one ``result_runs`` header plus the rows it
gave ``fundamentals_scores`` and ``fundamentals_gates`` (``fundamentals_scores_history`` / ``..._gates_history``,
mirrors), in one transaction on history.duckdb.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from RevenueChaser.app import runners
from RevenueChaser.core import calendar as cal
from RevenueChaser.core import ledger, rawstore
from RevenueChaser.core.tests.d01_seed import seed_d01
from RevenueChaser.rcdata.tests import prices_store
from RevenueChaser.core.providers import sec_edgar
from RevenueChaser.module_fundamentals import freeze, pipeline, scores

CUR = sec_edgar.EXTRACT_VERSION
# 2026-10-06 is a Tuesday: 22:00 UTC = 18:00 ET (session complete); 14:00 UTC = 10:00 ET (intraday).
D = date(2026, 10, 6)
COMPLETE_1 = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc)
COMPLETE_2 = datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc)
INTRADAY = datetime(2026, 10, 6, 14, 0, tzinfo=timezone.utc)


def _metrics(i=0):
    return {"ro40": 50.0 - i, "ro40_basis": "TTM", "rev_growth_ttm": 30.0, "fcf_margin": 20.0, "ttm_revenue": 1e9,
            "gross_margin": 0.5, "roic": 0.2, "net_debt_ebitda": 1.0, "pe": 20.0, "pb": 3.0,
            "dist_52w_pct": 0.9, "rs_6m": 0.1, "above_200d": True}


def _results(*tickers, version=CUR):
    return [{"ticker": t, "period": "Q2 vs Q2", "metrics": _metrics(i), "edgar_extract_version": version}
            for i, t in enumerate(tickers)]


def _rows(results):
    """What ``scores.persist`` hands the latest tables for these results."""
    sink: dict = {}
    scores.persist(results, sink=sink)
    return sink


def _payload(when=COMPLETE_1, *tickers, **kw):
    p = {"generated_at": when.isoformat(), "data_as_of": "2026-10-06", "regime": "RISK-ON", "universe_total": 900,
         "universe_generated_at": when.isoformat(), "universe_refreshed_by": "Fundamentals",
         "universe_partial": False, "passing": {"rule_of_40": 1, "quality": 1, "momentum": 1},
         "tiers": {"triple": 1, "dual": 0, "ro40": 0, "single_other": 0}, "distorted_count": 0,
         "no_data": False,
         "data_quality": {"stale_ohlc": 0, "spy_stale": False, "dropped": {}},
         "summary": {"filtered_universe": 400, "hygiene": 100, "data_short": 5, "no_edgar": 2, "top_n": len(tickers)},
         "candidates": [{"ticker": t, "multiplier": 3, "ro40": 50.0} for t in tickers]}
    p.update(kw)
    return p




def _fresh():
    return cal.session_close(D).timestamp() + 45 * 60        # cached 45 min after the close










# ── the sink: the writer gets exactly the rows the latest tables got ─────────







# ── _compute_row carries the version of the EDGAR row behind the metrics ─────

@pytest.mark.parametrize("meta, want", [({"extract_version": CUR}, CUR), ({"extract_version": 1}, 1), ({}, None)])
def test_compute_row_carries_the_extract_version_of_the_edgar_row(monkeypatch, meta, want):
    monkeypatch.setattr(pipeline.sec_edgar, "get_fundamentals", lambda t, no_fetch=False: ([{"x": 1}], [], meta))
    frame = pd.DataFrame({"Close": [1.0]})
    monkeypatch.setattr(pipeline.screen_common, "load_bars", lambda *a, **k: (frame, frame))     # D01 (C12)
    monkeypatch.setattr(pipeline, "load_ticker_info", lambda *a, **k: {})
    monkeypatch.setattr(pipeline, "ohlc_drop_reason", lambda df: None)
    monkeypatch.setattr(pipeline, "compute_indicators", lambda df, spy, **k: {"price": 10.0, "sma200": 5.0,
                                                                              "within_52w_high_pct": 0.9})
    monkeypatch.setattr(pipeline, "_ttm_metrics", lambda q, a: {k: None for k in (
        "rev_growth_ttm", "fcf_margin", "ro40", "ro40_basis", "ttm_revenue", "ttm_net_income")})
    monkeypatch.setattr(pipeline, "_quality_metrics", lambda a, q=None, **_: {k: None for k in (
        "gross_margin", "roic", "net_debt_ebitda", "total_equity")})
    row = pipeline._compute_row({"ticker": "AAA", "market_cap": 1e9}, None, spine={})
    assert row["edgar_extract_version"] == want


# ── the writer ───────────────────────────────────────────────────────────────























# the freeze's own anchor (B1 of the AG review)









# EDGAR re-extraction (extract_version 2, #158): a snapshot must not mix quarter bases









# ── the Fetch runner ─────────────────────────────────────────────────────────











