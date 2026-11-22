"""The watchlist augmentation reads the served screener set, not UW live (#1138).

``augment_calendar`` was the Earnings Fetch's last live UW calendar call: one ``screener_batch`` for the watchlist
names the session calendar omits (unknown report time, estimated date). ``option_screener_daily`` carries every field
that call was made for, so the store answers the names it covers and UW is asked only for the rest.

Offline: the reader's one store call is patched, as in ``test_stored_calendar_273``; the UW client is a fake that
records what it was asked.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from revenuechaser.core import calendar
from revenuechaser.module_earnings_radar import stored_inputs, watchlist_augment

# 2026-10-14 is a Wednesday. The builder's session is the 13th; the reports are the 16th (Friday), past today and
# tomorrow, so they are the store's to answer.
SESSION = date(2026, 10, 13)
DAY = date(2026, 10, 16)
NOW = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)       # 17:00 New York
TODAY = date(2026, 10, 14)
TOMORROW = date(2026, 10, 15)
START, END = date(2026, 10, 14), date(2026, 10, 21)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(calendar, "_now", lambda: NOW)


class FakeUW:
    """A UW client that records every ``screener_batch`` it is asked for."""

    def __init__(self, rows: dict | None = None, boom: bool = False):
        self.rows, self.boom, self.asked = rows or {}, boom, []

    def screener_batch(self, tickers, date=None):
        self.asked.append(list(tickers))
        if self.boom:
            raise RuntimeError("UW said no")
        return {t: self.rows[t] for t in tickers if t in self.rows}


def _row(ticker="AAA", *, next_day=DAY, session_date=SESSION, **over):
    row = {"session_date": session_date, "ticker": ticker, "next_earnings_date": next_day,
           "er_time": "premarket", "sector": "Technology", "full_name": f"{ticker} Inc",
           "marketcap": 1_500_000_000.0, "implied_move_perc": 0.052}
    row.update(over)
    return row


def _live(ticker="AAA", *, next_day=DAY, **over):
    row = {"next_earnings_date": next_day.isoformat(), "er_time": "postmarket", "sector": "Energy",
           "full_name": f"{ticker} Corp", "marketcap": 2.0e9, "implied_move_perc": 0.071}
    row.update(over)
    return row


def _served(monkeypatch, rows):
    monkeypatch.setattr(stored_inputs.market_read, "option_screener", lambda *a, **k: list(rows))


# ── the stored reader ────────────────────────────────────────────────────────

def test_a_covered_name_is_served_as_the_screener_answer(monkeypatch):
    _served(monkeypatch, [_row()])
    assert stored_inputs.screener_rows(["aaa"]) == {"AAA": {
        "next_earnings_date": "2026-10-16", "er_time": "premarket", "sector": "Technology",
        "full_name": "AAA Inc", "marketcap": 1_500_000_000.0, "implied_move_perc": 0.052}}


def test_a_name_the_set_does_not_hold_is_not_covered(monkeypatch):
    _served(monkeypatch, [_row("AAA")])
    assert stored_inputs.screener_rows(["BBB"]) == {}


def test_a_row_without_a_next_earnings_date_is_not_covered(monkeypatch):
    """Without a date the store cannot say when the name reports, so the live call must still be made."""
    _served(monkeypatch, [_row(next_day=None)])
    assert stored_inputs.screener_rows(["AAA"]) == {}


@pytest.mark.parametrize("day", [TODAY, TOMORROW])
def test_a_name_reporting_today_or_the_next_trading_day_stays_live(monkeypatch, day):
    """UW moves the report time and the implied move of a name about to report, as for the calendar pairs."""
    _served(monkeypatch, [_row(next_day=day)])
    assert stored_inputs.screener_rows(["AAA"]) == {}


def test_a_stale_set_covers_nothing(monkeypatch):
    _served(monkeypatch, [_row(session_date=SESSION - timedelta(days=30))])
    assert stored_inputs.screener_rows(["AAA"]) == {}


def test_only_the_newest_built_session_is_read(monkeypatch):
    _served(monkeypatch, [_row("AAA", session_date=SESSION - timedelta(days=1)), _row("BBB")])
    assert set(stored_inputs.screener_rows(["AAA", "BBB"])) == {"BBB"}


def test_an_empty_or_unreadable_table_covers_nothing(monkeypatch):
    _served(monkeypatch, [])
    assert stored_inputs.screener_rows(["AAA"]) == {}
    monkeypatch.setattr(stored_inputs.market_read, "option_screener", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert stored_inputs.screener_rows(["AAA"]) == {}


def test_no_names_reads_nothing(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("the store must not be read for an empty name list")
    monkeypatch.setattr(stored_inputs.market_read, "option_screener", boom)
    assert stored_inputs.screener_rows([]) == {}


# ── the augmentation ─────────────────────────────────────────────────────────

def test_a_fully_covered_watchlist_makes_no_uw_call(monkeypatch):
    """The point of #1138: the Earnings Fetch's last live UW calendar call is gone."""
    _served(monkeypatch, [_row("AAA"), _row("BBB")])
    uw, events, raw_cal = FakeUW(), [], {}

    counts = watchlist_augment.augment_calendar(uw, events, raw_cal, {"AAA", "BBB"}, START, END)

    assert uw.asked == []
    assert counts == {"stored": 2, "live": 0}
    assert sorted(e["ticker"] for e in events) == ["AAA", "BBB"]
    assert events[0]["earnings_date"] == DAY and events[0]["earnings_time"] == "BMO"
    assert events[0]["expected_move_perc"] == 0.052 and events[0]["source"] == "screener"
    assert raw_cal["AAA"] is events[0]


def test_uw_is_asked_only_for_the_names_the_store_does_not_cover(monkeypatch):
    _served(monkeypatch, [_row("AAA")])
    uw, events, raw_cal = FakeUW({"BBB": _live("BBB")}), [], {}

    counts = watchlist_augment.augment_calendar(uw, events, raw_cal, {"AAA", "BBB"}, START, END)

    assert uw.asked == [["BBB"]]
    assert counts == {"stored": 1, "live": 1}
    assert sorted(e["ticker"] for e in events) == ["AAA", "BBB"]
    assert raw_cal["BBB"]["earnings_time"] == "AMC"             # the live row's own er_time


def test_a_name_already_on_the_calendar_is_neither_read_nor_asked(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("nothing is missing, so nothing is read")
    monkeypatch.setattr(stored_inputs.market_read, "option_screener", boom)
    uw = FakeUW()
    assert watchlist_augment.augment_calendar(uw, [], {"AAA": {"ticker": "AAA"}}, {"AAA"}, START, END) == \
        {"stored": 0, "live": 0}
    assert uw.asked == []


def test_a_store_error_leaves_every_name_to_uw(monkeypatch):
    monkeypatch.setattr(stored_inputs, "screener_rows", lambda *a, **k: (_ for _ in ()).throw(OSError("no file")))
    uw, events, raw_cal = FakeUW({"AAA": _live("AAA")}), [], {}

    counts = watchlist_augment.augment_calendar(uw, events, raw_cal, {"AAA"}, START, END)

    assert uw.asked == [["AAA"]] and counts == {"stored": 0, "live": 1}
    assert [e["ticker"] for e in events] == ["AAA"]


def test_a_failed_uw_call_keeps_the_names_the_store_answered(monkeypatch):
    _served(monkeypatch, [_row("AAA")])
    uw, events, raw_cal = FakeUW(boom=True), [], {}

    counts = watchlist_augment.augment_calendar(uw, events, raw_cal, {"AAA", "BBB"}, START, END)

    assert counts == {"stored": 1, "live": 1}
    assert [e["ticker"] for e in events] == ["AAA"], "the run goes on without the extras UW owed"


def test_a_report_outside_the_span_is_not_added(monkeypatch):
    _served(monkeypatch, [_row("AAA", next_day=date(2026, 11, 20))])
    events, raw_cal = [], {}
    assert watchlist_augment.augment_calendar(FakeUW(), events, raw_cal, {"AAA"}, START, END) == \
        {"stored": 1, "live": 0}
    assert events == [] and raw_cal == {}


def test_the_day_list_narrows_what_the_store_added(monkeypatch):
    """``days`` is the discrete day list of a dashboard Fetch: a stored name reporting on another day comes off."""
    _served(monkeypatch, [_row("AAA", next_day=DAY), _row("BBB", next_day=date(2026, 10, 19))])
    events, raw_cal = [], {}

    watchlist_augment.augment_calendar(FakeUW(), events, raw_cal, {"AAA", "BBB"}, START, END, days=[DAY])

    assert [e["ticker"] for e in events] == ["AAA"] and set(raw_cal) == {"AAA"}
