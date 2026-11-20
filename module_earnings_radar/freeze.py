"""Earnings Radar board -> forecast ledger rows (#580, the rule of #128).

``freeze_cards`` is the last step of an Earnings Fetch (``app/runners.run_earnings_range``): it applies the shared
freeze rule (``core.ledger.freeze_board``) to the cards just rendered and appends them to ``forecast_ledger``, so the
board's calls can be scored later the way the screeners' are (#25). The mapping lives here, in the module, not in
``core/``.

Two rules are this board's own, because its cards are forward-looking:

- **Only a report still to come is a forecast.** A card whose earnings date is on or before the freeze session D is a
  report the market has already heard, so it is left out and the rest keep the board's order (``picks``). A Fetch of
  past days therefore freezes nothing, and the note says there were no usable picks.
- **No per-card bar check.** Swing and Fundamentals refuse the whole day when one shown name lacks its complete D bar,
  because every one of their scores is read from that bar. An Earnings Radar card is scored from the option chain, the
  flow and the estimates; one halted name must not refuse the board. SPY's own complete D bar in D01 still anchors the
  day (``core.ledger.spy_anchor_problem``), so ``forecast_date`` is a session the prices store has closed.

``market_cap`` and ``shown_price`` come from the card's two numeric fields (``market_cap_value``, ``shown_price``),
never from the rendered "$1.2B" / "$12.34" strings, which are rounded for the screen.
"""
from __future__ import annotations

from datetime import date, datetime

from RevenueChaser.core import ledger
from RevenueChaser.core.config import (
    FLOW_SWEEP_BLOCK_MIN, INST_FLOW_MIN_NET, MAX_DEEP_CHECKS_PER_DAY, MAX_EXPECTED_MOVE_PCT,
    MIN_DOLLAR_OPTION_VOLUME, MIN_EXPECTED_MOVE_PCT, MIN_OPTION_VOLUME, MIN_TOTAL_OI, RULE_WEIGHTS,
    DIRECTION_RANGE, VOLATILITY_EDGE_RANGE, WATCHLIST_BYPASS,
)
from RevenueChaser.module_earnings_radar import composite

SOURCE = "earnings_radar"
LABEL = "Earnings Radar"

# The gates in ``core/config.py`` that decide which calendar name is scored at all, and how deep the day goes.
_HASHED_GATES = {
    "MIN_OPTION_VOLUME": MIN_OPTION_VOLUME, "MIN_TOTAL_OI": MIN_TOTAL_OI,
    "MIN_DOLLAR_OPTION_VOLUME": MIN_DOLLAR_OPTION_VOLUME,
    "MIN_EXPECTED_MOVE_PCT": MIN_EXPECTED_MOVE_PCT, "MAX_EXPECTED_MOVE_PCT": MAX_EXPECTED_MOVE_PCT,
    "WATCHLIST_BYPASS": WATCHLIST_BYPASS, "MAX_DEEP_CHECKS_PER_DAY": MAX_DEEP_CHECKS_PER_DAY,
    "FLOW_SWEEP_BLOCK_MIN": FLOW_SWEEP_BLOCK_MIN, "INST_FLOW_MIN_NET": INST_FLOW_MIN_NET,
}


def effective_config() -> dict:
    """What the board scores with: the rule weights, the two score ranges, the filter gates and the call cuts."""
    return {
        "RULE_WEIGHTS": dict(RULE_WEIGHTS),
        "DIRECTION_RANGE": list(DIRECTION_RANGE),
        "VOLATILITY_EDGE_RANGE": list(VOLATILITY_EDGE_RANGE),
        "GATES": dict(_HASHED_GATES),
        "CUTS": dict(composite.SCORING_CUTS),
    }


def model_version() -> str:
    return ledger.model_version(composite.SELECTION_VERSION, effective_config())


def bucket(card) -> str:
    """The ledger bucket: the call and its conviction, e.g. ``OPTIONS_BULL|HIGH`` or ``WATCH|LOW``.

    The action carries the direction, so a scorer can tell a long call from a short one without the card.
    """
    return f"{getattr(card, 'final_action', '') or ''}|{getattr(card, 'conviction', '') or ''}"


def board_score(card) -> float:
    """The number the board ranks by (``pipeline.run``: confidence plus the preselect score)."""
    return round(float(getattr(card, "confidence_score", 0) or 0) + float(getattr(card, "pre_score", 0) or 0), 1)


def _report_date(card) -> date | None:
    value = getattr(card, "earnings_date", None)
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def picks(cards: list, session: date) -> list[dict]:
    """The shown cards whose report is still to come, as ledger picks, in board order.

    ``rank`` is the 1-based position among the frozen cards: a card left out does not leave a hole in the ranks.
    A card with no readable earnings date is left out too — without one there is nothing to say the report is ahead.
    """
    rows = []
    for card in cards:
        day = _report_date(card)
        if day is None or day <= session:
            continue
        rows.append({
            "subject": getattr(card, "ticker", ""),
            "rank": len(rows) + 1,
            "score": board_score(card),
            "bucket": bucket(card),
            "market_cap": getattr(card, "market_cap_value", None),
            "sector": getattr(card, "sector", "") or None,
            "shown_price": getattr(card, "shown_price", None),
            "stop": None,
            "target": None,
        })
    return rows


def freeze_cards(cards: list, *, run_id: str | None = None, now=None) -> ledger.Outcome:
    """Freeze a finished Earnings Fetch's cards when the rule allows it; the outcome is also a job note.

    Never raises for a refused freeze: the runner calls this after the board file is written.
    """
    payload = {"cards": list(cards or ())}
    return ledger.freeze_board(
        SOURCE, LABEL, payload, rows_key="cards", to_rows=lambda items: picks(items, _session(now)),
        model_version=model_version(), run_id=run_id, now=now, check_spy=False,
        anchor=ledger.spy_anchor_problem)


def _session(now) -> date:
    """The session ``freeze_board`` is about to freeze under. ``to_rows`` is called only after its gate passed, so
    the gate has already answered; asking it again is the one way to hand the session to the mapping."""
    session, _why = ledger.session_gate(now)
    return session or date.min
