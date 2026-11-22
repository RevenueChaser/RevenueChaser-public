"""PR 12: the fundamentals layer on Settings' "New data system" section: a card per dataset with its cadence, the
four WRDS ones no longer attended since #1361, and the WRDS difference slot filled by the newest monthly
difference report of a WRDS check dataset (decided 27 Oct)."""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from revenuechaser.core import calendar
from revenuechaser.module_settings import newdata, report
from revenuechaser.rcdata import ops
from revenuechaser.rcdata.tests.conftest import market_roots  # noqa: F401 - market roots per test

NOW = datetime(2026, 10, 28, 3, 0, tzinfo=timezone.utc)
FUNDAMENTALS = {"sec/companyfacts": "daily", "sec/filings": "daily", "alphavantage/earnings_calendar": "weekly",
                "yfinance/estimates": "weekly", "sec/fsds": "monthly",
                "wrds/fundq": "monthly", "wrds/funda": "monthly",
                "wrds/segments": "monthly", "wrds/exrt": "monthly", "wrds/audit": "monthly",
                "fundamentals/tables": "daily"}
WRDS = ["wrds/fundq", "wrds/funda", "wrds/segments", "wrds/exrt", "wrds/audit"]


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    monkeypatch.setattr(calendar, "_now", lambda: NOW)


def _card(data: dict, dataset: str) -> dict:
    return next(c for c in data["datasets"] if c["dataset"] == dataset)


def test_a_card_per_fundamentals_dataset_with_its_cadence_and_a_label():
    data = newdata.collect(NOW)
    assert {d: _card(data, d)["cadence"] for d in FUNDAMENTALS} == FUNDAMENTALS
    assert all(not _card(data, d)["label"].startswith(d) for d in FUNDAMENTALS)
    # #1361: the WRDS datasets follow their cadence now, so no fundamentals card is attended.
    assert [d for d in FUNDAMENTALS if _card(data, d)["attended"]] == []


def test_no_fundamentals_card_shows_an_attended_command_now():
    # #1361: the command was shown only in the attended branch, which offered no Fetch or Backfill button. With
    # the flag gone these cards take the ordinary branch and get the buttons instead (see test_newdata_prices).
    data = newdata.collect(NOW)
    for dataset in ("wrds/fundq", "wrds/co_hgic", "sec/companyfacts"):
        assert _card(data, dataset)["attended_command"] is None
        assert _card(data, dataset)["attended"] is False


def test_editing_one_cards_wrds_slot_leaves_the_others():
    # The Opus review's N3: the "no WRDS run yet" slot was one module-level dict shared by every card.
    data = newdata.collect(NOW)
    _card(data, "wrds/funda")["wrds"]["text"] = "edited"
    assert _card(data, "sec/companyfacts")["wrds"] == {"text": "no WRDS run yet", "produced": False}
    assert newdata.NO_WRDS == {"text": "no WRDS run yet", "produced": False}
