"""Next week's earnings of the watch-list names (#886, mock approved by avo 20 Nov 2026: "Olur").

avo's four answers: a third calendar tab, the Alpha Vantage calendar the builder already serves as the source of
the days, the News watch lists as the source of the names, and one pass a week, Sunday 09:00 Amsterdam.

The days come from a real ``fundamentals`` serving file built here the way the builder builds one; the watch
lists are read through ``read.job_list``, which this board's tests stand in for, as ``test_board_wiring`` does.
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from RevenueChaser.core import automations, rawstore
from RevenueChaser.module_news import calendar as cal, earnings, report
from RevenueChaser.rcdata import read, serving
from RevenueChaser.rcdata.build.fundamentals import tables

NOW = datetime(2026, 11, 20, 13, 48, tzinfo=cal.AMS).timestamp()      # Fri 20 Nov 13:48 Amsterdam
SUNDAY = datetime(2026, 11, 22, 9, 0, tzinfo=cal.AMS).timestamp()     # the weekly pass's own hour
NEXT_MONDAY, NEXT_FRIDAY = date(2026, 11, 23), date(2026, 11, 27)

COMPANIES = [("ZM", "0000001", "Zoom Communications"), ("ADI", "0000002", "Analog Devices"),
             ("DE", "0000003", "Deere & Company"), ("NVDA", "0000004", "NVIDIA Corporation")]


def _serve(events: list[dict], companies=COMPANIES) -> None:
    """A ``fundamentals`` serving file with ``fundamental_company`` and ``earnings_event``, the dataset's own
    schema, every column a row leaves out written NULL."""
    def _table(builder, name, schema, rows):
        cols = ", ".join(f'"{c}" {t}' for c, t in schema)
        names = [c for c, _ in schema]
        builder.con.execute(f"CREATE TABLE {name} ({cols})")
        full = [{**{c: None for c in names}, **r} for r in rows]
        if full:
            builder.con.executemany(f"INSERT INTO {name} VALUES ({', '.join('?' * len(names))})",
                                    [[r[c] for c in names] for r in full])
        return len(full)

    with serving.build("fundamentals") as b:
        n_c = _table(b, "fundamental_company", tables.COMPANY,
                     [{"ticker": t, "cik": c, "name": n} for t, c, n in companies])
        n_e = _table(b, "earnings_event", tables.EARNINGS_EVENT,
                     [{"confirmed": False, "source": "alphavantage", **e} for e in events])
        b.swap({"fundamental_company": n_c, "earnings_event": n_e})


@pytest.fixture
def lists(monkeypatch):
    """avo's own list holds ZM and ADI, the stock list DE; NVDA is on no list."""
    monkeypatch.setattr(read, "job_list", lambda feeds: {"": ["ZM", "ADI"], "stock": ["DE"], "news": []}[feeds])


@pytest.fixture
def served():
    _serve([{"cik": "0000001", "ticker": "ZM", "report_date": date(2026, 11, 23), "report_time": "post-market"},
            {"cik": "0000002", "ticker": "ADI", "report_date": date(2026, 11, 24), "report_time": "pre-market"},
            {"cik": "0000003", "ticker": "DE", "report_date": date(2026, 11, 25), "report_time": None},
            {"cik": "0000004", "ticker": "NVDA", "report_date": date(2026, 11, 24), "report_time": "post-market"},
            {"cik": "0000001", "ticker": "ZM", "report_date": date(2026, 12, 7), "report_time": "post-market"}])


def test_next_week_is_the_week_after_this_one_and_a_sunday_pass_writes_tomorrow_s():
    assert earnings.week(NOW) == (NEXT_MONDAY, NEXT_FRIDAY)
    assert earnings.week(SUNDAY) == (NEXT_MONDAY, NEXT_FRIDAY), "Sunday belongs to the week it is leaving"


def test_the_pass_writes_one_row_a_watch_list_name_reporting_next_week(lists, served):
    out = earnings.build(now=NOW)
    assert out == {"week_start": "2026-11-23", "names": 3}
    got = {r["ticker"]: r for r in rawstore.query("SELECT * FROM news_earnings", db="news")}
    assert sorted(got) == ["ADI", "DE", "ZM"], "NVDA is on no watch list"
    assert got["ZM"]["company"] == "Zoom Communications" and got["ZM"]["report_time"] == "post-market"
    assert str(got["DE"]["report_date"])[:10] == "2026-11-25" and got["DE"]["report_time"] is None
    assert all(str(r["week_start"])[:10] == "2026-11-23" for r in got.values()), "a later report is another week"


def test_the_pass_drops_the_week_it_replaces(lists, served):
    rawstore.write_rows(earnings.TABLE, [{"week_start": "2026-11-16", "ticker": "OLD", "company": "Last week",
                                          "report_date": "2026-11-17", "report_time": None, "confirmed": False,
                                          "source": "alphavantage", "run_id": "t", "run_at": 1.0}])
    earnings.build(now=NOW)
    assert "OLD" not in {r["ticker"] for r in rawstore.query("SELECT * FROM news_earnings", db="news")}


def test_a_confirmed_report_beats_a_calendar_guess_for_the_same_name(lists):
    _serve([{"cik": "0000001", "ticker": "ZM", "report_date": date(2026, 11, 23), "report_time": "post-market",
             "confirmed": False, "source": "alphavantage"},
            {"cik": "0000001", "ticker": "ZM", "report_date": date(2026, 11, 24), "report_time": "pre-market",
             "confirmed": True, "source": "sec"}])
    earnings.build(now=NOW)
    row = rawstore.query("SELECT * FROM news_earnings", db="news")[0]
    assert str(row["report_date"])[:10] == "2026-11-24" and row["confirmed"] is True


def test_the_mark_is_the_page_s_last_refresh_line(lists, served):
    earnings.build(now=NOW)
    rows, at = earnings.stored(NOW)
    assert len(rows) == 3 and at == pytest.approx(NOW)


def test_a_table_holding_another_week_answers_no_rows(lists, served):
    earnings.build(now=NOW - 7 * 86400)                   # last week's pass, never run since
    rows, at = earnings.stored(NOW)
    assert rows == [] and at is not None, "the tab says the week is not built, it never shows last week"


def test_the_tab_lists_monday_to_friday_with_the_refresh_line(lists, served):
    earnings.build(now=NOW)
    page = report.render_html(now=NOW)
    assert '>Earnings <span class="n">3</span>' in page
    assert "Next week · 23–27 November" in page and "3 names from your watch lists" in page
    assert "Your watch lists only · refreshed every Sunday · last refresh Friday 20 November 13:48" in page
    for day in ("Monday 23 November", "Tuesday 24 November", "Wednesday 25 November", "Thursday 26 November",
                "Friday 27 November"):
        assert day in page
    assert "No watch-list name reports on this day." in page, "Thursday has none and says so"
    assert "NVDA" not in page, "a name on no watch list never reaches the tab"


def test_the_time_of_day_is_written_in_the_board_s_own_words(lists, served):
    earnings.build(now=NOW)
    page = report.render_html(now=NOW)
    assert '<span class="when bmo">Before open</span>' in page            # ADI, pre-market
    assert '<span class="when amc">After close</span>' in page            # ZM, post-market
    assert '<span class="when">Time not published</span>' in page         # DE, no time served


def test_an_empty_watch_list_and_an_empty_week_both_say_so(monkeypatch, served):
    monkeypatch.setattr(read, "job_list", lambda feeds: [])
    assert earnings.build(now=NOW) == {"week_start": "2026-11-23", "names": 0}
    page = report.render_html(now=NOW)
    assert "No watch-list name reports next week." in page
    assert "add a name on any board to see its report day here" in page


def test_the_weekly_pass_is_a_sunday_nine_o_clock_registry_row():
    entry = next(e for e in automations.REGISTRY if e.name == "RC-News-Earnings-Weekly")
    assert entry.days == ("Sunday",) and entry.time == "09:00"
    assert entry.tables_written == ("news_earnings",)
    assert entry.args == ("-m", "RevenueChaser.scripts.board_fetch", "news-earnings")
    assert entry.unit == "life-rc-fetch-news-earnings", "one unit a board_fetch route (scripts/tests)"
    assert "weekly Sunday 09:00 (local)" == entry.schedule


def test_the_weekly_pass_waits_for_no_trading_session():
    """It reads a calendar of days still to come and runs on a Sunday, so the nightly Fetches' SPY gate would
    only ever hold it back (#886)."""
    from RevenueChaser.scripts import board_fetch
    assert board_fetch.ROUTES["news-earnings"] == "news_earnings"
    assert "news-earnings" not in board_fetch.NEEDS_SESSION
    assert "earnings" in board_fetch.NEEDS_SESSION, "the Earnings Radar Fetch still waits for its session"
