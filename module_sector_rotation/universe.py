"""Universe for the RRG rotation engine.

- The map's symbols — 108 symbols at the seed: 97 ETFs run through the SPY-relative rotation engine (A1: each against
  its own history; quadrants, money flow) plus 11 macro indicators (yield curve + volatility/commodities) that are
  named in ``core/rotation_reference.py`` and shown in the macro table, not on the map (B1). ``MACRO_SERIES`` holds
  their ``market_series`` rows and two more macro-table-only series (the HY and IG credit spreads).

The ETFs are avo's ``map`` watch list since plan v5 step 7b: every reader calls
``core.rotation_reference.rotation_etfs()`` at run time. ``MACRO_SERIES`` is reference data, not a board's own, so
it lives in ``core/rotation_reference.py`` (since #12) and is re-exported here (a test that rebinds
``store.MACRO_SERIES`` keeps working).
"""
from RevenueChaser.core.rotation_reference import MACRO_SERIES  # noqa: F401

# Country flag emoji per single-country ETF (rendered on the RRG map + table).
COUNTRY_FLAGS = {
    "EWZ": "🇧🇷", "EWY": "🇰🇷", "FXI": "🇨🇳", "INDA": "🇮🇳", "EWT": "🇹🇼",
    "EWC": "🇨🇦", "EWA": "🇦🇺", "EWJ": "🇯🇵", "EWU": "🇬🇧", "MCHI": "🇨🇳",
    "EWG": "🇩🇪", "EWW": "🇲🇽", "VNM": "🇻🇳", "EWS": "🇸🇬", "EIDO": "🇮🇩",
    "ECH": "🇨🇱", "EWP": "🇪🇸", "KSA": "🇸🇦", "EWM": "🇲🇾", "EPOL": "🇵🇱",
    "THD": "🇹🇭", "EEMV": "🌐", "EZA": "🇿🇦", "TUR": "🇹🇷", "ARGT": "🇦🇷",
    "EPHE": "🇵🇭", "IDX": "🇮🇩", "EPU": "🇵🇪",
}

GROUP_COLORS = {
    "sector": "#58a6ff",
    "theme": "#d2991d",
    "style": "#db61a2",
    "industry": "#3fb9a0",
    "bond": "#f85149",
    "region": "#a371f7",
    "yield": "#22d3ee",
    "commodity": "#34d399",
}

QUADRANT_COLORS = {
    "LEADING": "#3fb950",
    "WEAKENING": "#d2991d",
    "LAGGING": "#f85149",
    "IMPROVING": "#58a6ff",
}
