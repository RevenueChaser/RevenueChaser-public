"""#289 (data backbone review, finding B15): a MANIFEST table with no writer is marked.

The first store call creates every MANIFEST table, so a table nothing ever writes reads in the store as an
empty table with 0 rows — indistinguishable from a table whose writer broke. Two keys, same shape, both
data like ``history_mode``: rawstore does not read either, so neither changes DDL or a write. They differ
in the word a future listing prints.

- ``"planned": True`` — a writer is still to come.
- ``"retired": True`` — the only writer is in the past.

Nothing renders either flag yet (the Settings inventory lists its own dataset rows, and none of these
tables is among them).

``PLANNED`` and ``RETIRED`` below are the thing to update when a writer lands, or when a retired table
leaves the manifest: drop the name from the set and drop the key from its MANIFEST entry in the same
commit. They are explicit sets, not a grep, because a grep for a table name in the tree cannot tell a
writer from a comment, a doc line or a test.
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import rawstore

# Verified against the production tree on 2026-10-22 (#289), tests / module_testing / conftest.py /
# core/rawstore.py excluded:
#   planned — a writer is still to come
#   catalyst_events      writers arrive with #186-#192 (docs/data_architecture.md, Stage 2)
#   orphan_designations  the OOPD writer is #190's, not in the tree
#   orphan_lookups       the outcome table of that same #190 lookup
#   sec13f_filers        never named in production code; docs/data_architecture.md: G1 (#292), manifest only
#   retired — the only writer is in the past
#   leaps_daily_scores     only scripts/migrate_rawdata_to_duckdb.py, the legacy one-time import
#   sec13f_edgar_backfill  same, and the backfill itself is retired (leaves the manifest at the next bump)
#   sec13f_ticker_names    named only by that same legacy import (scripts/migrate_rawdata_to_duckdb.py)
#   sec_company_tickers    #301 D21: `sec_exchange_file` replaced it; its readers now read the file's rows
# relatedness_embeddings was planned until its writer landed (module_relatedness/embeddings.py, #669).
# NOT marked, though the issue's list named them — each has a writer since: price_bars_daily
# (core/prices.py), forecast_ledger (core/ledger.py) and job_runs (app/jobs.py, core/automations.py).
# migration_manifest is legacy-import-only in that script, but the store writes it itself, so it stays unmarked.
# An empty table is expected for either word. The invariant tests run over this union.


def _marked(key: str) -> set[str]:
    return {name for name, spec in rawstore.MANIFEST.items() if spec.get(key) is True}






def test_planned_is_a_true_flag_and_never_a_half_set_one():
    """One spelling each: ``True`` on the marked entries, the key absent everywhere else. Never a string."""
    bad = {}
    for key in ("planned", "retired"):
        bad.update({f"{name}.{key}": spec[key] for name, spec in rawstore.MANIFEST.items()
                    if key in spec and spec[key] is not True})
    assert not bad, f"planned and retired must be True or absent: {bad}"


# A fresh store's columns, read from information_schema before the flag was added: the flag must not change
# the DDL, so these stay exactly as the create path made them. The three added 2026-10-22 were read the same
# way, off a throwaway store, before their flags existed.


