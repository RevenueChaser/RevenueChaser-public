"""The cards' next earnings date and the earnings-week filter read UW's calendar from ``options.duckdb``
(``option_screener_daily``, G8) first and the stored D26 calendar for the names the layer does not hold, Yahoo last.

Since the internal data API (step B) the two are a **union**, not a choice, and the age window is counted in trading
sessions (the ``earnings.next`` need's ``max_lag``) rather than calendar days, so the layer's freshness is
measured the way the rest of the store's is. avo set that number to **one session** on 29 Oct 2026, which settles
the contradiction the boards carried (four calendar days here, one session in ``stored_inputs``) in favour of the
stricter one: a calendar older than the last session is not read at all.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from revenuechaser.core import earnings_dates as ed

TODAY = date(2026, 10, 22)


@pytest.fixture(autouse=True)
def reference_session(monkeypatch):
    """Pin the day freshness is measured against.

    Since the review's I1 the layer's age is counted against the market's newest complete session, the one day the
    envelope and the boards share, instead of against the caller's ``today``: on a trading day whose session is not
    over those two differ by one, and a card would say fresh while the filter had already dropped the layer. These
    cases are written against ``TODAY``, so ``TODAY`` is the newest complete session here.
    """
    from revenuechaser.rcdata import needs
    monkeypatch.setattr(needs.serve.calendar, "latest_complete_session", lambda: TODAY)


def _screener(rows):
    return lambda session_date=None, passing_only=False: [dict(r) for r in rows]


def _raw_none(*a, **k):
    """The stored D26 calendar holding nothing, so a test about the layer reads only the layer."""
    return []




# 22 Oct 2026 is a Thursday, so 21 Oct is one session back and 20 Oct two. The window is the need's, read from the
# catalog rather than restated, so this file cannot drift from it.
MAX_AGE_SESSIONS = 1
AT_THE_EDGE = date(2026, 10, 21)
PAST_THE_EDGE = date(2026, 10, 20)


def test_the_age_window_is_the_needs_own(monkeypatch):
    from revenuechaser.rcdata import needs
    need = needs.catalog.NEEDS["earnings.next"]
    assert need.max_lag == MAX_AGE_SESSIONS and need.max_lag_unit == "sessions"
    assert needs.lag_sessions(AT_THE_EDGE, TODAY) == MAX_AGE_SESSIONS
    assert needs.lag_sessions(PAST_THE_EDGE, TODAY) == MAX_AGE_SESSIONS + 1












# The real path (the file built from the UW mock at the HTTP boundary) is in
# ``rcdata/tests/test_options_read.py``, where the ``http_mock`` fixture lives.
