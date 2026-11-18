"""Implied Probability (OIPD) board configuration.

Per-ticker board: fetch one Unusual Whales option chain, fit an SVI volatility
smile per expiry, and transform the fitted surface into a risk-neutral price
distribution. All knobs live here so the fit is testable rather than magic.
"""
from __future__ import annotations

from RevenueChaser.core.config import OUTPUT_DIR

# Regenerable artifacts (flat html + namespaced json), written via runners.
OIPD_LATEST = OUTPUT_DIR / "oipd_latest.html"
OIPD_JSON = OUTPUT_DIR / "oipd" / "oipd_latest.json"

# ── Defaults ────────────────────────────────────────────────────────────────
DEFAULT_TICKER = "SPY"
# Risk-free proxy carried from the Financials DCF (10y US Treasury stand-in).
RISK_FREE_RATE = 0.04

# ── Expiry selection ────────────────────────────────────────────────────────
MIN_DTE = 1          # 0DTE is excluded: intraday time value breaks the T model
MAX_DTE = 365        # one-year horizon (matches the OIPD demo's "12m")
MAX_EXPIRIES = 12    # cap the fit cost; the highest-OI expiries win
MIN_CONTRACTS = 6    # an expiry needs at least this many usable strikes to fit

# ── UW chain paging ─────────────────────────────────────────────────────────
PAGE_LIMIT = 500     # the endpoint caps at 500 rows/page
MAX_PAGES = 6        # 3000 contracts is far more than one expiry ever returns

# ── SVI fit ─────────────────────────────────────────────────────────────────
# Butterfly-arbitrage guard: penalise g(k) below this floor during the fit.
G_FLOOR = 0.0
# The board greys its statistics when the density window clips more than this share (percent of mass).
CLIP_FLAG_PCT = 0.01
PENALTY_WEIGHT = 25.0

# ── Fit inputs (review N3/N4, avo's D1, 18 Nov 2026) ───────────────────────────
# A quote wider than this share of its mid stays out of the fit. The measured median relative spread on the stored
# chains is 0.06 to 0.17 per name (live check L2, 18 Nov 2026), so the cap drops only the wide wings.
MAX_REL_SPREAD = 0.5

# ── Density grid (review N13) ───────────────────────────────────────────────
# The log-moneyness grid ProbCurve integrates on: half-width = clamp(SD_MULT * sd, MIN_HALF_WIDTH, HALF_CAP).
GRID = {"min_half_width": 2.5, "sd_mult": 8.0, "half_cap": 6.0, "grid_n": 801}

# ── Model version ───────────────────────────────────────────────────────────
# Bump by hand when a fit knob changes; the golden test in tests/test_fit_inputs.py fails until it is.
SELECTION_VERSION = "oipd-1"


def fit_config() -> dict:
    """Every knob that changes a fitted distribution, hashed into the model version."""
    return {"min_dte": MIN_DTE, "max_dte": MAX_DTE, "max_expiries": MAX_EXPIRIES, "min_contracts": MIN_CONTRACTS,
            "g_floor": G_FLOOR, "penalty_weight": PENALTY_WEIGHT, "risk_free": RISK_FREE_RATE,
            "max_rel_spread": MAX_REL_SPREAD, "grid": GRID, "clip_flag_pct": CLIP_FLAG_PCT,
            "inputs": "otm-two-sided-no-vendor-iv", "expiries": "oi-top", "roots": "largest"}


def model_version() -> str:
    from RevenueChaser.core.ledger import model_version as _mv
    return _mv(SELECTION_VERSION, fit_config())
