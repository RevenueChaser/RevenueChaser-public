"""E5a (#372): the Earnings Fetch reads the ``earnings_calendar`` rows the nightly D26 sweep stored and calls UW
only for the (day, session) pairs the store does not cover.

Offline: a fake client that counts its calls, a temp store seeded with the stored rows. The stored event must be
byte-identical to the live one built from the same UW row (the live read is the reference), because the run
downstream (screener, scoring) cannot tell which path a row came from except by its ``source``.
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


def _row(item, day=DAY, session="premarket", session_date=SESSION):
    return {"session_date": session_date, "earnings_date": day, "ticker": item["symbol"],
            "report_session": session, "item": item, "marketcap": 1_500_000_000, "source": "uw"}


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












def test_weekends_are_skipped_without_a_read():
    fake = _UW({(DAY, "premarket"): [_item("AAA")]})

    events, _ = runners._fetch_calendar_days(fake, [SATURDAY, DAY])

    assert SATURDAY not in [d for d, _ in fake.calls]
    assert fake.calls == [(DAY, "premarket"), (DAY, "afterhours")]
    assert [e["earnings_date"] for e in events] == [DAY]






