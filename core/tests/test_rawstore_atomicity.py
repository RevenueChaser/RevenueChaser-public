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

from RevenueChaser.core import rawstore



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



class TestTickerStoreFullRefresh:
    """``write_from_cards`` is the single writer for a table other boards read;
    a failed scan must not leave them looking at an empty store."""

    def test_failed_write_from_cards_keeps_the_previous_scan(self, rawstore_tmp_db):
        from RevenueChaser.core import ticker_store
        ticker_store.write_from_cards(
            [{"ticker": "ETON", "name": "Eton", "market_cap": 1.8e9, "total_points": 9,
              "themes": ["Biotech"], "signals": []}], asof="2026-08-22")
        assert ticker_store.count() == 1

        with pytest.raises(Exception):
            ticker_store.write_from_cards([
                {"ticker": "AAPL", "name": "Apple", "market_cap": 1.0, "total_points": 1},
                {"ticker": "MSFT", "name": "Microsoft", "market_cap": BAD, "total_points": 2},
            ], asof="2026-08-23")

        assert ticker_store.count() == 1
        assert ticker_store.get("ETON")["themes"] == ["Biotech"]
        assert ticker_store.asof() == "2026-08-22"

    def test_write_from_cards_drops_tickers_absent_from_the_new_scan(self, rawstore_tmp_db):
        from RevenueChaser.core import ticker_store
        ticker_store.write_from_cards([{"ticker": "AAPL", "name": "Apple"},
                                       {"ticker": "MSFT", "name": "Microsoft"}])
        ticker_store.write_from_cards([{"ticker": "AAPL", "name": "Apple"}])
        assert [r["ticker"] for r in ticker_store.list_tickers()] == ["AAPL"]


