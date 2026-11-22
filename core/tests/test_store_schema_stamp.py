"""PL7-a (#26): each store file carries its own schema stamp. Nothing refuses.

The stamp is a ``store_schema`` row, not ``store_meta``'s ``schema_version`` (that key is the
ticker-store card version, ``"3"``). A first ensure writes the code version when the row is
absent or older. A newer stamp is left alone, logged, and listed by ``store_schema_mismatch()``.
An existing file with no stamp is stamped current — an already-wrong file would be marked right;
``schema_drift()`` is the backstop for a column or key the MANIFEST no longer matches.

Refusal of writes is PL7-b (``test_store_schema_refuse.py``) and is off unless its switch is on.
Temp stores only. No ``_SCHEMA_VERSION`` bump.
"""
from __future__ import annotations

import pytest

from revenuechaser.core import rawstore


@pytest.fixture(autouse=True)
def _fresh_stamp_counters():
    rawstore._STAMP_WRITES.clear()
    rawstore._STAMP_WARNED.clear()
    yield
    rawstore._STAMP_WRITES.clear()
    rawstore._STAMP_WARNED.clear()


def _set_stamp(db: str, version: str) -> None:
    with rawstore.connect(db=db) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS store_schema (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO store_schema (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [version])


def _canary(db: str) -> str | None:
    rows = rawstore.query(
        "SELECT value FROM store_schema WHERE key = 'canary'", db=db)
    return rows[0]["value"] if rows else None


class TestStampOnEnsure:
    def test_store_schema_is_a_manifest_table_and_the_version_is_not_bumped(self):
        spec = rawstore.MANIFEST["store_schema"]
        assert spec["key"] == ["key"]
        assert any(c.startswith("value ") for c in spec["columns"])
        assert rawstore.schema_version() == "13"

    def test_an_existing_unstamped_file_is_stamped_with_the_current_version(self, isolate_rawstore):
        """The documented assumption: a file from before the stamp is marked current, not refused."""
        with rawstore.connect(db="news") as conn:
            conn.execute("CREATE TABLE an_old_table (k TEXT)")
        assert rawstore.schema_stamp("news") is None
        rawstore.ensure_all_tables()
        assert rawstore.schema_stamp("news") == "13"

    def test_an_older_stamp_is_upgraded_and_a_text_sorted_9_is_still_older(self, isolate_rawstore):
        rawstore.ensure_all_tables()
        _set_stamp("welcome", "11")
        _set_stamp("news", "9")             # "9" > "13" as text; 9 < 13 as a version
        rawstore._TABLE_READY.clear()
        rawstore.ensure_all_tables()
        assert rawstore.schema_stamp("welcome") == "13"
        assert rawstore.schema_stamp("news") == "13"

    def test_an_upgrade_keeps_the_old_value_and_warns(self, isolate_rawstore, caplog):
        """A restored older file leaves a trace after the ensure upgrades it (review SHOULD-3)."""
        rawstore.ensure_all_tables()
        _set_stamp("welcome", "11")
        rawstore._TABLE_READY.clear()
        with caplog.at_level("WARNING"):
            rawstore.ensure_all_tables()
        rows = {r["key"]: r["value"] for r in rawstore.query("SELECT key, value FROM store_schema", db="welcome")}
        assert rows["schema_version"] == "13" and rows["upgraded_from"] == "11" and rows["upgraded_at"]
        assert any("upgraded" in r.getMessage() and r.levelname == "WARNING" for r in caplog.records)

    def test_a_current_stamp_is_not_rewritten(self, isolate_rawstore):
        rawstore.ensure_all_tables()
        before = dict(rawstore._STAMP_WRITES)
        assert set(before) == set(rawstore.BOARD_DBS)
        assert all(n == 1 for n in before.values())
        with rawstore.connect(db="news") as conn:
            conn.execute("INSERT INTO store_schema (key, value) VALUES ('canary', 'keep')")
        rawstore._TABLE_READY.clear()
        rawstore.ensure_all_tables()
        assert rawstore._STAMP_WRITES == before
        assert _canary("news") == "keep"



class TestMismatchReport:



    def test_a_missing_file_is_not_a_mismatch(self, isolate_rawstore):
        rawstore.ensure_all_tables()
        assert rawstore.store_schema_mismatch() == []
