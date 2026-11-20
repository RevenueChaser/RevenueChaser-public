"""The audit sample: every incremental build re-reads a few keys from Parquet and compares them with the file
(#446 step 5).

A build on the live copy never looks at the rows it carries over. So a row built wrongly — by a rule that was
once wrong, or by a dirty set that missed it — stays served until a whole build, and the whole build is what #446
is removing (``ownership/serve`` alone: 2,352 s and a 23.8 GB spill, homesrv, 12 Nov 2026). The audit is what
replaces it: each pass recomputes a small, risk-weighted sample of keys from Parquet and compares, so a
systematic fault shows up in days instead of never.

What a dataset declares is a :class:`Subject` per served table it can rebuild for one key::

    def audit(self, ctx):
        return [audit.Subject(table="sec13f_ticker_period", key="ticker", recompute=self._audit_sql)]

and ``recompute(ctx, con, keys)`` answers with SQL for that table's rows, for those keys only, read from Parquet.
The keys are also in :data:`KEYS_TABLE` for a query that would rather join than carry a list. A dataset that
declares no ``audit`` is not audited, exactly as a dataset that declares no ``dirty`` is not built incrementally,
so this module changes nothing until a kind's datasets declare.

Three rules the driver keeps:

- **The sample is risk-weighted.** A subject may declare ``weight`` — SQL answering ``(key, weight)`` — and the
  draw multiplies it by how long ago the key was last audited (:data:`ROUNDS`, carried in the serving file). A key
  never audited is the oldest there is. The draw itself is A-Res (``random() ** (1 / weight)``, largest first),
  which is a weighted sample without replacement in one pass.
- **A difference is evidence, not a refusal.** It opens a build issue (``ops.record_issue``, so the Logs board
  shows it) and marks the key for the **next** build (:data:`DIRTY`). ``dirty.plan`` reads those keys and hands
  them to the dataset (``Plan.audited``, ``ctx.audited``) for its own ``dirty`` to add to its dirty set, because
  only the dataset knows what its keys mean — ``market_series``' dirty keys are ``<source>/<year>``, not the
  ``series_id`` its audit subject would use. The file still swaps in: refusing it would stop the whole flow on one
  bad key, and the next pass rebuilds those keys anyway.
- **The cost is the sample, not the file.** Only the chosen keys are recomputed, and :data:`KEYS_ENV` (``0`` off)
  sets how many without a deploy.
"""
from __future__ import annotations

import logging
import random
import time
from typing import Any, Callable, Iterable, NamedTuple

import duckdb

from .. import ops

logger = logging.getLogger(__name__)

#: Keys per pass, per subject. The issue's own number, "500 keys/day for the first month".
KEYS = 500
#: ``RC_AUDIT_KEYS`` sets it without a deploy; ``0`` turns the audit off.
KEYS_ENV = "RC_AUDIT_KEYS"
#: Every key ever audited and how it came out: ``(table, key, checked_at, result)``, in the serving file.
ROUNDS = "build_audit"
#: The keys an audit found a difference for, for the next build to rebuild: ``(table, key, found_at)``.
DIRTY = "build_audit_dirty"
#: The chosen keys, for a ``recompute`` that would rather join than carry a list.
KEYS_TABLE = "audit_keys"
#: A key that has never been audited is read as this old, so it outweighs one audited yesterday.
NEVER_DAYS = 3650.0
#: The build issue's kind, so the Logs board can tell it from a source's own issues.
ISSUE = "audit"


class Subject(NamedTuple):
    """One served table that can be rebuilt for a single key.

    ``recompute(ctx, con, keys)`` answers with SQL yielding that table's rows **for those keys only**, read from
    Parquet, with the table's columns (the driver selects them by name, so their order in the SQL is free).
    ``weight`` is optional SQL yielding ``(key, weight)``: what makes a key worth looking at more often.
    """

    dataset: str
    table: str
    key: str
    recompute: Callable[[Any, duckdb.DuckDBPyConnection, tuple[str, ...]], str]
    weight: str | None = None


def subjects(datasets: Iterable[Any], ctx: Any) -> list[Subject]:
    """Every subject the datasets declare, in their order; empty when none does."""
    out: list[Subject] = []
    for d in datasets:
        step = getattr(d, "audit", None)
        if step is None:
            continue
        for s in step(ctx) or ():
            if not isinstance(s, Subject):
                raise TypeError(f"{getattr(d, 'name', d)}.audit returned {type(s).__name__}, not a Subject")
            out.append(s)
    return out


def wanted(env) -> int:
    """How many keys a subject is audited for this pass; 0 when the audit is off."""
    raw = (env.get(KEYS_ENV) or "").strip()
    if not raw:
        return KEYS
    try:
        return max(0, int(raw))
    except ValueError:
        return KEYS


def ensure_tables(con: duckdb.DuckDBPyConnection) -> None:
    """The two tables the audit carries in the serving file, made once and then kept by every live copy."""
    con.execute(f"CREATE TABLE IF NOT EXISTS {ROUNDS} "
                f'("table" TEXT, key TEXT, checked_at DOUBLE, result TEXT)')
    con.execute(f"CREATE TABLE IF NOT EXISTS {DIRTY} (\"table\" TEXT, key TEXT, found_at DOUBLE)")


def _columns(con: duckdb.DuckDBPyConnection, table: str) -> list[str]:
    return [d[0] for d in con.execute(f'SELECT * FROM "{table}" LIMIT 0').description]


def weights(con: duckdb.DuckDBPyConnection, subject: Subject, now: float) -> dict[str, float]:
    """Every key of ``subject``'s served table and what it is worth looking at: the weight the subject declares
    (1.0 when it declares none) times how many days ago the key was last audited, plus one.

    A key never audited counts as :data:`NEVER_DAYS` old, so it outweighs one audited yesterday without ever
    shutting a weighted key out.
    """
    key = f'CAST("{subject.key}" AS TEXT)'
    declared = (f"({subject.weight})" if subject.weight
                else "(SELECT NULL AS key, NULL AS weight WHERE false)")
    rows = con.execute(
        f'WITH served AS (SELECT DISTINCT {key} AS k FROM "{subject.table}" WHERE {key} IS NOT NULL), '
        f"w AS (SELECT CAST(key AS TEXT) AS k, CAST(weight AS DOUBLE) AS weight FROM {declared} AS declared), "
        f'seen AS (SELECT key AS k, max(checked_at) AS at FROM {ROUNDS} WHERE "table" = ? GROUP BY key) '
        "SELECT served.k, coalesce(w.weight, 1.0), seen.at "
        "FROM served LEFT JOIN w USING (k) LEFT JOIN seen USING (k)", (subject.table,)).fetchall()
    out: dict[str, float] = {}
    for k, weight, at in rows:
        days = NEVER_DAYS if at is None else min(max((now - float(at)) / 86400.0, 0.0), NEVER_DAYS)
        out[str(k)] = max(float(weight or 0.0), 0.0) * (1.0 + days)
    return out


def choose(con: duckdb.DuckDBPyConnection, subject: Subject, n: int, now: float, rng=None) -> tuple[str, ...]:
    """``n`` keys of ``subject``'s served table, drawn by :func:`weights` without replacement.

    The draw is A-Res — ``random() ** (1 / weight)``, largest first — which is one pass and gives each key a
    chance in proportion to its weight. Fewer keys when the table holds fewer; empty when it holds none.
    """
    if n <= 0:
        return ()
    rng = random if rng is None else rng
    scored = sorted(((rng.random() ** (1.0 / max(weight, 1e-9)), k)
                     for k, weight in weights(con, subject, now).items()), reverse=True)
    return tuple(k for _, k in scored[:n])


def differences(con: duckdb.DuckDBPyConnection, subject: Subject, keys: tuple[str, ...], sql: str) -> dict[str, int]:
    """``{key: rows that differ}`` for the keys whose recomputed rows and served rows are not the same set.

    Both directions: a row the recompute has and the file has not, and a row the file has and the recompute has
    not. A key with no difference is not in the answer.
    """
    cols = ", ".join(f'"{c}"' for c in _columns(con, subject.table))
    key = f'CAST("{subject.key}" AS TEXT)'
    served = f'SELECT {cols} FROM "{subject.table}" WHERE {key} IN (SELECT key FROM {KEYS_TABLE})'
    fresh = f"SELECT {cols} FROM ({sql}) WHERE {key} IN (SELECT key FROM {KEYS_TABLE})"
    rows = con.execute(f"SELECT {key} AS k, count(*) FROM ("
                       f"({fresh} EXCEPT {served}) UNION ALL ({served} EXCEPT {fresh})"
                       ") GROUP BY 1").fetchall()
    found = {str(k): int(n) for k, n in rows if k is not None}
    return {k: found[k] for k in keys if k in found}


def _put_keys(con: duckdb.DuckDBPyConnection, keys: tuple[str, ...]) -> None:
    con.execute(f"CREATE OR REPLACE TEMP TABLE {KEYS_TABLE} (key TEXT)")
    if keys:
        con.execute(f"INSERT INTO {KEYS_TABLE} SELECT unnest(?::TEXT[])", (list(keys),))


def _record(con: duckdb.DuckDBPyConnection, subject: Subject, keys: tuple[str, ...],
            differ: dict[str, int], now: float) -> None:
    results = [("differs" if k in differ else "ok") for k in keys]
    con.execute(f'INSERT INTO {ROUNDS} SELECT ?, unnest(?::TEXT[]), ?, unnest(?::TEXT[])',
                (subject.table, list(keys), now, results))
    con.execute(f'DELETE FROM {DIRTY} WHERE "table" = ? AND key IN (SELECT unnest(?::TEXT[]))',
                (subject.table, list(keys)))
    if differ:
        con.execute(f"INSERT INTO {DIRTY} SELECT ?, unnest(?::TEXT[]), ?",
                    (subject.table, sorted(differ), now))


def run(ctx: Any, con: duckdb.DuckDBPyConnection, found: list[Subject], env, run_id: str | None = None) -> dict:
    """Audit every subject of this build: ``{table: [keys that differ]}``, empty when nothing differs.

    Never raises on a subject's own SQL: an audit that cannot run is logged and the build goes on, because this
    is evidence about the file, not a check of it.
    """
    n, now, out = wanted(env), time.time(), {}
    if not found or n <= 0:
        return out
    ensure_tables(con)
    for subject in found:
        try:
            keys = choose(con, subject, n, now)
            if not keys:
                continue
            _put_keys(con, keys)
            differ = differences(con, subject, keys, subject.recompute(ctx, con, keys))
            _record(con, subject, keys, differ, now)
        except duckdb.Error:
            logger.exception("audit of %s could not run", subject.table)
            continue
        logger.info("audit %s: %d key(s), %d differ", subject.table, len(keys), len(differ))
        if not differ:
            continue
        out[subject.table] = sorted(differ)
        for key, rows in sorted(differ.items()):
            ops.record_issue(subject.dataset, ISSUE, key,
                             f"{subject.table}: {rows} row(s) differ from a recompute of this key from Parquet; "
                             "the key is dirty for the next build", run_id)
    return out


def dirty_keys(con: duckdb.DuckDBPyConnection, tables: Iterable[str]) -> frozenset[str]:
    """The keys an earlier audit found a difference for, over ``tables``; empty when the table is not there yet
    (a live file from before this landed)."""
    wanted_tables = [str(t) for t in tables]
    if not wanted_tables:
        return frozenset()
    try:
        rows = con.execute(f'SELECT DISTINCT key FROM {DIRTY} WHERE "table" IN (SELECT unnest(?::TEXT[]))',
                           (wanted_tables,)).fetchall()
    except duckdb.Error:
        return frozenset()
    return frozenset(str(r[0]) for r in rows if r[0] is not None)
