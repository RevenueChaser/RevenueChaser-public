"""The served Relatedness page carries no peer list: it fetches the focal ticker's peers on pick.

Measured on homesrv (coordinator PR #919 §8): the page was 35 MB, 32 MB of it every ticker's peer list inlined.
The served page now holds the chrome only; the companies ride the K10 payload and each focal ticker's peers come
from ``/api/relatedness/peers/<ticker>``, the same JSON the phone app reads.
"""
from __future__ import annotations

import gzip
import json

import pytest

from RevenueChaser.core.reporting_common import payload_path
from RevenueChaser.core.tests.board_js import assert_scripts_parse
from RevenueChaser.module_relatedness import engine, report


def _payload(n: int) -> dict:
    tickers = [f"T{i}" for i in range(n)]
    return {"as_of": "2026-11-17T00:00:00+00:00", "model": "m", "n": n,
            "companies": [{"ticker": t, "name": f"Name {t}", "sector": "Technology", "industry": "Software",
                           "weights": {"x": 1.0}, "profile": {"products": ["x"]}} for t in tickers],
            "peers": {t: [{"peer": p, "name": f"Name {p}", "score": 0.5, "percentile": 90,
                           "shared": ["cloud software", "enterprise customers"]}
                          for p in tickers if p != t][:25] for t in tickers}}


def test_the_served_page_holds_no_peer_and_no_company_and_the_payload_holds_the_companies():
    p = _payload(60)
    html, data = report.render_relatedness_board(p)
    assert "Name T59" not in html and "cloud software" not in html
    assert [c["ticker"] for c in data["companies"]] == [f"T{i}" for i in range(60)]
    assert "peers" not in data and "profile" not in data["companies"][0]
    # The one-file page (tests, guards) still inlines both.
    assert "cloud software" in report.render_relatedness_dashboard(p)


def test_an_empty_board_needs_no_payload_and_keeps_its_message():
    html, data = report.render_relatedness_board({"n": 0, "companies": [], "peers": {}})
    assert data is None
    assert "No profiles yet" in html


def test_the_served_page_scripts_parse(tmp_path):
    # No value reaches the served page (the probe test of the one-file page covers escaping); its scripts must parse.
    assert_scripts_parse(report.render_relatedness_board(_payload(2))[0], tmp_path)


@pytest.fixture
def board(tmp_path, monkeypatch):
    from RevenueChaser.app import dashboard, runners
    monkeypatch.setattr(runners, "RELATEDNESS_LATEST", tmp_path / "relatedness_latest.html")
    monkeypatch.setattr(runners, "RELATEDNESS_JSON", tmp_path / "relatedness" / "relatedness_latest.json")
    monkeypatch.setattr(runners, "RELATEDNESS_PEERS_DIR", tmp_path / "relatedness" / "peers")
    dashboard.app.config["TESTING"] = True
    return runners, dashboard.app.test_client()


def test_the_runner_writes_one_peer_file_per_ticker_and_the_route_serves_it(board, monkeypatch):
    runners, client = board
    monkeypatch.setattr(engine, "run", lambda **k: _payload(3))
    runners.run_relatedness(None, no_fetch=True)
    data = json.loads(gzip.decompress(payload_path(runners.RELATEDNESS_LATEST).read_bytes()))
    assert len(data["companies"]) == 3

    r = client.get("/api/relatedness/peers/t1")       # lower case is a valid request
    assert r.status_code == 200
    body = r.get_json()
    assert body["ticker"] == "T1" and [p["peer"] for p in body["peers"]] == ["T0", "T2"]
    assert client.get("/api/relatedness/peers/NOPE").status_code == 404
    assert client.get("/api/relatedness/peers/..").status_code in (400, 404)
    assert client.get("/api/relatedness/peers/%3Cx%3E").status_code == 400


def test_a_later_run_drops_the_peer_file_of_a_ticker_it_no_longer_scores(board, monkeypatch):
    runners, client = board
    monkeypatch.setattr(engine, "run", lambda **k: _payload(3))
    runners.run_relatedness(None, no_fetch=True)
    monkeypatch.setattr(engine, "run", lambda **k: _payload(2))
    runners.run_relatedness(None, no_fetch=True)
    assert client.get("/api/relatedness/peers/T2").status_code == 404
    assert sorted(f.name for f in runners.RELATEDNESS_PEERS_DIR.iterdir()) == ["T0.json", "T1.json"]
