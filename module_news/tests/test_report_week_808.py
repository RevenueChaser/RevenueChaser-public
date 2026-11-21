"""The News board's calendar view (#808, mock approved by avo 20 Nov 2026: "News olur").

The card is a week strip (Monday to Sunday, each day with its own count of economic releases and FDA catalysts)
over two tabs, Economic and FDA. The strip filters both lists to one day; the page is served on today, so it
stands without JavaScript. An FDA catalyst UW gives no day for is never snapped onto one: it carries its own
words and stands under "Later, no day yet".
"""
from __future__ import annotations

from datetime import date, datetime

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_news import calendar as cal, report

NOW = datetime(2026, 11, 20, 13, 48, tzinfo=cal.AMS).timestamp()      # Fri 20 Nov 13:48 Amsterdam
MONDAY, SUNDAY = date(2026, 11, 16), date(2026, 11, 22)


def _at(day, hh, mm=0):
    return datetime(2026, 11, day, hh, mm, tzinfo=cal.AMS).timestamp()


def _econ(ts, event, fc=None, prev=None):
    return {"event_ts": ts, "event": event, "type": "report", "importance": 2, "forecast": fc, "prev": prev,
            "reported_period": None, "first_seen": 1.0, "last_seen": 1.0, "retired_at": None, "run_id": "t",
            "run_at": NOW}


def _fda(day, event, indication, status, precision="day", text=None, outcome=None):
    return {"event_ts": cal.day_start(day), "event": event, "type": cal.FDA_TYPE, "importance": 3,
            "forecast": None, "prev": None, "reported_period": None, "first_seen": 1.0, "last_seen": 1.0,
            "retired_at": None, "run_id": "t", "run_at": NOW, "ticker": event.split()[0], "drug": None,
            "catalyst": None, "target_text": text or day.isoformat(), "target_precision": precision,
            "indication": indication, "status": status, "outcome": outcome, "url": None}


@pytest.fixture
def seeded():
    rawstore.write_rows("news_events", [
        _econ(_at(17, 14, 30), "Retail sales", fc="0.4%", prev="0.1%"),
        _econ(_at(20, 8, 0), "Building Permits, M/M%", fc="0.4%", prev="0.1%"),
        _econ(_at(20, 14, 30), "Initial Jobless Claims", fc="232K", prev="227K"),
        _fda(date(2026, 11, 20), "IOVA Lifileucel: PDUFA Date", "Advanced Melanoma", "NDA"),
        _fda(date(2026, 11, 17), "AMGN Olpasiran: Advisory Committee Meeting", "Lp(a) cardiovascular", "NDA"),
        _fda(date(2027, 4, 1), "MRNA mRNA-1283: FDA Decision", "COVID-19 vaccine", "BLA",
             precision="quarter", text="2027-Q2"),
    ])


def test_the_week_strip_is_monday_to_sunday_with_each_day_s_own_counts(seeded):
    page = report.render_html(now=NOW)
    assert report.week_days(NOW)[0] == MONDAY and report.week_days(NOW)[-1] == SUNDAY
    assert 'class="wk"' in page
    for day in report.week_days(NOW):
        assert f'data-day="{day.isoformat()}"' in page, f"{day} has no button on the strip"
    assert 'data-day="2026-11-20" onclick="newsDay(this)" aria-pressed="true"' in page, "today is the pressed day"
    assert 'aria-label="Tuesday 17 November: 1 releases, 1 FDA catalysts"' in page
    assert 'aria-label="Wednesday 18 November: 0 releases, 0 FDA catalysts"' in page


def test_the_page_is_served_on_today_and_the_other_days_wait_hidden(seeded):
    """Without JavaScript the board is today's; the strip only unhides a day that is already on the page."""
    page = report.render_html(now=NOW)
    assert 'data-day="2026-11-20"><span class="t">08:00' in page, "today's release is not hidden"
    assert 'data-day="2026-11-17" hidden>' in page, "another day's release is served hidden"
    assert "Retail sales" in page and "Initial Jobless Claims" in page


def test_economic_and_fda_are_two_tabs_counted_for_the_pressed_day(seeded):
    page = report.render_html(now=NOW)
    assert '>Economic <span class="n" data-n="econ">2</span>' in page
    assert '>FDA <span class="n" data-n="fda">1</span>' in page
    assert "Friday · 2 releases and 1 FDA catalyst today" in page


def test_an_fda_catalyst_shows_its_day_its_indication_and_its_status(seeded):
    page = report.render_html(now=NOW)
    assert '<span class="t">20 Nov</span>' in page
    assert "IOVA Lifileucel: PDUFA Date" in page
    assert "Indication <b>Advanced Melanoma</b>" in page and "Status <b>NDA</b>" in page


def test_a_catalyst_with_no_day_keeps_uw_s_own_words_and_stands_in_its_own_group(seeded):
    """#807's rule on the page: a quarter is never read as a day. It carries the chip, UW's own text and no
    place on the strip."""
    page = report.render_html(now=NOW)
    assert "Later, no day yet" in page
    assert '<span class="t na">Q2 2027</span>' in page
    assert '<span class="pchip">no day yet</span>' in page
    assert "Unusual Whales serves this one as 2027-Q2, not a day" in page
    assert 'data-day="2027-04-01"' not in page, "an undated catalyst never joins a day of the strip"


def test_the_countdown_names_the_next_release_and_an_fda_day_has_no_clock(seeded):
    page = report.render_html(now=NOW)
    assert f'<b data-ts="{_at(20, 14, 30):.0f}">42:00</b>' in page, "the clock to the next release"
    assert 'Initial Jobless Claims</span> 14:30' in page
    assert "Coming in <b>—</b>" in page and "today, no time published" in page


@pytest.mark.parametrize("text, written", [
    ("2027-Q2", "Q2 2027"), ("2027-H1", "H1 2027"), ("2027-MID", "Mid 2027"), ("2027-LATE", "Late 2027"),
    ("", "No date"), (None, "No date"), ("soon", "soon"),
])
def test_uw_s_target_text_is_written_as_the_board_says_it(text, written):
    assert report.window_label(text) == written


@pytest.mark.parametrize("precision, first_day, today, still_open", [
    ("quarter", date(2026, 10, 1), date(2026, 11, 20), True),      # Q4 2026 began before this week, still open
    ("quarter", date(2026, 7, 1), date(2026, 11, 20), False),      # Q3 2026 has ended
    ("half", date(2026, 7, 1), date(2026, 11, 20), True),
    ("late", date(2026, 10, 1), date(2027, 1, 2), False),
    ("mid", date(2026, 7, 1), date(2027, 1, 2), False),
])
def test_a_window_that_has_ended_leaves_the_later_group(precision, first_day, today, still_open):
    row = {"event_ts": cal.day_start(first_day), "target_precision": precision}
    assert report.window_open(row, today) is still_open


def test_a_window_that_has_ended_is_not_read_back(seeded):
    rawstore.write_rows("news_events", [_fda(date(2025, 4, 1), "OLD Drug: FDA Decision", "Gone", "BLA",
                                             precision="quarter", text="2025-Q2")])
    page = report.render_html(now=NOW)
    assert "OLD Drug" not in page and "MRNA mRNA-1283" in page


def test_an_empty_calendar_says_so_for_the_day_and_for_the_week():
    page = report.render_html(now=NOW)
    assert "Nothing on this day" in page and "No FDA catalyst on this day." in page
    assert "No release left this week." in page
