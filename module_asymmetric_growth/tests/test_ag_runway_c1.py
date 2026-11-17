"""Decision C1 (avo, 17 Nov 2026): with positive free cash flow the runway is not needed, so it is neither a second
Survival point nor an unknown; with FCF of zero or less it is read as before. Synthetic records."""
from __future__ import annotations

from RevenueChaser.module_asymmetric_growth.engine import score_ticker

_TECH = {"price": 100.0, "dist_52w_pct": 0.05, "vol_ratio": 1.6, "above_sma50": True}


def _survival(ocf: float) -> dict:
    years = [{"fiscal_year": str(y), "revenue": r, "gross_profit": r * 0.6, "operating_cash_flow": ocf,
              "capex": 10.0, "total_debt": 10.0, "cash": 500.0, "total_assets": 1000.0, "diluted_shares": 100.0}
             for y, r in ((2021, 100.0), (2022, 130.0), (2023, 190.0))]
    fin = {"info": {"country": "United States", "longName": "Runway Co"}, "annual": years, "market_cap": 5e8,
           "source": "sec_edgar"}
    card = score_ticker("RNWY", fin, _TECH)
    return next(s for s in card["signals"] if s["key"] == "survival")


def _runway(sig: dict) -> dict:
    return next(s for s in sig["subs"] if s["param"] == "runway")


def test_runway_counts_only_when_fcf_is_not_positive():
    funded = _survival(ocf=60.0)                    # FCF +50
    assert _runway(funded)["not_needed"] is True and _runway(funded)["passed"] is None
    assert (funded["passed"], funded["known"], funded["total"]) == (2, 2, 2)

    burning = _survival(ocf=-90.0)                  # FCF -100, 500 of cash: 5 years of runway
    assert _runway(burning)["not_needed"] is False and _runway(burning)["passed"] is True
    assert (burning["passed"], burning["known"], burning["total"]) == (2, 3, 3)
