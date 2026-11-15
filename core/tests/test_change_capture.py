"""Change history captured by the store (schema 11, history redesign C).

A live table that declares ``rawstore.CHANGES`` keeps its key, its writers and its readers; the store appends a rule-A
row to ``<table>_changes`` in the SAME transaction as every write to it, and the first store call of a process seeds and
syncs. The invariant every test below leans on: after any write, the keys whose latest change row is 'present' are
exactly the keys of the live table. Temp stores only.
"""
from __future__ import annotations

import random

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
