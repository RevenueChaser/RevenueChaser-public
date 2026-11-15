"""Implied Probability: the picker pool is the typed universe, but a ticker outside it
(a fund, SPY, ...) can still be opened (#87, Identity R4)."""
from __future__ import annotations

import json

from RevenueChaser.rcdata.tests import universe_store
from RevenueChaser.core import rawstore
from RevenueChaser.core.tests.board_js import run_board_js
from RevenueChaser.module_oipd import engine, report








def test_the_page_is_on_the_shared_filter_kit(rawstore_tmp_db):
    """#383 C1b: the shared filter bar (rc_filters), then one combobox; the constants kit is gone."""
    html = report.render_oipd_dashboard(engine._empty_payload("AAA", "x"))
    assert '<section class="rcf-bar" id="rc-filters"></section>' in html
    assert "RCFilters.mount(" in html and "RCCombobox.mount(" in html
    assert html.index('id="rc-filters"') < html.index('id="ticker-combo"')
    for gone in ('id="mc-tabs"', 'id="eweek-tabs"', 'id="index-tabs"', 'id="sector"', "initTickerCombo",
                 "buildMcPills", "INDEX_LABELS", 'id="industry-group"', 'id="sub-industry"'):
        assert gone not in html, f"constants kit left: {gone}"


def test_the_filter_meta_comes_from_the_registry_and_the_pinned_themes(rawstore_tmp_db):
    html = report.render_oipd_dashboard(engine._empty_payload("AAA", "x"))
    meta = json.loads(html.split("var META = ", 1)[1].split(";\n", 1)[0])
    assert meta["board"] == "oipd" and meta["earnings_mode"] == "filter"
    assert meta["indexes"] == []                      # no spine here: the registry offers no index (#642 PR 6)
    assert meta["themes"] == {}                       # a fresh store has no pinned run




def test_the_ticker_combobox_lets_a_free_ticker_be_typed(rawstore_tmp_db):
    html = report.render_oipd_dashboard(engine._empty_payload("AAA", "x"))
    assert "allowFree: true" in html.split("RCCombobox.mount(", 1)[1].split("});", 1)[0]
    assert "clear: true" in html.split("RCCombobox.mount(", 1)[1].split("});", 1)[0]   # the × works






def test_the_sector_filter_narrows_the_picker_pool(rawstore_tmp_db, tmp_path):
    """#266 on the kit: the pool is filtered at either of the two sector levels."""
    universe_store.replace([
        {"ticker": t, "market_cap": 9e9, "name": t + " Inc", "price": 10.0, "sector": s, "industry": i,
         "quote": {"symbol": t}}
        for t, s, i in (("AAA", "Healthcare", "Biotechnology"), ("BBB", "Healthcare", "Medical Devices"),
                        ("CCC", "Technology", "Software - Application"))])
    html = report.render_oipd_dashboard(engine._empty_payload("AAA", "x"))
    got = run_board_js(html, """
function pool(){ return DATA.filter(pass).map(function(c){ return c.ticker; }); }
var log = {all: pool()};
RCF.set({gics: {key: "Healthcare", label: "Healthcare", level: 1}}); log.sector = pool();
RCF.set({gics: {key: "Healthcare›Biotechnology", label: "Biotechnology", level: 2}}); log.industry = pool();
console.log(JSON.stringify(log));
""", tmp_path)
    assert got == {"all": ["AAA", "BBB", "CCC"], "sector": ["AAA", "BBB"], "industry": ["AAA"]}
