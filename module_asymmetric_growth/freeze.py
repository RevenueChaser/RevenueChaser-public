"""Asymmetric Growth board -> forecast ledger rows (#128).

``freeze_result`` is the last step of an AG Fetch (``app/runners.run_asymmetric_growth``): it applies the
shared freeze rule (``core.ledger.freeze_board``) to the scan just made and appends every shown card to
``forecast_ledger``. The mapping lives here, in the module, not in ``core/``.

AG's momentum is read from the prices store's daily bars up to the scan's session (#380 S4, PR 11), so the session is
complete for the board when the served prices file holds that session's complete SPY bar (``core.ledger.
d01_has_session``, which reads the served ``price_bars_daily`` view, the same test Swing and Fundamentals use) AND the
scan itself read up to that session (``data_as_of``, review F4): a prices build that lands during a Fetch must not
freeze cards scored on the session before under the new one. Not ``ohlc_gaps``: one gap in one name must not refuse
the board. AG also has no fixture / no-data flag, so it brings its own guards: no cards, and too many scoring errors.
"""
from __future__ import annotations

from revenuechaser.core import ledger
from revenuechaser.module_asymmetric_growth import engine

SOURCE = "asymmetric_growth"
LABEL = "AG"


def effective_config() -> dict:
    """What the board scores with: the default thresholds, the default market-cap range and the C18 rules."""
    return {"THRESHOLDS": engine.THRESHOLDS, "DEFAULT_MC_RANGE": list(engine.DEFAULT_MC_RANGE),
            "RULES": dict(engine.RULES)}


def model_version() -> str:
    return ledger.model_version(engine.SELECTION_VERSION, effective_config())


def bucket(card: dict) -> str:
    """The ledger bucket: tier and points bucket, e.g. ``tier:3|pts_9`` or ``tier:none|pts_lt5`` (#380 S2)."""
    tier = card.get("tier")
    return f"tier:{tier if tier in (2, 3) else 'none'}|{engine._points_bucket(card['total_points'])}"


def picks(cards: list[dict]) -> list[dict]:
    """The board's shown cards as ledger picks. ``rank`` is the 1-based position on the board."""
    return [{
        "subject": c["ticker"],
        "rank": position,
        "score": c.get("total_points"),
        "bucket": bucket(c),
        "market_cap": c.get("market_cap"),
        "sector": c.get("sector"),
        "shown_price": c.get("price"),
        "stop": None,
        "target": None,
    } for position, c in enumerate(cards, start=1)]


def _score_error_problem(result: dict) -> str | None:
    summary = result.get("summary") or {}
    attempted = int(result.get("universe_total") or 0) - int(summary.get("excluded_types") or 0)
    if attempted <= 0:
        return "no ticker was attempted"
    errors = int(summary.get("score_errors") or 0)
    if errors > engine.FREEZE_MAX_SCORE_ERROR_RATE * attempted:
        return (f"{errors:,} of {attempted:,} tickers failed to score (scoring errors above "
                f"{engine.FREEZE_MAX_SCORE_ERROR_RATE:.0%})")
    return None


def _make_anchor(result: dict):
    """The freeze anchor (#380 S4, decision 4): SPY's complete bar for the session in the served prices file, and the
    scan's own prices session (``result["data_as_of"]``) equal to it (review F4)."""
    def anchor(session) -> str | None:
        if not ledger.d01_has_session(session, "SPY"):
            return f"no complete SPY bar for the {session} session in the prices store yet (the nightly prices build)"
        scanned = str(result.get("data_as_of") or "")[:10]
        if scanned != session.isoformat():
            return (f"the scan read prices up to {scanned or 'no session'}, not the {session} session "
                    "(a prices build landed during the Fetch, or the scan found no bars)")
        return None
    return anchor


def freeze_result(result: dict, *, run_id: str | None = None, now=None) -> ledger.Outcome:
    """Freeze a finished AG scan when the rule allows it; the outcome is also a job note."""
    return ledger.freeze_board(
        SOURCE, LABEL, result, rows_key="cards", to_rows=picks, model_version=model_version(),
        run_id=run_id, now=now, check_spy=False, payload_check=_score_error_problem,
        anchor=_make_anchor(result))
