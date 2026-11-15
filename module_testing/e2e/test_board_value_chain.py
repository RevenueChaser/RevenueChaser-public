"""Value Chain board, end to end.

The corpus is store-backed. Seeding a filing row for every ``config.SEED`` ticker
means ``fetch_corpus`` finds nothing to fetch, so the POST path never touches
EDGAR and the tests exercise the real job + render + refresh flow offline.
"""
from __future__ import annotations

import re
import time

import pytest

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.module_value_chain import config

_TEXT = (
    "Item 1. Business\n"
    "We purchase wafers from Taiwan Semiconductor Manufacturing Company Limited "
    "(TSMC), our primary foundry supplier. Our customers include Microsoft and "
    "Amazon. We compete with Advanced Micro Devices.\n"
    "Item 1A. Risk Factors\nWe depend on a limited number of suppliers."
)


def _store_file(store_dir, table: str):
    """The store file ``table`` lives in, read from the MANIFEST.

    These tests open the file directly to check what the dashboard process wrote, so they cannot go through
    ``rawstore``'s own routing. Reading the file name off the MANIFEST means a table moving between files
    (#860 stage 1 put the ``chain_*`` tables in ``boards/value_chain.duckdb``) edits this helper, not six paths.
    """
    from RevenueChaser.core import rawstore

    db = rawstore.MANIFEST[table].get("db") or "raw"
    if db in rawstore.BOARD_DBS:
        return store_dir / rawstore.BOARDS_DIRNAME / f"{db}.duckdb"
    return store_dir / f"{db}.duckdb"














class TestEmptyStore:
    def test_a_board_with_no_data_renders_an_empty_state(self, dashboard):
        r = dashboard.view("module_value_chain")
        assert r.status_code == 200
        assert "No companies with supplier / customer edges" in r.text
