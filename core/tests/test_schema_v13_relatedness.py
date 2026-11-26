"""Schema 12 -> 13 (#401, Relatedness v2 Step 1): the ``relatedness_embeddings`` table. Additive: nothing already
stored is rewritten.

v13's other half was two nullable columns on ``relatedness_profiles``; that table is retired (#1520), so what the
migration still has to carry is the table. The v12 store is built from a MANIFEST without it and filled through
``write_rows``; then the real MANIFEST is restored and ``ensure_all_tables`` runs again, the way the dashboard's
first store call does after the merge.
"""
from __future__ import annotations

import duckdb
import pytest

from revenuechaser.core import rawstore

V13_TABLE = "relatedness_embeddings"
_SCORE = {"ticker": "AAPL", "peer": "MSFT", "score": 0.42}


def _forget_reconciliation():
    rawstore._TABLE_READY.clear()
    rawstore._ENSURED.clear()


def _snapshot(path):
    con = duckdb.connect(str(path), read_only=True)
    try:
        rows = con.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'main' ORDER BY table_name, ordinal_position").fetchall()
    finally:
        con.close()
    out: dict[str, list] = {}
    for t, c, ty in rows:
        out.setdefault(t, []).append((c, ty))
    return out


@pytest.fixture
def v12_store(isolate_rawstore):
    """A v12 store with one scored pair; yields that row as stored."""
    mp = pytest.MonkeyPatch()
    try:
        mp.delitem(rawstore.MANIFEST, V13_TABLE)
        _forget_reconciliation()
        rawstore.ensure_all_tables()
        rawstore.write_rows("relatedness_scores", [_SCORE])
    finally:
        mp.undo()
    assert V13_TABLE not in _snapshot(rawstore.board_db_path("relatedness"))
    yield rawstore.query("SELECT * FROM relatedness_scores", db="relatedness")[0]


def _migrate():
    _forget_reconciliation()
    rawstore.ensure_all_tables()


def test_the_label_is_13():
    assert rawstore.schema_version() == "13"




def test_the_vector_holds_bytes(rawstore_tmp_db):
    vec = bytes(range(16))
    rawstore.write_rows(V13_TABLE, [{"ticker": "AAPL", "model": "bge-small-en-v1.5", "dim": 4, "vector": vec}])
    rawstore.write_rows(V13_TABLE, [{"ticker": "AAPL", "model": "bge-small-en-v1.5", "dim": 4, "vector": vec[::-1]}])
    assert rawstore.count(V13_TABLE) == 1                      # keyed on (ticker, model): an upsert
    assert bytes(rawstore.get(V13_TABLE, ("AAPL", "bge-small-en-v1.5"))["vector"]) == vec[::-1]


def test_a_second_ensure_changes_nothing(v12_store):
    _migrate()
    before = _snapshot(rawstore.board_db_path("relatedness"))
    _migrate()
    assert _snapshot(rawstore.board_db_path("relatedness")) == before
    assert rawstore.count("relatedness_scores") == 1
