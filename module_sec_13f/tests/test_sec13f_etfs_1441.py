"""#1441 (mock approved by avo, 22 Nov 2026 21:34 Amsterdam): the 13F board's ETFs tab. One ETF's stock holdings
from its Form N-PORT report of a chosen quarter, the change in shares against the quarter before, and what it sold
out of; the rows are given here, the builder's own tests (``rcdata/tests/test_ownership_nport.py``) make them."""
from __future__ import annotations

from revenuechaser.core import ownership
from revenuechaser.module_sec_13f import report

Q3, Q2 = "2026q3", "2026q2"


def _h(ticker, name, shares, value, cusip=None, isin=None, country="US", weight=None, quarter=Q3):
    return {"quarter": quarter, "ticker": ticker, "name": name, "cusip": cusip, "isin": isin, "country": country,
            "shares": shares, "value": value, "weight": weight}


NOW = [_h(None, "Taiwan Semiconductor", 357_604_922, 26.5e9, isin="TW0002330008", country="TW", weight=4.1),
       _h("MSFT", "Microsoft Corp", 100, 40_000, cusip="594918104", weight=1.0),
       _h("NEWCO", "New Co", 10, 1_000, cusip="000000001", weight=0.1)]
BEFORE = [_h(None, "Taiwan Semiconductor", 355_970_748, 24.0e9, isin="TW0002330008", country="TW", quarter=Q2),
          _h("MSFT", "Microsoft Corp", 120, 45_000, cusip="594918104", quarter=Q2),
          _h(None, "Thomson Reuters Corp", 5, 189e6, isin="CA8849038085", country="CA", quarter=Q2),
          _h("GONE", "Gone Inc", 1, 10, cusip="000000002", quarter=Q2)]


def test_the_view_gives_the_change_in_shares_new_holdings_and_what_was_sold_out():
    """A foreign holding (no ticker) is matched across quarters by its ISIN, so TSMC reads +1,634,174 shares."""
    v = report.etf_holdings_view(NOW, BEFORE)
    assert [(h["ticker"] or h["name"], h["change"]) for h in v["holdings"]] == [
        ("Taiwan Semiconductor", 1_634_174), ("MSFT", -20), ("NEWCO", "new")]
    assert [e["name"] for e in v["exited"]] == ["Thomson Reuters Corp", "Gone Inc"]
    assert (v["positions"], v["no_ticker"], v["new"], v["exits"]) == (3, 1, 1, 2)


def test_the_first_quarter_held_has_no_change_and_nothing_sold_out():
    v = report.etf_holdings_view(NOW, None)
    assert {h["change"] for h in v["holdings"]} == {None}
    assert v["exited"] == [] and v["new"] is None and v["exits"] is None


def _client(monkeypatch, data: dict, hits=None):
    from revenuechaser.app import dashboard
    asked = []
    monkeypatch.setattr(ownership, "nport_etf", lambda e, q=None: asked.append((e, q)) or data)
    monkeypatch.setattr(ownership, "nport_etf_search", lambda q, limit=20: hits or [])
    dashboard.app.config["TESTING"] = True
    return dashboard.app.test_client(), asked


def test_the_etf_route_answers_the_quarters_and_the_view(monkeypatch):
    data = {"quarters": [{"quarter": Q3, "report_date": "2026-07-31"}, {"quarter": Q2, "report_date": "2026-04-30"}],
            "quarter": Q3, "prev_quarter": Q2, "rows": NOW, "prev_rows": BEFORE}
    client, asked = _client(monkeypatch, data, hits=[{"ticker": "VXUS", "name": "Vanguard Total Intl", "aum": 1}])
    body = client.get("/api/sec_13f/etfs/vxus?quarter=2026Q3").get_json()
    assert asked == [("VXUS", "2026q3")] and body["ok"] and body["name"] == "Vanguard Total Intl"
    assert body["quarter"] == Q3 and body["view"]["holdings"][0]["change"] == 1_634_174


def test_the_etf_route_refuses_a_bad_ticker_and_answers_404_without_a_quarter(monkeypatch):
    client, asked = _client(monkeypatch, {"quarters": [], "quarter": None, "rows": [], "prev_rows": []})
    assert client.get("/api/sec_13f/etfs/<script>").status_code in (400, 404)
    assert client.get("/api/sec_13f/etfs/SPY").status_code == 404


def test_the_search_route_answers_ticker_name_and_aum(monkeypatch):
    client, _ = _client(monkeypatch, {}, hits=[{"ticker": "VTI", "name": "Vanguard Total Stock", "aum": 5e11}])
    assert client.get("/api/sec_13f/etfs?q=").get_json()["etfs"] == []
    assert client.get("/api/sec_13f/etfs?q=vt").get_json()["etfs"] == [
        {"ticker": "VTI", "name": "Vanguard Total Stock", "aum": 5e11}]


def test_the_readers_give_an_empty_view_when_the_store_cannot_be_read(monkeypatch):
    from revenuechaser.rcdata import read as rcread

    def broken(*a, **kw):
        raise OSError("no ownership store")
    for name in ("etf_nport_quarters", "etf_holdings_history", "etf_search"):
        monkeypatch.setattr(rcread, name, broken)
    assert ownership.nport_etf("VTI")["quarters"] == []
    assert ownership.nport_etf_search("vt") == []


def test_the_board_has_an_etfs_tab():
    page = report.render_sec13f_dashboard({}, {})
    assert 'data-tab="etfs"' in page and '<div id="pane-etfs" hidden>' in page
    assert "/api/sec_13f/etfs/" in page and 'var DEFAULT_ETF = "VTI"' in page
