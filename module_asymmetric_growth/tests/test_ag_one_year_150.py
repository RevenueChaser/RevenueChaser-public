"""#150 (27-6): one fiscal year per AG score (U8) and the EDGAR fallback on a store-only run (U7).

Synthetic records, no network, no live store.
"""
from __future__ import annotations

import pytest

from revenuechaser.core import rawstore
from revenuechaser.module_asymmetric_growth import engine
from revenuechaser.module_asymmetric_growth.engine import score_ticker

_TECH = {"price": 100.0, "dist_52w_pct": 0.05, "vol_ratio": 1.6, "above_sma50": True}


def _rec(fy, **kw) -> dict:
    base = {"fiscal_year": fy}
    base.update(kw)
    return base


def _card(annual, **extra) -> dict:
    fin = {"info": {"country": "United States", "exchange": "NMS", "longName": "One Year Co"},
           "annual": annual, "market_cap": 5e9, "source": "sec_edgar"}
    fin.update(extra)
    return score_ticker("ONEY", fin, _TECH, spine={})


def _sub(card: dict, param: str) -> dict:
    return next(s for sig in card["signals"] for s in sig["subs"] if s["param"] == param)


# ── U8 ──────────────────────────────────────────────────────────────────────

def test_growth_needs_the_adjacent_prior_year():
    # 2022 is missing: 2023 vs 2021 is a two-year change, not YoY.
    card = _card([_rec(2021, revenue=100.0), _rec(2023, revenue=200.0)])
    assert card["rev_growth"] is None
    assert _sub(card, "rev_growth")["passed"] is None          # unknown, not a fail (#151)


def test_acceleration_needs_three_adjacent_years():
    card = _card([_rec(2020, revenue=100.0), _rec(2022, revenue=150.0), _rec(2023, revenue=200.0)])
    assert card["rev_growth"] == pytest.approx(200.0 / 150.0 - 1)
    assert _sub(card, "accelerating")["value"] == (pytest.approx(200.0 / 150.0 - 1), None)
    assert _sub(card, "accelerating")["passed"] is None


def test_adjacent_years_give_growth_and_acceleration():
    card = _card([_rec(2021, revenue=100.0), _rec(2022, revenue=120.0), _rec(2023, revenue=180.0)])
    assert card["rev_growth"] == pytest.approx(0.5)
    assert _sub(card, "accelerating")["passed"] is True


def test_every_field_comes_from_the_one_anchor_year():
    # The 2023 record has revenue but no balance sheet; the 2022 balance sheet must not be borrowed.
    annual = [
        _rec(2022, revenue=100.0, gross_profit=60.0, operating_cash_flow=50.0, capex=10.0,
             total_debt=10.0, cash=500.0, total_assets=1000.0, rd_expense=30.0, diluted_shares=100.0),
        _rec(2023, revenue=130.0, gross_profit=78.0, operating_cash_flow=60.0, capex=10.0),
    ]
    card = _card(annual)
    assert card["fiscal_year"] == 2023
    assert card["fcf"] == pytest.approx(50.0)
    assert _sub(card, "net_debt_assets")["value"] is None
    assert card["runway_years"] == 999.0          # FCF >= 0, no liquidity needed
    assert card["rd_intensity"] is None
    assert card["dilution_yoy"] is None


def test_an_old_ocf_is_not_paired_with_a_new_capex():
    annual = [_rec(2022, revenue=100.0, operating_cash_flow=80.0),
              _rec(2023, revenue=130.0, capex=10.0)]
    card = _card(annual)
    assert card["fcf"] is None


def test_the_anchor_is_the_newest_year_with_revenue():
    annual = [_rec(2022, revenue=100.0, total_assets=900.0),
              _rec(2023, revenue=130.0, total_assets=1000.0),
              _rec(2024, total_assets=1100.0)]          # balance sheet only, no income statement yet
    card = _card(annual)
    assert card["fiscal_year"] == 2023


def test_records_without_a_fiscal_year_keep_the_positional_rule():
    card = _card([{"revenue": 100.0}, {"revenue": 120.0}, {"revenue": 180.0}])
    assert card["rev_growth"] == pytest.approx(0.5)
    assert card["fiscal_year"] is None


def test_dilution_compares_adjacent_years_only():
    annual = [_rec(2021, revenue=1.0, diluted_shares=100.0), _rec(2023, revenue=2.0, diluted_shares=200.0)]
    assert _card(annual)["dilution_yoy"] is None


def test_string_fiscal_years_are_adjacent_too():
    card = _card([_rec("2022", revenue=100.0), _rec("2023", revenue=150.0)])
    assert card["rev_growth"] == pytest.approx(0.5)


# ── U7 ──────────────────────────────────────────────────────────────────────

_EDGAR_ANNUAL = [_rec(2022, revenue=100.0, gross_profit=60.0), _rec(2023, revenue=130.0, gross_profit=78.0)]
_QUOTE = {"regularMarketPrice": 100.0, "fiftyTwoWeekHigh": 105.0, "fiftyDayAverage": 90.0,
          "averageDailyVolume10Day": 160.0, "averageDailyVolume3Month": 100.0}


def _edgar(monkeypatch, annual, meta):
    monkeypatch.setattr(engine.sec_edgar, "get_fundamentals", lambda t, no_fetch=False: (annual, [], meta))










def test_a_new_ocf_is_not_paired_with_an_old_capex():
    annual = [_rec(2022, revenue=100.0, capex=10.0), _rec(2023, revenue=130.0, operating_cash_flow=60.0)]
    assert _card(annual)["fcf"] is None


def test_total_assets_of_an_older_year_are_not_borrowed():
    annual = [_rec(2022, revenue=100.0, total_assets=1000.0),
              _rec(2023, revenue=130.0, total_debt=50.0, cash=20.0)]
    assert _sub(_card(annual), "net_debt_assets")["value"] is None


# ── G4 K1: the SEC business address decides non-US ──────────────────────────









