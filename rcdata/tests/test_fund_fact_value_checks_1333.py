"""``fact_jumps_100x`` and ``eps_over_1000`` (#1333 draft G-5): the two value checks over ``fundamental_fact``.

Both read the served table only, so these tests build it on a bare connection. The named rows are the audit's own
cases of 21 Nov 2026: KIDZ's 2024 revenue (1.07 bn -> 3.7 m) and UPC's 2023 (40 m -> 32.3 bn)."""
from __future__ import annotations

import duckdb
import pytest

from revenuechaser.rcdata.build.fundamentals import tables as fund_tables

FACT = ("cik TEXT, field TEXT, period_type TEXT, fiscal_year INTEGER, value DOUBLE, accn TEXT, filed DATE, "
        "preliminary BOOLEAN")


def _world(rows: list[tuple]) -> duckdb.DuckDBPyConnection:
    con = duckdb.connect()
    con.execute(f"CREATE TABLE fundamental_fact ({FACT})")
    con.executemany("INSERT INTO fundamental_fact VALUES (?, ?, ?, ?, ?, ?, ?, ?)", rows)
    return con


def _annual(cik: str, field: str, year: int, value: float, *, accn: str = "a", filed: str = "2026-02-01",
            preliminary: bool = False) -> tuple:
    return (cik, field, "annual", year, value, accn, filed, preliminary)


def test_an_annual_revenue_that_falls_100x_from_the_year_before_is_named():
    """KIDZ 2024: 1.07 bn in 2023 and 3.7 m in 2024, a unit error of the source."""
    con = _world([_annual("1", "revenue", 2023, 1.07e9), _annual("1", "revenue", 2024, 3.7e6, accn="b")])
    found = fund_tables._fact_value_issues(con)
    assert [(k, key) for k, key, _ in found] == [("fact_jumps_100x", "1:revenue:2024")]
    assert "named not dropped" in found[0][2]
    # Named only: the rule writes nothing, so the row stands as the source tagged it.
    assert con.execute("SELECT value FROM fundamental_fact WHERE fiscal_year = 2024").fetchone() == (3.7e6,)


def test_an_annual_revenue_that_rises_100x_is_named_once():
    """UPC 2023: 40 m in 2022 and 32.3 bn in 2023. The pair is one finding, keyed on the later year."""
    con = _world([_annual("2", "revenue", 2022, 4.0e7), _annual("2", "revenue", 2023, 3.23e10, accn="b")])
    assert [key for _, key, _ in fund_tables._fact_value_issues(con)] == ["2:revenue:2023"]


def test_total_assets_is_checked_the_same_way_and_ordinary_growth_is_not_named():
    con = _world([_annual("3", "total_assets", 2022, 1.0e6), _annual("3", "total_assets", 2023, 1.0e9, accn="b"),
                  _annual("4", "revenue", 2022, 1.0e8), _annual("4", "revenue", 2023, 3.0e8, accn="b")])
    assert [key for _, key, _ in fund_tables._fact_value_issues(con)] == ["3:total_assets:2023"]


def test_a_quarterly_row_and_a_preliminary_row_are_not_compared():
    """The rule is over annual rows of the filed statements: a quarter against a year is not a jump, and a
    preliminary row is not a filing."""
    con = _world([_annual("5", "revenue", 2023, 1.0e9),
                  ("5", "revenue", "quarterly", 2024, 3.0e6, "b", "2024-05-01", False),
                  _annual("6", "revenue", 2023, 1.0e9), _annual("6", "revenue", 2024, 3.0e6, accn="c",
                                                                preliminary=True)])
    assert fund_tables._fact_value_issues(con) == []


def test_a_sign_change_is_no_jump():
    """A loss-making year against a profitable one is not a unit error, and a ratio across zero says nothing."""
    con = _world([_annual("7", "revenue", 2023, 1.0e9), _annual("7", "revenue", 2024, -3.0e6, accn="b")])
    assert fund_tables._fact_value_issues(con) == []


def test_only_the_newest_filing_of_a_fiscal_year_is_compared():
    """A restated year holds two rows; the reader sees the newest filing's value, so the check compares that one."""
    con = _world([_annual("8", "revenue", 2023, 1.0e9),
                  # the first filing of 2024 was the unit error; the restatement fixed it
                  _annual("8", "revenue", 2024, 3.0e6, accn="b", filed="2025-02-01"),
                  _annual("8", "revenue", 2024, 1.1e9, accn="c", filed="2025-08-01")])
    assert fund_tables._fact_value_issues(con) == []


def test_an_eps_over_the_bound_is_named_and_a_real_one_is_not():
    """343 rows on the live file of 21 Nov 2026. Berkshire's A share earns some 20,000 dollars a share, so the
    bound sits well above any real per-share figure and the kind is a flag."""
    con = _world([_annual("9", "eps_diluted", 2023, 25_000.0), _annual("9", "eps_basic", 2023, 5.0),
                  _annual("9", "eps_diluted", 2022, -2_000.0, accn="b")])
    assert [(k, key) for k, key, _ in fund_tables._fact_value_issues(con)] == [
        ("eps_over_1000", "9:eps_diluted:2022"), ("eps_over_1000", "9:eps_diluted:2023")]


def test_both_kinds_are_registered_with_their_bounds_named():
    """``ops.sync_issues`` writes a kind only when ``ISSUE_KINDS`` describes it, and the Settings board shows that
    text, so each bound is named there."""
    assert fund_tables.ISSUE_KINDS["fact_jumps_100x"].count("FACT_JUMP_F") == 2
    assert "FACT_EPS_MAX" in fund_tables.ISSUE_KINDS["eps_over_1000"]
    assert fund_tables.FACT_JUMP_FACTOR == pytest.approx(100.0)
    assert fund_tables.FACT_EPS_MAX == pytest.approx(1000.0)
    assert fund_tables.FACT_JUMP_FIELDS == ("revenue", "total_assets")
