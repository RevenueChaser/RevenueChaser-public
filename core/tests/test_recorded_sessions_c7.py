"""The shared "Recorded sessions" block (#383 C7) on the K2 readers (``core/history`` sessions/runs).

- A session board (MANIFEST ``"snapshot": "session"``: the screeners, LEAPS, Rotation) lists its session snapshots,
  newest first, with every Fetch of the session counted and the rows the snapshot kept.
- A run board (Earnings, OIPD, Relatedness, Value Chain, Financials, 13F) lists its runs, newest first, with their
  quality, rows, params and notes.
- Nothing recorded: one line saying what records the first entry, and the history file is still not created.
- A failed read is shown on the board, never a failed render; every recorded string is escaped.
- Every board that writes history shows the block once (Asymmetric Growth keeps its own panel, #380, same id).
Offline; temp store.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from RevenueChaser.core import ledger, rawstore
from RevenueChaser.core import reporting_common as rc
from RevenueChaser.core.tests.board_fixtures import BOARDS

# Tue-Wed 2026-10-06..07: 22:00 UTC = 18:00 ET (session complete).
TUE = datetime(2026, 10, 6, 22, 0, tzinfo=timezone.utc).timestamp()
TUE_LATER = datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc).timestamp()
WED = datetime(2026, 10, 7, 22, 0, tzinfo=timezone.utc).timestamp()


@pytest.fixture
def store(rawstore_tmp_db):
    ledger.take_notes()
    return rawstore_tmp_db
















# LEAPS keeps its old history tables (the scan that is switched off, #730), but its page is now the far-dated contracts
# board (#746): one stored session at a time with a session picker of its own, and none of those recorded scans.
NOT_SHOWN = {"module_leaps"}
HISTORY_BOARDS = sorted(({s["board"] for s in rawstore.MANIFEST.values()
                          if s.get("db") == "history" and s.get("board")} & set(BOARDS)) - NOT_SHOWN)


def test_every_history_board_is_covered():
    # Money Flow is a panel of the Rotation tab (its own board id, no page of its own): its block is on Rotation.
    boards = {s["board"] for s in rawstore.MANIFEST.values() if s.get("db") == "history" and s.get("board")}
    assert boards - set(BOARDS) == {"module_money_flow"}
    assert len(HISTORY_BOARDS) == 11 and NOT_SHOWN <= boards






@pytest.mark.parametrize("key", HISTORY_BOARDS)
def test_every_board_that_writes_history_shows_the_block_once(key, tmp_path, monkeypatch, store):
    html = BOARDS[key].render(tmp_path, monkeypatch)
    assert html.count('id="history-panel"') == 1


