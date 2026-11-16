"""``fetched_at`` on the six Stage-2 tables that had no fetch stamp (#127).

Additive ``DOUBLE``, no schema bump, no backfill. A row that is not rewritten stays
NULL (unknown, never 0). Each writer stamps the moment it fetches.
"""
from __future__ import annotations

import time

import pytest

from RevenueChaser.core import rawstore



def _forget():
    rawstore._TABLE_READY.clear()
    rawstore._ENSURED.clear()


def _columns(table: str) -> dict[str, str]:
    import duckdb
    db = rawstore._db_of(table)
    con = duckdb.connect(str(rawstore._db_path(db)), read_only=True)
    try:
        return dict(con.execute(
            "SELECT column_name, data_type FROM information_schema.columns WHERE table_name = ?",
            [table]).fetchall())
    finally:
        con.close()






def _recent(stamp, before: float) -> None:
    assert isinstance(stamp, float) and stamp > 0
    assert before <= stamp <= time.time() + 1


def test_chain_meta_writer_stamps_fetched_at(rawstore_tmp_db):
    from RevenueChaser.module_value_chain.engine import record_misses, miss_row
    before = time.time()
    record_misses([miss_row("AAA", "no_filing", "1")])
    row = rawstore.get("chain_meta", "miss:AAA")
    _recent(row["fetched_at"], before)


def test_rotation_holdings_writer_stamps_fetched_at(rawstore_tmp_db):
    from RevenueChaser.module_sector_rotation.store import save_holdings_cache
    before = time.time()
    save_holdings_cache("xlk", [{"ticker": "AAPL"}])
    row = rawstore.get("rotation_holdings", "XLK")
    _recent(row["fetched_at"], before)




def test_swing_info_writer_stamps_fetched_at(rawstore_tmp_db, monkeypatch):
    import yfinance
    class _T:
        info = {"shortName": "Aaa"}
    monkeypatch.setattr(yfinance, "Ticker", lambda ticker: _T())
    from RevenueChaser.module_swing_potential.indicators import load_ticker_info
    before = time.time()
    assert load_ticker_info("AAA")["shortName"] == "Aaa"
    row = rawstore.get("swing_info", "AAA")
    _recent(row["fetched_at"], before)
    assert row["payload"]["shortName"] == "Aaa"


def test_ticker_themes_backfill_stamps_fetched_at(rawstore_tmp_db):
    from RevenueChaser.core import ticker_store, ticker_themes
    ticker_store.write_from_cards([{"ticker": "ETON", "themes": ["Biotechnology"]}])
    before = time.time()
    ticker_themes.backfill_legacy()
    row = rawstore.get_all("ticker_themes")[0]
    _recent(row["fetched_at"], before)
    assert row["ticker"] == "ETON"


def test_a_label_sync_does_not_wipe_fetched_at(rawstore_tmp_db):
    """``naming._sync_ticker_themes`` rewrites the label through write_rows. The stamp must survive."""
    from RevenueChaser.module_relatedness.naming import _sync_ticker_themes
    rawstore.write_rows("ticker_themes", [{
        "ticker": "AAA", "theme_id": "r1:f0", "theme": "old", "level": "fine",
        "theme_run_id": "r1", "fetched_at": 1_700_000_000.0,
    }])
    n = _sync_ticker_themes("r1", {"r1:f0": {"label": "New label"}})
    assert n == 1
    row = rawstore.get_all("ticker_themes")[0]
    assert row["theme"] == "New label"
    assert row["fetched_at"] == 1_700_000_000.0
