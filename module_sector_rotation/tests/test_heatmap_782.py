"""The stock heatmap of the Sector Rotation board (#782; avo's decisions on the mock, 18 Nov 2026).

The payload is built from the shared universe (names, sectors, caps), the S&P 500 membership, avo's watch lists and
the stored closes; the page draws the treemap from it. These tests pin the change arithmetic, which names reach the
payload, the treemap layout and the bookmark's place (left of the ticker, avo, 18 Nov 2026).
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

from RevenueChaser.core.tests.board_js import function_source, run_board_js
from RevenueChaser.module_sector_rotation import heatmap


def test_changes_are_the_last_close_against_n_sessions_before():
    closes = [100.0 + i for i in range(300)]                # 100 .. 399, oldest first
    out = heatmap.changes(closes)
    assert [p for p, _ in heatmap.PERIODS] == ["1D", "1W", "1M", "3M", "6M", "1Y"]
    assert out[0] == round((399 / 398 - 1) * 100, 2)
    assert out[1] == round((399 / 394 - 1) * 100, 2)
    assert out[5] == round((399 / 147 - 1) * 100, 2)        # 252 sessions back


def test_a_short_series_has_no_long_changes():
    out = heatmap.changes([10.0, 11.0, 12.0])
    assert out[0] == round((12 / 11 - 1) * 100, 2)
    assert out[1:] == [None] * 5
    assert heatmap.changes([]) == [None] * 6


def _bars(tickers, newest, sessions=300, last=None):
    rows = []
    for t in tickers:
        end = last.get(t, newest) if last else newest
        for i in range(sessions):
            rows.append({"ticker": t, "session_date": pd.Timestamp(end - timedelta(days=sessions - 1 - i)),
                         "close": 100.0 + i})
    return pd.DataFrame(rows)


def test_the_payload_is_the_sp500_and_avos_lists_stocks_only(monkeypatch):
    from RevenueChaser.core import universe
    from RevenueChaser.module_watchlists import store
    from RevenueChaser.rcdata import read
    newest = date(2026, 11, 16)
    monkeypatch.setattr(universe, "load_cached_universe", lambda: [
        {"ticker": "AAPL", "name": "Apple", "sector": "Technology", "industry": "Consumer Electronics",
         "market_cap": 3.8e12, "security_type": "common"},
        {"ticker": "XOM", "name": "Exxon", "sector": "Energy", "industry": "Oil & Gas", "market_cap": 4.8e11,
         "security_type": "common"},
        {"ticker": "HALT", "name": "Halted", "sector": "Energy", "industry": "Oil & Gas", "market_cap": 1e9,
         "security_type": "common"},
        {"ticker": "SPY", "name": "SPDR S&P 500", "sector": "", "industry": "", "market_cap": 6e11,
         "security_type": "etp"},
        {"ticker": "NOCAP", "name": "No cap", "sector": "Energy", "industry": "", "market_cap": None,
         "security_type": "common"},
    ])
    monkeypatch.setattr(read, "membership", lambda index=None, **_k: [
        {"ticker": t} for t in ("AAPL", "XOM", "HALT", "NOCAP")])
    monkeypatch.setattr(store, "lists", lambda: [
        {"list_id": "semis", "name": "Semis", "feeds": ""},
        {"list_id": "jobs.map", "name": "Map", "feeds": "map"},          # not one of avo's picks
        {"list_id": "funds", "name": "Funds", "feeds": ""}])
    monkeypatch.setattr(store, "items", lambda list_id, section_id=None: {
        "semis": [{"ticker": "AAPL"}], "jobs.map": [{"ticker": "XOM"}], "funds": [{"ticker": "SPY"}]}[list_id])
    monkeypatch.setattr(read, "ticker_bars", lambda tickers, start=None, end=None, basis="split": _bars(
        [t for t in tickers if t != "NOCAP"], newest, last={"HALT": newest - timedelta(days=5)}))
    data = heatmap.payload(today=newest)
    assert data["as_of"] == "2026-11-16" and data["periods"][0] == "1D"
    by = {s[0]: s for s in data["stocks"]}
    assert set(by) == {"AAPL", "XOM", "HALT"}                # no fund, no name without a cap
    assert by["AAPL"][1:5] == ["Apple", "Technology", "Consumer Electronics", 3800.0]
    assert by["AAPL"][5] == round((399 / 398 - 1) * 100, 2)
    assert by["HALT"][5:] == [None] * 6                      # a stale name shows no change, never a flat one
    unis = {u["id"]: [data["stocks"][i][0] for i in u["idx"]] for u in data["universes"]}
    assert unis == {"sp500": ["AAPL", "HALT", "XOM"], "wl:semis": ["AAPL"]}
    assert data["universes"][0]["id"] == "sp500"             # the default (avo: "Sp500")


def test_no_universe_or_a_failed_read_draws_no_panel(monkeypatch):
    from RevenueChaser.core import universe
    monkeypatch.setattr(universe, "load_cached_universe", lambda: [])
    assert heatmap.payload() is None
    monkeypatch.setattr(universe, "load_cached_universe", lambda: 1 / 0)
    assert heatmap.payload() is None
    assert heatmap.panel_html(None) == ""


def test_the_treemap_fills_its_rectangle_by_value(tmp_path):
    src = function_source(heatmap.PANEL_JS, "squarify")
    tail = ("var out = squarify([{v:6},{v:6},{v:4},{v:3},{v:2},{v:2},{v:1}], {x:0,y:0,w:600,h:400});"
            "console.log(JSON.stringify(out.map(function(i){return [i.v, i.x, i.y, i.w, i.h];})));")
    out = run_board_js("<script>" + src + "</script>", tail, tmp_path)
    assert len(out) == 7
    total = sum(v for v, *_ in out)
    for v, x, y, w, h in out:
        assert abs(w * h - v / total * 600 * 400) < 1e-6
        assert -1e-6 <= x and x + w <= 600 + 1e-6 and -1e-6 <= y and y + h <= 400 + 1e-6


def _data():
    return {"as_of": "2026-11-16", "periods": ["1D", "1W", "1M", "3M", "6M", "1Y"], "stops": [3, 6, 12, 20, 30, 40],
            "stocks": [["AAPL", "Apple", "Technology", "Consumer Electronics", 3800.0, 1.5, 2, 3, 4, 5, 6],
                       ["XOM", "Exxon <b>", "Energy", "Oil & Gas", 480.0, -2.0, None, None, None, None, None]],
            "universes": [{"id": "sp500", "name": "S&P 500", "idx": [0, 1]}]}


def test_a_list_row_puts_the_bookmark_left_of_the_ticker_and_escapes_names(tmp_path):
    stub = ("<script>function rcWatchButtons(t){return '<span class=\"rc-watch\" data-ticker=\"' + t + '\"></span>';}"
            "</script>")
    html = stub + heatmap.panel_html(_data())
    tail = "console.log(JSON.stringify({list: _els['hm-list'].innerHTML, uni: _els['hm-uni'].innerHTML}));"
    out = run_board_js(html, tail, tmp_path)
    row = out["list"]
    assert row.index('data-ticker="AAPL"') < row.index('<span class="tk">AAPL')
    assert "Exxon &lt;b&gt;" in row and "Exxon <b>" not in row
    assert "S&amp;P 500 · 2" in out["uni"]


def test_the_board_carries_the_panel_only_with_data(monkeypatch):
    from RevenueChaser.module_sector_rotation import report
    monkeypatch.setattr(heatmap, "payload", lambda today=None: None)
    assert report._heatmap_html() == ""
    monkeypatch.setattr(heatmap, "payload", lambda today=None: _data())
    page = report._heatmap_html()
    assert 'id="hm"' in page and '"AAPL"' in page and "--pos" in page
