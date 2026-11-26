"""Durable Relatedness store — the cache key, the profile read, the scores.

The profile round trip went with the board's own writer (#1520): there is no table to write a profile to, so the
read of a service answer is ``test_profiles_from_service.py``.
"""
from __future__ import annotations

import pytest

from revenuechaser.core import rawstore
from revenuechaser.module_relatedness import store
from revenuechaser.module_relatedness.tests import service_fixture


def test_the_cache_key_is_stable_and_normalises_the_ticker():
    k1 = store.cache_key("m", True, "high", "v1", "aapl", "h")
    k2 = store.cache_key("m", True, "high", "v1", "AAPL", "h")
    assert k1 == k2 and store.input_hash(k1) == "h"      # ticker normalised, keys sorted


def test_a_service_answer_reads_as_a_profile(rawstore_tmp_db, monkeypatch):
    """The board's one profile reader, over a row in the shape the service's answer gives it."""
    prof = {"products": ["gpu"], "end_markets": ["data center"], "business_model": [],
            "customer_types": [], "value_chain_role": [], "keywords": ["ai"]}
    service_fixture.seed_profiles(monkeypatch, {"NVDA": prof}, cik="1045810")
    got = store.load_profiles(["NVDA"])
    assert got["NVDA"]["products"] == ["gpu"] and got["NVDA"]["keywords"] == ["ai"]
    assert store.profile_meta(["NVDA"])["NVDA"]["cik"] == "1045810"
    assert store.load_profiles([]) == {} and set(store.load_profiles()) == {"NVDA"}


def test_save_scores(rawstore_tmp_db):
    n = store.save_scores({"NVDA": [{"peer": "AMD", "score": 0.5},
                                    {"peer": "TSM", "score": 0.1}]})
    assert n == 2
    rows = rawstore.query("SELECT peer, score FROM relatedness_scores "
                          "WHERE ticker='NVDA' ORDER BY score DESC", db="relatedness")
    assert [r["peer"] for r in rows] == ["AMD", "TSM"]


def _seed_scores():
    store.save_scores({"NVDA": [{"peer": "AMD", "score": 0.5}]})


def _stored_peers():
    return [r["peer"] for r in rawstore.query("SELECT peer FROM relatedness_scores ORDER BY peer", db="relatedness")]


@pytest.mark.parametrize("peers", [{}, {"NVDA": [], "AMD": []}], ids=["no tickers", "no peers"])
def test_save_scores_empty_batch_keeps_the_last_good_scores_and_says_why(
        rawstore_tmp_db, caplog, peers):
    """A run that scored nothing (cold cache, peak-hours stop) must not wipe the last Fetch (#284)."""
    _seed_scores()
    with caplog.at_level("WARNING"):
        assert store.save_scores(peers) == 0
    assert _stored_peers() == ["AMD"]
    assert any("relatedness_scores" in r.getMessage() and "kept" in r.getMessage()
               for r in caplog.records)


def test_save_scores_empty_batch_on_a_cold_store_is_quiet_noop(rawstore_tmp_db):
    assert store.save_scores({}) == 0
    assert _stored_peers() == []


def test_save_scores_non_empty_batch_still_replaces_the_old_scores(rawstore_tmp_db):
    _seed_scores()
    assert store.save_scores({"TSM": [{"peer": "ASML", "score": 0.2}]}) == 1
    assert _stored_peers() == ["ASML"]
