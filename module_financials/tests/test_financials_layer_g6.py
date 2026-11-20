"""Financials on the data layer (G6, build plan PR 15): statements from the SEC facts, the risk-free rate from
``market_series``.

The DCF, the three-statement model and the credit grades read the annual statements. On the fundamentals layer
those are the SEC's (``core/fundamentals_layer``), not Yahoo's: a figure the SEC facts do not carry (current assets
and liabilities) stays empty, so the engines' labelled defaults show (review S1). The tax provision, pre-tax income
and interest expense the layer does serve since #645 G1, and ``test_financials_sec_fields_645.py`` covers them. EBITDA is operating income plus depreciation when the year has both. Price, shares and beta come
from the prices store since the G6 follow-up (``test_financials_market_prices.py``). The ten-year yield is read from
``market_series`` (DGS10, FRED; review S2), the old ``macro_series`` row only while the market file is not there.
"""
from __future__ import annotations

import copy
from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core.tests.test_fundamentals_layer import CIK, TICKER, built, grw_facts  # noqa: F401
from RevenueChaser.rcdata import ops, serving
from RevenueChaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401  (fixtures)


def _serve_dgs10(points):
    with serving.build("market") as b:
        b.con.execute("CREATE TABLE market_series (series_id TEXT, obs_date DATE, source TEXT, value DOUBLE, "
                      "frequency TEXT, session_date DATE, source_as_of DATE, fetched_at DOUBLE, run_id TEXT)")
        for day, value in points:
            b.con.execute("INSERT INTO market_series VALUES ('DGS10', ?, 'fred', ?, 'daily', ?, ?, 1.0, 'r1')",
                          [day, value, day, day])
        b.swap({"market_series": len(points)})
    ops.record_check("market_series", "changed", run_id="r1")


def _clock(monkeypatch):
    from RevenueChaser.core import calendar
    monkeypatch.setattr(calendar, "_now", lambda: datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc))




def test_a_stale_market_series_yield_is_not_used(monkeypatch, market_roots):  # noqa: F811
    import RevenueChaser.module_financials.run as fm
    _clock(monkeypatch)
    _serve_dgs10([("2026-10-13", 4.1)])                                         # fifteen days old
    assert fm._stored_risk_free() is None


def test_the_statements_are_the_secs_on_the_layer(built):  # noqa: F811
    import RevenueChaser.module_financials.run as fm
    annual, meta = fm._sec_statements(TICKER)
    assert [r["fiscal_year"] for r in annual] == ["2024", "2025"]
    assert [r["period_end"] for r in annual] == ["2024-12-31", "2025-12-31"]
    newest = annual[-1]
    assert newest["revenue"] == 140.0 + 150 + 160 + 170                          # 2025's four quarters
    assert newest["capex"] == newest["capital_expenditure"] and newest["total_debt"] == 320.0
    # Nothing the SEC facts do not carry is filled: the engines' labelled defaults show (S1). This fixture's filer
    # tags no tax, pre-tax or interest line either, so those stay empty here (#645 G1 reads them where it does).
    for missing in ("ebitda", "pretax_income", "tax_provision", "interest_expense", "current_assets"):
        assert newest.get(missing) is None
    assert meta["newest_filed"] == "2026-08-01"


def test_ebitda_is_operating_income_plus_depreciation():
    import RevenueChaser.module_financials.run as fm
    row = fm._financials_record({"fiscal_year": "2025", "revenue": 100.0, "ebit": 20.0, "depreciation": 5.0,
                                 "period_ends": {"revenue": "2025-12-31"}})
    assert row["ebitda"] == 25.0 and row["period_end"] == "2025-12-31"
    assert "ebitda" not in fm._financials_record({"fiscal_year": "2025", "revenue": 100.0, "ebit": 20.0})


def test_off_the_layer_there_are_no_sec_statements(monkeypatch):
    import RevenueChaser.module_financials.run as fm
    assert fm._sec_statements(TICKER) is None                                  # no fundamentals.duckdb




# ── which statements a run models: the SEC's unless Yahoo's same year gives an input the SEC's lacks ──

_FULL = {"revenue": 100.0, "ebitda": 30.0, "ebit": 25.0, "depreciation": 5.0, "capex": 4.0,
         "receivables": 10.0, "inventory": 5.0, "payables": 8.0}


def _year(fy, drop=(), **extra):
    return {"fiscal_year": str(fy), **{k: v for k, v in _FULL.items() if k not in drop}, **extra}


@pytest.mark.parametrize("sec, yahoo, used, missing", [
    ([_year(2025)], [_year(2025)], "sec", []),                                                  # both whole
    ([_year(2025, drop=("ebitda", "depreciation"))], [_year(2025)], "yahoo", ["depreciation", "ebitda"]),  # MSFT
    ([_year(2025, drop=("inventory",))], [_year(2025, drop=("receivables", "inventory", "payables"),
                                                current_assets=50.0, current_liabilities=30.0)], "yahoo",
     ["working capital"]),                                                                      # a software filer
    ([_year(2013)], [_year(2026)], "yahoo", ["the fiscal year 2026"]),                          # TM: SEC years stale
    # The SEC's year is newer: its statements are modelled, and what they lack is named (Opus review S1).
    ([_year(2026, drop=("depreciation",))], [_year(2025)], "sec", ["depreciation"]),
    ([_year(2025, drop=("depreciation",))], [_year(2025, drop=("depreciation",))], "sec", ["depreciation"]),
    # The years compare on revenue (Opus review S2): a newer year with only a balance sheet is no newer year.
    ([_year(2025, drop=("depreciation",)), {"fiscal_year": "2026", "cash": 1.0}], [_year(2025)], "yahoo",
     ["depreciation"]),
    ([_year(2024)], [_year(2025), {"fiscal_year": "2026", "cash": 1.0}], "yahoo", ["the fiscal year 2025"]),
    ([_year(2025)], [], "sec", []),                                                             # no Yahoo payload
])
def test_the_statements_a_run_models(sec, yahoo, used, missing):
    import RevenueChaser.module_financials.run as fm
    assert fm._statements_choice(sec, yahoo) == (used, missing)


def test_the_sec_statements_end_on_the_newest_year_with_revenue(monkeypatch):
    # Opus review S2: a newest year the layer serves with only balance-sheet fields is not the DCF's base year.
    import RevenueChaser.module_financials.run as fm
    from RevenueChaser.core import fundamentals_layer
    years = [{"fiscal_year": "2024", "revenue": 90.0}, {"fiscal_year": "2025", "revenue": 100.0},
             {"fiscal_year": "2026", "cash": 5.0}]
    monkeypatch.setattr(fundamentals_layer, "reads_layer", lambda: True)
    monkeypatch.setattr(fundamentals_layer, "records", lambda t: (years, [], {"newest_filed": "2026-08-01"}))
    annual, _meta = fm._sec_statements(TICKER)
    assert [r["fiscal_year"] for r in annual] == ["2024", "2025"]








def test_a_bank_names_no_working_capital_gap():
    # Opus review N4: no model of a Financial Services target reads working capital (P/E only), so the choice
    # neither counts it nor names it there.
    import RevenueChaser.module_financials.run as fm
    sec = [_year(2025, drop=("receivables", "inventory", "payables"))]
    yahoo = [_year(2025)]
    assert fm._statements_choice(sec, yahoo) == ("yahoo", ["working capital"])
    assert fm._statements_choice(sec, yahoo, bank=True) == ("sec", [])






def test_on_yahoos_statements_the_tax_rate_is_not_named():
    import RevenueChaser.module_financials.run as fm
    used, lacking = fm._statements_choice([_year(2025, drop=("depreciation",))], [_year(2025)])
    assert used == "yahoo" and "tax rate" not in lacking
