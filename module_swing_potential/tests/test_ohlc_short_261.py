"""#261: a short refetch must not replace a longer stored OHLC history."""
from __future__ import annotations

import time

import pandas as pd
import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_swing_potential import indicators
from RevenueChaser.module_swing_potential import pipeline
from RevenueChaser.module_swing_potential.tests.test_ohlc import _df


def _yahoo(frame):
    class _T:
        def __init__(self, t):
            pass

        def history(self, *a, **k):
            return frame

    return _T


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    """yfinance goes through curl_cffi, so socket patches do not stop it: patch the entry points."""
    def boom(*a, **k):
        raise AssertionError("yfinance was called for real")
    monkeypatch.setattr("yfinance.download", boom)
    monkeypatch.setattr(time, "sleep", lambda s: None)














def test_the_pipeline_counts_a_refused_short_frame_as_stale(rawstore_tmp_db, monkeypatch):
    frame = _df(300)
    frame.attrs["stale"] = True
    frame.attrs["short_refetch_refused"] = True
    monkeypatch.setattr(pipeline.screen_common, "load_bars", lambda *a, **k: (frame, frame))
    monkeypatch.setattr(pipeline, "compute_indicators",
                        lambda df, spy, **k: {"price": 100.0, "atr14": 2.0})
    row = pipeline._compute_row({"ticker": "AAPL"}, None)
    assert "short_refetch_refused" not in row                   # D01 bars are never refused; SPY's flag counts (PR 6)
    assert row["ohlc_stale"] is True                            # a refused frame is still counted stale
    payload = pipeline.build_payload([row], run_stats={})
    assert payload["data_quality"]["short_refetch_refused"] == 0


# ── review round (2026-10-14): boundaries, equal counts, a reused symbol ──────

def _shifted(n: int, start: str):
    frame = _df(n)
    frame.index = pd.bdate_range(start, periods=n)
    return frame








