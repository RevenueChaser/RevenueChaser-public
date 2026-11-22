"""#212: a Fetch press is refused while there is no fresh verified backup, and nothing is queued.

The press is refused on the page and not left to the builder's own gate: a request the builder will refuse would
sit in the queue looking queued, and the card would say nothing. Pause, Resume and the switches are not gated —
they only stop writes, so they have to work exactly when the store is in trouble.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from revenuechaser.core import config
from revenuechaser.core.tests.panel_client import panel_test_client
from revenuechaser.rcdata import backup, ops


@pytest.fixture(autouse=True)
def _market(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "MARKET_DIR", tmp_path / "market")
    monkeypatch.setattr(config, "MARKET_RAW_DIR", tmp_path / "market_raw")
    monkeypatch.setattr(ops, "read_log", ops.ReadLog(process="test"))
    monkeypatch.setattr(config, "RAW_STORE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv(backup.GATE_ENV, raising=False)


@pytest.fixture
def client():
    from revenuechaser.app.dashboard import app
    return panel_test_client(app)


def _verified(days_ago: float) -> None:
    out = backup.step_dir(backup.STEP_DUCKDB)
    out.mkdir(parents=True, exist_ok=True)
    at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    (out / backup.MANIFEST_NAME).write_text(json.dumps({"files": {}, "last_ok": at.isoformat()}), encoding="utf-8")


def test_a_fetch_press_with_no_backup_is_refused_and_queues_nothing(client):
    r = client.post("/api/build/request/market_series", headers={"X-RC-Panel": "settings"})
    assert r.status_code == 409
    assert "no fresh backup" in r.get_json()["error"]
    assert ops.rows("build_requests") == []


def test_a_fetch_press_with_a_stale_backup_is_refused(client):
    _verified(backup.STALE_DAYS + 1)
    r = client.post("/api/build/request/market_series")
    assert r.status_code == 409 and "days old" in r.get_json()["error"]
    assert ops.rows("build_requests") == []


def test_a_fetch_press_with_a_fresh_backup_goes_through(client):
    _verified(1)
    assert client.post("/api/build/request/market_series").status_code == 202
    assert [r["dataset"] for r in ops.rows("build_requests")] == ["market_series"]


def test_a_backfill_press_is_gated_too(client):
    """A backfill rewrites stored days, so it is the press that most needs the copy."""
    r = client.post("/api/build/request/market_series", json={"backfill_from": "2026-01-02"})
    assert r.status_code == 409
    assert ops.rows("build_requests") == []


def test_pause_and_the_switches_still_work_with_no_backup(client):
    """The safety valves are never gated: turning fetching off is what a person reaches for in trouble."""
    assert client.post("/api/build/schedule/market_series/pause").status_code == 200
    assert client.post("/api/build/switch/fetch", json={"on": False}).status_code == 200
