"""The SPX Gamma board on a phone, in a real browser against the real dashboard.

Phone pass on the pilot board: at an exact 390 px viewport (device emulation, ``harness/cdp_browser.py``) the page
never scrolls sideways, every table stacks, every control inside the board is at least 44 px, the board follows the shell's theme (``data-theme``) in light and dark, and the charts fit their container.

The board is rendered from the module's fixture snapshot (demo values, not market data) and written where the
dashboard looks for the newest SPX report; nothing here starts a job or touches a provider.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from RevenueChaser.core import calendar as nyse_calendar
from RevenueChaser.core.reporting_common import THEME_TOKENS

from .harness.cdp_browser import Page, find_chrome
from .harness.shared import shared_dashboard

# The dashboard is shared by the file; the mock provider still gets its default routes back for every test, as
# the function-scoped dashboard had them.
pytestmark = pytest.mark.usefixtures("provider_routes")


def _rgb(hex_colour: str) -> str:
    """A ``#RRGGBB`` token as the ``rgb(r, g, b)`` the browser reports, so a theme pick moves no test (#761)."""
    v = hex_colour.lstrip("#")
    return "rgb({}, {}, {})".format(*(int(v[i:i + 2], 16) for i in (0, 2, 4)))

MAP_SHORT = "document.querySelector('.chart-map .main-svg').getBoundingClientRect().height <= 0.7 * innerHeight + 1"
PHONE = (390, 844)
DESKTOP = (1280, 800)
TAB = "module_spx_gamma"


@pytest.fixture(scope="module")
def chrome():
    path = find_chrome()
    if path is None:
        msg = "no Chrome/Chromium for the SPX phone check: set RC_CHROME or install google-chrome / chromium"
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
    """The demo board, rendered with its three charts and stored as the newest SPX report.

    One dashboard per xdist worker for this file, not one per test (#896: the file's 23 functions booted a
    dashboard each, 126 s of the e2e tier on 15 Nov 2026). Every test here only reads the page; a theme choice
    lives in the browser, whose profile stays fresh per test.
    """
    from RevenueChaser.module_spx_gamma.charts import position_map
    from RevenueChaser.module_spx_gamma.charts.tornado import build_tornado_fig
    from RevenueChaser.module_spx_gamma.render import render_html
    from RevenueChaser.module_spx_gamma.run import _export_chart as export
    from RevenueChaser.module_spx_gamma.tests.conftest import make_snapshot

    with shared_dashboard(tmp_path_factory, mock_provider, "spx-gamma-phone") as dash:
        root = Path(dash.env["SPX_GAMMA_DATA_ROOT"])
        charts = root.parent / "charts"
        charts.mkdir(exist_ok=True)
        with pytest.MonkeyPatch.context() as mp:
            mp.setattr(nyse_calendar, "in_us_session_window", lambda *a, **k: False)
            snap = make_snapshot()

            def frag(fig):
                # The real export path (run._export_chart), so a change to its to_html config is seen here.
                return export(fig, charts, "c", png=False)[2]

            html = render_html(snap, chart_html=frag(position_map.build(snap, include_tornado=False)),
                               tornado_html=frag(build_tornado_fig(snap)),
                               envelope_html=frag(position_map.build_envelope_fig(snap)))
        day = root / "reports" / "2026-08-14"
        day.mkdir(parents=True)
        (day / "section.html").write_text(html, encoding="utf-8")
        yield dash


def _open(browser, board, size, scheme="dark", theme="dark"):
    browser.emulate(*size, scheme=scheme)
    browser.open(f"{board.url}/view/{TAB}")
    browser.eval(f"document.documentElement.setAttribute('data-theme', {theme!r})")
    browser.wait_for("document.querySelectorAll('.js-plotly-plot .main-svg').length >= 3")
    # The mock rebuild (5 Nov 2026) put the position map, tornado and liquidity layer in a collapsed card; the
    # chart checks open it as a reader does (the page resizes the charts on the toggle).
    browser.eval("document.getElementById('g6b').open = true")
    browser.settle()


def test_the_page_never_scrolls_sideways_on_a_phone(board, browser):
    _open(browser, board, PHONE)
    m = browser.eval("""(function(){ var vw = document.documentElement.clientWidth;
      var wide = Array.prototype.filter.call(document.querySelectorAll('body *'), function(e){
        return !(e instanceof SVGElement) && e.getBoundingClientRect().right > vw + 0.5; })
        .map(function(e){ return e.tagName + '.' + e.className; });
      return {vw: vw, scroll: document.documentElement.scrollWidth, wide: wide.slice(0, 8)}; })()""")
    assert m["vw"] == PHONE[0]
    assert m["scroll"] <= m["vw"], f"the page scrolls sideways: {m['wide']}"
    assert not m["wide"], f"elements reach past the right edge: {m['wide']}"


def test_no_inline_minimum_width_is_left(board):
    html = next(Path(board.cache_dir).parent.glob("spx_gamma/reports/*/section.html")).read_text(encoding="utf-8")
    assert "min-width:900px" not in html and "min-width:1100px" not in html


def test_tables_stay_tables_on_a_desktop(board, browser):
    _open(browser, board, DESKTOP)
    assert browser.eval("Array.prototype.every.call(document.querySelectorAll('table'),"
                        " function(t){ return getComputedStyle(t).display === 'table'; })")
    assert browser.eval("document.documentElement.scrollWidth") <= DESKTOP[0]


@pytest.mark.parametrize("scheme", ["dark", "light"])
@pytest.mark.parametrize("theme", ["dark", "light", "auto"])
def test_the_board_follows_the_theme_in_both_device_schemes(board, browser, scheme, theme):
    _open(browser, board, PHONE, scheme, theme)
    expected = theme if theme != "auto" else scheme
    bg = browser.eval("getComputedStyle(document.body).backgroundColor")
    v = THEME_TOKENS[expected]["bg"].lstrip("#")
    assert bg == "rgb({}, {}, {})".format(*(int(v[i:i + 2], 16) for i in (0, 2, 4))), f"{theme}/{scheme}: {bg}"


CONTRAST = r"""(function(){
  // Chromium reports a color-mix() colour as color(srgb 0.2 0.8 0.6 / 0.16), not rgb(): read both, and say so
  // when a colour is neither, instead of skipping it (#195 review MUST 2).
  var unparsed = [];
  function parse(c){ var m = c.match(/^rgba?\(([^)]+)\)/), k = 1;
    if(!m){ m = c.match(/^color\(srgb ([^)]+)\)/); k = 255; }
    if(!m){ if(c !== 'transparent') unparsed.push(c); return null; }
    var p = m[1].split(/[ ,\/]+/).filter(Boolean).map(Number);
    return {r: p[0] * k, g: p[1] * k, b: p[2] * k, a: p.length > 3 ? p[3] : 1}; }
  function over(top, base){ var a = top.a; return {r: top.r * a + base.r * (1 - a), g: top.g * a + base.g * (1 - a),
    b: top.b * a + base.b * (1 - a), a: 1}; }
  function lum(c){ function f(v){ v /= 255; return v <= .03928 ? v / 12.92 : Math.pow((v + .055) / 1.055, 2.4); }
    return .2126 * f(c.r) + .7152 * f(c.g) + .0722 * f(c.b); }
  function bgOf(e){ var stack = []; for(var n = e; n; n = n.parentElement){ var c = parse(getComputedStyle(n).backgroundColor);
      if(c && c.a > 0){ stack.push(c); if(c.a === 1) break; } }
    var base = {r: 0, g: 0, b: 0, a: 1}; var cs = getComputedStyle(document.documentElement).backgroundColor;
    base = parse(getComputedStyle(document.body).backgroundColor) || base;
    for(var i = stack.length - 1; i >= 0; i--) base = over(stack[i], base); return base; }
  var worst = [];
  document.querySelectorAll('body *').forEach(function(e){
    if(e instanceof SVGElement || e.closest('.js-plotly-plot') || e.closest('thead')) return;
    var own = Array.prototype.some.call(e.childNodes, function(n){ return n.nodeType === 3 && n.textContent.trim(); });
    var r = e.getBoundingClientRect(); if(!own || !r.width || !r.height || getComputedStyle(e).visibility === 'hidden') return;
    var fg = parse(getComputedStyle(e).color), bg = bgOf(e); if(!fg) return;
    fg = over(fg, bg); var l1 = lum(fg), l2 = lum(bg), ratio = (Math.max(l1, l2) + .05) / (Math.min(l1, l2) + .05);
    if(ratio < 4.5) worst.push(e.tagName + '.' + e.className + ' ' + ratio.toFixed(2) + ' ' + e.textContent.trim().slice(0, 24)); });
  return worst.concat(unparsed.map(function(c){ return 'unparsed colour ' + c; })); })()"""


@pytest.mark.parametrize("theme", ["dark", "light"])
def test_text_has_4_5_to_1_contrast_in_both_themes(board, browser, theme):
    _open(browser, board, PHONE, theme, theme)
    browser.eval("document.querySelectorAll('details.collapsible').forEach(function(d){ d.open = true; })")
    low = browser.eval(CONTRAST)
    assert not low, f"{theme}: text under 4.5:1: {low[:10]}"


def test_the_board_controls_are_44_px_on_a_phone(board, browser):
    _open(browser, board, PHONE)
    small = browser.eval("""(function(){ var out = [];
      document.querySelectorAll('summary, button, a[href], input, select').forEach(function(e){
        if(e.closest('.modebar')) return; var r = e.getBoundingClientRect(); if(!r.width) return;
        if(r.height < 44 || r.width < 44) out.push(e.tagName + '.' + e.className + ' ' + Math.round(r.width) + 'x' + Math.round(r.height)); });
      return out; })()""")
    assert not small, f"controls under 44 px: {small}"


def test_a_focused_summary_shows_a_focus_ring(board, browser):
    _open(browser, board, PHONE)
    browser.eval("document.querySelector('details.collapsible > summary').focus()")
    browser.press("Tab")
    browser.press("Tab", shift=True)
    ring = browser.eval("getComputedStyle(document.activeElement).outlineStyle")
    assert ring != "none", "keyboard focus on a summary is invisible"


@pytest.mark.parametrize("size", [PHONE, DESKTOP])
def test_the_charts_fit_their_container(board, browser, size):
    _open(browser, board, size)
    if size == PHONE:
        browser.wait_for(MAP_SHORT)
    got = browser.eval("""(function(){ return Array.prototype.map.call(document.querySelectorAll('.chart'), function(c){
      var g = c.querySelector('.js-plotly-plot'); var s = g.querySelector('.main-svg').getBoundingClientRect();
      var plot = g.layout.margin; return {box: c.getBoundingClientRect().width, svg: s.width, graph: g.getBoundingClientRect().width,
        h: g.getBoundingClientRect().height, vh: window.innerHeight, mr: plot.r, auto: g.layout.autosize}; }); })()""")
    assert len(got) == 3
    for c in got:
        assert c["svg"] <= c["box"] + 1 and c["graph"] <= c["box"] + 1, c
        assert c["auto"] is True, c
    if size == PHONE:
        browser.wait_for(MAP_SHORT)
        got[0]["mr"] = browser.eval("document.querySelector('.js-plotly-plot').layout.margin.r")
        assert all(c["mr"] <= 16 for c in got[:1]), f"the position map keeps its desktop margin: {got[0]}"
        assert got[0]["h"] <= 0.7 * got[0]["vh"] + 1, got[0]


# ── PR #195 review: the map's height, inside the shell and on a phone ──
FRAME_READY = ("(function(){ var f = document.querySelector('.frame.on'); try {"
               " return !!(f && f.getAttribute('src') && f.contentDocument.readyState === 'complete'"
               " && f.contentDocument.location.href !== 'about:blank'"
               " && f.contentDocument.querySelectorAll('.js-plotly-plot .main-svg').length >= 3); } catch (e) { return false; } })()")
FRAME_CHARTS = ("Array.prototype.map.call(document.querySelector('.frame.on').contentDocument.querySelectorAll('.chart'),"
                " function(c){ return Math.round(c.querySelector('.js-plotly-plot').getBoundingClientRect().height); })")


def test_the_position_map_is_700_px_tall_on_a_desktop_inside_the_shell(board, browser):
    """#195 review MUST 1: min(700px, 70vh) made the map 486 px in the shell at 1280x800."""
    browser.emulate(*DESKTOP, scheme="dark")
    browser.open(f"{board.url}/#{TAB}", ready=FRAME_READY)
    browser.eval("document.querySelector('.frame.on').contentDocument.getElementById('g6b').open = true")
    browser.wait_for(f"JSON.stringify({FRAME_CHARTS}) === '[700,460,460]'", timeout=8)
    assert browser.eval(FRAME_CHARTS) == [700, 460, 460]


FIRST_THEME = """(function(){ new MutationObserver(function(_, o){
  var t = document.documentElement.getAttribute('data-theme');
  if(t && !window.__first){ window.__first = {theme: t, body: !!document.body}; o.disconnect(); }
}).observe(document, {attributes: true, subtree: true}); })()"""


def _stored_theme(browser, board, choice, scheme="dark"):
    browser.emulate(*PHONE, scheme=scheme)
    browser.open(f"{board.url}/view/{TAB}")
    browser.eval(f"localStorage.setItem('rc-theme', {choice!r})")
    browser.send("Page.addScriptToEvaluateOnNewDocument", source=FIRST_THEME)
    browser.open(f"{board.url}/view/{TAB}")


@pytest.mark.parametrize("choice", ["light", "auto"])
def test_a_board_opened_directly_reads_the_stored_theme_before_it_paints(board, browser, choice):
    """#195 review SHOULD 2: opened directly, the board ignored rc-theme and was always dark; in the shell it
    painted dark first. The board's own head script applies the choice, before the body exists."""
    _stored_theme(browser, board, choice, scheme="light")
    first = browser.eval("window.__first")
    assert first == {"theme": choice, "body": False}, first
    bg = browser.eval("getComputedStyle(document.body).backgroundColor")
    assert bg == _rgb(THEME_TOKENS["light"]["bg"]), bg


def test_no_stored_theme_is_dark_on_a_light_device(board, browser):
    browser.emulate(*PHONE, scheme="light")
    browser.open(f"{board.url}/view/{TAB}")
    assert browser.eval("document.documentElement.getAttribute('data-theme')") == "dark"
    assert browser.eval("getComputedStyle(document.body).backgroundColor") == _rgb(THEME_TOKENS["dark"]["bg"])


# ── #195 review SHOULD 3: tests that guarded nothing, now pinned to the rule they name ──
def test_the_boards_own_focus_rule_draws_the_ring(board, browser):
    """The browser's default outline (style auto) is not this board's :focus-visible rule."""
    _open(browser, board, PHONE)
    browser.eval("document.body.focus()")
    browser.press("Tab")
    ring = browser.eval("(function(){ var a = document.activeElement, s = getComputedStyle(a);"
                        " return [a.tagName, s.outlineStyle, s.outlineWidth, a.matches(':focus-visible')]; })()")
    assert ring[3] is True and ring[1] == "solid" and ring[2] == "2px", ring


def test_the_iron_butterfly_legs_do_not_scroll_on_a_phone(board, browser):
    over = "getComputedStyle(document.querySelector('.ib-legs')).overflowX"
    _open(browser, board, PHONE)
    assert browser.eval(over) == "visible"
    _open(browser, board, DESKTOP)
    assert browser.eval(over) == "auto"


# ── #195 review SHOULD 4: phone readability ──
def test_collapsed_sections_open_for_print_and_close_again(board, browser):
    """#195 review SHOULD 6: nothing opened the <details> for a printout, so Details, How to read, the
    Walkthrough and the glossary were left out of it."""
    _open(browser, board, PHONE)
    state = "Array.prototype.map.call(document.querySelectorAll('details.collapsible'), function(d){ return d.open; })"
    before = browser.eval(state)
    assert not all(before) and any(not o for o in before)
    browser.eval("window.dispatchEvent(new Event('beforeprint'))")
    assert all(browser.eval(state)), "a section stays closed in the printout"
    browser.eval("window.dispatchEvent(new Event('afterprint'))")
    assert browser.eval(state) == before, "the sections the reader had open or closed are restored"


# ── #195 review NITs ──
def test_cards_use_the_mocks_radii(board, browser):
    """The mock: an 8 px card, a 6 px block inside it (trade, scenario, step)."""
    _open(browser, board, DESKTOP)
    radii = browser.eval("['.card', '.trade', '.sc', '.step'].map(function(q){"
                         " return getComputedStyle(document.querySelector(q)).borderTopLeftRadius; })")
    assert radii == ["8px", "6px", "6px", "6px"], radii

