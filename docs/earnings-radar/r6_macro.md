# R6 — Macro (veto only)

**Weight:** 0% of composite direction score (never votes bull/bear)
**Sources:** FRED `DGS10` daily + ticker OHLC already fetched for the card
**File:** `module_earnings_radar/rules/rule6_macro.py`

## What It Does

Blocks the trade when the name is **extremely rate-sensitive**. A veto sets
`final_action = NO_TRADE` and the `MACRO VETO` badge. The numeric score is
audit-only (same pattern as R4's vol-edge).

## Live input — 10Y yield beta

Once per earnings `run()`, FRED `DGS10` is fetched daily (not weekly). Each
ticker's already-fetched ~60d OHLC is paired on calendar date. OLS beta of
stock simple returns vs Δ yield, with FRED percent converted to **decimal**,
so β ≈ equity duration (−10 ≈ 10% price drop per 1pp yield rise).

| |β| | Effect |
|:---:|--------|
| > 26 | **veto** `extreme rate sensitivity` (`R6_RATE_VETO`) |
| > 22 | reason only — does not block (`R6_RATE_HIGH`) |
| else | measured, no penalty |

The two cuts are calibrated to the scale of this beta, not chosen (#635, 20 Nov 2026). The only stored run on
disk (`earnings_radar_latest.html`, 10 Nov 2026, 35 cards, 33 with a printed beta) measures
min 2.5 · p25 6.4 · **median 14.1** · p75 22.0 · p90 26.7 · max 47.4. The previous pair, 2.0 / 4.0, came from
another scale and marked **100%** and **82%** of that day's names, which separated nothing and is how one day
went from 0 to 8 `NO_TRADE`. `R6_RATE_HIGH` is now that p75 (the upper quartile) and `R6_RATE_VETO` the p90
(the top decile, ~3 names of 33 before the overlap and t-stat gates). The beta itself is unchanged: it is a
real quantity — duration — and the card prints it.

One run is the whole distribution, because the per-card history went with #860, so this is a calibration to
re-take once several runs' cards are stored again (#1250).

The `> 22` step also subtracts 15 from R6's score, but **R6's weight in the composite is 0**, so that −15
reaches no card: above `R6_RATE_HIGH` and below `R6_RATE_VETO` the effect is the reason line alone.

The veto also needs a real beta: `|t| < 2` on the beta, or no t statistic at all, is "noisy" and the
extreme reading stays a badge (`noisy_beta`, `beta_tstat` on the card; owner, 10 Nov 2026, #635).

Needs ≥ 20 paired returns and nonzero yield variance. Otherwise R6 is
`unavailable` (`score=None`, never a 0 fill).

No FRED key / failed fetch → empty series → R6 unavailable; the earnings run
continues. There is no yfinance `^TNX` fallback (`^TNX` is yield×10).

A duration above 4 is common (software, REITs, utilities) — 82% of the one
measured run — which is why the veto now sits at the measured top decile
instead.

## Not wired

FX tailwind / FX exposure, regulatory / geopolitical text, consensus crowding.
Optional kwargs still exist for a later pass; `regulatory_risk="low"` is not a
signal. Pipeline passes **only** `rate_sensitivity` (the 10Y beta).

## Coverage

1.0 when the yield-beta slot is present, else 0. Not divided by empty FX/reg slots.
