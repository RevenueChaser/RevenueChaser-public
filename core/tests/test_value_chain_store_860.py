"""#860 stage 1: the Value Chain package's three tables leave ``edgar.duckdb`` for its own board file.

avo, 14 Nov 2026 23:01 Amsterdam: "edgar.duckdb yi sil, ve ona giden her yolu bir daha olusmasin". The file holds
nine tables, six of which are not Value Chain's, so it goes in stages (#860). This is stage 1: ``chain_filings``,
``chain_mentions`` and ``chain_meta`` are the Value Chain package's own rows, nothing reads them as EDGAR content,
and they move to ``<store>/boards/value_chain.duckdb`` like every other board file. The rows are carried across on
the live store by ``scripts/migrate_board_store.py value_chain --from edgar``.

The guard that no module can recreate the file is stage 4's, not this test's: six tables still live there.
"""
from __future__ import annotations

from RevenueChaser.core import rawstore

_CHAIN_TABLES = ("chain_filings", "chain_mentions", "chain_meta")


def test_the_value_chain_tables_are_a_board_file_and_not_edgar_content():
    assert "value_chain" in rawstore.BOARD_DBS
    for name in _CHAIN_TABLES:
        assert rawstore.MANIFEST[name]["db"] == "value_chain", name
        assert rawstore._db_of(name) == "value_chain", name


def test_the_three_tables_resolve_to_the_boards_folder(isolate_rawstore):
    want = isolate_rawstore.parent / rawstore.BOARDS_DIRNAME / "value_chain.duckdb"
    assert rawstore.board_db_path("value_chain") == want
    for name in _CHAIN_TABLES:
        assert rawstore._db_path(rawstore._db_of(name)) == want, name
    # and no longer beside the raw store as EDGAR content
    assert want != rawstore.edgar_db_path()


def test_no_chain_table_is_left_in_the_edgar_file():
    left = sorted(n for n, m in rawstore.MANIFEST.items() if m.get("db") == "edgar")
    assert not [n for n in left if n.startswith("chain_")], left
    # stage 2 took edgar_facts and edgar_companyfacts; the rest goes with stages 2b-3 (#860)
    assert set(left) == {"edgar_financials", "edgar_documents", "sec_submissions", "sec_submissions_cik"}


def test_the_board_file_is_backed_up_and_schema_stamped():
    # a board file gets the schema stamp and the ``boards`` backup step by being in BOARD_DBS
    assert "value_chain" in rawstore._SCHEMA_FILES
