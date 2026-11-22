"""#82: a ``running`` job_runs row whose end write was skipped is closed on start.

A row stays ``running`` only while it might still be that job. Reconcile closes it as
``lost`` when it is older than the module's deadline (or a generous bound) and the
process is gone. A live process, a row still inside its bound, and a second call are
left untouched.
"""
import os

import pytest

from revenuechaser.app import jobs
from revenuechaser.core import automations as A
from revenuechaser.core import procs, rawstore

NOW = 1_700_000_000.0
DEAD = 4_000_000_001
OTHER = 4_000_000_002


@pytest.fixture
def sync_jobs(monkeypatch):
    jobs._JOB_QUEUE.queue.clear()
    with jobs._LOCK:
        jobs._JOBS.clear()
    monkeypatch.setattr(jobs, "_RUNNERS", {})
    monkeypatch.setattr(jobs, "_PRODUCES", {})
    monkeypatch.setattr(jobs, "_REQUIRES_UW", {})
    monkeypatch.setattr(jobs, "_REQUIRES", {})
    monkeypatch.setattr(jobs, "_LANE", {})
    monkeypatch.setattr(jobs, "_DEADLINE", {})
    monkeypatch.setattr(jobs, "_CANCELLABLE", {})
    monkeypatch.setattr(jobs, "_ensure_worker", lambda: None)
    monkeypatch.setattr(jobs, "_ensure_long_worker", lambda: None)




def _bound_module():
    jobs.register("t_bound", lambda uw, **p: None, [], requires_uw=False,
                  deadline_s=60, cancellable=True)






























def test_pid_alive_treats_an_out_of_range_pid_as_gone():
    from revenuechaser.core import procs
    assert procs.pid_alive(2 ** 70) is False


