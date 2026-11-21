"""The Stop a scheduled-job row offers, and the reason a row has none (#165).

avo's decision of 20 Nov 2026 ("1 olsun", option (a)): the only stop is the **cooperative** cancel of the dashboard
job a task queues. No ``Scheduler.stop``, no ``stop`` in ``ACTIONS``, no privileged verb, nothing that can land in
the middle of a DuckDB write. So this is all read-only serving: a row says whether there is something to stop and,
when there is, which job id the existing ``POST /api/job/<id>/cancel`` stops; otherwise it says why there is none.
"""
from __future__ import annotations

from datetime import datetime, timezone

from RevenueChaser.core import automations as A
from RevenueChaser.scripts import board_fetch

NOW = datetime(2026, 11, 21, 12, 0, tzinfo=timezone.utc)


def _entry(name: str) -> A.AutomationEntry:
    return A.entry(name)


# --- which dashboard job a task queues ---------------------------------------------


def test_board_fetch_rows_name_the_route_their_own_command_posts():
    """The mapping is read off the task's own ``args``, so a new board row needs no second table."""
    for e in A.REGISTRY:
        if len(e.args) == 3 and e.args[1] == "RevenueChaser.scripts.board_fetch":
            assert A.dashboard_job_modules(e) == (board_fetch.ROUTES[e.args[2]],), e.name


def test_the_two_tasks_that_post_their_own_run_are_named():
    assert A.dashboard_job_modules(_entry("RC-ValueChain-Sync")) == ("module_value_chain",)
    assert A.dashboard_job_modules(_entry("RC-SPX-Gamma-Fetch")) == ("spxgamma",)


def test_a_task_that_runs_in_its_own_process_queues_no_dashboard_job():
    # The builder, the backups, the login check and the scoring pass write from their own process.
    for name in ("RC-Build", "RC-SEC-Read", "RC-Backup-Weekly", "RC-Backup-Watchlists-Daily",
                 "RC-IBKR-Login-Check", "RC-Relatedness-Score", "RC-Forecast-Outcomes"):
        assert A.dashboard_job_modules(_entry(name)) == (), name


def test_every_named_module_is_a_job_the_dashboard_registers():
    """A name no runner is registered under could never be stopped, and would be a silent dead button."""
    from RevenueChaser.app import dashboard  # registers the runners  # noqa: F401
    from RevenueChaser.app import jobs

    for e in A.REGISTRY:
        for module in A.dashboard_job_modules(e):
            assert module in jobs.registered(), f"{e.name} -> {module}"


# --- the row's stop ----------------------------------------------------------------


def test_a_row_whose_job_the_os_runs_has_no_stop_and_says_why():
    s = A.stop_state(_entry("RC-Build"), None)
    assert s["can_stop"] is False and s["job_id"] is None and s["cancel_url"] is None
    assert s["reason"] == A.STOP_NOT_DASHBOARD


def test_a_dashboard_row_with_nothing_running_has_no_stop_and_says_why():
    s = A.stop_state(_entry("RC-ValueChain-Sync"), None)
    assert s["can_stop"] is False and s["job_id"] is None and s["cancel_url"] is None
    assert s["reason"] == A.STOP_NOT_RUNNING


def test_a_queued_job_can_be_stopped_at_once():
    job = {"id": "abc123", "status": "queued", "cancellable": False}
    s = A.stop_state(_entry("RC-ValueChain-Sync"), job)
    assert s["can_stop"] is True
    assert s["job_id"] == "abc123" and s["cancel_url"] == "/api/job/abc123/cancel"


def test_a_running_job_with_checkpoints_can_be_stopped():
    job = {"id": "dd", "status": "running", "cancellable": True}
    s = A.stop_state(_entry("RC-Fetch-Swing"), job)
    assert s["can_stop"] is True and s["cancel_url"] == "/api/job/dd/cancel"


def test_a_running_job_without_checkpoints_refuses_and_says_why():
    """``jobs.cancel`` refuses it, so the row must not offer a button that would only answer 409."""
    job = {"id": "dd", "status": "running", "cancellable": False}
    s = A.stop_state(_entry("RC-ValueChain-Sync"), job)
    assert s["can_stop"] is False and s["job_id"] == "dd" and s["cancel_url"] is None
    assert s["reason"] == A.STOP_NO_CHECKPOINT


def test_a_finished_job_is_not_a_stop():
    for status in ("done", "error", "cancelled", "lost"):
        s = A.stop_state(_entry("RC-ValueChain-Sync"), {"id": "x", "status": status, "cancellable": True})
        assert s["can_stop"] is False and s["reason"] == A.STOP_NOT_RUNNING, status


def test_no_reason_names_a_kill_or_a_privileged_verb():
    """Option (c) was declined: no wording here may promise a stop of an OS-started run."""
    for text in (A.STOP_NOT_DASHBOARD, A.STOP_NOT_RUNNING, A.STOP_NO_CHECKPOINT):
        low = text.lower()
        assert "kill" not in low and "sudo" not in low and "systemctl" not in low


# --- the stop is serving only ------------------------------------------------------


def test_stop_is_not_an_action_and_the_scheduler_has_no_stop():
    assert "stop" not in A.ACTIONS
    assert not hasattr(A.Scheduler, "stop")
    for name in ("install", "enable", "disable", "remove", "run"):
        assert name in A.ACTIONS


def test_every_live_row_carries_a_stop():
    rows = A.live_state(A.FakeScheduler(), NOW)["rows"]
    assert len(rows) == len(A.REGISTRY)
    for r in rows:
        assert set(r["stop"]) == {"can_stop", "job_id", "cancel_url", "reason"}
        assert r["stop"]["can_stop"] is False          # no lookup was given, so nothing is running


def test_live_state_asks_the_lookup_only_for_the_rows_that_have_a_dashboard_job():
    asked: list[tuple[str, ...]] = []

    def lookup(modules):
        asked.append(modules)
        return {"id": "j1", "status": "running", "cancellable": True}

    rows = {r["name"]: r for r in A.live_state(A.FakeScheduler(), NOW, active_job=lookup)["rows"]}
    assert asked and all(m for m in asked)
    assert ("module_value_chain",) in asked
    assert rows["RC-ValueChain-Sync"]["stop"]["can_stop"] is True
    assert rows["RC-Build"]["stop"]["job_id"] is None    # never asked for: the OS runs it
