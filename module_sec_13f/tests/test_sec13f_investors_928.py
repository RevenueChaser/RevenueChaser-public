"""#928 and #779 (mock approved by avo, 18 Nov 2026): the 13F board's Investors tab. One filer's top holdings over
time, its newest settled holdings, its style row and its UW tags; the rows are given here, the builder's own tests
(``rcdata/tests/test_ownership_serve.py``) make them from filings."""
from __future__ import annotations

import pytest

from revenuechaser.core import ownership
from revenuechaser.core.reporting_common import THEME_SCALE
from revenuechaser.module_sec_13f import report

Q1, Q2, Q3 = "2026-03-31", "2026-06-30", "2026-09-30"


def _row(period: str, ticker: str | None, weight: float, rank: int | None = None, shares: float | None = None) -> dict:
    return {"cik": "1067983", "period": period, "ticker": ticker, "rank": rank, "weight": weight,
            "value": weight * 1e9, "shares": shares}


def _rows() -> list[dict]:
    """Eight names over three quarters: H is the largest in Q1 only and sold out after; G and F are small."""
    q1 = [_row(Q1, t, w, i + 1, 100.0) for i, (t, w) in enumerate(
        [("H", 40.0), ("A", 20.0), ("B", 10.0), ("C", 8.0), ("D", 6.0), ("E", 5.0)])] + [_row(Q1, None, 11.0)]
    q2 = [_row(Q2, t, w, i + 1, sh) for i, (t, w, sh) in enumerate(
        [("A", 45.0, 100.0), ("B", 15.0, 120.0), ("C", 9.0, 100.0), ("D", 7.0, 50.0), ("E", 6.0, 100.0),
         ("G", 3.0, 10.0)])] + [_row(Q2, None, 15.0)]
    q3 = [_row(Q3, "A", 50.0, 1, 100.0), _row(Q3, "F", 2.0, 2, 5.0), _row(Q3, None, 48.0)]
    return q1 + q2 + q3


def test_the_figure_keeps_the_six_names_with_the_highest_weight_anywhere_in_the_window():
    fig, note = report.build_filer_fig("Berkshire", _rows(), quarters=None)
    traces = fig["data"]
    # H, sold out after Q1, keeps its colour because it was the largest there (#788's rule), G and F do not make it.
    assert [t["name"] for t in traces] == ["A", "H", "B", "C", "D", "E", "Other"]
    by = {t["name"]: list(t["y"]) for t in traces}
    assert by["H"] == [40.0, 0.0, 0.0] and by["A"] == [20.0, 45.0, 50.0]
    assert [sum(v[i] for v in by.values()) for i in range(3)] == pytest.approx([100.0, 100.0, 100.0])
    assert [t["line"]["color"] for t in traces[:6]] == [THEME_SCALE[f"c{i}"] for i in range(1, 7)]
    assert list(fig["layout"]["yaxis"]["range"]) == [0, 100]
    assert "Berkshire" in note and "highest weight anywhere" in note


def test_the_window_cuts_the_quarters_before_the_names_are_ranked():
    fig, _ = report.build_filer_fig("Berkshire", _rows(), quarters=2)
    names = [t["name"] for t in fig["data"]]
    assert "H" not in names and names[:2] == ["A", "B"] and len(fig["data"][0]["x"]) == 2


def test_a_quarter_still_arriving_is_marked_and_a_filer_with_no_rows_draws_nothing():
    fig, note = report.build_filer_fig("Berkshire", _rows(), still_arriving={Q3}, quarters=None)
    assert list(fig["data"][0]["x"])[-1] == report._qlabel(Q3) + report.ARRIVING_MARK and "still arriving" in note
    fig, note = report.build_filer_fig("Nobody", [])
    assert fig is None and "No 13F holdings of Nobody" in note


def test_the_holdings_are_the_newest_settled_quarters_with_the_change_against_the_one_before():
    period, rows = report.filer_holdings_view(_rows(), still_arriving={Q3})
    assert period == Q2 and [r["ticker"] for r in rows] == ["A", "B", "C", "D", "E", "G"]
    by = {r["ticker"]: r["change"] for r in rows}
    assert by["A"] == pytest.approx(0.0) and by["B"] == pytest.approx(20.0) and by["D"] == pytest.approx(-50.0)
    assert by["G"] is None                       # not among Q1's stored largest: unknown, not "new"
    assert report.filer_holdings_view(_rows(), still_arriving={Q1, Q2, Q3}) == (None, [])


def _client(monkeypatch, data: dict):
    from revenuechaser.app import dashboard
    asked = []
    monkeypatch.setattr(ownership, "sec13f_filer", lambda cik: asked.append(cik) or data)
    monkeypatch.setattr(ownership, "sec13f_open_periods", lambda: set())
    dashboard.app.config["TESTING"] = True
    return dashboard.app.test_client(), asked


def test_the_filer_route_answers_the_chart_holdings_style_and_tags(monkeypatch):
    style = {"cik": "1067983", "period": Q3, "filer_name": "BERKSHIRE HATHAWAY INC", "quarters": 8, "names": 2,
             "value": 3e11, "turnover": 0.05, "top10_share": 0.9, "held_share": 0.8}
    client, asked = _client(monkeypatch, {"holdings": _rows(), "style": style, "tags": ["value_investor"]})
    body = client.get("/api/sec_13f/filers/1067983?quarters=all").get_json()
    assert asked == ["1067983"] and body["ok"] and body["name"] == "BERKSHIRE HATHAWAY INC"
    assert body["fig"]["data"][0]["name"] == "A" and len(body["fig"]["data"][0]["x"]) == 3
    assert body["period"] == Q3 and [h["ticker"] for h in body["holdings"]] == ["A", "F"]
    assert body["style"]["turnover"] == 0.05 and body["tags"] == ["value_investor"]
    assert len(client.get("/api/sec_13f/filers/1067983").get_json()["fig"]["data"][0]["x"]) == 3   # 20 > 3 stored


def test_the_filer_route_refuses_a_bad_cik_and_answers_404_for_an_unknown_one(monkeypatch):
    client, asked = _client(monkeypatch, {"holdings": [], "style": None, "tags": []})
    assert client.get("/api/sec_13f/filers/abc").status_code == 400
    assert client.get("/api/sec_13f/filers/12345678901").status_code == 400
    assert asked == []
    assert client.get("/api/sec_13f/filers/42").status_code == 404


def test_the_search_route_needs_two_characters(monkeypatch):
    from revenuechaser.app import dashboard
    asked = []
    monkeypatch.setattr(ownership, "sec13f_filer_search", lambda q: asked.append(q) or [
        {"cik": "1067983", "filer_name": "BERKSHIRE HATHAWAY INC", "value": 3e11, "names": 29, "period": Q2}])
    client = dashboard.app.test_client()
    assert client.get("/api/sec_13f/filers?q=b").get_json()["filers"] == [] and asked == []
    hits = client.get("/api/sec_13f/filers?q=berk").get_json()["filers"]
    assert asked == ["berk"] and hits[0]["cik"] == "1067983" and hits[0]["name"] == "BERKSHIRE HATHAWAY INC"


def test_the_readers_give_an_empty_view_when_the_store_cannot_be_read(monkeypatch):
    from revenuechaser.rcdata import read as rcread

    def broken(*a, **kw):
        raise OSError("no ownership store")
    for name in ("filer_holdings_13f", "filer_style_13f", "institution_tags"):
        monkeypatch.setattr(rcread, name, broken)
    assert ownership.sec13f_filer("1067983") == {"holdings": [], "style": None, "tags": []}
    assert ownership.sec13f_filer_search("berk") == []


def test_the_board_has_a_tickers_and_an_investors_tab_with_the_type_view_as_group():
    page = report.render_sec13f_dashboard({}, {})
    assert 'data-tab="tickers" aria-selected="true"' in page and 'data-tab="investors"' in page
    assert '<div id="pane-investors" hidden>' in page and 'id="pane-tickers"' in page
    assert page.index('id="pane-investors"') < page.index('<details class="types" id="types">')
    assert "/api/sec_13f/filers/" in page and 'var DEFAULT_FILER = "1067983"' in page
