"""The transaction handle: one file per transaction (F6). The change capture this file once tested went with
raw.duckdb (#860)."""
from __future__ import annotations


import pytest

from RevenueChaser.core import rawstore


@pytest.fixture
def store(rawstore_tmp_db):
    return rawstore_tmp_db


# ── the four write calls and the capture in their transaction ───────────────────────────────────────────────────


# ── index_constituents has no PRIMARY KEY: today's repeats and NULLs stay accepted (report F10) ──────────────────


# ── the first call seeds and syncs; a failing table never holds the others back (F8, F10) ────────────────────────


# ── raw SQL cannot slip past the capture (refutation pass, report F11) ───────────────────────────────────────────


# ── a transaction handle writes the file it was opened on, and no other (F6) ─────────────────────────────────────
def test_a_transaction_refuses_a_table_of_another_file(store):
    with pytest.raises(rawstore.RawStoreError, match="one transaction, one file"):
        with rawstore.transaction(db="news") as tx:
            tx.write_rows("welcome_meta", [{"key": "k", "value": "v"}])  # lives in welcome
    with pytest.raises(rawstore.RawStoreError, match="one transaction, one file"):
        rawstore.atomic(lambda tx: tx.write_rows("news_meta", [{"key": "k", "value": "v"}]), db="welcome")
