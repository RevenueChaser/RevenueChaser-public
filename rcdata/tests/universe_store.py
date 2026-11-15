"""A served ``spine.duckdb`` written straight from ``equity_universe``-shaped rows, for the board tests (#642 PR 6).

Since #642 PR 6 the boards' universe is the spine's (``core/universe.py``): its listed names (Tier A and B, no
``my_universe`` list here) with the spine's name, sector, industry and security type. The board tests were written
against ``equity_universe`` rows (``ticker``, ``name``, ``sector``, ``industry``, ``market_cap``, ``price``,
``quote``, ...); ``put`` and ``replace`` write those rows as spine ``security`` rows. The old table they also
went into left with raw.duckdb (#860), and with it the ``quote`` the spine universe read from it.

A row's ``market_cap`` and ``price`` are kept in ``MARKET``: the root ``conftest.py`` answers them from
``spine_reads.latest_market`` for a seeded ticker the served prices file has no bar for, so a test of a board's cap
filter needs no bars (and a test of the bars' own checks keeps the bars it seeded). The old table played that part.

A row's ``tier`` defaults to ``A``; ``security_type`` stays NULL unless the row gives one, so a test's
row's ``security_type`` types the name. It also books a good
``spine/security`` check, so ``universe.source_state`` gives no reason.
"""
from __future__ import annotations

import duckdb

from RevenueChaser.rcdata import ops, serving
from RevenueChaser.rcdata.build.spine import security

# Every table the spine readers expect, but not ``my_universe``: an empty list there would keep no name.
TABLES = ("security", "security_history", "gics_history", "index_membership")
_COLS = [c for c, _ in security.SECURITY]
# The source ``read.membership`` reads by default; anything else is the Compustat check, not the membership.
_MEMBERSHIP_SOURCE = "funds/index_holdings"


def _connect() -> duckdb.DuckDBPyConnection:
    path = serving.live_path("spine")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    have = {r[0] for r in con.execute("SELECT table_name FROM information_schema.tables").fetchall()}
    if serving.VERSION_TABLE not in have:
        con.execute(f"CREATE TABLE {serving.VERSION_TABLE} (kind TEXT, version INTEGER, built_at DOUBLE, "
                    "build_id TEXT)")
        con.execute(f"INSERT INTO {serving.VERSION_TABLE} VALUES ('spine', ?, 1, 'test')",
                    [serving.SERVING_SCHEMA_VERSION["spine"]])
    for table in TABLES:
        if table not in have:
            cols = ", ".join(f'"{c}" {t}' for c, t in security.SCHEMAS[table])
            con.execute(f"CREATE TABLE {table} ({cols})")
    return con


def _security_row(r: dict) -> dict:
    ticker = str(r["ticker"]).strip().upper()
    return {"ticker": ticker, "cik": (str(r["cik"]) if r.get("cik") else None), "name": r.get("name") or ticker,
            "exchange": r.get("exchange"), "tier": r.get("tier") or "A", "security_type": r.get("security_type"),
            "sector": r.get("sector"), "industry": r.get("industry"), "source": "sec/company_tickers_exchange"}


#: ``{ticker: {"market_cap", "price"}}`` of the rows ``put``/``replace`` wrote in this test (cleared per test).
MARKET: dict[str, dict] = {}


def _write(rows: list[dict], *, replace: bool) -> None:
    from RevenueChaser.core import spine_reads
    if replace:
        MARKET.clear()
    for r in rows:
        ticker = str(r["ticker"]).strip().upper()
        MARKET.pop(ticker, None)
        if r.get("market_cap") is not None or r.get("price") is not None:
            MARKET[ticker] = {"market_cap": r.get("market_cap"), "price": r.get("price")}
    con = _connect()
    try:
        if replace:
            con.execute("DELETE FROM security")
        out = [_security_row(r) for r in rows]
        for r in out:
            con.execute("DELETE FROM security WHERE ticker = ?", [r["ticker"]])
        if out:
            con.executemany(f"INSERT INTO security ({', '.join(_COLS)}) VALUES ({', '.join('?' * len(_COLS))})",
                            [[r.get(c) for c in _COLS] for r in out])
        con.execute("CHECKPOINT")
    finally:
        con.close()
    spine_reads.clear()
    if ops.latest_unskipped_check("spine/security") is None:
        ops.record_check("spine/security", "changed")


def put(rows: list[dict]) -> None:
    """``equity_universe``-shaped rows added to the spine (a ticker already there is replaced)."""
    _write(list(rows), replace=False)


def replace(rows: list[dict]) -> None:
    """``equity_universe``-shaped rows as the whole spine universe."""
    _write(list(rows), replace=True)


def membership(slug: str, tickers) -> None:
    """``tickers`` as the current members of index ``slug`` in the spine, replacing that slug's rows.

    The shape ``read.membership`` asks for: the fund files' source and an open ``valid_to``. Since #642 PR 6 this
    is the only thing ``core/index_registry`` reads, so a test that used to call ``index_lists.save_index`` seeds
    here instead."""
    con = _connect()
    try:
        con.execute("DELETE FROM index_membership WHERE index_slug = ? AND source = ?",
                    [str(slug), _MEMBERSHIP_SOURCE])
        for t in tickers:
            con.execute("INSERT INTO index_membership (index_slug, ticker, source) VALUES (?, ?, ?)",
                        [str(slug), str(t).strip().upper(), _MEMBERSHIP_SOURCE])
        con.execute("CHECKPOINT")
    finally:
        con.close()
    from RevenueChaser.core import spine_reads
    spine_reads.clear()
