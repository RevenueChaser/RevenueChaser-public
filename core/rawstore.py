"""Single-file raw-data store backed by DuckDB.

All raw caches and derived data live in one ``.store/raw.duckdb`` file instead
of thousands of per-ticker JSON/CSV files (and three SQLite DBs). Every
read/write is ``connect -> do work -> close`` per operation — DuckDB is a
single-writer store (no SQLite-style WAL), so a handle is never held across a
job or a request.

- Writes raise on failure AND are atomic (``write_rows`` / ``replace_all`` /
  ``transaction`` each run in one transaction), so a failed refresh never
  leaves a table half-emptied. Writes retry on lock contention within a stated
  budget (``_WRITE_DELAYS``).
- Reads stay lenient: callers decide what a missing/stale row means; this layer
  raises only on I/O errors. Readers retry on lock with a longer budget
  (``_READ_DELAYS``) so they out-wait a chunked ingest. A lock held by another
  *RevenueChaser* process (dashboard, scheduled job, backup) gets that full
  budget too; only an unknown holder (a VS Code window, a notebook) fails fast.
- The schema manifest (``MANIFEST``) is the single source of truth: the
  migration script (``scripts/migrate_rawdata_to_duckdb.py``) and the coverage
  test (``core/tests/test_db_persistence.py``) both iterate it. The first store
  call in a process applies it (``ensure_all_tables``: renames, merges, views,
  column additions, compressed-column rebuilds), so a fresh or restored store
  never serves silently-empty views.
- Speed: opening the 500 MB file costs ~100 ms, so ``session()`` lets a burst
  of operations (one dashboard request) share one handle; big batches are
  inserted through a registered DataFrame instead of ``executemany`` (~75x).
  Large text/JSON cells DuckDB would store uncompressed are zlib-compressed
  (MANIFEST ``"compress"``), transparently for ``get``/``get_all``/``write_rows``.
"""
from __future__ import annotations

import atexit
import json
import logging
import os
import re
import subprocess
import threading
import time
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from RevenueChaser.core import procs
from RevenueChaser.core.config import DATA_DIR

logger = logging.getLogger(__name__)

#: The store folder. Since #860 it holds only the board files (``boards/<board>.duckdb``): the old ``raw``,
#: ``edgar``, ``history`` and ``prices`` files are gone with every path to them (avo, 15 Nov 2026 02:17
#: "Eskiye ait herseyi sil"). A test redirects the store by monkeypatching ``STORE_DIR``.
STORE_DIR = DATA_DIR


def _db_of(name: str) -> str:
    """The board file a MANIFEST table lives in; a table without one has no file (#860)."""
    db = (MANIFEST.get(name) or {}).get("db")
    if db is None:
        raise RawStoreError(f"{name} has no store file: the old stores are gone (#860)")
    return db


#: Board result files (DECISIONS S9, S16): ``<store>/boards/<board>.duckdb``, one writer per board package, written
#: incrementally. The first, narrow step of the board-file plan (2026-11-08): only boards born with their own file are
#: listed here (News, Welcome); the move of the older boards' tables (plan PR 0 and on) extends this tuple.
#: ``value_chain`` is the first entry moved OUT of ``edgar.duckdb`` rather than out of ``raw.duckdb`` (#860, stage 1
#: of letting that file go): ``chain_filings`` / ``chain_mentions`` / ``chain_meta`` are the Value Chain package's
#: own rows and nothing else reads them as EDGAR content.
#: ``watchlists`` is the one entry here that is not a board result: it is avo's own lists, typed by hand and not
#: regenerable from any source (#786). It sits here because it wants exactly what a board file gets — one writer,
#: the peer lock, the schema stamp and the ``boards`` backup step — and for nothing else. It is never rebuilt and
#: never written whole.
BOARD_DBS = ("news", "welcome", "relatedness", "comovement", "asymmetric_growth", "swing_potential",
             "fundamentals", "sector_rotation", "leaps", "oipd", "forecast", "spx_gamma", "sec_13f", "watchlists",
             "value_chain")
#: The folder of the board files, beside the raw store; ``rcdata/backup.py`` copies ``boards/*.duckdb``.
BOARDS_DIRNAME = "boards"


def board_db_path(board: str) -> Path:
    """A board's own result file, ``<store>/boards/<board>.duckdb`` (follows ``STORE_DIR`` redirects)."""
    return Path(STORE_DIR) / BOARDS_DIRNAME / f"{board}.duckdb"


def _db_path(db: str | None) -> Path:
    if db in BOARD_DBS:
        return board_db_path(db)
    raise RawStoreError(f"no store file {db!r}: only the board files are left (#860)")


# Write lock-wait budget ~6.9s — the first, tiny delays absorb the in-process
# attach race; the tail absorbs another process holding the lock. Plenty for the
# small per-ticker writes. A long ingest must stay chunked so it never holds the
# file lock for minutes; the 13F data-set ingest that set this budget is retired
# (G9: the builder keeps the filings and holdings in Parquet).
_WRITE_DELAYS = (0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0)
# Reader budget is longer so a reader out-waits a chunked ingest.
_READ_DELAYS = (0.01, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0)

# Serializes only the attach/detach of the database file within one process.
# duckdb.connect() on the SAME path from two threads at the same instant races
# on the library's global instance cache (BinderException "unique file handle
# conflict"), and on Windows a thread's close() can still hold the file lock a
# beat after returning, so a neighbouring thread's reopen raises a lock error.
# Both disappear if the connect() and close() calls themselves cannot overlap —
# the lock is NEVER held around the transaction/statements, so operations still
# overlap exactly as documented (a read during a held write handle works).
_ATTACH_LOCK = threading.Lock()
_SCHEMA_VERSION = "13"


# A manifest "column" entry is either a column definition (``name TYPE ...``) or
# an inline table constraint. Match on the FIRST TOKEN only, so a real column
# named e.g. ``checksum`` or ``uniqueness`` is never mistaken for a constraint.
_CONSTRAINT_KEYWORDS = {"PRIMARY", "UNIQUE", "CHECK", "FOREIGN", "CONSTRAINT"}


def _columns_of(spec: dict) -> list[str]:
    """Column names from a manifest spec (skipping inline constraint clauses).

    Names are returned UNQUOTED (``'"group" TEXT'`` -> ``'group'``) so they can
    be used both as dict keys on row objects and as SQL identifiers (write_rows
    quotes them for SQL).
    """
    names = []
    for c in spec["columns"]:
        head = re.split(r"[\s(]", c.strip(), maxsplit=1)[0]
        if head.upper() in _CONSTRAINT_KEYWORDS:
            continue
        names.append(head.strip('"'))
    return names


# Every way DuckDB says "someone else has this file right now". All are
# transient and must be retried, not raised:
#   - another PROCESS holds the file lock (IOException);
#   - a same-process handle opened with a different configuration
#     (ConnectionException) — see ``connect``;
#   - two threads racing to attach the file at the same instant
#     (BinderException "unique file handle conflict"), which the in-process
#     dashboard/job-worker split hits regularly.
_CONFLICT_MARKERS = (
    "could not set lock on file",
    "could not open database",
    "being used by another process",
    "locked",
    "conflict on transaction",
    "different configuration",
    "unique file handle conflict",
    "already attached",
)


def _conflict(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in _CONFLICT_MARKERS)


# A lock held by a DIFFERENT process. DuckDB phrases this differently per OS:
# Unix "Conflicting lock is held in ... (PID n)", Windows "Cannot open file ...
# being used by another process". Both mean the same 503-able condition.
_FOREIGN_LOCK_MARKERS = (
    "conflicting lock is held",
    "could not set lock on file",
    "being used by another process",
)


class RawStoreError(RuntimeError):
    pass


class StoreSchemaMismatch(RawStoreError):
    """A data write was refused because this file's schema stamp does not match this code (#26 PL7-b).

    Off unless ``RC_STORE_SCHEMA_REFUSE=1``. Does not fire at import. The message names the file
    (not a path), the stored version, the code version and the restore command.
    """


class StoreLockedError(RawStoreError):
    """The store is held by another process — the one failure with a real fix.

    DuckDB allows a single writer process at a time, so any other program that
    has ``raw.duckdb`` open (a DuckDB CLI, a notebook, the VS Code DuckDB
    extension) blocks the whole app. This carries the holder so the message can
    name it instead of surfacing as an unexplained 500 on every board.
    """

    def __init__(self, path, holder_pid: int | None, holder_name: str,
                 holder_path: str, detail: str):
        self.path = str(path)
        self.holder_pid = holder_pid
        self.holder_name = holder_name
        self.holder_path = holder_path
        self.detail = detail
        super().__init__(self.headline() + " " + self.remedy())

    def holder_label(self) -> str:
        if self.holder_name and self.holder_pid:
            return f"{self.holder_name} (PID {self.holder_pid})"
        if self.holder_pid:
            return f"PID {self.holder_pid}"
        return "another process"

    def headline(self) -> str:
        return (f"The database is currently locked by another process: "
                f"{self.holder_label()}.")

    def remedy(self) -> str:
        """Concrete next step, specialised for the holders we actually see."""
        blob = f"{self.holder_name} {self.holder_path}".lower()
        if "code" in blob and ("helper" in blob or "visual studio" in blob):
            return ('This is VS Code: its DuckDB extension attaches the file for '
                    'the life of the window. Set "attached": false for this '
                    'database in .vscode/settings.json (or detach it in the '
                    'extension), then reload the window (Cmd+Shift+P -> '
                    '"Reload Window").')
        if "duckdb" in blob:
            return ("Quit that DuckDB session (or close the notebook holding it) "
                    "and retry.")
        return (f"Close it and retry. On macOS/Linux: `lsof {self.path}` lists "
                f"every holder"
                + (f"; `kill {self.holder_pid}` if it is safe to stop."
                   if self.holder_pid else "."))


_LOCK_HOLDER_RE = re.compile(
    r"Conflicting lock is held in\s+(?P<path>.+?)\s*\(PID\s*(?P<pid>\d+)\)")


def _process_name(pid: int | None) -> str:
    """Friendly name for a PID, best effort — never raises, never blocks long."""
    if not pid:
        return ""
    try:
        out = subprocess.run(["ps", "-p", str(pid), "-o", "comm="],
                             capture_output=True, text=True, timeout=2)
        name = (out.stdout or "").strip().splitlines()
        if name:
            return Path(name[0].strip()).name
    except Exception:  # pragma: no cover - ps missing or refused
        pass
    return ""


def _lock_error(detail: str, path: Path | None = None) -> StoreLockedError:
    """Build a StoreLockedError from DuckDB's message, enriched via ``ps``."""
    path = Path(path) if path is not None else Path(STORE_DIR)
    m = _LOCK_HOLDER_RE.search(detail)
    holder_path = m.group("path").strip() if m else ""
    pid = int(m.group("pid")) if m else None
    # Prefer the live process name; fall back to the binary DuckDB named.
    name = _process_name(pid) or (Path(holder_path).name if holder_path else "")
    return StoreLockedError(path, pid, name, holder_path, detail)


def _open_failure_hint(msg: str) -> str:
    """Actionable next step for non-lock open failures."""
    if "different configuration" in msg.lower():
        return (" A handle to this file is already open in this process with a"
                " different configuration — every rawstore handle must be opened"
                " read-write (see docs/data_architecture.md).")
    return ""


# A lock held by an UNKNOWN process is not transient contention — a VS Code
# window or an open notebook holds it for as long as it stays open. Waiting out
# the full read budget (~29s) for that turns every board into a multi-minute
# stall and still fails. Try just long enough to ride out a momentary CLI query,
# then report it. The in-process races keep the full budget: those really do
# clear in milliseconds.
_FOREIGN_LOCK_DELAYS = (0.05, 0.1, 0.2)
# Another RevenueChaser process (the dashboard, a scheduled off-peak job, the
# nightly backup) only ever holds the file for one operation or one chunk, so
# it WILL release it: wait as long as a reader would.
_PEER_LOCK_DELAYS = _READ_DELAYS

# Every RevenueChaser process that touches a store drops ``.rc-proc-<pid>`` next
# to it (removed at exit; a leftover from a crash is ignored once its PID is
# gone). That is how a lock holder is recognised as a peer — on Windows DuckDB's
# lock error does not even name the holder PID. A marker records the holder's
# process start time too, so a reused PID does not read as a live peer (#355);
# and registering sweeps the directory's stale markers, because ``stop.ps1``
# kills the dashboard and ``atexit`` never runs, so leftovers pile up (#368).
_PRESENCE_PREFIX = ".rc-proc-"
_PRESENT_IN: set[str] = set()
_PRESENCE_LOCK = threading.Lock()


def _presence_file(directory: Path, pid: int) -> Path:
    return directory / f"{_PRESENCE_PREFIX}{pid}"


def _read_marker(f: Path) -> tuple[int | None, str | None]:
    """``(pid, start)`` from a marker; ``start`` is ``None`` for the old PID-only format."""
    try:
        parts = f.read_text(encoding="ascii").split()
    except OSError:
        return None, None
    if not parts:
        return None, None
    try:
        pid = int(parts[0])
    except ValueError:
        return None, None
    return pid, (parts[1] if len(parts) > 1 else None)


def _marker_is_stale(pid: int, start: str | None) -> bool:
    """True when the marker's process is gone or its PID was reused by another one.

    An old-format marker (no start time) of a live PID is kept: the PID alone decides.
    A start time that cannot be read (access denied, an unsupported OS) also keeps it.
    """
    if not procs.pid_alive(pid):
        return True
    if start is None:
        return False
    live = procs.process_start_time(pid)
    return live is not None and live != start


def _remove_marker(f: Path) -> None:
    try:
        f.unlink(missing_ok=True)
    except OSError:  # best-effort: a marker we cannot remove is ignored
        logger.debug("could not remove presence marker %s", f, exc_info=True)


def _sweep_presence(directory: Path) -> None:
    """Remove stale ``.rc-proc-*`` markers in a store directory (#368).

    Only marker files are considered; a ``.duckdb``, its ``.wal`` or a lock file
    in the same folder is never touched.
    """
    me = os.getpid()
    for f in Path(directory).glob(f"{_PRESENCE_PREFIX}*"):
        pid, start = _read_marker(f)
        if pid is None or pid == me:
            continue
        if _marker_is_stale(pid, start):
            _remove_marker(f)


def _register_presence(path: Path) -> None:
    d = Path(path).parent
    key = str(d)
    if key in _PRESENT_IN:
        return
    with _PRESENCE_LOCK:
        if key in _PRESENT_IN:
            return
        _sweep_presence(d)
        f = _presence_file(d, os.getpid())
        start = procs.process_start_time(os.getpid()) or ""
        try:
            f.write_text(f"{os.getpid()} {start}".strip(), encoding="ascii")
            atexit.register(f.unlink, missing_ok=True)
        except OSError:  # read-only dir etc.: presence is best-effort
            logger.debug("could not write presence file %s", f, exc_info=True)
        _PRESENT_IN.add(key)


def _peer_pids(path: Path) -> list[int]:
    """Live RevenueChaser processes (other than this one) using ``path``'s dir."""
    me = os.getpid()
    out = []
    for f in Path(path).parent.glob(f"{_PRESENCE_PREFIX}*"):
        pid, start = _read_marker(f)
        if pid is None or pid == me:
            continue
        if _marker_is_stale(pid, start):
            _remove_marker(f)  # a crashed process's leftover, or a reused PID
        else:
            out.append(pid)
    return out


def _holder_is_peer(msg: str, path: Path) -> bool:
    """True when the process holding the lock is another RevenueChaser process."""
    peers = _peer_pids(path)
    m = _LOCK_HOLDER_RE.search(msg)
    if m:  # POSIX names the holder: it must be one of ours
        return int(m.group("pid")) in peers
    return bool(peers)  # Windows does not: any live peer is the likely holder


def _foreign_lock(msg: str) -> bool:
    """True when the message says a *different* process owns the file lock."""
    low = msg.lower()
    if not any(k in low for k in _FOREIGN_LOCK_MARKERS):
        return False
    m = _LOCK_HOLDER_RE.search(msg)
    return not m or int(m.group("pid")) != os.getpid()


def _connect_with_retry(delays: tuple[float, ...], path: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Open the DuckDB file with retry semantics and attach serialization.

    Combines process-wide attach serialization (_ATTACH_LOCK) with foreign-lock
    detection and actionable StoreLockedError enrichment. The attach/detach are
    serialized; the lock is not held across transactions. A foreign lock held by
    a RevenueChaser peer keeps (at least) the full reader budget; any other
    foreign holder fails fast.
    """
    if path is None:
        raise RawStoreError("no store file named: only the board files are left (#860)")
    path = Path(path)
    if path.parent.name == BOARDS_DIRNAME:
        path.parent.mkdir(parents=True, exist_ok=True)   # the first write of a board makes its folder
    last: Exception | None = None
    i = 0
    judged = False
    while True:
        try:
            with _ATTACH_LOCK:
                conn = duckdb.connect(str(path))
            _register_presence(path)
            return conn
        except duckdb.Error as exc:
            last = exc
            if not judged and _foreign_lock(str(exc)):
                judged = True
                if _holder_is_peer(str(exc), path):
                    if sum(delays) < sum(_PEER_LOCK_DELAYS):
                        delays = _FOREIGN_LOCK_DELAYS if getattr(_LOCAL, "brief", False) else _PEER_LOCK_DELAYS
                else:
                    delays = _FOREIGN_LOCK_DELAYS
            if not _conflict(exc) or i >= len(delays):
                break
        logger.debug("connect contention, retrying in %.2fs: %s", delays[i] if i < len(delays) else 0, last)
        time.sleep(delays[i] if i < len(delays) else 0)
        i += 1
    detail = str(last).strip().replace("\n", " ") if last else ""
    if _foreign_lock(detail):
        raise _lock_error(detail, path) from last
    raise RawStoreError(
        f"could not open {path}: {detail}{_open_failure_hint(detail)}") from last


@contextmanager
def connect(read_only: bool = False, db: str | None = None):
    """Open a connection for one operation; always closes. Retries on lock.

    ``db`` names the board file (one of ``BOARD_DBS``); the old files are gone (#860). ``read_only`` is ADVISORY: it only selects the retry budget, and every handle is opened
    read-write. DuckDB refuses a second connection to the same file with a
    *different* configuration in the same process::

        ConnectionException: Can't open a connection to same database file
        with a different configuration than existing connections

    and this app reads and writes the store concurrently in one process — the
    dashboard's request threads read while ``app/jobs.py``'s in-process worker
    thread runs a module writer. Opening every handle the same way makes those
    coexist; cross-process contention is still handled by the lock retry.

    Inside ``session()`` the operation gets a cursor on the session's handle
    instead of opening the file again (its own connection, so transactions
    stay independent).
    """
    path = _db_path(db)
    held = _session_handle(path, read_only)
    if held is not None:
        cur = held.cursor()
        try:
            yield cur
        finally:
            cur.close()
        return
    conn = _connect_with_retry(delays=_READ_DELAYS if read_only else _WRITE_DELAYS,
                               path=path)
    try:
        yield conn
    finally:
        # Detach is serialized too (see _ATTACH_LOCK): on Windows a close() can
        # leave the file lock held a beat after it returns, which would make a
        # neighbouring thread's connect() fail spuriously.
        with _ATTACH_LOCK:
            conn.close()


# ── sessions: one handle for a burst of operations ──────────────────────────
# Opening the file is the dominant cost of a small operation (~100 ms on the
# 500 MB store: DuckDB loads the catalog and checkpoints on close), while an
# operation on an already-open database costs < 1 ms. A session keeps ONE handle
# per file open for the duration of a ``with`` block on this thread — a
# dashboard request, a render — and closes it at the end, so the file lock is
# still released between bursts and never held across an idle period. While a
# handle is open, other threads' ``connect()`` also re-use the cached database
# instance, so they get cheap too. Handles are opened lazily: a session that
# never touches edgar.duckdb never locks it.
_LOCAL = threading.local()


def _sessions() -> dict:
    s = getattr(_LOCAL, "sessions", None)
    if s is None:
        s = _LOCAL.sessions = {}
    return s


def _session_handle(path: Path, read_only: bool):
    entry = _sessions().get("depth")
    if not entry:
        return None
    handles = _sessions().setdefault("handles", {})
    key = str(path)
    conn = handles.get(key)
    if conn is None:
        conn = _connect_with_retry(delays=_READ_DELAYS if read_only else _WRITE_DELAYS,
                                   path=path)
        handles[key] = conn
    return conn


@contextmanager
def session():
    """Share one handle per store file across every operation in the block.

    Re-entrant (nested sessions share the outer one). Thread-local: other
    threads keep their own semantics. Keep the block short — a held handle
    blocks OTHER processes (a scheduled job waits for it), so wrap one request
    or one render, never a long-running job.
    """
    s = _sessions()
    s["depth"] = s.get("depth", 0) + 1
    try:
        yield
    finally:
        s["depth"] -= 1
        if s["depth"] == 0:
            handles = s.pop("handles", {})
            for conn in handles.values():
                with _ATTACH_LOCK:
                    try:
                        conn.close()
                    except Exception:  # noqa: BLE001 - closing is best-effort
                        logger.debug("session close failed", exc_info=True)


# DuckDB uses optimistic concurrency, so two transactions that touch the SAME
# row both start fine and the loser fails LATER — after connect, which is why
# the connect-level retry above cannot help and the whole operation is retried.
# It loses in two different ways:
#   - at COMMIT ("Failed to commit: ... duplicate key");
#   - mid-statement, because INSERT ... ON CONFLICT cannot see a row the other
#     transaction has not committed yet, so both attempt a plain insert and one
#     gets "Duplicate key ... violates primary key constraint".
# Reachable whenever two request threads write one row (two rapid
# /api/watchlist/toggle calls) or a request races the app/jobs.py worker.
#
# A *genuine* duplicate-key bug produces the same message; it simply raises
# after the budget instead of immediately.
_COMMIT_CONFLICT_MARKERS = (
    "failed to commit",
    "conflict on transaction",
    "transactioncontext error",
    "violates primary key constraint",
    "violates unique constraint",
)


def _commit_conflict(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in _COMMIT_CONFLICT_MARKERS)


def _retry_write(op, delays: tuple[float, ...] = _WRITE_DELAYS):
    """Run a self-contained write, retrying a lost commit race.

    Safe to repeat: a conflicting transaction is rolled back whole, so the
    retry starts from the same state the first attempt saw. A missing table
    (the store was reset/restored under us, invalidating the ``_TABLE_READY``
    memo) is re-created once.
    """
    healed = False
    for i, delay in enumerate(delays):
        try:
            return op()
        except duckdb.CatalogException:
            if healed:
                raise
            healed = True
            _TABLE_READY.clear()
            continue
        except duckdb.Error as exc:
            if not _commit_conflict(exc) or i == len(delays) - 1:
                raise
            logger.debug("write conflict, retrying in %.2fs: %s", delay, exc)
            time.sleep(delay)
    raise RawStoreError("unreachable")  # pragma: no cover


@contextmanager
def _tx(conn):
    """One all-or-nothing unit of work. DuckDB autocommits each statement
    otherwise, so a DELETE+INSERT refresh that fails halfway would commit the
    DELETE and destroy the previous good rows."""
    conn.execute("BEGIN TRANSACTION")
    ready = set(_TABLE_READY)
    try:
        yield conn
    except BaseException:
        _TABLE_READY.difference_update(_TABLE_READY - ready)   # its CREATE rolled back too
        try:
            conn.execute("ROLLBACK")
        except Exception:  # pragma: no cover - rollback of an aborted tx
            logger.debug("rollback failed", exc_info=True)
        raise
    conn.execute("COMMIT")


# ── schema manifest ───────────────────────────────────────────────────────────
# kind: "json_payload" = exact-hash comparable at migration; "tabular" =
# count + key-set + numeric-tolerance comparable.
# write: "upsert" = ON CONFLICT key DO UPDATE; "append" = plain INSERT;
#        "replace" = DELETE rows matching keys, then INSERT.
#
# Column types: a manifest column is written as ``name TYPE``. The storage type
# matters — see docs/plan_store_schema_evolution.md for the full rationale:
#   - scalar columns (TEXT/DOUBLE/...): SELECT-able, filterable in SQL.
#   - ``JSON`` columns: DuckDB's native JSON type, serialized once on write
#     (DuckDB's own Python converter mangles floats in mixed-type arrays, so
#     values are pre-serialized), read back as dicts/lists/scalars by
#     get()/get_all(), and reachable from SQL with path expressions
#     (``payload.market_cap::DOUBLE``).
#   - ``STRUCT(...)`` columns: read back as Python dicts natively.
#   - ``BLOB`` columns listed in ``"compress"`` (``{column: "json"|"text"}``):
#     zlib-compressed on write, decompressed (and JSON-decoded) on read by
#     get()/get_all(). For cells > a few KB, which DuckDB stores uncompressed.
#     Raw SQL sees bytes — read them through get()/get_all().
# group_by: the columns a "replace" batch clears before inserting (default: the
# key). A table written one whole run/entity at a time names that grain here,
# so rows that disappeared from the new batch are removed too.
# history: True marks a table that holds the PAST (the forecast ledger, session
# snapshots, change history; #286). rawstore then refuses to rewrite it:
# ``replace_all``, ``update_columns``, ``delete`` and ``clear`` raise, raw SQL that
# deletes, updates, drops, truncates, merges into or replaces it raises (see
# ``_refuse_history_sql``), and ``write_rows`` becomes first-write-wins whatever the
# ``write`` mode. It needs a ``key`` that is the table's PRIMARY KEY. The flag
# rides the built guard: ``forecast_ledger`` carries it (#286) and so do the schema-11
# change and history tables.
# history_mode: how a table treats the past (data backbone review ADR-1, #281). A label for now:
# rawstore does not read it, ``history`` above is what enforces. Every entry declares one.
#   event            dated facts, one row per event, kept (first write wins)
#   session_snapshot one row per key per NY session, appended
#   change_history   every change of a slow-moving value, with ``valid_from``
#   latest_cache     latest value only, for data that can be fetched or rebuilt again
#   operational      run stamps, pointers and logs of the store itself
# planned: True marks a table whose writer is still to come (data backbone review B15, #289). retired: True
# marks one whose only writer is in the past. Both mean an empty table is expected; they differ in the word a
# future listing prints. The first store call creates either like any other, so without the flag an empty table
# reads as "0 rows", the same as one whose writer broke. Like ``history_mode`` they are data only: rawstore does
# not read either, so neither changes DDL or a write. Drop the flag and the name in
# ``core/tests/test_manifest_planned_289.py`` together when a writer lands, or when a retired table leaves.
HISTORY_MODES = ("event", "session_snapshot", "change_history", "latest_cache", "operational")
_JSON_TYPES = {"JSON"}
_STRUCT_TYPES = {"STRUCT", "UNION"}
_NESTED_TYPES = _JSON_TYPES | _STRUCT_TYPES
MANIFEST: dict[str, dict] = {
    "swing_info": {
        "db": "swing_potential",
        "history_mode": "session_snapshot",
        "key": ["ticker"],
        "columns": ["ticker TEXT PRIMARY KEY", "payload JSON", "cached_at DOUBLE",
                    # #127: epoch seconds at fetch. NULL on rows written before the column (unknown, never 0).
                    # Added by ALTER, no schema bump.
                    "fetched_at DOUBLE"],
        "kind": "json_payload",
        "write": "upsert",
        "sources": ["swing_potential/info/{TICKER}.json"],
    },
    "leaps_cache": {
        "db": "leaps",
        "history_mode": "latest_cache",
        "key": ["ticker"],
        "columns": ["ticker TEXT PRIMARY KEY", "payload JSON",
                    # #127: epoch seconds at fetch. NULL on older rows (unknown, never 0). ALTER, no bump.
                    "fetched_at DOUBLE"],
        "kind": "json_payload",
        "write": "upsert",
        "sources": ["leaps/cache/{TICKER}.json"],
    },
    "rotation_holdings": {
        "db": "sector_rotation",
        "history_mode": "latest_cache",
        "key": ["ticker"],
        "columns": ["ticker TEXT PRIMARY KEY", "date TEXT", "rows JSON",
                    # #127: epoch seconds at fetch. NULL on older rows (unknown, never 0). ALTER, no bump.
                    "fetched_at DOUBLE"],
        "kind": "json_payload",
        "write": "upsert",
        "sources": ["sector_rotation/holdings/{TICKER}.json"],
    },
    # ── Co-movement board (module_comovement) ────────────────────────────────
    "comov_runs": {
        "db": "comovement",
        "history_mode": "event",
        # One dated clustering run. ``config_hash`` covers window/linkage/cuts
        # plus horizon/benchmark, so a config change produces a new as_of
        # instead of reusing members.
        "key": ["as_of"],
        "columns": [
            "as_of TEXT PRIMARY KEY", "generated_at TEXT", "window_days INTEGER",
            "n_tickers INTEGER", "linkage TEXT", "config_hash TEXT",
            "horizon INTEGER", "benchmark TEXT",
            "benchmark_status TEXT", "prices_through TEXT",
            # n_eff: legacy participation ratio, no longer written (runs
            # before 2026-10-01). n_factors: eigenvalues above the MP edge.
            # null_json: grid point -> shuffled-returns null (Refresh reuses it).
            "n_eff DOUBLE", "n_factors INTEGER", "null_json TEXT",
            # cut -> {"held", "total"}: lagged groups that held out-of-sample.
            "oos_json TEXT",
            # First session of the clustered window, last session of the lagged
            # (formation) window, and the universe funnel the header states.
            "window_start TEXT", "oos_start TEXT", "funnel_json TEXT",
            # #379 D2 (card "Kolon + header"): the Fetch that stored the run (its
            # precompute windows share the id; ``result_runs`` holds one
            # header-only row per Fetch), the run's session (rule B on as_of)
            # and its drop lists {dropped, no_prices, flat_prints}, which a
            # reload cannot rebuild. Added to an existing store by
            # ``_reconcile_table`` (ALTER TABLE ADD COLUMN), no schema bump;
            # older runs read NULL.
            "run_id TEXT", "session_date DATE", "dropped_json TEXT",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    "comov_nodes": {
        "db": "comovement",
        "history_mode": "event",
        "key": ["as_of", "cut", "cluster_id"],
        # A run is written whole: "replace" clears the run's old clusters.
        "group_by": ["as_of"],
        "columns": [
            "as_of TEXT", "cut INTEGER", "cluster_id TEXT", "label TEXT",
            "n INTEGER", "mean_corr DOUBLE", "last_residual_pct DOUBLE",
            # The shuffled-returns null (q99 of the groups the same pipeline
            # selects from pure noise) this cluster's mean_corr is judged
            # against. NULL → significance unknown (pre-S8 run, or a Refresh
            # with no persisted null for its config hash).
            "baseline_r DOUBLE",
            # Legacy S9 bootstrap stability: no longer written (removed
            # 2026-09-30, replaced by out-of-sample persistence below).
            "stability DOUBLE",
            # Out-of-sample persistence (module_comovement/persistence.py):
            # best Jaccard to a group formed a quarter earlier, whether that is
            # below the match bar (new), and whether the matched group held on
            # the held-out quarter (its r there vs random names). NULL = no
            # lagged test for this run.
            "persist_jaccard DOUBLE", "persist_new BOOLEAN", "persist_held BOOLEAN",
            "oos_r DOUBLE", "oos_base DOUBLE",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    "comov_members": {
        "db": "comovement",
        "history_mode": "event",
        "key": ["as_of", "cut", "ticker"],
        "group_by": ["as_of"],
        "columns": ["as_of TEXT", "cut INTEGER", "cluster_id TEXT", "ticker TEXT",
                    # ``core``: the name was in the matching group a quarter
                    # ago (persistence.core_members); False = joined since;
                    # NULL = no lagged match. ``stability`` is the legacy S9
                    # bootstrap value, no longer written.
                    "stability DOUBLE", "core BOOLEAN"],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    "comov_lag": {
        "db": "comovement",
        "history_mode": "event",
        # Groups formed on the window ending a quarter before the run, with
        # their held-out-quarter test (Fetch-only). A Refresh re-matches its
        # groups against the latest run's rows with the same config hash.
        "key": ["as_of", "cut", "ticker"],
        "group_by": ["as_of"],
        "columns": ["as_of TEXT", "cut INTEGER", "lag_id TEXT", "ticker TEXT",
                    "oos_r DOUBLE", "oos_base DOUBLE", "held BOOLEAN"],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    # ── Value Chain board (module_value_chain) ───────────────────────────────
    "chain_filings": {
        "history_mode": "latest_cache",
        # One row per issuer: the latest 10-K (else 20-F) we sliced, with the
        # Item 1/4 text and a quality flag. ``accession`` lets a re-run skip
        # unchanged filings.
        # ``item_text`` (~50 KB of prose per issuer) is zlib-compressed (3x):
        # DuckDB stores strings that size uncompressed. It is re-derivable from
        # the durable edgar_docs/ HTML, so this is a cache of the slice.
        "key": ["ticker"],
        "columns": [
            "ticker TEXT PRIMARY KEY", "cik TEXT", "form TEXT", "filed TEXT",
            "accession TEXT", "primary_doc TEXT", "item_text BLOB", "quality TEXT",
            "fetched_at DOUBLE",
        ],
        "compress": {"item_text": "text"},
        "kind": "tabular",
        "write": "upsert",
        "db": "value_chain",
        "sources": [],
    },
    "chain_mentions": {
        "history_mode": "latest_cache",
        # src = filing issuer, dst_name = the mentioned company, relation in
        # supplier / customer / competitor / other. dst_ticker is empty when the
        # name is private/unresolved.
        "key": ["src", "dst_name", "relation"],
        "columns": [
            "src TEXT", "dst_name TEXT", "dst_ticker TEXT", "relation TEXT",
            "snippet TEXT", "filed TEXT",
            # #387 D7 (DF57): the share of the filer's sales or purchases a concentration sentence states
            # ("Apple accounted for 29.8% of our net sales" -> 29.8); NULL on a keyword edge. Added to an
            # existing store, and to the value_chain_edges_history mirror, by ``_reconcile_table``
            # (ALTER TABLE ADD COLUMN) on the first store call.
            "share_pct DOUBLE",
            # #410: where the edge came from: ``profile`` (the Relatedness profile's customers / suppliers /
            # competitors), ``xbrl`` (the annual report's major customers) or ``regex`` (sentences and keywords);
            # NULL on an edge stored before the column. Added like ``share_pct``.
            "source TEXT",
        ],
        "kind": "tabular",
        "write": "replace",
        "db": "value_chain",
        "sources": [],
    },
    "chain_meta": {
        "history_mode": "latest_cache",
        "key": ["key"],
        "columns": ["key TEXT PRIMARY KEY", "value TEXT",
                    # #127: epoch seconds at fetch. NULL on older rows (unknown, never 0). ALTER, no bump.
                    "fetched_at DOUBLE"],
        "kind": "tabular",
        "write": "replace",
        "db": "value_chain",
        "sources": [],
    },
    # #26 PL7: this file's schema stamp (row key ``schema_version``). The same table is created in every
    # store file by ``_apply_schema_stamp``; this entry is the column contract and the raw copy. Not
    # ``store_meta``'s ticker-store ``schema_version`` (that value is ``"3"``). Additive: no version bump.
    "store_schema": {
        "history_mode": "latest_cache",
        "key": ["key"],
        "columns": ["key TEXT PRIMARY KEY", "value TEXT"],
        "kind": "tabular",
        "write": "upsert",
        "sources": [],
    },
    # ── tabular stores ───────────────────────────────────────────────────────
    "ticker_themes": {
        "db": "relatedness",
        "history_mode": "event",
        # Runtime theme SSoT. ``theme_id`` is the join key (stable slug), ``theme``
        # is the display label. ``theme_run_id`` separates the legacy keyword
        # themes (Phase 1) from each NMF run (Phase 8); the same theme in a later
        # run is a different row. See core/ticker_themes.py.
        "key": ["ticker", "theme_id", "theme_run_id"],
        "columns": [
            "ticker TEXT", "theme_id TEXT", "theme TEXT", "level TEXT",
            "theme_run_id TEXT",
            # #127: epoch seconds when the row was written. NULL on older rows (unknown, never 0). ALTER, no bump.
            "fetched_at DOUBLE",
            "PRIMARY KEY (ticker, theme_id, theme_run_id)",
        ],
        "kind": "tabular",
        "write": "upsert",
        "sources": [],
    },
    "fundamentals_scores": {
        "db": "fundamentals",
        "history_mode": "latest_cache",
        # Per-ticker OWN metrics only (no identity/GICS — those live on
        # equity_universe). Single writer: module_fundamentals/scores.py
        # (replace_all full refresh).
        "key": ["ticker"],
        "columns": [
            "ticker TEXT PRIMARY KEY", "period TEXT", "multiplier INTEGER",
            "distorted INTEGER", "quality_pass INTEGER", "momentum_pass INTEGER",
            "ro40 DOUBLE", "rev_growth_ttm DOUBLE", "fcf_margin DOUBLE",
            "ttm_revenue DOUBLE", "gross_margin DOUBLE", "roic DOUBLE",
            "net_debt_ebitda DOUBLE", "pe DOUBLE", "pb DOUBLE",
            "dist_52w_pct DOUBLE", "rs_6m DOUBLE", "above_200d INTEGER",
            # #386 F1: additive (the history mirror follows through ``_mirror_entry``)
            "ro40_basis TEXT", "anchor_period_end TEXT", "price DOUBLE", "market_cap DOUBLE",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    "fundamentals_gates": {
        "db": "fundamentals",
        "history_mode": "latest_cache",
        # One typed row per (ticker, gate, rule) — filterable.
        "key": ["ticker", "gate", "rule_id"],
        "columns": [
            "ticker TEXT", "gate TEXT", "rule_id TEXT", "passed INTEGER",
            "actual DOUBLE", "unit TEXT",
            "PRIMARY KEY (ticker, gate, rule_id)",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    "swing_scores": {
        "db": "swing_potential",
        "history_mode": "latest_cache",
        "key": ["ticker"],
        "columns": [
            "ticker TEXT PRIMARY KEY", "multiplier INTEGER", "quality DOUBLE",
            "rs_rating DOUBLE", "price DOUBLE", "change_pct DOUBLE",
            "change_1w DOUBLE", "change_1m DOUBLE", "entry DOUBLE",
            "target DOUBLE", "stop DOUBLE", "rr DOUBLE", "atr DOUBLE",
            "ma_alignment TEXT",
            "direction_ok INTEGER", "m_pass INTEGER", "w_pass INTEGER", "q_pass INTEGER",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    "swing_gates": {
        "db": "swing_potential",
        "history_mode": "latest_cache",
        "key": ["ticker", "gate", "rule_id"],
        "columns": [
            "ticker TEXT", "gate TEXT", "rule_id TEXT", "passed INTEGER",
            "actual DOUBLE", "unit TEXT",
            "PRIMARY KEY (ticker, gate, rule_id)",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    # ── Relatedness (Phase 6) ────────────────────────────────────────────────
    "llm_cache": {
        "db": "relatedness",
        "history_mode": "event",
        # Structured cache key over (model, thinking, effort, prompt_version,
        # ticker, input_hash). Response is the raw JSON. Durable (raw.duckdb).
        "key": ["cache_key"],
        "columns": [
            "cache_key TEXT PRIMARY KEY", "ticker TEXT", "cik TEXT", "model TEXT",
            "thinking INTEGER", "effort TEXT", "prompt_version TEXT",
            "input_hash TEXT", "response JSON", "fetched_at DOUBLE", "status TEXT",
        ],
        "kind": "tabular",
        "write": "upsert",
        "sources": [],
    },
    "relatedness_profiles": {
        "db": "relatedness",
        "history_mode": "latest_cache",
        # One row per ticker; profile job grain is CIK (dual-class shares one
        # item_text), so cache_key is keyed on cik+input_hash.
        "key": ["ticker"],
        "columns": [
            "ticker TEXT PRIMARY KEY", "cik TEXT", "model TEXT",
            "prompt_version TEXT", "fetched_at DOUBLE", "cache_key TEXT",
            "status TEXT",
            # LLM tries that ended in an empty profile (retried up to 3 runs).
            "attempts INTEGER",
            # The writer's provider beside its model (#360: evren / deepseek / grok). Nullable, added by
            # ``_reconcile_table`` (ALTER TABLE ADD COLUMN), no schema bump.
            "provider TEXT",
            # Relatedness v2 (#401, schema 13): the v3 structured profile (summary, segments, customers,
            # suppliers, named_competitors, business_model, channel, geography, stage, keywords) and, per field,
            # which chunk or table its value came from under the merge rule. Nullable: a v2 row reads NULL.
            "profile_json JSON", "label_source JSON",
        ],
        "kind": "tabular",
        "write": "upsert",
        "sources": [],
    },
    "relatedness_embeddings": {
        "db": "relatedness",
        # Relatedness v2 Step 2 (#401, schema 13): one vector per ticker and embedding model (raw BLOB, not
        # ``compress``: it is binary already). Writer: ``module_relatedness/embeddings.py`` (#669); the blob is a
        # 16-byte hash of the embedded text, then the float32 bytes of ``dim`` values.
        "history_mode": "latest_cache",
        "key": ["ticker", "model"],
        "columns": [
            "ticker TEXT", "model TEXT", "dim INTEGER", "vector BLOB",
            "PRIMARY KEY (ticker, model)",
        ],
        "kind": "tabular",
        "write": "upsert",
        "sources": [],
    },
    "relatedness_attributes": {
        "db": "relatedness",
        "history_mode": "latest_cache",
        "key": ["ticker", "field"],
        # A profile is written whole: "replace" clears the ticker's old fields.
        "group_by": ["ticker"],
        "columns": [
            "ticker TEXT", "field TEXT", "value TEXT", "value_num DOUBLE",
            "PRIMARY KEY (ticker, field)",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    "relatedness_scores": {
        "db": "relatedness",
        "history_mode": "latest_cache",
        "key": ["ticker", "peer"],
        "columns": [
            "ticker TEXT", "peer TEXT", "score DOUBLE",
            "PRIMARY KEY (ticker, peer)",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    "theme_runs": {
        "db": "relatedness",
        "history_mode": "event",
        # One NMF theme run (Phase 8). ``is_current`` pins the cut-over run.
        "key": ["id"],
        "columns": [
            "id TEXT PRIMARY KEY", "created_at TEXT", "k_fine INTEGER",
            "k_medium INTEGER", "k_coarse INTEGER", "jaccard DOUBLE",
            "is_current INTEGER", "session_date DATE", "run_at DOUBLE",
            # Relatedness v2 Step 0 (#341, avo 1 Nov 2026): the run's validation numbers
            # (module_relatedness/validation/metrics.py, THEME_RUNS_COLUMNS). Nullable; added to an existing
            # store by ``_reconcile_table`` (ALTER TABLE ADD COLUMN) on the first store call, no schema bump.
            "val_peer_recall_25 DOUBLE", "val_hand_precision_10 DOUBLE", "val_gics_purity DOUBLE",
            "val_etf_recall_medium DOUBLE", "val_seed_ari DOUBLE",
        ],
        "kind": "tabular",
        "write": "upsert",
        "sources": [],
    },
    "relatedness_themes": {
        "db": "relatedness",
        "history_mode": "event",
        "key": ["theme_id"],
        "columns": [
            "theme_id TEXT PRIMARY KEY", "level TEXT", "parent_id TEXT",
            "label TEXT", "size INTEGER",
        ],
        "kind": "tabular",
        "write": "upsert",
        "sources": [],
    },
    "relatedness_theme_tags": {
        "db": "relatedness",
        "history_mode": "event",
        "key": ["theme_id", "tag"],
        "columns": [
            "theme_id TEXT", "tag TEXT", "rank INTEGER",
            "PRIMARY KEY (theme_id, tag)",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    "relatedness_theme_members": {
        "db": "relatedness",
        "history_mode": "event",
        "key": ["ticker", "theme_id"],
        "columns": [
            "ticker TEXT", "theme_id TEXT", "weight DOUBLE",
            "PRIMARY KEY (ticker, theme_id)",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    "relatedness_theme_etfs": {
        "db": "relatedness",
        "history_mode": "event",
        # Top ETFs whose holdings overlap a theme node (fine/medium/coarse).
        # Written by module_relatedness.themes.match_theme_etfs (store-only).
        "key": ["theme_id", "etf"],
        "columns": [
            "theme_id TEXT", "etf TEXT", "etf_name TEXT", "group_name TEXT",
            "overlap DOUBLE", "rank INTEGER",
            "PRIMARY KEY (theme_id, etf)",
        ],
        "kind": "tabular",
        "write": "replace",
        "group_by": ["theme_id"],
        "sources": [],
    },
    "rotation_snapshots": {
        "db": "sector_rotation",
        "history_mode": "session_snapshot",
        "key": ["as_of_date", "ticker"],
        "group_by": ["as_of_date"],
        "columns": [
            "as_of_date TEXT", "ticker TEXT", "name TEXT", '"group" TEXT',
            "close_price DOUBLE", "rs_1w DOUBLE", "rs_1m DOUBLE", "rs_3m DOUBLE",
            "rs_ratio DOUBLE", "rs_momentum DOUBLE", "rs_ratio_z DOUBLE",
            "rs_momentum_z DOUBLE", "quadrant TEXT",
            "benchmark TEXT", "generated_at TEXT", "source TEXT",    # source: live (Rotation Fetch) / backfill (#374)
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": ["sector_rotation/snapshots/{ASOF}.json"],
    },
    "leaps_flow_prints": {
        "db": "leaps",
        "history_mode": "event",
        "key": ["id"],
        "columns": [
            "id TEXT PRIMARY KEY", "ticker TEXT", "strike DOUBLE", "expiry TEXT",
            "premium DOUBLE", "size INTEGER", "option_type TEXT", "delta DOUBLE",
            "next_earnings_date TEXT", "executed_at TEXT", "discovered_at TEXT",
            "ask_vol DOUBLE", "bid_vol DOUBLE", "source TEXT", "fetched_at DOUBLE",
            "session_date DATE", "run_at DOUBLE",
        ],
        "kind": "tabular",
        "write": "append",
        "sources": ["leaps/radar.db"],
    },
    "ticker_scores": {
        "db": "asymmetric_growth",
        "history_mode": "latest_cache",
        "key": ["ticker"],
        "columns": [
            "ticker TEXT PRIMARY KEY", "name TEXT", "sector TEXT", "industry TEXT",
            "industry_group TEXT", "sub_industry TEXT",
            "price DOUBLE", "market_cap DOUBLE", "ps_ratio DOUBLE", "rev_growth DOUBLE",
            "gross_margin DOUBLE", "fcf DOUBLE", "runway_years DOUBLE",
            "rd_intensity DOUBLE", "dilution_yoy DOUBLE", "earnings_date DOUBLE",
            "total_points INTEGER", "tech_breakthrough INTEGER",
            "dilution_warning INTEGER", "us_listed INTEGER", "source TEXT",
            "inst_holders INTEGER", "inst_new INTEGER", "inst_exited INTEGER",
            "inst_buy_flow DOUBLE", "inst_sell_flow DOUBLE", "inst_shares DOUBLE",
            "inst_shares_delta_pct DOUBLE", "inst_ownership_pct DOUBLE",
            "themes TEXT", "signals TEXT",
            # #380 AG W1 (additive): S2 the tier, the C18 flags (JSON list) and the model version that scored the row;
            # S3 the fiscal years and period ends the card read (JSON object)
            "tier INTEGER", "flags TEXT", "model_version TEXT",
            "anchor_fy INTEGER", "prior_fy INTEGER", "period_ends TEXT",
        ],
        "kind": "tabular",
        "write": "upsert",
        "sources": ["ticker_store/tickers.db"],
    },
    # Implied Probability (OIPD) board: the UW option chain for one ticker,
    # normalised so the risk-neutral surface can be re-fit on Refresh with zero
    # network. One ticker's chain is replaced per fetch (group_by ticker).
    "oipd_chain": {
        "db": "oipd",
        "history_mode": "latest_cache",
        "key": ["ticker", "option_symbol"],
        "group_by": ["ticker"],
        "columns": [
            "ticker TEXT", "option_symbol TEXT", "expiry TEXT", "option_type TEXT",
            "strike DOUBLE", "bid DOUBLE", "ask DOUBLE", "last_price DOUBLE",
            "volume DOUBLE", "open_interest DOUBLE", "iv DOUBLE", "delta DOUBLE",
            "tape_time TEXT", "fetched_at TEXT",
        ],
        "kind": "tabular",
        "write": "replace",
        "sources": [],
    },
    # One row per fetched ticker: the download context (asof/spot/rate/horizon)
    # the fit needs, plus provenance for /api/data_asof.
    "oipd_meta": {
        "db": "oipd",
        "history_mode": "latest_cache",
        "key": ["ticker"],
        "columns": [
            "ticker TEXT PRIMARY KEY", "as_of TEXT", "spot DOUBLE",
            "risk_free DOUBLE", "expiry_count INTEGER", "horizon_days INTEGER",
            "fetched_at TEXT",
        ],
        "kind": "tabular",
        "write": "upsert",
        "sources": [],
    },
    # The shared forecast ledger (#128 / #62 D-3, schema v8): every board's frozen
    # forecasts in one table. Forecast-only and append-only (decision 5-B): ``append``
    # is ON CONFLICT DO NOTHING, so the first write for a key wins and nothing is
    # ever updated; outcomes go to the derived ``forecast_outcomes`` table below
    # (62b-1). ``target_date`` (the session the forecast resolves
    # on) is in the key so a 0DTE and a weekly SPX pin on one day both persist; for
    # picks it is the forecast date. Manifest only: the writer is core/ledger.py (#128).
    # ``history: True`` (#286) makes rawstore enforce the append-only rule, so the
    # frozen picks can no longer be rewritten by a cleanup script or a refactor.
    "forecast_ledger": {
        "db": "forecast",
        "history": True,
        "history_mode": "session_snapshot",
        "key": ["source", "forecast_date", "subject", "target_type", "target_date"],
        "columns": [
            "source TEXT", "forecast_date DATE", "subject TEXT", "target_type TEXT",
            "target_date DATE NOT NULL", "frozen_at DOUBLE", "run_id TEXT",
            "model_version TEXT", "rank INTEGER", "score DOUBLE", "bucket TEXT",
            "probs JSON", "market_cap DOUBLE", "sector TEXT", "shown_price DOUBLE",
            "stop DOUBLE", "target DOUBLE",
            "PRIMARY KEY (source, forecast_date, subject, target_type, target_date)",
        ],
        "kind": "tabular",
        "write": "append",
        "sources": [],
    },
    # What happened after each frozen forecast (#62 62b-1, #380 S0; decision 5-B): derived from
    # ``forecast_ledger`` and the D01 bars, recomputed, never a fact of its own, so it is a keyed upsert
    # (``latest_cache``) beside the append-only ledger. Key = the ledger's key + ``horizon_days``: a pick
    # gets one row per horizon (30 and 90 calendar days); a dated target (an SPX pin, its own writer
    # later) gets one row with ``horizon_days`` = target_date - forecast_date, so no key column is NULL.
    # ``ref_price``/``mfe``/``mae`` are on the D01 nominal basis; ``status`` is open / closed / no_bars / split_check.
    # Additive (no schema bump). Writer: core/outcomes.py.
    "forecast_outcomes": {
        "db": "forecast",
        "history_mode": "latest_cache",
        "key": ["source", "forecast_date", "subject", "target_type", "target_date", "horizon_days"],
        "columns": [
            "source TEXT", "forecast_date DATE", "subject TEXT", "target_type TEXT",
            "target_date DATE NOT NULL", "horizon_days INTEGER", "ref_price DOUBLE", "mfe DOUBLE",
            "mae DOUBLE", "sessions_seen INTEGER", "status TEXT", "computed_at DOUBLE",
            "model_version TEXT", "run_id TEXT",
            "PRIMARY KEY (source, forecast_date, subject, target_type, target_date, horizon_days)",
        ],
        "kind": "tabular",
        "write": "upsert",
        "sources": [],
    },
    # What the same day's universe did after a freeze date (#25 HR-1), so a pick's hit rate has something to be
    # judged against. Derived from the universe snapshot and the D01 bars, recomputed, never a fact of its own, so a
    # keyed upsert beside ``forecast_outcomes``. Key ``(forecast_date, horizon_days, basis)``: one row for the whole
    # universe (``basis`` 'universe') and one per trailing-volatility decile ('vol_decile_1' .. 'vol_decile_10', 1 the
    # calmest; always all ten, so the set of keys never changes shape). ``n`` counts the members with a usable
    # reference price; ``ge20``/``ge10``/``ge5`` are cumulative MFE thresholds (>= 20%, >= 10%, >= 5%). A decile's
    # ``vol_lo``/``vol_hi`` are the realised-vol range it covers (``vol_lo`` inclusive, ``vol_hi`` exclusive, NULL at
    # either end), so a pick's own trailing vol maps to one basis without a second table. ``status`` is open / closed
    # like the outcomes, and ``mae_mean`` is there because "up 5% on average" means something else with a -40%
    # drawdown. Additive (no schema bump; the ``forecast_outcomes`` precedent). Writer: core/baselines.py.
    "forecast_baselines": {
        "db": "forecast",
        "history_mode": "latest_cache",
        "key": ["forecast_date", "horizon_days", "basis"],
        "columns": [
            "forecast_date DATE", "horizon_days INTEGER", "basis TEXT",
            "n INTEGER", "ge20 INTEGER", "ge10 INTEGER", "ge5 INTEGER",
            "mfe_mean DOUBLE", "mae_mean DOUBLE", "vol_lo DOUBLE", "vol_hi DOUBLE",
            "status TEXT", "computed_at DOUBLE", "model_version TEXT", "run_id TEXT",
            "PRIMARY KEY (forecast_date, horizon_days, basis)",
        ],
        "kind": "tabular",
        "write": "upsert",
        "sources": [],
    },
    # News board (plan 2026-11-09, DECISIONS S9/S16): its own boards/news.duckdb, one writer (module_news),
    # written incrementally: upserts by key, retired events marked, never a whole-table rewrite.
    "news_events": {
        "key": ["event_ts", "event", "type"],
        "columns": [
            "event_ts DOUBLE", "event TEXT", "type TEXT", "importance INTEGER", "forecast TEXT", "prev TEXT",
            "reported_period TEXT", "first_seen DOUBLE", "last_seen DOUBLE", "retired_at DOUBLE",
            "run_id TEXT", "run_at DOUBLE", "PRIMARY KEY (event_ts, event, type)",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "news", "sources": [],
    },
    "news_highlight": {
        "key": ["session_date"],
        "columns": [
            "session_date DATE PRIMARY KEY", "event_ts DOUBLE", "event TEXT", "type TEXT", "importance INTEGER",
            "forecast TEXT", "prev TEXT", "text TEXT", "text_source TEXT", "run_id TEXT", "run_at DOUBLE",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "news", "sources": [],
    },
    "news_headlines": {
        "key": ["headline_id"],
        "columns": [
            "headline_id TEXT PRIMARY KEY", "provider TEXT", "published_at DOUBLE", "headline TEXT", "source TEXT",
            "tickers TEXT", "url TEXT", "fetched_at DOUBLE", "run_id TEXT", "run_at DOUBLE",
            # The X lane (module_news/x_feed.py): the tweet's kind and option code, and for an option tweet its check
            # against UW's prints (module_news/x_check.py, JSON text); NULL for every other provider.
            "kind TEXT", "option TEXT", "x_check TEXT",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "news", "sources": [],
    },
    "news_meta": {
        "key": ["key"],
        "columns": ["key TEXT PRIMARY KEY", "value TEXT", "run_at DOUBLE"],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "news", "sources": [],
    },
    # Welcome board (S9, S16): its own file boards/welcome.duckdb, written only by module_welcome/build.py.
    "welcome_snapshot": {
        "key": ["series", "session_date"],
        "columns": [
            "series TEXT", "session_date DATE", "close DOUBLE", "prev_close DOUBLE", "change DOUBLE",
            "change_pct DOUBLE", "spark TEXT", "run_id TEXT", "run_at DOUBLE", "PRIMARY KEY (series, session_date)",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "welcome", "sources": [],
    },
    "welcome_earnings": {
        "key": ["earnings_date", "ticker", "report_session"],
        "columns": [
            "earnings_date DATE", "ticker TEXT", "report_session TEXT", "full_name TEXT", "expected_move_perc DOUBLE",
            "report_time TEXT", "source_session DATE", "first_seen DOUBLE", "last_seen DOUBLE", "retired_at DOUBLE",
            "run_id TEXT", "run_at DOUBLE", "PRIMARY KEY (earnings_date, ticker, report_session)",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "welcome", "sources": [],
    },
    "welcome_freshness": {
        "key": ["job"],
        "columns": [
            "job TEXT PRIMARY KEY", "last_status TEXT", "last_finished_at DOUBLE", "last_ok_at DOUBLE",
            "last_failed_at DOUBLE", "last_error TEXT", "run_id TEXT", "run_at DOUBLE",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "welcome", "sources": [],
    },
    "welcome_meta": {
        "key": ["key"],
        "columns": ["key TEXT PRIMARY KEY", "value TEXT", "run_at DOUBLE"],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "welcome", "sources": [],
    },
    # SPX Gamma board (SPX Gamma review 9 Nov 2026, D1-D5): its own file boards/spx_gamma.duckdb, written only by
    # module_spx_gamma/store.py. A raw day and its answers land in one transaction; UW serves no history, so they
    # cannot be fetched again.
    "spx_raw_days": {
        "key": ["session_date"],
        "columns": [
            "session_date DATE PRIMARY KEY", "requested_date TEXT", "api_snapshot_time TEXT", "origin TEXT",
            "spot DOUBLE", "zero_dte_expiry TEXT", "file_count INTEGER", "manifest BLOB", "stored_at DOUBLE",
        ],
        "compress": {"manifest": "json"},
        "kind": "tabular", "write": "upsert", "history_mode": "event", "db": "spx_gamma", "sources": [],
    },
    "spx_raw_files": {
        "key": ["session_date", "file"],
        "columns": [
            "session_date DATE", "file TEXT", "sha256 TEXT", "bytes INTEGER", "body BLOB", "stored_at DOUBLE",
            "PRIMARY KEY (session_date, file)",
        ],
        "compress": {"body": "text"},
        "kind": "tabular", "write": "upsert", "history_mode": "event", "db": "spx_gamma", "sources": [],
    },
    "spx_brier": {
        "key": ["asof_date"],
        "columns": [
            "asof_date DATE PRIMARY KEY", "scenario_probs JSON", "outcome TEXT", "brier DOUBLE", "rule TEXT",
            "target TEXT", "bands JSON", "resolved_on TEXT", "resolved_close DOUBLE", "updated_at DOUBLE",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "event", "db": "spx_gamma", "sources": [],
    },
    "spx_gex_daily": {
        "key": ["session_date"],
        "columns": [
            "session_date DATE PRIMARY KEY", "is_friday_close BOOLEAN", "spot DOUBLE", "net_dex DOUBLE",
            "net_gex_oi DOUBLE", "net_vanna DOUBLE", "live_charm DOUBLE", "vanna_at_spot DOUBLE",
            "charm_live_sum DOUBLE", "matrix_gex DOUBLE", "source_chip TEXT", "regime TEXT", "vix DOUBLE",
            "updated_at DOUBLE",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "session_snapshot", "db": "spx_gamma", "sources": [],
    },
    "spx_meta": {
        "key": ["key"],
        "columns": ["key TEXT PRIMARY KEY", "value TEXT", "updated_at DOUBLE"],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "spx_gamma", "sources": [],
    },
    # 13F board (#732, owner 12 Nov 2026): its own file boards/sec_13f.duckdb, written only by
    # module_sec_13f/store.py. The board reads it until the ownership build or the New York date changes; a period
    # stored as closed is never rewritten.
    "sec13f_board_cells": {
        "key": ["ticker", "period"],
        "columns": [
            "ticker TEXT", "period DATE", "shares DOUBLE", "value DOUBLE", "holders INTEGER", "top10_pct DOUBLE",
            "hhi DOUBLE", "new_holders INTEGER", "exited_holders INTEGER", "buy_flow DOUBLE", "sell_flow DOUBLE",
            "breadth DOUBLE", "breadth_chg DOUBLE", "complete BOOLEAN", "closed BOOLEAN", "stored_at DOUBLE",
            "PRIMARY KEY (ticker, period)",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "event", "db": "sec_13f", "sources": [],
    },
    "sec13f_board_breaks": {
        "key": ["ticker", "period", "kind", "cik"],
        "columns": [
            "ticker TEXT", "period DATE", "kind TEXT", "cik TEXT", "filer_name TEXT", "shares DOUBLE",
            "stored_at DOUBLE", "PRIMARY KEY (ticker, period, kind, cik)",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "event", "db": "sec_13f", "sources": [],
    },
    "sec13f_board_meta": {
        "key": ["key"],
        "columns": ["key TEXT PRIMARY KEY", "value TEXT", "updated_at DOUBLE"],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "sec_13f", "sources": [],
    },
    # Watch lists (#786, avo 12 Nov 2026): his own named lists, each with ordered sections and the symbols as he
    # writes them. Written only by module_watchlists/store.py into boards/watchlists.duckdb. Not a board result:
    # nothing recomputes these rows, so they are only added to, changed and removed one at a time, never replaced.
    # The names are ``wl_*`` and not ``watchlist*`` because the old store already owns ``watchlist`` and
    # ``watchlist_changes`` (the pre-PR-4 tables, kept unwritten until their retirement): a second entry under
    # either name would silently replace it in this dict.
    "wl_list": {
        "key": ["list_id"],
        "columns": [
            "list_id TEXT PRIMARY KEY", "name TEXT", "description TEXT", "position INTEGER",
            # Which job group this list feeds, "" for none: the options build reads "option", LEAPS and Earnings
            # read "stock" (several, comma separated). Empty until the bookmark menu lands; the jobs still read
            # ops.sqlite's two lists today.
            "feeds TEXT", "created_at DOUBLE", "created_by TEXT", "updated_at DOUBLE",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "watchlists", "sources": [],
    },
    "wl_section": {
        "key": ["list_id", "section_id"],
        "columns": [
            "list_id TEXT", "section_id TEXT", "name TEXT", "position INTEGER", "created_at DOUBLE",
            "PRIMARY KEY (list_id, section_id)",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "watchlists", "sources": [],
    },
    # ``symbol`` is avo's own spelling, kept exactly as he wrote it ("NASDAQ:NVDA", "TVC:US10Y-TVC:US02Y"), because
    # it is what goes back out to TradingView. ``exchange`` and ``ticker`` are its two parts, and ``coverage`` says
    # where its data comes from here: us_equity, etf, market_series, derived, or unsupported (#785).
    "wl_item": {
        "key": ["list_id", "symbol"],
        "columns": [
            "list_id TEXT", "symbol TEXT", "section_id TEXT", "position INTEGER", "exchange TEXT", "ticker TEXT",
            "coverage TEXT", "note TEXT", "added_at DOUBLE", "added_by TEXT",
            "PRIMARY KEY (list_id, symbol)",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "operational", "db": "watchlists", "sources": [],
    },
    "wl_change": {
        "key": ["list_id", "symbol", "changed_at", "action"],
        "columns": [
            "list_id TEXT", "symbol TEXT", "action TEXT", "changed_at DOUBLE", "changed_by TEXT", "note TEXT",
            # ``at`` and ``by`` are DuckDB keywords: an unquoted ``at DOUBLE`` fails the whole manifest apply.
            "PRIMARY KEY (list_id, symbol, changed_at, action)",
        ],
        "kind": "tabular", "write": "upsert", "history_mode": "change_history", "db": "watchlists", "sources": [],
    },
}


def table_names() -> list[str]:
    return sorted(MANIFEST)


def _ddl(name: str) -> str:
    spec = MANIFEST[name]
    cols = ",\n    ".join(spec["columns"])
    return f"CREATE TABLE IF NOT EXISTS {name} (\n    {cols}\n)"


def _check(name: str) -> dict:
    spec = MANIFEST.get(name)
    if spec is None:
        raise RawStoreError(f"unknown table in manifest: {name}")
    return spec


def _refuse_history(name: str, spec: dict, action: str) -> None:
    """Raise when ``action`` would rewrite a ``"history": true`` table (#286)."""
    if spec.get("history"):
        raise RawStoreError(
            f"{name} is a history table (MANIFEST \"history\": true): {action} would rewrite the past. "
            f"History is only ever added to: write_rows keeps the first row written for a key.")


# Raw-SQL guard (#286, #308). DuckDB reads the text, not a copy of its tokenizer: ``extract_statements`` splits
# and types it with DuckDB's own parser, and ``json_serialize_plan`` binds it against this connection's catalog,
# so the operator and its target table are the ones DuckDB would run. Every review round found text that the
# hand-written scanner this replaced read differently from DuckDB (#284 findings 1 and 5, N1, N2, N5 and N6:
# qualified names, dollar and E'' literals, ONLY, name characters, the parser's unicode-space pre-pass, ``\r``
# ending a ``--`` comment). Measured on DuckDB 1.5.6 in scripts/research/308_sql_guard_parser.py and
# .hermes/plans_claude/arch/2026-10-04_308_sql_guard_parser.md.
#
# A rewrite is a plan node that deletes (TRUNCATE plans as a DELETE), updates, drops, creates over (``CREATE OR
# REPLACE``), or merges with an UPDATE or DELETE branch (``INSERT ... ON CONFLICT DO UPDATE`` and ``INSERT OR
# REPLACE`` plan as that merge), or an INSERT whose conflict action is neither THROW nor NOTHING. The target is
# matched by name in any catalog or schema. Fail closed: text that spells a flagged name and that DuckDB cannot
# parse or plan is refused. DuckDB plans every statement of the text before any runs, so a table the text
# creates first is unknown to the plan and such text is refused too; send it as separate calls.
_PLAN_SQL = "SELECT json_serialize_plan(?::VARCHAR)"
_PLAN_VERBS = {
    "LOGICAL_DELETE": "DELETE or TRUNCATE",
    "LOGICAL_UPDATE": "UPDATE",
    "LOGICAL_DROP": "DROP",
    "LOGICAL_CREATE_TABLE": "CREATE OR REPLACE TABLE",
    "LOGICAL_MERGE_INTO": "MERGE INTO, INSERT ... ON CONFLICT DO UPDATE or INSERT OR REPLACE",
    "LOGICAL_INSERT": "INSERT with a conflict action that rewrites",
}
_MERGE_KEEPS = {"MERGE_INSERT", "MERGE_DO_NOTHING", "MERGE_ERROR"}
_INSERT_KEEPS = {"THROW", "NOTHING"}


def _as_dict(value) -> dict:
    return value if isinstance(value, dict) else {}


def _plan_rewrites(node) -> list[tuple[str, str | None]]:
    """``(operator, target)`` of every node in a ``json_serialize_plan`` tree that rewrites a table."""
    found: list[tuple[str, str | None]] = []
    if isinstance(node, list):
        for item in node:
            found += _plan_rewrites(item)
        return found
    if not isinstance(node, dict):
        return found
    # A part in a shape this DuckDB version does not use reads as empty or None, which refuses, never allows.
    op, table, info = node.get("type"), _as_dict(node.get("table_info")), _as_dict(node.get("info"))
    if op in ("LOGICAL_DELETE", "LOGICAL_UPDATE"):
        found.append((op, table.get("table")))
    elif op == "LOGICAL_MERGE_INTO":
        actions = set()
        for branch in node.get("actions") or []:
            todo = _as_dict(branch).get("value")
            actions |= {_as_dict(a).get("action_type") for a in (todo if isinstance(todo, list) else [None])}
        if not actions or actions - _MERGE_KEEPS:
            found.append((op, table.get("table")))
    elif op == "LOGICAL_INSERT" and node.get("action_type") not in _INSERT_KEEPS:
        found.append((op, table.get("table")))
    elif op == "LOGICAL_DROP":
        found.append((op, info.get("name")))
    elif op == "LOGICAL_CREATE_TABLE" and info.get("on_conflict") == "REPLACE_ON_CONFLICT":
        found.append((op, info.get("table")))
    for value in node.values():
        if isinstance(value, (dict, list)):
            found += _plan_rewrites(value)
    return found


# The canary (#308): True once this process has seen this DuckDB serialize the plan shapes `_plan_rewrites`
# reads, False when a shape it does not know means the walker cannot be trusted. None = not yet run.
_PLANNER_OK: bool | None = None
# One statement per rewriting shape, planned against the canary's scratch table ``{t}``. Each must plan as a rewrite
# of that table; a test pins this list, so dropping a shape from it fails.
_CANARY_SQL = (
    "DELETE FROM {t}",
    "TRUNCATE {t}",
    "UPDATE {t} SET v = 'x'",
    "DROP TABLE {t}",
    "CREATE OR REPLACE TABLE {t} AS SELECT 1 AS id, 'x' AS v",
    "INSERT OR REPLACE INTO {t} VALUES (1, 'x')",
    "INSERT INTO {t} VALUES (1, 'x') ON CONFLICT (id) DO UPDATE SET v = 'x'",
)


def _planner_understood() -> bool:
    """Whether ``_plan_rewrites`` reads this DuckDB's plan JSON, checked once per process.

    Plans one statement of each rewriting shape (``_CANARY_SQL``: DELETE, TRUNCATE, UPDATE, DROP, CREATE OR
    REPLACE, INSERT OR REPLACE, INSERT ... ON CONFLICT DO UPDATE) against a scratch table and requires a rewrite aimed at
    that table for each. Called only for text that names a flagged table and is not all-SELECT; any miss
    or exception is False, so an unknown plan shape refuses rather than reads as nothing to rewrite.
    """
    global _PLANNER_OK
    if _PLANNER_OK is not None:
        return _PLANNER_OK
    _PLANNER_OK = False
    try:
        with duckdb.connect(":memory:") as conn:
            scratch = "t_planner_canary"
            conn.execute(f"CREATE TABLE {scratch} (id INTEGER PRIMARY KEY, v VARCHAR)")
            for template in _CANARY_SQL:
                sql = template.format(t=scratch)
                plan = json.loads(conn.execute(_PLAN_SQL, [sql]).fetchone()[0])
                targets = {(t or "").casefold() for _, t in _plan_rewrites(plan.get("plans"))}
                if scratch.casefold() not in targets:
                    return False
        _PLANNER_OK = True
    except Exception:
        return False
    return _PLANNER_OK


def _history_rewrite(conn, sql: str) -> tuple[str, str, bool] | None:
    """``(table, what, checked)`` when ``sql`` would rewrite a history table on ``conn``, else None.

    ``checked`` is False when the text names a history table and DuckDB could not parse or plan it; ``what`` is
    then DuckDB's error."""
    flagged = {n.casefold(): n for n, spec in MANIFEST.items() if spec.get("history")}
    low = sql.casefold()
    named = [n for f, n in flagged.items() if f in low]
    if not named:
        # DuckDB matches a table name only as these ASCII letters in any case (no Unicode folding, and U&""
        # identifiers are not implemented: measured in #308), so text without the name cannot reach the table.
        return None
    try:
        statements = conn.extract_statements(sql)
        if all(s.type == duckdb.StatementType.SELECT for s in statements):
            return None
        if not _planner_understood():
            return named[0], "this DuckDB's plan JSON is not the shape the guard reads", False
        plan = json.loads(conn.execute(_PLAN_SQL, [sql]).fetchone()[0])
    except duckdb.Error as e:
        return named[0], f"{type(e).__name__}: {str(e).splitlines()[0]}", False
    if plan.get("error"):
        return named[0], str(plan.get("error_message")).splitlines()[0], False
    if not isinstance(plan.get("plans"), list) or not plan.get("plans"):
        return named[0], "this DuckDB's plan JSON has no statement list", False
    for op, target in _plan_rewrites(plan.get("plans")):
        if target is None:
            return named[0], _PLAN_VERBS[op], True
        if target.casefold() in flagged:
            return flagged[target.casefold()], _PLAN_VERBS[op], True
    return None


def _refuse_history_sql(conn, sql: str) -> None:
    """Raise when raw ``sql`` would rewrite a history table on ``conn``.

    Refused, however the table is spelled (``raw.main.t``, ``"T"``, ``ONLY (t)``) and whatever hides it from a
    text reader: whatever DuckDB plans as DELETE (and TRUNCATE), UPDATE, DROP, CREATE OR REPLACE TABLE, or a
    MERGE with an UPDATE or DELETE branch (and so ``INSERT ... ON CONFLICT DO UPDATE`` and ``INSERT OR
    REPLACE``), plus any text naming the table that DuckDB cannot parse or plan. Covers ``execute``,
    ``transaction().execute`` and ``query``. Outside it: ``ALTER``, and a caller's own ``connect()`` handle.
    """
    hit = _history_rewrite(conn, sql)
    if not hit:
        return
    table, what, checked = hit
    if checked:
        _refuse_history(table, MANIFEST[table], f"raw SQL {what}")
    raise RawStoreError(
        f"{table} is a history table (MANIFEST \"history\": true) and this raw SQL names it, but DuckDB could not "
        f"parse or plan it ({what}), so it could not be checked and is refused. DuckDB plans every statement of "
        f"one call before any runs: send a statement that needs an earlier one's table as its own call. A parameter "
        f"in a select list must be cast, for example ?::VARCHAR.")


def _ensure_table(conn, name: str) -> None:
    """DDL on an EXISTING connection — so a write needs one handle, not two.

    Two steps so a store that predates a MANIFEST column addition keeps
    working (see docs/plan_store_schema_evolution.md, "Still worth doing"):
      1. ``CREATE TABLE IF NOT EXISTS`` (no-op when the table already exists);
      2. ``ALTER TABLE ... ADD COLUMN`` for any manifest column the existing
         table is missing — a plain CREATE IF NOT EXISTS would silently skip
         the new column and the first write would fail with a Binder Error.
      3. a one-time rebuild of a table whose ``compress`` columns predate it.

    Memoised per (file, table) for the life of the process: the DDL plus the
    ``information_schema`` probe cost ~40 ms per write otherwise.
    """
    key = (str(_db_path(_db_of(name))), name)
    if key in _TABLE_READY:
        return
    existing = {r[0]: r[1] for r in conn.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_schema = 'main' AND table_name = ?", [name]).fetchall()}
    _reconcile_table(conn, name, existing)
    _TABLE_READY.add(key)


# (store file, table) pairs already reconciled with MANIFEST in this process.
_TABLE_READY: set[tuple[str, str]] = set()


def _reconcile_table(conn, name: str, existing: dict[str, str],
                     live_pks: dict[str, list[str]] | None = None) -> None:
    """Create ``name`` or bring an existing table up to its MANIFEST spec.

    ``existing`` maps column -> DuckDB data type (empty = table missing). ``live_pks`` maps table ->
    PRIMARY KEY columns for the whole file when the caller already probed it (``_ensure_db_tables``).
    Only a missing column is fixed; every other difference is recorded by ``_note_drift`` (#285).
    """
    if not existing:
        conn.execute(_ddl(name))
        return
    stale = [c for c in (MANIFEST[name].get("compress") or {})
             if c in existing and existing[c].upper() != "BLOB"]
    _note_drift(conn, name, existing, stale, live_pks)
    for c in MANIFEST[name]["columns"]:
        head = c.strip().split(None, 1)[0].strip('"')
        if head in _CONSTRAINT_KEYWORDS:
            continue
        if head not in existing:
            conn.execute(f'ALTER TABLE {name} ADD COLUMN "{head}" {c.split(None, 1)[1]}')
    if stale:
        _rebuild_compressed(conn, name, stale)
        _forget_drift(name)


# ── schema drift (#285, B10) ─────────────────────────────────────────────────────────────────
# ``_reconcile_table`` fixes one difference: a MANIFEST column the live table lacks. A retyped column,
# a changed key or constraint, and a live column the MANIFEST dropped it used to skip without a word
# (and a ``compress`` rebuild then drops the extra column for good). They are recorded here and logged,
# once per (file, table, kind, column) per process. ``schema_drift()`` is what Settings / Data Health will
# list. Nothing migrates by itself. The ``store_meta`` record of it lived in
# raw.duckdb and went with it (#860): the log keeps the history.
_SCHEMA_DRIFT: dict[tuple, dict] = {}
_DRIFT_LOCK = threading.Lock()
_TYPE_CANON: dict[str, str] = {}


def schema_drift() -> list[dict]:
    """Differences between the live store files and the MANIFEST that ``_ensure_table`` left alone.

    One dict per difference: ``db``, ``table``, ``kind`` (``type``, ``key`` or ``extra_column``),
    ``column`` (None for a key), ``live`` (the live type, or the live PRIMARY KEY columns) and
    ``manifest`` (what the MANIFEST declares). A copy, ordered by table; empty when the store matches.
    """
    with _DRIFT_LOCK:
        return [dict(d) for _, d in sorted(_SCHEMA_DRIFT.items(), key=lambda kv: tuple(map(str, kv[0])))]


def _record_drift(name: str, kind: str, column: str | None, live, manifest, rebuilt: bool = False) -> None:
    """Record one difference and log it once. ``rebuilt``: a ``compress`` rebuild of this table follows,
    which recreates it from the MANIFEST, so the difference is replaced, not skipped."""
    db = _db_of(name)
    k = (db, name, kind, column)
    with _DRIFT_LOCK:
        if k in _SCHEMA_DRIFT:
            return
        _SCHEMA_DRIFT[k] = {"db": db, "table": name, "kind": kind, "column": column,
                            "live": live, "manifest": manifest}
    what = {"type": f"column {column!r} is {live}, the MANIFEST says {manifest}",
            "key": f"PRIMARY KEY is {live}, the MANIFEST declares {manifest}",
            "extra_column": f"column {column!r} ({live}) is not in the MANIFEST"}[kind]
    outcome = ("the one-time compress rebuild that follows recreates the table from the MANIFEST, "
               "so this difference is replaced (an extra column's data is dropped)" if rebuilt
               else "skipped, nothing migrates by itself")
    logger.warning("rawstore schema drift in %s.%s: %s; %s", db, name, what, outcome)


def _forget_drift(name: str) -> None:
    """Drop the records of ``name`` after its ``compress`` rebuild recreated it from the MANIFEST: what
    they describe is gone, and ``schema_drift()`` lists differences that exist. The log line stays."""
    db = _db_of(name)
    with _DRIFT_LOCK:
        for k in [k for k in _SCHEMA_DRIFT if k[:2] == (db, name)]:
            del _SCHEMA_DRIFT[k]


def _declared_pk(spec: dict) -> list[str]:
    """The PRIMARY KEY columns a MANIFEST entry declares (inline or as a clause), in order; [] if none."""
    for c in spec["columns"]:
        c = c.strip()
        if c.upper().startswith("PRIMARY KEY") and "(" in c:
            return [x.strip().strip('"') for x in c[c.index("(") + 1:c.rindex(")")].split(",")]
    for c in spec["columns"]:
        head = c.strip().split(None, 1)[0]
        if head.upper() not in _CONSTRAINT_KEYWORDS and " PRIMARY KEY" in c.upper():
            return [head.strip('"')]
    return []


def _live_primary_keys(conn, table: str | None = None) -> dict[str, list[str]]:
    """``{table: PRIMARY KEY columns}`` of one store file (or just ``table``)."""
    sql = ("SELECT table_name, constraint_column_names FROM duckdb_constraints() "
           "WHERE schema_name = 'main' AND constraint_type = 'PRIMARY KEY'")
    params: list = []
    if table:
        sql += " AND table_name = ?"
        params = [table]
    return {t: list(cols) for t, cols in conn.execute(sql, params).fetchall()}


def _canon_type(conn, declared: str) -> str:
    """The name DuckDB itself reports for a declared type (``TEXT`` -> ``VARCHAR``), cached per process."""
    t = _TYPE_CANON.get(declared)
    if t is None:
        t = _TYPE_CANON[declared] = conn.execute(f"SELECT typeof(CAST(NULL AS {declared}))").fetchone()[0]
    return t


def _note_drift(conn, name: str, existing: dict[str, str], skip: list[str],
                live_pks: dict[str, list[str]] | None) -> None:
    """Record what differs between the live ``name`` and its MANIFEST entry (best effort: never a failed write).

    ``skip`` are the columns a ``compress`` rebuild is about to retype, which is a migration, not drift.
    A non-empty ``skip`` also means that rebuild runs next, and it recreates the whole table.
    """
    rebuilt = bool(skip)
    try:
        declared = {col: _base_type(name, col) for col in _columns_of(MANIFEST[name])}
        legacy = set(MANIFEST[name].get("legacy_columns") or ())
        for col, live_type in existing.items():
            if col not in declared:
                if col not in legacy:                   # a known empty leftover, named by the MANIFEST (#431)
                    _record_drift(name, "extra_column", col, live_type, None, rebuilt)
            elif col not in skip:
                want = _canon_type(conn, declared[col])
                if want.upper() != live_type.upper():
                    _record_drift(name, "type", col, live_type, want, rebuilt)
        pks = live_pks if live_pks is not None else _live_primary_keys(conn, name)
        live_pk, want_pk = pks.get(name, []), _declared_pk(MANIFEST[name])
        if live_pk != want_pk:
            _record_drift(name, "key", None, live_pk, want_pk, rebuilt)
    except Exception:  # noqa: BLE001 - a drift check must never break a write
        logger.warning("rawstore: schema drift check of %s failed", name, exc_info=True)


def _rebuild_compressed(conn, name: str, columns: list[str]) -> None:
    """One-time rebuild of a table whose ``compress`` columns are still text/JSON.

    Reads every row, decodes it (also undoing the old double-JSON-encoding of
    ``edgar_financials``), and rewrites it into a fresh table with the BLOB
    columns — a table rebuild instead of ALTER COLUMN TYPE, because the
    compression happens in Python. Runs in one transaction.
    """
    cols = _columns_of(MANIFEST[name])
    cur = conn.execute(f"SELECT * FROM {name}")
    names = [d[0] for d in cur.description]
    rows = [_decode_row(name, dict(zip(names, r))) for r in cur.fetchall()]
    logger.info("rawstore: compressing %s(%s) — %d rows", name, ", ".join(columns), len(rows))
    tmp = f"{name}__rebuild"
    try:
        conn.execute("BEGIN TRANSACTION")
        own_tx = True
    except duckdb.TransactionException:  # called inside atomic()/transaction()
        own_tx = False
    try:
        conn.execute(f"DROP TABLE IF EXISTS {tmp}")
        conn.execute(_ddl(name).replace(f"EXISTS {name} (", f"EXISTS {tmp} (", 1))
        prepared = _json_rows(name, rows)
        if prepared:
            _bulk_insert(conn, tmp, name, cols, prepared, conflict_sql="")
        conn.execute(f"DROP TABLE {name}")
        conn.execute(f"ALTER TABLE {tmp} RENAME TO {name}")
        if own_tx:
            conn.execute("COMMIT")
    except BaseException:
        if own_tx:
            conn.execute("ROLLBACK")
        raise


def ensure_table(name: str) -> None:
    _check(name)
    _auto_ensure(write=True)
    with connect(db=_db_of(name)) as conn:
        _ensure_table(conn, name)


# ── per-file schema stamp (#26 PL7-a) ────────────────────────────────────────────────────────
# A stamp in raw that describes edgar.duckdb cannot see a restore of one old file. The row lives in
# the file it describes: ``store_schema`` key ``schema_version``. Written on ensure when absent or
# older than ``_SCHEMA_VERSION``; a newer stamp is logged and left alone (never downgraded). An
# existing file with no row is stamped current — an already-wrong file would be marked right;
# ``schema_drift()`` is the backstop for a column or key the MANIFEST no longer matches. Additive:
# no ``_SCHEMA_VERSION`` bump. Refusal of writes is PL7-b (``store_schema_refuse``), off by default;
# it covers a stamp AHEAD of the code (newer, or unreadable) only, and it is checked before the
# ensure touches any file (``_refuse_ensure_if_ahead``), so an old checkout never reshapes a newer one.
_SCHEMA_STAMP_TABLE = "store_schema"
_SCHEMA_STAMP_KEY = "schema_version"
_SCHEMA_FILES = BOARD_DBS
_STAMP_WRITES: dict[str, int] = {}   # test hook: counts real stamp writes, not a metric
_STAMP_WARNED: set[tuple] = set()
_STAMP_SEEN: dict[str, tuple] = {}   # file path -> ((size, mtime_ns), stamp): a steady file costs one stat
_STAMP_LOCK = threading.Lock()


def _file_key(path: Path):
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_size, st.st_mtime_ns)


def _stamp_rank(value: str) -> tuple:
    """Numeric when the stamp is a plain integer (``"9"`` < ``"12"``); otherwise the text itself."""
    text = str(value).strip()
    try:
        return (0, int(text))
    except (TypeError, ValueError):
        return (1, text)


def _stamp_unreadable(value: str) -> bool:
    """A stamp that is not a plain integer sorts as ahead of the code and is never repaired: say so."""
    return _stamp_rank(value)[0] == 1


def _cached_stamp(db: str) -> str | None:
    """``schema_stamp`` keyed on the file's (size, mtime_ns): a swapped or restored file is re-read."""
    path = _db_path(db)
    key = _file_key(path)
    if key is None:
        return None
    with _STAMP_LOCK:
        hit = _STAMP_SEEN.get(str(path))
    if hit and hit[0] == key:
        return hit[1]
    stamp = schema_stamp(db)
    with _STAMP_LOCK:
        _STAMP_SEEN[str(path)] = (key, stamp)
    return stamp


def _refuse_ensure_if_ahead(dbs) -> None:
    """With refusal on, raise before the ensure reshapes a file whose stamp is ahead of this code."""
    from RevenueChaser.core import store_schema_refuse
    if not store_schema_refuse.schema_refuse_writes():
        return
    for db in dbs:
        if not _db_path(db).exists():
            continue
        stored = schema_stamp(db)
        if stored is not None and _stamp_rank(stored) > _stamp_rank(_SCHEMA_VERSION):
            raise StoreSchemaMismatch(store_schema_refuse.message(db, stored, _SCHEMA_VERSION))


def _read_schema_stamp(conn) -> str | None:
    """The stamp row on an open connection, or None when the table or the row is absent."""
    try:
        row = conn.execute(
            f"SELECT value FROM {_SCHEMA_STAMP_TABLE} WHERE key = ?",
            [_SCHEMA_STAMP_KEY]).fetchone()
    except duckdb.CatalogException:
        return None
    if not row or row[0] is None:
        return None
    return str(row[0])


def schema_stamp(db: str) -> str | None:
    """The schema version stored in ``db``, or None if the file or the row is absent.

    Does not create the file. ``history`` stays None until ``ensure_history`` (the file does not
    exist until the first recorded run).
    """
    if db not in _SCHEMA_FILES:
        raise RawStoreError(f"unknown store file {db!r}")
    path = _db_path(db)
    if not path.exists():
        return None
    with connect(read_only=True, db=db) as conn:
        return _read_schema_stamp(conn)


def store_schema_mismatch() -> list[dict]:
    """Files whose stored schema stamp is present and not this code's version.

    One dict per file: ``db``, ``file`` (the file name, never a path), ``stored``, ``code``, ``kind``
    (``older``, ``newer`` or ``unreadable`` for a stamp that is not an integer). A
    copy, in ``_SCHEMA_FILES`` order. A missing file, and a file with no stamp yet, are not listed
    — the first ensure stamps an absent row. Empty when every existing stamp matches.
    """
    code = _SCHEMA_VERSION
    out = []
    for db in _SCHEMA_FILES:
        path = _db_path(db)
        if not path.exists():
            continue
        stored = schema_stamp(db)
        if stored is None or _stamp_rank(stored) == _stamp_rank(code):
            continue
        kind = "unreadable" if _stamp_unreadable(stored) else (
            "newer" if _stamp_rank(stored) > _stamp_rank(code) else "older")
        out.append({"db": db, "file": path.name, "stored": stored, "code": code, "kind": kind})
    return out


def _note_schema_mismatch(db: str, stored: str) -> None:
    """Log one warning per (file, stored, code). ``RC_STORE_SCHEMA_OK=1`` suppresses it (PL7-b escape)."""
    if os.getenv("RC_STORE_SCHEMA_OK", "0") == "1":
        return
    path = _db_path(db)
    key = (str(path), stored, _SCHEMA_VERSION)
    with _STAMP_LOCK:
        if key in _STAMP_WARNED:
            return
        _STAMP_WARNED.add(key)
    logger.warning(
        "rawstore schema stamp mismatch in %s: stored %s%s, this code is %s",
        path.name, stored, " (not a version number)" if _stamp_unreadable(stored) else "", _SCHEMA_VERSION)


def _warn_schema_stamp(conn, db: str) -> None:
    """Log when this file's stamp is present and differs. Never raises: a read stays a read.

    Skipped while the file's (size, mtime_ns) is what it was at the last check, so a steady file costs
    a stat, not a query; a file swapped under a running process changes the key and is read again.
    """
    path = _db_path(db)
    key = _file_key(path)
    with _STAMP_LOCK:
        if key is not None and _STAMP_SEEN.get(str(path), (None,))[0] == key:
            return
    try:
        stored = _read_schema_stamp(conn)
    except Exception:  # noqa: BLE001 - a stamp check must never break a read
        with _STAMP_LOCK:
            first = ("check-failed", db) not in _STAMP_WARNED
            _STAMP_WARNED.add(("check-failed", db))
        if first:
            logger.warning("rawstore: schema stamp check of %s failed", db, exc_info=True)
        return
    with _STAMP_LOCK:
        _STAMP_SEEN[str(path)] = (key, stored)
    if stored is None or _stamp_rank(stored) == _stamp_rank(_SCHEMA_VERSION):
        return
    _note_schema_mismatch(db, stored)


def _apply_schema_stamp(conn, db: str) -> str:
    """Write this file's stamp when it is absent or older than the code. Never downgrades.

    Returns ``stamped``, ``upgraded``, ``unchanged`` or ``newer``. A newer stamp is logged and
    left as stored. Called from the ensure path only (``_ensure_db_tables``), so a read with
    ``RC_STORE_AUTO_ENSURE=0`` does not write one. ``_STAMP_WRITES`` counts real stamp writes,
    not a current row re-read.
    """
    conn.execute(_ddl(_SCHEMA_STAMP_TABLE))
    stored = _read_schema_stamp(conn)
    code = _SCHEMA_VERSION
    if stored is not None and _stamp_rank(stored) == _stamp_rank(code):
        return "unchanged"
    if stored is not None and _stamp_rank(stored) > _stamp_rank(code):
        _note_schema_mismatch(db, stored)
        return "newer"
    conn.execute(
        f"INSERT INTO {_SCHEMA_STAMP_TABLE} (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        [_SCHEMA_STAMP_KEY, code])
    with _STAMP_LOCK:
        _STAMP_WRITES[db] = _STAMP_WRITES.get(db, 0) + 1
        _STAMP_SEEN.pop(str(_db_path(db)), None)
    if stored is None:
        return "stamped"
    # An older stamp means an older file was restored (or a bump was never applied): keep the trace.
    for key, value in (("upgraded_from", stored),
                       ("upgraded_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))):
        conn.execute(
            f"INSERT INTO {_SCHEMA_STAMP_TABLE} (key, value) VALUES (?, ?) "
            "ON CONFLICT (key) DO UPDATE SET value = excluded.value", [key, value])
    logger.warning("rawstore: %s schema stamp %s upgraded to %s (an older file was restored, or a bump "
                   "was not applied)", _db_path(db).name, stored, code)
    return "upgraded"


def _ensure_db_tables(conn, db: str) -> None:
    """Reconcile every MANIFEST table of one file, with ONE catalog probe."""
    existing: dict[str, dict[str, str]] = {}
    for t, c, typ in conn.execute(
            "SELECT table_name, column_name, data_type FROM information_schema.columns "
            "WHERE table_schema = 'main'").fetchall():
        existing.setdefault(t, {})[c] = typ
    path = str(_db_path(db))
    live_pks = _live_primary_keys(conn)
    for name, spec in MANIFEST.items():
        if spec.get("db") != db:      # store_schema has no file of its own: the stamp below writes it in each
            continue
        _reconcile_table(conn, name, existing.get(name, {}), live_pks)
        _TABLE_READY.add((path, name))
    _apply_schema_stamp(conn, db)


def ensure_all_tables() -> None:
    """Reconcile every board file with the MANIFEST (each board's own file, made eagerly)."""
    prev = getattr(_LOCAL, "ensuring", False)
    _LOCAL.ensuring = True  # the steps below call the public API themselves
    try:
        _refuse_ensure_if_ahead(_SCHEMA_FILES)   # before any ALTER (PL7-b)
        for board in BOARD_DBS:
            with connect(db=board) as conn:
                _ensure_db_tables(conn, board)
    finally:
        _LOCAL.ensuring = prev
    _ENSURED[str(Path(STORE_DIR))] = 0.0


# ── apply the manifest once per process, on first use ───────────────────────
# Nothing used to call ensure_all_tables() outside tests and the migration
# script, so a fresh or restored store never got its renames, merges or VIEWs
# (``company_profile``/``index_tickers``) and those readers silently returned
# []. Now the first store call of every process (dashboard, CLI, scheduled job)
# applies it. A failure (e.g. the store is locked) is logged and retried at most
# every _ENSURE_RETRY_S seconds rather than on every call. The unit suite turns
# it off (RC_STORE_AUTO_ENSURE=0 in conftest.py) because every test gets a fresh
# DB and the full manifest costs ~1 s; tests that need it call it explicitly.
_ENSURED: dict[str, float] = {}  # store folder -> 0.0 done | time of last failure
_ENSURE_LOCK = threading.Lock()
_ENSURE_RETRY_S = 30.0


def _auto_ensure(write: bool) -> None:
    if os.getenv("RC_STORE_AUTO_ENSURE", "1") == "0" or getattr(_LOCAL, "ensuring", False):
        return
    key = str(Path(STORE_DIR))
    state = _ENSURED.get(key)
    if state == 0.0 or (state and time.time() - state < _ENSURE_RETRY_S):
        return
    if not write and not (Path(STORE_DIR) / BOARDS_DIRNAME).exists():
        return  # a read of a store that does not exist yet must not create it
    with _ENSURE_LOCK:
        state = _ENSURED.get(key)
        if state == 0.0 or (state and time.time() - state < _ENSURE_RETRY_S):
            return
        try:
            ensure_all_tables()
        except Exception:  # noqa: BLE001 - never turn a read into a crash
            logger.warning("rawstore: applying the schema manifest failed; "
                           "retrying in %.0fs", _ENSURE_RETRY_S, exc_info=True)
            _ENSURED[key] = time.time()


def _sql_text(path: Path) -> str:
    """A path as a single-quoted SQL literal's body (rcdata/build/base.py uses it too)."""
    return path.as_posix().replace("'", "''")


def _col_type(name: str, col: str) -> str:
    """The base DuckDB type declared for ``col`` (uppercased), or "TEXT"."""
    spec = MANIFEST[name]
    for c in spec["columns"]:
        head, _, rest = c.strip().partition(" ")
        if head.strip('"') == col:
            rest = rest.strip() or "TEXT"
            return rest.upper()
    return "TEXT"


def _json_rows(name: str, rows: list[dict]) -> list[dict]:
    """Prepare dict/list-valued cells for storage.

    A cell targeting a native DuckDB nested type (``JSON``/``STRUCT``) is
    serialised to a JSON *string* first (DuckDB validates it on the way in and
    stores it as a proper JSON value — reading a Python dict/list straight into
    a JSON column mangles floats inside mixed-type arrays, e.g.
    ``[["2026-08-01", 100.0]]`` -> ``[["2026-08-01", "100.0"]]``). A scalar
    string is JSON-quoted so it stays a JSON string. TEXT-blob columns (legacy)
    keep the old behaviour.
    """
    spec = MANIFEST[name]
    compress = spec.get("compress") or {}
    out = []
    for r in rows:
        row = dict(r)
        for col in _columns_of(spec):
            v = row.get(col)
            if v is None:
                continue
            if col in compress:
                row[col] = _compress(v, compress[col])
                continue
            base = _col_type(name, col).split("(", 1)[0].rstrip("[]")
            if base in _NESTED_TYPES:
                row[col] = json.dumps(v, ensure_ascii=False, default=str)
            elif isinstance(v, (dict, list)):
                row[col] = json.dumps(v, ensure_ascii=False, default=str)
        out.append(row)
    return out


def _compress(v, kind: str) -> bytes:
    if isinstance(v, (bytes, bytearray, memoryview)):
        return bytes(v)  # already compressed (e.g. copied row to row)
    text = json.dumps(v, ensure_ascii=False, default=str) if kind == "json" else str(v)
    return zlib.compress(text.encode("utf-8"), 6)


def _decompress(v, kind: str):
    """Inverse of ``_compress``; also accepts the pre-compression text form.

    A cell read from a table not yet rebuilt is still JSON text — possibly
    JSON-encoded twice (the old edgar_financials migration bug) — so a JSON
    string that itself holds a JSON array/object is decoded again.
    """
    if isinstance(v, (bytes, bytearray, memoryview)):
        v = zlib.decompress(bytes(v)).decode("utf-8")
    if kind != "json" or not isinstance(v, str):
        return v
    try:
        out = json.loads(v)
        while isinstance(out, str) and out[:1] in ("[", "{"):
            out = json.loads(out)
    except (json.JSONDecodeError, TypeError):
        return v
    return out


def _base_type(name: str, col: str) -> str:
    """``_col_type`` without constraints: ``"TEXT PRIMARY KEY"`` -> ``"TEXT"``."""
    t = _col_type(name, col)
    for stop in (" PRIMARY", " NOT ", " DEFAULT", " UNIQUE", " CHECK", " REFERENCES"):
        i = t.find(stop)
        if i >= 0:
            t = t[:i]
    return t.strip() or "TEXT"


def _col_sql(cols: list[str]) -> str:
    # quote every identifier — column names come from the manifest unquoted and
    # some (e.g. rotation_snapshots."group") are SQL reserved words
    return ", ".join(f'"{c}"' for c in cols)


# ── who wrote a row ─────────────────────────────────────────────────────────────────────────────────────────────
# ``(run_id, source)`` of the running dashboard job when the app registered a provider (app/jobs: the job id and its
# module), else the scheduled task's run (``task_run``: its ``job_runs`` id and registry name), else a fresh id like
# ``ledger.new_run_id`` and no source. The change capture that also read it went with raw.duckdb (#860).
_CHANGE_WRITER = None


# A scheduled task's run (#129 A1): ``core/automations.run_task`` records the run's ``job_runs`` row and hands its id
# and registry name to the command it starts in these variables.
RUN_ID_ENV, RUN_SOURCE_ENV = "RC_RUN_ID", "RC_RUN_SOURCE"


def task_run() -> tuple[str, str | None] | None:
    """``(run_id, source)`` of the scheduled task this process runs under, else None."""
    run_id = os.environ.get(RUN_ID_ENV, "").strip()
    return (run_id, os.environ.get(RUN_SOURCE_ENV, "").strip() or None) if run_id else None


def set_change_writer(fn) -> None:
    """Called once by app/jobs: ``fn()`` returns ``(run_id, source)`` of the job on this thread, or None."""
    global _CHANGE_WRITER
    _CHANGE_WRITER = fn


def _change_writer() -> tuple[str, str | None]:
    got = _CHANGE_WRITER() if _CHANGE_WRITER else None
    if got and got[0]:
        return got[0], got[1]
    task = task_run()
    if task:
        return task
    import uuid
    return uuid.uuid4().hex[:12], None


def writer_run_id() -> str:
    """The ``run_id`` a core writer stamps on its rows: the running dashboard job's id, else the scheduled task's,
    else a fresh one.

    So a row joins to its ``job_runs`` row. For core code that cannot import
    ``app.jobs.run_id`` (``core/quotes.py``, called from inside the universe pull).
    """
    return _change_writer()[0]


def _q(c: str) -> str:
    return f'"{c}"'


def _refuse_wrong_file(sql: str, db: str) -> None:
    """Raise when raw ``sql`` names a MANIFEST table that lives in another store file than ``db``.

    A read of a missing table comes back ``[]`` (``query`` is lenient), so once a table moves to its board file
    (``boards/<board>.duckdb``, DECISIONS S9) a call site still sending it to ``raw`` would empty the board without
    an error. DuckDB names the tables itself when it can bind the text (parameters read as NULL); otherwise (writes,
    ``USING`` joins) a table is a name after FROM, JOIN, INTO, UPDATE or TABLE, comments and literals left out.
    Covers ``query``, ``execute`` and ``transaction().execute``; a caller's own ``connect()`` handle is not checked.
    """
    text = re.sub(r"--[^\n]*|/\*.*?\*/", " ", re.sub(r"'(?:[^']|'')*'", "''", sql), flags=re.S)
    try:
        names = duckdb.get_table_names(re.sub(r"\?|\$\d+", "NULL", text))
    except duckdb.Error:
        names = {m.split(".")[-1].strip('"') for m in re.findall(
            r'(?i)\b(?:FROM|JOIN|INTO|UPDATE|TABLE)\s+((?:"?\w+"?\.){0,2}"?\w+"?)', text)}
    # Only a board file's side is checked: the older moves (edgar, prices) still read their tables' old raw copies.
    wrong = sorted(f"{n} ({_db_of(n)})" for n in names if n in MANIFEST and n != _SCHEMA_STAMP_TABLE
                   and _db_of(n) != db and (db in BOARD_DBS or _db_of(n) in BOARD_DBS))
    if wrong:
        raise RawStoreError(f"raw SQL sent to the {db} file names tables that live in another file: "
                            f"{', '.join(wrong)}. Pass db=<that file>, one query per file (S9: no ATTACH).")


def _apply_write(conn, name: str, spec: dict, rows: list[dict]) -> None:
    """Mode-specific INSERT for a prepared (JSON-serialized) batch.

    Caller supplies the connection and the surrounding transaction, so a
    multi-statement mode ("replace" = DELETE + INSERT) is all-or-nothing.
    """
    cols = _columns_of(spec)
    key_cols = spec.get("key") or []
    mode = spec.get("write", "upsert")

    if spec.get("history"):
        # A history table is only ever added to (#286): the first row written for a key stays, whatever
        # the table's write mode would otherwise do with a duplicate.
        if not key_cols:
            raise RawStoreError(f"history table {name} needs a key: first-write-wins is decided per key")
        conflict_sql = f"ON CONFLICT ({_col_sql(key_cols)}) DO NOTHING"
        rows = _dedupe(rows, key_cols, keep="first")
    elif mode == "upsert" and key_cols:
        conflict = _col_sql(key_cols)
        update_cols = [c for c in cols if c not in key_cols]
        if update_cols:
            updates = ", ".join(f'"{c}"=excluded."{c}"' for c in update_cols)
            conflict_sql = f"ON CONFLICT ({conflict}) DO UPDATE SET {updates}"
        else:
            conflict_sql = f"ON CONFLICT ({conflict}) DO NOTHING"
        rows = _dedupe(rows, key_cols, keep="last")  # row-by-row: last one wins
    elif mode == "append":
        conflict_sql = f"ON CONFLICT ({_col_sql(key_cols)}) DO NOTHING" if key_cols else ""
        if key_cols:
            rows = _dedupe(rows, key_cols, keep="first")  # DO NOTHING: first wins
    elif mode == "replace" and key_cols:
        # Delete the rows matching the batch's groups (group_by defaults to the
        # key), then insert — a per-group refresh (one slug/ticker/date/run)
        # doesn't clear other groups. One DELETE for the whole batch.
        group_cols = spec.get("group_by") or key_cols
        distinct = list({tuple(r.get(c) for c in group_cols) for r in rows})
        _delete_groups(conn, name, group_cols, distinct)
        conflict_sql = ""
    else:
        raise RawStoreError(f"table {name}: unsupported write mode {mode!r}")

    if len(rows) >= _BULK_MIN_ROWS:
        _bulk_insert(conn, name, name, cols, rows, conflict_sql)
    else:
        values = ", ".join(["?"] * len(cols))
        conn.executemany(
            f"INSERT INTO {name} ({_col_sql(cols)}) VALUES ({values}) {conflict_sql}",
            [[r.get(c) for c in cols] for r in rows])


# ``executemany`` binds and executes one row at a time: 50k rows take ~15 s.
# Registering the batch as a DataFrame and running ONE ``INSERT ... SELECT``
# takes ~0.2 s. Small batches keep ``executemany`` (no pandas overhead).
_BULK_MIN_ROWS = 64
_NUMERIC_TYPES = {"INTEGER", "BIGINT", "SMALLINT", "TINYINT", "HUGEINT", "UBIGINT",
                  "UINTEGER", "DOUBLE", "FLOAT", "REAL"}


def _dedupe(rows: list[dict], key_cols: list[str], keep: str) -> list[dict]:
    """One row per key, as a row-by-row write would have left it.

    A single ``INSERT ... ON CONFLICT DO UPDATE`` refuses to touch one row twice,
    so a batch carrying a key twice must be collapsed first.
    """
    seen: dict[tuple, dict] = {}
    for r in rows:
        k = tuple(r.get(c) for c in key_cols)
        if keep == "last" or k not in seen:
            seen[k] = r
    return rows if len(seen) == len(rows) else list(seen.values())


def _delete_groups(conn, name: str, group_cols: list[str], groups: list[tuple]) -> None:
    if not groups:
        return
    if len(groups) < _BULK_MIN_ROWS:
        where = " AND ".join(f'"{c}" = ?' for c in group_cols)
        for kv in groups:
            conn.execute(f"DELETE FROM {name} WHERE {where}", list(kv))
        return
    import pandas as pd
    view = "_rc_groups"
    conn.register(view, pd.DataFrame([[None if v is None else str(v) for v in g] for g in groups],
                                     columns=group_cols, dtype=object))
    try:
        match = " AND ".join(f'CAST({name}."{c}" AS VARCHAR) = {view}."{c}"' for c in group_cols)
        conn.execute(f"DELETE FROM {name} WHERE EXISTS (SELECT 1 FROM {view} WHERE {match})")
    finally:
        conn.unregister(view)


def _cell_text(v, base: str):
    """A cell as the VARCHAR the bulk INSERT casts back to ``base``.

    Every value goes in as text and is CAST to the column type in SQL, which
    reproduces exactly what binding the Python value did (float repr is
    round-trip exact; ``CAST('3.7' AS INTEGER)`` rounds like a bound 3.7).
    Bytes stay bytes (BLOB). Booleans follow DuckDB's own rendering.
    """
    if v is None or isinstance(v, (bytes, bytearray, memoryview)):
        return None if v is None else bytes(v)
    if isinstance(v, bool):
        return ("1" if v else "0") if base in _NUMERIC_TYPES else ("true" if v else "false")
    return str(v)


def _bulk_insert(conn, target: str, spec_name: str, cols: list[str], rows: list[dict],
                 conflict_sql: str) -> None:
    import pandas as pd
    bases = [_base_type(spec_name, c) for c in cols]
    frame = pd.DataFrame([[_cell_text(r.get(c), b) for c, b in zip(cols, bases)] for r in rows],
                         columns=cols, dtype=object)
    view = "_rc_batch"
    # Analyse every row, not a sample: a column whose first 1000 cells are NULL
    # must still be typed from the cells that are not.
    conn.execute(f"SET pandas_analyze_sample = {max(len(rows), 1000)}")
    conn.register(view, frame)
    try:
        select = ", ".join(f'CAST({view}."{c}" AS {b})' for c, b in zip(cols, bases))
        conn.execute(f"INSERT INTO {target} ({_col_sql(cols)}) "
                     f"SELECT {select} FROM {view} {conflict_sql}")
    finally:
        conn.unregister(view)


def _guard_schema_write(db: str) -> None:
    """PL7-b (#26). No-op unless ``RC_STORE_SCHEMA_REFUSE=1``. See ``store_schema_refuse``."""
    from RevenueChaser.core.store_schema_refuse import refuse_schema_write
    refuse_schema_write(db)


def write_rows(name: str, rows: list[dict]) -> int:
    """Insert/upsert rows into a manifest table. Raises on failure.

    Atomic: the whole batch commits or none of it does, so a partial/failed
    refresh can never leave the table emptied by the DELETE half of a
    "replace".
    """
    spec = _check(name)
    if not rows:
        return 0
    _auto_ensure(write=True)
    _guard_schema_write(_db_of(name))
    rows = _json_rows(name, rows)

    def _op():
        with connect(db=_db_of(name)) as conn:
            _ensure_table(conn, name)  # self-healing: create the table if the DB predates it
            with _tx(conn):
                _apply_write(conn, name, spec, rows)

    _retry_write(_op)
    return len(rows)


def update_columns(name: str, key_col: str, rows: list[dict],
                   columns: list[str]) -> int:
    """UPDATE only ``columns`` on rows matched by ``key_col`` — never insert.

    The narrow writer for a partial-row refresh: ``equity_universe`` is
    ``write: "upsert"``, so sending ``{ticker, market_cap, price}`` through
    ``write_rows`` overwrites *every* non-key column from ``r.get(c)`` and NULLs
    name/sector/GICS/quote (see docs/data_health.md, "Feasibility review"). A key
    absent from the table matches no row and is a no-op, so this can fill a
    backfill without ever growing or shrinking the table. One transaction per
    call; all statements share the module's connect/retry semantics.
    """
    spec = _check(name)
    _refuse_history(name, spec, "update_columns")
    if not rows:
        return 0
    valid = _columns_of(spec)
    for c in [key_col, *columns]:
        if c not in valid:
            raise RawStoreError(f"table {name} has no column {c!r}")
    _auto_ensure(write=True)
    _guard_schema_write(_db_of(name))
    rows = _json_rows(name, rows)
    set_sql = ", ".join(f'"{c}" = ?' for c in columns)
    sql = f'UPDATE {name} SET {set_sql} WHERE "{key_col}" = ?'

    def _op():
        with connect(db=_db_of(name)) as conn:
            _ensure_table(conn, name)
            with _tx(conn):
                if len(rows) >= _BULK_MIN_ROWS:
                    _bulk_update(conn, name, key_col, columns, rows)
                else:
                    conn.executemany(
                        sql, [[r.get(c) for c in columns] + [r.get(key_col)] for r in rows])

    _retry_write(_op)
    return len(rows)


def _bulk_update(conn, name: str, key_col: str, columns: list[str], rows: list[dict]) -> None:
    """``UPDATE ... FROM`` a registered batch — one statement instead of N."""
    import pandas as pd
    cols = [key_col, *columns]
    bases = [_base_type(name, c) for c in cols]
    # Row-by-row UPDATEs let the last row for a key win; keep that.
    rows = _dedupe(rows, [key_col], keep="last")
    frame = pd.DataFrame([[_cell_text(r.get(c), b) for c, b in zip(cols, bases)] for r in rows],
                         columns=cols, dtype=object)
    view = "_rc_upd"
    conn.execute(f"SET pandas_analyze_sample = {max(len(rows), 1000)}")
    conn.register(view, frame)
    try:
        sets = ", ".join(f'"{c}" = CAST({view}."{c}" AS {b})'
                         for c, b in zip(columns, bases[1:]))
        conn.execute(f'UPDATE {name} SET {sets} FROM {view} '
                     f'WHERE {name}."{key_col}" = CAST({view}."{key_col}" AS {bases[0]})')
    finally:
        conn.unregister(view)


def replace_all(name: str, rows: list[dict], *, allow_empty: bool = False) -> int:
    """Atomically make ``rows`` the ENTIRE contents of a table.

    The full-refresh equivalent of the JSON stores these tables replaced: keys
    absent from ``rows`` are removed, instead of lingering forever under the
    per-row upsert. Delete + insert share one transaction, so a failure leaves
    the previous contents untouched.

    An EMPTY ``rows`` would delete everything and write nothing, which is what a
    degraded run (no peers, no edges, a fetch that returned nothing) produces by
    accident. It raises unless the caller says it means it with
    ``allow_empty=True`` (#284).
    """
    spec = _check(name)
    _refuse_history(name, spec, "replace_all")
    if not rows and not allow_empty:
        raise RawStoreError(
            f"replace_all({name!r}, []) would empty the table; pass allow_empty=True if an "
            f"empty table is the intent, or keep the stored rows when a run produced nothing")
    cols = _columns_of(spec)
    _auto_ensure(write=True)
    _guard_schema_write(_db_of(name))
    rows = _json_rows(name, rows)

    def _op():
        with connect(db=_db_of(name)) as conn:
            _ensure_table(conn, name)
            with _tx(conn):
                conn.execute(f"DELETE FROM {name}")
                if len(rows) >= _BULK_MIN_ROWS:
                    _bulk_insert(conn, name, name, cols, rows, conflict_sql="")
                elif rows:
                    conn.executemany(
                        f"INSERT INTO {name} ({_col_sql(cols)}) "
                        f"VALUES ({', '.join(['?'] * len(cols))})",
                        [[r.get(c) for c in cols] for r in rows])

    _retry_write(_op)
    return len(rows)


def sync_rows(name: str, rows: list[dict], *, allow_empty: bool = False) -> int:
    """Make ``rows`` the table's contents incrementally (plan 2026-11-08 §10, the board-file rule): upsert the run's
    rows and delete, by key, only the stored keys the run no longer has, in one transaction. Returns the number of
    keys retired. An empty run raises like ``replace_all`` (#284) or, with ``allow_empty``, deletes nothing."""
    spec = _check(name)
    _refuse_history(name, spec, "sync_rows")
    if not rows:
        if allow_empty:
            return 0
        raise RawStoreError(f"sync_rows({name!r}, []) would retire every key; keep the stored rows when a run "
                            f"produced nothing")
    key = [k.strip('"') for k in spec.get("key") or []]
    if not key:
        raise RawStoreError(f"sync_rows needs a key; {name} has none")
    new = {tuple(r.get(k) for k in key) for r in rows}
    cols = ", ".join(_q(k) for k in key)

    def _write(tx):
        tx.ensure_table(name)
        gone = [tuple(k) for k in tx.execute(f"SELECT {cols} FROM {name}").fetchall() if tuple(k) not in new]
        one = "(" + ", ".join(["?"] * len(key)) + ")"
        for i in range(0, len(gone), 500):
            chunk = gone[i:i + 500]
            tx.execute(f"DELETE FROM {name} WHERE ({cols}) IN ({', '.join([one] * len(chunk))})",
                       [v for k in chunk for v in k])
        tx.write_rows(name, rows)
        return len(gone)

    return atomic(_write, db=_db_of(name))


class _Tx:
    """Handle passed to ``transaction()`` — the same write API, one transaction."""

    def __init__(self, conn, db: str | None = None):
        self._conn = conn
        self._db = db

    def _own(self, name: str) -> dict:
        spec = _check(name)
        if _db_of(name) != self._db:
            raise RawStoreError(f"{name} lives in the {_db_of(name)} file; this transaction writes the {self._db} "
                                f"file (one transaction, one file)")
        return spec

    def execute(self, sql: str, params: list | None = None):
        _refuse_wrong_file(sql, self._db)
        _refuse_history_sql(self._conn, sql)
        return self._conn.execute(sql, params or [])

    def ensure_table(self, name: str) -> None:
        """Create ``name`` if missing, inside this transaction (before ``execute``)."""
        self._own(name)
        _ensure_table(self._conn, name)

    def write_rows(self, name: str, rows: list[dict]) -> int:
        spec = self._own(name)
        if not rows:
            return 0
        _ensure_table(self._conn, name)
        _apply_write(self._conn, name, spec, _json_rows(name, rows))
        return len(rows)


@contextmanager
def transaction(db: str | None = None):
    """One connection + one transaction spanning SEVERAL tables.

    For writes that must land together or not at all — e.g. a 13F zip's
    submissions/holdings/names plus its ``ingested_zips`` marker, where a
    half-applied zip would be silently re-ingested and double-counted. All
    tables in one transaction must share ``db``.

    Unlike ``write_rows``/``replace_all`` this cannot retry a lost commit race
    for you — the caller owns the block, so it must re-run it itself. Use
    ``atomic(fn)`` for a block that should be retried.
    """
    _auto_ensure(write=True)
    _guard_schema_write(db)
    with connect(db=db) as conn:
        with _tx(conn):
            yield _Tx(conn, db)


def atomic(fn, db: str | None = None):
    """Run ``fn(tx)`` in ONE transaction, retrying a lost commit race.

    ``fn`` receives the ``transaction()`` handle (``tx.write_rows``,
    ``tx.execute``) and must be safe to re-run: a conflicting attempt is rolled
    back whole before the retry. Returns ``fn``'s result.
    """
    _auto_ensure(write=True)
    _guard_schema_write(db)

    def _op():
        with connect(db=db) as conn:
            with _tx(conn):
                return fn(_Tx(conn, db))

    return _retry_write(_op)


def execute(sql: str, params: list | None = None, db: str | None = None) -> None:
    """Run a single write statement (DELETE/UPDATE) against a store file."""
    _refuse_wrong_file(sql, db)
    _auto_ensure(write=True)
    _guard_schema_write(db)
    with connect(db=db) as conn:
        _refuse_history_sql(conn, sql)
        conn.execute(sql, params or [])


def query(sql: str, params: list | None = None, read_only: bool = True,
          db: str | None = None) -> list[dict]:
    """Run a read query; returns rows as dicts. Safe for raw SQL from callers."""
    _refuse_wrong_file(sql, db)
    if read_only and not _db_path(db).exists():
        return []
    _auto_ensure(write=not read_only)
    if not read_only:
        _guard_schema_write(db)
    try:
        with connect(read_only=read_only, db=db) as conn:
            if read_only:
                _warn_schema_stamp(conn, db)   # PL7-a: a mismatch warns; it does not refuse the read
            _refuse_history_sql(conn, sql)
            cur = conn.execute(sql, params or [])
            cols = [d[0] for d in cur.description] if cur.description else []
            return [dict(zip(cols, row)) for row in cur.fetchall()]
    except duckdb.CatalogException:
        # Missing table == no data (reads stay lenient; a pre-migration DB may
        # not have every table yet).
        if read_only:
            return []
        raise


def get(name: str, key) -> dict | None:
    """Fetch one row by its key column(s). ``key`` may be a single value or tuple."""
    spec = _check(name)
    key_cols = spec.get("key") or []
    if not key_cols:
        raise RawStoreError(f"table {name} has no key column")
    if not isinstance(key, tuple):
        key = (key,)
    if len(key_cols) != len(key):
        raise RawStoreError(f"table {name} expects {len(key_cols)} key values, got {len(key)}")
    where = " AND ".join(f'"{c}" = ?' for c in key_cols)
    rows = query(f"SELECT * FROM {name} WHERE {where}", list(key), db=_db_of(name))
    if not rows:
        return None
    return _decode_row(name, rows[0])


def get_many(name: str, keys, columns: list[str] | None = None) -> dict:
    """``{key: row}`` for the existing rows among ``keys`` of a table with ONE key column.

    One query for the lot (``get`` costs one per key); rows are decoded as ``get`` decodes them.
    ``columns`` narrows the SELECT (the key column is always included).
    """
    spec = _check(name)
    key_cols = spec.get("key") or []
    if len(key_cols) != 1:
        raise RawStoreError(f"table {name} needs exactly one key column for get_many")
    keys = list(dict.fromkeys(keys))
    if not keys:
        return {}
    key_col = key_cols[0]
    select = "*"
    if columns:
        valid = set(_columns_of(spec))
        bad = [c for c in columns if c not in valid]
        if bad:
            raise RawStoreError(f"table {name} has no column(s) {bad!r}")
        select = _col_sql(list(dict.fromkeys([key_col, *columns])))
    marks = ", ".join("?" for _ in keys)
    rows = query(f'SELECT {select} FROM {name} WHERE "{key_col}" IN ({marks})', keys, db=_db_of(name))
    return {row[key_col]: _decode_row(name, row) for row in rows}


def _decode_row(name: str, row: dict) -> dict:
    """Parse stored JSON columns back to Python objects.

    A ``JSON`` column holds JSON text, so its cell is decoded whatever the
    contained type is (dict, list, or a scalar — a plain string in a JSON
    column round-trips as ``"RTX"``, not ``'"RTX"'``). Legacy TEXT-blob columns
    are only re-parsed when they hold a JSON object/array (their pre-schema
    evolution contract). ``compress`` columns are decompressed (and decoded).
    """
    spec = MANIFEST[name]
    compress = spec.get("compress") or {}
    for col in _columns_of(spec):
        v = row.get(col)
        if col in compress and v is not None:
            row[col] = _decompress(v, compress[col])
            continue
        if not isinstance(v, str):
            continue
        try:
            parsed = json.loads(v)
        except (json.JSONDecodeError, TypeError):
            continue
        base = _col_type(name, col).split("(", 1)[0].rstrip("[]")
        # ``text_verbatim`` tables hold third-party text: a TEXT cell is never re-parsed.
        if base in _NESTED_TYPES or (isinstance(parsed, (dict, list))
                                     and not spec.get("text_verbatim")):
            if base in _JSON_TYPES and isinstance(parsed, str) and not spec.get("text_verbatim"):
                # Legacy double-encoded cell (#202): decode once more, but only when the
                # inner text is itself a JSON object/array; any other string stays as is.
                try:
                    inner = json.loads(parsed)
                except (json.JSONDecodeError, TypeError):
                    inner = None
                if isinstance(inner, (dict, list)):
                    parsed = inner
            row[col] = parsed
    return row


def get_all(name: str, columns: list[str] | None = None) -> list[dict]:
    """All rows as dicts; JSON columns parsed back to objects.

    ``columns`` narrows the SELECT — e.g. ``chain_filings`` without its
    ``item_text`` blobs when only the filing dates are needed.
    """
    spec = _check(name)
    if columns:
        valid = set(_columns_of(spec))
        bad = [c for c in columns if c not in valid]
        if bad:
            raise RawStoreError(f"table {name} has no column(s) {bad!r}")
        select = _col_sql(columns)
    else:
        select = "*"
    return [_decode_row(name, row)
            for row in query(f"SELECT {select} FROM {name}", db=_db_of(name))]


def count(name: str) -> int:
    _check(name)
    rows = query(f"SELECT COUNT(*) AS n FROM {name}", db=_db_of(name))
    return int(rows[0]["n"]) if rows else 0


def delete(name: str, key) -> None:
    """Delete a single row by its key column(s)."""
    spec = _check(name)
    _refuse_history(name, spec, "delete")
    key_cols = spec.get("key") or []
    if not key_cols:
        raise RawStoreError(f"table {name} has no key column")
    if not isinstance(key, tuple):
        key = (key,)
    _auto_ensure(write=True)
    _guard_schema_write(_db_of(name))
    where = " AND ".join(f'"{c}" = ?' for c in key_cols)
    with connect(db=_db_of(name)) as conn:
        with _tx(conn):
            conn.execute(f"DELETE FROM {name} WHERE {where}", list(key))


def clear(name: str) -> None:
    """Delete all rows from a manifest table.

    Prefer ``replace_all`` when new rows follow: clear-then-write across two
    calls is two transactions, so a failed write leaves the table empty and a
    concurrent reader can observe the gap.
    """
    _refuse_history(name, _check(name), "clear")
    _auto_ensure(write=True)
    _guard_schema_write(_db_of(name))
    with connect(db=_db_of(name)) as conn:
        _ensure_table(conn, name)
        with _tx(conn):
            conn.execute(f"DELETE FROM {name}")


# ── watchlist: the stock watch list in ops.sqlite (PR 4) ─────────────────────
# Since PR 4 "the watchlist" is the stock watch list of ``rcdata.ops`` (D2, D6). These three keep their names for the
# readers that call them (Earnings, the old toggle route, the tests); the ``watchlist`` store table stays in the
# manifest, untouched and unread by them (purged on 27 Oct, D5), until its retirement.
def load_watchlist() -> set[str]:
    """The stock watch list's tickers (``rcdata.read.watched("stock")``)."""
    from RevenueChaser.rcdata import read
    return read.watched("stock")


def save_watchlist(tickers: set[str], *, by: str = "save_watchlist") -> None:
    """Make the stock watch list exactly ``tickers``, one history row per ticker added or removed. An empty set clears
    it: that is the user's choice. The dashboard does not call it: a click goes through ``toggle_watchlist``."""
    from RevenueChaser.rcdata import ops
    ops.watch_replace("stock", tickers, by=by)


def toggle_watchlist(ticker: str, *, by: str = "dashboard") -> bool:
    """Add ``ticker`` to the stock watch list, or remove it when it is there; whether it is on the list now.

    One ``BEGIN IMMEDIATE`` transaction on ``ops.sqlite`` that reads and writes this ticker only, so two clicks that
    race cannot drop each other's ticker; each flip writes its history row (``watchlist_stock_changes``, with ``by``)."""
    from RevenueChaser.rcdata import ops
    return ops.watch_toggle("stock", ticker, by=by)


def reset_db() -> None:
    """Drop and recreate the board files (tests)."""
    for db in BOARD_DBS:
        if _db_path(db).exists():
            _guard_schema_write(db)   # PL7-b: do not delete a newer file while refusal is on
    for p in (board_db_path(b) for b in BOARD_DBS):
        if p.exists():
            p.unlink()
        _TABLE_READY.difference_update({k for k in _TABLE_READY if k[0] == str(p)})
    _ENSURED.pop(str(Path(STORE_DIR)), None)
    ensure_all_tables()


def compact(db: str | None = None) -> dict:
    """Rewrite a store file without its free blocks; swap it in; verify.

    DuckDB re-uses the blocks freed by DELETE/``replace_all`` but never gives
    them back to the OS, so a file only grows. ``COPY FROM DATABASE`` writes a
    fresh, densely packed copy; row counts are verified table by table before
    the swap. The previous file is kept as ``<name>.pre-compact`` (overwritten
    each time) until the caller deletes it.

    Needs the file to itself: refuses while another RevenueChaser process is
    using the store, and the swap fails (leaving the original untouched) if any
    other process holds it.
    """
    src = _db_path(db)
    if not src.exists():
        raise RawStoreError(f"no store file at {src}")
    _guard_schema_write(db)   # PL7-b: do not rewrite a newer file while refusal is on
    peers = _peer_pids(src)
    if peers:
        raise RawStoreError(f"store in use by RevenueChaser process(es) {peers}; "
                            f"stop them and retry")
    if _sessions().get("depth"):
        raise RawStoreError("compact() cannot run inside a session()")
    dst = src.with_name(src.stem + ".compact.duckdb")
    bak = src.with_name(src.name + ".pre-compact")
    dst.unlink(missing_ok=True)
    before = src.stat().st_size
    conn = _connect_with_retry(_WRITE_DELAYS, src)
    try:
        catalog = conn.execute("SELECT current_database()").fetchone()[0]
        tables = [r[0] for r in conn.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema = 'main' AND table_type = 'BASE TABLE'").fetchall()]
        counts = {t: conn.execute(f'SELECT count(*) FROM "{t}"').fetchone()[0] for t in tables}
        conn.execute(f"ATTACH '{dst.as_posix()}' AS _rc_compact")
        try:
            conn.execute(f'COPY FROM DATABASE "{catalog}" TO _rc_compact')
            got = {t: conn.execute(f'SELECT count(*) FROM _rc_compact.main."{t}"').fetchone()[0]
                   for t in tables}
        finally:
            conn.execute("DETACH _rc_compact")
    finally:
        with _ATTACH_LOCK:
            conn.close()
    if got != counts:
        dst.unlink(missing_ok=True)
        bad = {t: (counts[t], got.get(t)) for t in counts if counts[t] != got.get(t)}
        raise RawStoreError(f"compact verification failed: {bad}")
    os.replace(src, bak)
    try:
        os.replace(dst, src)
    except OSError:
        os.replace(bak, src)  # put the original back
        raise
    _TABLE_READY.difference_update({k for k in _TABLE_READY if k[0] == str(src)})
    return {"db": db, "before_bytes": before, "after_bytes": src.stat().st_size,
            "tables": len(tables), "previous": str(bak)}


def schema_version() -> str:
    return _SCHEMA_VERSION


@contextmanager
def brief_wait():
    """Within the block, a lock held by another RevenueChaser process is waited for only as long as a foreign
    holder is (~0.35 s), then ``StoreLockedError``. For best-effort bookkeeping writes (the ``job_runs`` row, #282)
    that must not hold up the caller for the ~29 s a real peer wait takes. In-process races keep their budget."""
    previous = getattr(_LOCAL, "brief", False)
    _LOCAL.brief = True
    try:
        yield
    finally:
        _LOCAL.brief = previous
