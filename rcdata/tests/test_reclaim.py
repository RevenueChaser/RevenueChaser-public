"""PR 2 step 1: a request a dead builder left ``running`` is reclaimed at builder start, with the dead pid named and
a ``failed`` check row; a request whose builder is still alive (a live ``.rc-proc-<pid>`` marker of that pid in the
market dir) is left alone."""
from __future__ import annotations

import subprocess
import sys

from revenuechaser.core import config, procs
from revenuechaser.rcdata import ops
from revenuechaser.rcdata.build import __main__ as cli


def _dead_pid() -> int:
    p = subprocess.Popen([sys.executable, "-c", "pass"])
    p.wait()
    assert not procs.pid_alive(p.pid)
    return p.pid


def _taken_and_started(dataset: str, run_id: str, pid: int) -> int:
    rid = ops.enqueue(dataset, None, by="test")
    assert ops.next_request(dataset)["id"] == rid
    ops.start_run(run_id, dataset, "queue")
    [run] = [r for r in ops.rows("job_runs2") if r["run_id"] == run_id]
    ops.put_rows("job_runs2", [{**run, "pid": pid}])
    return rid


def _request(rid: int) -> dict:
    return next(r for r in ops.rows("build_requests") if r["id"] == rid)


def test_a_running_request_whose_pid_is_gone_is_reclaimed_at_builder_start(monkeypatch):
    from revenuechaser.rcdata.build import due
    monkeypatch.setattr(due, "enqueue_due", lambda datasets=None, stage=None, kinds=(): [])   # this start is about the reclaim only
    dead = _dead_pid()
    rid = _taken_and_started("market_series", "dead-run", dead)
    assert cli.main(["run", "--once"]) == 0
    req = _request(rid)
    assert req["status"] == "failed"
    assert req["note"].startswith(f"lost: pid {dead} gone")
    check = ops.latest_check("market_series")
    assert check["result"] == "failed" and check["note"].startswith(f"lost: pid {dead} gone")
    [run] = [r for r in ops.rows("job_runs2") if r["run_id"] == "dead-run"]
    assert run["status"] == "failed" and f"lost: pid {dead} gone" in run["error"]


def test_a_running_request_without_a_run_row_is_reclaimed_with_the_pid_unknown():
    rid = ops.enqueue("market_series", None, by="test")
    ops.next_request()                                     # taken, then the builder died before start_run
    assert ops.fail_orphans() == (1, 0)
    req = _request(rid)
    assert req["status"] == "failed" and req["note"].startswith("lost: pid unknown")
    assert ops.latest_check("market_series")["result"] == "failed"


def test_a_running_request_whose_builder_is_alive_is_left_alone():
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        config.MARKET_DIR.mkdir(parents=True, exist_ok=True)
        start = procs.process_start_time(sleeper.pid) or ""
        (config.MARKET_DIR / f".rc-proc-{sleeper.pid}").write_text(f"{sleeper.pid} {start}".strip(),
                                                                  encoding="ascii")
        rid = _taken_and_started("market_series", "live-run", sleeper.pid)
        assert ops.fail_orphans() == (0, 0)
        assert _request(rid)["status"] == "running"
        assert ops.latest_check("market_series") is None
    finally:
        sleeper.kill()
        sleeper.wait()
    # Once that builder is gone, the next start reclaims it.
    assert ops.fail_orphans() == (1, 1)
    assert _request(rid)["note"].startswith(f"lost: pid {sleeper.pid} gone")


# #602: between builder starts (the timer is off), a reader closes what a SIGKILL or an OOM kill left running.

def test_a_request_whose_run_pid_is_gone_is_closed_without_a_builder_start():
    dead = _dead_pid()
    rid = _taken_and_started("market_series", "killed-run", dead)
    assert ops.fail_dead_requests() == (1, 1)
    req = _request(rid)
    assert req["status"] == "failed" and req["note"].startswith(f"lost: pid {dead} gone")
    [run] = [r for r in ops.rows("job_runs2") if r["run_id"] == "killed-run"]
    assert run["status"] == "failed"
    assert ops.fail_dead_requests() == (0, 0)                  # idempotent


def test_a_request_with_no_run_row_yet_is_left_to_the_builder():
    rid = ops.enqueue("market_series", None, by="test")
    ops.next_request()                                     # just taken: its run row may be a moment away
    assert ops.fail_dead_requests() == (0, 0)
    assert _request(rid)["status"] == "running"


def test_a_request_whose_run_pid_is_alive_is_left_alone_even_without_a_builder_marker():
    sleeper = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    try:
        rid = _taken_and_started("market_series", "live-cli-run", sleeper.pid)   # a cli run marks no presence
        assert ops.fail_dead_requests() == (0, 0)
        assert _request(rid)["status"] == "running"
    finally:
        sleeper.kill()
        sleeper.wait()


def test_the_data_health_page_read_closes_a_request_whose_run_was_killed():
    """#602: the board's own queue rows (the Stop buttons) come from this read, not from /api/build/queue."""
    from revenuechaser.module_settings import report
    rid = _taken_and_started("market_series", "killed-page-run", _dead_pid())
    nd = report._collect_newdata()
    assert all(r["id"] != rid for r in (nd.get("queue") or {}).get("active", []))
    assert _request(rid)["status"] == "failed"


def test_a_reader_leaves_a_run_another_host_started_alone():
    """#611: a pid is only meaningful on the host that wrote it, so the queue sweep skips another host's run."""
    rid = _taken_and_started("market_series", "other-host-run", _dead_pid())
    [run] = [r for r in ops.rows("job_runs2") if r["run_id"] == "other-host-run"]
    ops.put_rows("job_runs2", [{**run, "host": "some-other-host"}])
    assert ops.fail_dead_requests() == (0, 0)
    assert _request(rid)["status"] == "running"


# #815: the same reclaim, worded from the kernel's own log when that is what killed the builder.

def test_a_request_the_kernel_oom_killed_says_so_instead_of_pid_gone(monkeypatch):
    from revenuechaser.core import oom
    dead = _dead_pid()
    monkeypatch.setenv(oom.ENV, "1")
    monkeypatch.setattr(oom, "_journal",
                        lambda since: f"Out of memory: Killed process {dead} (python3) total-vm:41288104kB")
    rid = _taken_and_started("market_series", "oom-run", dead)
    assert ops.fail_dead_requests() == (1, 1)
    req = _request(rid)
    assert req["note"].startswith(f"lost: pid {dead} {oom.NOTE}"), req["note"]
    assert ops.latest_check("market_series")["note"].startswith(f"lost: pid {dead} {oom.NOTE}")
    [run] = [r for r in ops.rows("job_runs2") if r["run_id"] == "oom-run"]
    assert f"lost: pid {dead} {oom.NOTE}" in run["error"]


def test_a_run_the_kernel_did_not_kill_keeps_the_note_it_had(monkeypatch):
    from revenuechaser.core import oom
    dead = _dead_pid()
    monkeypatch.setenv(oom.ENV, "1")
    monkeypatch.setattr(oom, "_journal", lambda since: "Out of memory: Killed process 999999 (someone-else)")
    rid = _taken_and_started("market_series", "sigkill-run", dead)
    assert ops.fail_dead_requests() == (1, 1)
    assert _request(rid)["note"].startswith(f"lost: pid {dead} gone")


# #1239: a job the dashboard ran, swept after the dashboard's own process went away (a restart), is not a builder
# failure and has no duration -- four news_headlines rows read as 45-minute runs against a 6 s median that way.

def _dashboard_run(run_id: str, pid: int, job: str = "news_headlines", trigger: str = "dashboard",
                   dataset: str | None = None) -> dict:
    ops.start_run(run_id, dataset, trigger, job=job)
    [run] = [r for r in ops.rows("job_runs2") if r["run_id"] == run_id]
    ops.put_rows("job_runs2", [{**run, "pid": pid}])
    return run


def _run_row(run_id: str) -> dict:
    return next(r for r in ops.rows("job_runs2") if r["run_id"] == run_id)


def test_a_dashboard_job_whose_dashboard_went_away_is_interrupted_not_a_builder_failure():
    dead = _dead_pid()
    _dashboard_run("news-cut", dead)
    assert ops.fail_orphans() == (0, 1)
    run = _run_row("news-cut")
    assert run["status"] == ops.INTERRUPTED == "interrupted"
    assert "builder died" not in run["error"] and "the dashboard" in run["error"]
    assert str(dead) in run["error"]


def test_an_interrupted_dashboard_job_records_no_end_time():
    """The only end time the sweeper knows is its own clock, so the row keeps none and shows no duration."""
    from revenuechaser.app import runview
    _dashboard_run("news-no-end", _dead_pid())
    assert ops.fail_orphans() == (0, 1)
    run = _run_row("news-no-end")
    assert run["finished_at"] is None
    assert runview.view_row(run)["duration_s"] is None


def test_an_interrupted_run_is_not_counted_as_a_problem():
    """It is a run with no outcome, not a fault: the Runs tab's "Problems only" switch must not keep it."""
    from revenuechaser.app import activity, runview
    _dashboard_run("news-not-bad", _dead_pid())
    ops.fail_orphans()
    row = runview.view_row(_run_row("news-not-bad"))
    assert row["status"] not in runview.BAD and row["status"] not in activity.BAD_STATUS
    assert runview.matches(row, problems=True, query="") is False


def test_the_queue_read_interrupts_a_dashboard_job_the_same_way():
    """#602's reader path (the dashboard's own start, ``fail_dead_requests``) words it the same, from its own pid."""
    _dashboard_run("news-queue-read", _dead_pid())
    assert ops.fail_dead_requests() == (0, 1)
    run = _run_row("news-queue-read")
    assert run["status"] == ops.INTERRUPTED and run["finished_at"] is None
    assert "builder died" not in run["error"]


def test_a_board_build_is_failed_in_the_same_sweep_that_interrupts_a_dashboard_job():
    """A build run asked for from a board carries the trigger ``dashboard`` too, but it ran in the builder: the
    dataset is what tells them apart, so one sweep words the two rows differently."""
    build_pid, job_pid = _dead_pid(), _dead_pid()
    rid = _taken_and_started("market_series", "board-build", build_pid)
    ops.put_rows("job_runs2", [{**_run_row("board-build"), "trigger": "dashboard"}])
    _dashboard_run("news-beside-build", job_pid)
    assert ops.fail_orphans() == (1, 2)
    build = _run_row("board-build")
    assert build["status"] == "failed" and build["finished_at"] is not None
    assert build["error"].startswith(f"lost: pid {build_pid} gone")
    assert _request(rid)["status"] == "failed"
    job = _run_row("news-beside-build")
    assert job["status"] == ops.INTERRUPTED and job["finished_at"] is None


def test_a_scheduled_task_is_failed_in_the_same_sweep_that_interrupts_a_dashboard_job():
    """Only the dashboard's own lane is interrupted: a task runner whose process died is a real failure (#1239)."""
    _dashboard_run("task-dead", _dead_pid(), job="RC-Forecast-Outcomes", trigger="schedule")
    _dashboard_run("news-beside-task", _dead_pid())
    assert ops.fail_orphans() == (0, 2)
    task = _run_row("task-dead")
    assert task["status"] == "failed" and task["finished_at"] is not None
    job = _run_row("news-beside-task")
    assert job["status"] == ops.INTERRUPTED and job["finished_at"] is None


def test_a_dashboard_job_the_kernel_oom_killed_stays_a_failure_that_says_so(monkeypatch):
    """#815's wording wins over the restart wording: an OOM kill is a fault, and only that pid's row gets it."""
    from revenuechaser.core import oom
    killed, restarted = _dead_pid(), _dead_pid()
    monkeypatch.setenv(oom.ENV, "1")
    monkeypatch.setattr(oom, "_journal", lambda since: f"Out of memory: Killed process {killed} (python3)")
    _dashboard_run("news-oom", killed)
    _dashboard_run("news-restart", restarted)
    assert ops.fail_orphans() == (0, 2)
    oom_row = _run_row("news-oom")
    assert oom_row["status"] == "failed" and oom_row["finished_at"] is not None
    assert f"lost: pid {killed} {oom.NOTE}" in oom_row["error"]
    assert _run_row("news-restart")["status"] == ops.INTERRUPTED
