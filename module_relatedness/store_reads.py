"""The Relatedness board's one reader of its own store: every SELECT against ``boards/relatedness.duckdb``
lives here (#217).

#217 (F12, the 27 Oct 2026 architecture review) is not about SQL being slow or wrong. It is about *where* it is
written: a board whose logic files each carry their own table name and their own ``SELECT`` makes a table rename, a
column rename or a new filter a change to every one of those files, and nothing tells the reader which files those
are. The decision (D4) was a read API that carries provenance, with a strangler migration board by board.

This is the Relatedness board's step of that migration, the second after the News board (PR #1195, which took the
largest block). Measured on ``main`` at ``b523bbd``: the Relatedness store was read by **15** places —
10 in the board itself (``themes.py`` 7, ``naming.py`` 1, ``compare.py`` 1, ``engine.py`` 1), 2 in
``module_sector_rotation/theme_focus.py`` and 3 in ``core/universe.py`` — and its eleven table names were spelled
in string literals about seventy times across six modules of the board. The three reads furthest from the board
were the ones nobody could check, and two of them turned out to be copies (see :func:`pinned_run_id` and
:func:`catalog_rows`).

The shape is the News board's (``module_news/store_reads.py``): one module per board, thin functions named after
the need, no connection kept and no provider call. The writes stay with the code that produces the rows — a write
is not a query — but they take their table names from here, so a rename is still one file. Nothing here fetches,
and nothing here raises on an empty store: a missing table reads as no rows (``rawstore.query`` swallows
``CatalogException`` on a read), which is also why a read of a *wrong* name fails silently and why the SQL belongs
next to the tables it names.

A reader that the boards' filters call keeps its caller's lenience: ``core.universe`` wraps its three calls in
``try`` because a filter must never break a board. That stays with the caller — only one read here is strict by
contract (:func:`pinned_run_id`), because the guards that refuse to rebuild or prune the current run must not read
a failure as "no current run".

The nine tables (``core/rawstore.py`` owns their columns, ``docs/data_architecture.md`` the contract). It was
eleven until #1520: ``relatedness_profiles`` and ``relatedness_attributes`` were the board's own profile writer's,
and the profile is the SEC reading service's answer now (#894 step 3b), read where it is and copied nowhere.

- ``relatedness_embeddings`` one row per ticker: the profile's vector, as bytes.
- ``relatedness_scores`` the board's peer rows.
- ``theme_runs`` one row per theme run; exactly one carries ``is_current = 1`` (the pinned run).
- ``relatedness_themes`` one row per theme of a run, at the three levels, linked by ``parent_id``.
- ``relatedness_theme_tags`` a theme's representative tags, ``rank`` ordered.
- ``relatedness_theme_members`` a fine theme's tickers, ``rank`` being the member's place in the
  cap-descending universe (#298).
- ``relatedness_theme_etfs`` the ETFs a theme overlaps, ``rank`` ordered (Sector Rotation reads them).
- ``ticker_themes`` the *cut over* run, materialised one row per ``(ticker, level)``: what the other boards read.
- ``llm_cache`` the shared model-answer cache, which this store happens to hold.

A run's rows carry no ``run_id`` column: a theme id is either the run id itself or ``<run_id>:<...>``, so every
read of "the rows of this run" is the prefix filter :func:`run_rows` writes once.
"""
from __future__ import annotations

from revenuechaser.core import rawstore

#: The board's DuckDB file, as ``rawstore`` names it.
DB = "relatedness"

#: The nine table names. Every reader here, every writer in the board and every caller outside it takes them
#: from this module, so a rename is a change to one file (the point of #217).
EMBEDDINGS = "relatedness_embeddings"
SCORES = "relatedness_scores"
THEME_RUNS = "theme_runs"
THEMES = "relatedness_themes"
THEME_TAGS = "relatedness_theme_tags"
THEME_MEMBERS = "relatedness_theme_members"
THEME_ETFS = "relatedness_theme_etfs"
TICKER_THEMES = "ticker_themes"
LLM_CACHE = "llm_cache"

#: The three levels of a theme run, coarsest first. ``ticker_themes`` holds one row per level per ticker.
LEVELS = ("coarse", "medium", "fine")

#: The deterministic read order of a run's theme tables (#20). :data:`THEMES` is deliberately absent — see
#: :func:`run_rows`.
ROW_ORDER = {THEME_TAGS: "theme_id, rank, tag",
             THEME_MEMBERS: "theme_id, rank NULLS LAST, ticker"}

#: The predicate that selects one run's rows in the theme tables, which have no ``run_id`` column: the row whose
#: ``theme_id`` *is* the run id, or one of its ``<run>:<...>`` children.
_OF_RUN = "(theme_id = ? OR starts_with(theme_id, ?))"


def _query(sql: str, params: list | None = None) -> list[dict]:
    return rawstore.query(sql, params, db=DB)


def _run_args(run_id: str) -> list:
    return [run_id, f"{run_id}:"]


def _count(sql: str, params: list | None = None) -> int:
    rows = _query(sql, params)
    return int((rows[0]["n"] if rows else 0) or 0)


# ── theme_runs: which run the boards read ─────────────────────────────────────────────────────────────────────────
def pinned_run_id() -> str | None:
    """The id of the run carrying ``is_current = 1``, or None when no run is pinned.

    The one place this is asked of the store. ``core.universe.current_theme_run`` is the one *lookup* every board
    goes through (C23) and ``module_relatedness.themes.current_run_id`` delegates to it — but the SQL behind it
    was written in ``core/universe.py``, three directories from the table, and the board's own
    ``theme_runs`` reads could not be checked against it. It is this function now.

    This read does **not** swallow a failure: ``current_theme_run`` catches it for a filter (a filter never breaks
    a board) and lets it through for the guards that refuse to rebuild or prune the current run.
    """
    rows = _query(f"SELECT id FROM {THEME_RUNS} WHERE is_current = 1 LIMIT 1")
    return rows[0]["id"] if rows else None


# ── the theme tables of one run ───────────────────────────────────────────────────────────────────────────────────
def run_rows(table: str, run_id: str, level: str | None = None) -> list[dict]:
    """Rows of a theme table that belong to ``run_id`` (the run id or ``run:fN``).

    The one reader of a run's rows: a SQL prefix filter (no ``run_id`` column, no whole-table scan filtered in
    Python). ``level`` narrows :data:`THEMES`.

    **The order is part of the contract for the tags and the members table** (#20, :data:`ROW_ORDER`): without it
    the order was the scan's, and a caller that aggregates one theme's rows into another's -- the offline label
    (``themes.relabel_from_tags``) and the naming prompt (``naming.name_themes``) both do -- could give a different
    answer on two machines from the same rows. #20 reports the #51 e2e labelling one merged medium theme
    ``branch, consumer, deposits`` on Windows and ``biologics, clinical, drugs`` on the hosted Linux CI; the cause
    of *that* split is not the scan order (the tag rows are written in numeric fine order, and DuckDB here returns
    rows in insertion order) but which group NMF numbers ``f0``: the fixture's top singular values are exactly
    tied, so ``nndsvda``'s starting point is down to the LAPACK build. This function removes the scan-order
    dependency, which is a real one for any run whose rows were not written in that order; it does not and cannot
    fix the fine numbering.

    :data:`THEME_MEMBERS` is ordered ``theme_id, rank NULLS LAST, ticker``, and ``naming._aggregate`` keeps the
    first ``MAX_TICKERS`` of a theme as the prompt's example companies -- so the order decides which companies the
    model is shown. ``rank`` is the member's place in the cap-descending universe (``themes.member_ranks``), which
    makes those examples the theme's **largest** names: #298, avo's B of 19 Nov 2026. It was the alphabetically
    first names before (``AAPL, ADBE, AMAT, ...`` for a semiconductor theme), because the members came from
    ``tag_docs``' ``sorted(profiles)`` and the order read ``theme_id, ticker``.

    ``NULLS LAST`` is for the stored runs: ``rank`` is an additive column, so a run written before it carries NULL
    for every member and falls back to the ``ticker`` order it was read in until it is rebuilt. The stored **names**
    do not move either way: a label changes only when naming runs again (``naming.name_themes``), which is a paid
    step of its own.

    :data:`THEMES` is deliberately **not** ordered. #20 does not need it (the callers sort the ids they walk
    themselves), and an ``ORDER BY theme_id`` would change ``themes.rebalance_coarses``, which takes the mediums in
    read order: the numeric insertion order ``m0, m1, m2, ...`` would become the text order ``m0, m1, m10, ..., m2``
    for a run with 11+ mediums, deciding which coarse group gets the ``(2)`` suffix on a future rebuild. That is a
    board-visible change and not this PR's.
    """
    sql = f"SELECT * FROM {table} WHERE {_OF_RUN}"
    args = _run_args(run_id)
    if level:
        sql += " AND level = ?"
        args.append(level)
    order = ROW_ORDER.get(table)
    return _query(f"{sql} ORDER BY {order}" if order else sql, args)


def catalog_rows(run_id: str) -> list[dict]:
    """``theme_id, level, parent_id, label, size`` of a run's themes: what the one Theme vocabulary is built from
    (``core.universe.theme_catalog``, ADR-2).

    The same rows as ``run_rows(THEMES, run_id)``, asked for by the five columns the catalog uses rather than by
    ``*``. It was a second copy of the prefix filter in ``core/universe.py``; both are this file's one predicate
    now, so a change to what "the rows of this run" means cannot reach the board and miss the vocabulary.
    """
    return _query(f"SELECT theme_id, level, parent_id, label, size FROM {THEMES} WHERE {_OF_RUN}",
                  _run_args(run_id))


def coarse_labels_of_run(run_id: str) -> list[dict]:
    """``theme_id, label`` of a run's **coarse** themes, as :data:`THEMES` holds them.

    Sector Rotation's Theme control reads the stored label beside the catalog's, so a sector-named coarse theme
    keeps the sector ETF it plotted before the catalog renamed it (avo's card on the R2 review, 14 Oct 2026).
    """
    return _query(f"SELECT theme_id, label FROM {THEMES} WHERE level = 'coarse' AND {_OF_RUN}", _run_args(run_id))


def member_tickers_of_run(run_id: str) -> list[dict]:
    """``ticker, theme_id`` of a run's fine-theme members, in no particular order.

    ``core.universe`` walks each ticker's fine theme up its parents into a *set* of ids, so the #20 order
    :func:`run_rows` carries buys it nothing and an ``ORDER BY`` over every member of a run would be paid on every
    filter build. A caller that aggregates one theme's rows into another's uses :func:`run_rows` instead.
    """
    return _query(f"SELECT ticker, theme_id FROM {THEME_MEMBERS} WHERE {_OF_RUN}", _run_args(run_id))


def member_count_of_run(run_id: str) -> int:
    """How many member rows a run holds: the cutover's guard, which refuses a run with none."""
    return _count(f"SELECT count(*) AS n FROM {THEME_MEMBERS} WHERE {_OF_RUN}", _run_args(run_id))


def profiled_ticker_count(run_id: str) -> int:
    """How many distinct tickers a run's **fine** themes hold between them: the cutover's "profiled" count.

    A member row whose fine theme is gone from :data:`THEMES` does not count, which is why this is a join and not
    a ``count(DISTINCT ticker)`` over the members.
    """
    return _count(
        f"SELECT count(DISTINCT m.ticker) AS n FROM {THEME_MEMBERS} m "
        f"JOIN {THEMES} f ON f.theme_id = m.theme_id AND f.level = 'fine' "
        f"WHERE (m.theme_id = ? OR starts_with(m.theme_id, ?))", _run_args(run_id))


def theme_etfs(theme_id: str) -> list[dict]:
    """``etf, rank`` of one theme's overlapping ETFs, best rank first (Sector Rotation's Jaccard overlay)."""
    return _query(f"SELECT etf, rank FROM {THEME_ETFS} WHERE theme_id = ? ORDER BY rank ASC, etf ASC", [theme_id])


# ── ticker_themes: the cut-over run every board reads ─────────────────────────────────────────────────────────────
def medium_labels_for_ticker(ticker: str, run_id: str) -> list[dict]:
    """``theme, theme_id`` of one ticker's medium themes in ``run_id``.

    ``theme`` is the label copied onto the row at cutover and by naming; it can be empty for a run named after
    its cutover, which is why the caller falls back to the theme's own row.
    """
    return _query(f"SELECT theme, theme_id FROM {TICKER_THEMES} "
                  f"WHERE ticker = ? AND theme_run_id = ? AND level = 'medium'", [ticker.upper(), run_id])


def medium_labels_for_tickers(tickers, run_id: str) -> list[dict]:
    """``ticker, theme, theme_id`` for many tickers' medium themes in one query; an empty ask reaches no store."""
    names = [str(t).upper() for t in tickers]
    if not names:
        return []
    marks = ", ".join("?" for _ in names)
    return _query(f"SELECT ticker, theme, theme_id FROM {TICKER_THEMES} "
                  f"WHERE theme_run_id = ? AND level = 'medium' AND ticker IN ({marks})", [run_id, *names])


def medium_members_of_run(run_id: str) -> list[dict]:
    """``ticker, theme_id`` of every medium row of a cut-over run: the source side of a theme adoption."""
    return _query(f"SELECT ticker, theme_id FROM {TICKER_THEMES} "
                  f"WHERE theme_run_id = ? AND level = 'medium'", [run_id])


def ticker_theme_levels(run_id: str) -> list[dict]:
    """``ticker, level, theme_id, theme`` of a cut-over run: the peer rows' level labels.

    The level comes from here and the **label** from ``core.universe.theme_catalog``, so Relatedness, Co-movement
    and Sector Rotation show the same coarse label; the stored ``theme`` is the fallback when the catalog has no
    row.
    """
    return _query(f"SELECT ticker, level, theme_id, theme FROM {TICKER_THEMES} WHERE theme_run_id = ?", [run_id])


def ticker_theme_rows(run_id: str) -> list[dict]:
    """Every row of a cut-over run, with the columns a rewrite needs back (naming copies its labels on).

    The write is a whole-row ``write_rows``, so this read asks for the table's full key and payload rather than
    ``*``: a column added to the table does not silently become NULL on the rewrite.
    """
    return _query(f"SELECT ticker, theme_id, theme, level, theme_run_id, fetched_at FROM {TICKER_THEMES} "
                  f"WHERE theme_run_id = ?", [run_id])


def ticker_theme_row_count(run_id: str) -> int:
    """How many ``ticker_themes`` rows a run holds: what the cutover reports as ``rows``."""
    return _count(f"SELECT count(*) AS n FROM {TICKER_THEMES} WHERE theme_run_id = ?", [run_id])


# ── llm_cache ─────────────────────────────────────────────────────────────────────────────────────────────────────
def llm_cache_rows_for_model(model: str) -> int:
    """How many cached answers the store holds for ``model``: the provider comparison's before/after count."""
    return _count(f"SELECT count(*) AS n FROM {LLM_CACHE} WHERE model = ?", [model])
