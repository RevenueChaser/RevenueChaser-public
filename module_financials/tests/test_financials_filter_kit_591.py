"""The Financials board adopts the shared filter kit and the shared theme (#591).

Financials was the last board with a ticker box in the dashboard's header and a dark palette of its own. The
board now carries the kit's filter bar and its Ticker combobox, and reads the shared theme tokens, so it looks
and filters like every other board and follows the shell into Light.

The one rule that makes the bar honest here: **the filters narrow only what the picker offers.** Financials
shows one company at a time, so a filter must never slice the statements below.

Offline: the builder is handed a payload, the runner's pool is read from a temp DuckDB spine.
"""
from __future__ import annotations

import re

from RevenueChaser.module_financials import run as run_mod
from RevenueChaser.module_financials.reporting.html_builder import build_report_html
from RevenueChaser.rcdata.tests import universe_store

POOL = [
    {"ticker": "TEST", "name": "Test Industries Inc.", "market_cap": 1.1e11, "index": ["sp500"],
     "gics": ["Energy", "Oil & Gas E&P"], "theme_ids": [], "earnings_date": "2026-02-10"},
    {"ticker": "CROX", "name": "Crocs, Inc.", "market_cap": 5.1e9, "index": ["sp600"],
     "gics": ["Consumer Cyclical", "Footwear & Accessories"], "theme_ids": [], "earnings_date": "2026-02-12"},
]


def _html(financials, picker=None) -> str:
    results = {"ticker": "TEST", "financials": financials, "modules": {}, "warnings": []}
    if picker is not None:
        results["picker"] = picker
    return build_report_html(results)


# ── the kit is on the page ─────────────────────────────────────────────────────────────────────────────
def test_the_board_mounts_the_shared_bar_and_the_kits_picker(financials):
    html = _html(financials, {"rows": POOL, "meta": {"board": "financials"}})
    assert 'id="rc-filters"' in html and "RCFilters.mount" in html      # the shared bar
    assert 'id="ticker-combo"' in html and "RCCombobox.mount" in html   # the kit's combobox, not a bare box
    assert "rcfPass" in html or "RCF.pass" in html                      # the picker reads the bar's verdict


def test_the_pool_and_the_bars_meta_ride_the_page(financials):
    html = _html(financials, {"rows": POOL, "meta": {"board": "financials", "earnings_mode": "filter"}})
    assert "Crocs, Inc." in html and '"sp600"' in html
    assert '"board": "financials"' in html


def test_a_page_built_without_a_picker_payload_still_renders(financials):
    """A caller that hands no pool (a CLI report, an older payload) must not lose the board: the bar mounts
    over no rows and the picker offers none."""
    html = _html(financials)
    assert 'id="rc-filters"' in html and "DCF" in html
    assert "RC_PICKER_ROWS = []" in html


def test_the_filters_never_slice_the_statements(financials):
    """The point of the issue: an empty pool (or one that excludes the ticker) changes nothing below the bar."""
    from RevenueChaser.module_financials.engines.dcf_engine import run_dcf

    res = {"ticker": "TEST", "financials": financials, "warnings": [], "modules": {"dcf": run_dcf(financials)},
           "picker": {"rows": [], "meta": {"board": "financials"}}}
    html = build_report_html(res)
    assert "WACC" in html and "Per Share (Gordon)" in html
    assert "never slice the statements" in html      # the help box says so too


# ── the shared theme ───────────────────────────────────────────────────────────────────────────────────
def test_the_board_ships_the_shared_theme(financials):
    html = _html(financials, {"rows": POOL, "meta": {}})
    assert '--card-2' in html and 'data-theme="light"' in html   # THEME_CSS, both schemes
    assert "rcThemeApply" in html                                # THEME_JS


def test_the_board_keeps_no_palette_of_its_own():
    from pathlib import Path

    from RevenueChaser.module_financials.reporting import html_builder

    tpl = (Path(html_builder.__file__).resolve().parent / "templates" / "report_base.html.j2")
    own = tpl.read_text(encoding="utf-8").split("</style>")[0]
    literals = re.findall(r"#[0-9a-fA-F]{6}\b|rgba?\(", own)
    assert not literals, f"{sorted(set(literals))} should be theme tokens, not literals"


# ── the runner's pool ──────────────────────────────────────────────────────────────────────────────────
def _seed(rows):
    universe_store.replace([{
        "ticker": r["ticker"], "cik": "", "name": r.get("name") or r["ticker"], "market_cap": r["market_cap"],
        "price": 10.0, "sector": "Energy", "industry": "Oil & Gas E&P", "industry_group": None,
        "sub_industry": None, "quote": {"symbol": r["ticker"]}, "ggroup": None, "gind": None, "gsubind": None,
    } for r in rows])


def test_the_pool_is_the_boards_own_universe_cut(rawstore_tmp_db):
    _seed([{"ticker": "TEST", "market_cap": 1.1e11, "name": "Test Industries Inc."},
           {"ticker": "OIL1", "market_cap": 9.0e10}])
    got = run_mod.picker_payload("TEST")
    assert {r["ticker"] for r in got["rows"]} == {"TEST", "OIL1"}
    assert got["meta"]["board"] == "financials"
    row = next(r for r in got["rows"] if r["ticker"] == "TEST")
    assert row["name"] == "Test Industries Inc." and row["gics"] and "theme_ids" in row


def test_the_ticker_on_the_page_is_never_missing_from_its_own_picker(rawstore_tmp_db):
    """A name the cut drops (below the floor, an excluded type) is still the one the board is showing."""
    _seed([{"ticker": "OIL1", "market_cap": 9.0e10}])
    got = run_mod.picker_payload("tiny")
    assert got["rows"][0]["ticker"] == "TINY"


def test_an_empty_spine_gives_an_empty_pool_not_an_error(rawstore_tmp_db):
    universe_store.replace([])
    assert run_mod.picker_payload("")["rows"] == []
