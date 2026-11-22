"""The card says what a held whole build is waiting for (#1336, draft P-A of the data audit of 21 Nov 2026).

A change to the shared build code holds every hourly pass of ``prices/serving`` at once, and the live file stood
from 20 Nov 14:05 UTC until someone pressed Fetch on 21 Nov. The status was already ``late`` and then ``stale``
from the sessions missed, but the only sign of **why** was a ``skipped`` note inside the card, so the reason now
names the action. Nothing here changes what the builder does: the pass is still held, as #446 step 8 decided.
"""
from __future__ import annotations

from datetime import datetime, timezone

from RevenueChaser.module_settings import newdata
from RevenueChaser.rcdata.build.base import WholeBuildByHand

# 23:00 New York on Wednesday 28 Oct 2026: the latest complete session is that day.
NOW = datetime(2026, 10, 29, 3, 0, tzinfo=timezone.utc)
HELD = {"result": "skipped", "checked_on": "2026-10-28",
        "note": f"skipped: a whole prices build {WholeBuildByHand.MARK} (prices/serving): the shared build code "
                f"changed since the live prices file was built; press Fetch on the Settings board"}


def _status(last: dict, as_of: str) -> tuple[str, str]:
    built = {"result": "changed", "source_as_of": as_of, "checked_on": as_of, "coverage": 1.0}
    status, reason, _ = newdata.status_of("prices/serving", last, built, "daily", NOW)
    return status, reason


def test_a_pass_held_for_a_person_says_so_once_a_session_has_passed():
    assert _status(HELD, "2026-10-27") == ("late", f"one session missed; {newdata.HELD_BUILD_REASON}")
    assert _status(HELD, "2026-10-26") == ("stale", f"two or more sessions missed; {newdata.HELD_BUILD_REASON}")
    assert "press Fetch" in newdata.HELD_BUILD_REASON
    # Within its cycle nothing is waiting: the file is current and the pass had nothing to do.
    assert _status(HELD, "2026-10-28") == ("fresh", "within its cycle; the last run changed rows")


def test_a_skip_for_any_other_reason_leaves_the_reason_as_it_was():
    paused = {"result": "skipped", "checked_on": "2026-10-28", "note": "skipped: paused by settings at x"}
    assert _status(paused, "2026-10-27") == ("late", "one session missed")
    assert _status({"result": "changed", "checked_on": "2026-10-28"}, "2026-10-26") == (
        "stale", "two or more sessions missed")
    assert not newdata._held_build(None) and not newdata._held_build({"result": "skipped"})
