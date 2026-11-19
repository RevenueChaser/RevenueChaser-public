"""``core/oom.py``: a request the kernel OOM-killed says so, instead of ``lost: pid <n> gone`` (#815).

The lines are the kernel's own, as the journal held them on homesrv on 12 Nov 2026 for the two kills that stood
behind that note.
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import oom

OOM_KILL = ("oom-kill:constraint=CONSTRAINT_NONE,nodemask=(null),cpuset=life-rc-builder.service,"
            "mems_allowed=0,oom_memcg=/system.slice/life-rc-builder.service,"
            "task_memcg=/system.slice/life-rc-builder.service,task=python3,pid=2098,uid=1000")
KILLED = "Out of memory: Killed process 2098 (python3) total-vm:41288104kB, anon-rss:30811264kB, UID:1000"
OTHER = "python3 invoked oom-killer: gfp_mask=0x140cca(GFP_HIGHUSER_MOVABLE|__GFP_COMP), order=0"


def test_the_kernels_two_lines_for_a_kill_both_name_the_pid():
    assert oom.names_pid(OOM_KILL, 2098) and oom.names_pid(KILLED, 2098)
    assert oom.names_pid(f"{OTHER}\n{OOM_KILL}\n{KILLED}\n", 2098)


def test_another_processs_kill_is_not_this_runs():
    assert not oom.names_pid(f"{OOM_KILL}\n{KILLED}", 2099)


def test_a_line_that_only_carries_the_number_is_no_evidence():
    """The reclaim words a failure from this: a line has to be one the kernel writes for a kill."""
    assert not oom.names_pid("systemd[1]: Started life-rc-builder.service with main pid 2098", 2098)
    assert not oom.names_pid(OTHER.replace("order=0", "order=2098"), 2098)


def test_the_journal_is_asked_for_what_came_after_the_run_started(monkeypatch):
    monkeypatch.setenv(oom.ENV, "1")
    asked = []
    assert oom.killed(2098, since=1763000000.0, read=lambda since: asked.append(since) or KILLED)
    assert asked == [1763000000.0]


def test_a_journal_that_cannot_be_read_is_no_evidence(monkeypatch):
    monkeypatch.setenv(oom.ENV, "1")
    assert not oom.killed(2098, read=lambda since: "")


def test_a_reader_that_raises_never_fails_the_reclaim(monkeypatch):
    monkeypatch.setenv(oom.ENV, "1")

    def boom(since):
        raise OSError("journalctl: Operation not permitted")

    assert not oom.killed(2098, read=boom)


@pytest.mark.parametrize("pid", [None, 0, -1])
def test_no_pid_is_no_evidence(pid):
    assert not oom.killed(pid, read=lambda since: KILLED)


def test_the_lever_off_reads_nothing(monkeypatch):
    """What the test suite runs with: a runner's journal is not this machine's."""
    monkeypatch.setenv(oom.ENV, "0")

    def never(since):
        raise AssertionError("the journal was read with the lever off")

    assert not oom.killed(2098, read=never)
