"""#374 (avo's card tap, 2026-10-10): the RRG points of a live Rotation Fetch are kept per session.

``rotation_snapshots`` gets a ``source`` column (``live`` from a Rotation Fetch, ``backfill`` from a range backfill),
and ``rotation_snapshots_history`` mirrors the rows a live Fetch saved, keyed ``(run_id, row_no)``. Only the live
Fetch records them; a range Fetch shows stored snapshots, so its run is partial and never the session's snapshot.
Offline; temp stores.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_sector_rotation import store as rotation_store
from RevenueChaser.module_sector_rotation.tests.bars_seed import ny, pin_clock, seed
from RevenueChaser.module_sector_rotation.tests.test_rotation_store import _FakeUW, _snap

COMPLETE = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc).timestamp()




def test_a_live_save_stamps_source_live_and_returns_the_rows_it_wrote(rawstore_tmp_db):
    rows = rotation_store.save_snapshot([_snap("XLK"), _snap("XLF")], as_of=date(2026, 8, 14))
    stored = rawstore.query("SELECT * FROM rotation_snapshots ORDER BY ticker", db="sector_rotation")
    assert {r["source"] for r in stored} == {"live"} and sorted(r["ticker"] for r in rows) == ["XLF", "XLK"]
    assert sorted(rows, key=lambda r: r["ticker"]) == stored


def test_a_backfill_stamps_source_backfill(rawstore_tmp_db, monkeypatch):
    import RevenueChaser.module_sector_rotation.store as rs
    pin_clock(monkeypatch, ny(2026, 8, 14, 18))
    seed("SPY", date(2026, 8, 14), closes=lambda i: 100.0 + i)
    seed("XLK", date(2026, 8, 14), closes=lambda i: 100.0 + i)
    assert rs.backfill_snapshots(_FakeUW(), days=2) == 2
    assert {r["source"] for r in rawstore.query("SELECT source FROM rotation_snapshots", db="sector_rotation")} == {"backfill"}






