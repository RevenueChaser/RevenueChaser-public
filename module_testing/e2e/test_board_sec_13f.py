"""SEC 13F board, end to end.

Since G9 the numbers are the builder's: ``ownership.duckdb`` holds ``sec13f_ticker_period`` and
"/run/module_sec_13f" refreshes only what the dashboard owns — the UW names/sectors and shares outstanding — then
re-renders. It needs no Unusual Whales key (#206): the names/sectors step is best-effort and a rejected token only
leaves a note on the board. Fetch and Refresh make no SEC call at all, so there is no data-set page to mock: both
render whatever the ownership store holds.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import duckdb
import pytest

from . import harness
from .harness.shared import shared_dashboard, write_13f_totals

TOTALS = {
    "NVDA": {"2026-03-31": {"holders": 2100, "shares": 5_000_000, "value": 700_000_000},
             "2026-06-30": {"holders": 2250, "shares": 5_400_000, "value": 780_000_000}},
    "AMD": {"2026-03-31": {"holders": 1400, "shares": 3_100_000, "value": 400_000_000},
            "2026-06-30": {"holders": 1330, "shares": 2_900_000, "value": 370_000_000}},
}


def _rows(dashboard) -> list:
    """The board's rows from the payload route (#429); the page itself is chrome and scripts now."""
    r = dashboard.get("/view/module_sec_13f/payload.json")
    assert r.status_code == 200, r.text
    return r.json()["rows"]


def _tickers(dashboard) -> set:
    return {row[0] for row in _rows(dashboard)}


@pytest.fixture
def seeded_totals(serve_13f_totals):
    return serve_13f_totals(TOTALS)


SHARED = pytest.mark.xdist_group("e2e-sec13f-shared-fetch")


@pytest.fixture(scope="module")
def _served_once(tmp_path_factory, mock_provider):
    """One dashboard, seeded with ``TOTALS`` and refreshed once, for this file's read-only tests (#896).

    Measured on the 19 Nov 2026 e2e run: the four tests that only read the served board took 70.4 s, and a
    dashboard boot alone is about 6.3 s (what an empty-store test costs end to end). A test that changes the
    store, the routes or the cache in a way a later test could see keeps the function-scoped ``dashboard``:
    the Refresh, restart and empty-store tests below, and the off-spine test, which seeds different rows.
    """
    with shared_dashboard(tmp_path_factory, mock_provider, "sec13f-shared") as dash:
        write_13f_totals(dash, TOTALS)
        result = dash.run_job("/run/module_sec_13f")
        yield dash, result


@pytest.fixture
def served(_served_once):
    dash, result = _served_once
    assert result.ok, f"13F refresh failed: {result}\n{dash.logs()}"
    return dash




def _payload(dashboard) -> dict:
    r = dashboard.get("/view/module_sec_13f/payload.json")
    assert r.status_code == 200, r.text
    return r.json()


def _cells(dashboard, ticker) -> dict:
    payload = _payload(dashboard)
    return dict(zip(payload["cols"], next(r for r in payload["rows"] if r[0] == ticker)[3]))


class TestCredentials:
    """Neither 13F route is gated on the UW token: the served store is the board."""


    def test_refresh_renders_with_a_rejected_token(
            self, dashboard, dead_uw_token, seeded_totals, clear_cache):
        clear_cache()
        assert dashboard.view("module_sec_13f", refresh=True).status_code == 200
        assert "NVDA" in _tickers(dashboard)


class TestRenderAndRefresh:
    @SHARED
    def test_fetch_renders_the_served_totals(self, served):
        assert served.view("module_sec_13f").status_code == 200
        assert {"NVDA", "AMD"} <= _tickers(served)

    def test_refresh_makes_no_network_calls(self, dashboard, provider_routes,
                                            seeded_totals, clear_cache):
        assert dashboard.run_job("/run/module_sec_13f").ok
        clear_cache()
        before = provider_routes.request_count
        r = dashboard.view("module_sec_13f", refresh=True)
        assert r.status_code == 200
        assert provider_routes.request_count == before, (
            "refresh reached the network: "
            f"{[q.path for q in provider_routes.requests()[before:]]}")

    def test_refresh_still_shows_the_data(self, dashboard, seeded_totals, clear_cache):
        assert dashboard.run_job("/run/module_sec_13f").ok
        clear_cache()
        assert dashboard.view("module_sec_13f", refresh=True).status_code == 200
        assert "NVDA" in _tickers(dashboard)

    def test_refresh_survives_a_restart(self, dashboard, seeded_totals, clear_cache):
        assert dashboard.run_job("/run/module_sec_13f").ok
        clear_cache()
        dashboard.restart()
        assert dashboard.view("module_sec_13f", refresh=True).status_code == 200
        assert "NVDA" in _tickers(dashboard)


class TestEmptyStore:
    def test_no_totals_renders_an_empty_state_not_a_crash(self, dashboard):
        r = dashboard.view("module_sec_13f")
        assert r.status_code == 200




def _payload(dashboard) -> dict:
    r = dashboard.get("/view/module_sec_13f/payload.json")
    assert r.status_code == 200, r.text
    return r.json()


def _cells(dashboard, ticker) -> dict:
    payload = _payload(dashboard)
    return dict(zip(payload["cols"], next(r for r in payload["rows"] if r[0] == ticker)[3]))


class TestFilterKit:
    """#375 KF: the shared filter kit mounts on the 13F board and its rows/metadata ride the payload route."""

    @SHARED
    def test_render_includes_the_filter_bar(self, served):
        html = served.view("module_sec_13f").text
        assert '<section class="rcf-bar" id="rc-filters"></section>' in html

    @SHARED
    def test_payload_carries_filter_fields(self, served):
        payload = _payload(served)
        assert "fields" in payload
        for t in ("NVDA", "AMD"):
            assert t in payload["fields"], payload["fields"].keys()
            f = payload["fields"][t]
            assert set(f) >= {"ticker", "name", "index", "market_cap", "gics", "theme_ids"}

    def test_off_spine_tickers_are_unclassified(self, dashboard, serve_13f_totals):
        serve_13f_totals({**TOTALS, "FAKE999": {"2026-06-30": {"holders": 1, "shares": 100, "value": 1000}}})
        assert dashboard.run_job("/run/module_sec_13f").ok
        payload = _payload(dashboard)
        assert payload["fields"]["FAKE999"]["gics"][0] == "Unclassified"
        assert payload["fields"]["FAKE999"]["market_cap"] is None




# ── R7 review: the rows load in a real browser ───────────────────────────────────────────────────────────────────
# The payload route and the served markup above can both be right while the page itself shows nothing: the filter
# kit's script once rode outside any <script> tag, so ``RCFilters`` was undefined, ``build`` threw and no row was
# drawn. Headless Chrome (as in test_board_leaps.py) loads the served board and its payload from the dashboard.
def _chrome_path() -> str | None:
    override = os.environ.get("RC_CHROME")
    if override:
        return override if Path(override).exists() or shutil.which(override) else None
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if shutil.which(name):
            return shutil.which(name)
    return None


class TestRowsInTheBrowser:
    @SHARED
    def test_the_board_draws_its_rows_and_mounts_the_kit(self, served, tmp_path):
        chrome = _chrome_path()
        if chrome is None:
            msg = "no Chrome/Chromium for the 13F browser check: set RC_CHROME"
            if os.environ.get("CI", "").lower() == "true":
                pytest.fail(msg)
            pytest.skip(msg)
        out = subprocess.run(
            [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-first-run", "--disable-extensions",
             f"--user-data-dir={tmp_path / 'profile'}",
             "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
             "--virtual-time-budget=5000", "--dump-dom", served.url + "/view/module_sec_13f"],
            capture_output=True, text=True, encoding="utf-8", timeout=harness.CHROME_TIMEOUT_S)
        dom = out.stdout
        assert "<html" in dom.lower(), f"Chrome dumped no DOM (exit {out.returncode}): {out.stderr[-1500:]}"
        drawn = set(re.findall(r'<tr\b[^>]*\bdata-ticker="([^"]+)"', dom))
        assert {"NVDA", "AMD"} <= drawn, f"rows drawn: {sorted(drawn)}"
        assert "Loading rows" not in dom
        assert re.search(r'id="rc-filters"[^>]*>\s*<', dom), "the filter bar never mounted"
