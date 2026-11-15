"""Every MANIFEST table declares a history mode (#281); only ``forecast_ledger`` is flagged history (#286).

``history_mode`` is one of five values (data backbone review ADR-1): event, session_snapshot, change_history,
latest_cache, operational. It is a label only. The pins of the old raw/edgar/history tables (the 22 G1 entries of
#292, the schema-11 change and run tables) went with those files (#860); the board tables are what is left.
"""
from __future__ import annotations

from RevenueChaser.core import rawstore

HISTORY_MODES = {"event", "session_snapshot", "change_history", "latest_cache", "operational"}


def test_every_entry_has_one_of_the_five_modes():
    bad = {n: s.get("history_mode") for n, s in rawstore.MANIFEST.items()
           if s.get("history_mode") not in HISTORY_MODES}
    assert not bad, f"entries without a valid history_mode: {bad}"


def test_mode_list_in_rawstore_matches_the_five_values():
    assert set(rawstore.HISTORY_MODES) == HISTORY_MODES


def test_only_the_forecast_ledger_is_flagged_history():
    assert sorted(n for n, s in rawstore.MANIFEST.items() if s.get("history")) == ["forecast_ledger"]
