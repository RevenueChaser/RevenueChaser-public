"""The News board's one reader of its own store: every SELECT against ``boards/news.duckdb`` lives here (#217).

#217 (F12, the 27 Oct 2026 architecture review) is not about SQL being slow or wrong. It is about *where* it is
written: a board whose logic files each carry their own table name and their own ``SELECT`` makes a table rename, a
column rename or a new filter a change to every one of those files, and nothing tells the reader which files those
are. The decision (D4) was a read API that carries provenance, with a strangler migration board by board.

This is the News board's step of that migration, chosen first because the News board held the most embedded SQL of
any board — 20 of the 83 non-test ``rawstore.query`` calls on ``main`` at ``d349458``, spread over five files
(``calendar.py`` 4, ``report.py`` 5, ``headlines.py`` 8, ``x_reader.py`` 2, ``x_check.py`` 1), and the table names
re-declared in five places. After it, the board's modules name a *need* ("the live events of this week", "the
headlines waiting for an option check") and this module owns the SQL, the table names and the lane definition.

The shape is the one the board readers already written for the **market** store use
(``module_spx_gamma/store_reads.py``, ``module_earnings_radar/store_reads.py``, PR 3): one module per board, thin
functions named after the need, no connection kept and no provider call. It differs in one way, because the store
differs: those two read rcdata's serving layer through ``rcdata.read``, while the News board's own tables are
*written* by this board, so this module reads them through ``core.rawstore``. The writes stay with the code that
produces the rows — a write is not a query — but they take their table names from here, so a rename is still one
file.

Nothing here fetches, and nothing here raises on an empty store: a table with no rows reads as no rows.

The tables (``core/rawstore.py`` owns their columns, ``docs/data_architecture.md`` the contract):

- ``news_events`` the calendar, one row per ``(event_ts, event, type)``, built incrementally by ``calendar.build``;
  a row the newest fetch no longer lists carries ``retired_at`` and is never deleted, so every read of "what is on
  the calendar" filters it out (``live_`` below). Two kinds of row share the table: the economic releases, which
  keep UW's own ``type`` (report, fomc, fed-speaker), and the FDA catalysts of #807, whose ``type`` is
  :data:`FDA_TYPE` and which carry nine columns of their own. A read is almost never about both, so the economic
  reads exclude the FDA rows by name rather than by the caller remembering to.
- ``news_earnings`` next week's report day of every name on the board's watch lists (#886): one week at a time.
- ``news_highlight`` one row per Amsterdam day: that day's most important live **economic** event.
- ``news_headlines`` one row per story, the three lanes of the page in one table (see ``LANES``).
- ``news_meta`` the board's marks and cursors, ``key`` -> ``value`` as text.
- ``news_reading`` the hourly reading of the tape (#1234): one row per ``(window_end, field)``, each
  carrying the sentence it came from, written by ``module_news/reading.py``.
"""
from __future__ import annotations

from RevenueChaser.core import rawstore

#: The board's DuckDB file, as ``rawstore`` names it.
DB = "news"
#: The table names. Every reader here and every writer in the board takes them from this module, so a rename
#: is a change to one file (the point of #217).
EVENTS = "news_events"
EARNINGS = "news_earnings"
HIGHLIGHT = "news_highlight"
HEADLINES = "news_headlines"
META = "news_meta"
#: The hourly reading of the headline flow (#1234): one row per ``(window_end, field)``.
READING = "news_reading"

#: The ``type`` of an FDA catalyst row in :data:`EVENTS` (#807). It is a value in a column rather than a table
#: name, but it cuts the table in two for every read below and for the writes in ``calendar.py``, so it is owned
#: here with them: the economic reads and the FDA reads cannot drift apart over the spelling of one word.
FDA_TYPE = "fda"

#: The lanes of the News page, in its order. ``market`` is the broad tape (no ticker), ``stocks`` a headline carrying
#: one, ``x`` a post from the X summaries or RC's own X reader. The SQL that cuts them is ``_LANE_CASE``; the Python
#: that cuts one row is ``report.lane``. Both read ``x_feed.X_PROVIDERS``, so they cannot disagree.
LANES = ("market", "stocks", "x")


def _x_providers() -> tuple[str, ...]:
    from RevenueChaser.module_news.x_feed import X_PROVIDERS
    return tuple(X_PROVIDERS)


def _x_clause(providers: tuple[str, ...]) -> str:
    """``provider`` is one of the X providers, as a parameterised predicate (never an interpolated literal)."""
    return f"coalesce(provider, '') IN ({', '.join('?' for _ in providers)})"


def _query(sql: str, params: list | None = None) -> list[dict]:
    return rawstore.query(sql, params, db=DB)


# ── news_meta: the board's marks and cursors ──────────────────────────────────────────────────────────────────────
def meta_value(key: str) -> str | None:
    """The stored text under ``key``, or None when the board has never written it.

    Every mark the board keeps is read through this one function: the calendar's incremental mark, the per-ticker
    cursor, the tape and X-mail offsets, RC's X reader state and a ticker's last on-demand answer. Each caller
    parses its own value (a float, a JSON object), because only the caller knows its shape.
    """
    rows = _query(f"SELECT value FROM {META} WHERE key = ?", [str(key)])
    return None if not rows else rows[0]["value"]


def meta_values(keys) -> dict[str, str]:
    """``{key: value}`` for the keys of ``keys`` the board has written; a key never written is absent."""
    names = [str(k) for k in keys]
    if not names:
        return {}
    rows = _query(f"SELECT key, value FROM {META} WHERE key IN ({', '.join('?' for _ in names)})", names)
    return {str(r["key"]): r["value"] for r in rows}


# ── news_events: the economic calendar ────────────────────────────────────────────────────────────────────────────
def events_between(lo: float, hi: float) -> list[dict]:
    """Every stored row, **retired ones too**, whose ``event_ts`` is in ``[lo, hi]``.

    The incremental build's own read: it has to see a retired row to carry its ``first_seen`` forward rather than
    write a second row for the same key. No board read uses this one — a page asks ``live_events_*``.
    """
    return _query(f"SELECT * FROM {EVENTS} WHERE event_ts BETWEEN ? AND ?", [lo, hi])


def live_economic_between(lo: float, hi: float) -> list[dict]:
    """The live (not retired) **economic** rows whose ``event_ts`` is in ``[lo, hi]``: the FDA rows of #807 are
    left out, because the economic pass retires what the economic source stopped listing and must not touch them."""
    return _query(f"SELECT * FROM {EVENTS} WHERE event_ts BETWEEN ? AND ? AND retired_at IS NULL AND type <> ?",
                  [lo, hi, FDA_TYPE])


def live_fda_between(lo: float, hi: float) -> list[dict]:
    """The live FDA rows whose ``event_ts`` is in ``[lo, hi]``: the mirror of
    :func:`live_economic_between` for the FDA pass, so neither pass can retire the other's rows."""
    return _query(f"SELECT * FROM {EVENTS} WHERE event_ts BETWEEN ? AND ? AND retired_at IS NULL AND type = ?",
                  [lo, hi, FDA_TYPE])


def live_economic_from(start: float) -> list[dict]:
    """The live economic rows at or after ``start``, in time order: the highlight pass reads the days forward from
    one day, and a day's highlight is an economic release (#807), never an FDA catalyst."""
    return _query(f"SELECT * FROM {EVENTS} WHERE event_ts >= ? AND retired_at IS NULL AND type <> ? "
                  f"ORDER BY event_ts", [start, FDA_TYPE])


def live_events_in_window(start: float, end: float) -> list[dict]:
    """The live rows in ``[start, end)``, in the page's order: by time, then by name for a tie.

    The Welcome card's own read of this window ordered by ``event_ts`` alone and left two releases of the same
    minute in whatever order DuckDB returned them; it reads this one now, so the two pages cannot disagree.
    """
    return _query(f"SELECT * FROM {EVENTS} WHERE event_ts >= ? AND event_ts < ? AND retired_at IS NULL "
                  f"ORDER BY event_ts, event", [start, end])


def live_fda_outside_a_day(precision: str, since: float, limit: int) -> list[dict]:
    """The live FDA rows whose ``target_precision`` is not ``precision`` — a quarter, a half year, "late" — from
    ``since`` on, in time order, at most ``limit``.

    They belong to no day of the week strip, so the page stands them in their own group under the FDA tab and
    reads them outside the week's window (#808). A row with no precision at all counts as dated, which is why the
    SQL coalesces to ``precision`` before comparing.
    """
    return _query(f"SELECT * FROM {EVENTS} WHERE type = ? AND retired_at IS NULL "
                  f"AND coalesce(target_precision, ?) <> ? AND event_ts >= ? "
                  f"ORDER BY event_ts, event LIMIT {int(limit)}",
                  [FDA_TYPE, str(precision), str(precision), float(since)])


def live_events_of_types(start: float, end: float, types, limit: int) -> list[dict]:
    """The live rows in ``[start, end)`` of the types ``types`` names (every type when it names none), in time
    order, at most ``limit``: what ``GET /api/news/events`` serves.

    The type names are compared in lower case, as the route receives them. An ask whose names are all blank is no
    types at all, not every type, and answers no rows — the caller's own guard, kept here so the route cannot get
    it wrong twice.
    """
    sql = f"SELECT * FROM {EVENTS} WHERE event_ts >= ? AND event_ts < ? AND retired_at IS NULL"
    params: list = [float(start), float(end)]
    if types is not None:
        wanted = sorted({str(t).strip().lower() for t in types if str(t or "").strip()})
        if not wanted:
            return []
        sql += f" AND lower(type) IN ({', '.join('?' * len(wanted))})"
        params += wanted
    return _query(sql + f" ORDER BY event_ts, event LIMIT {int(limit)}", params)


# ── news_earnings ─────────────────────────────────────────────────────────────────────────────────────────────────
def earnings_week(week_start: str) -> list[dict]:
    """The stored report days of the week beginning ``week_start`` (``YYYY-MM-DD``), by day then ticker.

    The weekly pass empties the table before it writes, so a table holding another week (the pass has not run
    since the week turned) answers no rows here and the tab says the week is not built, rather than showing last
    week's days.
    """
    return _query(f"SELECT * FROM {EARNINGS} WHERE week_start = ? ORDER BY report_date, ticker", [str(week_start)])


def newest_event_fetch_at() -> float | None:
    """The newest ``last_seen`` of any calendar row: when the board last saw a fetch of the economic calendar.

    ``last_seen`` is the served row's own ``fetched_at`` carried forward by ``calendar.build``, so this is the
    source's freshness and not the build's (which is ``newest_event_run_at``). The provenance line's News date
    (``core/provenance.py``) asked a table called ``news_calendar`` for ``max(fetched_at)``; no such table has
    ever existed in this board's file — ``news_calendar`` is the *dataset* key in ``core/datasets.py``, whose
    tables are ``news_events``, ``news_highlight`` and ``news_meta`` — and a missing table reads as no rows
    (``rawstore.query`` swallows ``CatalogException`` on a read), so that line has silently shown no date at all.
    SQL written far from the board, against a name nobody could check, is the thing #217 is about.
    """
    rows = _query(f"SELECT max(last_seen) AS t FROM {EVENTS}")
    value = rows[0]["t"] if rows else None
    return None if value is None else float(value)


def newest_event_run_at() -> float | None:
    """The newest ``run_at`` of any calendar row: half of the page's "updated" time (the headlines are the other)."""
    rows = _query(f"SELECT max(run_at) AS t FROM {EVENTS}")
    value = rows[0]["t"] if rows else None
    return None if value is None else float(value)


# ── news_highlight ────────────────────────────────────────────────────────────────────────────────────────────────
def highlight(session_date: str) -> dict | None:
    """The stored highlight of one Amsterdam day (``YYYY-MM-DD``), or None when that day has none."""
    rows = _query(f"SELECT * FROM {HIGHLIGHT} WHERE session_date = ?", [str(session_date)])
    return rows[0] if rows else None


# ── news_headlines ────────────────────────────────────────────────────────────────────────────────────────────────
#: The columns the poll draws. Spelled out rather than ``*`` because the answer crosses the HTTP boundary.
API_COLUMNS = ("headline_id", "provider", "published_at", "headline", "source", "tickers", "url", "kind", "option",
               "x_check", "run_at")
#: The columns the on-demand ticker box shows.
TICKER_COLUMNS = ("headline_id", "published_at", "headline", "source", "tickers", "url")


def stored_headline_ids(ids) -> set[str]:
    """Which of ``ids`` the table already holds. Empty for an empty ask (no query is run)."""
    names = [str(i) for i in ids]
    if not names:
        return set()
    rows = _query(f"SELECT headline_id FROM {HEADLINES} WHERE headline_id IN ({', '.join('?' for _ in names)})",
                  names)
    return {str(r["headline_id"]) for r in rows}


def stored_tickers(ids) -> dict[str, str]:
    """``{headline_id: tickers}`` (the JSON text as stored) for the ids of ``ids`` already held.

    The per-name fetch merges a story's names rather than replacing them: the same story met under a second ticker
    must gain that ticker, not lose the first.
    """
    names = [str(i) for i in ids]
    if not names:
        return {}
    rows = _query(f"SELECT headline_id, tickers FROM {HEADLINES} "
                  f"WHERE headline_id IN ({', '.join('?' for _ in names)})", names)
    return {str(r["headline_id"]): r["tickers"] for r in rows}


def headlines_by_lane(since: float, limit: int) -> list[dict]:
    """The newest ``limit`` headlines **of each lane** published at or after ``since``, newest first within a lane.

    One ``LIMIT`` over the table would let a busy lane crowd the others off the page, so each lane gets its own
    (the page then renders the three groups). The X lane leaves out what Grok filed as ``other``.
    """
    providers = _x_providers()
    x = _x_clause(providers)
    lanes = (f"NOT {x} AND coalesce(tickers, '[]') = '[]'",
             f"NOT {x} AND coalesce(tickers, '[]') <> '[]'",
             f"{x} AND coalesce(kind, '') <> 'other'")
    out: list[dict] = []
    for cond in lanes:
        out += _query(f"SELECT * FROM {HEADLINES} WHERE published_at >= ? AND {cond} "
                      f"ORDER BY published_at DESC LIMIT {int(limit)}", [float(since), *providers])
    return out


def headlines_since(written_after: float, published_from: float, limit: int) -> list[dict]:
    """The rows written after ``written_after`` (their ``run_at``) and published at or after ``published_from``,
    newest published first, at most ``limit``: what the page's poll draws."""
    return _query(f"SELECT {', '.join(API_COLUMNS)} FROM {HEADLINES} "
                  f"WHERE run_at > ? AND published_at >= ? ORDER BY published_at DESC LIMIT {int(limit)}",
                  [float(written_after), float(published_from)])


def headlines_for_ticker(ticker: str, published_from: float, limit: int) -> list[dict]:
    """The stored IBKR headlines carrying ``ticker``, published at or after ``published_from``, newest first.

    ``tickers`` is JSON text, so the name is matched as a quoted element (``%"AAPL"%``): a substring match on the
    bare name would let ``AA`` answer for ``AAPL``.
    """
    return _query(f"SELECT {', '.join(TICKER_COLUMNS)} FROM {HEADLINES} "
                  f"WHERE provider = 'ibkr' AND tickers LIKE ? AND published_at >= ? "
                  f"ORDER BY published_at DESC LIMIT {int(limit)}",
                  [f'%"{str(ticker).strip().upper()}"%', float(published_from)])


def headlines_newest(published_from: float, limit: int) -> list[dict]:
    """The newest ``limit`` headlines of **any** lane published at or after ``published_from``, newest first.

    The Welcome card's read: one short list across the lanes, where the board's own page keeps them apart
    (``headlines_by_lane``).
    """
    return _query(f"SELECT * FROM {HEADLINES} WHERE published_at >= ? ORDER BY published_at DESC LIMIT {int(limit)}",
                  [float(published_from)])


def headlines_in_window(start: float, end: float, limit: int) -> list[dict]:
    """The stored headlines published inside ``[start, end]``, newest first, at most ``limit``: what
    ``GET /api/news/headlines`` serves when it is asked for a window instead of the page's ``since`` poll.

    The window is what makes the join of #809 possible — the headlines around a release, not the last 24 hours.
    The lane and ticker cuts stay with the route, which already owns them in Python (``report.lane``,
    ``report.x_group``), because they read a row rather than the table.
    """
    return _query(f"SELECT {', '.join(API_COLUMNS)} FROM {HEADLINES} "
                  f"WHERE published_at >= ? AND published_at <= ? ORDER BY published_at DESC LIMIT {int(limit)}",
                  [float(start), float(end)])


# ── news_reading: the hourly reading (#1234) ──────────────────────────────────────────────────────────────────────
def readings_since(window_from: float) -> list[dict]:
    """Every stored reading field whose window ends at or after ``window_from``, newest hour first.

    One row is one field of one hour and carries the sentence it came from (``quote``, ``headline_id``); the
    caller groups them by ``window_end`` (``module_news.reading.api_rows``).
    """
    return _query(f"SELECT * FROM {READING} WHERE window_end >= ? ORDER BY window_end DESC, field",
                  [float(window_from)])


def reading_window(window_end: float) -> list[dict]:
    """The stored fields of the hour ending at ``window_end``, by field name; no rows when it was never read."""
    return _query(f"SELECT * FROM {READING} WHERE window_end = ? ORDER BY field", [float(window_end)])


def newest_reading_window() -> float | None:
    """The newest hour the reading pass stored anything for, or None when it never has."""
    rows = _query(f"SELECT max(window_end) AS t FROM {READING}")
    value = rows[0]["t"] if rows else None
    return None if value is None else float(value)


def x_headlines_since(since: float) -> list[dict]:
    """Every X-lane row published at or after ``since`` except what Grok filed as ``other``, newest first: the set
    the option check walks to find the rows still waiting for an answer."""
    providers = _x_providers()
    return _query(f"SELECT * FROM {HEADLINES} WHERE {_x_clause(providers)} AND kind <> 'other' "
                  f"AND published_at >= ? ORDER BY published_at DESC", [*providers, float(since)])


def lane_freshness() -> dict[str, float | None]:
    """``{lane: newest fetched_at}`` over ``LANES``; None for a lane with no row at all.

    One freshness over the whole table cannot see a dead lane (review F2, 18 Nov 2026): the hourly X load keeps
    ``news_headlines.fetched_at`` moving, so the dataset stays "fresh" on Settings and in Grafana while the
    per-ticker IBKR fetch has been down for a day. The lane cut is the SQL twin of ``report.lane``.
    """
    providers = _x_providers()
    rows = _query(f"SELECT CASE WHEN {_x_clause(providers)} THEN 'x' "
                  f"WHEN coalesce(tickers, '[]') = '[]' THEN 'market' ELSE 'stocks' END AS lane, "
                  f"max(fetched_at) AS newest FROM {HEADLINES} GROUP BY 1", [*providers])
    got = {str(r["lane"]): r["newest"] for r in rows}
    return {name: (float(got[name]) if got.get(name) is not None else None) for name in LANES}


__all__ = ["DB", "EVENTS", "EARNINGS", "HIGHLIGHT", "HEADLINES", "META", "READING", "FDA_TYPE", "LANES", "API_COLUMNS",
           "TICKER_COLUMNS", "meta_value", "meta_values",
           "events_between", "live_economic_between", "live_fda_between", "live_economic_from",
           "live_events_in_window", "live_fda_outside_a_day", "live_events_of_types",
           "newest_event_fetch_at", "newest_event_run_at", "earnings_week", "highlight",
           "stored_headline_ids", "stored_tickers", "headlines_by_lane", "headlines_newest", "headlines_since",
           "headlines_for_ticker", "headlines_in_window", "x_headlines_since", "lane_freshness",
           "readings_since", "reading_window", "newest_reading_window"]
