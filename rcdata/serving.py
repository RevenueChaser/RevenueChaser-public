"""Serving files: built as a new file, checked, then swapped over the live one; read only through ``open_read`` (D1).

One builder process writes. Each kind (``market``; ``spine`` since PR 5; ``prices`` since PR 7; ``ownership`` since
PR 16; ``fundamentals`` since PR 12; ``options`` since PR 18) is built into ``<kind>.<build_id>.duckdb``
beside the live ``<kind>.duckdb`` under ``config.MARKET_DIR``; ``BuildFile.swap`` closes the writer (after a
``CHECKPOINT``, so no ``.wal`` is left), opens the new file read-only, checks its ``serving_schema_version`` row and
the row count of every expected table, and only then moves it into place. On any failure — a check, or an exception inside the
``build()`` block — the new file is deleted and the live file is not touched (test T3).

The swap never leaves the live name missing: the previous file is first copied to ``<kind>.prev.duckdb`` under
``prev_dir()`` (hard-linked where that is the live files' own disk), then ``os.replace`` moves the new file over the live name in one
step. A reader that opened the old file keeps reading it; the next ``open_read`` gets the new one.

A build either starts empty (``build(kind)``, every table made from Parquet) or as a copy of the live file
(``build(kind, base="live")``), for a build that replaces only what changed. The copy is a build file like any
other — the live file is never opened read-write — so the checks, the atomic swap, the ``prev`` rollback and the
shrink guard all hold unchanged. ``serving_schema_version.build_mode`` says which base the build really got:
``"live"`` falls back to ``"fresh"`` when there is no live file or it carries another serving schema version.

The dashboard and the boards open serving files with ``open_read`` only: read-only, the path resolved on every
call, never a connection kept across requests. Serving files are never compacted; they are rebuilt (F10 B).
"""
from __future__ import annotations

import atexit
import logging
import os
import shutil
import time
import uuid
import zlib
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

import duckdb

from ..core import config

# The serving schema of each kind lives in ``serving_versions.py``, not here: this file is in every kind's rules
# fingerprint (``build/dirty.py``), so a number kept here made one kind's bump a whole build of all six (#649).
from .serving_versions import SERVING_SCHEMA_VERSION, SHRINKS_BY_CHOICE

logger = logging.getLogger(__name__)

KINDS = tuple(SERVING_SCHEMA_VERSION)
VERSION_TABLE = "serving_schema_version"
# The base a build starts from: an empty file, or a copy of the live one (``build``).
BUILD_MODES = ("fresh", "live")
# A table may lose at most this share of its live rows in one build without an explicit allow_shrink. The datasets
# only ever add or replace rows, so any real shrink is a build from a partial or missing Parquet tree.
MAX_SHRINK = 0.01
# The tables whose row count is a chosen list (``SHRINKS_BY_CHOICE``) live in ``serving_versions.py`` for the same
# reason as the versions: a table added to that list must not be a whole build of all six kinds.
# The tables a kind's code no longer builds, by kind: the live file may still hold one, and the build may leave it
# out (its swap removes it with the old file). Any other live table missing from a build is still refused, because
# that is a build from a partial Parquet tree. ``allow_shrink`` cannot stand in for this: the "missing" check comes
# first, and a request-wide flag would relax every other table of the kind with it (review M2 of #382).
#   prices: ``crsp_unadjusted`` (#353's CRSP bars no action adjusted); PR 382 serves no CRSP bar, so it is gone.
RETIRED_TABLES: dict[str, tuple[str, ...]] = {"prices": ("crsp_unadjusted",)}
# A build file's own bookkeeping, not served data (``build/dirty.py``: the Parquet manifest and the build code's
# fingerprint, and ``prices``' identity, ``build/prices/incremental.py``): neither the shrink nor the missing-table
# check applies to it.
META_TABLES = ("build_manifest", "build_rules", "build_identity")
# A table that serves only its newest sessions (``option_eod``, G8) names the first value it keeps here, in its own
# build file (``declare_window``), so the shrink check compares the rows both files are meant to hold: a session
# that left the window is not a loss, a session inside it that lost rows is.
WINDOW_TABLE = "serving_window"
# The build connection's memory and threads. DuckDB's own default is 80 % of the machine's RAM per connection, and the
# kernel, not DuckDB, ended the first ``prices/serving`` build on #319's ASOF joins: request #35, 30 Oct 2026, OOM-killed
# at a 7.7 GB peak on the 15 GB server beside the dashboard. Under a limit DuckDB spills instead (``spill_dir``).
# A DuckDB size string (``5GB``) and a positive whole number; empty or invalid keeps the default.
# The limit is chosen at build start from what the machine can still give (``auto_memory_limit``): a fixed 5 GB was
# both too much and too little — the ``sec_forms`` build of 19 Nov 2026 (build 808) was OOM-killed at it while about
# 10 GB was free, and a build that starts while the box is busy needs less, not the same. This constant is only the
# fallback for a machine whose free memory cannot be read; ``RC_DUCKDB_MEMORY_LIMIT`` still overrides everything.
MEMORY_LIMIT_DEFAULT = "5GB"
# The share of what is available that the build connection may take (``RC_DUCKDB_MEMORY_SHARE``, 0 < share <= 1).
# Not all of it: DuckDB's own limit counts only its buffers, and the Python process, Arrow batches and the spill
# bookkeeping live outside it — the share is what leaves room for them and for the rest of the box.
MEMORY_SHARE_DEFAULT = 0.6
# The limit never leaves this range (``RC_DUCKDB_MEMORY_FLOOR`` / ``RC_DUCKDB_MEMORY_CAP``, DuckDB sizes). The floor
# is below the 2.5 GB peak of an incremental build only because DuckDB spills instead of failing; the cap keeps a
# quiet box from handing one build everything, which is what DuckDB's own 80 %-of-RAM default did (#319).
MEMORY_FLOOR_DEFAULT = "2GB"
MEMORY_CAP_DEFAULT = "12GB"
# Where "what is available" is read from. Both are consulted and the smaller wins: the kernel's MemAvailable says
# what the box has, the process's cgroup says what it is allowed (homesrv runs the builder under a systemd
# ``MemoryMax``, so free host RAM alone would be a limit the cgroup kills the build for taking).
MEMINFO_PATH = Path("/proc/meminfo")
PROC_CGROUP_PATH = Path("/proc/self/cgroup")
CGROUP_ROOT = Path("/sys/fs/cgroup")
# A read connection's buffer pool (``RC_DUCKDB_READ_MEMORY_LIMIT``). DuckDB's own default is 80 % of RAM (8 GiB on
# homesrv), and the one database instance a process keeps per path holds what every open connection read: the
# relatedness run, 8 workers reading business texts from sec_forms.duckdb, grew to 7.3 GB anon and was OOM-killed on
# 15 Nov 2026 (measured: 400 business texts took one process from 49 MB to 2.6 GB). A reader needs no more than this.
READ_MEMORY_LIMIT_DEFAULT = "1GiB"
THREADS_DEFAULT = 3
# The most a build may spill (``RC_DUCKDB_MAX_TEMP``, a DuckDB size): past it the build fails, it does not fill the disk.
# DuckDB's own default is 90 % of the free space. 2010-2025 of history spilled 9.5 GB at its largest statement (#372).
MAX_TEMP_DEFAULT = "200GB"
# A build needs room for its copy of the live file on the live files' disk: it does not start with less free space
# than ``RC_BUILD_MIN_FREE`` (a DuckDB size) or twice the live file, whichever is larger. 15 Nov 2026 the root SSD
# filled to 100 % and froze homesrv for 40 minutes; ext4's 5 % root reserve does not cover the builder (user life).
MIN_FREE_DEFAULT = "10GiB"
_SIZE_BYTES = {"KIB": 2**10, "MIB": 2**20, "GIB": 2**30, "TIB": 2**40,
               "KB": 10**3, "MB": 10**6, "GB": 10**9, "TB": 10**12}
_SIZE_UNITS = tuple(_SIZE_BYTES)


def _size(env: str, default: str) -> str:
    value = os.getenv(env, "").strip().replace(" ", "")
    return value if value[:1].isdigit() and value.upper().endswith(_SIZE_UNITS) else default


def _spill_cap(cap: str, spill_parent: Path) -> str:
    """The smaller of ``cap`` and 90 % of the free space on ``spill_parent``'s disk (DuckDB's own default, which a set
    cap replaces): a 200 GB cap must not let a spill moved to the SSD (``RC_DUCKDB_TEMP_DIR``, or ``MARKET_RAW_DIR``
    falling back into the checkout) fill the disk the live stores share (#379)."""
    unit = next(u for u in _SIZE_UNITS if cap.upper().endswith(u))
    try:
        cap_bytes = float(cap[:-len(unit)]) * _SIZE_BYTES[unit]
    except ValueError:                        # not a number DuckDB reads either: it refuses it at connect
        return cap
    room = shutil.disk_usage(spill_parent).free * 0.9
    return cap if cap_bytes <= room else f"{int(room) // 1000}KB"


def _read_int(path: Path) -> int | None:
    """``path``'s contents as a whole number, or None when it is missing, unreadable or not a number (a cgroup
    file holding ``max`` reads as None: no limit there)."""
    try:
        return int(path.read_text().strip())
    except (OSError, ValueError):
        return None


def _meminfo_available() -> int | None:
    """``MemAvailable`` in bytes: the kernel's own estimate of what a new allocation can get without swapping."""
    try:
        for line in MEMINFO_PATH.read_text().splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 2**10          # meminfo is in kB
    except (OSError, ValueError, IndexError):
        return None
    return None


def _cgroup_dir() -> Path:
    """The process's own cgroup v2 folder under ``CGROUP_ROOT``, or the root itself when there is no v2 line."""
    try:
        for line in PROC_CGROUP_PATH.read_text().splitlines():
            fields = line.split(":", 2)
            if len(fields) == 3 and fields[0] == "0":        # cgroup v2 has this one line
                return CGROUP_ROOT / fields[2].strip().lstrip("/")
    except OSError:
        pass
    return CGROUP_ROOT


def _cgroup_headroom() -> int | None:
    """How much the process's cgroup still allows, in bytes, or None where no limit is set on it.

    Every level up to the root is read, because a limit set on a parent slice binds its children: on homesrv the
    builder's ``MemoryMax`` is on its own unit and Claude's sessions have another on theirs. ``memory.high`` counts
    too — past it the kernel throttles and reclaims, which is where a build goes from slow to killed.
    """
    folder = _cgroup_dir()
    room: int | None = None
    while True:
        limits = [v for v in (_read_int(folder / "memory.max"), _read_int(folder / "memory.high")) if v is not None]
        current = _read_int(folder / "memory.current")
        if limits and current is not None:
            level = min(limits) - current
            room = level if room is None else min(room, level)
        if folder == CGROUP_ROOT or CGROUP_ROOT not in folder.parents:
            return room
        folder = folder.parent


def available_memory() -> int | None:
    """What a build may count on, in bytes: the smaller of the kernel's ``MemAvailable`` and the cgroup's headroom.
    None when neither can be read (not Linux, or ``/proc`` not mounted), which keeps ``MEMORY_LIMIT_DEFAULT``."""
    seen = [v for v in (_meminfo_available(), _cgroup_headroom()) if v is not None]
    return min(seen) if seen else None


def _memory_share() -> float:
    try:
        share = float(os.getenv("RC_DUCKDB_MEMORY_SHARE", "").strip())
    except ValueError:
        return MEMORY_SHARE_DEFAULT
    return share if 0 < share <= 1 else MEMORY_SHARE_DEFAULT


def auto_memory_limit() -> str:
    """The build connection's ``memory_limit`` for the machine as it is now: a share of what is available
    (:func:`available_memory`), never below ``RC_DUCKDB_MEMORY_FLOOR`` nor above ``RC_DUCKDB_MEMORY_CAP``.

    More when the box is quiet, less when it is not. A floor below what the build needs is not a failure: DuckDB
    spills past its limit (``spill_dir``). ``RC_DUCKDB_MEMORY_LIMIT`` set to a size skips all of this.
    """
    available = available_memory()
    if available is None:
        return MEMORY_LIMIT_DEFAULT
    floor = _bytes(_size("RC_DUCKDB_MEMORY_FLOOR", MEMORY_FLOOR_DEFAULT))
    cap = _bytes(_size("RC_DUCKDB_MEMORY_CAP", MEMORY_CAP_DEFAULT))
    chosen = max(floor, min(cap, int(available * _memory_share())))
    return f"{chosen // 10**6}MB"


def build_config(spill_parent: Path | None = None) -> dict[str, str | int]:
    """``memory_limit``, ``threads`` and ``max_temp_directory_size`` for a build connection, from
    ``RC_DUCKDB_MEMORY_LIMIT`` / ``RC_DUCKDB_THREADS`` / ``RC_DUCKDB_MAX_TEMP``; given the spill folder's parent, the
    spill cap is held to 90 % of that disk's free space (``_spill_cap``).

    With no ``RC_DUCKDB_MEMORY_LIMIT``, the memory limit follows the machine (``auto_memory_limit``).
    """
    try:
        threads = int(os.getenv("RC_DUCKDB_THREADS", "").strip())
    except ValueError:
        threads = THREADS_DEFAULT
    max_temp = _size("RC_DUCKDB_MAX_TEMP", MAX_TEMP_DEFAULT)
    return {"memory_limit": _size("RC_DUCKDB_MEMORY_LIMIT", "") or auto_memory_limit(),
            "threads": threads if threads > 0 else THREADS_DEFAULT,
            "max_temp_directory_size": _spill_cap(max_temp, spill_parent) if spill_parent else max_temp}


def spill_dir(path: Path) -> Path:
    """Where the build file ``path`` spills: under the raw root (the server's HDD), one folder per build, which DuckDB
    removes when the build closes. Not beside the build file: request 71 spilled 47 GB on the SSD the live files share
    (#372). ``RC_DUCKDB_TEMP_DIR`` moves the parent folder (a later move to the SSD, once a build's logged spill peak
    says it fits); unset or empty keeps the raw root."""
    root = os.getenv("RC_DUCKDB_TEMP_DIR", "").strip()
    return (Path(root) if root else Path(config.MARKET_RAW_DIR) / "build_tmp") / f"{path.name}.tmp"


class DiskTooFull(RuntimeError):
    """Too little free space on the live files' disk to start a build; nothing was written."""


def _bytes(size: str) -> int:
    s = size.strip().upper().replace(" ", "")
    unit = next((u for u in sorted(_SIZE_BYTES, key=len, reverse=True) if s.endswith(u)), None)
    return int(float(s[:-len(unit)]) * _SIZE_BYTES[unit]) if unit else int(s)


def check_room(kind: str, folder: Path) -> None:
    """Refuse a build of ``kind`` when ``folder``'s disk has less free space than ``MIN_FREE`` or twice the live file."""
    live = live_path(kind)
    need = max(_bytes(_size("RC_BUILD_MIN_FREE", MIN_FREE_DEFAULT)), 2 * live.stat().st_size if live.exists() else 0)
    free = shutil.disk_usage(folder).free
    if free < need:
        raise DiskTooFull(f"{kind} build not started: {free / 2**30:.1f} GiB free on {folder}, "
                          f"needs {need / 2**30:.1f} GiB (RC_BUILD_MIN_FREE or twice the live file)")


class SwapRefused(RuntimeError):
    """The new build failed its checks; it was deleted and the live file left as it was."""


class ServingFileMissing(FileNotFoundError):
    """No live serving file of this kind yet (nothing has been built)."""


def _kind(kind: str) -> str:
    if kind not in SERVING_SCHEMA_VERSION:
        raise ValueError(f"unknown serving kind {kind!r}; known: {KINDS}")
    return kind


def live_path(kind: str) -> Path:
    return Path(config.MARKET_DIR) / f"{_kind(kind)}.duckdb"


def prev_dir() -> Path:
    """Where the rollback copies live: ``RC_SERVING_PREV_DIR``, else ``serving_prev`` under the raw root (the server's
    HDD). Not beside the live files: six ``.prev`` files held 8.6 GB of the SSD the live files share (15 Nov 2026)."""
    root = os.getenv("RC_SERVING_PREV_DIR", "").strip()
    return Path(root) if root else Path(config.MARKET_RAW_DIR) / "serving_prev"


def prev_path(kind: str) -> Path:
    return prev_dir() / f"{_kind(kind)}.prev.duckdb"


def build_path(kind: str, build_id: str) -> Path:
    return Path(config.MARKET_DIR) / f"{_kind(kind)}.{build_id}.duckdb"


def new_build_id() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]


def open_read(kind: str) -> duckdb.DuckDBPyConnection:
    """A read-only connection to the live ``kind`` file, resolved now. The caller closes it (``with`` works).

    DuckDB caches one database instance per path in a process (S7): a connection kept open across a swap goes on
    reading the build it opened. Open and close per request, as ``read`` does.
    """
    path = live_path(kind)
    if not path.exists():
        raise ServingFileMissing(f"no {kind} serving file at {path} yet")
    con = connect_read(path)
    con.execute(f"SET memory_limit = '{read_memory_limit()}'")
    from . import opens
    opens.note(kind, path, con, VERSION_TABLE)       # #566: which build this job read; never raises
    return con


def connect_read(path: Path) -> duckdb.DuckDBPyConnection:
    """A read-only connection to ``path`` that spills into this process's own directory (``read_spill_dir``).

    Every read-only open of a serving file goes through here, so the one database instance a process keeps per path
    is always asked for with the same configuration.
    """
    return duckdb.connect(str(path), read_only=True, config={"temp_directory": str(read_spill_dir(path))})


_SPILL_DIRS: set[Path] = set()


def read_spill_dir(path: Path) -> Path:
    """``<file>.tmp-<pid>`` beside ``path``, removed when this process exits; with ``RC_TMP_DIR`` set (homesrv:
    the SSD temp root ``/srv/tmp/rc``, avo 17 Nov 2026), ``<RC_TMP_DIR>/duckdb-read/<file>.<folder hash>.tmp-<pid>``.

    DuckDB's default, ``<file>.tmp``, is one directory for every process that reads the file, and its spill file names
    (``duckdb_temp_storage_<size>-<n>.tmp``) restart at 0 in each process: two readers that spill at once write over
    each other's blocks. On 17 Nov 2026 the forecast baselines (SIGBUS) and the dashboard (SIGSEGV) crashed inside
    DuckDB 4 s apart, both reading ``prices.duckdb`` through the shared ``prices.duckdb.tmp``. The folder hash keeps
    two same-named files of one process (a live file and its backup copy) on two folders under the temp root.
    """
    root = os.getenv("RC_TMP_DIR", "").strip()
    if root:
        parent, name = Path(root) / "duckdb-read", f"{path.name}.{zlib.crc32(str(path.parent).encode()):08x}"
        parent.mkdir(parents=True, exist_ok=True)
    else:
        parent, name = path.parent, path.name
    spill = parent / f"{name}.tmp-{os.getpid()}"
    if spill not in _SPILL_DIRS:
        _SPILL_DIRS.add(spill)
        atexit.register(shutil.rmtree, spill, True)
        for old in parent.glob(f"{name}.tmp-*"):     # left by a process that was killed (SIGKILL, OOM)
            if stale_spill(old):
                shutil.rmtree(old, True)
    return spill


def scratch_dir(name: str, fallback: Path | None) -> Path | None:
    """Where a big scratch folder goes: ``<RC_TMP_HDD_DIR>/<name>`` (made here) when that is set (homesrv: the HDD
    temp root ``/mnt/data/tmp/rc``, avo 17 Nov 2026), else ``fallback`` (the raw folder; ``None`` = the system's)."""
    root = os.getenv("RC_TMP_HDD_DIR", "").strip()
    if not root:
        return fallback
    folder = Path(root) / name
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def stale_spill(path: Path) -> bool:
    """A ``<file>.tmp-<pid>`` spill directory (``read_spill_dir``) whose process is gone."""
    _, sep, pid = path.name.rpartition(".tmp-")
    if not (sep and pid.isdigit() and path.is_dir()):
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return True
    except PermissionError:                                    # alive, another user's
        return False
    return False


def read_memory_limit() -> str:
    """The buffer-pool cap of a read connection: ``RC_DUCKDB_READ_MEMORY_LIMIT`` when it is a DuckDB size, else
    ``READ_MEMORY_LIMIT_DEFAULT``."""
    return _size("RC_DUCKDB_READ_MEMORY_LIMIT", READ_MEMORY_LIMIT_DEFAULT)


def _remove(path: Path) -> None:
    for p in (path, path.with_name(path.name + ".wal")):
        try:
            p.unlink()
        except FileNotFoundError:
            pass


class BuildFile:
    """One build in progress: its read-write connection, path and id. Made by :func:`build`."""

    def __init__(self, kind: str, build_id: str, path: Path, con: duckdb.DuckDBPyConnection, mode: str):
        self.kind, self.build_id, self.path, self.con = kind, build_id, path, con
        # What this file started as, for the datasets: under ``"live"`` their tables are already here with the
        # live rows, under ``"fresh"`` the file is empty and every table is built whole.
        self.mode = mode
        self.swapped = False

    def close(self) -> None:
        if self.con is not None:
            self.con.close()
            self.con = None

    def swap(self, expected_counts: dict[str, int], checks: Iterable[dict] = (), *,
             allow_shrink: Iterable[str] = ()) -> Path:
        """Check this build and move it over the live file; :class:`SwapRefused` (file deleted) when a check fails.

        ``expected_counts`` maps every table the build must hold to its row count; ``checks`` are the build's
        ``dataset_check`` rows, and one whose result is ``failed`` refuses the swap. Every table of the live file
        must be in the build and may not empty or shrink by more than ``MAX_SHRINK`` (B2: the expected counts come
        from the build itself, so only the live file can show a build made from a missing Parquet tree). The tables
        named in ``allow_shrink`` (the asking dataset's own, on a request's explicit ``"allow_shrink": true``) may
        shrink or empty; every other table keeps the guard (review S-1 of #220: the flag used to switch the check off
        for the whole file, and another dataset's table could empty under it). A windowed table
        (``declare_window``) is compared on its rows inside the build's window, in both files.
        """
        self.con.execute("CHECKPOINT")
        self.close()
        try:
            _verify(self.kind, self.path, expected_counts, list(checks))
            shrank = _verify_against_live(self.kind, self.path, relax=frozenset(allow_shrink))
        except Exception as e:
            _remove(self.path)
            raise SwapRefused(f"{self.kind} build {self.build_id} refused: {e}") from e
        live, prev = live_path(self.kind), prev_path(self.kind)
        if live.exists():
            prev.parent.mkdir(parents=True, exist_ok=True)
            _remove(prev)
            try:
                os.link(live, prev)
            except OSError:
                shutil.copy2(live, prev)
        os.replace(self.path, live)
        self.swapped = True
        _record_small_shrinks(self.kind, self.build_id, shrank)
        return live


def _record_small_shrinks(kind: str, build_id: str, shrank: list[tuple[str, int, int]]) -> None:
    """A shrink under ``MAX_SHRINK`` swaps in, but no longer without a trace (#292 N-3): one open ``build_issues`` row
    per table, under the kind's name, kept until someone resolves it. A table that shrinks again adds no second row,
    so an hourly build cannot flood the list. Recording is best effort: the swap has happened and stays."""
    if not shrank:
        return
    try:
        from . import ops
        found = [("shrink", table, f"{before} -> {after} rows (under {MAX_SHRINK:.0%}, swapped in)")
                 for table, before, after in shrank]
        ops.sync_issues(kind, ["shrink"], found, run_id=build_id, keep=lambda kind_, key: True)
    except Exception:  # noqa: BLE001 - the file is already live; a failed note must not report a failed build
        pass


def _verify(kind: str, path: Path, expected_counts: dict[str, int], checks: list[dict]) -> None:
    failed = [c.get("dataset") for c in checks if c.get("result") == "failed"]
    if failed:
        raise ValueError(f"failed dataset checks: {failed}")
    if path.with_name(path.name + ".wal").exists():
        raise ValueError("the build file still has a .wal after its checkpoint")
    con = connect_read(path)
    try:
        rows = con.execute(f"SELECT kind, version FROM {VERSION_TABLE}").fetchall()
        if rows != [(kind, SERVING_SCHEMA_VERSION[kind])]:
            raise ValueError(f"{VERSION_TABLE} is {rows}, expected [({kind!r}, {SERVING_SCHEMA_VERSION[kind]})]")
        tables = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        for table, want in expected_counts.items():
            if table not in tables:
                raise ValueError(f"table {table} is missing")
            got = con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0]
            if got != want:
                raise ValueError(f"{table} has {got} rows, expected {want}")
    finally:
        con.close()


def sweep_builds(kind: str) -> list[Path]:
    """Remove the build files of ``kind`` a killed builder left (``<kind>.<build_id>.duckdb`` and its ``.wal``) and
    their spill folders (``spill_dir``: DuckDB removes one only when its build closes, so an OOM-killed build left
    19 GB of ownership and 22 GB of prices spill on homesrv, 10 Nov 2026); never the live or the ``prev`` file.
    Called by the builder at start, while it holds the ``rcdata_build`` lock, so no build of its own is in progress.
    Returns what it removed."""
    keep = {live_path(kind).name, prev_path(kind).name}
    removed = []
    for p in sorted(Path(config.MARKET_DIR).glob(f"{_kind(kind)}.*.duckdb*")):
        stem = p.name[:-4] if p.name.endswith(".wal") else p.name
        if stem in keep or not stem.endswith(".duckdb"):
            continue
        p.unlink(missing_ok=True)
        removed.append(p)
    for d in sorted(spill_dir(Path(f"{_kind(kind)}.duckdb")).parent.glob(f"{kind}.*.duckdb.tmp")):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
            removed.append(d)
    return removed


def declare_window(con: duckdb.DuckDBPyConnection, table: str, column: str, first) -> None:
    """Record in the build file that ``table`` keeps only the rows whose ``column`` is ``>= first``."""
    con.execute(f"CREATE TABLE IF NOT EXISTS {WINDOW_TABLE} (table_name TEXT PRIMARY KEY, column_name TEXT, "
                "first_value TEXT)")
    con.execute(f"INSERT OR REPLACE INTO {WINDOW_TABLE} VALUES (?, ?, ?)", (table, column, str(first)))


def _windows(path: Path) -> dict[str, tuple[str, str]]:
    con = connect_read(path)
    try:
        names = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
        if WINDOW_TABLE not in names:
            return {}
        return {t: (c, v) for t, c, v in con.execute(f"SELECT * FROM {WINDOW_TABLE}").fetchall()}
    finally:
        con.close()


def _counts(path: Path, windows: dict[str, tuple[str, str]] | None = None) -> dict[str, int]:
    """Rows per table; a windowed table counts only its rows inside the window (``windows``, the build's)."""
    windows = windows or {}
    con = connect_read(path)
    try:
        names = [r[0] for r in con.execute("SELECT table_name FROM duckdb_tables() WHERE database_name = "
                                           "current_database()").fetchall()
                 if r[0] not in (VERSION_TABLE, WINDOW_TABLE)]
        out = {}
        for n in names:
            sql, params = f'SELECT count(*) FROM "{n}"', []
            if n in windows:
                column, first = windows[n]
                sql += f' WHERE CAST("{column}" AS VARCHAR) >= ?'
                params.append(first)
            out[n] = int(con.execute(sql, params).fetchone()[0])
        return out
    finally:
        con.close()


def _verify_against_live(kind: str, path: Path, relax: frozenset[str] = frozenset()) -> list[tuple[str, int, int]]:
    """Refuse a build missing a live table, or (outside ``relax``) emptying or shrinking one by over MAX_SHRINK;
    return the ``(table, before, after)`` of each table that shrank by less, so the swap can say so (#292 N-3).

    A table of :data:`SHRINKS_BY_CHOICE` may shrink by any amount; it may still not empty. A table of
    :data:`RETIRED_TABLES` may be missing from the build: the code no longer builds it.
    """
    live = live_path(kind)
    if not live.exists():
        return []
    small: list[tuple[str, int, int]] = []
    windows = _windows(path)
    old, new = _counts(live, windows), _counts(path, windows)
    retired = set(RETIRED_TABLES.get(kind, ()))
    for table, before in sorted(old.items()):
        if table in META_TABLES:
            continue
        if table not in new and table in retired:
            continue
        if table not in new:
            raise ValueError(f"table {table} of the live file is missing from the build")
        after = new[table]
        if table in relax:
            continue
        if before > 0 and after == 0:
            raise ValueError(f"{table} empties: {before} rows live, 0 in the build")
        if table in SHRINKS_BY_CHOICE:
            continue
        if after < before * (1 - MAX_SHRINK):
            raise ValueError(f"{table} shrinks from {before} to {after} rows (more than {MAX_SHRINK:.0%})")
        if after < before:
            small.append((table, before, after))
    return small


def live_version(kind: str) -> int | None:
    """The serving schema version the live ``kind`` file was built by; ``None`` when there is no file, no version
    row, or more than one (a file no build of ours finished)."""
    try:
        with open_read(kind) as con:
            rows = con.execute(f"SELECT version FROM {VERSION_TABLE} WHERE kind = ?", (kind,)).fetchall()
    except (ServingFileMissing, duckdb.Error):
        return None
    return int(rows[0][0]) if len(rows) == 1 else None


def live_stamp(kind: str) -> dict | None:
    """``{kind, file, build_id, built_at}`` of the build that is live now, from the file's own version row
    (``_stamp``); ``None`` when there is no file. ``built_at`` is epoch seconds; ``build_id`` and ``built_at`` are
    None for a file with no single version row. Not an ``open_read``: looking at a file is not a board reading it
    (``rcdata/opens.py``, #566)."""
    from . import opens
    path = live_path(kind)
    if not path.exists():
        return None
    try:
        with connect_read(path) as con:
            build_id, built_at = opens.stamp_of(con, VERSION_TABLE, kind)
    except duckdb.Error:
        return None
    return {"kind": kind, "file": path.name, "build_id": build_id, "built_at": built_at}


def _copy_live(kind: str, path: Path) -> str:
    """Start the build file ``path`` as a copy of the live ``kind`` file; the mode that gave.

    ``"fresh"`` (nothing copied) when there is no live file, or it was built by another serving schema version:
    its tables are then not the ones this code builds, so only a whole build is safe. That is also what makes a
    version bump a full rebuild without any dataset asking for one.
    """
    if live_version(kind) != SERVING_SCHEMA_VERSION[kind]:
        return "fresh"
    # No ``.wal`` to carry over: ``swap`` checkpoints and closes before its checks, ``_verify`` refuses a build file
    # that still has one, and only the ``.duckdb`` is ever moved or linked. A ``.wal`` beside a live file would mean
    # something outside this module held the writer, and replaying that into a build is not the safe answer.
    shutil.copy2(live_path(kind), path)
    return "live"


def _stamp(con: duckdb.DuckDBPyConnection, kind: str, build_id: str, mode: str) -> None:
    """Write this build's one version row, over the row a copied live file brought with it."""
    con.execute(f"CREATE TABLE IF NOT EXISTS {VERSION_TABLE} (kind TEXT, version INTEGER, built_at DOUBLE, "
                "build_id TEXT, build_mode TEXT)")
    # A live file built before this column existed: the copy keeps its four columns until the first build adds it.
    con.execute(f"ALTER TABLE {VERSION_TABLE} ADD COLUMN IF NOT EXISTS build_mode TEXT")
    con.execute(f"DELETE FROM {VERSION_TABLE}")
    con.execute(f"INSERT INTO {VERSION_TABLE} (kind, version, built_at, build_id, build_mode) "
                "VALUES (?, ?, ?, ?, ?)", (kind, SERVING_SCHEMA_VERSION[kind], time.time(), build_id, mode))


@contextmanager
def build(kind: str, base: str = "fresh") -> Iterator[BuildFile]:
    """A new, stamped build file of ``kind``; deleted unless ``swap`` moved it into place inside the block.

    ``base="live"`` starts the file as a copy of the live one, for a build that replaces only what changed;
    ``b.mode`` and ``serving_schema_version.build_mode`` say what it really got, which is ``"fresh"`` when there
    was nothing to copy (:func:`_copy_live`). The live file itself is only ever read: the copy is checked and
    swapped like any other build.

    The only read-write handle the builder ever opens on a serving file is this one, on its own new file.
    """
    if base not in BUILD_MODES:
        raise ValueError(f"unknown build base {base!r}; known: {BUILD_MODES}")
    build_id = new_build_id()
    path = build_path(kind, build_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    check_room(kind, path.parent)
    spill = spill_dir(path)
    spill.parent.mkdir(parents=True, exist_ok=True)               # DuckDB makes only the last level
    try:
        mode = _copy_live(kind, path) if base == "live" else "fresh"
        settings = build_config(spill.parent)
        con = duckdb.connect(str(path), config={**settings, "temp_directory": str(spill)})
    except BaseException:
        _remove(path)      # a copy that broke mid-way is as large as the live file, on the live files' own disk
        raise
    # The limit follows the machine, so which one a build got is the first thing to know after an OOM or a long spill.
    available = available_memory()
    logger.info("build %s %s: memory_limit %s, threads %s, available %s", kind, build_id, settings["memory_limit"],
                settings["threads"], f"{available / 2**30:.1f} GiB" if available is not None else "unknown")
    b = BuildFile(kind, build_id, path, con, mode)
    try:
        _stamp(con, kind, build_id, mode)
        yield b
    finally:
        b.close()
        if not b.swapped:
            _remove(path)
