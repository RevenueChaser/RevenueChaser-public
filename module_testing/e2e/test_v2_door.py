"""The v2 door, end to end on loopback (step 6, #1264).

The unit tier tests the door's rules through the in-process ASGI transport. This file is the other half the run
plan asks for: a **real uvicorn**, a real socket, real gzip over the wire, against envelope files a real
``write_board`` wrote. It is what proves the deploy's check before the deploy — for each board served, the
``sha256`` of the door's ``data`` equals the ``sha256`` of the dashboard's own payload file, decompressed.

No dashboard subprocess and no mock provider here: the door reads files, so the thing under test is the door, the
socket and the bytes. The board artifacts are written by ``core.reporting_common.write_board`` itself, the one
function the dashboard's jobs use, so the files are the real ones and not a fixture's idea of them.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
import types
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from RevenueChaser.core import reporting_common as rc
from RevenueChaser.core import v2_envelope as env

REPO = Path(__file__).resolve().parents[2]
HOST = "127.0.0.1"
# The boards this test serves. Two is enough to prove the pairing and the list; the deploy quotes all six from the
# box, where the real jobs have run.
SERVED = {
    "module_relatedness": {"as_of": "2026-11-20", "rows": [{"ticker": "AAPL", "score": 1.5}]},
    "module_swing_potential": {"data_as_of": "2026-11-19", "rows": [{"ticker": "MSFT", "score": -0.5}]},
}


def _free_port() -> int:
    with socket.socket() as s:
        s.bind((HOST, 0))
        return s.getsockname()[1]


def _get(url: str, headers: dict | None = None):
    """``(status, headers, body)``. The header names are **lower-cased**, because uvicorn sends them that way.

    ``dict(response.headers)`` keeps each name exactly as the server wrote it, and uvicorn writes
    ``content-encoding``, not ``Content-Encoding`` — so a plain dict lookup by the capitalised name silently finds
    nothing and a header assertion passes or fails for the wrong reason. Lower-casing here is the fix; HTTP header
    names are case-insensitive by RFC 9110, so there is nothing to lose.
    """
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=10) as r:
            return r.status, _lower(r.headers), r.read()
    except urllib.error.HTTPError as e:                 # a 404 or 405 is an answer, not a failure
        return e.code, _lower(e.headers), e.read()


def _lower(headers) -> dict[str, str]:
    return {name.lower(): value for name, value in headers.items()}


@pytest.fixture(scope="module")
def door(tmp_path_factory):
    """A real door process on loopback, serving a cache folder with two boards written into it."""
    root = tmp_path_factory.mktemp("v2-door")
    cache = root / ".cache"
    cache.mkdir()
    artifacts = {}
    for board, payload in SERVED.items():
        html = cache / f"{env.BOARDS[board]}.html"
        rc.write_board(html, "<html></html>", payload, run_id=f"run-{board}")
        artifacts[board] = html

    port = _free_port()
    env_vars = dict(os.environ)
    # The repository's parent first, so ``RevenueChaser.*`` imports resolve, and whatever was already on
    # PYTHONPATH after it — that is the suite's own netguard folder, and dropping it would start the one child in
    # this tier that runs unguarded (module_testing/netguard/sitecustomize.py).
    env_vars.update(RC_CACHE_DIR=str(cache), RC_STORE_DIR=str(root / ".store"),
                    RC_EDGAR_DOCS_DIR=str(root / "edgar_docs"), RC_DOOR_HOSTS=HOST,
                    RC_BUILD_SHA="e" * 40,
                    PYTHONPATH=os.pathsep.join(p for p in (str(REPO.parent),
                                                           os.environ.get("PYTHONPATH", "")) if p))
    env_vars.pop("RC_REDIS_URL", None)   # the read side needs no queue; the probe then reports "not configured"
    log = (root / "door.log").open("w", encoding="utf-8")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "RevenueChaser.v2.door.app:app",
                             "--host", HOST, "--port", str(port), "--workers", "1"],
                            cwd=REPO.parent, env=env_vars, stdout=log, stderr=subprocess.STDOUT)
    base = f"http://{HOST}:{port}"
    try:
        _wait_for(proc, base, root / "door.log")
        yield types.SimpleNamespace(base=base, cache=cache, artifacts=artifacts)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.close()


def _wait_for(proc, base: str, log_path: Path, timeout: float = 60.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            pytest.fail(f"the door exited with {proc.returncode}:\n{log_path.read_text(errors='replace')[-3000:]}")
        try:
            status, _, _ = _get(f"{base}/api/v1/health")
        except OSError:
            time.sleep(0.2)
            continue
        if status == 200:
            return
        time.sleep(0.2)
    pytest.fail(f"the door never answered 200 on /api/v1/health:\n{log_path.read_text(errors='replace')[-3000:]}")


def test_health_answers_200_with_the_artifacts_probe_green(door):
    status, _, body = _get(f"{door.base}/api/v1/health")
    assert status == 200
    result = json.loads(body)
    assert result["status"] == "ok"
    by_name = {c["check"]: c for c in result["checks"]}
    assert by_name["artifacts"]["ok"] is True
    assert by_name["redis"]["ok"] is None, "no RC_REDIS_URL is 'not configured', not a fault"
    assert result["budget_s"] == 2.0


def test_version_names_the_build_it_was_started_from(door):
    _, _, body = _get(f"{door.base}/api/v1/version")
    result = json.loads(body)
    assert result["build_sha"] == "e" * 40
    assert result["envelope_schema_version"] == env.ENVELOPE_SCHEMA_VERSION
    assert set(result["boards"]) == set(env.BOARDS)


def test_the_board_list_shows_what_is_present_and_what_is_not(door):
    _, _, body = _get(f"{door.base}/api/v1/boards")
    rows = {row["board"]: row for row in json.loads(body)["boards"]}
    assert set(rows) == set(env.BOARDS)
    for board in SERVED:
        assert rows[board]["present"] is True
        assert rows[board]["run_id"] == f"run-{board}"
    absent = set(env.BOARDS) - set(SERVED)
    assert all(rows[board]["present"] is False for board in absent)


@pytest.mark.parametrize("board", sorted(SERVED))
def test_the_doors_data_hash_equals_the_dashboards_payload_file(door, board):
    """The deploy's proof, over a real socket: one equal pair per board served."""
    _, headers, body = _get(f"{door.base}/api/v1/boards/{board}", {"Accept-Encoding": "gzip"})
    assert headers.get("content-encoding") == "gzip", "the stored bytes are served as stored"
    envelope = json.loads(gzip.decompress(body))
    from_door = hashlib.sha256(env.data_bytes(envelope)).hexdigest()
    payload_file = rc.payload_path(door.artifacts[board])
    from_payload = hashlib.sha256(gzip.decompress(payload_file.read_bytes())).hexdigest()
    assert from_door == from_payload
    assert envelope["data"] == SERVED[board]


def test_a_client_without_gzip_gets_the_same_envelope_plain(door):
    board = sorted(SERVED)[0]
    _, headers, body = _get(f"{door.base}/api/v1/boards/{board}", {"Accept-Encoding": "identity"})
    assert "content-encoding" not in headers
    assert json.loads(body)["board"] == board


def test_a_board_with_no_envelope_is_404_over_the_wire(door):
    missing = sorted(set(env.BOARDS) - set(SERVED))[0]
    status, _, body = _get(f"{door.base}/api/v1/boards/{missing}")
    assert status == 404
    assert "no envelope" in json.loads(body)["detail"]


def test_a_write_is_refused_by_the_real_server(door):
    """Step 7 adds the proxy. Until then a real POST to a real socket gets 405 and changes nothing."""
    request = urllib.request.Request(f"{door.base}/api/v1/boards", data=b"{}", method="POST")
    try:
        with urllib.request.urlopen(request, timeout=10) as r:
            pytest.fail(f"a POST answered {r.status}")
    except urllib.error.HTTPError as e:
        assert e.code == 405
        assert "GET" in e.headers["Allow"]


def test_a_host_outside_the_allowlist_is_refused_by_the_real_server(door):
    status, _, _ = _get(f"{door.base}/api/v1/version", {"Host": "someone-elses.example"})
    assert status == 400


def test_every_answer_carries_the_csp_and_names_no_cdn(door):
    for path in ("/api/v1/version", "/api/v1/boards", "/"):
        _, headers, _ = _get(f"{door.base}{path}")
        policy = headers.get("content-security-policy", "")
        assert "default-src 'self'" in policy, path
        assert "cdn" not in policy and "unpkg" not in policy, path
        assert headers.get("x-content-type-options") == "nosniff", path
