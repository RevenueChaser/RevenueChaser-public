"""The Sector Rotation board's one reader of its own store: every SELECT against
``boards/sector_rotation.duckdb`` lives here (#217).

#217 (F12, the 27 Oct 2026 architecture review) is not about SQL being slow or wrong. It is about *where* it is
written: a board whose logic files each carry their own table name and their own ``SELECT`` makes a table rename, a
column rename or a new filter a change to every one of those files, and nothing tells the reader which files those
are. The decision (D4) was a read API that carries provenance, with a strangler migration board by board.

This is the last board block of that migration, after News (PR #1195), Relatedness (PR #1269), Co-movement
(PR #1280) and Welcome (PR #1281). Measured on ``main``: the store was read by **5** places — 3 in ``store.py``,
1 in ``etf_holdings.py`` and **1 in ``core/provenance.py``**, which is the read this step is for. A ``core``
module holding a board's SQL is exactly the shape the News step's bug had: ``core/provenance._news_day()``
queried ``news_calendar``, a table that has never existed, and because ``rawstore.query`` swallows
``CatalogException`` on a read the board's data date had been blank for ever, with nothing failing. The date a
board shows comes from its own tables, so the read belongs to the board.

The shape is the earlier steps': one module per board, thin functions named after the need, no connection kept
and no provider call. The writes stay with the code that produces the rows — a write is not a query — but they
take their table names from here, so a rename is still one file. Nothing here raises on an empty store: a missing
table reads as no rows, which is also why a read of a *wrong* name fails silently.

The two tables (``core/rawstore.py`` owns their columns, ``docs/data_architecture.md`` the contract):

- ``rotation_snapshots`` one row per ``(as_of_date, ticker)``: an ETF's relative-strength numbers on that
  session, its quadrant, the benchmark they were measured against, and whether the row came from a live Fetch or
  a backfill (#374).
- ``rotation_holdings`` one row per ETF, its holdings as a JSON payload with the session they were read for
  (``latest_cache``: only the newest read is kept).
"""
from __future__ import annotations

from datetime import date

from RevenueChaser.core import rawstore

#: The board's DuckDB file, as ``rawstore`` names it.
DB = "sector_rotation"

#: The two table names. Every reader here, the board's writes and the data-date resolver take them from this
#: module, so a rename is a change to one file (the point of #217).
SNAPSHOTS = "rotation_snapshots"
HOLDINGS = "rotation_holdings"

#: The read order of a session's rows. The board renders them in it, and a snapshot is compared row by row with
#: another session's, so the order is part of the answer rather than a nicety.
ROW_ORDER = "ticker"


def _query(sql: str, params: list | None = None) -> list[dict]:
    """One place where this board's file is read."""
    return rawstore.query(sql, params, db=DB)


def snapshot_rows(as_of: date) -> list[dict]:
    """One session's ETF rows, by ticker. ``SELECT *`` on purpose: a store that predates a column still loads."""
    return _query(f"SELECT * FROM {SNAPSHOTS} WHERE as_of_date = ? ORDER BY {ROW_ORDER}", [as_of.isoformat()])


def snapshot_dates() -> list[str]:
    """Every stored session, oldest first — the dates the board offers to look at."""
    return [r["d"] for r in _query(f"SELECT DISTINCT as_of_date AS d FROM {SNAPSHOTS} ORDER BY d")]


def snapshot_rows_between(start: date, end: date) -> list[dict]:
    """Every stored row from ``start`` to ``end`` inclusive, by session then ticker.

    Both ends are inclusive: the range the board draws includes the session it is centred on.
    """
    return _query(
        f"SELECT * FROM {SNAPSHOTS} WHERE as_of_date >= ? AND as_of_date <= ? ORDER BY as_of_date, {ROW_ORDER}",
        [start.isoformat(), end.isoformat()])


def newest_snapshot_date() -> str | None:
    """The newest stored session, or ``None`` — the board's **data date**.

    It is this board's own rows that answer it, which is why the read lives here and not in
    ``core/provenance.py``: a resolver written next to another board's tables cannot be checked against them, and
    a wrong table name there reads as "no date" instead of failing.
    """
    rows = _query(f"SELECT max(as_of_date) AS v FROM {SNAPSHOTS}")
    return rows[0]["v"] if rows else None


def etfs_with_holdings() -> set[str]:
    """The ETFs whose stored holdings payload actually has lines.

    A row with ``rows`` NULL or an empty array is a read that answered nothing; counting it would tell the
    Settings card that an ETF is stored when the board has no holdings for it.
    """
    return {r["ticker"] for r in
            _query(f"SELECT ticker FROM {HOLDINGS} WHERE rows IS NOT NULL AND json_array_length(rows) > 0")}
