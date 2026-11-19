"""Implied Probability (OIPD) board, end to end: the nightly options build -> the board, no provider call.

Decision B (avo 10 Nov 2026): the board reads the stored chain from ``options.duckdb`` (``option_eod``) for the
names on the option watch list. The served file is seeded directly, as the 13F e2e seeds its ownership file: the
build is a CLI path the dashboard never runs. The chain is generated relative to ``date.today()`` because the
board's expiry window is DTE-based (1d-365d) and a frozen fixture would age out of range.
"""
from __future__ import annotations

import math
from datetime import date, timedelta

import numpy as np
import pytest

import duckdb

from RevenueChaser.module_oipd import opd_math

from .harness.shared import shared_dashboard

_SPOT = 100.0
_R = 0.04
_TICKER = "TST"
_TRUE = dict(a=0.02, b=0.12, rho=-0.5, m=0.0, sigma=0.15)


def _expiries():
    today = date.today()
    return [(today + timedelta(days=n)).isoformat() for n in (30, 60, 120)]


def _occ(expiry, cp, strike):
    return f"{_TICKER}{expiry[2:4]}{expiry[5:7]}{expiry[8:10]}{cp}{int(round(strike * 1000)):08d}"


def _contracts_for(expiry):
    d = (date.fromisoformat(expiry) - date.today()).days
    T = d / 365.0
    F = _SPOT * math.exp(_R * T)
    out = []
    for K in np.arange(round(_SPOT * 0.7), _SPOT * 1.31, _SPOT * 0.02):
        k = math.log(K / F)
        iv = math.sqrt(float(opd_math.svi_w(k, **_TRUE)) / T)
        for cp in ("C", "P"):
            price = opd_math.black76_price(F, K, T, _R, iv, cp)
            out.append({
                "option_symbol": _occ(expiry, cp, K),
                "nbbo_bid": round(price * 0.99, 4), "nbbo_ask": round(price * 1.01, 4),
                "last_price": round(price, 4), "implied_volatility": round(iv, 5),
                "open_interest": 100, "volume": 10, "delta": 0.5,
                "last_tape_time": "2026-09-23T20:00:00Z"})
    return out


def _seed(dashboard) -> date:
    """TST's chain and close in ``dashboard``'s options serving file, and TST on the option list.

    A plain function and not only a fixture: a module-scoped fixture that shares one dashboard across the
    read-only tests (#896) cannot request the function-scoped one.
    """
    from pathlib import Path

    from RevenueChaser.rcdata.build.options import tables

    market = Path(dashboard.env["RC_MARKET_DIR"])
    market.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(market / "options.duckdb"))
    try:
        for t in tables.TABLES.values():
            cols = ", ".join(f'"{c}" {typ}' for c, typ in t.schema)
            con.execute(f'CREATE TABLE IF NOT EXISTS "{t.name}" ({cols})')
        today = date.today()
        for e in _expiries():
            for c in _contracts_for(e):
                con.execute("INSERT INTO option_eod (session_date, ticker, option_symbol, expiry, nbbo_bid, nbbo_ask, "
                            "last_price, implied_volatility, open_interest, volume, delta, last_tape_time, fetched_at) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                            [today, _TICKER, c["option_symbol"], e, c["nbbo_bid"], c["nbbo_ask"], c["last_price"],
                             c["implied_volatility"], c["open_interest"], c["volume"], c["delta"],
                             c["last_tape_time"], 1.7e9])
        con.execute("INSERT INTO option_daily (session_date, ticker, close) VALUES (?, ?, ?)", [today, _TICKER, _SPOT])
    finally:
        con.close()
    r = dashboard.client.post(f"/api/watchlist/option/add/{_TICKER}", headers={"X-RC-Panel": "oipd"})
    assert r.status_code == 200, r.text
    return today


@pytest.fixture
def served(dashboard):
    """The seeded chain on this test's own dashboard; returns its session date."""
    return _seed(dashboard)


@pytest.fixture
def fetched(dashboard, served):
    result = dashboard.run_job("/run/module_oipd", ticker=_TICKER)
    assert result.ok, f"OIPD run failed: {result}\n{dashboard.logs()}"
    return result


SHARED = pytest.mark.xdist_group("e2e-oipd-shared-build")


@pytest.fixture(scope="module")
def _built_once(tmp_path_factory, mock_provider):
    """One dashboard, seeded and run once, for the read-only tests of ``TestFromTheBuild`` (#896).

    Measured on the 19 Nov 2026 e2e run: those five tests took 38.1 s. Each paid a dashboard boot (about 6.3 s,
    what an empty-store test costs end to end) and four of them also rebuilt the same three-expiry chain and ran
    the same fit. The Refresh and empty-state tests below keep the function-scoped ``dashboard``: they clear the
    cache, restart the subprocess, or need a store without this seed.
    """
    with shared_dashboard(tmp_path_factory, mock_provider, "oipd-shared") as dash:
        session = _seed(dash)
        result = dash.run_job("/run/module_oipd", ticker=_TICKER)
        yield dash, session, result


@pytest.fixture
def built(_built_once):
    dash, session, result = _built_once
    assert result.ok, f"OIPD run failed: {result}\n{dash.logs()}"
    return dash, session


class TestFromTheBuild:
    @SHARED
    def test_the_dashboard_serves_its_shell(self, built):
        dash, _ = built
        r = dash.get("/")
        assert r.status_code == 200
        assert "Implied Probability" in r.text

    @SHARED
    def test_the_run_writes_the_board_artifact(self, built):
        dash, _ = built
        assert dash.artifact("oipd_latest.html").exists()

    @SHARED
    def test_the_board_shows_the_fitted_ticker(self, built):
        dash, _ = built
        html = dash.view("module_oipd").text
        assert "Implied Probability" in html
        assert _TICKER in html
        assert "Risk-neutral" in html

    @SHARED
    def test_provenance_reports_the_chain_s_session(self, built):
        dash, session = built
        assert dash.data_as_of("module_oipd") == session.isoformat()

    @SHARED
    def test_the_board_writes_no_chain_of_its_own(self, built):
        dash, _ = built
        assert dash.table_count("oipd_chain") == 0


class TestRefreshIsOfflineAndFaithful:
    def test_refresh_rebuilds_a_deleted_artifact(self, dashboard, served, clear_cache):
        clear_cache()
        assert not dashboard.artifact("oipd_latest.html").exists()
        r = dashboard.view("module_oipd", refresh=True, ticker=_TICKER)
        assert r.status_code == 200
        assert "Implied Probability" in r.text

    def test_the_run_and_refresh_make_no_network_calls(self, dashboard, served, provider_routes, clear_cache):
        clear_cache()
        before = provider_routes.request_count
        assert dashboard.run_job("/run/module_oipd", ticker=_TICKER).ok
        r = dashboard.view("module_oipd", refresh=True, ticker=_TICKER)
        assert r.status_code == 200 and _TICKER in r.text
        assert provider_routes.request_count == before, (
            "the board reached the network: "
            f"{[q.path for q in provider_routes.requests()[before:]]}")

    def test_refresh_survives_a_restart(self, dashboard, served, clear_cache):
        clear_cache()
        dashboard.restart()
        r = dashboard.view("module_oipd", refresh=True, ticker=_TICKER)
        assert r.status_code == 200
        assert _TICKER in r.text


class TestEmptyStates:
    def test_a_name_off_the_list_says_so(self, dashboard, served):
        r = dashboard.view("module_oipd", refresh=True, ticker="ZZZ")
        assert r.status_code == 200
        assert "not on the option list" in r.text

    def test_a_listed_name_with_no_stored_chain_waits_for_the_build(self, dashboard):
        assert dashboard.client.post(f"/api/watchlist/option/add/{_TICKER}",
                                     headers={"X-RC-Panel": "oipd"}).status_code == 200
        r = dashboard.view("module_oipd", refresh=True, ticker=_TICKER)
        assert r.status_code == 200
        assert "No stored chain" in r.text
