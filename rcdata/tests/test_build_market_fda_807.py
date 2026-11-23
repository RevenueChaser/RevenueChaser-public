"""Market 5 (#807): ``uw/fda_calendar`` through the builder, UW mocked at the HTTP boundary.

An hourly dataset of the ``market`` kind, kept the way the economic calendar is: a snapshot day is that day's newest
fetch. The row fields are UW's own (``docs/openapi.yaml``, schema ``FDA Calendar``).
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from revenuechaser.core import calendar
from revenuechaser.core.providers import unusual_whales
from revenuechaser.rcdata import ops, read, serving
from revenuechaser.rcdata.build import DATASETS, base, due, uw_fda_calendar as fda

pytestmark = pytest.mark.usefixtures("kinds_full")

UW_HEADERS = {"x-uw-daily-req-count": "355", "x-uw-req-per-minute-remaining": "1000000",
              "x-uw-req-per-minute-reset": "60000", "x-uw-token-req-limit": "100000000",
              "content-type": "application/json"}
NOW = datetime(2026, 11, 20, 19, 0, tzinfo=timezone.utc)
PDUFA = {"ticker": "IOVA", "drug": "Lifileucel", "status": "NDA", "catalyst": "PDUFA Date",
         "start_date": "2026-12-04", "end_date": "2026-12-04", "indication": "Advanced Melanoma",
         "description": "FDA decision for Lifileucel in advanced melanoma", "notes": "Pipeline milestone",
         "outcome": None, "outcome_brief": None, "has_options": True, "marketcap": "1000000000",
         "source_link": "https://www.fda.gov/news-events/press-announcements/fda-example"}
QUARTER = {"ticker": "SRPT", "drug": "Elevidys", "status": "BLA", "catalyst": "FDA Decision",
           "start_date": "2027-Q2", "end_date": "2027-Q2", "indication": "DMD"}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("UNUSUAL_WHALES_API_KEY", "test-key")
    monkeypatch.setattr(unusual_whales, "BASE", "https://uw.test/api")
    monkeypatch.setattr(calendar, "_now", lambda: NOW)


def _run(name: str = fda.NAME) -> dict:
    return base.run_request({"dataset": name, "params": {}})


def test_the_calendar_lands_typed_and_reads_back(http_mock):
    http_mock.add("/market/fda-calendar", {"data": [PDUFA, {"ticker": "X", "drug": "no date"}]}, headers=UW_HEADERS)
    row = _run()
    assert row["result"] == "changed" and row["rows"] == 1 and row["calls"] == 1, row
    got = read.fda_calendar()
    assert len(got) == 1
    r = got[0]
    assert (r["snapshot_date"], r["target_date"], r["ticker"], r["drug"]) == (
        date(2026, 11, 20), date(2026, 12, 4), "IOVA", "Lifileucel")
    assert r["catalyst"] == "PDUFA Date" and r["indication"] == "Advanced Melanoma"
    # UW's own ``status`` is served as ``application_status``: ``read`` keeps ``status`` for the dataset's
    # freshness and stamps it on every row it hands back.
    assert r["application_status"] == "NDA" and r["status"] == "changed"
    assert r["target_text"] == "2026-12-04" and r["target_precision"] == fda.DAY
    assert r["has_options"] is True and r["marketcap"] == 1_000_000_000.0
    assert r["outcome"] is None and r["source_link"].startswith("https://www.fda.gov/")
    assert any(i["kind"] == "unkeyed" for i in ops.rows("build_issues")), "the row with no target date is reported"


def test_a_quarter_is_resolved_to_its_first_day_and_says_so(http_mock):
    """UW writes ``2027-Q2`` as well as a day. The text is kept and the day is written with its precision, so a
    reader can tell "4 Dec 2026" from "some time in Q2 2027" (#807: never snap a quarter to a day silently)."""
    http_mock.add("/market/fda-calendar", {"data": [QUARTER]}, headers=UW_HEADERS)
    assert _run()["result"] == "changed"
    r = read.fda_calendar()[0]
    assert r["target_date"] == date(2027, 4, 1) and r["target_text"] == "2027-Q2"
    assert r["target_precision"] == fda.QUARTER


@pytest.mark.parametrize("text, day, precision", [
    ("2027-01-15", date(2027, 1, 15), fda.DAY),
    ("2027-Q1", date(2027, 1, 1), fda.QUARTER),
    ("2027-Q4", date(2027, 10, 1), fda.QUARTER),
    ("2027-H1", date(2027, 1, 1), fda.HALF),
    ("2027-H2", date(2027, 7, 1), fda.HALF),
    ("2027-MID", date(2027, 7, 1), fda.MID),
    ("2027-LATE", date(2027, 10, 1), fda.LATE),
    ("2027-02-30", None, None),
    ("soon", None, None),
    (None, None, None),
])
def test_every_target_date_format_uw_documents_resolves_with_its_precision(text, day, precision):
    assert fda.target_day(text) == (day, precision)


def test_a_later_fetch_the_same_day_replaces_the_day_so_a_revision_is_kept(http_mock):
    http_mock.add("/market/fda-calendar", {"data": [PDUFA, QUARTER]}, headers=UW_HEADERS)
    _run()
    http_mock.routes.clear()
    decided = {**PDUFA, "outcome": "Approved", "outcome_brief": "Approved for advanced melanoma"}
    http_mock.add("/market/fda-calendar", {"data": [decided, QUARTER]}, headers=UW_HEADERS)
    assert _run()["result"] == "changed"
    got = {r["ticker"]: r for r in read.fda_calendar()}
    assert got["IOVA"]["outcome"] == "Approved" and got["IOVA"]["outcome_brief"].startswith("Approved for")
    assert len(got) == 2 and len(list(fda.day_dir(date(2026, 11, 20)).glob("*.json.gz"))) >= 1


def test_a_later_fetch_that_dropped_a_catalyst_is_served_and_not_refused_by_the_shrink_guard(http_mock):
    """The answer is the calendar as it stands, so a catalyst UW drops leaves the day it was fetched on: the day's
    newest fetch can hold fewer rows than its first one. ``fda_event`` is in ``serving.SHRINKS_BY_CHOICE``."""
    http_mock.add("/market/fda-calendar", {"data": [PDUFA, QUARTER]}, headers=UW_HEADERS)
    _run()
    http_mock.routes.clear()
    http_mock.add("/market/fda-calendar", {"data": [PDUFA]}, headers=UW_HEADERS)
    row = _run()
    assert row["result"] == "changed" and row["rows"] == 1, row
    assert [r["ticker"] for r in read.fda_calendar()] == ["IOVA"], "the swap did not go through"
    assert fda.TABLE in serving.SHRINKS_BY_CHOICE


def test_two_catalysts_of_one_drug_on_one_day_keep_the_first_row_and_are_reported(http_mock):
    """The key is #807's ``(snapshot_date, target_date, ticker, drug)``, so a second catalyst of the same drug on the
    same day cannot have a row of its own: the first stands and the build writes an issue about it."""
    http_mock.add("/market/fda-calendar",
                  {"data": [PDUFA, {**PDUFA, "catalyst": "Advisory Committee Meeting"}]}, headers=UW_HEADERS)
    assert _run()["rows"] == 1
    assert read.fda_calendar()[0]["catalyst"] == "PDUFA Date"
    assert any(i["kind"] == "duplicate" for i in ops.rows("build_issues"))


def test_an_empty_or_failed_answer_is_a_failed_check_and_keeps_what_is_served(http_mock):
    http_mock.add("/market/fda-calendar", {"data": []}, headers=UW_HEADERS)
    assert _run()["result"] == "failed"
    assert read.fda_calendar() == []


def test_no_market_file_reads_as_no_rows():
    assert read.fda_calendar() == [] and read.fda_events() == []


def test_the_dataset_is_an_hourly_market_source_and_the_kind_is_market_5_or_later(http_mock):
    from revenuechaser.rcdata import scaffold
    assert serving.SERVING_SCHEMA_VERSION["market"] >= 5      # 6 since #1433: ``source`` joined the key
    assert DATASETS[fda.NAME].cadence == "hourly" and DATASETS[fda.NAME].kind == "market"
    assert scaffold.SCHEMA_OF_KIND["market"][fda.TABLE] == list(fda.SCHEMA)
    assert read.DATASET_OF_TABLE[fda.TABLE] == fda.NAME and read.KIND_OF_TABLE[fda.TABLE] == "market"


def test_an_hourly_dataset_is_due_again_an_hour_after_its_run(http_mock, monkeypatch):
    http_mock.add("/market/fda-calendar", {"data": [PDUFA]}, headers=UW_HEADERS)
    _run()
    # The fixture's ``_now`` is a fixed day, the run's own start is the wall clock, so both ends of the hour are
    # read from the run that just happened.
    started = ops.run_started_at(ops.latest_check(fda.NAME)["run_id"])
    monkeypatch.setattr(calendar, "_now", lambda: datetime.fromtimestamp(started + 60, timezone.utc))
    assert due.is_due(DATASETS[fda.NAME])[0] is False
    monkeypatch.setattr(calendar, "_now", lambda: datetime.fromtimestamp(started + 3600, timezone.utc))
    assert due.is_due(DATASETS[fda.NAME])[0] is True


def test_the_need_catalog_knows_the_table_and_asks_no_names():
    from revenuechaser.rcdata.needs import catalog, screen
    need = catalog.NEEDS["market.fda_calendar"]
    assert (need.table, need.day_column, need.max_lag_unit) == (fda.TABLE, "snapshot_date", catalog.DAYS)
    assert need.reader is read.fda_calendar and need.ask_param is None
    assert fda.NAME in screen.DATASETS and fda.NAME in screen.NO_TIER_DATASET_WORDS


def test_a_timeout_gets_a_second_ladder_after_a_pause_and_the_fetch_lands(http_mock, monkeypatch):
    import httpx
    monkeypatch.setattr(unusual_whales, "_sleep", lambda s: None)
    pauses, sent = [], []

    def answer(request):
        sent.append(request)
        if len(sent) <= unusual_whales.MAX_ATTEMPTS:            # the client's whole first ladder times out
            raise httpx.ConnectTimeout("timed out", request=request)
        return 200, {"data": [PDUFA]}, UW_HEADERS

    http_mock.add("/market/fda-calendar", answer)
    row = base.run_request({"dataset": fda.NAME, "params": {}}, sleep=pauses.append)
    assert row["result"] == "changed", row
    assert fda.TRANSPORT_RETRY_PAUSE_S in pauses
    assert len(sent) == unusual_whales.MAX_ATTEMPTS + 1
