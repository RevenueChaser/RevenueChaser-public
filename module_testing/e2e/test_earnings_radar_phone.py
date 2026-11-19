"""The Earnings Radar board on a phone, in a real browser against the real dashboard (#581).

The 25 Oct 2026 audit called this the worst board on a phone: about 2600 px wide with no breakpoint at all.
At avo's own screen (realme GT2 Pro, 412 px — ``harness/devices.py``) the page must never scroll sideways,
every row must stack into a card that prints its own column names, and every control the board owns must be
at least 44 px. On a desktop the table stays a table.

The rows come from one Fetch against the mock provider (demo values, not market data); the browser only reads
the page the dashboard already wrote, so nothing here starts a job or reaches a provider.
"""
from __future__ import annotations

import os

import pytest

from .harness.cdp_browser import Page, find_chrome
from .harness.devices import REALME_GT2_PRO
from .harness.shared import shared_dashboard

# The ``e2e`` marker comes from this tier's conftest; the routes are refreshed for every test.
pytestmark = pytest.mark.usefixtures("provider_routes")

DAY = "2026-08-12"           # an explicit Wednesday: no test reads today's date (AGENTS.md)
TAB = "module_earnings_radar"
DESKTOP = (1280, 800)
CALENDAR = {"data": [
    {"symbol": "NVDA", "sector": "Technology", "full_name": "NVIDIA Corp", "marketcap": "3000000000000",
     "expected_move_perc": "0.06", "street_mean_est": "1.2", "report_time": "premarket"},
    {"symbol": "AMD", "sector": "Technology", "full_name": "Advanced Micro Devices Inc",
     "marketcap": "250000000000", "expected_move_perc": "0.08", "street_mean_est": "0.9",
     "report_time": "premarket"},
]}


@pytest.fixture(scope="module")
def chrome():
    path = find_chrome()
    if path is None:
        msg = "no Chrome/Chromium for the Earnings Radar phone check: set RC_CHROME or install chromium"
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail(msg + " (a skip on CI would leave the check unenforced)")
        pytest.skip(msg)
    return path


@pytest.fixture
def browser(chrome):
    with Page(chrome) as page:
        yield page


@pytest.fixture(scope="module")
def board(tmp_path_factory, mock_provider):
    """One dashboard and one Fetch for the file; every test here only reads the written board."""
    with shared_dashboard(tmp_path_factory, mock_provider, "earnings-radar-phone") as dash:
        mock_provider.route("/api/earnings/premarket", payload=CALENDAR)
        result = dash.run_job("/run/earnings", start=DAY, end=DAY)
        assert result.ok, f"Earnings fetch failed: {result}\n{dash.logs()}"
        dash.wait_until_idle()
        assert "NVDA" in dash.view(TAB, refresh=True).text, "the Fetch wrote no rows to look at"
        yield dash


def _open(browser, board, size=None, device=REALME_GT2_PRO):
    if size is None:
        browser.emulate_device(device)
    else:
        browser.emulate(*size, scheme="dark")
    browser.open(f"{board.url}/view/{TAB}?refresh=1")
    browser.wait_for("document.querySelectorAll('tbody tr[data-ticker]').length > 0")
    browser.settle()


def test_the_page_never_scrolls_sideways_on_a_phone(board, browser):
    _open(browser, board)
    m = browser.eval("""(function(){ var vw = document.documentElement.clientWidth;
      var wide = Array.prototype.filter.call(document.querySelectorAll('body *'), function(e){
        return !(e instanceof SVGElement) && e.getBoundingClientRect().right > vw + 0.5; })
        .map(function(e){ return e.tagName + '.' + e.className; });
      return {vw: vw, scroll: document.documentElement.scrollWidth, wide: wide.slice(0, 8)}; })()""")
    assert m["vw"] == REALME_GT2_PRO.width
    assert m["scroll"] <= m["vw"], f"the page scrolls sideways: {m['wide']}"
    assert not m["wide"], f"elements reach past the right edge: {m['wide']}"


def test_every_row_is_a_full_width_card(board, browser):
    _open(browser, board)
    got = browser.eval("""(function(){ var vw = document.documentElement.clientWidth;
      var t = document.querySelector('table.data-table');
      var r = document.querySelector('tbody tr[data-ticker]');
      return {table: getComputedStyle(t).display, head: getComputedStyle(t.tHead).display,
              row: getComputedStyle(r).display, width: Math.round(r.getBoundingClientRect().width), vw: vw}; })()""")
    assert got["table"] == "block" and got["head"] == "none", got
    assert got["row"] == "grid", got
    assert got["width"] >= got["vw"] - 32, f"the card does not fill the screen: {got}"


def test_each_value_prints_its_own_column_name(board, browser):
    """A card has no header row: the label comes from ``data-label`` through ``::before``."""
    _open(browser, board)
    got = browser.eval("""(function(){ var r = document.querySelector('tbody tr[data-ticker]');
      var cells = Array.prototype.filter.call(r.querySelectorAll('td'), function(td){
        return getComputedStyle(td).display !== 'none'; });
      var missing = cells.filter(function(td){
        if (['ticker', 'name', 'sector'].indexOf(td.getAttribute('data-col')) >= 0) return false;
        return !td.getAttribute('data-label') ||
               getComputedStyle(td, '::before').content.indexOf(td.getAttribute('data-label')) < 0; })
        .map(function(td){ return td.getAttribute('data-col'); });
      return {n: cells.length, missing: missing}; })()""")
    assert got["n"] >= 8, got
    assert not got["missing"], f"values with no column name above them: {got['missing']}"


def test_the_board_controls_are_44_px_on_a_phone(board, browser):
    """The shared watch-list button keeps its 36 px (``reporting_common``, as on 13F and LEAPS)."""
    _open(browser, board)
    small = browser.eval("""(function(){ var out = [];
      document.querySelectorAll('summary, button, input').forEach(function(e){
        if (e.closest('.rc-watch') || e.closest('.rcf-bar')) return;
        var r = e.getBoundingClientRect(); if (!r.width) return;
        if (r.height < 44) out.push(e.tagName + '.' + e.className + ' ' + Math.round(r.width) + 'x' + Math.round(r.height)); });
      return out; })()""")
    assert not small, f"controls under 44 px: {small}"


def test_a_tapped_card_opens_the_drawer_over_the_page(board, browser):
    _open(browser, board)
    browser.eval("document.querySelector('tbody tr[data-ticker]').click()")
    browser.settle()
    got = browser.eval("""(function(){ var d = document.getElementById('drawer'), s = getComputedStyle(d);
      var r = d.getBoundingClientRect();
      return {open: d.classList.contains('open'), pos: s.position, display: s.display,
              width: Math.round(r.width), vw: document.documentElement.clientWidth,
              scroll: document.documentElement.scrollWidth}; })()""")
    assert got["open"] and got["pos"] == "fixed" and got["display"] == "block", got
    assert got["width"] == got["vw"], f"the drawer is not full width: {got}"
    assert got["scroll"] <= got["vw"], f"the open drawer scrolls the page sideways: {got}"


def test_the_table_stays_a_table_on_a_desktop(board, browser):
    _open(browser, board, size=DESKTOP)
    got = browser.eval("""(function(){ var t = document.querySelector('table.data-table');
      var d = document.getElementById('drawer');
      return {table: getComputedStyle(t).display, head: getComputedStyle(t.tHead).display,
              drawer: getComputedStyle(d).position}; })()""")
    assert got == {"table": "table", "head": "table-header-group", "drawer": "static"}, got
