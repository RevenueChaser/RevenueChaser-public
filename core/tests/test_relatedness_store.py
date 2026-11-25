"""Relatedness durable tables (Phase 6 schema) — populate + round-trip.

``relatedness_profiles`` and ``relatedness_attributes`` are retired (#1520): the SEC reading service owns the
profile and the board keeps no copy, so the rows this file used to round-trip through them are gone with them.
"""
from __future__ import annotations

from revenuechaser.core import rawstore


def test_llm_cache(rawstore_tmp_db):
    key = "flash|think0|low|v1|AAPL|abc"
    rawstore.write_rows("llm_cache", [{
        "cache_key": key, "ticker": "AAPL", "cik": "320193",
        "model": "deepseek-v4-flash", "thinking": 0, "effort": "low",
        "prompt_version": "v1", "input_hash": "abc", "response": {"segments": []},
        "fetched_at": 1.0, "status": "ok"}])
    assert rawstore.get("llm_cache", key)["response"] == {"segments": []}


def test_relatedness_scores(rawstore_tmp_db):
    rawstore.replace_all("relatedness_scores", [
        {"ticker": "AAPL", "peer": "MSFT", "score": 0.42}])
    row = rawstore.query(
        "SELECT score FROM relatedness_scores WHERE ticker='AAPL' AND peer='MSFT'", db="relatedness")[0]
    assert row["score"] == 0.42
