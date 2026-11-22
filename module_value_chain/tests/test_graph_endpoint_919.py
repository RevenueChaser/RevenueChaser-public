"""The Value Chain page fetches the picked company's graph instead of embedding every company's (claude-coordinator
PR #919 section 8: the page measured 14.6 MB on homesrv). ``engine.focal_from_payload_file`` answers from the board's
last payload file; ``/api/value_chain/graph/<ticker>`` serves it as JSON, which the phone app reads too."""
from __future__ import annotations

import json
import os

import pytest

from revenuechaser.app import dashboard, runners
from revenuechaser.module_value_chain import engine, report


def _edge(src, dst, rel, snippet):
    return {"src": src, "dst_name": dst, "dst_ticker": dst, "relation": rel, "snippet": snippet,
            "filed": "2026-02-01", "source": "xbrl"}


EDGES = [_edge("AMKR", "AAPL", "customer", "Apple 21% of revenue"), _edge("AAPL", "TSM", "supplier", "TSMC wafers")]


@pytest.fixture
def payload_file(tmp_path, monkeypatch):
    path = tmp_path / "value_chain_latest.json"
    path.write_text(json.dumps({"edges": EDGES}), encoding="utf-8")
    monkeypatch.setattr(engine, "_GRAPH_CACHE", {})
    monkeypatch.setattr(runners, "VALUE_CHAIN_JSON", path)
    return path


def test_the_file_answers_the_same_graph_the_page_embedded(payload_file):
    assert engine.focal_from_payload_file(payload_file, "AMKR") == engine.focal_graph(EDGES, "AMKR", depth=2)


def test_no_file_is_no_graph(tmp_path):
    assert engine.focal_from_payload_file(tmp_path / "missing.json", "AMKR") is None


def test_a_new_run_is_read_again(payload_file):
    assert engine.focal_from_payload_file(payload_file, "NVDA")["links"] == []
    payload_file.write_text(json.dumps({"edges": [_edge("NVDA", "TSM", "supplier", "s")]}), encoding="utf-8")
    st = payload_file.stat()
    os.utime(payload_file, ns=(st.st_atime_ns, st.st_mtime_ns + 10**9))
    assert [l["dst"] for l in engine.focal_from_payload_file(payload_file, "NVDA")["links"]] == ["TSM"]


@pytest.fixture
def client(rawstore_tmp_db):
    dashboard.app.config["TESTING"] = True
    return dashboard.app.test_client()


def test_the_endpoint_serves_one_companys_graph(client, payload_file):
    r = client.get("/api/value_chain/graph/amkr")
    assert r.status_code == 200
    body = r.get_json()
    assert body["ok"] is True and body["ticker"] == "AMKR"
    assert body["graph"] == engine.focal_graph(EDGES, "AMKR", depth=2)


def test_the_endpoint_says_when_no_run_wrote_the_file(client, tmp_path, monkeypatch):
    monkeypatch.setattr(runners, "VALUE_CHAIN_JSON", tmp_path / "missing.json")
    r = client.get("/api/value_chain/graph/AMKR")
    assert r.status_code == 404 and r.get_json()["ok"] is False


def test_a_hostile_ticker_is_a_400(client, payload_file):
    r = client.get("/api/value_chain/graph/%3Cimg%3E")
    assert r.status_code == 400 and "<img>" not in r.get_data(as_text=True)


def test_the_page_embeds_no_graph(rawstore_tmp_db):
    filings = [{"ticker": t, "name": t, "form": "10-K", "filed": "2026-02-01", "quality": "ok"}
               for t in ("AMKR", "AAPL", "TSM")]
    html = report.render_value_chain_dashboard({"as_of": "", "filings": filings, "edges": EDGES})
    assert "Apple 21% of revenue" not in html and "TSMC wafers" not in html     # snippets live in the graphs
    assert '"/api/value_chain/graph/"' in html
