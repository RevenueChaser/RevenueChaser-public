"""PL7-b (#26): refuse data writes when a file's schema stamp is ahead of this code (newer, or unreadable).

Off unless ``RC_STORE_SCHEMA_REFUSE=1`` (``SCHEMA_REFUSE_WRITES`` is False). Readers warn, they do
not raise. ``RC_STORE_SCHEMA_OK=1`` lets a deliberate migration through and suppresses the warning.
An older stamp is not a refusal: the ensure path upgrades it (PL7-a). Temp stores only.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from RevenueChaser.core import rawstore


def _set_stamp(db: str, version: str) -> None:
    with rawstore.connect(db=db) as conn:
        conn.execute(
            "INSERT INTO store_schema (key, value) VALUES ('schema_version', ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
            [version])


def _refuse():
    from RevenueChaser.core import store_schema_refuse
    return store_schema_refuse


class TestSwitch:
    def test_the_switch_is_named_off_by_default_and_documented(self, monkeypatch):
        monkeypatch.delenv("RC_STORE_SCHEMA_REFUSE", raising=False)
        monkeypatch.delenv("RC_STORE_SCHEMA_OK", raising=False)
        mod = _refuse()
        assert mod.SCHEMA_REFUSE_WRITES is False
        assert mod.schema_refuse_writes() is False
        text = (Path(__file__).resolve().parents[2] / "docs" / "data_architecture.md").read_text(encoding="utf-8")
        assert "RC_STORE_SCHEMA_REFUSE" in text
        assert "RC_STORE_SCHEMA_OK" in text
        assert "SCHEMA_REFUSE_WRITES" in text
        assert "store_schema_refuse.py" in text

    def test_the_env_turns_refusal_on_and_the_escape_turns_it_off(self, monkeypatch):
        mod = _refuse()
        monkeypatch.setenv("RC_STORE_SCHEMA_REFUSE", "1")
        monkeypatch.delenv("RC_STORE_SCHEMA_OK", raising=False)
        assert mod.schema_refuse_writes() is True
        monkeypatch.setenv("RC_STORE_SCHEMA_OK", "1")
        assert mod.schema_refuse_writes() is False


class TestRefuseWrites:






    def test_the_other_files_are_checked_too_and_an_unreadable_stamp_is_named(self, isolate_rawstore, monkeypatch):
        monkeypatch.setenv("RC_STORE_SCHEMA_REFUSE", "1")
        rawstore.ensure_all_tables()
        _set_stamp("news", "12-dev")
        with pytest.raises(rawstore.StoreSchemaMismatch, match="not a version number"):
            rawstore.ensure_all_tables()
        assert rawstore.store_schema_mismatch()[0]["kind"] == "unreadable"




