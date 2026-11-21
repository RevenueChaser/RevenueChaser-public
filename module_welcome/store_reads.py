"""The Welcome board's one reader of its own store: every SELECT against ``boards/welcome.duckdb`` lives here
(#217).

#217 (F12, the 27 Oct 2026 architecture review) is not about SQL being slow or wrong. It is about *where* it is
written: a board whose logic files each carry their own table name and their own ``SELECT`` makes a table rename, a
column rename or a new filter a change to every one of those files, and nothing tells the reader which files those
are. The decision (D4) was a read API that carries provenance, with a strangler migration board by board.

This is the Welcome board's step, after News (PR #1195), Relatedness (PR #1269) and Co-movement (PR #1280).
Measured on ``main`` at ``226f0580``: the store was read by **5** places — 3 in ``report.py`` and 2 in
``build.py``. The four table names already sat in one module (``build.py``), which is half of what #217 asks; what
was still spread was the SQL, and with it two pairs of reads of the same table that have to agree:

- the snapshot tile and the build's own "what do I already hold" read both take the newest row per series, with
  the same ``QUALIFY row_number() OVER (PARTITION BY series ORDER BY session_date DESC) = 1``;
- the earnings card and the build's held-rows read both cut the two days, the card additionally hiding a retired
  row. A card that forgets ``retired_at IS NULL`` shows names the screener has dropped, which is the bug this seam
  makes impossible to write twice.

The board's own file is the only store read here. The Welcome page also reads the News board's file, and it does
that through *its* reader (``module_news.store_reads``), never with SQL of its own; the market tiles, the earnings
names and the builder-file rows come from the serving layer through the package's ``READS`` needs, which is not a
board file at all.

The writes stay with the build that produces the rows — a write is not a query — but they take their table names
from here, so a rename is still one file. Nothing here fetches, and nothing here raises on an empty store: a
missing table reads as no rows (``rawstore.query`` swallows ``CatalogException`` on a read).

The four tables (``core/rawstore.py`` owns their columns, ``docs/data_architecture.md`` the contract):

- ``welcome_snapshot`` one row per ``(series, session_date)``: the stored close, its change against the session
  before, and the 20-session line the tile draws.
- ``welcome_earnings`` the names reporting today and on the next trading day, one row per
  ``(earnings_date, ticker, report_session)``; a name the newest built session no longer lists carries
  ``retired_at`` and is never deleted.
- ``welcome_freshness`` one row per builder file (avo's D2 of 10 Nov 2026): its last finished run, the last that
  ended well and the last that failed.
- ``welcome_meta`` the table the plan designed for an incremental mark. **Nothing writes it** (#643): the build
  compares the rows it already holds instead, which converges where a drifted mark never would. It is named here
  so a reader of the manifest finds the explanation and a test can hold that no build writes it.
"""
from __future__ import annotations

from RevenueChaser.core import rawstore

#: The board's DuckDB file, as ``rawstore`` names it.
DB = "welcome"

#: The four table names. Every reader here, the build's writes and ``report.py`` take them from this module, so a
#: rename is a change to one file (the point of #217).
SNAPSHOT = "welcome_snapshot"
EARNINGS = "welcome_earnings"
FRESHNESS = "welcome_freshness"
META = "welcome_meta"

#: The newest stored session of each series. The table keeps one row per ``(series, session_date)`` — every
#: session the build has ever written — so "the current close" is a window over the series, not a ``LIMIT 1``.
_NEWEST_PER_SERIES = "QUALIFY row_number() OVER (PARTITION BY series ORDER BY session_date DESC) = 1"


def _query(sql: str, params: list | None = None) -> list[dict]:
    """One place where this board's file is read."""
    return rawstore.query(sql, params, db=DB)


def latest_snapshot_rows() -> list[dict]:
    """The newest stored row of each series, every column (the change, the percentage and the spark line).

    ``SELECT *`` on purpose: a store that predates a column still loads, the value simply absent.
    """
    return _query(f"SELECT * FROM {SNAPSHOT} {_NEWEST_PER_SERIES}")


def latest_snapshot_by_series() -> dict[str, dict]:
    """:func:`latest_snapshot_rows` keyed by series, which is how the card reads it."""
    return {r["series"]: r for r in latest_snapshot_rows()}


def stored_snapshot_closes() -> dict[str, tuple]:
    """``{series: (session_date, close)}`` of the newest stored row — what the build compares its observations
    against, so that it writes only a newer session or a corrected close.

    The same cut as :func:`latest_snapshot_rows`, which is why both live here: a build that read "newest" one way
    and a card that read it another would disagree about which close is current.
    """
    return {r["series"]: (r["session_date"], r["close"])
            for r in _query(f"SELECT series, session_date, close FROM {SNAPSHOT} {_NEWEST_PER_SERIES}")}


def earnings_rows(days) -> list[dict]:
    """Every stored row of the two days, retired ones included: what the build already holds."""
    return _query(f"SELECT * FROM {EARNINGS} WHERE earnings_date IN (?, ?)", [days[0], days[1]])


def earnings_held(days) -> dict[tuple, dict]:
    """:func:`earnings_rows` keyed by ``(earnings_date, ticker, report_session)``, the table's own key."""
    return {(r["earnings_date"], r["ticker"], r["report_session"]): r for r in earnings_rows(days)}


def listed_earnings_rows(days) -> list[dict]:
    """The rows of the two days a card may show: the retired ones are left out.

    A retired row is a name the newest built session no longer lists. It stays in the store on purpose (nothing
    about this board deletes), so the filter is the card's correctness, not a tidiness: without it the card shows
    companies that are no longer reporting.
    """
    return _query(f"SELECT * FROM {EARNINGS} WHERE earnings_date IN (?, ?) AND retired_at IS NULL",
                  [days[0], days[1]])


def freshness_rows() -> list[dict]:
    """One row per builder file, unfiltered: the card decides which files it labels and what counts as quiet."""
    return _query(f"SELECT * FROM {FRESHNESS}")
