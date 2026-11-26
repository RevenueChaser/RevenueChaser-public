"""``sec/nport`` refuses to serve far fewer rows than the live ownership file holds (#1544).

``allow_shrink`` on a ``sec/nport`` request relaxes **both** of the dataset's tables, because
``base.shrink_scope`` is ``tables`` plus ``feeds`` and ``Nport.tables`` is ``(etf_holdings_nport,
etf_holdings_nport_history)``. A relaxed table skips ``serving._verify_against_live``'s ``before > 0 and
after == 0`` check and its ``MAX_SHRINK`` check -- that is ``swap``'s own contract, held by
``test_pr220_review_gaps``'s S1, so the shared guard is not the place to fix this. The builder is: four paths
reach 0 rows (no typed quarter, no spine ETF, no CUSIP map, and a CUSIP map that joins nothing), so the refusal
reads the live file rather than a predicate.

Offline: no provider, no swap. The live file is hand-made tables.
"""
from __future__ import annotations

import duckdb
import pytest

from revenuechaser.rcdata import serving
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.ownership import KIND, nport

#: The shape of the live file on 25 Nov 2026, in miniature.
LIVE = {nport.TABLE: 3, nport.HISTORY: 1000}


def _live(rows: dict[str, int], *, tables: tuple[str, ...] | None = None) -> None:
    """A live ``ownership.duckdb`` holding ``rows`` rows of each named table (``tables`` adds empty ones)."""
    path = serving.live_path(KIND)
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        for table in (*rows, *(tables or ())):
            con.execute(f'CREATE TABLE IF NOT EXISTS "{table}" (etf_ticker TEXT)')
        for table, n in rows.items():
            for i in range(n):
                con.execute(f'INSERT INTO "{table}" VALUES (?)', [f"E{i}"])
    finally:
        con.close()


def _ctx(*named: str) -> base.RunContext:
    return base.RunContext(run_id="w1", dataset=nport.NAME, shrink_tables=tuple(named))


# ── 0 rows over a live table ────────────────────────────────────────────────────────────────────────────────────

def test_zero_over_live_rows_is_refused_and_names_both_counts():
    _live(LIVE)
    with pytest.raises(base.SourceError) as caught:
        nport._refuse_shrink(_ctx(), duckdb.connect(), {nport.TABLE: 0, nport.HISTORY: 0})
    said = str(caught.value)
    assert "0 built, 3 live" in said and "0 built, 1,000 live" in said


def test_one_table_at_zero_is_refused_while_the_other_is_served():
    _live(LIVE)
    with pytest.raises(base.SourceError) as caught:
        nport._refuse_shrink(_ctx(), duckdb.connect(), {nport.TABLE: 3, nport.HISTORY: 0})
    said = str(caught.value)
    assert "0 built, 1,000 live" in said and "0 built, 3 live" not in said


def test_a_first_build_with_no_live_file_still_publishes_empty_tables():
    assert not serving.live_path(KIND).exists()
    nport._refuse_shrink(_ctx(), duckdb.connect(), {nport.TABLE: 0, nport.HISTORY: 0})


def test_an_empty_live_table_and_a_served_build_are_both_left_alone():
    _live({}, tables=(nport.TABLE, nport.HISTORY))
    con = duckdb.connect()
    nport._refuse_shrink(_ctx(), con, {nport.TABLE: 0, nport.HISTORY: 0})
    _live(LIVE)
    nport._refuse_shrink(_ctx(), duckdb.connect(), {nport.TABLE: 3, nport.HISTORY: 1000})


def test_a_named_table_may_empty_because_the_request_meant_that_table():
    _live(LIVE)
    nport._refuse_shrink(_ctx(nport.HISTORY), duckdb.connect(), {nport.TABLE: 3, nport.HISTORY: 0})


# ── The history floor: 14,014,752 -> 1 is not a 0 ───────────────────────────────────────────────────────────────

def test_history_past_the_swaps_own_limit_is_refused_although_it_is_not_zero():
    _live(LIVE)
    with pytest.raises(base.SourceError) as caught:
        nport._refuse_shrink(_ctx(), duckdb.connect(), {nport.TABLE: 3, nport.HISTORY: 1})
    assert "1 built, 1,000 live" in str(caught.value)


def test_history_inside_the_limit_is_served():
    _live(LIVE)
    nport._refuse_shrink(_ctx(), duckdb.connect(), {nport.TABLE: 3, nport.HISTORY: 995})


def test_the_newest_quarter_table_may_still_shrink_on_its_own():
    """``etf_holdings_nport`` loses rows legitimately (ownership serving 6: about 1.2% on a long-equity rule), so
    the floor is the history table's alone."""
    _live(LIVE)
    nport._refuse_shrink(_ctx(), duckdb.connect(), {nport.TABLE: 1, nport.HISTORY: 1000})


# ── The catalog must not fail open ──────────────────────────────────────────────────────────────────────────────

def test_a_live_file_whose_tables_cannot_be_listed_is_refused_not_ignored():
    """An empty catalog answer read as "the live file holds neither table" would be the one fail-open that matters
    (Grok xReview round 2 (a))."""
    _live({})
    with pytest.raises(base.SourceError) as caught:
        nport._refuse_shrink(_ctx(), duckdb.connect(), {nport.TABLE: 0, nport.HISTORY: 0})
    assert "could be listed" in str(caught.value)


# ── Through the builder ─────────────────────────────────────────────────────────────────────────────────────────

def test_the_build_refuses_instead_of_returning_zeros(monkeypatch):
    """The branch the finding names: no live spine ETF, so ``build`` would have published two empty tables."""
    _live(LIVE)
    monkeypatch.setattr(nport, "_spine_etfs", lambda: [])
    with pytest.raises(base.SourceError):
        nport.DATASET.build(_ctx(), duckdb.connect())
