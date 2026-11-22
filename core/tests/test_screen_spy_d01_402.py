"""U1 (#402, K8b's SPY part): the Swing and Fundamentals SPY baseline reads D01 first.

``core.screen_common.load_spy`` takes SPY from ``price_bars_daily`` when D01 holds the latest complete session, and
returns an empty frame marked ``fetch_failed`` when it does not (the old ``swing_ohlc`` read went with #860). Offline; the store is a temp
DuckDB, the clock is the calendar seam.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pandas as pd
import pytest

from revenuechaser.core import calendar as cal
from revenuechaser.core import ledger, rawstore, screen_common
from revenuechaser.core.tests.d01_seed import write_d01

D = date(2026, 10, 14)                                         # the 14 Oct session (#402)
NOW = datetime(2026, 10, 14, 21, 45, tzinfo=timezone.utc)      # 17:45 EDT, after RC-Daily-Bars
FETCHED = datetime(2026, 10, 14, 20, 40, tzinfo=timezone.utc).timestamp()   # 16:40 EDT, after close + 30 min


def _sessions(end: date, n: int) -> list[date]:
    return [d.date() for d in pd.bdate_range(end=end, periods=n)]


def _seed_d01(ticker: str, days: list[date], *, fetched_at: float = FETCHED, close=None):
    write_d01([{
        "ticker": ticker, "session_date": d, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
        "adj_close": None, "volume": 1.0e6, "split_ratio": None, "adj_source": None, "source": "uw",
        "fetched_at": fetched_at, "run_id": "seed", "run_at": fetched_at}
        for i, d in enumerate(days) for c in [close(i) if close else 400.0 + i]])


def _failed(frame) -> bool:
    """No D01 baseline: an empty frame marked ``fetch_failed`` (the old ``swing_ohlc`` read went with #860)."""
    return frame.empty and frame.attrs.get("fetch_failed") is True


@pytest.fixture
def clock(monkeypatch):
    monkeypatch.setattr(cal, "_now", lambda: NOW)


def test_the_baseline_reads_d01_when_it_holds_the_latest_complete_session(rawstore_tmp_db, clock):
    _seed_d01("SPY", _sessions(D, 300))
    spy = screen_common.load_spy()
    assert spy.index[-1] == pd.Timestamp(D)
    assert list(spy.columns) == ["Open", "High", "Low", "Close", "Volume"]
    assert spy["Close"].iloc[-1] == 400.0 + 299
    assert not spy.attrs.get("stale")
    assert spy.attrs.get("source") == "d01"


def test_the_baseline_is_empty_when_d01_lacks_the_session(rawstore_tmp_db, clock):
    _seed_d01("SPY", _sessions(D - timedelta(days=1), 300))
    spy = screen_common.load_spy()
    assert _failed(spy)


def test_the_baseline_is_empty_with_no_spy_in_d01(rawstore_tmp_db, clock):
    _seed_d01("QQQ", _sessions(D, 10))
    assert _failed(screen_common.load_spy())


def test_the_baseline_is_empty_when_the_d01_bar_was_written_before_the_close_plus_30(rawstore_tmp_db, clock):
    early = datetime(2026, 10, 14, 20, 29, tzinfo=timezone.utc).timestamp()
    _seed_d01("SPY", _sessions(D, 300), fetched_at=early)
    assert _failed(screen_common.load_spy())


def test_a_failed_d01_read_is_an_empty_baseline(rawstore_tmp_db, clock, monkeypatch):
    from revenuechaser.core import prices
    _seed_d01("SPY", _sessions(D, 300))

    def boom(*a, **k):
        raise RuntimeError("IO Error: Could not set lock on file prices.duckdb")

    monkeypatch.setattr(prices, "daily_bars", boom)
    assert _failed(screen_common.load_spy())


def test_a_run_the_calendar_cannot_place_is_an_empty_baseline(rawstore_tmp_db, monkeypatch):
    monkeypatch.setattr(cal, "_now", lambda: datetime(2099, 1, 5, 23, 0, tzinfo=timezone.utc))
    assert _failed(screen_common.load_spy())


def test_the_baseline_is_dividend_adjusted_like_yfinance_auto_adjust(rawstore_tmp_db, clock):
    """yfinance ``auto_adjust=True`` (the old read) scales the bars before an ex-date; so does D01's adjusted basis."""
    days = _sessions(D, 300)
    _seed_d01("SPY", days, close=lambda i: 400.0)
    ex = days[-10]
    write_d01([], [{
        "ticker": "SPY", "ex_date": ex, "action": "dividend", "value": 4.0, "session_date": ex,
        "source": "yfinance", "fetched_at": FETCHED, "run_id": "seed", "run_at": FETCHED}])
    spy = screen_common.load_spy()
    assert spy.loc[pd.Timestamp(days[-11]), "Close"] == pytest.approx(400.0 * (1 - 4.0 / 400.0))
    assert spy.loc[pd.Timestamp(ex), "Close"] == pytest.approx(400.0)


def test_the_baseline_window_is_the_old_two_years(rawstore_tmp_db, clock):
    days = _sessions(D, 700)
    _seed_d01("SPY", days)
    spy = screen_common.load_spy()
    assert spy.index[0] >= pd.Timestamp(D - timedelta(days=screen_common.SPY_BASELINE_DAYS))
    assert len(spy) >= 252 + 1                                  # enough for the 12-month RS and the 200-day mean


def test_the_baseline_and_the_freeze_anchor_agree(rawstore_tmp_db, clock):
    """Both use ``ledger.d01_has_session``: a baseline from D01 is never refused by the anchor, and back."""
    _seed_d01("SPY", _sessions(D - timedelta(days=1), 5))
    assert _failed(screen_common.load_spy()) and ledger.d01_has_session(D, "SPY") is False
    _seed_d01("SPY", [D])
    assert not _failed(screen_common.load_spy())
    assert ledger.spy_anchor_problem(D) is None


# ── the two boards are wired to it ──────────────────────────────────────────



# ── avo L1 (18 Nov 2026): Fundamentals scores as of SPY's newest stored session ──

def test_the_newest_baseline_reads_spys_newest_session_when_d01_lacks_the_latest(rawstore_tmp_db, clock):
    _seed_d01("SPY", _sessions(D - timedelta(days=1), 300))
    assert _failed(screen_common.load_spy())                       # Swing's baseline is unchanged
    spy = screen_common.load_spy_newest()
    assert not spy.empty and spy.index[-1] == pd.Timestamp(D - timedelta(days=1))
    assert spy.attrs["behind"] == (D - timedelta(days=1)).isoformat() and not spy.attrs.get("fetch_failed")


def test_the_newest_baseline_is_load_spy_when_the_session_is_there(rawstore_tmp_db, clock):
    _seed_d01("SPY", _sessions(D, 300))
    spy = screen_common.load_spy_newest()
    assert spy.index[-1] == pd.Timestamp(D) and "behind" not in spy.attrs


def test_the_newest_baseline_is_empty_with_no_spy_at_all(rawstore_tmp_db, clock):
    _seed_d01("QQQ", _sessions(D, 10))
    assert _failed(screen_common.load_spy_newest())
