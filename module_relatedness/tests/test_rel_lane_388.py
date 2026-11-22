"""#388 REL lane: the Pending split (D4), a Refresh keeps the last run's ``as_of`` (REL-10), and the peer market reads
only its window of the stored bars (the prices store since PR 8; D01 from the #379 switch before).

Offline, temp store; nothing calls DeepSeek or SEC (``build_profiles`` runs with ``use_llm=False`` on a Refresh and is
replaced on a Fetch).
"""
from __future__ import annotations

import json
import time

import numpy as np
import pandas as pd
import pytest

from revenuechaser.core import rawstore
from revenuechaser.module_comovement.tests import prices_bars
from revenuechaser.module_relatedness import engine, report, store
from revenuechaser.module_relatedness.tests.test_pure_refresh import _market_peers, _market_prices
from revenuechaser.module_relatedness.tests.test_relatedness import _prof, _seed_filings

TICKERS = [f"T{i:02d}" for i in range(8)]




# ── D4: Pending = tickers - usable - no_text ────────────────────────────────










# ── REL-10: a Refresh keeps the last run's as_of ────────────────────────────






# ── the peer market reads its window only ───────────────────────────────────
def _seed_prices(prices: pd.DataFrame) -> None:
    now = time.time()
    prices_bars.write_bars([
        {"ticker": t, "ts": ts.isoformat(), "open": float(p), "high": float(p), "low": float(p),
         "close": float(p), "volume": 1.0, "cached_at": now}
        for t in prices.columns for ts, p in prices[t].items() if not np.isnan(p)])


def _attach(peers):
    engine._attach_peer_market(peers)
    return json.dumps(peers, sort_keys=True)


def test_the_peer_market_equals_the_full_read(rawstore_tmp_db, monkeypatch):
    from revenuechaser.module_comovement import ohlc as comov_ohlc

    _seed_prices(_market_prices(n=420))
    real = comov_ohlc.price_frame
    monkeypatch.setattr(comov_ohlc, "price_frame", lambda tickers, start=None: real(tickers))
    full = _attach(_market_peers())
    monkeypatch.setattr(comov_ohlc, "price_frame", real)
    windowed = _attach(_market_peers())
    assert windowed == full
    assert '"move"' in full and '"beyond_spy"' in full


def test_the_peer_market_reads_only_its_window(rawstore_tmp_db, monkeypatch):
    from revenuechaser.module_comovement import config as comov_config
    from revenuechaser.module_comovement import ohlc as comov_ohlc
    from revenuechaser.module_comovement import settings as comov_settings

    prices = _market_prices(n=420)
    _seed_prices(prices)
    starts = []
    real = comov_ohlc.price_frame

    def spy(tickers, start=None):
        starts.append(start)
        return real(tickers, start=start)

    monkeypatch.setattr(comov_ohlc, "price_frame", spy)
    engine._attach_peer_market(_market_peers())
    need = comov_settings.effective().window + max(comov_config.HORIZONS)
    assert starts == [prices.index[-need].strftime("%Y-%m-%d")]


def test_a_short_store_reads_everything(rawstore_tmp_db, monkeypatch):
    from revenuechaser.module_comovement import ohlc as comov_ohlc

    _seed_prices(_market_prices(n=200))
    starts = []
    real = comov_ohlc.price_frame
    monkeypatch.setattr(comov_ohlc, "price_frame",
                        lambda tickers, start=None: starts.append(start) or real(tickers, start=start))
    engine._attach_peer_market(_market_peers())
    assert starts == [None]
