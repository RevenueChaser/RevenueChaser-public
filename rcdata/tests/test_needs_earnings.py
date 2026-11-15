"""``earnings.next`` (step B): the first need a board really uses, and the end of the short-circuit.

Until this step ``core.earnings_dates`` returned the options layer's calendar **instead of** the stored D26 one
(``_layer_next_dates`` returned early), so a name the layer does not cover lost the date the D26 sweep had for it.
The need is one ordered union: the layer first, the stored calendar for the names it does not name, and Yahoo's own
value for whatever neither holds.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from RevenueChaser.core import earnings_dates
from RevenueChaser.rcdata import needs

TODAY = date(2026, 10, 27)
SOON = date(2026, 10, 30)
LATER = date(2026, 11, 5)


@pytest.fixture(autouse=True)
def reference_session(monkeypatch):
    """The day freshness is measured against (the review's I1): one shared function, not the caller's ``today``.
    These cases are written around ``TODAY``, so ``TODAY`` is the newest complete session here."""
    monkeypatch.setattr(needs.serve.calendar, "latest_complete_session", lambda: TODAY)


@pytest.fixture
def layer(monkeypatch):
    """The options layer's screener rows, as ``rcdata.read.option_screener`` returns them."""
    def set_rows(rows):
        monkeypatch.setattr(needs.catalog.read, "option_screener", lambda **kw: list(rows))
    return set_rows




def _screener(ticker, report_date, session=TODAY):
    return {"ticker": ticker, "report_date": report_date, "session_date": session,
            "source": "uw/option_screener", "source_as_of": session, "fetched_at": 1.0, "run_id": "r1"}


def test_the_catalog_holds_the_need():
    need = needs.catalog.NEEDS["earnings.next"]
    assert need.reader_name == "option_screener" and need.dataset == "uw/option_screener"
    assert need.fallbacks == ("d26_calendar",) and need.key_column == "ticker"


















