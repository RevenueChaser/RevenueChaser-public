"""A dataset whose provider stops answering is not due for ever after (#1432, UW migration lane E).

avo's Unusual Whales plan ends 6 December 2026, and ``uw/institutions`` is the only ownership dataset that reads
it. Its rows are already ours -- the 13F type slices read the newest ``uw_institution`` snapshot of our own
ownership file -- so the dataset must simply stop being asked for, instead of failing on every pass and reading
"stale" on the Settings board for ever. No provider call: every test stops at ``is_due`` or ``status_of``.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from revenuechaser.core import calendar
from revenuechaser.rcdata import ops
from revenuechaser.rcdata.build import DATASETS, due
from revenuechaser.module_settings import newdata

pytestmark = pytest.mark.usefixtures("kinds_full")

NAME = "uw/institutions"
#: 12:00 New York on the last day UW answers, and on the day after the plan ends.
LAST_DAY = datetime(2026, 12, 4, 17, 0, tzinfo=timezone.utc)
AFTER_END = datetime(2026, 12, 7, 17, 0, tzinfo=timezone.utc)


@pytest.fixture
def clock(monkeypatch):
    def set_to(when: datetime) -> None:
        monkeypatch.setattr(calendar, "_now", lambda: when)
    set_to(LAST_DAY)
    return set_to


def test_the_plans_end_is_the_datasets_end(clock):
    assert due.SOURCE_ENDS[NAME] == date(2026, 12, 6)


def _built_then_failed() -> None:
    """The real shape after the plan lapses: the dataset has built before (so it is past ``starts_by_hand``) and
    its newest check is the failure the dead endpoint gives."""
    ops.record_check(NAME, "changed", source_as_of="2026-09-05", checked_on="2026-09-05")
    ops.record_check(NAME, "failed", checked_on="2026-12-04")


def test_a_failed_check_makes_it_due_again_while_the_plan_runs(clock):
    _built_then_failed()
    assert due.is_due(DATASETS[NAME]) == (True, "the last check failed")


def test_past_the_plans_end_it_is_never_due_again(clock):
    _built_then_failed()
    clock(AFTER_END)
    due_now, why = due.is_due(DATASETS[NAME])
    assert due_now is False
    assert "2026-12-06" in why and "stand" in why


def test_past_the_plans_end_the_settings_row_is_not_stale(clock):
    failed = {"result": "failed", "checked_on": "2026-12-04"}
    changed = {"result": "changed", "checked_on": "2026-12-04", "source_as_of": "2026-12-04"}
    assert newdata.status_of(NAME, failed, changed, "quarterly", LAST_DAY)[0] == "stale"
    status, reason, _ = newdata.status_of(NAME, failed, changed, "quarterly", AFTER_END)
    assert status == "unchanged"
    assert "2026-12-06" in reason
