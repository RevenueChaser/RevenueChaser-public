"""Market 6 (#1433 lane F, #1417 G-4): the economic and FDA calendars from keyless sources, beside UW's.

Every source is mocked at the HTTP boundary. The rows are cut from the real answers of 23 Nov 2026 (TradingView's
calendar, the Fed's ``calendar.json``, an EDGAR full-text search hit and its 8-K exhibit, a Federal Register
notice), shortened to the fields the code reads.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from revenuechaser.core import calendar
from revenuechaser.core.providers import unusual_whales
from revenuechaser.rcdata import read, serving
from revenuechaser.rcdata.build import DATASETS, base, econ_calendar_sources as econ, fda_calendar_sources as fda
from revenuechaser.rcdata.build import uw_economic_calendar, uw_fda_calendar

pytestmark = pytest.mark.usefixtures("kinds_full")

NOW = datetime(2026, 11, 23, 21, 0, tzinfo=timezone.utc)
UW_HEADERS = {"x-uw-daily-req-count": "1", "x-uw-req-per-minute-remaining": "1000000",
              "x-uw-req-per-minute-reset": "60000", "x-uw-token-req-limit": "100000000",
              "content-type": "application/json"}
TV = {"status": "ok", "result": [
    {"id": "1", "title": "Initial Jobless Claims", "country": "US", "date": "2026-11-25T13:30:00.000Z",
     "forecast": 222, "previous": 220, "actual": None, "period": "Nov/22", "importance": 0},
    {"id": "2", "title": "CPI", "country": "US", "date": "2026-12-10T13:30:00.000Z", "forecast": None,
     "previous": 325.1, "actual": None, "period": "Nov", "importance": 0},
    {"id": "3", "title": "no time", "country": "US", "date": None}]}
FED = {"events": [
    {"month": "2026-11", "days": "20", "time": "12:15 p.m.", "title": "Speech - Governor Lisa D. Cook",
     "description": "The U.S. Economy in Global Context", "type": "Speeches"},
    {"month": "2026-12", "days": "9", "time": "2:00 p.m.", "title": "FOMC Meeting",
     "description": "&lt;p&gt;Two-day meeting, December 8 - 9&lt;/p&gt;", "type": "FOMC"},
    {"month": "2026-11", "days": "25", "time": "2:00 p.m.", "title": "Beige Book", "description": None,
     "type": "Beige"},
    {"month": "2026-11", "days": "24", "time": "4:30 p.m.", "title": "H.4.1 Factors", "type": "Stat"},
    {"month": "2019-03", "days": "20", "time": "2:00 p.m.", "title": "FOMC Meeting", "type": "FOMC"}]}
UW_PDUFA = {"ticker": "IOVA", "drug": "Lifileucel", "status": "NDA", "catalyst": "PDUFA Date",
            "start_date": "2026-12-04", "end_date": "2026-12-04", "indication": "Advanced Melanoma"}
UW_CPI = {"event": "CPI", "type": "report", "time": "2026-12-10T13:30:00Z", "forecast": "0.3%", "prev": "0.4%",
          "reported_period": "November"}
EFTS = {"hits": {"total": {"value": 1}, "hits": [
    {"_id": "0001689548-26-000086:praxisq32026pr.htm",
     "_source": {"ciks": ["0001689548"], "display_names": ["Praxis Precision Medicines, Inc.  (PRAX)  (CIK 0001689548)"],
                 "file_date": "2026-11-09", "form": "8-K"}}]}}
EXHIBIT = ("<html><body><p>Praxis Precision Medicines Provides Corporate Update.</p>"
           "<p>The NDA for relutrigine for the treatment of SCN2A and SCN8A DEEs remains under FDA review, with a "
           "PDUFA target action date of December 27, 2026.</p>"
           "<p>The New Drug Application (NDA) for ulixacaltamide was accepted with a PDUFA date of Jan. 29, 2027.</p>"
           "<p>This release contains forward-looking statements about the PDUFA date of December 27, 2026.</p>"
           "</body></html>")
FEDREG = {"count": 2, "results": [
    {"title": "Oncologic Drugs Advisory Committee; Notice of Meeting; Establishment of a Public Docket",
     "dates": "The meeting will be held on December 15, 2026, from 8:00 a.m. to 5:00 p.m. Eastern Time.",
     "abstract": "The Food and Drug Administration (FDA) announces a forthcoming public advisory committee meeting.",
     "html_url": "https://www.federalregister.gov/documents/2026/11/20/x", "publication_date": "2026-11-20"},
    {"title": "Tobacco Products Scientific Advisory Committee; Notice of Meeting",
     "dates": "The meeting will be held on December 3, 2026.", "html_url": "https://example.test/t"}]}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("UNUSUAL_WHALES_API_KEY", "test-key")
    monkeypatch.setattr(unusual_whales, "BASE", "https://uw.test/api")
    monkeypatch.setattr(calendar, "_now", lambda: NOW)


def _run(name: str) -> dict:
    return base.run_request({"dataset": name, "params": {}})


def _econ_routes(http_mock, fed=FED, fed_status=200):
    http_mock.add("/events", TV)
    http_mock.add("/json/calendar.json", fed, status=fed_status)


def _fda_routes(http_mock):
    http_mock.add("/LATEST/search-index", EFTS)
    http_mock.add("/Archives/edgar/data/1689548/000168954826000086/praxisq32026pr.htm", EXHIBIT)
    http_mock.add("/api/v1/documents.json", FEDREG)


# ── the economic calendar ─────────────────────────────────────────────────────────────────────────────────────

def test_both_sources_land_in_economic_event_with_their_source_and_read_back(http_mock):
    _econ_routes(http_mock)
    row = _run(econ.NAME)
    assert row["result"] == "changed", row
    got = read.economic_calendar()
    by_event = {r["event"]: r for r in got}
    assert set(by_event) == {"Initial Jobless Claims", "CPI", "Speech - Governor Lisa D. Cook", "FOMC Meeting",
                             "Beige Book"}, "a Fed statistical release and a 2019 meeting are left out"
    assert by_event["CPI"]["source"] == "tradingview" and by_event["CPI"]["type"] == "report"
    assert by_event["Initial Jobless Claims"]["forecast"] == "222" and by_event["CPI"]["prev"] == "325.1"
    assert by_event["Speech - Governor Lisa D. Cook"]["type"] == "fed-speaker"
    assert by_event["FOMC Meeting"]["type"] == "fomc" and by_event["FOMC Meeting"]["source"] == "fed"
    assert by_event["Beige Book"]["type"] == "report"
    # The Fed's times are New York times: 2:00 p.m. on 9 Dec 2026 is 19:00 UTC.
    assert by_event["FOMC Meeting"]["event_ts"] == datetime(2026, 12, 9, 19, 0, tzinfo=timezone.utc).timestamp()
    assert by_event["FOMC Meeting"]["reported_period"] == "Two-day meeting, December 8 - 9"


def test_a_day_with_the_keyless_sources_leaves_uws_rows_of_that_day_out_and_a_uw_only_day_reads_as_before(http_mock):
    http_mock.add("/market/economic-calendar", {"data": [UW_CPI]}, headers=UW_HEADERS)
    assert _run(uw_economic_calendar.NAME)["result"] == "changed"
    assert [(r["event"], r["source"]) for r in read.economic_calendar()] == [("CPI", "uw")]
    _econ_routes(http_mock)
    assert _run(econ.NAME)["result"] == "changed"
    got = read.economic_calendar()
    assert {r["source"] for r in got} == {"tradingview", "fed"}, "UW's CPI would be the same release twice"
    assert all(r["source"] != "uw" for r in read.economic_events())
    with serving.open_read("market") as con:
        stored = con.execute("SELECT source, count(*) FROM economic_event GROUP BY source ORDER BY 1").fetchall()
    assert dict(stored)["uw"] == 1, "UW's row is still stored: the key holds the source, so both CPI rows fit"


def test_a_run_where_one_source_fails_keeps_nothing(http_mock):
    """The News board retires what its newest fetch no longer lists, so a run must never keep one source alone."""
    _econ_routes(http_mock, fed={"events": []})
    row = _run(econ.NAME)
    assert row["result"] in ("skipped", "failed"), row
    assert read.economic_calendar() == []
    assert not list(econ.day_dir(date(2026, 11, 23)).glob("*.json.gz"))


@pytest.mark.parametrize("month, days, clock, expected", [
    ("2026-11", "19", "9:25 a.m.", datetime(2026, 11, 19, 9, 25)),
    ("2026-12", "9", "2:00 p.m.", datetime(2026, 12, 9, 14, 0)),
    ("2026-12", "8-9", "12:30 p.m.", datetime(2026, 12, 8, 12, 30)),
    ("2026-11", "19", "", None),
    ("2026-11", None, "9:25 a.m.", None),
    ("2026-02", "30", "9:00 a.m.", None),
])
def test_the_feds_month_day_and_clock_are_a_new_york_time(month, days, clock, expected):
    got = econ.fed_ts(month, days, clock)
    want = None if expected is None else expected.replace(tzinfo=ZoneInfo("America/New_York")).timestamp()
    assert got == want


# ── the FDA calendar ──────────────────────────────────────────────────────────────────────────────────────────

def test_pdufa_dates_from_an_8k_and_a_meeting_from_the_federal_register_land_in_fda_event(http_mock):
    _fda_routes(http_mock)
    row = _run(fda.NAME)
    assert row["result"] == "changed", row
    got = {(r["ticker"], r["drug"]): r for r in read.fda_calendar()}
    assert set(got) == {("PRAX", "relutrigine"), ("PRAX", "ulixacaltamide"),
                        ("", "Oncologic Drugs Advisory Committee")}, "tobacco and the forward-looking text are out"
    r = got[("PRAX", "relutrigine")]
    assert r["target_date"] == date(2026, 12, 27) and r["target_precision"] == uw_fda_calendar.DAY
    assert r["catalyst"] == "PDUFA Date" and r["application_status"] == "NDA" and r["source"] == "sec"
    assert r["source_link"].endswith("/1689548/000168954826000086/praxisq32026pr.htm")
    assert got[("PRAX", "ulixacaltamide")]["target_date"] == date(2027, 1, 29), "a month cut short is read"
    meeting = got[("", "Oncologic Drugs Advisory Committee")]
    assert meeting["target_date"] == date(2026, 12, 15) and meeting["catalyst"] == "Advisory Committee Meeting"
    assert meeting["source"] == "federalregister"


def test_a_day_with_the_keyless_fda_sources_leaves_uws_rows_of_that_day_out(http_mock):
    """The FDA twin of the economic rule: UW's row of a day reads only until the SEC or the Federal Register has one."""
    http_mock.add("/market/fda-calendar", {"data": [UW_PDUFA]}, headers=UW_HEADERS)
    assert _run(uw_fda_calendar.NAME)["result"] == "changed"
    assert [(r["ticker"], r["source"]) for r in read.fda_calendar()] == [("IOVA", "uw")]
    _fda_routes(http_mock)
    assert _run(fda.NAME)["result"] == "changed"
    assert all(r["source"] != "uw" for r in read.fda_calendar()), "a keyless day hides UW's rows of that day"
    assert all(r["source"] != "uw" for r in read.fda_events())


def test_a_filed_document_is_fetched_once(http_mock):
    _fda_routes(http_mock)
    _run(fda.NAME)
    _run(fda.NAME)
    assert len(http_mock.calls("/Archives/edgar/data/")) == 1


@pytest.mark.parametrize("text, day, precision", [
    ("a PDUFA target action date of March 15, 2027.", date(2027, 3, 15), "day"),
    ("a PDUFA date of Dec. 4, 2026", date(2026, 12, 4), "day"),
    ("a PDUFA date of Sept. 4, 2026", date(2026, 9, 4), "day"),
    ("PDUFA date in the first quarter of 2027", date(2027, 1, 1), "quarter"),
    ("PDUFA goal in Q3 2027", date(2027, 7, 1), "quarter"),
    ("PDUFA date expected 1H 2027", date(2027, 1, 1), "half"),
    ("PDUFA in the second half of 2027", date(2027, 7, 1), "half"),
    ("a mid-2027 PDUFA", date(2027, 7, 1), "mid"),
    ("PDUFA late 2027", date(2027, 10, 1), "late"),
    ("no date at all", None, None),
])
def test_a_pdufa_date_is_read_with_its_precision(text, day, precision):
    assert fda.target(text)[:2] == (day, precision)


@pytest.mark.parametrize("sentence, name", [
    ("the FDA accepted the BLA for INO-3107 with a PDUFA date", "INO-3107"),
    ("Exhibit EX-99 says the NDA for relutrigine has a PDUFA date", "relutrigine"),
    ("approval of Zurzuvae (zuranolone) with a PDUFA date", "Zurzuvae"),
    ("The BLA has a PDUFA target action date of March 31, 2027.", None),
])
def test_the_product_a_sentence_names(sentence, name):
    assert fda.product(sentence) == name


# ── market 6 ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_market_6_keys_both_calendars_with_their_source_and_registers_the_two_new_datasets():
    assert serving.SERVING_SCHEMA_VERSION["market"] == 6
    assert "source" in uw_economic_calendar.KEY and "source" in uw_fda_calendar.KEY
    for ds in (econ.DATASET, fda.DATASET):
        assert DATASETS[ds.name] is ds and ds.kind == "market" and ds.cadence == "hourly" and ds.tables == ()
        assert ds.starts_by_hand, "a new dataset starts by hand (decision F4)"
    assert econ.DATASET.feeds == (uw_economic_calendar.TABLE,) and fda.DATASET.feeds == (uw_fda_calendar.TABLE,)


def test_spx_gammas_week_calendar_reads_the_store_and_not_uw(http_mock):
    """#1433: SPX Gamma's volatility calendar (A8) is the market store's, so the board asks UW for nothing here."""
    from revenuechaser.module_spx_gamma import snapshot as spx_snap, store_reads, vol_calendar
    assert store_reads.vol_calendar(date(2026, 11, 23))["stored"] is False, "nothing stored yet: says so"
    _econ_routes(http_mock)
    assert _run(econ.NAME)["result"] == "changed"
    out = store_reads.vol_calendar(date(2026, 11, 24))          # no snapshot of the 24th yet: the newest before it
    assert out["stored"] is True and out["source_as_of"] == "2026-11-23"
    week = vol_calendar.week_events(out["payload"], "2026-11-23")   # through Fri 27 Nov
    assert [r["event"] for r in week] == ["Initial Jobless Claims", "Beige Book"]
    assert week[0]["forecast"] == "222" and week[0]["local"] == "Wed 25 Nov 14:30"
    assert "economic_calendar" not in spx_snap.BASE_ENDPOINTS
