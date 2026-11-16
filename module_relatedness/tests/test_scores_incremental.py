"""``relatedness_scores`` in ``boards/relatedness.duckdb`` is written incrementally (plan 2026-11-08 §10): the run's
pairs are upserted, only the pairs the run retired are deleted, and an empty run deletes nothing."""
from __future__ import annotations

from RevenueChaser.core import rawstore
from RevenueChaser.module_relatedness import store


def _pairs():
    assert rawstore._db_of("relatedness_scores") == "relatedness"   # read from the board file, not raw.duckdb
    return {(r["ticker"], r["peer"]): r["score"] for r in
            rawstore.query("SELECT ticker, peer, score FROM relatedness_scores", db="relatedness")}


def test_the_scores_live_in_the_relatedness_board_file(rawstore_tmp_db):
    store.save_scores({"AAA": [{"peer": "BBB", "score": 0.5}]})
    assert rawstore._db_of("relatedness_scores") == "relatedness"
    assert rawstore.board_db_path("relatedness").exists()
    assert _pairs() == {("AAA", "BBB"): 0.5}


def test_a_run_upserts_its_pairs_and_deletes_only_the_retired_ones(rawstore_tmp_db):
    store.save_scores({"AAA": [{"peer": "BBB", "score": 0.5}, {"peer": "CCC", "score": 0.4}],
                       "DDD": [{"peer": "EEE", "score": 0.3}]})
    store.save_scores({"AAA": [{"peer": "BBB", "score": 0.6}], "DDD": [{"peer": "EEE", "score": 0.3}]})
    assert _pairs() == {("AAA", "BBB"): 0.6, ("DDD", "EEE"): 0.3}


def test_an_empty_run_deletes_nothing(rawstore_tmp_db):
    store.save_scores({"AAA": [{"peer": "BBB", "score": 0.5}]})
    assert store.save_scores({}) == 0
    assert _pairs() == {("AAA", "BBB"): 0.5}


def _fetch_returns(monkeypatch, peers):
    from RevenueChaser.module_relatedness import engine
    monkeypatch.setattr(engine, "_run", lambda *a, **k: {"n": len(peers), "peers": peers})
    return engine


def test_a_whole_board_fetch_keeps_its_peer_scores(rawstore_tmp_db, monkeypatch):
    """Decision F (avo, 16 Nov 2026): the Fetch's scores replace the stored ones, so the old v3b rows retire."""
    store.save_scores({"OLD": [{"peer": "V3B", "score": 0.1}]})
    engine = _fetch_returns(monkeypatch, {"AAA": [{"peer": "BBB", "score": 0.7}]})
    engine.run(no_fetch=False, provider="evren")
    assert _pairs() == {("AAA", "BBB"): 0.7}


def test_a_sliced_fetch_or_a_refresh_leaves_the_stored_scores(rawstore_tmp_db, monkeypatch, tmp_path):
    store.save_scores({"AAA": [{"peer": "BBB", "score": 0.5}]})
    engine = _fetch_returns(monkeypatch, {"CCC": [{"peer": "DDD", "score": 0.9}]})
    monkeypatch.setattr(engine.config, "RELATEDNESS_JSON", tmp_path / "missing.json")
    engine.run(no_fetch=False, tickers=["CCC"], provider="evren")
    engine.run(no_fetch=False, limit=1, provider="evren")
    engine.run(no_fetch=True)
    assert _pairs() == {("AAA", "BBB"): 0.5}
