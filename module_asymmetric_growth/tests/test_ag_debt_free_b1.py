"""Decision B1 (avo, 17 Nov 2026): a name that tags no debt and pays no interest reads as owing nothing, by the
Fundamentals rule (``module_fundamentals.debt``, #737), flagged ``debt_inferred_none``. Synthetic records."""
from __future__ import annotations

from revenuechaser.module_asymmetric_growth.engine import score_ticker

_TECH = {"price": 100.0, "dist_52w_pct": 0.05, "vol_ratio": 1.6, "above_sma50": True}


def _year(y: int, r: float, **extra) -> dict:
    return {"fiscal_year": str(y), "revenue": r, "gross_profit": r * 0.6, "operating_cash_flow": r * 0.3,
            "capex": r * 0.05, "cash": 200.0, "total_assets": 1000.0, "diluted_shares": 100.0,
            "period_ends": {"revenue": f"{y}-12-31", "total_assets": f"{y}-12-31"}, **extra}


def _card(annual, quarterly=(), us_gaap=True) -> dict:
    fin = {"info": {"country": "United States", "longName": "Debtless Co"}, "annual": annual,
           "quarterly": list(quarterly), "market_cap": 5e8, "source": "sec_edgar", "us_gaap": us_gaap}
    return score_ticker("DBTL", fin, _TECH)


def _net_debt(card: dict) -> dict:
    survival = next(s for s in card["signals"] if s["key"] == "survival")
    return next(s for s in survival["subs"] if s["param"] == "net_debt_assets")


_YEARS = [_year(2021, 100.0), _year(2022, 130.0), _year(2023, 190.0)]


def test_no_debt_tag_and_no_interest_reads_as_net_cash_and_nothing_else_does():
    card = _card(_YEARS)
    sub = _net_debt(card)
    assert sub["value"] == -0.2 and sub["passed"] is True
    assert "debt_inferred_none" in card["flags"]

    # Interest above the floor, a later quarter that tags debt, an IFRS filer: debt stays unknown.
    assert _net_debt(_card([*_YEARS[:2], _year(2023, 190.0, interest_expense=5e6)]))["value"] is None
    assert _net_debt(_card(_YEARS, [{"period": "2024-03-31", "short_term_borrowings": 50.0}]))["value"] is None
    assert _net_debt(_card(_YEARS, us_gaap=False))["value"] is None

    # A filed total is the filer's figure, not an inference.
    card = _card([*_YEARS[:2], _year(2023, 190.0, total_debt=300.0)])
    assert abs(_net_debt(card)["value"] - 0.1) < 1e-9 and "debt_inferred_none" not in card["flags"]
