"""#156 (avo, 2026-10-09): the daily price tables live in their own ``.store/prices.duckdb``.

``price_bars_daily``, ``price_actions`` and their watermarks (``price_checks``, the shape of ``source_checks``)
declare MANIFEST ``"db": "prices"``, so the multi-GiB price history stays out of ``raw.duckdb`` and out of raw's
never-pruned weekly backups (review 2026-10-08 §6, F8). A store from before keeps the two tables and the price rows
of ``source_checks`` in raw until the first call moves them: copied, checked row by row, and only then removed from
raw. On the live store both tables are empty, so the move is two DROPs. Temp stores only.

D03 (#293, avo 2026-10-10): ``index_levels_daily`` (the SPX daily levels) joins them before it has a writer. A store
from before keeps the empty G1 table in raw until the first call moves it the same way, so on the live store the move
is one more DROP and the marker names it too.
"""
from __future__ import annotations

import logging
import math
from pathlib import Path

import duckdb
import pytest

from revenuechaser.core import rawstore

MOVED = ("price_bars_daily", "price_actions")
MARKER = "price_tables_to_prices_db"

_BARS = [
    ("AAA", "2026-10-06", 1.0, 2.0, 0.5, 1.5, 1.4, 100.0, None, "yfinance", "yfinance", 1.7e9, "r1", 1.7e9),
    ("AAA", "2026-10-07", 1.5, 2.5, 1.0, float("nan"), None, None, None, None, "uw", 1.7e9, "r1", 1.7e9),
    ("BBB", "2026-10-07", 9.0, 9.0, 9.0, 9.0, 9.0, 5.0, None, "yfinance", "yfinance", None, None, None),
]
_ACTIONS = [
    ("AAA", "2026-10-06", "dividend", 0.25, "2026-10-06", "yfinance", 1.7e9, "r1", 1.7e9),
    ("BBB", "2026-09-01", "split", 2.0, None, "yfinance", 1.7e9, "r1", 1.7e9),
]
_CHECKS = [
    ("price_actions", "yfinance", "AAA", 1.7e9, "r1"),
    ("price_bars_daily", "yfinance_max", "AAA", 1.7e9, "r1"),
    ("security_master", "uw", "AAA", 1.6e9, "id1"),           # a D22 identity stamp: stays in raw
]


def _con(path: Path, read_only: bool = True):
    return duckdb.connect(str(path), read_only=read_only)


def _tables(path: Path) -> set[str]:
    if not path.exists():
        return set()
    con = _con(path)
    try:
        return {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables "
                                          "WHERE table_schema = 'main'").fetchall()}
    finally:
        con.close()


def _dump(path: Path, table: str, where: str = "") -> list[tuple]:
    """Every row of ``table`` in ``path`` as text, sorted (NaN compares equal to itself here)."""
    con = _con(path)
    try:
        cols = [r[0] for r in con.execute("SELECT column_name FROM information_schema.columns WHERE table_name = ? "
                                          "ORDER BY ordinal_position", [table]).fetchall()]
        rows = con.execute(f"SELECT {', '.join(cols)} FROM {table} {where}").fetchall()
    finally:
        con.close()
    def cell(v):
        return "nan" if isinstance(v, float) and math.isnan(v) else (None if v is None else str(v))
    return sorted(tuple(cell(v) for v in r) for r in rows)


def _fresh():
    rawstore._TABLE_READY.clear()
    rawstore._ENSURED.clear()








# ── routing and the file ─────────────────────────────────────────────────────











def test_the_move_did_not_bump_the_schema_version():
    """A new file and no changed table (the #72 precedent): an old checkout ignores prices.duckdb."""
    assert rawstore.schema_version() == "13"


# ── the one-time move out of raw.duckdb ──────────────────────────────────────















# ── review round (2026-10-09): the guards each get a test, two processes, the marker ─────────────────────────────



_LATE = ("CCC", "2026-10-07", 1.0, 1.0, 1.0, 1.0, None, 1.0, None, None, "uw", None, None, None)














class _Killed(BaseException):
    """The process stops here (a SIGKILL, a power cut): nothing after it runs."""




# ── D03 (#293, avo 2026-10-10): index_levels_daily moves the same way ───────────────────────────────────────────────

D03 = "index_levels_daily"
LIVE_156_MARKER = "price_bars_daily:0,price_actions:0"        # what the #156 move left on the live store (case above)
_LEVELS = [
    ("^GSPC", "2026-10-06", 1.0, 2.0, 0.5, 1.5, None, "yfinance", 1.7e9, "r1", 1.7e9),
    ("^GSPC", "2026-10-07", 1.5, 2.5, 1.0, float("nan"), None, None, None, None, None),
]












