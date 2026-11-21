"""Market 3 (#643): ``uw/economic_calendar`` through the builder, UW mocked at the HTTP boundary; an hourly dataset of
the ``market`` kind. Market 4 dropped the IBKR headlines (``ibkr/news``, ``news_headline``) for ``boards/news.duckdb``."""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from RevenueChaser.core import calendar
from RevenueChaser.core.providers import unusual_whales
from RevenueChaser.rcdata import ops, read, serving
from RevenueChaser.rcdata.build import DATASETS, base, due, uw_economic_calendar as econ

pytestmark = pytest.mark.usefixtures("kinds_full")

UW_HEADERS = {"x-uw-daily-req-count": "355", "x-uw-req-per-minute-remaining": "1000000",
              "x-uw-req-per-minute-reset": "60000", "x-uw-token-req-limit": "100000000",
              "content-type": "application/json"}
NOW = datetime(2026, 11, 9, 19, 0, tzinfo=timezone.utc)
CPI = {"event": "CPI", "type": "report", "time": "2026-11-12T13:30:00Z", "forecast": "0.3%", "prev": "0.4%",
       "reported_period": "October"}
FOMC = {"event": "FOMC Minutes", "type": "fomc", "time": "2026-11-18 19:00:00+00:00", "forecast": None,
        "prev": None, "reported_period": None}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("UNUSUAL_WHALES_API_KEY", "test-key")
    monkeypatch.setattr(unusual_whales, "BASE", "https://uw.test/api")
    monkeypatch.setattr(calendar, "_now", lambda: NOW)


def _run(name: str) -> dict:
    return base.run_request({"dataset": name, "params": {}})


# ── uw/economic_calendar ──────────────────────────────────────────────────────────────────────────────────────

def test_the_calendar_lands_typed_and_reads_back(http_mock):
    http_mock.add("/market/economic-calendar", {"data": [CPI, FOMC, {"event": "no time", "type": "report"}]},
                  headers=UW_HEADERS)
    row = _run(econ.NAME)
    assert row["result"] == "changed" and row["rows"] == 2 and row["calls"] == 1, row
    got = read.economic_calendar()
    assert [(r["event"], r["type"], r["forecast"]) for r in got] == [("CPI", "report", "0.3%"),
                                                                     ("FOMC Minutes", "fomc", None)]
    assert got[0]["snapshot_date"] == date(2026, 11, 9) and got[0]["event_ts"] == datetime(
        2026, 11, 12, 13, 30, tzinfo=timezone.utc).timestamp()
    assert any(i["kind"] == "unkeyed" for i in ops.rows("build_issues"))


def test_a_later_fetch_the_same_day_replaces_the_day_so_a_revision_is_kept(http_mock):
    http_mock.add("/market/economic-calendar", {"data": [CPI, FOMC]}, headers=UW_HEADERS)
    _run(econ.NAME)
    http_mock.routes.clear()
    # The forecast is revised and the minutes move a day: same row count, so the swap's shrink guard is not met.
    moved = {**FOMC, "time": "2026-11-19 19:00:00+00:00"}
    http_mock.add("/market/economic-calendar", {"data": [{**CPI, "forecast": "0.2%"}, moved]}, headers=UW_HEADERS)
    row = _run(econ.NAME)
    assert row["result"] == "changed", row
    got = read.economic_calendar()
    assert [(r["event"], r["forecast"]) for r in got] == [("CPI", "0.2%"), ("FOMC Minutes", None)]
    assert got[1]["event_time"] == "2026-11-19 19:00:00+00:00", "the moved event is not kept twice"
    assert len(list(econ.day_dir(date(2026, 11, 9)).glob("*.json.gz"))) >= 1


def test_a_later_fetch_that_dropped_an_event_is_served_and_not_refused_by_the_shrink_guard(http_mock):
    """RC-Build on homesrv failed every hour from 00:05 UTC on 14 Nov 2026: the calendar is a forward-looking window
    and a day's partition is replaced whole by that day's newest fetch, so the day loses the events that rolled out
    of UW's "this week and next" (114 rows against 126 live, -9.5 %). The swap's 1 % shrink guard refused that, and
    with it the whole ``market`` build. ``economic_event`` is in ``serving.SHRINKS_BY_CHOICE`` since."""
    http_mock.add("/market/economic-calendar", {"data": [CPI, FOMC]}, headers=UW_HEADERS)
    _run(econ.NAME)
    http_mock.routes.clear()
    http_mock.add("/market/economic-calendar", {"data": [CPI]}, headers=UW_HEADERS)   # the minutes rolled out
    row = _run(econ.NAME)
    assert row["result"] == "changed" and row["rows"] == 1, row
    assert [r["event"] for r in read.economic_calendar()] == ["CPI"], "the swap did not go through"


def test_an_empty_answer_is_skipped_not_failed_and_keeps_what_is_served(http_mock):
    """21 Nov 2026: UW answered 200 with no rows and the whole hourly pass exited 1 with it. An empty answer must
    still not be stored -- the window is never empty -- but it is this dataset's skip, not the pass's failure, and
    the gap is an open ``source_empty`` issue while it lasts."""
    http_mock.add("/market/economic-calendar", {"data": []}, headers=UW_HEADERS)
    row = _run(econ.NAME)
    assert row["result"] == "skipped"
    assert "no rows" in row["note"]
    assert read.economic_calendar() == []
    assert [(i["kind"], i["key"]) for i in ops.open_issues(econ.NAME)[1]] == [("source_empty", "2026-11-09")]


def test_an_answer_that_is_not_a_list_is_skipped_the_same_way(http_mock):
    http_mock.add("/market/economic-calendar", {"data": {"event": "CPI"}}, headers=UW_HEADERS)
    assert _run(econ.NAME)["result"] == "skipped"
    assert read.economic_calendar() == []


def test_no_market_file_reads_as_no_rows():
    assert read.economic_calendar() == []


# ── market 4: the headlines left for the News board's own file ───────────────────────────────────────────────

def test_market_4_builds_no_headlines_and_retires_the_live_table():
    """avo's option A (10 Nov 2026): ``boards/news.duckdb`` is the only home of the headlines, so the builder's
    ``ibkr/news`` is gone and a live market 3 file's ``news_headline`` may leave the build."""
    from RevenueChaser.rcdata import scaffold
    assert serving.SERVING_SCHEMA_VERSION["market"] >= 4      # 5 since #807; the rule below holds at every one
    assert "ibkr/news" not in DATASETS and not hasattr(read, "news_headlines")
    assert "news_headline" in serving.RETIRED_TABLES["market"]
    assert "news_headline" not in scaffold.SCHEMA_OF_KIND["market"], "a retired table is still built"
    assert econ.TABLE != "economic_calendar", "the old raw table's name, retired by needs/screen.py"
    assert DATASETS[econ.NAME].cadence == "hourly" and DATASETS[econ.NAME].kind == "market"


def test_a_live_market_3_file_with_headlines_swaps_to_a_build_without_them(http_mock, monkeypatch):
    with monkeypatch.context() as m:                # the live file is the deployed market 3 one
        m.setitem(serving.SERVING_SCHEMA_VERSION, "market", 3)
        with serving.build("market") as b:
            b.con.execute("CREATE TABLE news_headline AS SELECT range AS i FROM range(5)")
            b.swap({"news_headline": 5})
    assert serving.live_version("market") == 3
    http_mock.add("/market/economic-calendar", {"data": [CPI]}, headers=UW_HEADERS)
    assert _run(econ.NAME)["result"] == "changed"
    with serving.open_read("market") as con:
        names = {r[0] for r in con.execute("SELECT table_name FROM duckdb_tables()").fetchall()}
    assert "news_headline" not in names and econ.TABLE in names


def test_an_hourly_dataset_is_due_again_an_hour_after_its_run(http_mock, monkeypatch):
    http_mock.add("/market/economic-calendar", {"data": [CPI]}, headers=UW_HEADERS)
    _run(econ.NAME)
    assert due.is_due(DATASETS[econ.NAME])[0] is False
    started = ops.run_started_at(ops.latest_check(econ.NAME)["run_id"])
    monkeypatch.setattr(calendar, "_now", lambda: datetime.fromtimestamp(started + 3600, timezone.utc))
    assert due.is_due(DATASETS[econ.NAME])[0] is True


def test_settings_reads_the_hourly_cadence_and_counts_it_like_a_daily_one():
    from RevenueChaser.module_settings import newdata
    assert newdata._cadence(econ.NAME, None) == "hourly"
    check = {"result": "changed", "source_as_of": "2026-11-09", "checked_on": "2026-11-09", "coverage": None}
    assert newdata.status_of(econ.NAME, check, check, "hourly", NOW)[0] == "fresh"


def test_a_timeout_gets_a_second_ladder_after_a_pause_and_the_fetch_lands(http_mock, monkeypatch):
    import httpx
    monkeypatch.setattr(unusual_whales, "_sleep", lambda s: None)
    pauses, sent = [], []

    def answer(request):
        sent.append(request)
        if len(sent) <= unusual_whales.MAX_ATTEMPTS:            # the client's whole first ladder times out
            raise httpx.ConnectTimeout("timed out", request=request)
        return 200, {"data": [CPI]}, UW_HEADERS

    http_mock.add("/market/economic-calendar", answer)
    row = base.run_request({"dataset": econ.NAME, "params": {}}, sleep=pauses.append)
    assert row["result"] == "changed", row
    assert econ.TRANSPORT_RETRY_PAUSE_S in pauses
    assert len(sent) == unusual_whales.MAX_ATTEMPTS + 1


def test_an_http_error_is_not_retried_after_a_pause(http_mock, monkeypatch):
    monkeypatch.setattr(unusual_whales, "_sleep", lambda s: None)
    pauses = []
    http_mock.add("/market/economic-calendar", {"error": "down"}, status=500, headers=UW_HEADERS)
    assert base.run_request({"dataset": econ.NAME, "params": {}}, sleep=pauses.append)["result"] == "failed"
    assert econ.TRANSPORT_RETRY_PAUSE_S not in pauses


# ── the call names its window (#1235) ────────────────────────────────────────────────────────────────────────────

def test_the_call_asks_for_a_window_around_the_snapshot_day(http_mock):
    """The parameterless call is forward-only, so it answers nothing while UW's forward window is empty -- measured
    21 Nov 2026 08:35 UTC: 0 rows with no parameters, 34 for a named 17-28 Nov window. The call names the window."""
    http_mock.add("/market/economic-calendar", {"data": [CPI, FOMC]}, headers=UW_HEADERS)
    _run(econ.NAME)
    url = str(http_mock.calls("/market/economic-calendar")[0].url)
    assert "min_date=2026-11-02" in url and "max_date=2026-11-30" in url, url


def test_the_window_is_named_in_days_around_the_new_york_day():
    assert econ.window_params(date(2026, 11, 9)) == {"min_date": "2026-11-02", "max_date": "2026-11-30"}


def test_a_day_the_window_does_not_cover_is_recorded_as_an_issue_and_still_stored(http_mock):
    """This provider drops a parameter it does not support without an error (#746), so the filter we send is
    verified on the rows that come back rather than trusted. It is **recorded**, not raised: a row outside the
    window is a correct calendar row, so refusing the day would drop good data over a parameter habit."""
    far = {**CPI, "event": "CPI next year", "time": "2026-12-25T13:30:00Z"}
    http_mock.add("/market/economic-calendar", {"data": [CPI, far]}, headers=UW_HEADERS)
    row = _run(econ.NAME)
    assert row["result"] == "changed", row
    issue = next(i for i in ops.open_issues(econ.NAME)[1] if i["kind"] == "outside_window")
    assert "2026-12-25" in issue["detail"] and "2026-11-02..2026-11-30" in issue["detail"], issue["detail"]
    assert sorted(r["event"] for r in read.economic_calendar()) == ["CPI", "CPI next year"]


def test_the_window_edges_are_inside_it_with_a_day_of_slack_for_the_utc_day():
    """``time`` is UTC and the window is named in New York days, so a 00:30 UTC row belongs to the day before."""
    as_of = date(2026, 11, 9)
    assert econ.outside_window([date(2026, 11, 1), date(2026, 11, 2), date(2026, 11, 30),
                                date(2026, 12, 1)], as_of) == []
    assert econ.outside_window([date(2026, 10, 31), date(2026, 12, 2)], as_of) == [date(2026, 10, 31),
                                                                                   date(2026, 12, 2)]


def test_an_empty_answer_names_the_window_it_asked_for(http_mock):
    http_mock.add("/market/economic-calendar", {"data": []}, headers=UW_HEADERS)
    _run(econ.NAME)
    detail = ops.open_issues(econ.NAME)[1][0]["detail"]
    assert "2026-11-02..2026-11-30" in detail, detail


def test_a_backfill_is_refused_because_a_snapshot_cannot_be_made_after_the_day(http_mock):
    """Not because UW has no past: the named window does answer for days behind today. A day's row is what UW said
    on that day, so only a fetch made that day can say it."""
    with pytest.raises(Exception) as e:
        econ.DATASET.backfill(None, date(2026, 11, 1), date(2026, 11, 8))
    assert "only a fetch made that day" in str(e.value)
