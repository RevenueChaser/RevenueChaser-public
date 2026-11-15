"""#388 D5 (REL-3 + REL-5, DF61): a profile is redone when its input changes, the prompt names the company, and the
prompt is v2.

- **Input hash:** a stored profile carries the hash of the exact prompt it was made from (``cache_key.input_hash``).
  ``build_profiles`` re-profiles a group whose filing text (or company name) changed since, and leaves one whose
  input is the same alone. Before D5 a usable profile in the current mode was never redone, whatever the filing said.
- **Company name:** the prompt says ``Company: <the spine's name>``; it used to say the ticker
  (``chain_filings`` has no name column, so ``_filing_text`` fell back to it).
- **v2:** ``PROMPT_VERSION`` moves to "v2", so every v1 profile reads stale (kept and badged until redone).

Offline, temp store: ``profile_for`` / ``deepseek.complete`` are fakes, nothing reaches DeepSeek or SEC.
"""
from __future__ import annotations

import json

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_relatedness.tests.test_relatedness import v3_reply
from RevenueChaser.core.providers import deepseek
from RevenueChaser.module_relatedness import config, engine, store
from RevenueChaser.module_relatedness.tests.test_relatedness import _prof, long_body
from RevenueChaser.rcdata.tests import spine_fixture

TICKERS = ["AAA", "BBB", "CCC"]


def _seed_filings(texts: dict[str, str]) -> None:
    rawstore.write_rows("chain_filings", [
        {"ticker": t, "cik": "", "form": "10-K", "filed": "2026-01-01", "accession": "a-" + t,
         "primary_doc": "u", "item_text": long_body(text), "quality": "ok", "fetched_at": 1.0}
        for t, text in texts.items()])




def test_the_prompt_is_v3():
    assert config.PROMPT_VERSION == "v3d" and store.PROMPT_VERSION == "v3d"   # #841 (v3c #717, v3b #400, v2 #388 D5)


















def test_input_hash_reads_the_stored_key():
    ck = store.cache_key("m", True, "high", "v2", "AAA", "abc")
    assert store.input_hash(ck) == "abc"
    assert store.input_hash(json.loads(ck)) == "abc"                  # rawstore decodes JSON text on read
    assert store.input_hash("") is None and store.input_hash("not json") is None
