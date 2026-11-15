"""CUSIP and ISIN on ``security_master`` (#127). Additive columns, no schema bump.

``identity_cusip.current_map`` is keyed by CUSIP. Two present CUSIPs can name one
ticker (the live store was 1:1; the table does not forbid a collision). The tie
is newest ``valid_from``, then lowest CUSIP. No provider call, temp store only.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from RevenueChaser.core import rawstore

RUN_AT = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc).timestamp()
LATER = RUN_AT + 86400
ID_COLS = ("cusip", "isin", "cusip_source", "isin_source")


def _present(ticker):
    return {"status": "present", "ticker": ticker, "figi": "F-1", "share_class_figi": "S-1",
            "share_class": None, "name": ticker, "exch_code": "US", "security_type": "Common Stock",
            "fetched_at": RUN_AT}


def _forget():
    rawstore._TABLE_READY.clear()
    rawstore._ENSURED.clear()




def test_security_master_declares_the_identifier_columns_as_text_and_tracks_them():
    decl = {d.split()[0]: d for d in rawstore.MANIFEST["security_master"]["columns"]}
    for col in ID_COLS:
        assert decl[col] == f"{col} TEXT", col
        assert col in rawstore.CHANGES["security_master"]["track"]
    assert rawstore.schema_version() == "13"   # moved for relatedness v13 (#401), not for these columns


























