"""Implied Probability reads the nightly options build (decision B, avo 10 Nov 2026; F2, 18 Nov 2026): the names the
build stores a chain for, one session's chain from ``option_eod``, no provider call. The build is filled through the
UW mock at the HTTP boundary, as the options read tests do."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from RevenueChaser.core import calendar
from RevenueChaser.core.providers import unusual_whales
from RevenueChaser.module_oipd import config, engine
from RevenueChaser.module_watchlists import store as wl_store
from RevenueChaser.rcdata import read
from RevenueChaser.rcdata.build import base
from RevenueChaser.rcdata.build.options import uw_list, uw_screener
from .options_fixture import SESSION, UWOptions

AFTER_CLOSE = datetime(2026, 10, 26, 21, 0, tzinfo=timezone.utc)
NEXT = calendar.next_trading_day(SESSION)
LIQUID = {"call_volume": 400, "put_volume": 200, "total_open_interest": 5000, "call_premium": 80_000,
          "put_premium": 40_000}


@pytest.fixture(autouse=True)
def uw_env(monkeypatch):
    monkeypatch.setenv("UNUSUAL_WHALES_API_KEY", "test-key")
    monkeypatch.setattr(unusual_whales, "BASE", "https://uw.test/api")
    monkeypatch.setattr(unusual_whales, "_sleep", lambda s: None)
    monkeypatch.setattr(calendar, "_now", lambda: AFTER_CLOSE)


@pytest.fixture
def built(http_mock):
    """LIST on the option list (with SPX); GOOD reports the next session and passes the gates (the earnings set)."""
    mock = UWOptions()
    wl_store.job_set("option", "LIST", True, by="test")
    mock.calendar[(NEXT, "premarket")] = ["GOOD"]
    mock.screener["GOOD"] = dict(LIQUID)
    http_mock.add("uw.test/api", mock)
    for name in (uw_list.NAME, uw_screener.NAME):
        assert base.run_request({"dataset": name, "params": {}}, sleep=lambda s: None)["result"] != "failed"
    return mock


def test_the_names_are_spx_the_option_list_and_the_newest_earnings_set(built):
    assert engine.list_names() == ["GOOD", "LIST", "SPX"]


def test_the_board_fits_the_stored_chain_with_no_provider_call(built):
    before = len(built.requests)
    p = engine.build("LIST")
    assert len(built.requests) == before, "the board called Unusual Whales"
    assert p["ticker"] == "LIST" and p["asof"] == SESSION.isoformat()
    assert p["n_contracts"] == len(built.expiries) * len(built.strikes) * 2
    assert p["names"] == ["GOOD", "LIST", "SPX"] and p["fetched_at"]


def test_an_earnings_set_name_is_read_from_its_own_chain(built):
    p = engine.build("GOOD")
    assert p["asof"] == SESSION.isoformat() and p["n_contracts"] > 0
    assert p["spot"] == 101.5, "no list close for an earnings name: the price served with its spot exposures"


def test_a_name_off_the_list_is_named_not_fetched(built):
    before = len(built.requests)
    p = engine.build("ZZZ")
    assert "not on the option list" in p["error"] and p["expiries"] == []
    assert len(built.requests) == before


def test_an_unreadable_list_says_so_and_is_never_an_empty_board(monkeypatch):
    def boom(kind):
        raise read.JobListUnreadable("watchlists.duckdb: no such file")
    monkeypatch.setattr(read, "watched", boom)
    p = engine.build("SPY")
    assert "could not be read" in p["error"] and "no such file" in p["error"]


def test_a_listed_name_with_no_stored_chain_waits_for_the_build(monkeypatch):
    monkeypatch.setattr(read, "watched", lambda kind: {"SPY"})
    p = engine.build("SPY")
    assert "No stored chain for SPY" in p["error"]


def test_the_fit_takes_the_heaviest_expiries_1_to_365_days_out():
    asof = date(2026, 11, 17)

    def c(days, oi):
        return {"expiry": (asof + timedelta(days=days)).isoformat(), "open_interest": oi}
    chain = [c(0, 10**9), c(400, 10**9)] + [c(d, 100 * d) for d in range(1, 21)] + [c(20, 5)]
    got = sorted({x["expiry"] for x in engine.pick_expiries(chain, asof.isoformat())})
    assert got == [(asof + timedelta(days=d)).isoformat() for d in range(21 - config.MAX_EXPIRIES, 21)]
