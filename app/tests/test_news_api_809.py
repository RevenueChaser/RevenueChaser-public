"""The News board's two read-only routes (#809, slice N3 of #783).

``GET /api/news/events`` is new: the calendar rows still to come, economic and FDA (#807). ``GET
/api/news/headlines`` keeps its ``since`` poll and gains a window (``from``/``to``, optionally one ``ticker``),
which is what lets a reader ask for the headlines around a release instead of the last 24 hours.

Both are read-only: no ``X-RC-Panel`` header, and they write nothing. The rows are seeded against the clock the
run itself sees, because the events route answers "from today, Amsterdam" and has no ``now`` of its own.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta

import pytest

from RevenueChaser.app import dashboard
from RevenueChaser.core import rawstore
from RevenueChaser.module_news import calendar as cal, report

HOUR = 3600.0
NOW = time.time()
TODAY = cal.local_day(NOW)


def _day(offset: int, hour: int = 0) -> float:
    """``hour`` o'clock Amsterdam, ``offset`` days from today. Built from the day, not by adding seconds, so the
    two days a year the clocks change do not move it."""
    d = TODAY + timedelta(days=offset)
    return datetime(d.year, d.month, d.day, hour, tzinfo=cal.AMS).timestamp()


def _event(ts, event, kind="report", importance=1, forecast=None, prev=None, retired=None, **fda):
    return {"event_ts": ts, "event": event, "type": kind, "importance": importance, "forecast": forecast,
            "prev": prev, "reported_period": None, "first_seen": 1.0, "last_seen": 1.0, "retired_at": retired,
            "run_id": "t", "run_at": NOW, **fda}


@pytest.fixture
def client():
    return dashboard.app.test_client()


@pytest.fixture
def seeded():
    rawstore.write_rows("news_events", [
        _event(_day(0, 12), "Initial Jobless Claims", importance=2, forecast="232K", prev="227K"),
        _event(_day(0, 9), "Cancelled release", retired=NOW),
        _event(_day(3), "IOVA Lifileucel: PDUFA Date", kind=cal.FDA_TYPE, importance=3, ticker="IOVA",
               drug="Lifileucel", catalyst="PDUFA Date", indication="Advanced Melanoma", status="NDA",
               target_text=(TODAY + timedelta(days=3)).isoformat(), target_precision="day", outcome=None,
               url=None),
        _event(_day(20, 12), "Past the week"),
    ])
    rawstore.write_rows("news_headlines", [
        {"headline_id": "a", "provider": "ibkr", "published_at": NOW - 10 * 60, "headline": "Claims come in light",
         "source": "Dow Jones", "tickers": "[]", "url": None, "fetched_at": NOW, "run_id": "t", "run_at": NOW},
        {"headline_id": "b", "provider": "ibkr", "published_at": NOW - 6 * HOUR, "headline": "NVDA guides up",
         "source": "Dow Jones", "tickers": json.dumps(["NVDA"]), "url": None, "fetched_at": NOW, "run_id": "t",
         "run_at": NOW},
        {"headline_id": "c", "provider": "ibkr", "published_at": NOW - 40 * HOUR, "headline": "Old story",
         "source": "Dow Jones", "tickers": "[]", "url": None, "fetched_at": NOW, "run_id": "t", "run_at": NOW},
    ])


def test_the_events_route_serves_the_week_and_needs_no_panel_header(client, seeded):
    body = client.get("/api/news/events").get_json()
    assert body["ok"] is True and body["days"] == report.WEEK_DAYS
    names = [r["event"] for r in body["rows"]]
    assert names == ["Initial Jobless Claims", "IOVA Lifileucel: PDUFA Date"], names
    assert "Cancelled release" not in names, "a retired event is never served"
    assert "Past the week" not in names, "beyond the window asked for"
    first = body["rows"][0]
    assert first["importance"] == 2 and first["forecast"] == "232K" and first["prev"] == "227K"
    assert first["hm"] == "12:00" and first["day"] == TODAY.isoformat()


def test_an_fda_row_carries_its_own_fields_and_its_precision(client, seeded):
    rows = client.get("/api/news/events").get_json()["rows"]
    fda = next(r for r in rows if r["type"] == cal.FDA_TYPE)
    assert fda["ticker"] == "IOVA" and fda["drug"] == "Lifileucel" and fda["catalyst"] == "PDUFA Date"
    assert fda["indication"] == "Advanced Melanoma" and fda["application_status"] == "NDA"
    assert fda["target_precision"] == "day"
    econ = next(r for r in rows if r["type"] != cal.FDA_TYPE)
    assert "target_precision" not in econ, "an economic row carries no FDA fields"


def test_the_events_route_takes_a_type_and_a_day_count(client, seeded):
    body = client.get("/api/news/events?days=30&types=fda").get_json()
    assert [r["event"] for r in body["rows"]] == ["IOVA Lifileucel: PDUFA Date"]
    assert client.get("/api/news/events?days=30").get_json()["days"] == 30
    assert client.get("/api/news/events?days=0").status_code == 400
    assert client.get("/api/news/events?days=x").status_code == 400
    assert client.get("/api/news/events?days=400").get_json()["days"] == report.API_MAX_DAYS, "the window is capped"


def test_the_headlines_route_answers_a_window_and_one_name(client, seeded):
    body = client.get(f"/api/news/headlines?from={NOW - HOUR}&to={NOW}").get_json()
    assert [r["headline"] for r in body["rows"]] == ["Claims come in light"]
    wide = client.get(f"/api/news/headlines?from={NOW - 8 * HOUR}&to={NOW}&ticker=nvda").get_json()
    assert [r["headline"] for r in wide["rows"]] == ["NVDA guides up"], "the ticker filter is case-free"
    cut = client.get(f"/api/news/headlines?from={NOW - 8 * HOUR}&to={NOW}&limit=1").get_json()
    assert [r["headline"] for r in cut["rows"]] == ["Claims come in light"], "newest first, cut to the limit"
    assert "Old story" not in json.dumps(cut), "40 hours back is outside the window asked for"


def test_the_headlines_route_keeps_its_poll_and_refuses_a_bad_window(client, seeded):
    assert client.get("/api/news/headlines?since=0").get_json()["ok"] is True
    assert client.get("/api/news/headlines?since=x").status_code == 400
    assert client.get(f"/api/news/headlines?from={NOW}&to={NOW - HOUR}").status_code == 400
    assert client.get(f"/api/news/headlines?from=0&to={NOW}").status_code == 400, "a window of years is refused"
    assert client.get(f"/api/news/headlines?from={NOW - HOUR}&to={NOW}&ticker=NOT%20A%20TICKER").status_code == 400


def _count(table: str) -> int:
    return rawstore.query(f"SELECT count(*) AS n FROM {table}", db="news")[0]["n"]


def test_neither_route_writes_anything(client, seeded):
    before = (_count("news_events"), _count("news_headlines"))
    events = client.get("/api/news/events")
    heads = client.get(f"/api/news/headlines?from={NOW - HOUR}&to={NOW}")
    # Both answered, so the counts below are about two routes that ran and not about a 404.
    assert events.status_code == 200 and events.get_json()["ok"] is True
    assert heads.status_code == 200 and heads.get_json()["ok"] is True
    assert (_count("news_events"), _count("news_headlines")) == before
