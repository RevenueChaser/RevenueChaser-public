"""E5a (#372), back on the new serving layer (#273 board half): the Earnings Fetch reads the served calendar and
calls UW only for the (day, session) pairs the store does not cover.

The rows come from ``option_screener_daily`` now, not the nightly D26 sweep of the old raw.duckdb (#860). The
stored event must be byte-identical to the live one built from the same UW row (the live read is the reference),
because the run downstream (screener, scoring) cannot tell which path a row came from except by its ``source``.

Offline: a fake client that counts its calls, and the board's one reader patched (the reader's own cases are
``module_earnings_radar/tests/test_stored_calendar_273.py``).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from RevenueChaser.app import runners
from RevenueChaser.core import calendar, rawstore

SESSION = date(2026, 10, 13)          # Tuesday, the night the D26 sweep ran
DAY = date(2026, 10, 16)              # Friday, the day the Fetch reads the calendar for (past the live days)
SATURDAY = date(2026, 10, 17)
NOW = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)      # 17:00 New York: the D14 session is complete


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(calendar, "_now", lambda: NOW)


@pytest.fixture(autouse=True)
def _store(rawstore_tmp_db):
    return rawstore_tmp_db


def _item(ticker, **over):
    item = {"symbol": ticker, "sector": "Technology", "full_name": f"{ticker} Inc", "marketcap": 1_500_000_000,
            "expected_move_perc": 0.052, "street_mean_est": 1.25, "pre_earnings_close": 10.0,
            "post_earnings_close": 10.5, "report_time": "premarket"}
    item.update(over)
    return item


@pytest.fixture
def stored(monkeypatch):
    """``stored({(day, session): [item, ...]})``: what the board's reader answers for this test."""
    from RevenueChaser.module_earnings_radar import stored_inputs

    def make(pairs: dict, session=SESSION):
        monkeypatch.setattr(stored_inputs, "calendar_items", lambda days, today=None: (dict(pairs), session))

    return make


class _UW:
    """Records every ``calendar_day_raw`` call; serves one canned row per (day, session)."""

    def __init__(self, rows=None):
        self.rows = rows or {}
        self.calls = []

    def calendar_day_raw(self, d, session):
        self.calls.append((d, session))
        return list(self.rows.get((d, session), []))


def _live_events(uw, days):
    """The events the live path builds: the reference for the stored path."""
    out = []
    for d in days:
        if d.weekday() >= 5:
            continue
        for session in ("premarket", "afterhours"):
            for item in uw.calendar_day_raw(d, session):
                ev = runners._calendar_event(item, d, session)
                if ev is not None:
                    out.append(ev)
    return out


def _key(ev):
    return (str(ev["earnings_date"]), ev["earnings_time"], ev["ticker"])












def test_a_served_pair_is_not_asked_of_uw(stored):
    stored({(DAY, "premarket"): [_item("AAA")], (DAY, "afterhours"): []})
    fake = _UW()

    events, raw_cal = runners._fetch_calendar_days(fake, [DAY])

    assert fake.calls == [], "the Fetch asked UW for a pair the store answered"
    assert [e["ticker"] for e in events] == ["AAA"] and set(raw_cal) == {"AAA"}


def test_a_pair_the_store_does_not_cover_is_still_asked_of_uw(stored):
    stored({(DAY, "premarket"): [_item("AAA")]})      # no afterhours entry: that pair is UW's
    fake = _UW({(DAY, "afterhours"): [_item("BBB")]})

    events, _ = runners._fetch_calendar_days(fake, [DAY])

    assert fake.calls == [(DAY, "afterhours")]
    assert sorted(e["ticker"] for e in events) == ["AAA", "BBB"]


def test_a_served_event_is_the_live_event_built_from_the_same_row(stored):
    item = _item("AAA")
    reference = _live_events(_UW({(DAY, "premarket"): [item]}), [DAY])
    stored({(DAY, "premarket"): [item], (DAY, "afterhours"): []})

    events, _ = runners._fetch_calendar_days(_UW(), [DAY])

    assert events == reference
    assert [_key(e) for e in events] == [_key(e) for e in reference]
    assert {e["source"] for e in events} == {"UW"}, "the run downstream must not be able to tell the paths apart"


def test_premarket_still_wins_in_raw_cal_when_both_pairs_are_served(stored):
    stored({(DAY, "premarket"): [_item("AAA", full_name="AAA premarket")],
            (DAY, "afterhours"): [_item("AAA", full_name="AAA afterhours")]})

    _, raw_cal = runners._fetch_calendar_days(_UW(), [DAY])

    assert raw_cal["AAA"]["full_name"] == "AAA premarket"


def test_the_run_records_which_pairs_came_from_the_store(stored):
    stored({(DAY, "premarket"): [_item("AAA")]})
    fake = _UW({(DAY, "afterhours"): []})

    runners._fetch_calendar_days(fake, [DAY])

    assert runners._CALENDAR_SOURCES == {"stored": 1, "live": 1, "session": SESSION.isoformat()}


def test_nothing_served_names_no_session_and_counts_every_pair_live(stored):
    stored({}, session=None)
    fake = _UW({(DAY, "premarket"): [_item("AAA")]})

    runners._fetch_calendar_days(fake, [DAY])

    assert fake.calls == [(DAY, "premarket"), (DAY, "afterhours")]
    assert runners._CALENDAR_SOURCES == {"stored": 0, "live": 2, "session": None}


def test_a_failing_reader_does_not_fail_the_fetch(monkeypatch):
    from RevenueChaser.module_earnings_radar import stored_inputs

    def boom(days, today=None):
        raise RuntimeError("serving file locked")

    monkeypatch.setattr(stored_inputs, "calendar_items", boom)
    fake = _UW({(DAY, "premarket"): [_item("AAA")]})

    events, _ = runners._fetch_calendar_days(fake, [DAY])

    assert [e["ticker"] for e in events] == ["AAA"]
    assert fake.calls == [(DAY, "premarket"), (DAY, "afterhours")]


def test_weekends_are_skipped_without_a_read():
    """No store is seeded here, so every pair is UW's: the reader answers nothing from an empty temp store."""
    fake = _UW({(DAY, "premarket"): [_item("AAA")]})

    events, _ = runners._fetch_calendar_days(fake, [SATURDAY, DAY])

    assert SATURDAY not in [d for d, _ in fake.calls]
    assert fake.calls == [(DAY, "premarket"), (DAY, "afterhours")]
    assert [e["earnings_date"] for e in events] == [DAY]






