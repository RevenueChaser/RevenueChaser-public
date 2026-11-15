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
















# ── equity_universe.next_earnings_date (#265): an added column, no schema bump ────────────────
def _forget_reconciliation():
    # A second ensure in the same process is a no-op unless the memos are reset.
    rawstore._TABLE_READY.clear()
    rawstore._ENSURED.clear()














# ── security_master FIGI columns (#267): added columns, no schema bump ────────────────────────
_FIGI_COLS = ("figi", "composite_figi", "share_class_figi", "exch_code", "security_description", "figi_source")












# ── security_master raw SIC group (#272, schema v9) ───────────────────────────────────────────
_SIC_COLS = ("sic", "sic_description", "sic_group2", "sic_source")










