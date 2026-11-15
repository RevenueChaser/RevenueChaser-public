"""#860 stage 1: the Value Chain package's three tables leave ``edgar.duckdb`` for its own board file.

avo, 14 Nov 2026 23:01 Amsterdam: "edgar.duckdb yi sil, ve ona giden her yolu bir daha olusmasin". The file holds
nine tables, six of which are not Value Chain's, so it goes in stages (#860). This is stage 1: ``chain_filings``,
``chain_mentions`` and ``chain_meta`` are the Value Chain package's own rows, nothing reads them as EDGAR content,
and they move to ``<store>/boards/value_chain.duckdb`` like every other board file. The rows are carried across on
the live store before #860 removed the old files.

The guard that nothing names an old store file again is ``test_no_old_store.py``.
"""
from __future__ import annotations

from RevenueChaser.core import rawstore

_CHAIN_TABLES = ("chain_filings", "chain_mentions", "chain_meta")


def test_the_value_chain_tables_are_a_board_file_and_not_edgar_content():
    assert "value_chain" in rawstore.BOARD_DBS
    for name in _CHAIN_TABLES:
        assert rawstore.MANIFEST[name]["db"] == "value_chain", name
        assert rawstore._db_of(name) == "value_chain", name






def test_the_board_file_is_backed_up_and_schema_stamped():
    # a board file gets the schema stamp and the ``boards`` backup step by being in BOARD_DBS
    assert "value_chain" in rawstore._SCHEMA_FILES
