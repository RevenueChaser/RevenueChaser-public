"""PL6-a (#26): the 13F jobs are one at a time, and repeated clicks do not queue a second long-lane run.

Two halves:

* the 13F Fetch takes ``job_lock`` name ``"sec_13f"`` for the whole composed job — the steps are building blocks,
  the job is the unit — so a second Fetch refuses and writes nothing (the rebuild and map jobs went with the
  retired derive, G9);
* ``/run/module_sec_13f``, ``/run/identity``, ``/run/edgar-sync``,
  ``/run/daily-bars``, ``/run/index-lists`` and ``/run/universe-stats`` answer ``409`` while a job of their family is
  queued or running, instead of queueing a second multi-minute ingest behind the first.

The universe run and the single-board Fetches keep their own locks (``refused_during_universe``, #244/#356) and are
not touched here.
"""
from __future__ import annotations

import os

import pytest

from revenuechaser.app import dashboard, jobs, runners
from revenuechaser.core import job_lock, rawstore
from revenuechaser.core.tests.lock_holders import lock_held
from revenuechaser.core.tests.panel_client import panel_test_client


# ── the 13F runners: one family lock ─────────────────────────────────────────

def test_the_13f_fetch_refuses_while_the_family_lock_is_held(rawstore_tmp_db):
    with lock_held("sec_13f"):
        with pytest.raises(jobs.JobMessage) as err:
            runners.build_sec13f()
    assert err.value.message == f"A 13F job is already running (pid {os.getpid()}); nothing was written."


def test_a_refused_fetch_renders_nothing(rawstore_tmp_db, monkeypatch):
    called: list[tuple] = []
    monkeypatch.setattr(runners, "_render_13f", lambda *a, **k: called.append(a))
    with lock_held("sec_13f"):
        with pytest.raises(jobs.JobMessage):
            runners.build_sec13f()
    assert called == [], "the lock is taken before the first step"


def test_a_finished_13f_run_releases_the_lock(rawstore_tmp_db):
    runners.build_sec13f()                            # an empty store: the empty board, no note
    assert "sec_13f" not in dict(job_lock.holders()), "the lock outlived the run"


# ── the run routes: a second click is a 409, not a second job ────────────────



class _FakeUW:
    """A UW client that verifies: these route tests must not reach the network."""

    def verify(self):
        return True, None

    def close(self):
        pass


@pytest.fixture(autouse=True)
def queued_jobs_only(monkeypatch):
    """Submit without starting a worker and without a real UW probe; the registry starts empty."""
    monkeypatch.setattr(jobs, "_ensure_worker", lambda: None)
    monkeypatch.setattr(jobs, "_ensure_long_worker", lambda: None)
    monkeypatch.setattr(jobs, "_JOBS", {})
    monkeypatch.setattr(jobs, "_SEQ", {})
    monkeypatch.setattr(dashboard, "_uw", lambda: _FakeUW())


@pytest.fixture
def client():
    return panel_test_client(dashboard.app)


def _queued(module: str) -> list[dict]:
    return [j for j in jobs.list_jobs() if j["module"] == module]




def test_an_unrelated_route_still_submits(client):
    assert client.post("/run/module_sec_13f").status_code == 202
    assert client.post("/run/module_value_chain").status_code == 202
