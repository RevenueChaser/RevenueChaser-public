"""Rescore only the pairs a changed profile touches (#1132, the incremental half of #884).

A whole-board Refresh used to rescore every pair: about two hours single-threaded on the dashboard for 5,096
profiles (measured 15 Nov 2026, #884 A), for scores the run had just written. Filings land spread over weeks, so
the common case is a handful of changed profiles against an unchanged rest.

The rule this module implements, and the reason it is exact on the embedding path:

* The blended score of a pair (``similarity.Blend``) is built from the two profiles only -- their vectors, their
  customer/supplier sets and their structure fields. No run-wide quantity enters it, so a pair of **unchanged**
  profiles scores exactly what it scored before. (The tag cosine is different: its idf is run-wide, so every pair
  moves when any profile moves. The incremental path is therefore offered on the embedding path alone.)
* A ticker's own top-``top`` list can only move if a changed profile is in it, or wants into it, or if a name it
  listed has left the board. So:
  - **changed** profiles get a full score row;
  - so does every ticker whose stored list names a changed or departed ticker -- that is the trap of the top-25
    cut: when a changed name drops out of *another* name's list, the name ranked just below it takes the slot, and
    only a full row knows which name that is;
  - every other ticker keeps its stored entries (their scores cannot have moved) and is offered the changed
    profiles as candidates: a changed name that now outscores one of its entries enters the list and pushes the
    weakest out. Nothing can leave such a list except by being pushed, so no unknown rank is needed.

With K changed profiles out of n, the rows actually scored are K plus the lists that named one -- about 26K at a
top-25 cut, so 10 changed profiles out of 5,096 score some 260 rows instead of 5,096.

Two things a carried entry keeps rather than earns again, both of them what a whole-board Refresh already did
before this (#884 renders the saved payload as it is when nothing is newer):

* its **market stats** -- the ``move`` correlations, ``beyond_spy`` and the comovement cluster. They are the ones
  the run that scored the pair computed; the weekly ``--score`` step scores the whole board and prices every pair
  again.
* its **rank** in the merge: a saved payload carries the score rounded to 4 decimals (``_payload`` pops the
  unrounded one before it writes), so two peers within 1e-4 of each other -- the same score to the board's own
  display precision -- can swap places against what a full rescore would have ordered.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


def _score(entry: dict) -> float:
    """An entry's score for ranking: the unrounded one when it is still there, else the rounded one a saved payload
    carries (``_payload`` pops ``score_raw`` before it writes)."""
    v = entry.get("score_raw")
    if v is None:
        v = entry.get("score")
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def rows_to_rescore(stored_peers: dict[str, list[dict]], tickers: list[str], changed: set[str],
                    gone: set[str]) -> set[str]:
    """The tickers whose score row must be computed: the changed ones, the ones with no stored list, and every
    ticker whose stored list names a changed or departed name."""
    present = set(tickers)
    moved = (set(changed) | set(gone))
    rows = {t for t in changed if t in present}
    for t in present:
        if t in rows:
            continue
        entries = stored_peers.get(t)
        if entries is None:
            rows.add(t)                                     # never scored: no stored list to carry
            continue
        if any((e or {}).get("peer") in moved for e in entries):
            rows.add(t)
    return rows


def peer_lists(blend, stored_peers: dict[str, list[dict]], rows: set[str], changed: set[str],
               top: int) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """``(peers, fresh)``: the board's peer lists, and the entries that are new in this run.

    ``rows`` is ``rows_to_rescore``'s answer; every ticker in it gets a full score row and a freshly cut list.
    Every other ticker carries its stored entries and is offered the ``changed`` profiles. ``fresh`` holds the same
    entry objects as ``peers``, so attaching the name, the percentile and the market stats to them is enough.
    """
    changed = {t for t in changed if t in blend.index}
    peers: dict[str, list[dict]] = {}
    fresh: dict[str, list[dict]] = {}
    # Only a changed profile's row is kept: it is read again as the (carried ticker, changed ticker) score, which
    # the matrix is symmetric in. The other rescored rows are cut and dropped, so memory stays len(changed) x n.
    changed_rows = {}
    for t in sorted(rows):
        row = blend.row(t)
        peers[t] = fresh[t] = blend.top(t, row, top)
        if t in changed:
            changed_rows[t] = row
    for t in sorted(changed):
        if t not in changed_rows:                           # a changed ticker is always a rescored row
            changed_rows[t] = blend.row(t)

    for focal in blend.tickers:
        if focal in peers:
            continue
        i = blend.index[focal]
        kept = [dict(e) for e in (stored_peers.get(focal) or []) if (e or {}).get("peer")]
        add = []
        for c in sorted(changed):
            if c == focal:
                continue
            s = float(changed_rows[c][i])
            if s > 0:
                add.append(blend.entry(focal, c, s))
        if not add:
            peers[focal] = kept
            continue
        merged = sorted(kept + add, key=lambda e: -_score(e))[:top]
        peers[focal] = merged
        new = [e for e in add if any(e is m for m in merged)]
        if new:
            fresh[focal] = new
    return peers, fresh
