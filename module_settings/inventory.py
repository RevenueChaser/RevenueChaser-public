"""The Settings payload's store-only parts — zero network, no store file opened here.

The dataset inventory that lived here read the old ``raw``, ``edgar``, ``history`` and ``prices`` files; it went
with them (#860). What is left is what the page still draws besides the control board: the Ticker lookup's names
(from the spine), the board input cards, the automations, and the IBKR login state.
"""
from __future__ import annotations

import os
from datetime import datetime, timezone

from revenuechaser.core import automations, ibkr_login
from revenuechaser.module_settings import boards

DASH = "—"
BOARD = "module_settings"


def _ibkr_login_url() -> str:
    """``RC_IBKR_LOGIN_URL``: where the IBKR gateway's login screen is reachable, or "" when unset.

    Read per payload build rather than at import, so setting the variable needs no restart, and kept out of the code
    so no host is pinned here. The page validates it before linking to it (``report._ibkr_login_href``).
    """
    return os.getenv("RC_IBKR_LOGIN_URL", "").strip()


def _universe_tickers() -> tuple[list[dict], str | None]:
    """``([{ticker, name}], error)`` for the ticker combobox, from the spine through ``rcdata.read`` (#485)."""
    from revenuechaser.rcdata import read as rcread
    try:
        rows = rcread.universe()
    except Exception as exc:  # noqa: BLE001 - said on the page in the box's place, never an empty box
        return [], f"{type(exc).__name__}: {exc}"[:300]
    return [{"ticker": r["ticker"], "name": r.get("name") or r["ticker"]}
            for r in rows if r.get("ticker")], None


def collect(now: datetime | None = None) -> dict:
    """The Settings payload. ``now`` is the clock of the IBKR card (tests pin it)."""
    now = now or datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    errors: list[dict] = []
    try:
        ibkr = ibkr_login.collect(now=now)
    except Exception as exc:  # noqa: BLE001 - the card is left out and the failure listed, never a blank page
        ibkr = None
        errors.append({"table": "ibkr", "where": "ibkr_login.collect", "error": f"{type(exc).__name__}: {exc}"[:300]})
    tickers, tickers_error = _universe_tickers()
    return {
        "rows": [],
        "tickers": tickers,
        "tickers_error": tickers_error,
        "boards": boards.board_cards(),
        # One row per LLM job and its writer pair (#404).
        "llm_writers": boards.llm_writers_card(),
        # Fixed registry fields only: the live state is polled from /api/automations.
        "automations": automations.static_rows(),
        "ibkr_login_state": ibkr,
        "ibkr_login_url": _ibkr_login_url(),
        "errors": errors,
        "generated_at": now.isoformat(timespec="seconds"),
    }
