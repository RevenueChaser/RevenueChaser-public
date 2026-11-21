"""The Co-movement board's one reader of its own store: every SELECT against ``boards/comovement.duckdb``
lives here (#217).

#217 (F12, the 27 Oct 2026 architecture review) is not about SQL being slow or wrong. It is about *where* it is
written: a board whose logic files each carry their own table name and their own ``SELECT`` makes a table rename, a
column rename or a new filter a change to every one of those files, and nothing tells the reader which files those
are. The decision (D4) was a read API that carries provenance, with a strangler migration board by board.

This is the Co-movement board's step of that migration, the third after News (PR #1195) and Relatedness
(PR #1269). Measured on ``main`` at ``bbb0c541``: the store was read by **13** places — 10 in
``module_comovement/engine.py`` and 3 in ``module_relatedness/engine.py``, which enriches a peer row with the
co-movement cluster a pair shares — and the four table names were spelled thirty times in the engine alone.

The shape is the News and Relatedness boards': one module per board, thin functions named after the need, no
connection kept and no provider call. The writes stay with the code that produces the rows — a write is not a
query, and the dated run is written in one transaction in ``engine._persist`` — but they take their table names
from here, so a rename is still one file. Nothing here fetches, and nothing here raises on an empty store: a
missing table reads as no rows (``rawstore.query`` swallows ``CatalogException`` on a read), which is also why a
read of a *wrong* name fails silently and why the SQL belongs next to the tables it names.

The lenience stays with the caller. Every one of the engine's persisted-run reads is wrapped in ``try`` with a
logged warning, because a store that predates a column or a table must degrade to "no persisted verdict" rather
than failing a render; ``module_relatedness`` wraps its two member reads for the same reason. None of that is
decided here.

The four tables (``core/rawstore.py`` owns their columns, ``docs/data_architecture.md`` the contract). They are
keyed by ``as_of``, the run's timestamp, which is why nearly every read below takes one:

- ``comov_runs`` one row per dated run: its ``config_hash`` (every input that changes the numbers),
  ``prices_through``, the window and horizon, and the JSON blobs of the run (``null_json``, ``oos_json``,
  ``funnel_json``, ``dropped_json``).
- ``comov_nodes`` one row per cluster of a run, at each ``cut``.
- ``comov_members`` one row per ``(cut, cluster_id, ticker)``.
- ``comov_lag`` the lagged groups and their held-out test, one row per member.
"""
from __future__ import annotations

from RevenueChaser.core import rawstore

#: The board's DuckDB file, as ``rawstore`` names it.
DB = "comovement"

#: The four table names. Every reader here, the engine's writer and the Settings record take them from this
#: module, so a rename is a change to one file (the point of #217).
RUNS = "comov_runs"
NODES = "comov_nodes"
MEMBERS = "comov_members"
LAG = "comov_lag"

#: The run's tables in the order the writer clears and prunes them: the children before the header, so no child
#: row outlives the run it belongs to.
RUN_TABLES = (NODES, MEMBERS, LAG)

#: The deterministic read order of a run's clusters: by cut, then the largest cluster first. ``load_payload``
#: renders them in this order and the board shows them in it.
NODE_ORDER = "cut, n DESC"


def _query(sql: str, params: list | None = None) -> list[dict]:
    """One place where this board's file is read."""
    return rawstore.query(sql, params, db=DB)


def persisted_source(config_hash: str) -> str | None:
    """``prices_through`` of the newest persisted Fetch run with this config hash, or ``None``.

    A Refresh reuses that run's null and lagged test; when its prices differ from the ones being re-clustered now,
    the board says whose verdicts it shows (review SP-F7) instead of presenting them as current.
    """
    row = _query(
        f"SELECT prices_through FROM {RUNS} WHERE config_hash = ? "
        f"AND null_json IS NOT NULL ORDER BY as_of DESC LIMIT 1", [str(config_hash)])
    return row[0].get("prices_through") if row else None


def persisted_null_json(config_hash: str) -> str | None:
    """The stored ``null_json`` of the newest persisted Fetch run with this config hash, or ``None``.

    The text, not the parsed null: the engine owns what a malformed blob means (groups are then not judged), and
    a store written before the column simply has no such run.
    """
    row = _query(
        f"SELECT null_json FROM {RUNS} WHERE config_hash = ? "
        f"AND null_json IS NOT NULL ORDER BY as_of DESC LIMIT 1", [str(config_hash)])
    return row[0].get("null_json") if row else None


def latest_run_with_lag(config_hash: str) -> str | None:
    """``as_of`` of the newest run with this config hash that has lagged-test rows, or ``None``."""
    row = _query(
        f"SELECT r.as_of FROM {RUNS} r WHERE r.config_hash = ? AND EXISTS "
        f"(SELECT 1 FROM {LAG} l WHERE l.as_of = r.as_of) "
        f"ORDER BY r.as_of DESC LIMIT 1", [str(config_hash)])
    return row[0]["as_of"] if row else None


def lag_rows(as_of: str) -> list[dict]:
    """A run's lagged groups and their held-out test, one row per member."""
    return _query(
        f"SELECT cut, lag_id, ticker, oos_r, oos_base, held FROM {LAG} WHERE as_of = ?", [as_of])


def runs_with_prices(config_hash: str, prices_through: str) -> list[dict]:
    """``as_of`` of every run with this config hash **and** these prices, newest first.

    The engine walks them to find a stored run it may serve, so the order is part of the answer: it stops at the
    first run older than the engine epoch or than the last store change for the tickers.
    """
    return _query(
        f"SELECT as_of FROM {RUNS} WHERE config_hash = ? AND prices_through = ? "
        f"ORDER BY as_of DESC", [str(config_hash), str(prices_through)])


def clustered_tickers(as_of: str) -> set[str]:
    """The distinct tickers a run clustered: what a stored run has to match to be served again."""
    return {r["ticker"] for r in _query(f"SELECT DISTINCT ticker FROM {MEMBERS} WHERE as_of = ?", [as_of])}


def latest_run_as_of(horizon: int | None = None, benchmark: str | None = None) -> str | None:
    """``as_of`` of the newest run matching ``horizon``/``benchmark``, or ``None``.

    An unset filter matches any run, which is what ``load_payload()`` with no arguments asks for.
    """
    where, params = [], []
    if horizon is not None:
        where.append("horizon = ?")
        params.append(int(horizon))
    if benchmark is not None:
        where.append("benchmark = ?")
        params.append(str(benchmark))
    sql = f"SELECT as_of FROM {RUNS}"
    if where:
        sql += " WHERE " + " AND ".join(where)
    sql += " ORDER BY as_of DESC LIMIT 1"
    row = _query(sql, params)
    return row[0]["as_of"] if row else None


def default_run_as_of(horizon: int, benchmark: str, default_window: int) -> str | None:
    """``as_of`` of the run another board should read for this ``(horizon, benchmark)``, or ``None``.

    The newest prices first, then the board's default window — a Fetch also stores other windows (#95), which must
    not displace it — then the latest. ``module_relatedness`` reads the co-movement cluster of a pair through this,
    rather than through a horizon of its own: a hardcoded ``horizon = 5`` went stale the moment the board's
    default moved to 1d (S7).
    """
    rows = _query(
        f"SELECT as_of FROM {RUNS} WHERE horizon = ? AND benchmark = ? "
        f"ORDER BY prices_through DESC NULLS LAST, (window_days = ?) DESC, as_of DESC LIMIT 1",
        [int(horizon), str(benchmark), int(default_window)])
    return rows[0]["as_of"] if rows else None


def run_row(as_of: str) -> dict | None:
    """A run's header row, or ``None``.

    ``SELECT *`` on purpose: a store that predates a column still loads, the value simply absent rather than a
    hard error.
    """
    rows = _query(f"SELECT * FROM {RUNS} WHERE as_of = ?", [as_of])
    return rows[0] if rows else None


def node_rows(as_of: str) -> list[dict]:
    """A run's clusters, in the board's read order (:data:`NODE_ORDER`). ``SELECT *``, as :func:`run_row`."""
    return _query(f"SELECT * FROM {NODES} WHERE as_of = ? ORDER BY {NODE_ORDER}", [as_of])


def member_rows(as_of: str) -> list[dict]:
    """A run's members, every column (the ``core`` flag among them). ``SELECT *``, as :func:`run_row`."""
    return _query(f"SELECT * FROM {MEMBERS} WHERE as_of = ?", [as_of])


def cuts_of_run(as_of: str) -> list[int]:
    """The cuts a run holds, coarsest first — the levels another board maps its names onto."""
    return sorted(int(r["cut"]) for r in _query(f"SELECT DISTINCT cut FROM {NODES} WHERE as_of = ?", [as_of]))


def cluster_members(as_of: str) -> list[dict]:
    """``(cut, cluster_id, ticker)`` of a run: which cluster each name sat in, for a board that only needs that."""
    return _query(f"SELECT cut, cluster_id, ticker FROM {MEMBERS} WHERE as_of = ?", [as_of])
