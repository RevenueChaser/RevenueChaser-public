"""Fundamentals board -> forecast ledger rows (#128).

``freeze_payload`` is the last step of a Fundamentals Fetch (``app/runners.run_fundamentals``): it
applies the shared freeze rule (``core.ledger.freeze_board``) to the board just built and appends the
shown candidates to ``forecast_ledger``. The mapping lives here, in the module, not in ``core/``.
"""
from __future__ import annotations

from revenuechaser.core import fiscal_year, ledger
from revenuechaser.module_fundamentals import config
from revenuechaser.module_fundamentals import debt as _debt

SOURCE = "fundamentals"
LABEL = "Fundamentals"

# The thresholds the board scores with; ``model_version`` hashes exactly these. A saved setting (PR 2: the two
# prefilter floors and the type filter, ``module_fundamentals/settings.py``) replaces its config value or, for the
# type filter, joins the hash only when overridden, so the default leaves today's model version as it was.
_HASHED = (
    "MIN_PRICE", "MIN_DOLLAR_VOLUME",
    "RO40_MIN", "GROWTH_MIN", "ROIC_MIN", "ROIC_IC_MIN_SHARE", "GM_MIN", "ND_EBITDA_MAX",
    "DIST_52W_MAX", "RS_6M_MIN", "DISTORTED_GROWTH", "DISTORTED_REV_MIN", "TAX_RATE",
    "EXCLUDED_SECTORS", "RO40_BARRIER",     # #386 F1 data-health gates
)
# Fundamentals review 17 Nov N7: thresholds that live outside config.py but move a score (the debt inference, the
# debt note's date window, the stale-annual cut). ``ABOVE_200D`` left the hash: no rule reads it.
_HASHED_ELSEWHERE = ((_debt, "INTEREST_FLOOR_USD"), (_debt, "NOTE_DAYS"), (fiscal_year, "STALE_DAYS"))


def effective_config() -> dict:
    from revenuechaser.module_fundamentals import settings as fund_settings
    return {**{name: getattr(config, name) for name in _HASHED},
            **{name: getattr(mod, name) for mod, name in _HASHED_ELSEWHERE},
            **fund_settings.stored_overrides()}


def model_version() -> str:
    return ledger.model_version(config.SELECTION_VERSION, effective_config())


def picks(candidates: list[dict]) -> list[dict]:
    """The board's shown candidates as ledger picks. ``rank`` is the 1-based position on the board."""
    return [{
        "subject": c["ticker"],
        "rank": position,
        "score": c.get("ro40"),
        "bucket": c.get("bucket"),     # #386 F2: the rules passed ("rule_of_40+quality+momentum"), not a 1-3 count
        "market_cap": c.get("market_cap"),
        "sector": c.get("sector"),
        "shown_price": c.get("price"),
        "stop": None,
        "target": None,
    } for position, c in enumerate(candidates, start=1)]


def freeze_payload(payload: dict, *, run_id: str | None = None, now=None) -> ledger.Outcome:
    """Freeze a finished Fundamentals payload when the rule allows it; the outcome is also a job note.

    The board's prices come from the prices store (D01), so the anchor and the per-candidate check are the same as
    Swing's: SPY and each frozen name must end on one complete session D.
    """
    return ledger.freeze_board(
        SOURCE, LABEL, payload, rows_key="candidates", to_rows=picks, model_version=model_version(),
        run_id=run_id, now=now, anchor=ledger.spy_anchor_problem,
        bar_gaps=ledger.ohlc_gaps)
