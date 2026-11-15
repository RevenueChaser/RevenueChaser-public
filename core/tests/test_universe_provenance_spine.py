"""The board header's universe line (``reporting_common.universe_provenance_html``) under the spine (build plan PR 6):
it names the spine, its sources and its last build, and keeps the old cache's "refreshed by" only for what that cache
still feeds (the market caps); on the old store the line is unchanged."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from RevenueChaser.core import rawstore, universe
from RevenueChaser.core.reporting_common import universe_provenance_html
from RevenueChaser.rcdata import ops, serving
from RevenueChaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401 - market roots per test
from RevenueChaser.rcdata.tests.test_spine_security import built, run_all  # noqa: F401 - the 10 names

WHEN = "2026-10-28T09:00:00+00:00"


@pytest.fixture
def spine(built):
    assert universe.universe_source() == "spine"


def _built_at() -> str:
    """The live spine's build time as the line shows it, read straight from the serving file."""
    with serving.open_read("spine") as con:
        built = con.execute(f"SELECT max(built_at) FROM {serving.VERSION_TABLE}").fetchone()[0]
    return datetime.fromtimestamp(built, timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


@pytest.mark.usefixtures("spine")
def test_the_build_time_is_the_spines_own_not_a_datasets_check():
    """Real-data check (28 Oct): ``spine/security`` reads "unchanged" when an earlier dataset of the kind already
    rebuilt the file, so its check says nothing about when the spine was built. A later check changes nothing.

    The check's day is a date no build can carry. It used to be 2026-10-30, which the line really did contain on
    30 Oct 2026 - the day the clock reached it - because the line carries the build's own day: the test failed on
    a date rather than on a change (CI run 40982614219, on a diff that does not touch this file).
    """
    later = "2099-01-01"
    before = universe_provenance_html(WHEN, "X")
    assert later not in before, "the sentinel day must be one the line can never carry"
    ops.record_check("spine/security", "unchanged", source_as_of="2026-10-28", checked_on=later)
    assert universe_provenance_html(WHEN, "X") == before and later not in before


@pytest.mark.usefixtures("spine")
def test_the_board_name_is_escaped():
    assert "<img" not in universe_provenance_html(WHEN, "<img src=x>")


