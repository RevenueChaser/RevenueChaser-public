"""The LEAPS board (#746): one session of ``option_far_contract``, drawn from the read API with no fetch.

The store is filled the real way, by the ``uw/far_contracts`` dataset against UW mocked at the HTTP boundary (the
same helpers as ``rcdata/tests/test_options_far_contracts.py``): an evening sweep, then the next morning's chains.
"""
from __future__ import annotations

import json
import re
from datetime import date

import pytest

from RevenueChaser.core import calendar
from RevenueChaser.core.providers import unusual_whales
from RevenueChaser.module_leaps import board
from RevenueChaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401
from RevenueChaser.rcdata.tests.options_fixture import SESSION, UWOptions
from RevenueChaser.rcdata.tests.test_options_far_contracts import (AFTER_CLOSE, MORNING, _swept, at, chain_row,
                                                                   contract)


@pytest.fixture(autouse=True)
def uw_env(monkeypatch):
    monkeypatch.setenv("UNUSUAL_WHALES_API_KEY", "test-key")
    monkeypatch.setattr(unusual_whales, "BASE", "https://uw.test/api")
    monkeypatch.setattr(unusual_whales, "_sleep", lambda s: None)
    at(monkeypatch, AFTER_CLOSE)


@pytest.fixture
def stored(http_mock, monkeypatch):
    """One session: NVDA's roll (closing C100 2027, opening C110 2029), a put, an ETF, an index and a stale call."""
    uw = UWOptions()
    http_mock.add("uw.test/api", uw)
    near = contract("NVDA", "C", 100, volume=3000, oi=15725, premium="900000.00", expiry=date(2027, 12, 17))
    far = contract("NVDA", "C", 110, volume=3000, oi=130, premium="2500000.00", expiry=date(2029, 1, 19))
    put = contract("AAA", "P", 40, volume=500, oi=1000, premium="60000.00")
    etf = contract("SPY", "C", 700, volume=800, oi=50, premium="400000.00", issue_type="ETF")
    idx = contract("SPX", "P", 5000, volume=100, oi=10, premium="1200000.00", issue_type="Index")
    stale = contract("BBB", "C", 50, volume=200, oi=10, premium="55000.00")
    _swept(uw, [near, far, put, etf, idx, stale])
    uw.far_chain = {"NVDA": [chain_row(near, oi=14567), chain_row(far, oi=3584)],
                    "AAA": [chain_row(put, oi=1300)], "SPY": [chain_row(etf, oi=850)],
                    "SPX": [chain_row(idx, oi=60)], "BBB": [chain_row(stale, oi=60, prev_oi=11)]}
    at(monkeypatch, MORNING)
    from RevenueChaser.rcdata.build import base
    from RevenueChaser.rcdata.build.options import uw_far_contracts as far_ds
    assert base.run_request({"dataset": far_ds.NAME, "params": {}})["result"] != "failed"
    return {"near": near, "far": far, "put": put, "etf": etf, "idx": idx, "stale": stale}


def _data_of(page: str) -> dict:
    m = re.search(r"var LP_DATA = (\{.*?\});\n", page, re.S)
    assert m, "the page carries its session as LP_DATA"
    return json.loads(m.group(1).replace("\\u003c", "<"))


# ── Pure helpers ───────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("ticker, issue_type, want", [
    ("NVDA", "Common Stock", "stocks"), ("SPY", "ETF", "etfs"), ("SPX", "Index", "index"),
    ("SPXW", None, "index"), ("VIX", "Common Stock", "index"), ("ABC", None, "stocks"), ("QQQ", "etf", "etfs")])
def test_each_contract_falls_in_one_of_three_groups(ticker, issue_type, want):
    assert board.product_of(ticker, issue_type) == want


def test_a_roll_partner_is_named_short_enough_for_a_chip():
    assert board.partner_label("NVDA271217C00100000") == "C100 Dec 2027"
    assert board.partner_label("SPXW290119P05012500") == "P5,012.5 Jan 2029"
    assert board.partner_label("not-an-occ") == "not-an-occ"


def test_a_session_parameter_is_a_date_or_nothing():
    assert board.parse_session("2026-10-26") == date(2026, 10, 26)
    assert board.parse_session("26 Oct") is None and board.parse_session(None) is None


# ── The payload, from the real table ───────────────────────────────────────────────────────────────────────────

def test_nothing_stored_is_no_payload():
    assert board.payload() is None


def test_one_stored_session_is_collecting_with_its_counts(stored):
    data = board.payload()
    assert data["session"] == SESSION.isoformat()
    assert (data["stored"], data["min_sessions"], data["collecting"]) == (1, 20, True)
    assert data["counts"] == {"contracts": 6, "names": 5, "matched": 5, "pending": 0, "stale": 1}
    assert [r["t"] for r in data["rows"]] == ["NVDA", "SPX", "NVDA", "SPY", "AAA", "BBB"], "premium, largest first"


def test_a_row_carries_what_the_card_draws(stored):
    rows = {r["sym"]: r for r in board.payload()["rows"]}
    far = rows[stored["far"]["option_symbol"]]
    assert far["con"] == "Call 110 · 19 Jan 2029" and far["side"] == "C" and far["prod"] == "stocks"
    assert (far["prem"], far["vol"], far["oi"], far["next"], far["chg"]) == (2_500_000.0, 3000, 130, 3584, 3454)
    assert far["st"] == "matched" and far["share"] == pytest.approx(1.1513, abs=1e-4) and far["out"] is True
    assert far["roll"] == "C100 Dec 2027"
    near = rows[stored["near"]["option_symbol"]]
    assert near["share"] == pytest.approx(-0.386, abs=1e-3) and near["out"] is False and near["roll"] == "C110 Jan 2029"
    assert rows[stored["stale"]["option_symbol"]]["st"] == "stale"
    assert rows[stored["stale"]["option_symbol"]]["share"] is None
    assert rows[stored["etf"]["option_symbol"]]["prod"] == "etfs"
    assert rows[stored["idx"]["option_symbol"]]["prod"] == "index"
    assert rows[stored["put"]["option_symbol"]]["con"].startswith("Put 40 · ")


def test_an_unknown_session_falls_back_to_the_newest(stored):
    assert board.payload(date(2020, 1, 2))["session"] == SESSION.isoformat()
    assert board.payload(SESSION)["session"] == SESSION.isoformat()


# ── The page ───────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_page_says_collecting_and_carries_the_session(stored):
    page = board.render_html(board.payload())
    assert "Collecting" in page and "1 / 20 sessions" in page
    assert f'<option value="{SESSION.isoformat()}" selected>' in page
    assert _data_of(page)["rows"][0]["t"] == "NVDA"
    assert 'rcWatchInit("leaps");' in page, "the shared watch-list pair, under the board's old panel name"
    assert "Sort: opened share" not in page, "while collecting nothing is ranked by the measure"
    for word in ("Accumulat", "conviction", "Tier"):
        assert word not in page, "a measurement, not a label"


def test_the_page_uses_the_theme_tokens_and_no_palette_of_its_own(stored):
    page = board.render_html(board.payload())
    css = page[page.index("<style>"):page.index("</style>")]
    own = css[css.index("body{margin:0"):]
    assert not re.search(r"#[0-9A-Fa-f]{3,8}\b", own), "colours come from THEME_CSS by name"
    assert "var(--data-1" in own and "var(--accent" in own and "var(--amber" in own


def test_a_hostile_ticker_cannot_close_the_script(stored, monkeypatch):
    data = board.payload()
    data["rows"][0]["t"] = "</script><img src=x onerror=alert(1)>"
    page = board.render_html(data)
    assert "</script><img" not in page


# ── The tab ────────────────────────────────────────────────────────────────────────────────────────────────────

def test_the_tab_serves_the_board_once_a_session_is_stored(stored):
    from RevenueChaser.app import dashboard
    c = dashboard.app.test_client()
    body = c.get("/view/module_leaps").get_data(as_text=True)
    assert "No data yet" not in body and "1 / 20 sessions" in body
    assert _data_of(body)["session"] == SESSION.isoformat()
    picked = c.get("/view/module_leaps?session=not-a-date").get_data(as_text=True)
    assert _data_of(picked)["session"] == SESSION.isoformat(), "an unknown session shows the newest"


def test_after_twenty_tested_sessions_the_board_stops_collecting_and_offers_the_share_sort(stored):
    data = dict(board.payload(), stored=20, collecting=False, tested=True)
    page = board.render_html(data)
    assert "Collecting" not in page and "20 sessions stored." in page and "Sort: opened share" in page


def test_twenty_sessions_not_yet_tested_offer_no_share_sort(stored):
    """The measure is collected, not yet tested (#746 step 6): nothing is ranked by it."""
    assert board.TESTED is False and board.payload()["tested"] is False
    page = board.render_html(dict(board.payload(), stored=20, collecting=False))
    assert "Collecting" not in page and "Sort: opened share" not in page
    assert "20 sessions stored, not tested yet" in page, "stored is not tested: the banner keeps saying so"


def test_a_session_with_no_open_interest_read_does_not_count_as_stored(monkeypatch):
    """A sweep waiting for its open interest, or a read that all went stale, holds no opened share."""
    from datetime import date as d
    sessions = [dict(session_date=d(2026, 11, 17), contracts=3, tickers=2, matched=0, pending=3, stale=0, missing=0),
                dict(session_date=d(2026, 11, 16), contracts=3, tickers=2, matched=0, pending=0, stale=3, missing=0),
                dict(session_date=d(2026, 11, 13), contracts=3, tickers=2, matched=2, pending=0, stale=1, missing=0)]
    monkeypatch.setattr(board.read, "far_contract_sessions", lambda: sessions)
    monkeypatch.setattr(board.read, "far_contracts", lambda *_a, **_k: [])
    data = board.payload()
    assert (data["stored"], data["collecting"], len(data["sessions"])) == (1, True, 3)


def test_the_counts_say_how_many_wait_for_their_open_interest(stored):
    data = board.payload()
    data["counts"] = dict(data["counts"], matched=0, pending=6, stale=0)
    page = board.render_html(data)
    assert "waiting for open interest" in page and "stale or missing" in page, "a partial read keeps both counts"
    assert "waiting for open interest" not in board.render_html(board.payload()), "shown only while some wait"


# ── Layout and sort rules (review round 2: F3, M4, M5) ─────────────────────────────────────────────────────────

def _wide_css() -> str:
    return board._CSS[board._CSS.index("@media (min-width:900px)"):]


def test_the_product_buttons_are_44_px_touch_targets():
    assert ".lp-seg button{min-height:var(--touch);" in board._CSS and ".lp-seg button{min-height:40px" not in board._CSS


def test_the_wide_row_aligns_each_cell_by_where_it_stands():
    """rules/ui-design.md cell grid: Watch (leftmost) left, the middle cells centred, Flags (rightmost) right."""
    wide = _wide_css()
    assert ".lp-head>:first-child{text-align:left}.lp-head>:last-child{text-align:right}" in wide
    assert "text-align:center}" in wide[wide.index(".lp-head{font-size"):wide.index(".lp-head>:first-child")]
    assert "justify-content:center" in wide[wide.index("  .c-n{flex-direction:row"):]
    assert ".c-p{text-align:center}" in wide and ".c-x div{align-items:center}" in wide
    assert ".c-f{grid-area:f;justify-content:flex-end}" in wide
    assert "align-items:flex-end" not in wide and ".lp-head .r{" not in wide


def test_the_wide_row_keeps_the_stat_names_for_screen_readers():
    """The header row is aria-hidden, so each cell's name is only hidden from sight, never display:none."""
    wide = _wide_css()
    assert "small{display:none}" not in wide and ".lab{display:none}" not in wide
    assert ".ct .sh .lab,.c-x small{position:absolute;width:1px;height:1px;" in wide


def test_the_open_interest_sort_puts_the_largest_rise_first(stored):
    assert "-r.chg;" in board._JS and "Math.abs(r.chg)" not in board._JS, "signed change, not its size"
    page = board.render_html(board.payload())
    assert '<option value="change">Sort: open interest rise</option>' in page


# ── Review 18 Nov 2026: R3, R6/R11 and R8 ────────────────────────────────────────────────────────────

def test_the_help_gives_the_builder_s_causes_for_beyond_one():
    """R3: the builder names an exercise, an adjustment or a data error; the help no longer guesses a cause."""
    assert "an exercise, an adjustment or a data error" in board.HELP
    assert "settled into it" not in board.HELP


def test_a_matched_row_with_no_next_open_interest_says_not_read_not_no_volume():
    """R8: "No volume" only when the next open interest was read; an unread one has its own note."""
    assert "Open interest not read" in board._JS
    assert "r.next == null ? 'unread' : 'noshare'" in board._JS


def test_the_counts_follow_the_rows_listed(stored):
    """R6/R11: the counts line and the product counts are redrawn from the rows of the picked product and side."""
    page = board.render_html(board.payload())
    assert '<div class="lp-counts" id="lp-counts">' in page
    assert "lpCounts(rows);" in board._JS and "if(lpSided(r)) LP_COUNT[r.prod]" in board._JS
