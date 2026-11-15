"""Tests for the cached OHLC loader (cache-first, no network when cached)."""
from __future__ import annotations

import time
import types
from datetime import date, datetime, timezone

import pandas as pd
import pytest

from RevenueChaser.core import calendar as cal
from RevenueChaser.core import ledger, rawstore
from RevenueChaser.module_swing_potential import indicators


def _df(periods=300) -> pd.DataFrame:
    idx = pd.bdate_range("2024-01-01", periods=periods)
    close = pd.Series(100 + pd.Series(range(periods), index=idx) * 0.1, index=idx)
    return pd.DataFrame({
        "Open": close.shift(1).fillna(close.iloc[0]),
        "High": close * 1.01,
        "Low": close * 0.99,
        "Close": close,
        "Volume": 1_000_000,
    })










def test_load_ticker_info_no_fetch(rawstore_tmp_db, monkeypatch):
    assert indicators.load_ticker_info("ZZZZ", no_fetch=True) == {}
    rawstore.write_rows("swing_info", [{
        "ticker": "AAAA", "payload": {"sector": "Technology"}, "cached_at": 0.0,
    }])
    assert indicators.load_ticker_info("AAAA", no_fetch=True) == {"sector": "Technology"}


class TestScanProvenance:
    """``generated_at`` is when the scan RAN; the data date lives in
    core/provenance.py and is asserted in core/tests/test_provenance.py."""

    def test_payload_carries_the_data_date(self):
        from RevenueChaser.module_swing_potential.pipeline import build_payload
        p = build_payload([], run_stats={"data_as_of": "2026-08-31"})
        assert p["data_as_of"] == "2026-08-31"
        assert p["generated_at"][:10] != "2026-08-31"

    def test_data_as_of_delegates_to_provenance(self, rawstore_tmp_db):
        from RevenueChaser.core import rawstore
        from RevenueChaser.module_swing_potential import pipeline
        from RevenueChaser.core.tests.d01_seed import seed_d01
        assert pipeline.data_as_of() is None
        seed_d01("AAPL", ["2026-08-31"], 1.0)                 # the D01 date of a scored name (K7, #383 R3)
        rawstore.replace_all("swing_scores", [{"ticker": "AAPL"}])
        assert pipeline.data_as_of() == "2026-08-31"


# ── #128 F1: a cache that ends before the latest complete session is not fresh ─────────────────────
#
# ``load_ohlc`` reused any series younger than its TTL (1 day). A post-close run at 17:00 ET that
# started a few minutes before yesterday's write time reused bars ending D-1, and the ledger freeze
# then found no complete D bar. A Fetch now also refetches a series whose last bar is D or older (D is
# the latest complete session) and that was written before D's close + 30 min: the D bar of a
# mid-session Fetch is a partial bar (option A of #128, chosen by avo 2026-10-03).
#
# Since K8b (#383 R3) the freeze checks the picks' D01 bars (``core/tests/test_ledger_d01_only_383.py``):
# Swing and Fundamentals score from D01. ``load_ohlc`` still serves the SPY fallback and Co-movement, so
# these tests check that its cache ends with one complete D bar, by the same rule the freeze applies.

D = date(2026, 10, 2)                      # a Friday, EDT: close 20:00Z, close + 30 min = 20:30Z
RUN = datetime(2026, 10, 2, 21, 0, tzinfo=timezone.utc)         # 17:00 ET on D


def _utc(y, m, d, hh=0, mm=0):
    return datetime(y, m, d, hh, mm, tzinfo=timezone.utc)


def _ending(last_day: date, periods: int = 30) -> pd.DataFrame:
    """``periods`` business days ending on ``last_day`` (which must itself be a business day)."""
    idx = pd.bdate_range(end=pd.Timestamp(last_day), periods=periods)
    close = pd.Series(range(periods), index=idx, dtype=float) + 100.0
    return pd.DataFrame({"Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close,
                         "Volume": 1_000_000.0})






@pytest.fixture
def clock(monkeypatch):
    """Pin the market-calendar seam and ``time.time`` together: the TTL reads one, the rule the other."""
    def _set(now: datetime) -> None:
        monkeypatch.setattr(cal, "_now", lambda: now)
        monkeypatch.setattr(time, "time", lambda: now.timestamp())
    return _set


@pytest.fixture
def yahoo(monkeypatch):
    """A stand-in for ``yfinance.Ticker`` that counts calls. yfinance goes through curl_cffi, so a
    socket patch would not stop it: patch the entry points."""
    state = types.SimpleNamespace(calls=[], frame=None, fail=False, fail_for=set())

    class _T:
        def __init__(self, t):
            self.t = t

        def history(self, *a, **k):
            state.calls.append(self.t)
            if state.fail or self.t in state.fail_for:
                raise RuntimeError("Too Many Requests. Rate limited.")
            return state.frame

    def no_download(*a, **k):
        raise AssertionError("yfinance.download was called")

    monkeypatch.setattr("yfinance.Ticker", _T)
    monkeypatch.setattr("yfinance.download", no_download)
    monkeypatch.setattr(time, "sleep", lambda s: None)
    return state


































# ── option A on a whole scan: the refetch completes every cache, and a retry refetches only a failure ──
#
# Before K8b these tests froze the Swing board on the refetched cache. The freeze reads D01 now (C12
# scores from it; ``core/tests/test_ledger_d01_only_383.py`` freezes and refuses on D01), so they check
# the cache the loader leaves behind for its remaining readers (the SPY fallback, Co-movement).





