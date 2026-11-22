"""Opus review of MW-ROT-A (#374, M-ROT-2/3), 2026-10-16: the D01 inputs line up by session.

- The RRG lines an ETF's ISO-week closes up with SPY's weeks: a week D01 lacks for the ETF does not shift its 4- and
  12-week lookbacks onto other weeks, and an ETF whose D01 series stops before the session's week is not plotted as
  of that session (it is missing, so the run is partial).
- A split inside the window does not move the RRG (the prices store's split basis applies it on read, since PR 9).
- Money Flow does not rank an ETF whose D01 series stops before the session (missing, so the result is partial).
- The range backfill names the ETFs it left out of the sessions it wrote.
Offline: a temp store, the calendar clock pinned.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

import pytest

from revenuechaser.app import runners
from revenuechaser.app.jobs import JobMessage
from revenuechaser.core import rawstore
from revenuechaser.module_sector_rotation import engine, money_flow as mf, store
from revenuechaser.module_sector_rotation.tests.bars_seed import ny, pin_clock, seed as _seed, sessions as _sessions
from revenuechaser.rcdata import read
from revenuechaser.rcdata.tests import prices_store
from revenuechaser.module_sector_rotation.tests.test_rotation_a5_374 import UNIVERSE, _UW, _stored

SESSION = date(2026, 10, 7)


def _bars(ticker: str, days: list[date], close, fetched_at: float = 0.0) -> None:
    prices_store.put_bars([
        {"ticker": ticker, "session_date": d, "open": close(d), "high": close(d), "low": close(d), "close": close(d),
         "volume": 1e6, "fetched_at": fetched_at} for d in days], replace=False, overwrite=True)


def _rising(d: date) -> float:
    return 100.0 + (d - date(2025, 1, 1)).days * 0.1


def _week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


# ── the RRG lines weeks up with SPY's ─────────────────────────────────────────────────────────────────────────────────







# ── Money Flow ───────────────────────────────────────────────────────────────────────────────────────────────────────

def test_money_flow_does_not_rank_an_etf_whose_series_stops_before_the_session(rawstore_tmp_db, monkeypatch):
    session = date(2026, 8, 14)
    pin_clock(monkeypatch, ny(2026, 8, 14, 18))
    ranked = mf.ranked_tickers()
    stale = ranked[0]
    for k, t in enumerate(ranked):
        end = date(2026, 7, 24) if t == stale else session
        _seed(t, end, start=date(2026, 5, 1), closes=(lambda i: 100.0 + i) if k % 2 else (lambda i: 200.0 - i))
    res = mf.compute_money_flow(days=30, window=21, top_n=len(ranked))
    assert res["partial"] is True and res["missing"] == [stale]
    assert stale not in {r["ticker"] for r in res["inflows"] + res["outflows"]}
    assert res["as_of"] == session.isoformat()


# ── backfill ─────────────────────────────────────────────────────────────────────────────────────────────────────────

