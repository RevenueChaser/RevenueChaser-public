"""Implied Probability (OIPD) board configuration.

Per-ticker board: fetch one Unusual Whales option chain, fit an SVI volatility
smile per expiry, and transform the fitted surface into a risk-neutral price
distribution. All knobs live here so the fit is testable rather than magic.
"""
from __future__ import annotations

from revenuechaser.core.config import OUTPUT_DIR

# Regenerable artifacts (flat html + namespaced json), written via runners.
OIPD_LATEST = OUTPUT_DIR / "oipd_latest.html"
OIPD_JSON = OUTPUT_DIR / "oipd" / "oipd_latest.json"

# ── Defaults ────────────────────────────────────────────────────────────────
DEFAULT_TICKER = "SPY"
# The rate the discounting uses is the stored FRED 10-year Treasury yield of the chain's session
# (``macro.dgs10``, through ``core/risk_free.stored_dgs10``; avo's decision of 10 Nov 2026, #644). The constant below
# is only the fallback when no yield is held inside the window, and the board says when it stands on it.
RISK_FREE_RATE = 0.04
# How many calendar days before the chain's session a DGS10 observation may be and still count (FRED publishes the
# yield one business day late, so the session's own observation is often not held yet).
RISK_FREE_MAX_AGE_DAYS = 14

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
# A fitted 5-95 % band wider than this multiple of what ATM IV alone implies is flagged (a runaway wing).
TAIL_FLAG_RATIO = 2.0
# g(k) must fall below -G_FLAG_TOL to flag "negative density": the board shows g-min to 3 decimals.
G_FLAG_TOL = 5e-4
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
SELECTION_VERSION = "oipd-2"
# What the fit's rate IS, hashed instead of the day's value: the rate now moves with the stored yield, and a model
# version that moved with it would change on every FRED observation.
RISK_FREE_SOURCE = f"macro.dgs10<={RISK_FREE_MAX_AGE_DAYS}d-else-{RISK_FREE_RATE}"


def fit_config() -> dict:
    """Every knob that changes a fitted distribution, hashed into the model version."""
    return {"min_dte": MIN_DTE, "max_dte": MAX_DTE, "max_expiries": MAX_EXPIRIES, "min_contracts": MIN_CONTRACTS,
            "g_floor": G_FLOOR, "penalty_weight": PENALTY_WEIGHT, "risk_free": RISK_FREE_SOURCE,
            "max_rel_spread": MAX_REL_SPREAD, "grid": GRID, "clip_flag_pct": CLIP_FLAG_PCT,
            "tail_flag_ratio": TAIL_FLAG_RATIO, "g_flag_tol": G_FLAG_TOL,
            "inputs": "otm-two-sided-no-vendor-iv", "expiries": "oi-top", "roots": "largest"}


def model_version() -> str:
    from revenuechaser.core.ledger import model_version as _mv
    return _mv(SELECTION_VERSION, fit_config())
