"""Write atomicity — a failed refresh must never destroy the previous data.

DuckDB autocommits every statement, so the DELETE half of a "replace" write (or
a ``clear()`` followed by a separate ``write_rows``) used to commit on its own:
a batch that failed to insert left the table EMPTIED. The store's docstring
promises "no silent data loss"; the exception propagating is only half of that.

Every test here seeds good rows, attempts a refresh that fails partway, and
asserts the good rows are still exactly as they were.
"""
from __future__ import annotations

import pytest

from revenuechaser.core import rawstore



# a value DuckDB cannot cast into the DOUBLE/INTEGER column it lands in, so the
# failure happens INSIDE executemany — after the DELETE, mid-batch
BAD = "not-a-number"


def _ohlc(ts: str, close: float, bad: bool = False):
    return {"ticker": "AAPL", "ts": ts, "open": BAD if bad else 1.0, "high": 1.0,
            "low": 1.0, "close": close, "volume": 1.0, "cached_at": 1.0}






class TestReplaceAll:

    def test_failed_replace_all_keeps_the_previous_rows(self, rawstore_tmp_db):
        rawstore.replace_all("ticker_scores", [
            {"ticker": "AAPL", "name": "Apple", "market_cap": 1.0, "total_points": 3},
            {"ticker": "MSFT", "name": "Microsoft", "market_cap": 2.0, "total_points": 4},
        ])
        with pytest.raises(Exception):
            rawstore.replace_all("ticker_scores", [
                {"ticker": "NVDA", "name": "Nvidia", "market_cap": 3.0, "total_points": 5},
                {"ticker": "AMD", "name": "AMD", "market_cap": BAD, "total_points": 6},
            ])
        assert {r["ticker"] for r in rawstore.get_all("ticker_scores")} == {"AAPL", "MSFT"}





