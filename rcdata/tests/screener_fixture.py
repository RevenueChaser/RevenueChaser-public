"""A live ``options.duckdb`` holding ``option_screener_daily`` rows, for the boards that read the earnings calendar.

Written for #643 PR 5b, where the Welcome board's earnings card moves off the old ``raw.earnings_calendar`` onto the
options builder's screener table (needs ``earnings.next`` / ``options.screener``). The shape is the builder's own
(``rcdata/build/options/tables.py`` ``OPTION_SCREENER_DAILY``), so a test seeds the columns the real file has and
every column it leaves out is NULL. Same pattern as ``market_fixture``: no dataset run, no HTTP mock, no network.
"""
from __future__ import annotations

from datetime import date

import duckdb


def row(ticker: str, *, session_date: date, report_date: date, report_session: str = "premarket",
        **over) -> dict:
    """One screener row: the name, the session it was swept on, and the calendar fields the card reads."""
    out = {"session_date": session_date, "ticker": ticker, "report_date": report_date,
           "report_session": report_session, "report_time": report_session, "screened": True,
           "passes_gates": True, "full_name": f"{ticker} Inc", "expected_move_perc": 0.05,
           "implied_move_perc": 0.04, "marketcap": 1_500_000_000.0, "sector": "Technology"}
    out.update(over)
    return out


def write(rows: list[dict], version: int | None = None) -> None:
    """A live ``options.duckdb`` holding ``rows`` in ``option_screener_daily`` (called again to add more)."""
    from RevenueChaser.rcdata import serving
    from RevenueChaser.rcdata.build.options.tables import OPTION_SCREENER_DAILY as table
    path = serving.live_path("options")
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute(f"CREATE TABLE IF NOT EXISTS {serving.VERSION_TABLE} (kind TEXT, version INTEGER, "
                    "built_at DOUBLE, build_id TEXT)")
        if not con.execute(f"SELECT 1 FROM {serving.VERSION_TABLE} WHERE kind = 'options'").fetchone():
            con.execute(f"INSERT INTO {serving.VERSION_TABLE} VALUES ('options', ?, 0, 'test')",
                        [version or serving.SERVING_SCHEMA_VERSION["options"]])
        cols = ", ".join(f'"{c}" {t}' for c, t in table.schema)
        con.execute(f"CREATE TABLE IF NOT EXISTS {table.name} ({cols})")
        names = table.columns
        for r in rows:
            con.execute(f"INSERT INTO {table.name} ({', '.join(names)}) "
                        f"VALUES ({', '.join('?' * len(names))})", [r.get(c) for c in names])
    finally:
        con.close()
