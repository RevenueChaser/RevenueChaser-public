"""Storage-layer fixes: reset scope, schema-on-first-use, compressed columns,
bulk writes, sessions, peer-aware lock budget, atomic multi-table writes,
compaction. Each class names the defect it guards against.
"""
from __future__ import annotations

import json
import math
import os
import pathlib
import subprocess
import sys
import time

import duckdb
import pytest

from revenuechaser.core import rawstore


def _raw_conn(path):
    """A raw handle on a store file, made if it is not there yet.

    A board file sits in ``<store>/boards/``, which only ``rawstore`` creates; these tests plant a legacy file
    before the first ``rawstore`` call, so the folder has to be made here.
    """
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return duckdb.connect(str(path))


# ── reset_db must never delete the live edgar.duckdb ─────────────────────────


# ── moving EDGAR tables out of raw.duckdb must not double-encode JSON ────────


# ── large text/JSON cells are stored compressed, transparently ───────────────
class TestCompressedColumns:
    ANNUAL = [{"fiscal_year": str(y), "revenue": 1e9 + y, "ebit": None} for y in range(2000, 2026)]


    def test_cells_are_stored_as_smaller_blobs(self, rawstore_tmp_db):
        text = "The Company designs semiconductors. " * 2000
        rawstore.write_rows("chain_filings", [{"ticker": "NVDA", "item_text": text}])
        raw = rawstore.query("SELECT item_text, typeof(item_text) AS t FROM chain_filings",
                             db="value_chain")[0]
        assert raw["t"] == "BLOB"
        assert len(raw["item_text"]) < len(text) / 10
        assert rawstore.get("chain_filings", "NVDA")["item_text"] == text


    def test_a_write_rebuilds_a_legacy_table_first(self, isolate_rawstore):
        with _raw_conn(rawstore.board_db_path("value_chain")) as c:
            c.execute("CREATE TABLE chain_filings (ticker TEXT PRIMARY KEY, cik TEXT, form TEXT, "
                      "filed TEXT, accession TEXT, primary_doc TEXT, item_text TEXT, "
                      "quality TEXT, fetched_at DOUBLE)")
            c.execute("INSERT INTO chain_filings (ticker, item_text) VALUES ('OLD', 'old text')")
        rawstore.write_rows("chain_filings", [{"ticker": "NEW", "item_text": "new text"}])
        got = {r["ticker"]: r["item_text"] for r in rawstore.get_all("chain_filings")}
        assert got == {"OLD": "old text", "NEW": "new text"}

    def test_get_all_can_skip_the_heavy_column(self, rawstore_tmp_db):
        rawstore.write_rows("chain_filings", [{"ticker": "X", "filed": "2026-01-01",
                                               "item_text": "long"}])
        assert rawstore.get_all("chain_filings", columns=["ticker", "filed"]) == [
            {"ticker": "X", "filed": "2026-01-01"}]
        with pytest.raises(rawstore.RawStoreError):
            rawstore.get_all("chain_filings", columns=["nope"])


# ── the manifest is applied on a process's first store call ──────────────────
@pytest.mark.rawstore_schema_from_scratch
class TestAutoEnsure:
    @pytest.fixture
    def auto(self, monkeypatch):
        monkeypatch.setenv("RC_STORE_AUTO_ENSURE", "1")
        monkeypatch.setattr(rawstore, "_ENSURED", {})




# ── "replace" clears the whole group, not just the keys in the new batch ─────
class TestReplaceGroups:
    def test_a_rerun_drops_clusters_that_disappeared(self, rawstore_tmp_db):
        rows = lambda ids: [{"as_of": "D", "cut": 20, "cluster_id": c} for c in ids]
        rawstore.write_rows("comov_nodes", rows("abc"))
        rawstore.write_rows("comov_nodes", rows("ax"))
        got = rawstore.query("SELECT cluster_id FROM comov_nodes ORDER BY 1", db="comovement")
        assert [r["cluster_id"] for r in got] == ["a", "x"]

    def test_other_runs_are_untouched(self, rawstore_tmp_db):
        rawstore.write_rows("comov_nodes", [{"as_of": "D1", "cut": 20, "cluster_id": "k"}])
        rawstore.write_rows("comov_nodes", [{"as_of": "D2", "cut": 20, "cluster_id": "z"}])
        assert rawstore.count("comov_nodes") == 2

    def test_a_profile_rewrite_drops_old_fields(self, rawstore_tmp_db):
        rawstore.write_rows("relatedness_attributes", [
            {"ticker": "A", "field": f, "value": "[]"} for f in ("x", "y")])
        rawstore.write_rows("relatedness_attributes", [{"ticker": "A", "field": "x", "value": "[]"}])
        assert rawstore.count("relatedness_attributes") == 1


# ── bulk writes store exactly what row-by-row writes stored ──────────────────
def _mixed_rows(n):
    rows = []
    for i in range(n):
        rows.append({
            "ticker": f"T{i:04d}", "name": None if i % 7 == 0 else f"Name {i}",
            "price": [1.5, 3, None, float("inf"), 1e-12, 123456789.123456789][i % 6],
            "market_cap": float(i) * 1e9, "total_points": [3, 3.7, True, None][i % 4],
            "dilution_warning": [True, False, None][i % 3], "us_listed": 1,
            "earnings_date": None, "themes": ["AI", "Cloud"] if i % 2 else None,
            "signals": {"s": i}, "source": i if i % 5 == 0 else "screener",
        })
    return rows


def _table_rows(name):
    out = []
    for r in sorted(rawstore.get_all(name), key=lambda r: json.dumps(
            [r.get(k) for k in rawstore.MANIFEST[name]["key"]], default=str)):
        out.append({k: ("nan" if isinstance(v, float) and math.isnan(v) else v)
                    for k, v in r.items()})
    return out


class TestBulkParity:
    @pytest.mark.parametrize("mode", ["write_rows", "replace_all"])
    def test_same_contents_as_row_by_row(self, rawstore_tmp_db, monkeypatch, mode):
        rows = _mixed_rows(150)
        getattr(rawstore, mode)("ticker_scores", rows)  # bulk (150 >= 64)
        bulk = _table_rows("ticker_scores")
        rawstore.clear("ticker_scores")
        monkeypatch.setattr(rawstore, "_BULK_MIN_ROWS", 10**9)
        getattr(rawstore, mode)("ticker_scores", rows)  # executemany
        assert _table_rows("ticker_scores") == bulk


    def test_append_duplicate_keys_first_wins(self, rawstore_tmp_db):
        # forecast_ledger is the one append table left since leaps_flow_prints went (#746 plan step 5).
        rows = [{"source": "s", "forecast_date": "2026-11-02", "subject": "AAPL", "target_type": "t",
                 "target_date": "2026-12-01", "score": float(i)} for i in range(100)]
        rawstore.write_rows("forecast_ledger", rows)
        got = rawstore.query("SELECT score FROM forecast_ledger", db="forecast")
        assert [r["score"] for r in got] == [0.0]


# ── one handle per burst ─────────────────────────────────────────────────────


# ── another RevenueChaser process holding the lock is waited out ─────────────


WINDOWS_LOCK = ("IO Error: Cannot open file \"news.duckdb\": The process cannot access "
                "the file because it is being used by another process.")


class TestPeerLockBudget:
    """The presence files sit beside the board files; a board file stands for the store here."""

    @pytest.fixture
    def board(self, rawstore_tmp_db):
        path = rawstore.board_db_path("news")
        path.parent.mkdir(parents=True, exist_ok=True)
        return path

    @pytest.fixture
    def peer(self, board):
        proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
        f = rawstore._presence_file(board.parent, proc.pid)
        f.write_text(str(proc.pid))
        yield proc
        proc.kill()
        proc.wait()

    def _locked(self, monkeypatch):
        def _raise(*a, **k):
            raise duckdb.IOException(WINDOWS_LOCK)
        monkeypatch.setattr(duckdb, "connect", _raise)
        slept: list[float] = []
        monkeypatch.setattr(time, "sleep", slept.append)
        return slept

    def test_a_peer_gets_the_full_budget_even_for_a_write(self, board, peer, monkeypatch):
        slept = self._locked(monkeypatch)
        with pytest.raises(rawstore.StoreLockedError):
            rawstore._connect_with_retry(rawstore._WRITE_DELAYS, board)
        assert sum(slept) > 20.0

    def test_an_unknown_holder_still_fails_fast(self, board, monkeypatch):
        slept = self._locked(monkeypatch)
        with pytest.raises(rawstore.StoreLockedError):
            rawstore._connect_with_retry(rawstore._READ_DELAYS, board)
        assert sum(slept) < 1.0

    def test_a_dead_peers_presence_file_is_ignored_and_removed(self, board, monkeypatch):
        proc = subprocess.Popen([sys.executable, "-c", "pass"])
        proc.wait()
        f = rawstore._presence_file(board.parent, proc.pid)
        f.write_text(str(proc.pid))
        assert rawstore._peer_pids(board) == []
        assert not f.exists()


# ── several tables in one retried transaction ────────────────────────────────
class TestAtomic:
    def test_a_failure_leaves_every_table_as_it_was(self, rawstore_tmp_db):
        rawstore.write_rows("comov_runs", [{"as_of": "D", "n_tickers": 1}])
        rawstore.write_rows("comov_nodes", [{"as_of": "D", "cut": 20, "cluster_id": "a"}])

        def fn(tx):
            tx.ensure_table("comov_nodes")
            tx.execute("DELETE FROM comov_nodes WHERE as_of = ?", ["D"])
            tx.write_rows("comov_runs", [{"as_of": "D", "n_tickers": 2}])
            raise RuntimeError("members failed")

        with pytest.raises(RuntimeError):
            rawstore.atomic(fn, db="comovement")
        assert rawstore.get("comov_runs", "D")["n_tickers"] == 1
        assert rawstore.count("comov_nodes") == 1



# ── compaction ───────────────────────────────────────────────────────────────


# ── #202: edgar_financials.meta is a JSON column that legacy rows hold double-encoded ──
class TestDoubleEncodedJsonColumn:
    def _legacy(self, edgar_path, meta_cell: str):
        with _raw_conn(edgar_path) as c:
            c.execute("CREATE TABLE edgar_financials (ticker TEXT PRIMARY KEY, "
                      "annual JSON, quarterly JSON, meta JSON)")
            c.execute("INSERT INTO edgar_financials VALUES ('AAPL', '[]', '[]', ?)", [meta_cell])




# ── an empty replace_all would empty the table: refused unless asked for (#284, B9) ─────────
class TestReplaceAllEmptyGuard:
    """``replace_all(table, [])`` is DELETE + nothing: a degraded run (no peers, no edges, a
    failed fetch that produced no rows) used to wipe the last good data without a word."""


    def test_an_unknown_table_is_still_reported_as_unknown(self, rawstore_tmp_db):
        with pytest.raises(rawstore.RawStoreError, match="unknown table"):
            rawstore.replace_all("no_such_table", [])
