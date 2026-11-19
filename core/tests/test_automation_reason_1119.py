"""A failed scheduled run names its reason on ``run_task``'s own stdout (#1119).

``run_task`` sends its command's output to ``<entry>.log`` and used to print nothing itself. On the server it is
a child of home-server's ``jobrun``, which keeps a job's **last printed line** as its ``job_runs.message`` and
writes the stream to its own log and the journal. So a failed hourly job showed "exit 1" with no reason in all
three of those places, and only ``<entry>.log`` held it (RC-Build, 19 Nov 2026: eight red rows, every message
empty).
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import automations as A

FAILS = A.AutomationEntry(name="RC-Red", label="red", time="22:35", description="d",
                          args=("-c", "import sys; print('stage one ok'); "
                                      "print('fetch failed: SourceError: sec.gov said 504'); sys.exit(1)"))
WORKS = A.AutomationEntry(name="RC-Green", label="green", args=("-c", "print('all good')"),
                          time="22:40", description="d")
QUIET = A.AutomationEntry(name="RC-Mute", label="mute", args=("-c", "import sys; sys.exit(2)"),
                          time="22:45", description="d")


@pytest.fixture(autouse=True)
def _registry(tmp_path, monkeypatch):
    monkeypatch.setattr(A.config, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(A, "_BY_NAME", {e.name: e for e in (FAILS, WORKS, QUIET)})
    A.set_scheduler(None)
    yield
    A.set_scheduler(None)


def test_a_failed_run_echoes_its_exit_code_its_last_line_and_the_log(capsys):
    assert A.run_task(FAILS.name) == 1
    [said] = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("RC-Red ")]
    assert said.startswith("RC-Red exit 1: fetch failed: SourceError: sec.gov said 504")
    assert str(FAILS.log_path) in said          # where the whole output is
    # The log itself is unchanged: the echo is this process's stdout, not a line in the entry's log.
    assert "RC-Red exit 1:" not in FAILS.log_path.read_text(encoding="utf-8")


def test_a_run_that_exits_0_echoes_nothing(capsys):
    assert A.run_task(WORKS.name) == 0
    assert capsys.readouterr().out == ""


def test_a_failed_run_that_said_nothing_still_names_its_exit_code(capsys):
    assert A.run_task(QUIET.name) == 2
    [said] = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("RC-Mute ")]
    assert said == f"RC-Mute exit 2 (log: {QUIET.log_path})"


def test_the_reason_is_this_runs_own_output_not_an_earlier_runs(capsys):
    """The log is appended to for ever, so a run that says nothing must not borrow last night's reason."""
    QUIET.log_path.parent.mkdir(parents=True, exist_ok=True)
    QUIET.log_path.write_text("=== 2026-11-18T19:00:00+00:00 start RC-Mute\nyesterday: fetch failed: 504\n"
                              "=== 2026-11-18T19:05:00+00:00 exit 1\n", encoding="utf-8")
    assert A.run_task(QUIET.name) == 2
    [said] = [ln for ln in capsys.readouterr().out.splitlines() if ln.startswith("RC-Mute ")]
    assert "yesterday" not in said and said == f"RC-Mute exit 2 (log: {QUIET.log_path})"


def test_last_reason_skips_this_runners_own_lines_and_never_invents_one(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("=== 2026-11-19T19:00:00+00:00 start RC-Red\nthe reason\n"
                   "=== 2026-11-19T19:05:00+00:00 exit 1\n", encoding="utf-8")
    assert A.last_reason(log, 0) == "the reason"
    assert A.last_reason(log, log.stat().st_size) == ""
    assert A.last_reason(tmp_path / "missing.log", 0) == ""


def test_a_long_reason_is_cut_where_the_job_record_cuts_it(tmp_path):
    log = tmp_path / "x.log"
    log.write_text("x" * (A.REASON_MAX + 50) + "\n", encoding="utf-8")
    assert len(A.last_reason(log, 0)) == A.REASON_MAX
