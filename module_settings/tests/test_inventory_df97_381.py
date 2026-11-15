"""Settings / Data health: the corpus row's "holes" stops counting recorded misses (#381, DF97).

A ticker whose CIK has no usable annual filing is recorded in ``chain_meta`` as ``miss:<TICKER>``
(``module_value_chain.engine``), so it has no ``chain_filings`` row on purpose. The row's note
already reports those names; the hole count must not count them a second time. Store reads only.
"""
from __future__ import annotations

import json

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.core import rawstore
from RevenueChaser.module_settings import inventory

CHECKED = "2026-10-20T00:00:00+00:00"


def _rows(payload=None) -> dict:
    return {r["key"]: r for r in (payload or inventory.collect())["rows"]}


def _universe(*tickers: str) -> None:
    universe_store.put([{"ticker": t, "market_cap": 1e9, "name": t} for t in tickers])


def _filing(ticker: str, cik: str = "1") -> dict:
    return {"ticker": ticker, "cik": cik, "form": "10-K", "filed": "2026-01-15"}


def _miss(ticker: str, reason: str = "no_filing", cik: str = "2", checked: str = CHECKED) -> dict:
    return {"key": f"miss:{ticker}", "value": json.dumps(
        {"reason": reason, "note": "no 10-K / 20-F", "cik": cik, "checked": checked})}


def test_a_recorded_miss_is_not_a_hole(rawstore_tmp_db):
    """1 filing, 1 recorded miss, 1 never settled -> one hole, and the tooltip states the rule."""
    _universe("AAA", "BBB", "CCC")
    rawstore.write_rows("chain_filings", [_filing("AAA")])
    rawstore.write_rows("chain_meta", [_miss("BBB")])
    row = _rows()["corpus"]
    assert row["holes"] == 1  # CCC; BBB is settled, not missing
    assert row["hole_label"] == "no filing, excluding recorded misses"


def test_a_miss_key_outside_the_universe_changes_nothing(rawstore_tmp_db):
    """A ``miss:`` key survives a universe exit (``corpus_miss_summary``'s docstring), so it is not a hole."""
    _universe("AAA", "BBB")
    rawstore.write_rows("chain_filings", [_filing("AAA")])
    rawstore.write_rows("chain_meta", [_miss("ZZZ")])
    row = _rows()["corpus"]
    assert row["holes"] == 1  # BBB, the only unsettled universe name
    assert "recorded misses" not in row["note"]  # ZZZ is not a universe name, so the note says nothing








def test_the_row_and_its_note_describe_the_same_set(rawstore_tmp_db):
    """DF97: the number and the note under it must not contradict each other."""
    _universe("AAA", "BBB", "CCC", "DDD")
    rawstore.write_rows("chain_filings", [_filing("AAA")])
    rawstore.write_rows("chain_meta", [_miss("BBB"), _miss("CCC", reason="form_40f")])
    row = _rows()["corpus"]
    assert row["holes"] == 1  # DDD, and only DDD
    assert "2 recorded misses (1 no 10-K/20-F, 1 40-F;" in row["note"]
    assert row["holes"] + 2 == 3  # every universe name with no chain_filings row, counted once


