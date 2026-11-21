"""#881: the freeze's session check reads the asked session's own bar, not the ticker's newest one.

On 15 Nov 2026 a Fundamentals Fetch refused with "SPY has no complete 2026-11-13 bar in the prices store"
while that bar was in the store (close 754.37, measured read-only on 21 Nov 2026). The reason is the shape of
the read: ``d01_last_bars`` groups by ticker and takes ``max(session_date)``, so a question about a past
session is answered with a later session's bar and can only ever be False once a newer bar exists. Offline;
the store is a temp DuckDB.
"""
from __future__ import annotations

from datetime import date

from RevenueChaser.core import calendar as cal
from RevenueChaser.core import ledger
from RevenueChaser.core.tests.d01_seed import seed_d01

PAST = date(2026, 10, 2)        # a Friday and a normal session
NEWER = date(2026, 10, 5)       # the Monday after it


def _built_after(day=NEWER):
    """The served view's build stamp: one time for the whole file, after ``day``'s close + 30 min."""
    return cal.session_close(day).timestamp() + 40 * 60


def test_a_past_session_with_its_own_bar_is_complete(rawstore_tmp_db):
    """The bug: SPY has PAST's bar and a newer one, and the anchor still refused the day."""
    seed_d01("SPY", ["2026-10-01", PAST, NEWER], _built_after())
    assert ledger.d01_has_session(PAST, "SPY") is True
    assert ledger.spy_anchor_problem(PAST) is None


def test_a_past_session_without_its_own_bar_is_not_complete(rawstore_tmp_db):
    """A later bar never stands in for the asked session: PAST is a gap when only its neighbours are there."""
    seed_d01("SPY", ["2026-10-01", NEWER], _built_after())
    assert ledger.d01_has_session(PAST, "SPY") is False
    assert ledger.spy_anchor_problem(PAST) == f"SPY has no complete {PAST} bar in the prices store"


def test_the_picks_of_a_past_session_are_not_gaps(rawstore_tmp_db):
    """``ohlc_gaps`` reads the same way, so a pick with PAST's bar does not refuse the board either."""
    seed_d01("SPY", ["2026-10-01", PAST, NEWER], _built_after())
    seed_d01("AAA", ["2026-10-01", PAST, NEWER], _built_after())
    seed_d01("BBB", ["2026-10-01", NEWER], _built_after())
    assert ledger.ohlc_gaps(PAST, ["AAA"]) == {}
    assert ledger.ohlc_complete(PAST, ["AAA", "BBB"]) == {"AAA"}


def test_the_newest_session_still_answers_as_before(rawstore_tmp_db):
    """The ordinary case, unchanged: the asked session is the newest bar in the store."""
    seed_d01("SPY", ["2026-10-01", PAST], cal.session_close(PAST).timestamp() + 40 * 60)
    assert ledger.d01_has_session(PAST, "SPY") is True
    assert ledger.d01_has_session(NEWER, "SPY") is False
