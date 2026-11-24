"""A8 (Fable report review, 5 Nov 2026): the week's volatility calendar.

Since #1433 it is read from the market store's ``economic_event`` (TradingView and the Fed, else UW), not asked of UW
by the Fetch; an older raw day's ``economic_calendar.json`` still loads. The card lists the events from the board's day through the
target Friday, high-impact ones (CPI, the employment report, PPI, FOMC, PCE, GDP, retail sales) marked, times in
Europe/Amsterdam, duplicates dropped (UW repeats rows).
"""
from __future__ import annotations

import json

from revenuechaser.module_spx_gamma import normalize as nm, snapshot as snap, vol_calendar
from revenuechaser.module_spx_gamma.raw_day import load_raw_day

PAYLOAD = {"data": [
    {"type": "report", "time": "2026-11-06T13:30:00Z", "event": "Employment Report", "prev": "29000", "forecast": "55000"},
    {"type": "report", "time": "2026-11-06T13:30:00Z", "event": "Employment Report", "prev": "29000", "forecast": "55000"},
    {"type": "report", "time": "2026-11-05T13:30:00Z", "event": "Weekly Jobless Claims", "prev": "194000"},
    {"type": "fed-speaker", "time": "2026-11-06T14:10:00Z", "event": "Fed President Musalem speaks"},
    {"type": "report", "time": "2026-11-10T13:30:00Z", "event": "CPI, Y/Y%", "prev": "3.7%"},
    {"type": "report", "time": "2026-11-03T13:30:00Z", "event": "Old event"},
]}


def test_week_events_through_the_target_friday():
    rows = vol_calendar.week_events(PAYLOAD, "2026-11-04")       # target Friday 2026-11-06
    assert [r["event"] for r in rows] == ["Weekly Jobless Claims", "Employment Report",
                                          "Fed President Musalem speaks"]
    emp = rows[1]
    assert emp["high_impact"] is True and emp["local"] == "Fri 6 Nov 14:30"     # CET
    assert rows[0]["high_impact"] is False


def test_cpi_is_high_impact():
    rows = vol_calendar.week_events(PAYLOAD, "2026-11-09")        # target 2026-11-13
    assert rows[0]["event"] == "CPI, Y/Y%" and rows[0]["high_impact"] is True


def test_snapshot_and_raw_day(tmp_path):
    assert nm.normalize_snapshot({"economic_calendar": PAYLOAD}, "2026-11-04")["vol_calendar"][0]["event"] == \
        "Weekly Jobless Claims"
    from .conftest import store_day
    store_day("2026-11-04", {"effective_date": "2026-11-04"}, {"economic_calendar.json": PAYLOAD})
    assert load_raw_day("2026-11-04")["economic_calendar"] == PAYLOAD


def test_the_fetch_no_longer_asks_uw_for_the_calendar():
    """#1433: the week's calendar is the market store's (``store_reads.vol_calendar``), not a UW call of the Fetch."""
    assert "economic_calendar" not in snap.BASE_ENDPOINTS
    assert all(path != "/market/economic-calendar" for path, _ in snap.BASE_ENDPOINTS.values())


def test_a_refresh_keeps_the_pr415_files(tmp_path):
    """greek_flow.json and vix_greeks.json (PR 415) were written by the Fetch but not read back, so a Refresh
    dropped the vega flow and the VIX option book."""
    from .conftest import store_day
    store_day("2026-11-04", {"effective_date": "2026-11-04"},
              {f"{name}.json": {"data": [1]} for name in ("greek_flow", "vix_greeks")})
    raw = load_raw_day("2026-11-04")
    assert raw["greek_flow"] == {"data": [1]} and raw["vix_greeks"] == {"data": [1]}
