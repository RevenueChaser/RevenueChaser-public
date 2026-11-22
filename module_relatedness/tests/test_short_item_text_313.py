"""#313: a filing text under Value Chain's ``MIN_ITEM_CHARS`` is never sent to the profile writer.

20 of the pilot's 1,503 names carry an empty Item 1 and 58 carry one under 2,000 characters (live store,
2026-10-30); a model asked from a 1-character description invents the profile. The guard refuses the call,
marks the name ``short_text`` (``no_text`` stays for an empty one), keeps a usable profile it already has,
and counts both apart from Pending.

Offline, temp store; no LLM and no SEC call (``profile_for`` is replaced).
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.core import rawstore
from revenuechaser.module_relatedness import config, engine, report, store
from revenuechaser.module_relatedness.tests.test_relatedness import _prof

TICKERS = ["AAA", "BBB"]
LONG = "We design gpu accelerators for data center customers. " * 60      # >= MIN_INPUT_CHARS


def _seed_filings(texts: dict[str, str]) -> None:
    rawstore.write_rows("chain_filings", [
        {"ticker": t, "cik": "", "form": "10-K", "filed": "2026-01-01", "accession": "a-" + t,
         "primary_doc": "u", "item_text": text, "quality": "ok", "fetched_at": 1.0}
        for t, text in texts.items()])




def test_the_floor_is_value_chains_own():
    from revenuechaser.module_value_chain import config as vc_config
    assert config.MIN_INPUT_CHARS == vc_config.MIN_ITEM_CHARS == 2000










# ── the status tile and the run's history ───────────────────────────────────






