"""#1132: a Refresh scores only the pairs a changed profile touches, and lands where a full rescore would.

No model, no network: the scores come from vectors handed straight to ``similarity.Blend``, and the engine wiring
is checked at its own boundary.
"""
from __future__ import annotations

import numpy as np
import pytest

from revenuechaser.module_relatedness import config, engine, incremental, similarity, store
from revenuechaser.module_relatedness.tests.test_relatedness import _prof

TOP = 5


def _board(n: int, seed: int, dim: int = 6) -> tuple[dict, dict]:
    """``(profiles, vectors)`` for ``n`` tickers: unit vectors, one weak shared tag so the evidence fields fill."""
    rng = np.random.default_rng(seed)
    tickers = [f"T{i:02d}" for i in range(n)]
    profiles = {t: _prof(products=["x", t.lower()], keywords=["y"]) for t in tickers}
    vectors = {}
    for t in tickers:
        v = rng.random(dim).astype("float32")
        vectors[t] = v / np.linalg.norm(v)
    return profiles, vectors


def _full(profiles, vectors, top=TOP):
    peers, scores = similarity.blended_peer_lists(profiles, {}, vectors, None, top=top)
    return peers, scores


def _as_saved(peers) -> dict:
    """The peer lists as a saved payload carries them: ``score_raw`` popped, a name and a percentile attached."""
    return {t: [{k: v for k, v in e.items() if k != "score_raw"} | {"name": e["peer"], "percentile": 50.0}
                for e in entries] for t, entries in peers.items()}


def _order(peers) -> dict:
    return {t: [e["peer"] for e in entries] for t, entries in peers.items()}


def _scores(peers) -> dict:
    return {t: [e["score"] for e in entries] for t, entries in peers.items()}


# ── which rows a run has to score ───────────────────────────────────────────
def test_the_rows_scored_are_the_changed_names_and_every_list_that_named_one():
    stored = {"A": [{"peer": "B"}], "B": [{"peer": "C"}], "C": [{"peer": "D"}], "D": [{"peer": "A"}]}
    rows = incremental.rows_to_rescore(stored, ["A", "B", "C", "D"], {"C"}, set())
    assert rows == {"C", "B"}                       # C changed; B listed C; A and D keep their lists


def test_a_ticker_with_no_stored_list_gets_a_row():
    stored = {"A": [{"peer": "B"}]}
    assert incremental.rows_to_rescore(stored, ["A", "B"], set(), set()) == {"B"}


def test_a_name_that_left_the_board_sends_its_listers_back_through_a_row():
    stored = {"A": [{"peer": "GONE"}], "B": [{"peer": "A"}]}
    assert incremental.rows_to_rescore(stored, ["A", "B"], set(), {"GONE"}) == {"A"}


def test_a_changed_name_is_a_row_even_when_nothing_listed_it():
    assert incremental.rows_to_rescore({"A": [], "B": []}, ["A", "B"], {"A"}, set()) == {"A"}


# ── the lists it produces are the lists a full rescore produces ─────────────
@pytest.mark.parametrize("seed", [1, 2, 3])
def test_the_incremental_lists_equal_a_full_rescore(seed):
    profiles, vectors = _board(40, seed)
    before, _ = _full(profiles, vectors)
    stored = _as_saved(before)

    changed = {"T03", "T17"}
    rng = np.random.default_rng(seed + 100)
    for t in changed:                                # the two companies now look like something else entirely
        v = rng.random(6).astype("float32")
        vectors[t] = v / np.linalg.norm(v)

    after, _ = _full(profiles, vectors)
    blend = similarity.Blend(profiles, {}, vectors, None)
    rows = incremental.rows_to_rescore(stored, blend.tickers, changed, set())
    got, fresh = incremental.peer_lists(blend, stored, rows, changed, TOP)

    # The peers and their scores are the full rescore's. The order is compared as a set per focal, because a
    # carried entry ranks by the 4-decimal score a saved payload carries: two peers that close can swap places.
    assert {t: sorted(e["peer"] for e in es) for t, es in got.items()} == \
           {t: sorted(e["peer"] for e in es) for t, es in after.items()}
    assert {t: sorted(_scores(got)[t]) for t in got} == {t: sorted(_scores(after)[t]) for t in after}
    assert len(rows) < len(blend.tickers)            # the point of the exercise
    assert set(fresh) <= set(got)


def test_a_name_whose_own_profile_did_not_change_still_moves_when_a_changed_name_leaves_its_list():
    """The top-cut trap: the name ranked just below the one that left takes the slot."""
    tickers = ["AAA", "BBB", "CCC", "DDD"]
    profiles = {t: _prof(products=["x"]) for t in tickers}
    # AAA's list at top=2 is [BBB, CCC]; DDD is third. BBB then moves away and DDD must take its place.
    vectors = {"AAA": np.asarray([1.0, 0.0], "float32"), "BBB": np.asarray([0.95, 0.312], "float32"),
               "CCC": np.asarray([0.9, 0.436], "float32"), "DDD": np.asarray([0.8, 0.6], "float32")}
    before, _ = _full(profiles, vectors, top=2)
    assert [e["peer"] for e in before["AAA"]] == ["BBB", "CCC"]

    vectors["BBB"] = np.asarray([0.0, 1.0], "float32")
    blend = similarity.Blend(profiles, {}, vectors, None)
    stored = _as_saved(before)
    rows = incremental.rows_to_rescore(stored, tickers, {"BBB"}, set())
    got, _fresh = incremental.peer_lists(blend, stored, rows, {"BBB"}, 2)
    assert [e["peer"] for e in got["AAA"]] == ["CCC", "DDD"]
    expected = _full(profiles, vectors, top=2)[0]["AAA"]
    assert _scores({"AAA": got["AAA"]}) == _scores({"AAA": expected})


def test_a_changed_name_enters_a_list_that_never_held_it_and_pushes_the_weakest_out():
    tickers = ["AAA", "BBB", "CCC", "DDD"]
    profiles = {t: _prof(products=["x"]) for t in tickers}
    vectors = {"AAA": np.asarray([1.0, 0.0], "float32"), "BBB": np.asarray([0.95, 0.312], "float32"),
               "CCC": np.asarray([0.9, 0.436], "float32"), "DDD": np.asarray([0.0, 1.0], "float32")}
    before, _ = _full(profiles, vectors, top=2)
    assert [e["peer"] for e in before["AAA"]] == ["BBB", "CCC"]

    vectors["DDD"] = np.asarray([0.99, 0.141], "float32")       # DDD is now AAA's closest peer
    blend = similarity.Blend(profiles, {}, vectors, None)
    stored = _as_saved(before)
    rows = incremental.rows_to_rescore(stored, tickers, {"DDD"}, set())
    assert rows == {"DDD"}                                      # no stored list named DDD
    got, fresh = incremental.peer_lists(blend, stored, rows, {"DDD"}, 2)
    assert [e["peer"] for e in got["AAA"]] == ["DDD", "BBB"]
    assert [e["peer"] for e in fresh["AAA"]] == ["DDD"]          # only the new entry is this run's


def test_only_the_touched_rows_are_scored():
    profiles, vectors = _board(40, 11)
    before, _ = _full(profiles, vectors)
    stored = _as_saved(before)
    blend = similarity.Blend(profiles, {}, vectors, None)
    scored_rows = []
    real_block = blend.block

    def counting(rows):
        rows = list(rows)
        scored_rows.extend(rows)
        return real_block(rows)

    blend.block = counting
    rows = incremental.rows_to_rescore(stored, blend.tickers, {"T03"}, set())
    incremental.peer_lists(blend, stored, rows, {"T03"}, TOP)
    assert len(set(scored_rows)) == len(rows) < 40      # one row each, and fewer rows than the matrix


def test_an_unchanged_board_scores_no_row_at_all():
    profiles, vectors = _board(12, 5)
    before, _ = _full(profiles, vectors)
    blend = similarity.Blend(profiles, {}, vectors, None)
    stored = _as_saved(before)
    rows = incremental.rows_to_rescore(stored, blend.tickers, set(), set())
    assert rows == set()
    got, fresh = incremental.peer_lists(blend, stored, rows, set(), TOP)
    assert _order(got) == _order(before) and fresh == {}


# ── the full matrix stays the fallback ──────────────────────────────────────
def test_the_blended_rows_equal_the_rows_of_the_full_matrix():
    profiles, vectors = _board(20, 4)
    peers, _ = _full(profiles, vectors)
    blend = similarity.Blend(profiles, {}, vectors, None)
    def shape(entries):
        return [(e["peer"], e["score"], e["n_shared"]) for e in entries]
    for t in ("T00", "T07", "T19"):
        assert shape(blend.top(t, blend.row(t), TOP)) == shape(peers[t])


def test_above_the_share_cap_the_whole_matrix_is_scored(monkeypatch):
    profiles, vectors = _board(10, 6)
    before, _ = _full(profiles, vectors)
    reuse = {"as_of": "2026-11-19T00:00:00+00:00", "companies": [{"ticker": t} for t in profiles],
             "peers": _as_saved(before), "score_quantiles": [0.0, 1.0], "similarity": "embedding"}
    monkeypatch.setattr(engine, "_changed_since", lambda *a: (set(list(profiles)[:5]), set()))
    monkeypatch.setattr(config, "INCREMENTAL_MAX_SHARE", 0.2)
    assert engine._incremental_peers(profiles, {}, vectors, {}, reuse) is None


def test_an_unreadable_payload_date_scores_the_whole_matrix():
    profiles, vectors = _board(4, 7)
    reuse = {"as_of": "not a date", "companies": [], "peers": {}}
    assert engine._incremental_peers(profiles, {}, vectors, {}, reuse) is None


@pytest.mark.parametrize("missing", ["score_quantiles", "similarity", "peers"])
def test_a_payload_without_a_score_grid_or_from_the_tag_cosine_is_no_base(monkeypatch, missing):
    base = {"as_of": "2026-11-19T00:00:00+00:00", "companies": [{"ticker": "AAA"}], "peers": {"AAA": []},
            "score_quantiles": [0.1, 0.2], "similarity": "embedding"}
    monkeypatch.setattr(engine, "load_payload", lambda: base)
    assert engine._incremental_base() == base
    monkeypatch.setattr(engine, "load_payload", lambda: {k: v for k, v in base.items() if k != missing})
    assert engine._incremental_base() is None


# ── the engine wiring ───────────────────────────────────────────────────────
def test_a_whole_board_refresh_scores_against_the_saved_payload(monkeypatch):
    seen = {}
    monkeypatch.setattr(engine, "_reusable_payload", lambda *a: None)
    monkeypatch.setattr(engine, "_incremental_base", lambda: {"as_of": "base"})
    monkeypatch.setattr(engine, "_run", lambda *a, **kw: seen.update(kw) or {"n": 0})
    engine.run(no_fetch=True)
    assert seen["reuse"] == {"as_of": "base"}


@pytest.mark.parametrize("kw", [{"no_fetch": False}, {"no_fetch": True, "tickers": ["AAPL"]},
                                {"no_fetch": True, "limit": 3}])
def test_a_fetch_or_a_sliced_refresh_scores_the_whole_matrix(monkeypatch, kw):
    seen = {}
    monkeypatch.setattr(engine, "_reusable_payload", lambda *a: None)
    monkeypatch.setattr(engine, "_incremental_base", lambda: {"as_of": "base"})
    monkeypatch.setattr(engine, "_run", lambda *a, **kw2: seen.update(kw2) or {"n": 0})
    monkeypatch.setattr(store, "save_scores", lambda peers: 0)
    engine.run(**kw)
    assert seen.get("reuse") is None


def test_the_weekly_scoring_scores_the_whole_matrix(monkeypatch):
    seen = {}
    monkeypatch.setattr(engine, "_reusable_payload", lambda *a: None)
    monkeypatch.setattr(engine, "_run", lambda *a, **kw: seen.update(kw) or {"peers": {}})
    monkeypatch.setattr(store, "save_scores", lambda peers: 0)
    engine.score(only_if_new=False)
    assert seen.get("reuse") is None and seen["write"] is True


# ── the score grid the percentile is read off ───────────────────────────────
def test_the_score_grid_samples_the_sorted_scores_and_keeps_their_order():
    arr = np.sort(np.random.default_rng(3).random(50_000).astype("float32"))
    grid = engine._score_grid(arr)
    assert len(grid) == config.SCORE_QUANTILES
    assert grid == sorted(grid)
    assert grid[0] == pytest.approx(float(arr[0]), abs=1e-6)
    assert grid[-1] == pytest.approx(float(arr[-1]), abs=1e-6)
    # The grid ranks a score where the full array ranks it, to within its own resolution.
    for x in (0.1, 0.5, 0.9):
        full = 100.0 * float(np.searchsorted(arr, x)) / len(arr)
        from_grid = 100.0 * float(np.searchsorted(np.asarray(grid), x)) / len(grid)
        assert abs(full - from_grid) < 0.2


def test_a_short_run_s_grid_is_no_longer_than_its_scores():
    assert engine._score_grid(np.asarray([0.1, 0.2, 0.3], dtype="float32")) == [0.1, 0.2, 0.3]
    assert engine._score_grid(np.zeros(0)) == []
