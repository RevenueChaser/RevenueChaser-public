"""The served earnings calendar the Fetch reads (#273 board half).

``option_screener_daily`` carries the UW calendar's own expected move since #273's data half (the options builder's
G8 read, 18 Nov 2026), so ``stored_inputs.calendar_items`` can answer a (report day, report session) pair the Fetch
used to ask UW for. What it must never do: serve a stale session, a day outside the built session's window, or
today and the next trading day, whose expected move, estimate and report time UW still moves.

Offline: the reader's one store call is patched, as in ``test_er_options_o1``. The table itself is built and read in
``rcdata/tests/test_options_tables.py``.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from RevenueChaser.core import calendar
from RevenueChaser.module_earnings_radar import stored_inputs

# 2026-10-14 is a Wednesday. The builder's session is the 13th; the Fetch's day the 16th (Friday), which is past
# today and tomorrow, so it is the store's to answer.
SESSION = date(2026, 10, 13)
DAY = date(2026, 10, 16)
NOW = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)       # 17:00 New York
TODAY = date(2026, 10, 14)
TOMORROW = date(2026, 10, 15)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    monkeypatch.setattr(calendar, "_now", lambda: NOW)


def _row(ticker="AAA", *, day=DAY, session="premarket", session_date=SESSION, **over):
    row = {"session_date": session_date, "ticker": ticker, "report_date": day, "report_session": session,
           "sector": "Technology", "full_name": f"{ticker} Inc", "marketcap": 1_500_000_000.0,
           "expected_move_perc": 0.052, "street_mean_est": 1.25, "pre_earnings_close": 10.0,
           "post_earnings_close": 10.5, "report_time": "premarket"}
    row.update(over)
    return row


def _served(monkeypatch, rows):
    monkeypatch.setattr(stored_inputs.market_read, "option_screener", lambda *a, **k: list(rows))


def test_a_covered_pair_is_served_as_the_uw_calendar_item(monkeypatch):
    _served(monkeypatch, [_row()])

    items, session = stored_inputs.calendar_items([DAY])

    assert session == SESSION
    assert items[(DAY, "premarket")] == [{
        "symbol": "AAA", "sector": "Technology", "full_name": "AAA Inc", "marketcap": 1_500_000_000.0,
        "expected_move_perc": 0.052, "street_mean_est": 1.25, "pre_earnings_close": 10.0,
        "post_earnings_close": 10.5, "report_time": "premarket"}]
    assert items[(DAY, "afterhours")] == [], "a covered pair with no report is answered, not asked of UW"


def test_the_afterhours_pair_keeps_its_own_names(monkeypatch):
    _served(monkeypatch, [_row("AAA"), _row("BBB", session="afterhours")])

    items, _ = stored_inputs.calendar_items([DAY])

    assert [i["symbol"] for i in items[(DAY, "premarket")]] == ["AAA"]
    assert [i["symbol"] for i in items[(DAY, "afterhours")]] == ["BBB"]


@pytest.mark.parametrize("stored", ["pre-market", "PreMarket", "bmo"])
def test_uws_other_spellings_of_premarket_land_in_the_premarket_pair(monkeypatch, stored):
    _served(monkeypatch, [_row(session=stored)])

    items, _ = stored_inputs.calendar_items([DAY])

    assert [i["symbol"] for i in items[(DAY, "premarket")]] == ["AAA"]


def test_an_unreadable_report_session_is_left_to_uw(monkeypatch):
    _served(monkeypatch, [_row(session="sometime")])

    items, _ = stored_inputs.calendar_items([DAY])

    assert items == {(DAY, "premarket"): [], (DAY, "afterhours"): []}


def test_today_and_the_next_trading_day_are_never_served(monkeypatch):
    """UW moves the expected move, the estimate and the report time during the day for the names about to report."""
    _served(monkeypatch, [_row(day=TODAY), _row("BBB", day=TOMORROW)])

    items, session = stored_inputs.calendar_items([TODAY, TOMORROW])

    assert items == {} and session is None


def test_a_session_older_than_the_need_catalog_allows_serves_nothing(monkeypatch):
    """``options.screener``: one session (avo, 29 Oct 2026 — a calendar older than the last session is not read)."""
    # ``previous_trading_day`` answers the latest trading day **on or before** its argument, so the day
    # before SESSION is what makes a session one older.
    stale = calendar.previous_trading_day(SESSION - timedelta(days=1))
    _served(monkeypatch, [_row(session_date=stale, day=DAY)])

    assert stored_inputs.calendar_items([DAY]) == ({}, None)


def test_the_newest_session_is_the_one_read(monkeypatch):
    older = calendar.previous_trading_day(SESSION - timedelta(days=1))
    _served(monkeypatch, [_row("OLD", session_date=older), _row("NEW")])

    items, session = stored_inputs.calendar_items([DAY])

    assert session == SESSION
    assert [i["symbol"] for i in items[(DAY, "premarket")]] == ["NEW"], "a row of an older session was served"


def test_a_day_past_the_built_sessions_window_is_left_to_uw(monkeypatch):
    far = SESSION + timedelta(days=stored_inputs.calendar_days_ahead() + 1)
    _served(monkeypatch, [_row(day=far)])

    assert stored_inputs.calendar_items([far]) == ({}, None)


def test_the_window_comes_from_the_builder_not_a_second_copy():
    from RevenueChaser.rcdata.build.options.uw_screener import DAYS_AHEAD
    assert stored_inputs.calendar_days_ahead() == DAYS_AHEAD


def test_the_freshness_comes_from_the_need_catalog():
    from RevenueChaser.rcdata import needs
    assert stored_inputs.calendar_max_lag() == needs.catalog.NEEDS["options.screener"].max_lag


def test_a_weekend_is_never_asked_for(monkeypatch):
    _served(monkeypatch, [_row()])
    saturday = date(2026, 10, 17)

    items, _ = stored_inputs.calendar_items([saturday])

    assert items == {}


def test_a_store_error_is_nothing_stored(monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("no serving file")

    monkeypatch.setattr(stored_inputs.market_read, "option_screener", boom)

    assert stored_inputs.calendar_items([DAY]) == ({}, None)


def test_an_empty_table_is_nothing_stored(monkeypatch):
    _served(monkeypatch, [])

    assert stored_inputs.calendar_items([DAY]) == ({}, None)
