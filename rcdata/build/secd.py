"""Compustat's daily security file (``comp.secd``) as the raw layer stores it, and the one rule every reader of it
needs: **a stored row is a session only when it carries a price** (#423).

``wrds/prices`` writes the file as ``parquet/wrds/prices/secd/year=<Y>/part-0.parquet``, a faithful copy of what
WRDS answered. Compustat ships the year partition with its own forward-dated calendar placeholders: measured
read-only on homesrv on 5 Nov 2026, **1,128 rows over 929 tickers with ``datadate`` from 2026-11-03 to 2026-12-31
and ``prccd`` and ``cshtrd`` entirely NULL**. Nothing but the NULL price marks them apart, so a plain
``SELECT max(datadate)`` over the partitions answers about two months past the last real session — and does it
again with every new year partition.

Nothing shipped is wrong today, because both readers of the raw file already filter on the price. This module is
so that the next one cannot step into it by accident: :data:`PRICED` and :data:`PRICED_USD` are the filter, and
:func:`last_session` is the day, which is what a freshness check, a "data as of" label or a window bound
(``last session - n days``) must ask for instead of ``max(datadate)``.

Option A of #423, with B (filtering at write) refused: the stored partition stays what WRDS returned, which is
what the rest of the raw layer promises, and a partition already written would otherwise keep its placeholders
until it is fetched again — a store where the rule holds for some years and not others.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

from . import base
from .spine.stage import partitions

#: Where ``wrds/prices`` stores it, under ``base.parquet_root()``.
DATASET = ("wrds", "prices", "secd")
#: A real session: the row carries a close. The placeholders carry none (#423).
PRICED = "prccd > 0"
#: :data:`PRICED` and the currency the served bar keeps, so a day priced in another currency is no session either.
PRICED_USD = f"{PRICED} AND coalesce(upper(curcdd), 'USD') = 'USD'"


def root() -> Path:
    folder = base.parquet_root()
    for part in DATASET:
        folder = folder / part
    return folder


def files(years: int | None = None, as_of: date | None = None) -> list[Path]:
    """The stored year partitions, oldest first; the newest ``years`` of them when ``years`` is given. A year after
    ``as_of`` is not read at all, so a build of an earlier day reads that day's Compustat."""
    kept = [(y, f) for y, f in partitions(root(), "year")
            if y.isdigit() and (as_of is None or int(y) <= as_of.year)]
    return [f for _, f in (kept[-years:] if years else kept)]


def last_session(as_of: date | None = None, years: int = 2) -> date | None:
    """The newest ``datadate`` the stored partitions hold a **priced** row for, ``None`` with no partition and no
    priced row. Never ``max(datadate)`` over the raw file: that one reads Compustat's placeholders (#423).

    Only the newest ``years`` partitions are read, because the answer is the last session and a year of sessions
    is far more than enough to find it; a caller that has none of them reads further back by raising ``years``.
    """
    found = files(years, as_of)
    if not found:
        return None
    src = f"read_parquet([{', '.join(base.sql_path(f) for f in found)}], union_by_name = true)"
    cutoff = "" if as_of is None else f" AND datadate <= DATE '{as_of.isoformat()}'"
    con = base.scratch_con()
    try:
        day = con.execute(f"SELECT max(datadate) FROM {src} WHERE {PRICED}{cutoff}").fetchone()[0]
    finally:
        con.close()
    return day
