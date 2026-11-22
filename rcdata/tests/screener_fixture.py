"""A live ``options.duckdb`` holding the earnings-set tables a board reads: ``option_screener_daily`` (the earnings
calendar) and ``earnings_tape`` (the ``/earnings/{ticker}`` answer of an earnings-set name, #644).

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


def tape_row(ticker: str, *, session_date: date, report_date: date, report_time: str = "premarket",
             **over) -> dict:
    """One ``earnings_tape`` row: the name, the evening it was fetched and the print's own fields (#644)."""
    out = {"session_date": session_date, "ticker": ticker, "report_date": report_date,
           "report_time": report_time, "ending_fiscal_quarter": report_date, "report_source": "uw",
           "actual_eps": 1.10, "street_mean_est": 1.00, "price": 50.0,
           "expected_move": 2.5, "expected_move_perc": 0.05,
           "post_earnings_move_1d": 0.04, "long_straddle_1d": 0.10}
    out.update(over)
    return out


def write(rows: list[dict], version: int | None = None) -> None:
    """A live ``options.duckdb`` holding ``rows`` in ``option_screener_daily`` (called again to add more)."""
    from revenuechaser.rcdata.build.options.tables import OPTION_SCREENER_DAILY as table
    _write(table, rows, version)


def write_tape(rows: list[dict], version: int | None = None) -> None:
    """The same file holding ``rows`` in ``earnings_tape`` (#644); called beside :func:`write` or on its own."""
    from revenuechaser.rcdata.build.options.tables import EARNINGS_TAPE as table
    _write(table, rows, version)


def _write(table, rows: list[dict], version: int | None = None) -> None:
    from revenuechaser.rcdata import serving
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
