"""Which ticker a symbol used to be, and since when a ticker is its company's (K-E step 2).

A company that changes its ticker keeps its gvkey and iid, so Compustat's ``tic`` periods name every symbol it went
by. The spine copies them into ``security_history`` (``field = 'tic'``, ``source = 'wrds/sec_idhist'``) and fills
``ticker`` with the current ticker of the linked security, so a closed period that reads differently is an old
symbol of that security: BK until 2026-05-21 is BNY, PHB is IFLN, SPLG is SPYM. A store keyed by the symbol a
source wrote on a day reads this map to name its rows by date, which also keeps a reused ticker apart (GOLD was
Barrick's from 2019 to 2025 and is Gold.com's since 2025-12-02).

The spine is read from its live file, read-only and closed again, as ``ownership/common.py`` does; a caller that
already holds a connection passes it. No spine file, or a spine without the table, gives an empty map.

Rows left out as noise (measured on the live spine, 24 Nov 2026): a symbol ending in ``.<digits>`` or ``.H``
(TEVA.1, the old line after the move), one ending in a bare ``.``, and an iid ending in ``C`` or ``W``.
A move to an OTC or bankruptcy form of the same ticker (ALDF -> ALDFF) is a rename like any other (decision D1).
"""
from __future__ import annotations

import re
from datetime import date
from typing import NamedTuple

import duckdb

from .. import serving
from .spine.security import compustat_ticker

SPINE = "spine"
SOURCE = "wrds/sec_idhist"
_NOISE = re.compile(r"\.([0-9]+|H)?$")
_NOISE_IID = re.compile(r"[CW]$")


class Period(NamedTuple):
    """``symbol`` named the security that is ``ticker`` (``gvkey``:``iid``) today, from ``valid_from`` up to but
    not including ``valid_to``."""
    symbol: str
    valid_from: date
    valid_to: date
    ticker: str
    gvkey: str
    iid: str


def _rows(con: duckdb.DuckDBPyConnection | None) -> list[tuple]:
    """``(ticker, gvkey, iid, symbol, valid_from, valid_to)`` of every ``tic`` period that is not noise, the
    symbol spelled as the SEC writes it; ``ticker`` is None on an iid no current ticker is linked to."""
    own = con is None
    if own:
        try:
            con = serving.open_read(SPINE)
        except serving.ServingFileMissing:
            return []
    try:
        if not con.execute("SELECT count(*) FROM duckdb_tables() WHERE database_name = current_database() "
                           "AND table_name = 'security_history'").fetchone()[0]:
            return []
        rows = con.execute("SELECT ticker, gvkey, iid, value, valid_from, valid_to FROM security_history "
                           "WHERE field = 'tic' AND source = ? AND value IS NOT NULL", (SOURCE,)).fetchall()
    finally:
        if own:
            con.close()
    return [(t, g, i, compustat_ticker(v), f, to) for t, g, i, v, f, to in rows
            if not _NOISE.search(v.strip()) and not _NOISE_IID.search(i or "") and compustat_ticker(v)]


def periods(con: duckdb.DuckDBPyConnection | None = None) -> list[Period]:
    """Every closed period of an old symbol of a linked security, by symbol and date. A symbol that two current
    tickers held over the same days is ambiguous, and both periods are left out: no name beats a wrong one."""
    by_symbol: dict[str, list[Period]] = {}
    for t, g, i, s, f, to in _rows(con):
        if t is not None and f is not None and to is not None and s != t:
            by_symbol.setdefault(s, []).append(Period(s, f, to, t, g, i))
    out = []
    for found in by_symbol.values():
        out += [a for a in found if not any(a.ticker != b.ticker and a.valid_from < b.valid_to
                                            and b.valid_from < a.valid_to for b in found)]
    return sorted(out, key=lambda p: (p.symbol, p.valid_from, p.ticker))


def starts(con: duckdb.DuckDBPyConnection | None = None) -> dict[str, date]:
    """``{current ticker: the first day it named its company}``: the earliest period of that symbol on the
    ticker's gvkey, over every iid, so a listing that moved to another iid (TEVA, 2026-09-14) stays continuous."""
    rows = _rows(con)
    gvkeys = {(t, g) for t, g, *_ in rows if t is not None}
    first: dict[tuple[str, str], date] = {}
    for t, g, _, s, f, _ in rows:
        if t is not None and f is not None and (s, g) in gvkeys:
            first[(s, g)] = min(f, first.get((s, g), f))
    out: dict[str, date] = {}
    for (t, _), f in first.items():
        out[t] = min(f, out.get(t, f))
    return out
