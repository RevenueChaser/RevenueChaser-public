"""#146 (U4 / D6): a partial Yahoo pull never deletes the universe, and two writers never interleave.

- A pull is *full* only when every market-cap chunk ran to its reported total AND the screener quoted at least 90%
  of the stored names that carry a quote (D6). A full pull replaces the table; anything else upserts, flags the pull
  partial (``__fetch__`` provenance row), re-applies the identity master and skips Phase B.
- Membership is the SEC list (#264): the fixture serves one, by default every stored name plus every quoted name, so
  only the tests that say otherwise see a name leave the list.
- ``universe_write_lock`` serialises fetch + write + identity apply + provenance (and Phase B). It is re-entrant
  per thread and gives up at once (no network, no write) when another run holds it.
"""
from __future__ import annotations

import os

import pytest

from revenuechaser.core import job_lock, rawstore
from revenuechaser.rcdata.tests import spine_fixture

SECTOR = "Technology"


def _quote(sym, cap=1e9, **extra):
    q = {"symbol": sym, "quoteType": "EQUITY", "exchange": "NMS", "currency": "USD", "marketCap": cap,
         "regularMarketPrice": 10.0, "shortName": f"{sym} Corp", "sector": SECTOR}
    q.update(extra)
    return q














# ── U4 / D6: full vs partial ──────────────────────────────────────────────────























# ── the SEC member list and the quotes (#264) ─────────────────────────────────













# ── the first load ────────────────────────────────────────────────────────────





# ── what the upsert keeps, and what runs after it ─────────────────────────────















# ── the lock ──────────────────────────────────────────────────────────────────

















# ── the visible flag ──────────────────────────────────────────────────────────

def test_the_provenance_line_says_partial_fetch_and_escapes_the_board_name():
    from revenuechaser.core.reporting_common import universe_provenance_html
    plain = universe_provenance_html("2026-10-03T00:00:00+00:00", "Swing Potential")
    flagged = universe_provenance_html("2026-10-03T00:00:00+00:00", "Swing Potential", partial=True)
    assert "partial fetch" not in plain and "partial fetch" in flagged
    hostile = universe_provenance_html("2026-10-03T00:00:00+00:00", "<img src=x>", partial=True)
    assert "<img src=x>" not in hostile






