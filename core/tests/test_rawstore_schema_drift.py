"""Schema drift: differences between a live store and the MANIFEST that ``_ensure_table`` leaves alone
are recorded and logged, and a fresh store's keys are tested against the declared ones (#285, B10).

``_ensure_table`` adds a missing column. It does not retype a column or change a key, and until now it
skipped both without a word. History tables will live for years, so their keys will change: the first
sign must not be a failed write. The record is kept in memory (``schema_drift()``) and logged; a lone
``_ensure_table`` writes nothing to the store, ``ensure_all_tables`` keeps what its apply saw in ``store_meta``
(#312 item 1, ``TestDriftInStoreMeta``), and nothing migrates by itself.
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import rawstore


@pytest.fixture(autouse=True)
def _no_drift_from_other_tests():
    rawstore._SCHEMA_DRIFT.clear()
    yield
    rawstore._SCHEMA_DRIFT.clear()


def _live(ddl: str, db: str = "news") -> None:
    with rawstore.connect(db=db) as conn:
        conn.execute(ddl)


def _ensure(name: str) -> None:
    rawstore._TABLE_READY.clear()
    rawstore.ensure_table(name)














class TestNotDrift:


    def test_a_second_reconcile_of_a_fresh_store_finds_no_drift_in_any_table(self, isolate_rawstore):
        """Every MANIFEST type, STRUCT and array included, must compare equal to what DuckDB reports."""
        rawstore.ensure_all_tables()
        rawstore._TABLE_READY.clear()
        rawstore.ensure_all_tables()
        assert rawstore.schema_drift() == []



class TestLegacyColumns:
    """#431 (option B): ``edgar_documents`` still carries two empty columns of its pre-D16 shape.

    Every store open logged them twice ("not in the MANIFEST"). The MANIFEST now names them as
    ``legacy_columns``, so the check skips exactly those and nothing else: nothing migrates, no ALTER runs, and
    ``schema_drift()`` keeps its shape.
    """



    def test_no_legacy_column_is_also_a_declared_column(self):
        """A name that is both would hide a real extra column instead of explaining a known one."""
        both = {name: sorted(set(spec.get("legacy_columns") or []) & set(rawstore._columns_of(spec)))
                for name, spec in rawstore.MANIFEST.items()}
        assert {name: names for name, names in both.items() if names} == {}


# ── a fresh store's keys match the keys the MANIFEST declares ────────────────────────────────
# Tables written in "replace" mode (rows grouped by ``key`` columns) or key-less, which carry no PRIMARY
# KEY constraint by design. A table not listed here must have one that equals its ``key``.
# ``sec13f_holdings`` left this set in schema v12: it is keyed on (accession, line_no) now (#208).










# ── #312 item 1: the drift the schema apply saw is kept in store_meta ─────────────────────────────
# ``ensure_all_tables`` (the first store call of a process, read-write) upserts ``store_meta`` key
# ``schema_drift`` = {"recorded_at", "drift": [...]} when the list differs from the stored one: a store with
# drift gets the row, a fixed store gets an empty list (the record clears), an unchanged list writes nothing.


def _new_process() -> None:
    """What a new dashboard or job process starts with: no drift in memory, no table reconciled yet."""
    rawstore._SCHEMA_DRIFT.clear()
    rawstore._TABLE_READY.clear()






