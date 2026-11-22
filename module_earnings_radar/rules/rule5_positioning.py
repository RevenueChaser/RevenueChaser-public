"""Rule 5: Positioning & short squeeze.

Who is positioned how, and what does that imply for the stock's reaction to
earnings? Two independent components, at least one of which must be present or
the rule is unavailable (never a zero fill):

1. **Institutional lean** — from UW flow-recent, by the print's side (docs/module_earnings-radar/redesign.md R5, review S4):
   bullish = ask-side calls + bid-side puts, bearish = bid-side calls + ask-side puts, mid dropped, institutional
   = size >= 10 AND premium >= $10k (``aggregate_flow``). The net is scaled by the sided premium (a one-sided
   but small imbalance scores less than a clean sweep); a net under ``INST_FLOW_MIN_NET`` is Thin (present, no
   lean); no side served is no lean; a material multi-leg package is left out and tagged ``package-risk``.
   The prints the lean reads are sliced first (``module_earnings_radar/lean.py``, #256): the last
   ``R5_LEAN_SESSIONS`` sessions of the tape, strikes inside the R4 expected-move band, expiries from the report
   day out to ``R5_LEAN_EXPIRY_DAYS`` days after it.
2. **Squeeze potential** — a ``none`` / ``fuel`` **tag** from the short interest or the borrow fee, never a score
   (``docs/module_earnings-radar/redesign.md`` R5: "``none`` / ``fuel`` from ``si_float`` or ``fee_rate``. No Z ladder.
   Low SI != bearish", #256). ``fuel`` when the short interest is at or above ``R5_FUEL_SI_PCT`` percent or the
   borrow fee at or above ``R5_FUEL_FEE_PCT`` percent a year; ``none`` below both. There is no utilization figure:
   UW serves none and the parser never derives one (#250). Days to cover is shown in the drawer's metrics and is
   not part of the tag, because FINRA's twice-monthly figure is the only basis for it.

The peer Z ladder this rule used to score (+40 / +25 / +15 above peer Z 3 / 2 / 1, and -10 below -1) is gone with
#256: it made a low short interest bearish, which the design rules out, and it compared borrow fees across names
whose float and listing age differ.

Honest inputs:
- missing fields are ``None``, never 0, so a missing borrow fee cannot silently
  read as "cheap to borrow";
- a name with neither a short interest nor a borrow fee has no squeeze component (it is missing, not ``none``);
- retail-call euphoria is NOT scored here — that fade lives in R8 (sentiment).
  Scoring the same 65%+ retail-call share in both R5 and R8 double-faded it.
"""
from typing import Optional

from datetime import date

from RevenueChaser.core.config import (
    INST_FLOW_MIN_NET, R5_FUEL_FEE_PCT, R5_FUEL_SI_PCT, SCORE_RANGE,
)
from RevenueChaser.module_earnings_radar.models import RuleResult


def score(
    short_interest_pct_float: Optional[float] = None,
    days_to_cover: Optional[float] = None,
    borrow_fee: Optional[float] = None,
    institutional_net_delta: Optional[float] = None,
    institutional_call_premium: Optional[float] = None,
    institutional_put_premium: Optional[float] = None,
    institutional_side_served: Optional[bool] = None,
    institutional_package_premium: Optional[float] = None,
    short_as_of: Optional[str] = None,
    si_basis: Optional[str] = None,
) -> RuleResult:
    """``institutional_net_delta`` is the lean net (bullish minus bearish side premium) and the call/put premiums
    the bullish and bearish side premium. ``institutional_side_served`` False says the tape carried no print side,
    so there is no lean (the flow component is absent, never neutral). ``short_as_of`` is the FINRA settlement day the short figures are as of (#287): the squeeze reason
    names it, because a twice-monthly figure can be weeks old. ``si_basis`` "outstanding" says the short interest is
    a percent of the shares outstanding, not of the float (no float stored); the absolute read then says so."""
    available = False
    score_val = 0.0
    reasons: list[str] = []
    raw_metrics: dict = {}
    signals_present = 0
    signal_slots = 2  # flow + squeeze

    # ── Component 1: institutional lean by print side ──
    flow_signal = False
    if institutional_side_served is False:
        reasons.append("no print side: institutional lean unavailable")
        institutional_net_delta = None
    if institutional_net_delta is not None and institutional_net_delta != 0 \
            and abs(institutional_net_delta) < INST_FLOW_MIN_NET:
        # Thin is present (a real but small tape), not missing, and is no lean (redesign.md R5).
        reasons.append("thin institutional lean")
        raw_metrics["inst_net"] = round(float(institutional_net_delta), 2)
        flow_signal = True
        signals_present += 1
    elif institutional_net_delta is not None and institutional_net_delta != 0:
        ic = float(institutional_call_premium or 0)
        ip = float(institutional_put_premium or 0)
        total_inst = ic + ip
        if total_inst > 0:
            imbalance = institutional_net_delta / total_inst  # -1..+1
            score_val += 20 * imbalance
            raw_metrics["inst_flow_imbalance"] = round(imbalance, 3)
            if imbalance > 0:
                reasons.append("institutional bullish lean")
            else:
                reasons.append("institutional bearish lean")
        else:
            score_val += 20 if institutional_net_delta > 0 else -20
            if institutional_net_delta > 0:
                reasons.append("institutional bullish lean")
            else:
                reasons.append("institutional bearish lean")
        raw_metrics["inst_net"] = round(float(institutional_net_delta), 2)
        flow_signal = True
        signals_present += 1
    if institutional_package_premium is not None and institutional_package_premium >= INST_FLOW_MIN_NET:
        reasons.append("package-risk: multi-leg premium left out of the lean")
        raw_metrics["inst_package"] = round(float(institutional_package_premium), 2)

    # ── Component 2: squeeze tag (none / fuel; no Z ladder, no points — #256) ──
    # A field present makes the component present with score 0 (redesign.md R5 Coverage), so a quiet short book
    # lowers no score and lifts none.
    squeeze_signal = False
    of_base = " of shares outstanding" if si_basis == "outstanding" else ""
    if short_interest_pct_float is not None:
        raw_metrics["si_pct"] = round(float(short_interest_pct_float), 2)
    if borrow_fee is not None:
        raw_metrics["borrow_fee"] = round(float(borrow_fee), 2)
    if days_to_cover is not None:
        # Shown, never part of the tag: the days-to-cover figure rests on the same twice-monthly FINRA count.
        raw_metrics["days_to_cover"] = round(float(days_to_cover), 2)
    if short_interest_pct_float is not None or borrow_fee is not None:
        squeeze_signal = True
        signals_present += 1
        si_fuel = short_interest_pct_float is not None and short_interest_pct_float >= R5_FUEL_SI_PCT
        fee_fuel = borrow_fee is not None and borrow_fee >= R5_FUEL_FEE_PCT
        raw_metrics["squeeze_tag"] = "fuel" if (si_fuel or fee_fuel) else "none"
        if si_fuel or fee_fuel:
            parts = []
            if si_fuel:
                parts.append(f"short interest {short_interest_pct_float:.1f}%{of_base}")
            if fee_fuel:
                parts.append(f"borrow fee {borrow_fee:.1f}%")
            reasons.append("squeeze fuel: " + " and ".join(parts))
        else:
            shown = (f"short interest {short_interest_pct_float:.1f}%{of_base}"
                     if short_interest_pct_float is not None else f"borrow fee {borrow_fee:.1f}%")
            reasons.append(f"squeeze none ({shown})")

    if squeeze_signal and short_as_of and short_interest_pct_float is not None:
        # Only a reason that shows the short interest carries the settlement day; a fee-only read is IBKR's own,
        # of today, and must not borrow FINRA's date.
        raw_metrics["si_as_of"] = short_as_of
        for i in range(len(reasons) - 1, -1, -1):
            if "short interest" in reasons[i]:
                # day and month only: the age limit is 35 days, so the year is never in doubt, and the short form
                # does not wrap mid-date in the drawer's narrow reason column
                settled = date.fromisoformat(short_as_of[:10])
                reasons[i] += f" · FINRA settled {settled.day} {settled:%b}"
                break

    available = signals_present > 0
    if not available:
        return RuleResult(
            score=None,
            available=False,
            coverage=0,
            reasons=reasons + ["no positioning signal available"],
            raw_metrics=raw_metrics,
        )

    score_val = max(SCORE_RANGE[0], min(SCORE_RANGE[1], score_val))
    coverage = min(signals_present / signal_slots, 1.0)

    return RuleResult(
        score=round(score_val, 1),
        available=available,
        coverage=coverage,
        reasons=reasons if reasons else ["neutral positioning"],
        raw_metrics=raw_metrics,
    )
