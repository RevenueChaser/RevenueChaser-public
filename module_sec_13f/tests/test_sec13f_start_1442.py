"""#1442 (avo, 22 Nov 2026: "2019'a kadar"): the 13F board and its chart start in 2019q1. The store holds 13F back to
2013q2, but the closes and split factors are read from 2019 only, so the chart route leaves the older quarters out."""
from __future__ import annotations

from revenuechaser.module_sec_13f import engine


def test_the_chart_route_shows_the_quarters_from_2019_only(monkeypatch):
    from revenuechaser.app import dashboard
    from revenuechaser.module_sec_13f import enrich
    from revenuechaser.module_sec_13f import store as sec13f_store
    cell = {"shares": 100.0, "value": 1000.0, "holders": 2}
    stored = {"2013-06-30": cell, "2018-12-31": cell, "2019-03-31": cell, "2026-06-30": cell}
    monkeypatch.setattr(sec13f_store, "read_ticker", lambda t: dict(stored))
    asked = []
    monkeypatch.setattr(enrich, "load_inputs", lambda totals: asked.append(totals) or {})
    dashboard.app.config["TESTING"] = True
    r = dashboard.app.test_client().get("/api/sec_13f/AAPL")
    assert r.status_code == 200 and engine.START_QUARTER == "2019-03-31"
    assert sorted(asked[0]["AAPL"]) == ["2019-03-31", "2026-06-30"]
