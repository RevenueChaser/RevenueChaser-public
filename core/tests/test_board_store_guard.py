"""Board-file move, PR 0 (plan 2026-11-08 §2 step 1, §8, §10): the guards every later board PR leans on.

- A raw SQL call sent to the wrong file raises: a table that MANIFEST places in ``boards/<board>.duckdb`` read with
  ``db="raw"`` would otherwise come back ``[]`` (a missing table reads as no data) and the board would go empty
  without an error.
- ``reset_db`` takes the board files with the other store files.
- A board table is never rewritten whole (§10 rule 3): no ``replace_all`` on it in the code, and no handle onto a
  board file except ``rawstore.connect`` (§9, R4). ``_WHOLE_REWRITE_EXCEPTIONS`` holds the tables whose conversion
  has not landed yet, each with its issue, and a second test fails as soon as an entry stops being true.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from revenuechaser.core import rawstore

_TABLE = "board_guard_probe"
_REPO = Path(__file__).resolve().parents[2]


@pytest.fixture
def board_table(monkeypatch):
    monkeypatch.setattr(rawstore, "BOARD_DBS", ("news",))
    monkeypatch.setattr(rawstore, "_SCHEMA_FILES", ("news",))
    monkeypatch.setitem(rawstore.MANIFEST, _TABLE, {
        "key": ["k"], "columns": ["k TEXT PRIMARY KEY", "v TEXT"],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "news", "sources": [],
    })
    rawstore.write_rows(_TABLE, [{"k": "a", "v": "1"}])
    return _TABLE


@pytest.mark.rawstore_schema_from_scratch
def test_a_read_sent_to_the_wrong_file_raises(board_table):
    with pytest.raises(rawstore.RawStoreError, match="news"):
        rawstore.query(f"SELECT v FROM {board_table}")
    with pytest.raises(rawstore.RawStoreError, match="news"):
        rawstore.query(f"SELECT 1 FROM security_master s JOIN {board_table} b ON s.ticker = b.k")


@pytest.mark.rawstore_schema_from_scratch
def test_a_write_sent_to_the_wrong_file_raises(board_table):
    with pytest.raises(rawstore.RawStoreError, match="news"):
        rawstore.execute(f"DELETE FROM {board_table} WHERE k = 'a'")


@pytest.mark.rawstore_schema_from_scratch
def test_a_parameterised_or_using_read_sent_to_the_wrong_file_still_raises(board_table):
    with pytest.raises(rawstore.RawStoreError, match="news"):
        rawstore.query(f"SELECT v FROM {board_table} WHERE k = ?", ["a"])
    with pytest.raises(rawstore.RawStoreError, match="news"):
        rawstore.query(f"SELECT 1 FROM security_master s JOIN main.{board_table} USING (k)")


@pytest.mark.rawstore_schema_from_scratch
def test_the_right_file_still_reads_and_writes(board_table):
    assert rawstore.query(f"SELECT v FROM {board_table}", db="news") == [{"v": "1"}]
    rawstore.execute(f"UPDATE {board_table} SET v = '2'", db="news")
    assert rawstore.query(f"SELECT v FROM {board_table}", db="news") == [{"v": "2"}]


@pytest.mark.rawstore_schema_from_scratch
def test_reset_db_takes_the_board_files_too(board_table):
    board = rawstore.board_db_path("news")
    assert board.exists()
    rawstore.reset_db()
    assert rawstore.query(f"SELECT v FROM {board_table}", db="news") == []


def _board_tables() -> set[str]:
    return {n for n, s in rawstore.MANIFEST.items() if s.get("db") in rawstore.BOARD_DBS}


def _code_files():
    for p in _REPO.rglob("*.py"):
        rel = p.relative_to(_REPO).as_posix()
        if "/tests/" in rel or rel.startswith(("tests/", "module_testing/")) or rel == "conftest.py":
            continue
        yield rel, p.read_text(encoding="utf-8", errors="replace")


#: Board tables still written whole, each with the issue that converts it. Empty since #863 converted
#: ``chain_mentions``; a new entry needs its own issue.
_WHOLE_REWRITE_EXCEPTIONS: dict[str, int] = {}


def test_no_board_table_is_rewritten_whole():
    names = _board_tables() - set(_WHOLE_REWRITE_EXCEPTIONS)
    hits = [f"{rel}: replace_all({m.group(1)})" for rel, text in _code_files()
            for m in re.finditer(r"replace_all\(\s*[\"'](\w+)[\"']", text) if m.group(1) in names]
    assert hits == [], "board tables are written incrementally (plan §10): " + "; ".join(hits)


def test_every_whole_rewrite_exception_is_still_a_board_table_that_is_still_rewritten():
    """An exception that stopped being true is removed, so the list cannot outlive its conversion."""
    code = list(_code_files())
    for table, issue in _WHOLE_REWRITE_EXCEPTIONS.items():
        assert table in _board_tables(), f"{table} is no longer a board table: drop it from the list (#{issue})"
        assert any(re.search(rf"replace_all\(\s*[\"']{table}[\"']", text) for _rel, text in code), (
            f"{table} is no longer rewritten whole: drop it from the list and close #{issue}")


_BOARD_OPENERS = {"core/rawstore.py", "rcdata/backup.py"}   # the store itself, and the weekly backup's copy


def _direct_board_opens(files) -> list[str]:
    path_hint = re.compile(rf"board_db_path\(|BOARDS_DIRNAME|[\"'/]{rawstore.BOARDS_DIRNAME}[\"'/]")
    return [rel for rel, text in files
            if rel not in _BOARD_OPENERS and path_hint.search(text) and "duckdb.connect" in text]


def test_only_rawstore_opens_a_board_file():
    assert _direct_board_opens([("module_x/w.py", "con = duckdb.connect(str(store / 'boards' / 'x.duckdb'))")])
    hits = _direct_board_opens(_code_files())
    assert hits == [], "a board file is opened only through rawstore.connect(db=<board>) (plan §9, R4): " + str(hits)
