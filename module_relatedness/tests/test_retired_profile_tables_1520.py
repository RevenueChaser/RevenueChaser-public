"""The Relatedness board keeps no profile of its own (#1520, avo's "Sil simdi", 25 Nov 2026).

The board read the SEC reading service's ``company.profile`` answers from #894 step 3b on, but it still carried
its own writer behind a switch and still copied every answer into ``relatedness_profiles`` /
``relatedness_attributes``. Until this landed the app recreated both tables, empty, on every start.

Written over the board's **source and its store**, never over a list of offenders kept in this file, so each
assertion is red on a base that still holds the writer (``red-on-base``; CLAUDE.md, #1213).
"""
from __future__ import annotations

import ast
import importlib.util
from pathlib import Path

import pytest

from revenuechaser.core import rawstore

_REPO = Path(__file__).resolve().parents[2]
_BOARD = _REPO / "module_relatedness"
_RETIRED = ("relatedness_profiles", "relatedness_attributes")


def test_the_two_tables_are_retired_and_the_store_does_not_carry_them():
    for name in _RETIRED:
        assert name not in rawstore.MANIFEST, f"{name} is still a table the store creates"
        assert name in rawstore.RETIRED_TABLES, f"{name} must say why it went, as swing_info does"


def test_opening_the_boards_file_creates_neither_table(rawstore_tmp_db):
    """What avo saw: a fresh store file held both tables, empty. ``ensure_all_tables`` built them from MANIFEST."""
    rawstore.write_rows("relatedness_scores", [{"ticker": "AAPL", "peer": "MSFT", "score": 0.42}])
    have = {r["table_name"] for r in rawstore.query(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'", db="relatedness")}
    assert have and not have & set(_RETIRED), f"the board file still carries {sorted(have & set(_RETIRED))}"


def test_a_reader_of_either_table_is_refused_by_name():
    for name in _RETIRED:
        with pytest.raises(rawstore.RawStoreError):
            rawstore.get(name, "AAPL")


def test_the_board_has_no_writer_module_left():
    """``compare``, ``service_import``, ``profiles`` and ``locator`` were the own-writer path end to end."""
    gone = [m for m in ("compare", "service_import", "profiles", "locator")
            if importlib.util.find_spec(f"revenuechaser.module_relatedness.{m}") is not None]
    assert not gone, f"the board's own profile writer is still here: {gone}"


def test_the_store_module_cannot_save_a_profile():
    from revenuechaser.module_relatedness import store
    assert not hasattr(store, "save_profile"), "a profile is the service's answer; the board writes none"
    assert not hasattr(store, "prompt_hash"), "the prompt the answer was written from is the service's own"


def _calls_a_model(path: Path) -> bool:
    """True when the file calls a writer: ``complete(...)`` on a provider module or through the registry."""
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "complete":
            return True
    return False


def test_no_source_file_of_the_board_calls_a_model_for_a_profile():
    """The naming pass is the board's one model call and it lives in the SEC service's sibling question set, so
    every remaining file of the board is model-free apart from ``naming.py``."""
    callers = sorted(p.relative_to(_REPO).as_posix() for p in _BOARD.glob("*.py")
                     if p.name != "naming.py" and _calls_a_model(p))
    assert not callers, f"these still ask a model themselves: {callers}"


def test_the_board_declares_no_profile_dataset():
    """Settings' Data inventory read the board's freshness off ``relatedness_profiles.fetched_at``; the two tables
    it still writes carry no timestamp, so the claim is the run log's."""
    from revenuechaser.core import datasets
    specs = [d for d in datasets.REGISTRY if d.db == "relatedness"]
    assert specs, "the Relatedness board has no dataset at all; this test is reading the wrong field"
    named = {t for d in specs for t in d.tables}
    assert not named & set(_RETIRED), f"a dataset still claims {sorted(named & set(_RETIRED))}"
    assert all(not isinstance(d.freshness, tuple) or d.freshness[0] not in _RETIRED for d in specs)


def test_the_scheduled_run_claims_only_the_tables_it_writes():
    from revenuechaser.core import automations
    written = set(automations.entry("RC-Relatedness-OffPeak").tables_written)
    assert not written & set(_RETIRED), f"the automation still claims {sorted(written & set(_RETIRED))}"
    assert written <= set(rawstore.MANIFEST), f"it claims tables the store has not: {sorted(written - set(rawstore.MANIFEST))}"
