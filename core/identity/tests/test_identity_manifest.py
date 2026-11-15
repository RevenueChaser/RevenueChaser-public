"""Part 1 of the identity master: the four store tables exist with typed columns."""
from __future__ import annotations

import pytest

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.core import rawstore



def test_the_schema_version_pin_is_explicit():
    """The label is pinned to a literal, so a bump is a deliberate act and not a side effect of a new table.

    12: the (accession, line_no) key on ``sec13f_holdings`` (#208). 13: ``relatedness_profiles.profile_json`` /
    ``label_source`` and the ``relatedness_embeddings`` table (#401). Bump the pin, the doc and the checkpoint
    warning together.
    """
    assert rawstore.schema_version() == "13"




def test_security_master_columns():
    cols = rawstore._columns_of(rawstore.MANIFEST["security_master"])
    for c in ("ticker", "cik", "cik_source", "exchange", "name", "name_source",
              "security_type", "type_source", "type_asof", "sector", "sector_source",
              "industry_group", "group_source", "industry", "industry_source",
              "sub_industry", "sub_source", "gics_asof", "updated_at",
              "figi", "composite_figi", "share_class_figi", "exch_code", "security_description", "figi_source",
              "sic", "sic_description", "sic_group2", "sic_source",
              "cusip", "isin", "cusip_source", "isin_source"):
        assert c in cols, c
    assert len(cols) == 33












# ── equity_universe.next_earnings_date (#265): an added column, no schema bump ────────────────
def _forget_reconciliation():
    # A second ensure in the same process is a no-op unless the memos are reset.
    rawstore._TABLE_READY.clear()
    rawstore._ENSURED.clear()






def test_equity_universe_declares_the_earnings_date_as_text():
    decl = {d.split()[0]: d for d in rawstore.MANIFEST["equity_universe"]["columns"]}
    assert decl["next_earnings_date"] == "next_earnings_date TEXT"








# ── security_master FIGI columns (#267): added columns, no schema bump ────────────────────────
_FIGI_COLS = ("figi", "composite_figi", "share_class_figi", "exch_code", "security_description", "figi_source")






def test_security_master_declares_the_figi_columns_as_text():
    decl = {d.split()[0]: d for d in rawstore.MANIFEST["security_master"]["columns"]}
    for c in _FIGI_COLS:
        assert decl[c] == f"{c} TEXT", c






# ── security_master raw SIC group (#272, schema v9) ───────────────────────────────────────────
_SIC_COLS = ("sic", "sic_description", "sic_group2", "sic_source")




def test_security_master_declares_the_sic_columns_as_text():
    decl = {d.split()[0]: d for d in rawstore.MANIFEST["security_master"]["columns"]}
    for c in _SIC_COLS:
        assert decl[c] == f"{c} TEXT", c






