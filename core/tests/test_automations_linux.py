"""#158: the Automations panel on Linux, through systemd user timers.

Every call goes through a fake ``systemctl`` runner and a temp unit folder, so the tests stay offline and run the
same on any platform, the way ``WindowsScheduler``'s tests go through a fake PowerShell.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from RevenueChaser.core import automations as A


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setattr(A.config, "OUTPUT_DIR", tmp_path)
    A.set_scheduler(None)
    yield
    A.set_scheduler(None)


class FakeSystemctl:
    def __init__(self, out="", rc=0, err=""):
        self.calls: list[list[str]] = []
        self.out, self.rc, self.err = out, rc, err

    def __call__(self, args):
        self.calls.append(list(args))
        return self.rc, self.out, self.err


def _linux(tmp_path, sc, python="/srv/rc/.venv/bin/python", workdir="/srv/rc"):
    return A.LinuxScheduler(runner=sc, python=python, workdir=workdir, unit_dir=tmp_path / "units")


def _unit(tmp_path, name, kind):
    return (tmp_path / "units" / f"{name}.{kind}").read_text(encoding="utf-8")


def _show(timer: dict, service: dict) -> str:
    """What ``systemctl show <timer> <service>`` prints: one block per unit, a blank line between them."""
    block = lambda d: "\n".join(f"{k}={v}" for k, v in d.items())
    return block(timer) + "\n\n" + block(service) + "\n"


# --- install ----------------------------------------------------------------------





def test_on_calendar_covers_every_registry_row():
    for e in A.REGISTRY:
        spec = A.on_calendar(e)
        if e.hourly:                                   # RC-Build (PR 2): every hour at the row's minute
            assert spec == f"*-*-* *:{e.time[-2:]}:00"
            continue
        assert spec.endswith(f"*-*-* {e.time}:00")
        assert (spec.count(",") + 1 if e.days else 0) == len(e.days)














class FailOn(FakeSystemctl):
    """Fails the calls whose first word is in ``verbs``, like a missing bus or a refused unit."""

    def __init__(self, *verbs):
        super().__init__()
        self.verbs = set(verbs)

    def __call__(self, args):
        self.calls.append(list(args))
        return (1, "", "Failed to connect to bus") if args[0] in self.verbs else (0, "", "")






# --- the other four buttons ---------------------------------------------------------

def test_enable_disable_run_and_remove_name_exactly_one_registry_unit(tmp_path):
    sc = FakeSystemctl()
    s = _linux(tmp_path, sc)
    s.install(A.entry("RC-Relatedness-OffPeak"))
    sc.calls.clear()
    s.set_enabled("RC-Relatedness-OffPeak", False)
    s.set_enabled("RC-Relatedness-OffPeak", True)
    s.run("RC-Relatedness-OffPeak")
    s.remove("RC-Relatedness-OffPeak")
    assert sc.calls == [
        ["disable", "--now", "RC-Relatedness-OffPeak.timer"],
        ["enable", "--now", "RC-Relatedness-OffPeak.timer"],
        ["start", "--no-block", "RC-Relatedness-OffPeak.service"],
        ["disable", "--now", "RC-Relatedness-OffPeak.timer"],
        ["daemon-reload"],
    ]
    assert list((tmp_path / "units").iterdir()) == []


def test_a_name_outside_the_registry_is_refused_without_a_call(tmp_path):
    sc = FakeSystemctl()
    s = _linux(tmp_path, sc)
    for call in (lambda: s.status("Other"), lambda: s.remove("Other"), lambda: s.run("x; rm -rf ~"),
                 lambda: s.set_enabled("Other", False)):
        with pytest.raises(A.UnknownTask):
            call()
    assert sc.calls == []




# --- status -----------------------------------------------------------------------

_TIMER_ON = {"ActiveState": "active", "Result": "success", "NextElapseUSecRealtime": "@1792987200",
             "LastTriggerUSec": "@1792900800"}
_SERVICE_OK = {"ActiveState": "inactive", "Result": "success", "ExecMainStatus": "0",
               "ExecMainStartTimestamp": "@1792900800"}


def _iso(ts: int) -> str:
    return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat()














# --- which scheduler a host gets -----------------------------------------------------

@pytest.fixture
def linux_host(monkeypatch):
    monkeypatch.setattr(A.sys, "platform", "linux")
    monkeypatch.setattr(A.shutil, "which", lambda name: "/usr/bin/systemctl" if name == "systemctl" else None)
    monkeypatch.delenv("RC_SCHEDULER", raising=False)


def test_linux_gets_the_systemd_backend_only_when_asked_for(linux_host, monkeypatch):
    """Opt-in: a server that already runs these jobs as system timers must not be offered a second schedule."""
    assert isinstance(A.get_scheduler(), A.UnavailableScheduler)
    A.set_scheduler(None)
    monkeypatch.setenv("RC_SCHEDULER", "systemd-user")
    assert isinstance(A.get_scheduler(), A.LinuxScheduler)


def test_an_unknown_scheduler_choice_stays_unavailable(linux_host, monkeypatch):
    monkeypatch.setenv("RC_SCHEDULER", "systemd")
    assert isinstance(A.get_scheduler(), A.UnavailableScheduler)


def test_systemctl_finds_the_user_bus_when_xdg_runtime_dir_is_missing(monkeypatch):
    seen = {}

    def run(cmd, **kw):
        seen.update(cmd=cmd, env=kw.get("env"))
        return A.subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(A.subprocess, "run", run)
    monkeypatch.delenv("XDG_RUNTIME_DIR", raising=False)
    monkeypatch.setattr(A.os, "getuid", lambda: 1234, raising=False)
    A._systemctl(["daemon-reload"])
    assert seen["cmd"] == ["systemctl", "--user", "daemon-reload"]
    assert seen["env"]["XDG_RUNTIME_DIR"] == "/run/user/1234"
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/77")
    A._systemctl(["daemon-reload"])
    assert seen["env"]["XDG_RUNTIME_DIR"] == "/run/user/77"


def test_windows_is_unchanged(monkeypatch):
    monkeypatch.setattr(A.sys, "platform", "win32")
    assert isinstance(A.get_scheduler(), A.WindowsScheduler)


def test_the_default_unit_folder_follows_xdg_config_home(monkeypatch, tmp_path):
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    assert A.LinuxScheduler(runner=FakeSystemctl()).unit_dir == tmp_path / "cfg" / "systemd" / "user"


# --- #164: scripts ask the code for the task list -------------------------------------

def test_names_prints_every_registry_name_one_per_line_without_the_scheduler(capsys):
    f = A.FakeScheduler()
    A.set_scheduler(f)
    assert A.main(["names"]) == 0
    assert capsys.readouterr().out.splitlines() == [e.name for e in A.REGISTRY]
    assert f.calls == []


def test_a_relative_xdg_config_home_is_ignored(monkeypatch):
    """The XDG spec: a relative value is invalid and is ignored, never resolved against the dashboard's cwd."""
    monkeypatch.setenv("XDG_CONFIG_HOME", "relative/cfg")
    assert A.LinuxScheduler(runner=FakeSystemctl()).unit_dir == A.Path.home() / ".config" / "systemd" / "user"








