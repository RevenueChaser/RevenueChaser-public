"""What the last build of each serving kind did, read from the live file (#446 step 8B).

Every kind of #446 now builds on a copy of the live file when it can (``serving.build(kind, base="live")``), and
``prices`` holds its **whole** build back for a person (``base.WholeBuildByHand``). Both are invisible from the
outside: the Settings board showed a build's rows and its time, never whether those rows were rebuilt or carried
over, so "did the incremental flow actually stay incremental?" could only be answered by reading a log. This module
answers it from the files themselves.

**It reports the last build, not the next one.** ``dirty.plan`` would say what the next build will do, but it calls
``dirty.scan``, which stats every Parquet file of the kind -- minutes of disk for one page render, on every load.
Everything here is already written in the live file, so a kind costs one open and a few aggregates:

- ``serving.VERSION_TABLE``: ``build_mode`` (``live`` or ``fresh``), ``built_at``, ``build_id``, ``version``;
- ``dirty.MANIFEST_TABLE``: how many Parquet files that build was built from;
- ``audit.ROUNDS`` and ``audit.DIRTY`` (#446 step 5): the last audit round and the keys waiting for the next build.

The cost of reading the past is that a kind whose build code changed since its last build will be built whole next
time and nothing here can know it yet. The board says so in words rather than implying otherwise.

Read-only by construction: every open is ``serving.open_read`` (``duckdb.connect(..., read_only=True)``), so no
read of this module can apply the schema manifest to a file it meant only to read. A kind that cannot be read is
that kind's ``error`` string, never an exception, because this is drawn on a page that must not go blank for it.
"""
from __future__ import annotations

from typing import Any

import duckdb

from .. import serving
from . import audit, base, dirty

#: The build modes ``serving`` stamps, in the order the board lists them: a carried-over build first.
MODES = ("live", "fresh")


def _one(con: duckdb.DuckDBPyConnection, sql: str, *args) -> tuple | None:
    """One row of ``sql``, or None when the table is not in this file (a build from before it existed)."""
    try:
        return con.execute(sql, *args).fetchone()
    except duckdb.Error:
        return None


def _stamp(con: duckdb.DuckDBPyConnection, kind: str) -> dict:
    row = _one(con, f"SELECT build_mode, built_at, build_id, version FROM {serving.VERSION_TABLE} "
                    "WHERE kind = ?", (kind,))
    if row is None:
        # The table is there (the file opened) but has no ``build_mode`` column, or no row for this kind.
        row = _one(con, f"SELECT NULL, built_at, build_id, version FROM {serving.VERSION_TABLE} WHERE kind = ?",
                   (kind,))
    if row is None:
        return {}
    mode, built_at, build_id, version = row
    return {"mode": None if mode is None else str(mode),
            "built_at": None if built_at is None else float(built_at),
            "build_id": None if build_id is None else str(build_id),
            "version": None if version is None else int(version)}


def _count(con: duckdb.DuckDBPyConnection, table: str) -> int | None:
    """Rows of ``table``, or None when this file does not carry it — which is not the same as zero rows."""
    row = _one(con, f'SELECT count(*) FROM "{table}"')
    return None if row is None else int(row[0])


def _last_round(con: duckdb.DuckDBPyConnection) -> dict:
    """The newest audit round in the file: when it ran, how many keys it checked and how many differed.

    A round is every row of :data:`audit.ROUNDS` with the same ``checked_at``, because that is what one pass
    writes (``audit._record`` stamps every key of a subject with one ``now``). Several subjects audited in the
    same pass get the same stamp, so the count is the pass's, which is what the board asks.
    """
    row = _one(con, f'SELECT max(checked_at) FROM {audit.ROUNDS}')
    if row is None:
        return {}
    at = row[0]
    if at is None:
        return {"checked_at": None, "keys": 0, "differs": 0, "tables": []}
    counts = _one(con, f'SELECT count(*), count(*) FILTER (WHERE result = \'differs\') FROM {audit.ROUNDS} '
                       "WHERE checked_at = ?", (at,))
    tables = con.execute(f'SELECT DISTINCT "table" FROM {audit.ROUNDS} WHERE checked_at = ? ORDER BY 1',
                         (at,)).fetchall()
    return {"checked_at": float(at), "keys": int(counts[0]), "differs": int(counts[1]),
            "tables": [str(t[0]) for t in tables]}


def of(kind: str, datasets: Any = None) -> dict:
    """What the last build of ``kind`` did, as one row for the board.

    The keys that do not need the file (``incremental``, ``by_hand``, ``datasets``) are answered even when there is
    no file yet, so a kind nothing has built still says how it would be built.
    """
    members = list(base.kind_datasets(kind) if datasets is None else datasets)
    row: dict = {"kind": kind, "datasets": [d.name for d in members],
                 "incremental": dirty.incremental(members),
                 "by_hand": list(base.whole_build_by_hand(kind))}
    try:
        con = serving.open_read(kind)
    except serving.ServingFileMissing:
        return {**row, "built": False}
    except (duckdb.Error, OSError) as exc:
        return {**row, "built": False, "error": f"{type(exc).__name__}: {exc}"[:300]}
    try:
        row.update(_stamp(con, kind))
        row["parquet_files"] = _count(con, dirty.MANIFEST_TABLE)
        row["audit_dirty"] = _count(con, audit.DIRTY)
        row["audit"] = _last_round(con)
        row["built"] = True
    except (duckdb.Error, OSError) as exc:  # a half-written file is one row's error, never a blank page
        row = {**row, "built": True, "error": f"{type(exc).__name__}: {exc}"[:300]}
    finally:
        con.close()
    return row


def all_kinds(kinds: Any = None) -> list[dict]:
    """One :func:`of` row per serving kind, in ``serving.KINDS`` order. One unreadable kind is its own ``error``."""
    out = []
    for kind in (serving.KINDS if kinds is None else kinds):
        try:
            out.append(of(kind))
        except Exception as exc:  # noqa: BLE001 - the registry itself refusing one kind is that row, not the part
            out.append({"kind": kind, "built": False, "error": f"{type(exc).__name__}: {exc}"[:300]})
    return out
