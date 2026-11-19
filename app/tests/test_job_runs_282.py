"""#282 J4: every dashboard job leaves one run-log row, and a failing write never fails the job.

The row was ``job_runs`` in the old raw.duckdb and went with it (#860). Since #136 it is a row of
``ops.job_runs2``: ``job`` is the job's module, ``trigger`` is ``dashboard``, and ``counts`` is what the runner
counted — which ``_set`` used to drop for want of a destination.
"""

import pytest

from RevenueChaser.app import jobs
from RevenueChaser.core import ledger, rawstore


class _FakeUW:
    active = True

    def verify(self):
        return True, None


@pytest.fixture
def sync_jobs(monkeypatch):
    jobs._JOB_QUEUE.queue.clear()
    with jobs._LOCK:
        jobs._JOBS.clear()
    monkeypatch.setattr(jobs, "_RUNNERS", {})
    monkeypatch.setattr(jobs, "_PRODUCES", {})
    monkeypatch.setattr(jobs, "_ensure_worker", lambda: None)
    monkeypatch.setattr(jobs, "_ensure_long_worker", lambda: None)
    monkeypatch.setattr(jobs, "UWClient", lambda: _FakeUW())
    monkeypatch.setattr(jobs, "_LANE", dict(jobs._LANE))


def test_run_id_is_the_running_jobs_id_and_a_fresh_one_outside(sync_jobs):
    seen = []
    jobs.register("t_r", lambda uw, **p: seen.append(jobs.run_id()), [], requires_uw=False)
    jid = jobs.submit("t_r")
    jobs.execute(jid)
    assert seen == [jid]
    a, b = jobs.run_id(), jobs.run_id()
    assert a != b and len(a) == len(ledger.new_run_id())


def test_job_semantics_are_unchanged_by_the_new_row(sync_jobs):
    jobs.register("t_s", lambda uw, **p: None, [], requires_uw=False)
    jid = jobs.submit("t_s")
    jobs.execute(jid)
    # #243 added the deadline and cancel fields to the job JSON; the job_runs row needed no new column.
    assert set(jobs.get(jid)) == {"id", "module", "params", "status", "produces", "queued_at", "started_at",
                                  "finished_at", "error", "message", "notes", "lane",
                                  "deadline_s", "deadline_at", "cancellable", "cancel_requested", "phase"}




# --- the run-log row (#136) ------------------------------------------------------------------------------------

def test_a_dashboard_job_records_its_row_and_the_runners_counts(sync_jobs):
    from RevenueChaser.rcdata import ops
    jobs.register("t_counts", lambda uw, **p: {"counts": {"rows": 12, "frozen": 4}}, [], requires_uw=False)
    jid = jobs.submit("t_counts")
    jobs.execute(jid)
    [run] = ops.job_runs()
    assert run["run_id"] == jid and run["job"] == "t_counts" and run["trigger"] == "dashboard"
    assert run["status"] == "done" and run["counts"] == {"rows": 12, "frozen": 4}
    assert ops.last_builder_run() is None          # it is not a dataset build


def test_a_runner_that_ends_with_a_message_records_its_counts(sync_jobs):
    """The long writers raise ``JobMessage`` rather than returning, so #136 gave it a ``counts`` keyword."""
    from RevenueChaser.rcdata import ops

    def ends_with_a_message(uw, **params):
        raise jobs.JobMessage("Wrote 9 rows.", {"rows": 9})

    jobs.register("t_msg", ends_with_a_message, [], requires_uw=False)
    jid = jobs.submit("t_msg")
    jobs.execute(jid)
    [run] = ops.job_runs()
    assert run["status"] == "done" and run["counts"] == {"rows": 9}


def test_a_failed_job_records_its_error(sync_jobs):
    from RevenueChaser.rcdata import ops

    def boom(uw, **params):
        raise ValueError("no")

    jobs.register("t_boom", boom, [], requires_uw=False)
    jid = jobs.submit("t_boom")
    jobs.execute(jid)
    [run] = ops.job_runs()
    assert run["status"] == "error" and run["error"] and run["counts"] is None


def test_an_ops_store_that_refuses_the_row_does_not_fail_the_job(sync_jobs, monkeypatch):
    from RevenueChaser.rcdata import ops

    def refuse(*a, **k):
        raise RuntimeError("ops store is busy")

    monkeypatch.setattr(ops, "start_run", refuse)
    monkeypatch.setattr(ops, "finish_run", refuse)
    jobs.register("t_busy", lambda uw, **p: {"counts": {"rows": 1}}, [], requires_uw=False)
    jid = jobs.submit("t_busy")
    jobs.execute(jid)
    assert jobs.get(jid)["status"] == "done"


def test_counts_stay_out_of_the_job_json(sync_jobs):
    """The dashboard poll reads the job dict; ``counts`` is not one of its fields."""
    jobs.register("t_json", lambda uw, **p: {"counts": {"rows": 3}}, [], requires_uw=False)
    jid = jobs.submit("t_json")
    jobs.execute(jid)
    assert "counts" not in jobs.get(jid)
