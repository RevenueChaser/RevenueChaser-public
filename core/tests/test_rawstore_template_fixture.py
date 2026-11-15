"""The ``rawstore_tmp_db`` fixture copies a per-session template instead of applying the schema per test.

The template is built once per pytest process by ``ensure_all_tables`` itself, and every test gets its OWN copy of
the files in its own ``tmp_path``; the template is never handed to a test. A test marked
``rawstore_schema_from_scratch``, or one whose schema inputs (``MANIFEST`` and the migration tables) differ from the
template's, still gets the apply run on its own file. See ``conftest.py`` and ``docs/testing_framework.md``.
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import rawstore






def _tables(db: str) -> set[str]:
    return {r["table_name"] for r in rawstore.query(
        "SELECT table_name FROM information_schema.tables WHERE table_schema = 'main'", db=db)}






@pytest.fixture
def extra_table(monkeypatch):
    """A schema input the template was not built from: a MANIFEST patched before the store is made."""
    monkeypatch.setitem(rawstore.MANIFEST, "template_probe", {
        "kind": "tabular", "key": ["k"], "write": "upsert", "db": "news",
        "columns": ["k TEXT", "v DOUBLE", "PRIMARY KEY (k)"]})




@pytest.fixture
def reordered_manifest(monkeypatch):
    """The same MANIFEST in another key order, as monkeypatch.delitem's undo leaves it for the next test."""
    reordered = dict(rawstore.MANIFEST)
    reordered["news_meta"] = reordered.pop("news_meta")
    monkeypatch.setattr(rawstore, "MANIFEST", reordered)












def _changed(value):
    if isinstance(value, dict):
        return {**value, "fingerprint_probe": None}
    if isinstance(value, (list, tuple)):
        return type(value)([*value, "fingerprint_probe"])
    return value + "-probe"


@pytest.mark.parametrize("name", ["_SCHEMA_VERSION", "MANIFEST"])
def test_a_change_to_any_schema_input_moves_the_fingerprint(name, monkeypatch):
    """Each input the copy is checked against; a change to one sends the test to the apply (see the MANIFEST test)."""
    from RevenueChaser.conftest import _schema_fingerprint
    before = _schema_fingerprint()
    monkeypatch.setattr(rawstore, name, _changed(getattr(rawstore, name)))
    assert _schema_fingerprint() != before


# The two tests below run in file order on one worker (--dist loadfile): the first changes its store in every way
# it can, the second must see a store exactly as the apply makes it, and the template must be untouched.


