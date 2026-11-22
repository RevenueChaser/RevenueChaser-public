"""Did the kernel kill this process for memory? (#815)

A builder the kernel OOM-kills leaves the request it held ``running``, and the next start closes it with
``lost: pid <n> gone`` (``rcdata/ops.py``, :func:`~revenuechaser.rcdata.ops.fail_orphans`). On 12 Nov 2026 that
note stood for two **kernel OOM kills**, and it reads like a mystery crash: nothing on the Logs board said the
machine had run out of memory, so the next pass simply repeated the same work.

The evidence the app was not reading is the kernel's own log::

    oom-kill:constraint=CONSTRAINT_NONE ... task_memcg=/system.slice/life-rc-builder.service,task=python3,pid=2098
    Out of memory: Killed process 2098 (python3) total-vm:41288104kB ...

Of the three places the issue weighed it up, this is the journal, read by **pid** at the moment the request is
closed: a systemd ``ExecStopPost`` would have to be installed on the unit on the server (another repository) before
any note could say anything, and the cgroup's ``memory.events`` ``oom_kill`` counter is reset when systemd recreates
the service's cgroup on the restart that does the reading. The journal is the one source that still holds the
answer after the process and its cgroup are gone, and the pid in it is the pid the queue already stores.

The read never decides anything: it only words a note. It is bounded (:data:`TIMEOUT_S`, and the journal is asked
only for what was logged since the run started), it never raises, and ``RC_OOM_JOURNAL=0`` turns it off — which is
what the test suite does, because a runner's journal is not this machine's and a test may not depend on it.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess

#: How long the journal read may take before it is given up on. The note is worth a moment, not a wait.
TIMEOUT_S = 5.0
#: ``RC_OOM_JOURNAL=0`` answers "no evidence" without reading anything.
ENV = "RC_OOM_JOURNAL"
#: What the note says when the kernel's log names the pid.
NOTE = "killed by the kernel: out of memory"

#: ``Out of memory: Killed process 2098 (python3) ...`` — the kill itself.
_KILLED = re.compile(r"Killed process\s+(\d+)\b")
#: ``oom-kill:constraint=... ,task=python3,pid=2098,uid=...`` — the same kill, as the cgroup accounting writes it.
_OOM_KILL = re.compile(r"oom-kill:.*?\bpid=(\d+)\b")


def names_pid(text: str, pid: int) -> bool:
    """Whether ``text`` (kernel log lines) holds an out-of-memory kill of ``pid``.

    A line is read only when it is one of the two the kernel writes for a kill, so an unrelated line that happens
    to carry the number is no evidence.
    """
    for line in text.splitlines():
        for found in (_KILLED.search(line), _OOM_KILL.search(line)):
            if found and int(found.group(1)) == pid:
                return True
    return False


def _journal(since: float | None) -> str:
    """The kernel's log since ``since`` (epoch seconds), empty when it cannot be read — which is the usual answer
    off the server: no ``journalctl``, no permission, another platform."""
    if os.name == "nt":
        return ""
    found = shutil.which("journalctl")
    if not found:
        return ""
    cmd = [found, "-k", "--no-pager", "-o", "cat"]
    if since:
        cmd += ["--since", f"@{int(since)}"]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S, check=False)
    except (OSError, subprocess.SubprocessError):
        return ""
    return done.stdout if done.returncode == 0 else ""


def killed(pid: int | None, *, since: float | None = None, read=None) -> bool:
    """Whether the kernel's log says it killed ``pid`` for memory; False whenever it cannot be known.

    ``since`` is when the run started: the log is asked for what came after it, so a pid the kernel killed and the
    system has since handed out again is not read as this run's death.
    """
    if not pid or pid <= 0 or os.getenv(ENV, "").strip() == "0":
        return False
    try:
        # Looked up here, not bound as a default, so a test can put its own lines in front of the real reader.
        text = (read or _journal)(since)
    except Exception:                                   # a note is never worth a failure of the reclaim
        return False
    return bool(text) and names_pid(text, pid)
