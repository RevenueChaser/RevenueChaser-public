"""``build/secd.py``: the last **priced** Compustat session, and why ``max(datadate)`` is not it (#423).

Measured read-only on homesrv on 5 Nov 2026: the stored ``comp.secd`` held 1,128 rows over 929 tickers with
``datadate`` from 2026-11-03 to 2026-12-31 and ``prccd`` and ``cshtrd`` NULL — Compustat's own calendar
placeholders, which come down with the year partition. They are shaped here as they were found.
"""
from __future__ import annotations

from datetime import date

from revenuechaser.rcdata.build import base, secd
from revenuechaser.rcdata.build.prices import stage as prices_stage, wrds_history

PROVENANCE = {"source_as_of": date(2026, 11, 2), "fetched_at": 1.0, "run_id": "test"}


def _row(day: date, close: float | None) -> dict:
    """One ``secd`` row; a placeholder is a day with no close and no volume, every other column as Compustat
    sends it."""
    return {"gvkey": "012141", "iid": "01", "datadate": day, "tic": "MSFT", "cusip": "594918104",
            "curcdd": "USD", "prccd": close, "prcod": close, "prchd": close, "prcld": close,
            "cshtrd": None if close is None else 1_000_000.0, "cshoc": 7.4e9,
            "ajexdi": 1.0, "trfd": 1.0, "exchg": 14, **PROVENANCE}


def _put(rows: list[dict]) -> None:
    by_year: dict[int, list[dict]] = {}
    for r in rows:
        by_year.setdefault(r["datadate"].year, []).append(r)
    for year, part in by_year.items():
        prices_stage.write_rows(part, wrds_history.SECD + wrds_history.PROVENANCE,
                                wrds_history.partition_path("secd", year), order="gvkey, iid, datadate")


def _raw_max() -> date:
    """``max(datadate)`` over the stored partitions, which is what the trap looks like."""
    files = secd.files()
    con = base.scratch_con()
    try:
        return con.execute("SELECT max(datadate) FROM read_parquet([" +
                           ", ".join(base.sql_path(f) for f in files) + "], union_by_name = true)").fetchone()[0]
    finally:
        con.close()


def test_the_last_session_is_the_last_priced_day_not_the_last_stored_one():
    _put([_row(date(2026, 10, 30), 100.0), _row(date(2026, 11, 2), 101.0),
          _row(date(2026, 11, 3), None), _row(date(2026, 12, 31), None)])
    assert _raw_max() == date(2026, 12, 31), "the placeholders are stored as Compustat sent them"
    assert secd.last_session() == date(2026, 11, 2)


def test_a_placeholder_in_the_next_year_partition_is_skipped_too():
    """The bug comes back with every new year partition, so the answer may not be the newest partition's max."""
    _put([_row(date(2026, 11, 2), 101.0), _row(date(2027, 1, 4), None)])
    assert secd.last_session() == date(2026, 11, 2)


def test_the_last_session_is_never_later_than_the_day_asked_for():
    _put([_row(date(2026, 10, 30), 100.0), _row(date(2026, 11, 2), 101.0), _row(date(2026, 11, 3), None)])
    assert secd.last_session(as_of=date(2026, 10, 31)) == date(2026, 10, 30)


def test_without_a_partition_or_a_priced_row_there_is_no_last_session():
    assert secd.last_session() is None
    _put([_row(date(2026, 11, 3), None)])
    assert secd.last_session() is None


def test_the_priced_filter_is_one_string_every_reader_uses():
    """``PRICED_USD`` is ``PRICED`` and the currency, so a reader cannot take half the rule by accident."""
    assert secd.PRICED == "prccd > 0" and secd.PRICED in secd.PRICED_USD and "curcdd" in secd.PRICED_USD
