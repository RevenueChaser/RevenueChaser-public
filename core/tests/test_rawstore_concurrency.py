"""Concurrency contract for the single-file DuckDB store.

The whole reason ``core/rawstore.py`` opens/closes a handle per operation is
that DuckDB has one writer and no SQLite-style WAL. Two things must hold, and
neither used to be tested:

1. A read and a write that OVERLAP IN ONE PROCESS must both work. The dashboard
   serves requests on Flask's threads while ``app/jobs.py``'s worker thread runs
   a module writer, so this happens constantly. DuckDB refuses a second
   connection to the same file with a *different* configuration, so
   ``connect()`` must never mix read-only and read-write handles.
2. Contention must be RETRIED within the stated budget, not raised on the first
   attempt — and DuckDB signals it as several different exception classes
   (another process holding the lock, the configuration clash above, and a
   thread-vs-thread race on attaching the file).
"""
from __future__ import annotations

import threading
import time

import duckdb
import pytest

from RevenueChaser.core import rawstore






class TestSameProcessOverlap:
    """Regression: a read during a write raised ConnectionException and 500'd
    the dashboard — and the retry loop never saw it, because it only caught
    IOException."""




    def test_connect_never_mixes_configurations(self, rawstore_tmp_db, monkeypatch):
        """``read_only`` selects the retry budget only — it must not reach DuckDB,
        or the same-process configuration clash comes straight back."""
        seen = []
        real = duckdb.connect

        def spy(path, *args, **kwargs):
            seen.append(kwargs)
            return real(path, *args, **kwargs)

        monkeypatch.setattr(duckdb, "connect", spy)
        with rawstore.connect(read_only=True, db="news"):
            pass
        with rawstore.connect(read_only=False, db="news"):
            pass
        assert seen and all(not k.get("read_only") for k in seen), seen




