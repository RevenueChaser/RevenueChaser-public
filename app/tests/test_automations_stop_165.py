"""``GET /api/automations`` carries each row's Stop, and the Stop is the cancel route that already exists (#165).

avo's decision (a), 20 Nov 2026: a row's Stop is ``POST /api/job/<id>/cancel`` on the dashboard job the task
queues, and a job the OS started has no Stop. So no route is added here: the panel is told which id to cancel.
"""
from __future__ import annotations

import pytest

from RevenueChaser.app import dashboard, jobs
from RevenueChaser.core import automations as A


@pytest.fixture
def fake():
    f = A.FakeScheduler()
    A.set_scheduler(f)
    yield f
    A.set_scheduler(None)


@pytest.fixture
def client():
    return dashboard.app.test_client()


def _row(client, name: str) -> dict:
    rows = client.get("/api/automations").get_json()["rows"]
    return next(r for r in rows if r["name"] == name)


def test_no_stop_action_was_added_to_the_action_route(client, fake):
    r = client.post("/api/automations/RC-ValueChain-Sync/stop", headers={"X-RC-Panel": "automations"})
    assert r.status_code == 400 and fake.calls == []


def test_each_row_says_whether_it_has_a_stop(client, fake):
    rows = client.get("/api/automations").get_json()["rows"]
    assert all("stop" in r for r in rows)
    assert _row(client, "RC-Build")["stop"]["reason"] == A.STOP_NOT_DASHBOARD
    assert _row(client, "RC-ValueChain-Sync")["stop"]["reason"] == A.STOP_NOT_RUNNING


def test_a_queued_job_shows_on_its_row_and_that_id_is_the_one_the_cancel_route_stops(client, fake, monkeypatch):
    """End to end on the queued side: the row's ``cancel_url`` is a route that really cancels that job."""
    monkeypatch.setattr(jobs, "_ensure_worker", lambda: None)
    monkeypatch.setattr(jobs, "_ensure_long_worker", lambda: None)
    job_id = jobs.submit("module_value_chain", {})
    try:
        stop = _row(client, "RC-ValueChain-Sync")["stop"]
        assert stop["can_stop"] is True and stop["job_id"] == job_id
        assert stop["cancel_url"] == f"/api/job/{job_id}/cancel"
        # Another row must not claim it.
        assert _row(client, "RC-SPX-Gamma-Fetch")["stop"]["job_id"] is None
        r = client.post(stop["cancel_url"], headers={"X-RC-Panel": "cli"})
        assert r.status_code == 200 and r.get_json()["ok"]
        assert jobs.get(job_id)["status"] == "cancelled"
        assert _row(client, "RC-ValueChain-Sync")["stop"]["can_stop"] is False
    finally:
        jobs.cancel(job_id)


def test_a_running_job_without_checkpoints_offers_no_stop(client, fake, monkeypatch):
    monkeypatch.setattr(jobs, "_ensure_worker", lambda: None)
    monkeypatch.setattr(jobs, "_ensure_long_worker", lambda: None)
    job_id = jobs.submit("module_value_chain", {})
    try:
        jobs._set(job_id, status="running")
        stop = _row(client, "RC-ValueChain-Sync")["stop"]
        assert stop["can_stop"] is False and stop["job_id"] == job_id
        assert stop["cancel_url"] is None and stop["reason"] == A.STOP_NO_CHECKPOINT
        # and the cancel route agrees, so the row is not hiding a button that would have worked
        assert client.post(f"/api/job/{job_id}/cancel", headers={"X-RC-Panel": "cli"}).status_code == 409
    finally:
        jobs._set(job_id, status="cancelled")


def test_a_get_of_the_rows_starts_and_cancels_nothing(client, fake, monkeypatch):
    started: list = []
    monkeypatch.setattr(jobs, "submit", lambda *a, **k: started.append(a))
    monkeypatch.setattr(jobs, "cancel", lambda *a, **k: started.append(a))
    client.get("/api/automations")
    assert started == [] and fake.mutations == [] and fake.calls == []
