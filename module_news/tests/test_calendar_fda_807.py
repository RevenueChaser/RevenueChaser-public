"""The FDA lane of the incremental calendar build (#807): ``market.fda_event`` -> ``news.news_events``, ``type``
``fda``, upsert by key, retire never delete, and never a day's highlight."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from revenuechaser.core import econ_importance, rawstore
from revenuechaser.module_earnings_radar.tests.market_store_fixture import serve_economic, serve_fda
from revenuechaser.module_news import calendar as cal

T0 = datetime(2026, 11, 20, 14, 30, tzinfo=cal.AMS).timestamp()     # Fri 20 Nov 14:30 Amsterdam
PDUFA = {"ticker": "IOVA", "drug": "Lifileucel", "status": "NDA", "catalyst": "PDUFA Date",
         "start_date": "2026-12-04", "end_date": "2026-12-04", "indication": "Advanced Melanoma",
         "source_link": "https://www.fda.gov/news-events/press-announcements/fda-example"}
ADCOM = {"ticker": "SRPT", "drug": "Elevidys", "status": "BLA", "catalyst": "Advisory Committee Meeting",
         "start_date": "2026-12-08", "end_date": "2026-12-08"}
QUARTER = {"ticker": "MRNA", "drug": "mRNA-1283", "status": "BLA", "catalyst": "FDA Decision",
           "start_date": "2027-Q2", "end_date": "2027-Q2"}


def _sweep(items, fetched_at, day="2026-11-20"):
    serve_fda({date.fromisoformat(day): items}, fetched_at=fetched_at)


def _fda_rows():
    return {r["event"]: r for r in rawstore.query(
        "SELECT * FROM news_events WHERE type = ? ORDER BY event_ts", [cal.FDA_TYPE], db="news")}


def test_the_first_pass_writes_one_row_a_catalyst_with_its_own_type():
    _sweep([PDUFA, ADCOM], fetched_at=100.0)
    out = cal.build(now=200.0)
    rows = _fda_rows()
    assert out["fda_read"] == 2 and out["fda_upserted"] == 2 and out["fda_retired"] == 0
    r = rows["IOVA Lifileucel: PDUFA Date"]
    assert r["type"] == cal.FDA_TYPE and r["ticker"] == "IOVA" and r["drug"] == "Lifileucel"
    assert r["catalyst"] == "PDUFA Date" and r["indication"] == "Advanced Melanoma"
    # The board's ``status`` comes from the served ``application_status``: ``rcdata.read`` stamps every row it
    # hands back with a ``status`` of its own, so the served name had to change (#807) and this pins the join.
    assert r["status"] == "NDA"
    assert r["url"].startswith("https://www.fda.gov/") and r["first_seen"] == 100.0 and r["retired_at"] is None
    assert r["forecast"] is None and r["prev"] is None
    assert r["event_ts"] == cal.day_start(date(2026, 12, 4)) and cal.local_day(r["event_ts"]) == date(2026, 12, 4)
    assert r["target_text"] == "2026-12-04" and r["target_precision"] == "day"


def test_a_catalyst_without_a_day_keeps_the_precision_of_the_text_it_came_from():
    """``2027-Q2`` is stored as the first day of the quarter, and ``target_precision`` says it was a quarter, so the
    board can write "Q2 2027" instead of a false 1 April."""
    _sweep([QUARTER], fetched_at=100.0)
    cal.build(now=200.0)
    r = _fda_rows()["MRNA mRNA-1283: FDA Decision"]
    assert r["target_text"] == "2027-Q2" and r["target_precision"] == "quarter"
    assert cal.local_day(r["event_ts"]) == date(2027, 4, 1)


def test_importance_comes_from_the_catalyst():
    _sweep([PDUFA, ADCOM, {**QUARTER, "catalyst": "Phase 3 data"}], fetched_at=100.0)
    cal.build(now=200.0)
    rows = _fda_rows()
    assert rows["IOVA Lifileucel: PDUFA Date"]["importance"] == econ_importance.HIGH
    assert rows["SRPT Elevidys: Advisory Committee Meeting"]["importance"] == econ_importance.HIGH
    assert rows["MRNA mRNA-1283: Phase 3 data"]["importance"] == econ_importance.MEDIUM


def test_a_second_build_reads_only_new_rows_and_keeps_first_seen():
    _sweep([PDUFA], fetched_at=100.0)
    cal.build(now=200.0)
    assert cal.build(now=250.0)["fda_read"] == 0
    _sweep([{**PDUFA, "outcome": "Approved"}], fetched_at=300.0)
    out = cal.build(now=400.0)
    r = _fda_rows()["IOVA Lifileucel: PDUFA Date"]
    assert out["fda_read"] == 1
    assert r["first_seen"] == 100.0 and r["last_seen"] == 300.0 and r["outcome"] == "Approved"


def test_a_catalyst_the_newest_fetch_drops_inside_its_span_is_retired_not_deleted():
    _sweep([PDUFA, ADCOM, QUARTER], fetched_at=100.0)
    cal.build(now=200.0)
    _sweep([PDUFA, QUARTER], fetched_at=300.0)
    out = cal.build(now=400.0)
    rows = _fda_rows()
    assert out["fda_retired"] == 1
    assert rows["SRPT Elevidys: Advisory Committee Meeting"]["retired_at"] == 400.0
    assert rows["IOVA Lifileucel: PDUFA Date"]["retired_at"] is None and len(rows) == 3


def test_an_fda_row_is_never_a_day_s_highlight():
    """The highlight is the economic calendar's (plan §5): an FDA row on the same day never takes it, and a day with
    FDA rows only has none."""
    serve_economic({date(2026, 11, 20): [{"event_ts": T0, "event": "CPI, M/M%", "type": "report"}]}, fetched_at=100.0)
    _sweep([{**PDUFA, "start_date": "2026-11-20", "end_date": "2026-11-20"}], fetched_at=100.0)
    cal.build(now=T0)
    hl = rawstore.query("SELECT * FROM news_highlight", db="news")
    assert [(r["event"], r["type"]) for r in hl] == [("CPI, M/M%", "report")]


def test_the_economic_lane_does_not_retire_an_fda_row_and_the_two_marks_are_their_own():
    serve_economic({date(2026, 11, 20): [{"event_ts": T0, "event": "CPI, M/M%", "type": "report"}]}, fetched_at=100.0)
    _sweep([{**PDUFA, "start_date": "2026-11-20", "end_date": "2026-11-20"}], fetched_at=100.0)
    cal.build(now=200.0)
    # The next economic sweep drops nothing of its own; the FDA row sits inside its span and must stay live.
    serve_economic({date(2026, 11, 21): [{"event_ts": T0, "event": "CPI, M/M%", "type": "report"}]}, fetched_at=300.0)
    out = cal.build(now=400.0)
    assert out["retired"] == 0 and out["fda_retired"] == 0
    assert _fda_rows()["IOVA Lifileucel: PDUFA Date"]["retired_at"] is None
    marks = {r["key"]: r["value"] for r in rawstore.query("SELECT * FROM news_meta", db="news")}
    assert float(marks[cal.MARK_KEY]) == 300.0 and float(marks[cal.FDA_MARK_KEY]) == 100.0


def test_the_board_page_shows_the_stored_fda_lane():
    """#807 stored the lane and kept it off the page until avo had approved a mock; #808 is that tab (avo,
    19 Nov 2026: "News olur"), so a stored catalyst now stands on the board with its own two columns."""
    from revenuechaser.module_news import report
    _sweep([{**PDUFA, "start_date": "2026-11-21", "end_date": "2026-11-21"}], fetched_at=100.0)
    cal.build(now=T0)
    html = report.render_html(now=T0)
    assert "IOVA Lifileucel: PDUFA Date" in html
    assert "Advanced Melanoma" in html and ">NDA<" in html      # the indication and where the application stands
    assert "21 Nov" in html and 'pchip">no day yet' not in html   # a real day is a day, not a window


@pytest.mark.parametrize("catalyst, level", [("PDUFA Date", econ_importance.HIGH),
                                             ("Advisory Committee Meeting", econ_importance.HIGH),
                                             ("FDA Decision", econ_importance.HIGH),
                                             ("Topline results", econ_importance.MEDIUM),
                                             ("NDA submission", econ_importance.MEDIUM),
                                             ("Investor day", econ_importance.LOW),
                                             (None, econ_importance.LOW)])
def test_the_fda_importance_table(catalyst, level):
    assert econ_importance.fda_importance(catalyst) == level
