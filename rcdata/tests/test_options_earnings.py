"""The earnings set of ``uw/option_screener``: once per name, on the evening before its report, every name that
passes the gates and is not on the option watch list. UW is mocked at the HTTP boundary."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from revenuechaser.core import calendar
from revenuechaser.core.providers import unusual_whales
from revenuechaser.rcdata import ops, serving
from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.options import names, tables, uw_screener
from revenuechaser.module_watchlists import store as wl_store

from .options_fixture import SESSION, UWOptions

AFTER_CLOSE = datetime(2026, 10, 26, 21, 0, tzinfo=timezone.utc)
NEXT = calendar.next_trading_day(SESSION)
LATER = calendar.next_trading_day(calendar.next_trading_day(NEXT))
LIQUID = {"call_volume": 400, "put_volume": 200, "total_open_interest": 5000, "call_premium": 80_000,
          "put_premium": 40_000}
THIN = {"call_volume": 10, "put_volume": 5, "total_open_interest": 30, "call_premium": 900, "put_premium": 400}
ER_PARTS = ("spot-exposures/strike", "gex-levels", "volatility/term-structure", "options-volume", "flow-recent")


@pytest.fixture(autouse=True)
def uw_env(monkeypatch):
    monkeypatch.setenv("UNUSUAL_WHALES_API_KEY", "test-key")
    monkeypatch.setattr(unusual_whales, "BASE", "https://uw.test/api")
    monkeypatch.setattr(unusual_whales, "_sleep", lambda s: None)
    monkeypatch.setattr(calendar, "_now", lambda: AFTER_CLOSE)


@pytest.fixture
def uw_opts(http_mock):
    mock = UWOptions()
    http_mock.add("uw.test/api", mock)
    return mock


def _daily():
    return base.run_request({"dataset": uw_screener.NAME, "params": {}})


def _query(sql: str, params=()):
    with serving.open_read("options") as con:
        return con.execute(sql, list(params)).fetchall()


def _fetched(uw_opts) -> set[str]:
    return {p.split("/")[2] for p, _ in uw_opts.calls("/stock/")}


def _setup(uw_opts, **who):
    """``who``: ticker -> (report day, screener fields)."""
    for t, (day, fields) in who.items():
        uw_opts.calendar.setdefault((day, "premarket"), []).append(t)
        uw_opts.screener[t] = dict(fields)


def test_a_name_that_passes_reports_next_session_and_is_not_on_the_list_is_fetched_once(uw_opts):
    _setup(uw_opts, GOOD=(NEXT, LIQUID))
    row = _daily()
    assert _fetched(uw_opts) == {"GOOD"}
    asked = [p.split("/", 3)[3] for p, _ in uw_opts.calls("/stock/GOOD/")]
    chain = ["expiry-breakdown"] + ["option-contracts"] * len(uw_opts.expiries)   # avo's F2: the chain, no greeks
    assert sorted(asked) == sorted([*ER_PARTS, *chain]), "spot exposures, GEX levels, term structure, volume, prints"
    assert [p for p, _ in uw_opts.calls("/earnings/GOOD")] == ["/earnings/GOOD"], "the tape, once"
    assert row["calls"] == (2 * len(uw_screener.report_days(SESSION)) + 1 + len(ER_PARTS) + len(chain)
                            + 1 + 1)   # tape, far
    assert _query("SELECT ticker, report_date, report_session, option_volume, total_open_interest, gamma_flip, "
                  "call_volume, prints FROM er_options") == [("GOOD", NEXT, "premarket", 600, 5000, 102.5, 600, 50)]
    uw_opts.requests.clear()
    _daily()
    assert uw_opts.calls("/stock/") == [], "once per name and evening"


def test_a_name_on_the_option_list_is_not_in_the_earnings_set(uw_opts):
    wl_store.job_set("option", "LISTED", True, by="test")
    _setup(uw_opts, LISTED=(NEXT, LIQUID), GOOD=(NEXT, LIQUID))
    _daily()
    assert _fetched(uw_opts) == {"GOOD"}
    assert [r[0] for r in _query("SELECT ticker FROM er_options")] == ["GOOD"]


def test_a_name_that_fails_the_gates_is_not_fetched(uw_opts):
    _setup(uw_opts, THIN=(NEXT, THIN))
    _daily()
    assert _fetched(uw_opts) == set() and _query("SELECT count(*) FROM er_options") == [(0,)]


def test_a_name_reporting_after_the_next_session_waits_for_its_evening(uw_opts):
    _setup(uw_opts, LATE=(LATER, LIQUID))
    _daily()
    assert _fetched(uw_opts) == set()


def test_the_earnings_rows_share_the_list_tables_marked_earnings(uw_opts):
    _setup(uw_opts, GOOD=(NEXT, LIQUID))
    _daily()
    assert _query("SELECT DISTINCT ticker, set_name FROM option_strike") == [("GOOD", "earnings")]
    assert _query("SELECT count(*), min(set_name) FROM option_print") == [(50, "earnings")]
    expiry = _query("SELECT set_name, volatility, call_gex FROM option_expiry ORDER BY expiry")
    assert expiry and all(r[0] == "earnings" and r[1] == 0.3 and r[2] is None for r in expiry), \
        "the term structure only: no greek exposure is asked for the earnings set"


def test_the_tape_is_one_row_per_report_of_the_name(uw_opts):
    """avo's D2 (10 Nov 2026): ``/earnings/{ticker}`` of an earnings-set name lands in ``earnings_tape``; a report
    UW lists twice is kept once."""
    _setup(uw_opts, GOOD=(NEXT, LIQUID))
    _daily()
    assert _query("SELECT ticker, report_date, report_time, actual_eps, street_mean_est, expected_move_perc, "
                  "post_earnings_move_1d, long_straddle_1d, report_source, session_date FROM earnings_tape "
                  "ORDER BY report_date") == [
        ("GOOD", date(2026, 4, 28), "postmarket", 2.45, 2.25, 0.0359, 0.0724, 0.2349, "company", SESSION),
        ("GOOD", date(2026, 7, 28), "postmarket", 2.45, 2.25, 0.0359, 0.0724, 0.2349, "company", SESSION)]


def test_the_earnings_set_rule_on_its_own():
    rows = [{"ticker": "GOOD", "report_date": NEXT, "passes_gates": True},
            {"ticker": "LISTED", "report_date": NEXT, "passes_gates": True},
            {"ticker": "THIN", "report_date": NEXT, "passes_gates": False},
            {"ticker": "SOON", "report_date": calendar.next_trading_day(NEXT), "passes_gates": True},
            {"ticker": "LATE", "report_date": LATER, "passes_gates": True},
            {"ticker": "SPX", "report_date": NEXT, "passes_gates": True}]
    got = names.earnings_set(SESSION, rows, on_list={"SPX", "LISTED"})
    assert [r["ticker"] for r in got] == ["GOOD", "SOON"]   # the next two report days (avo's D1), not the third


def test_the_check_names_the_earnings_set_of_the_evening(uw_opts):
    _setup(uw_opts, GOOD=(NEXT, LIQUID), MORE=(NEXT, LIQUID))
    uw_opts.fail["/stock/MORE/gex-levels"] = 500
    row = _daily()
    assert f"earnings set 1/2 for {NEXT}" in row["note"]
    assert row["next_check_due"] == SESSION.isoformat()
    uw_opts.fail.clear()
    row = _daily()
    assert f"earnings set 2/2 for {NEXT}" in row["note"] and row["next_check_due"] == NEXT.isoformat()
    assert set(tables.names_done(uw_screener.SOURCE, SESSION)) == {"GOOD", "MORE"}


def test_an_earnings_set_name_s_chain_lands_in_option_eod(uw_opts):
    """avo's F2 (18 Nov 2026): the Implied Probability board fits earnings-set names too, so their chain is stored
    like a list name's, without greeks."""
    _setup(uw_opts, GOOD=(NEXT, LIQUID))
    _daily()
    got = _query("SELECT ticker, count(*), count(DISTINCT expiry), min(nbbo_bid), max(charm) FROM option_eod "
                 "GROUP BY ticker")
    assert got == [("GOOD", len(uw_opts.expiries) * len(uw_opts.strikes) * 2, len(uw_opts.expiries), 1.1, None)]


def test_the_earnings_chain_takes_the_12_heaviest_expiries_1_to_365_days_out():
    def row(days, oi):
        return {"expires": (SESSION + timedelta(days=days)).isoformat(), "open_interest": oi}
    body = {"data": [row(0, 10**9), row(400, 10**9)] + [row(d, 100 * d) for d in range(1, 21)]}
    got = uw_screener.chain_expiries(body, SESSION)
    assert got == [SESSION + timedelta(days=d) for d in range(9, 21)], \
        "same-day and over a year out are left out; the 12 with the most open interest, by date"
    assert uw_screener.chain_expiries(None, SESSION) == []
