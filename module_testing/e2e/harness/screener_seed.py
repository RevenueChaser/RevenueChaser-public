"""Seeds for the Swing and Fundamentals Fetch in the e2e tier (#383 R3 C12).

The two boards score from D01, which they read from the builder's served prices file, so a test that runs their
Fetch writes the bars there (``config.MARKET_DIR`` patched to the dashboard's market root). The D04 quotes they
prefiltered on lived in the old raw.duckdb and went with it (#860).
"""
from __future__ import annotations

import time
from datetime import date

import pandas as pd


def seed_d01(ticker: str, df: pd.DataFrame, fetched_at: float | None = None) -> None:
    """``df``'s Open/High/Low/Close/Volume bars as D01 rows; ``fetched_at`` defaults to now (after any past close)."""
    at = time.time() if fetched_at is None else fetched_at
    from RevenueChaser.rcdata.tests import prices_store
    rows = [{
        "ticker": ticker, "session_date": pd.Timestamp(ts).date(), "open": float(r["Open"]),
        "high": float(r["High"]), "low": float(r["Low"]), "close": float(r["Close"]), "adj_close": None,
        "volume": float(r["Volume"]), "split_ratio": None, "adj_source": None, "source": "uw", "fetched_at": at,
        "run_id": "e2e", "run_at": at} for ts, r in df.iterrows()]
    prices_store.put_store_rows(rows, built_at=at)


def bars_to(end: date, periods: int = 300) -> pd.DataFrame:
    """``periods`` rising business-day bars ending on ``end`` (the shape of ``test_ohlc._df``)."""
    idx = pd.bdate_range(end=end, periods=periods)
    close = pd.Series(100 + pd.Series(range(periods), index=idx) * 0.1, index=idx)
    return pd.DataFrame({"Open": close.shift(1).fillna(close.iloc[0]), "High": close * 1.01,
                         "Low": close * 0.99, "Close": close, "Volume": 1_000_000})
