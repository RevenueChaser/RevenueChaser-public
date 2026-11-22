"""Swing indicators — pure technical calculations over OHLCV history.

All functions are pure (no network, no I/O) so they are unit-testable with
synthetic data. ``compute_indicators`` produces the raw values consumed by the
screeners and the ranking engine; the screeners apply the thresholds.
"""
from __future__ import annotations

import logging

import pandas as pd

from revenuechaser.module_swing_potential import config

logger = logging.getLogger(__name__)

_REQUIRED = ("Open", "High", "Low", "Close", "Volume")


def normalize_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """Align/normalize OHLCV: required columns, datetime index, sorted, deduped."""
    if df is None or df.empty:
        return pd.DataFrame()
    out = df.copy()
    missing = [c for c in _REQUIRED if c not in out.columns]
    if missing:
        return pd.DataFrame()
    if not isinstance(out.index, pd.DatetimeIndex):
        idx = pd.to_datetime(out.index, errors="coerce", utc=True)
        out.index = idx.tz_localize(None) if idx.tz is not None else idx
    elif out.index.tz is not None:
        out.index = out.index.tz_localize(None)
    out = out[list(_REQUIRED)].apply(pd.to_numeric, errors="coerce")
    out = out.dropna(subset=["Close"])
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


def _to_float(v) -> float | None:
    try:
        if v is None:
            return None
        f = float(v)
        return f if f == f else None  # NaN guard
    except (TypeError, ValueError):
        return None


def _ret(close: pd.Series, n: int) -> float | None:
    if len(close) < n + 1 or n <= 0:
        return None
    base = _to_float(close.iloc[-1 - n])
    last = _to_float(close.iloc[-1])
    if not base or not last:
        return None
    return last / base - 1.0


def _sma(close: pd.Series, n: int) -> float | None:
    if len(close) < n:
        return None
    v = close.rolling(n).mean().iloc[-1]
    return _to_float(v)


def _ema(close: pd.Series, n: int) -> float | None:
    if len(close) < n:
        return None
    v = close.ewm(span=n, adjust=False).mean().iloc[-1]
    return _to_float(v)


def _atr(df: pd.DataFrame, n: int) -> float | None:
    if len(df) < n + 1:
        return None
    prev_close = df["Close"].shift(1)
    tr = pd.concat(
        [df["High"] - df["Low"], (df["High"] - prev_close).abs(), (df["Low"] - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    return _to_float(tr.rolling(n).mean().iloc[-1])


def _consistency(df: pd.DataFrame, lookback: int) -> float | None:
    if len(df) < lookback:
        return None
    sma50 = df["Close"].rolling(50).mean()
    recent = (df["Close"] > sma50).tail(lookback)
    return _to_float(recent.mean())


def _max_move_1_3m(close: pd.Series) -> float | None:
    if len(close) < 64:
        return None
    last = _to_float(close.iloc[-1])
    if not last:
        return None
    best = -1.0
    for i in range(21, 64):  # 1..3 months back
        base = _to_float(close.iloc[-1 - i])
        if base:
            best = max(best, last / base - 1.0)
    return best if best > -1.0 else None


def _breakout_volume(vol: pd.Series, close: pd.Series | None = None) -> float | None:
    """Weinstein's volume confirmation (Swing review finding 3, PR 6): the best of the last ``VOL_WINDOW`` sessions'
    volume, each over the mean of the ``VOL_AVG_DAYS`` sessions before it (itself excluded, so a spike does not
    inflate its own average). None without enough bars, or when no session of the window has both numbers.
    With ``close`` only an up day (close above the previous close) counts (Swing review D1, avo 17 Nov): heavy
    volume on a down day is selling, not a breakout. With no up day in the window the ratio is 0.0."""
    vol = pd.to_numeric(vol, errors="coerce")
    if len(vol) < config.VOL_WINDOW + config.VOL_AVG_DAYS:
        return None
    ratios = []
    for i in range(len(vol) - config.VOL_WINDOW, len(vol)):
        if close is not None:
            today, prev = _to_float(close.iloc[i]), _to_float(close.iloc[i - 1])
            if today is None or prev is None or today <= prev:      # not a known up day: its volume never counts
                ratios.append(0.0)
                continue
        day = _to_float(vol.iloc[i])
        avg = _to_float(vol.iloc[i - config.VOL_AVG_DAYS:i].mean())
        if day is not None and avg:
            ratios.append(day / avg)
    return max(ratios) if ratios else None


def compute_indicators(df: pd.DataFrame, spy_df: pd.DataFrame | None = None,
                       returns_df: pd.DataFrame | None = None) -> dict:
    """Compute all raw indicator values for one ticker (plus optional SPY benchmark).

    ``df`` gives the levels (price, averages, the 52-week range, ADR, ATR, volume). ``returns_df``, when given, gives
    the returns (the 1-day, 1-week and 1-month changes, the 1-3 month move, 12-1 momentum and RS against SPY): D3
    (#383 R3 C12) reads D01's nominal bars for levels and its dividend-adjusted bars for returns. Without it ``df``
    gives both, as before.
    """
    ind: dict = {
        "price": None, "change_pct": None, "change_1w": None, "change_1m": None, "ret_3m": None,
        "ema10": None, "ema20": None, "ema20_prev": None,
        "ema10_prev": None, "sma50": None, "sma150": None, "sma200": None,
        "sma200_prev_1m": None, "sma150_prev_1m": None,
        "adr_pct": None, "low_52w": None, "high_52w": None,
        "above_52w_low_pct": None, "within_52w_high_pct": None,
        "vol_20d": None, "vol_ratio": None,
        "move_max_1_3m": None, "mom_12_1": None, "consistency_6m": None,
        "rs_vs_spy_12m": None, "rs_vs_spy_3m": None,
        "atr14": None, "range_recent": None, "range_before": None,
    }
    df = normalize_ohlcv(df)
    if df.empty:
        return ind

    close = df["Close"]
    rclose = close
    if returns_df is not None:
        r = normalize_ohlcv(returns_df)
        rclose = r["Close"] if not r.empty else close.iloc[:0]
    price = _to_float(close.iloc[-1])
    ind["price"] = price
    rlast = _to_float(rclose.iloc[-1]) if len(rclose) else None
    rprev = _to_float(rclose.iloc[-2]) if len(rclose) >= 2 else None
    ind["change_pct"] = (rlast / rprev - 1.0) if (rlast and rprev) else None
    ind["change_1w"] = _ret(rclose, 5)
    ind["change_1m"] = _ret(rclose, 21)
    ind["ret_3m"] = _ret(rclose, 63)      # 3-month return on the RETURNS series (#384 SW-S1, D3)

    ind["ema10"] = _ema(close, 10)
    ind["ema20"] = _ema(close, 20)
    ind["ema10_prev"] = _ema(close.iloc[:-5], 10) if len(close) > 10 else None
    ind["ema20_prev"] = _ema(close.iloc[:-5], 20) if len(close) > 20 else None
    ind["sma50"] = _sma(close, 50)
    ind["sma150"] = _sma(close, 150)
    ind["sma200"] = _sma(close, 200)
    ind["sma200_prev_1m"] = _sma(close.iloc[:-21], 200) if len(close) > 220 else None
    ind["sma150_prev_1m"] = _sma(close.iloc[:-21], 150) if len(close) > 170 else None

    rng = (df["High"] - df["Low"]) / close
    ind["adr_pct"] = _to_float(rng.tail(20).mean())
    # Swing review B2: a consolidation proxy, the last sessions' mean range against the ones before them.
    n_recent, n_before = config.TIGHT_RECENT, config.TIGHT_BEFORE
    if len(rng) >= n_recent + n_before:
        ind["range_recent"] = _to_float(rng.tail(n_recent).mean())
        ind["range_before"] = _to_float(rng.iloc[-(n_recent + n_before):-n_recent].mean())

    if len(df) >= 252:
        low = _to_float(df["Low"].tail(252).min())
        high = _to_float(df["High"].tail(252).max())
    else:
        low = _to_float(df["Low"].min())
        high = _to_float(df["High"].max())
    ind["low_52w"] = low
    ind["high_52w"] = high
    ind["above_52w_low_pct"] = (price / low) if (price and low) else None
    ind["within_52w_high_pct"] = (price / high) if (price and high) else None

    vol = df["Volume"]
    # ``vol_20d`` is the plain 20-day mean, today included; ``vol_ratio`` is NOT today / vol_20d but the best of the
    # last VOL_WINDOW days, each against the VOL_AVG_DAYS before it (review 3). No card or row shows them side by
    # side (Opus review N4); do not divide one by the other.
    ind["vol_20d"] = _to_float(vol.tail(20).mean())
    ind["vol_ratio"] = _breakout_volume(vol, close)

    ind["move_max_1_3m"] = _max_move_1_3m(rclose)
    mom_12 = _ret(rclose, 252)
    mom_1 = _ret(rclose, 21)
    # Jegadeesh-Titman 12-1: the return from 12 months ago to 1 month ago
    # (skip the latest month), i.e. (1 + r12) / (1 + r1) - 1, not r12 - r1.
    ind["mom_12_1"] = ((1.0 + mom_12) / (1.0 + mom_1) - 1.0) if (mom_12 is not None and mom_1 is not None) else None
    ind["consistency_6m"] = _consistency(df, 126)

    if spy_df is not None:
        spy = normalize_ohlcv(spy_df)
        if not spy.empty:
            sc = spy["Close"]
            r12 = _ret(rclose, 252)
            s12 = _ret(sc, 252)
            r3 = _ret(rclose, 63)
            s3 = _ret(sc, 63)
            ind["rs_vs_spy_12m"] = (r12 - s12) if (r12 is not None and s12 is not None) else None
            ind["rs_vs_spy_3m"] = (r3 - s3) if (r3 is not None and s3 is not None) else None

    ind["atr14"] = _atr(df, 14)
    return ind
