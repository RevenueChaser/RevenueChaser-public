"""The two freshness labels the data audit of 21 Nov 2026 found wrong (#1338, report sections 10 and 12).

A card's freshness is the dataset's, so it has to name the dataset that actually writes the served rows, and it
has to be counted in the unit the source publishes in. Both were off: the two tables derived from the daily bars
named Alpaca, the tester that is compared and never served, and FINRA's short interest and the SEC's
fails-to-deliver were counted in sessions although each publishes twice a month, so a run that correctly found
nothing new read ``stale``.
"""
from __future__ import annotations

from datetime import datetime, timezone

from revenuechaser.module_settings import newdata
from revenuechaser.rcdata import read
from revenuechaser.rcdata.needs import catalog, screen

# 23:00 New York on Wednesday 28 Oct 2026: the latest complete session is that day.
NOW = datetime(2026, 10, 29, 3, 0, tzinfo=timezone.utc)


def _status(dataset: str, as_of: str, result: str = "unchanged") -> tuple[str, str]:
    check = {"result": result, "source_as_of": as_of, "checked_on": "2026-10-28", "coverage": 1.0}
    status, reason, _ = newdata.status_of(dataset, check, check, "daily", NOW)
    return status, reason


def test_the_two_tables_derived_from_the_bars_name_the_source_that_serves_them():
    """``security_symbol`` and ``market_cap_daily`` are built from ``price_bar_daily``, so they follow its source."""
    served = read.DATASET_OF_TABLE["price_bar_daily"]
    assert served == "wrds/prices"
    assert read.DATASET_OF_TABLE["security_symbol"] == served
    assert read.DATASET_OF_TABLE["market_cap_daily"] == served


def test_only_the_twice_monthly_releases_are_judged_by_a_publication_window():
    assert screen.lag_needs() == {"finra/short_interest": "ownership.short_interest", "sec/ftd": "ownership.ftd"}
    for dataset, need in screen.lag_needs().items():
        assert need in catalog.NEEDS, f"{dataset}: {need} is not a need"
        assert newdata.LAG_NEED[dataset] == need, "the screen owns the map; newdata reads it"


def test_a_twice_monthly_source_that_has_not_published_is_within_its_cycle():
    """27 calendar days for FINRA (max_lag 35) and 6 sessions for the SEC's file (max_lag 10): neither is late."""
    assert catalog.NEEDS["ownership.short_interest"].max_lag == 35
    assert catalog.NEEDS["ownership.ftd"].max_lag == 10
    assert _status("finra/short_interest", "2026-10-01")[0] == "unchanged"
    assert _status("sec/ftd", "2026-10-20")[0] == "unchanged"
    assert _status("finra/short_interest", "2026-10-01", result="changed")[0] == "fresh"


def test_a_window_that_passes_is_late_and_twice_the_window_is_stale():
    """The alarm stays: a job that stops fetching still goes late and then stale, in the need's own unit."""
    status, reason = _status("finra/short_interest", "2026-09-15")      # 43 days, over the 35 the need allows
    assert status == "late" and "publication window" in reason
    assert _status("finra/short_interest", "2026-08-01")[0] == "stale"  # 88 days, over twice the window
    assert _status("sec/ftd", "2026-10-02")[0] == "late"                # 18 sessions, over the 10 the need allows
