"""v2 step 6 (#1264): the door's HTTP surface — its four read routes and the guards in front of them.

The guards are what these tests exist for. The door is read-only in this step **by construction**, not by the
accident of no write route being declared yet: the method guard sits in front of every route the app will ever
have, so step 7's proxy cannot open a write by being added. A Host allowlist and a CSP that names no CDN are the
other two, and the CSP's single external origin is Grafana's, because v2 runs on a tailnet.
"""
from __future__ import annotations

import gzip
import json

import pytest

from RevenueChaser.core import reporting_common as rc
from RevenueChaser.core import v2_envelope as env
from RevenueChaser.v2.door import app as door_app
from RevenueChaser.v2.door import boards

fastapi_testclient = pytest.importorskip("fastapi.testclient")

HOST = "127.0.0.1"
BASE = f"http://{HOST}:8100"


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A door whose artifacts root is a scratch folder, reached over the in-process ASGI transport."""
    monkeypatch.setenv("RC_DOOR_HOSTS", HOST)
    monkeypatch.setenv("RC_BUILD_SHA", "0" * 40)
    monkeypatch.setattr(boards, "artifacts_dir", lambda: tmp_path)
    with fastapi_testclient.TestClient(door_app.create_app(), base_url=BASE) as c:
        c.artifacts = tmp_path
        yield c


def _write(root, board="module_relatedness", payload=None):
    payload = {"as_of": "2026-11-20", "rows": [{"ticker": "AAPL"}]} if payload is None else payload
    html = root / f"{env.BOARDS[board]}.html"
    rc.write_board(html, "<html></html>", payload, run_id="run-1")
    return html


# ── the guards ──────────────────────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("path", ["/api/v1/health", "/api/v1/boards", "/api/v1/boards/module_relatedness", "/"])
def test_the_door_refuses_every_write_method_on_every_path(client, method, path):
    """Step 7 adds the proxy; until then nothing can get through the door to a write."""
    r = client.request(method, path)
    assert r.status_code == 405, f"{method} {path} answered {r.status_code}"
    assert "GET" in r.headers["Allow"]


def test_the_read_methods_are_exactly_get_head_and_options():
    assert door_app.READ_METHODS == frozenset({"GET", "HEAD", "OPTIONS"})


def test_a_host_outside_the_allowlist_is_refused(client):
    assert client.get("/api/v1/version").status_code == 200
    assert client.get("/api/v1/version", headers={"Host": "someone-elses.example"}).status_code == 400


def test_the_csp_names_the_grafana_origin_and_no_cdn(monkeypatch):
    monkeypatch.setenv("RC_DOOR_GRAFANA_ORIGIN", "https://homesrv.example:3000")
    policy = door_app.content_security_policy()
    assert "frame-src https://homesrv.example:3000" in policy
    assert "default-src 'self'" in policy
    assert "frame-ancestors 'none'" in policy
    for banned in ("cdn.", "unpkg", "jsdelivr", "googleapis", "*"):
        assert banned not in policy, f"the CSP names {banned}"


def test_the_csp_frames_nothing_when_no_grafana_origin_is_set(monkeypatch):
    monkeypatch.setenv("RC_DOOR_GRAFANA_ORIGIN", "")
    assert "frame-src 'none'" in door_app.content_security_policy()


def test_every_answer_carries_the_doors_headers(client):
    for path in ("/api/v1/version", "/api/v1/boards", "/"):
        r = client.get(path)
        assert "Content-Security-Policy" in r.headers, path
        assert r.headers["X-Content-Type-Options"] == "nosniff", path
        assert r.headers["Referrer-Policy"] == "no-referrer", path


def test_the_door_publishes_no_schema_or_docs_page(client):
    for path in ("/openapi.json", "/docs", "/redoc"):
        assert client.get(path).status_code == 404, path


# ── the routes ──────────────────────────────────────────────────────────────────────────────────────────────────

def test_version_answers_which_commit_is_serving(client):
    body = client.get("/api/v1/version").json()
    assert body["build_sha"] == "0" * 40
    assert body["envelope_schema_version"] == env.ENVELOPE_SCHEMA_VERSION
    assert body["boards"] == list(boards.board_keys())


def test_health_is_200_when_the_artifacts_root_is_there(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.headers["Cache-Control"] == "no-store"


def test_health_is_503_when_a_required_probe_is_red(client, monkeypatch):
    monkeypatch.setattr(boards, "artifacts_dir", lambda: client.artifacts / "gone")
    r = client.get("/api/v1/health")
    assert r.status_code == 503
    assert r.json()["failed"] == ["artifacts"]


def test_the_board_list_carries_metadata_and_no_rows(client):
    _write(client.artifacts)
    rows = client.get("/api/v1/boards").json()["boards"]
    assert len(rows) == len(env.BOARDS)
    served = [row for row in rows if row["board"] == "module_relatedness"][0]
    assert served["run_id"] == "run-1" and served["present"] is True
    allowed = set(boards.LIST_KEYS) | {"board", "present", "stored_bytes", "data_bytes"}
    assert all(set(row) <= allowed for row in rows), "the list grew a key"
    assert "AAPL" not in json.dumps(rows), "the list is carrying a board's rows"


def test_a_board_is_served_gzip_as_stored(client):
    html = _write(client.artifacts)
    r = client.get("/api/v1/boards/module_relatedness", headers={"Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.json()["board"] == "module_relatedness"
    # httpx decodes the body; the file on disk is what the door handed over.
    assert gzip.decompress(boards.envelope_path("module_relatedness").read_bytes()) == r.content
    assert r.json()["data"] == json.loads(gzip.decompress(rc.payload_path(html).read_bytes()))


def test_a_client_that_takes_no_gzip_gets_plain_json(client):
    _write(client.artifacts)
    r = client.get("/api/v1/boards/module_relatedness", headers={"Accept-Encoding": "identity"})
    assert r.status_code == 200
    assert "Content-Encoding" not in r.headers
    assert r.json()["board"] == "module_relatedness"


def test_an_unknown_board_and_a_board_with_no_envelope_both_404_with_their_own_reason(client):
    unknown = client.get("/api/v1/boards/module_made_up")
    missing = client.get("/api/v1/boards/module_sec_13f")
    assert unknown.status_code == missing.status_code == 404
    assert "unknown board" in unknown.json()["detail"]
    assert "no envelope" in missing.json()["detail"]


def test_the_root_says_the_web_files_are_not_built_rather_than_failing_to_start(client, monkeypatch):
    """A door built from a checkout with no ``v2/web/dist`` still answers the API — step 8 fills the frame."""
    if door_app.WEB_DIST.is_dir():
        pytest.skip("this checkout has a built v2/web/dist")
    r = client.get("/")
    assert r.status_code == 200
    assert "not built" in r.text
