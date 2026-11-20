"""``wrds/exrt``: Compustat's daily exchange rates against a fake worker (never WRDS), step H of the WRDS plan
(#1181). Every row is quoted from GBP, so the rate we keep is a cross; it is staged beside Yahoo's and compared,
and nothing served reads it yet."""
from __future__ import annotations

from datetime import date

import duckdb
import pytest

from RevenueChaser.rcdata import ops
from RevenueChaser.rcdata.build import DATASETS
from RevenueChaser.rcdata.build.fundamentals import common, fx_rates, wrds_fund
from RevenueChaser.rcdata.build.spine import wrds as spine_wrds

from . import fund_fixture as fx

EXRT = wrds_fund.EXRT
AS_OF = date(2026, 10, 27)


def _con(rows: list[tuple], yahoo: list[tuple] = ()) -> duckdb.DuckDBPyConnection:
    """A scratch connection with the staged snapshot (``(tocurd, datadate, exratd)`` rows, all from GBP) and
    Yahoo's staged rates (``(currency, day, usd_per_unit)``)."""
    con = duckdb.connect()
    cols = ", ".join(f'"{c}" {t}' for c, t in EXRT.schema + wrds_fund.PROVENANCE)
    con.execute(f"CREATE TEMP TABLE {EXRT.raw_staging} ({cols})")
    for c, d, v in rows:
        con.execute(f"INSERT INTO {EXRT.raw_staging} VALUES ('GBP', ?, ?, ?, ?, 1.0, 'w1')", [c, d, v, AS_OF])
    cols = ", ".join(f'"{c}" {t}' for c, t in fx_rates.SCHEMA)
    con.execute(f"CREATE TEMP TABLE {fx_rates.STAGING} ({cols})")
    for c, d, v in yahoo:
        con.execute(f"INSERT INTO {fx_rates.STAGING} VALUES (?, ?, ?, ?, 2.0, 'y1')", [c, d, v, AS_OF])
    return con


def _staged(con) -> list[tuple]:
    return con.execute(f"SELECT currency, day, round(usd_per_unit, 6) FROM {EXRT.staging} ORDER BY currency, day"
                       ).fetchall()


def test_a_rate_is_the_cross_through_the_base_currency():
    """1.25 USD and 1.75 CAD per GBP: one CAD is 1.25 / 1.75 USD, and one GBP is 1.25 USD."""
    con = _con([("USD", "2026-10-26", 1.25), ("CAD", "2026-10-26", 1.75), ("JPY", "2026-10-26", 190.0)])
    assert EXRT.cross(con) == 3
    assert _staged(con) == [("CAD", date(2026, 10, 26), round(1.25 / 1.75, 6)), ("GBP", date(2026, 10, 26), 1.25),
                            ("JPY", date(2026, 10, 26), round(1.25 / 190.0, 6))]
    assert con.execute(f"SELECT DISTINCT source_as_of, run_id FROM {EXRT.staging}").fetchall() == [(AS_OF, "w1")]


def test_the_base_currencys_own_row_is_not_counted_twice():
    con = _con([("USD", "2026-10-26", 1.25), ("GBP", "2026-10-26", 1.0)])
    EXRT.cross(con)
    assert _staged(con) == [("GBP", date(2026, 10, 26), 1.25)]


def test_a_day_without_a_usd_rate_and_a_rate_of_zero_serve_nothing():
    con = _con([("JPY", "2026-10-22", 190.0),                              # no USD row that day: no cross
                ("USD", "2026-10-23", 1.2), ("CAD", "2026-10-23", 0.0),    # a zero is no rate
                ("USD", "2026-10-24", 0.0), ("CAD", "2026-10-24", 1.7)])   # nor is a zero USD rate
    EXRT.cross(con)
    assert _staged(con) == [("GBP", date(2026, 10, 23), 1.2)]


def test_the_note_counts_the_newest_years_pairs_that_agree_with_yahoo():
    con = _con([("USD", "2026-10-26", 1.25), ("CAD", "2026-10-26", 1.75),
                ("USD", "2026-10-23", 1.25), ("CAD", "2026-10-23", 1.75),
                ("USD", "2020-01-02", 1.25), ("CAD", "2020-01-02", 1.75)],
               yahoo=[("CAD", "2026-10-26", 0.7143),          # within 1%
                      ("CAD", "2026-10-23", 0.75),            # 5% off
                      ("CAD", "2020-01-02", 0.7143),          # older than the newest year: not counted
                      ("GBP", "2026-10-26", 1.25)])
    EXRT.cross(con)
    note = EXRT.note(con)
    assert "2 currencies, 2020-01-02 to 2026-10-26" in note
    assert "2 of 3 (currency, day) pairs of the newest year agree with Yahoo within 1%" in note
    assert "not at Compustat: " in note and "CAD" not in note.split("not at Compustat: ")[1]


def test_no_snapshot_yet_says_so():
    con = _con([])
    EXRT.cross(con)
    assert EXRT.note(con) == "WRDS exrt_dly: no snapshot yet"


def test_the_dataset_is_registered_attended_monthly_and_feeds_no_served_table():
    assert DATASETS[EXRT.name] is EXRT and EXRT.cadence == "monthly" and EXRT.starts_by_hand
    assert EXRT.feeds == () and EXRT.tables == ()
    assert EXRT.full_rebuild_reason(None) is None


@pytest.fixture
def fake(monkeypatch):
    fx.spine()
    conn = fx.FakeFundWrds()
    monkeypatch.setattr(spine_wrds, "_factory", lambda: conn)
    spine_wrds.reset()
    yield conn
    spine_wrds.reset()


def test_one_query_asks_the_currencies_we_convert_and_the_snapshot_is_typed(fake):
    check = fx.run(EXRT.name, mode="backfill", to="2026-10-27")
    assert check["result"] == "changed", check["note"]
    assert len(fake.queries) == 1 and ops.calls_today("wrds") == 1
    sql = fake.queries[0]
    assert "FROM comp.exrt_dly" in sql and "fromcurd = 'GBP'" in sql
    assert "'USD'" in sql and all(f"'{c}'" in sql for c in fx_rates.CURRENCIES)
    path = common.parquet_dir(EXRT.name) / "snapshot=2026-10-27" / "exrt_dly.parquet"
    assert duckdb.sql(f"SELECT count(*), count(DISTINCT tocurd) FROM read_parquet('{path}')").fetchall() == [(6, 4)]
    assert "2 currencies, 2026-10-23 to 2026-10-26" in check["note"]        # CAD and GBP; JPY had no USD day
    check = fx.run(EXRT.name, "2026-11-10")
    assert len(fake.queries) == 1 and "snapshot of 2026-10-27 is current" in check["note"]
