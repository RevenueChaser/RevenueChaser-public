"""``GET /api/automations`` carries each row's Stop, and the Stop is the cancel route that already exists (#165).

avo's decision (a), 20 Nov 2026: a row's Stop is ``POST /api/job/<id>/cancel`` on the dashboard job the task
queues, and a job the OS started has no Stop. So no route is added here: the panel is told which id to cancel.
"""
from __future__ import annotations

import pytest

from revenuechaser.app import dashboard, jobs
from revenuechaser.core import automations as A


@pytest.fixture
def fake():
    f = A.FakeScheduler()
    A.set_scheduler(f)
    yield f
    A.set_scheduler(None)


@pytest.fixture
def client():
    return dashboard.app.test_client()


def _no_worker(monkeypatch) -> None:
    """Keep a submitted job queued. Patching ``_ensure_*`` alone is not enough: a worker an earlier test of the same
    process started is still alive and would take the job off the shared queue (then the cancel answers 409). Fresh
    queues reach no live worker, because a worker reads the queue object it was started with (``_worker_loop``)."""
    import queue
    monkeypatch.setattr(jobs, "_ensure_worker", lambda: None)
    monkeypatch.setattr(jobs, "_ensure_long_worker", lambda: None)
    monkeypatch.setattr(jobs, "_JOB_QUEUE", queue.Queue())
    monkeypatch.setattr(jobs, "_LONG_QUEUE", queue.Queue())


def _row(client, name: str) -> dict:
    rows = client.get("/api/automations").get_json()["rows"]
    return next(r for r in rows if r["name"] == name)


def test_each_row_says_whether_it_has_a_stop_and_the_get_itself_changes_nothing(client, fake, monkeypatch):
    """One test, because the halves are only evidence together: a GET that starts nothing is as true on the
    merge-base, so it proves nothing on its own (``scripts/red_on_base.py``); tied to the field this change
    adds, it says that the field is served without the route starting or cancelling a job."""
    touched: list = []
    monkeypatch.setattr(jobs, "submit", lambda *a, **k: touched.append(("submit", a)))
    monkeypatch.setattr(jobs, "cancel", lambda *a, **k: touched.append(("cancel", a)))
    rows = client.get("/api/automations").get_json()["rows"]
    assert touched == [] and fake.mutations == []
    # Reading each task's state is the one thing a GET may do; nothing else was asked of the scheduler.
    assert {c[0] for c in fake.calls} == {"status"}
    assert all("stop" in r for r in rows)
    assert _row(client, "RC-Build")["stop"]["reason"] == A.STOP_NOT_DASHBOARD
    assert _row(client, "RC-ValueChain-Sync")["stop"]["reason"] == A.STOP_NOT_RUNNING
    # The stop is the cancel route, so the action route gained nothing. Asserted here rather than on its own:
    # alone it would pass on the merge-base and prove nothing (``scripts/red_on_base.py``).
    r = client.post("/api/automations/RC-ValueChain-Sync/stop", headers={"X-RC-Panel": "automations"})
    assert r.status_code == 400 and fake.mutations == []


def test_a_queued_job_shows_on_its_row_and_that_id_is_the_one_the_cancel_route_stops(client, fake, monkeypatch):
    """End to end on the queued side: the row's ``cancel_url`` is a route that really cancels that job."""
    _no_worker(monkeypatch)
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
    _no_worker(monkeypatch)
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
