"""#282 J4: every dashboard job leaves one ``job_runs`` row, and a failing write never fails the job."""

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


def test_the_row_is_stored_before_the_registry_shows_the_new_status(sync_jobs, monkeypatch):
    """A poller (the e2e harness, the UI) that sees "done" may open the store at once. If the final row were
    written after that, the dashboard's writer would still hold the file and the poller's connect would fail
    with "Conflicting lock"."""
    seen = []
    real = rawstore.write_rows

    def spy(name, rows):
        seen.append((rows[0]["status"], jobs.get(rows[0]["run_id"])["status"]))
        return real(name, rows)

    monkeypatch.setattr(rawstore, "write_rows", spy)
    jobs.register("t_order", lambda uw, **p: None, [], requires_uw=False)
    jobs.execute(jobs.submit("t_order"))
    assert seen == [("running", "running"), ("done", "running")]






def test_a_slow_store_does_not_hold_the_job_up(sync_jobs, monkeypatch):
    """The write asks for the brief lock wait (a peer holding the file would otherwise cost ~29 s per write)."""
    flags = []

    def spy(name, rows):
        flags.append(getattr(rawstore._LOCAL, "brief", False))

    monkeypatch.setattr(rawstore, "write_rows", spy)
    jobs.register("t_brief", lambda uw, **p: None, [], requires_uw=False)
    jobs.execute(jobs.submit("t_brief"))
    assert flags == [True, True]
    assert getattr(rawstore._LOCAL, "brief", False) is False
