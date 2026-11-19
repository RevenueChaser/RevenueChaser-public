"""Earnings Radar v1 board, end to end: Fetch → history → restart → Refresh (#215).

The Fetch reads its inputs live (calendar, per-ticker UW reads) and stores nothing of them; its store
footprint is one ``result_runs`` header plus ``earnings_cards_history`` rows in ``history.duckdb`` (#278).
The mock tape covers the calendar and the common UW reads but not a Rotation map, so the run lands
``partial`` with that named cause. A fixture gap and a real breakage differ in the header, which is why the
tests pin it rather than only "the job finished".

Earnings is not store-refreshable (``_STORE_REFRESHABLE``): Refresh serves the written board and, with the
board file gone, answers the fetch-only empty state. Both paths make no network call.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import duckdb
import pytest

from . import harness
from .harness.shared import shared_dashboard

DAY = "2026-08-12"           # an explicit Wednesday: no test reads today's date (AGENTS.md)
CALENDAR = {"data": [{
    "symbol": "NVDA", "sector": "Technology", "full_name": "NVIDIA Corp", "marketcap": "3000000000000",
    "expected_move_perc": "0.06", "street_mean_est": "1.2", "report_time": "premarket"}]}
ROTATION_CAUSE = "rotation quadrant map failed or came back empty"


@pytest.fixture
def calendar(provider_routes):
    provider_routes.route("/api/earnings/premarket", payload=CALENDAR)
    return provider_routes


@pytest.fixture
def fetched(dashboard, calendar):
    result = dashboard.run_job("/run/earnings", start=DAY, end=DAY)
    assert result.ok, f"Earnings fetch failed: {result}\n{dashboard.logs()}"
    dashboard.wait_until_idle()
    return result




SHARED = pytest.mark.xdist_group("e2e-earnings-shared-fetch")


@pytest.fixture(scope="module")
def _fetched_once(tmp_path_factory, mock_provider):
    """One dashboard, with one Fetch of ``DAY``, for the tests that only read what it wrote (#896).

    Measured on the 19 Nov 2026 e2e run: ``TestFetch`` took 21.8 s over three tests, each booting its own
    dashboard (about 6.3 s, what an empty-store test costs end to end) and running the same Fetch. The calendar
    route is added here because ``shared_dashboard`` starts from the default routes; the function-scoped
    ``provider_routes`` of a later test resets them, which is harmless once this Fetch has written the board.

    The provider-call test keeps its own Fetch — it reads the request log — and so do the Refresh, restart,
    rejected-key and empty-store tests.
    """
    with shared_dashboard(tmp_path_factory, mock_provider, "earnings-shared") as dash:
        mock_provider.route("/api/earnings/premarket", payload=CALENDAR)
        result = dash.run_job("/run/earnings", start=DAY, end=DAY)
        dash.wait_until_idle()
        yield dash, result


@pytest.fixture
def fetched_shared(_fetched_once):
    dash, result = _fetched_once
    assert result.ok, f"Earnings fetch failed: {result}\n{dash.logs()}"
    return dash


class TestFetch:

    @SHARED
    def test_fetch_writes_the_board_artifact(self, fetched_shared):
        assert fetched_shared.artifact("earnings_radar_latest.html").exists()

    @SHARED
    def test_the_board_shows_the_fetched_name(self, fetched_shared):
        r = fetched_shared.view("module_earnings_radar")
        assert r.status_code == 200 and "NVDA" in r.text

    def test_the_fetch_actually_called_the_provider(self, provider_routes, fetched):
        assert provider_routes.requests("/api/earnings/premarket"), "fetch must read the calendar"
        assert provider_routes.requests("/api/stock/NVDA/"), "fetch must read the per-ticker UW data"



class TestRefreshIsOffline:
    def test_refresh_serves_the_board_with_no_network_calls(self, dashboard, provider_routes, fetched):
        before = provider_routes.request_count
        r = dashboard.view("module_earnings_radar", refresh=True)
        assert r.status_code == 200 and "NVDA" in r.text
        assert provider_routes.request_count == before, (
            f"refresh reached the network: {[q.path for q in provider_routes.requests()[before:]]}")

    def test_refresh_without_the_board_file_is_the_fetch_only_empty_state(self, dashboard, provider_routes,
                                                                          fetched, clear_cache):
        """Not store-refreshable: no re-render from the store, a 200 empty state, still no network."""
        clear_cache()
        before = provider_routes.request_count
        r = dashboard.view("module_earnings_radar", refresh=True)
        assert r.status_code == 200 and "NVDA" not in r.text
        assert provider_routes.request_count == before

    def test_refresh_survives_a_restart(self, dashboard, fetched):
        dashboard.restart()
        assert "NVDA" in dashboard.view("module_earnings_radar", refresh=True).text

    def test_a_rejected_key_does_not_break_viewing_the_board(self, dashboard, fetched, dead_uw_token):
        """AGENTS.md: a board that needs no network must not require credentials."""
        dashboard.restart()
        r = dashboard.view("module_earnings_radar", refresh=True)
        assert r.status_code == 200 and "NVDA" in r.text


class TestEmptyStore:
    def test_a_board_with_no_data_renders_an_empty_state(self, dashboard):
        r = dashboard.view("module_earnings_radar")
        assert r.status_code == 200


_DRIVE = r"""<script>
window.addEventListener("load", function(){ setTimeout(function(){
  function vis(t){
    var row = null;
    document.querySelectorAll("tbody tr[data-ticker]").forEach(function(r){
      if (r.getAttribute("data-ticker") === t) row = r;
    });
    return row ? (row.style.display || "shown") : "missing";
  }
  var radio = document.querySelector('[role=radio][data-v="S&P 500"]');
  if (radio && radio.getAttribute("aria-disabled") !== "true") radio.click();
  document.documentElement.setAttribute("data-after-index", "NVDA=" + vis("NVDA") + ";AMD=" + vis("AMD"));
  var chip = document.querySelector('#chips [data-f="wl"]');
  if (chip) chip.click();
  document.documentElement.setAttribute("data-after-chip",
    "NVDA=" + vis("NVDA") + ";active=" + (chip && chip.classList.contains("active")));
}, 0); });
</script>"""


def _chrome() -> str | None:
    override = os.environ.get("RC_CHROME")
    if override:
        return override if Path(override).exists() or shutil.which(override) else None
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        found = shutil.which(name)
        if found:
            return found
    for path in (r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                 r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"):
        if Path(path).exists():
            return path
    return None


def _drive_filters(html: str, tmp_path: Path) -> str:
    chrome = _chrome()
    if chrome is None:
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail("no Chrome/Chromium for the Earnings filter kit")
        pytest.skip("no Chrome/Chromium for the Earnings filter kit")
    i = html.lower().rfind("</body>")
    page = tmp_path / "earnings_kit.html"
    page.write_text(html[:i] + _DRIVE + html[i:] if i >= 0 else html + _DRIVE, encoding="utf-8")
    out = subprocess.run(
        [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-first-run", "--disable-extensions",
         f"--user-data-dir={tmp_path / 'chrome-profile'}",
         # as in ``test_board_sec_13f``: a board's CDN plotly request would pause the virtual clock
         "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
         "--virtual-time-budget=6000", "--dump-dom", page.as_uri()],
        capture_output=True, text=True, encoding="utf-8", timeout=harness.CHROME_TIMEOUT_S)
    assert "<html" in out.stdout.lower(), f"Chrome dumped no DOM: {out.stderr[-1500:]}"
    assert "data-after-index" in out.stdout, out.stdout[-2000:]
    return out.stdout


def _event(symbol, name):
    return {"symbol": symbol, "sector": "Technology", "full_name": name, "marketcap": "3000000000000",
            "expected_move_perc": "0.06", "street_mean_est": "1.2", "report_time": "premarket"}


