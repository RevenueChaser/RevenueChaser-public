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






def test_a_failed_reinstall_puts_the_working_pair_back(tmp_path):
    """#191 item 1: a reinstall over an installed task whose ``enable`` failed used to remove the working pair too."""
    name = "RC-Relatedness-OffPeak"
    with pytest.raises(A.AutomationError):                     # a failed first install still leaves no files
        _linux(tmp_path, FailOn("enable")).install(A.entry(name))
    assert not any((tmp_path / "units").glob(f"{name}.*"))
    _linux(tmp_path, FakeSystemctl()).install(A.entry(name))
    service, timer = _unit(tmp_path, name, "service"), _unit(tmp_path, name, "timer")
    sc = FailOn("enable")
    with pytest.raises(A.AutomationError):
        _linux(tmp_path, sc).install(A.entry(name))
    assert _unit(tmp_path, name, "service") == service and _unit(tmp_path, name, "timer") == timer
    # The other half of #191 item 2: the wants symlink of a pair this call did not create is not this call's to
    # take away -- only an install that made the pair disables it again.
    assert not any(c[0] == "disable" for c in sc.calls)


def test_a_rolled_back_first_install_leaves_no_enabled_timer(tmp_path):
    """#191 item 2: ``enable --now`` writes timers.target.wants/<name>.timer before the start can fail, and the
    rollback never disabled it, so the manager kept a symlink to a unit file that was gone."""
    calls: list[list[str]] = []

    def run(args):                                   # the symlink is written, then the start of the unit fails
        calls.append(list(args))
        return (1, "", "Job failed") if args[0] == "enable" else (0, "", "")

    with pytest.raises(A.AutomationError):
        _linux(tmp_path, run).install(A.entry("RC-Relatedness-OffPeak"))
    assert ["disable", "RC-Relatedness-OffPeak.timer"] in calls
    assert not any((tmp_path / "units").glob("RC-Relatedness-OffPeak.*"))


def test_the_timer_carries_the_zone_the_service_carries(tmp_path, monkeypatch):
    """#191 item 4: ``TZ`` goes into the service, but a bare ``OnCalendar=`` fires in the user manager's zone."""
    monkeypatch.setenv("TZ", "Europe/Amsterdam")
    e = A.entry("RC-Relatedness-OffPeak")
    _linux(tmp_path, FakeSystemctl()).install(e)
    timer = _unit(tmp_path, e.unit, "timer")
    assert f"OnCalendar={A.on_calendar(e)} Europe/Amsterdam" in timer
    # The Control board reads the minute out of ``on_calendar``, so that one stays zone-free.
    assert A.on_calendar(e).split()[-1].count(":") == 2
    # A value that is not one zone word is left off rather than written into the unit file.
    monkeypatch.setenv("TZ", "Europe/Amsterdam extra")
    _linux(tmp_path, FakeSystemctl()).install(e)
    assert f"OnCalendar={A.on_calendar(e)}\n" in _unit(tmp_path, e.unit, "timer")


def test_a_failed_timer_names_the_command_that_clears_it(tmp_path):
    """#191 item 3: the panel offers an error row no button, so the message has to say how to get out of it.
    ``systemctl status`` only prints the failure again."""
    sc = FakeSystemctl(out=_show({**_TIMER_ON, "ActiveState": "failed", "Result": "exit-code"}, _SERVICE_OK))
    s = _linux(tmp_path, sc)
    s.install(A.entry("RC-Relatedness-OffPeak"))
    with pytest.raises(A.AutomationError) as err:
        s.status("RC-Relatedness-OffPeak")
    assert "reset-failed RC-Relatedness-OffPeak.timer" in str(err.value) and "--user" in str(err.value)


def test_a_failed_system_timer_names_the_system_command(monkeypatch):
    e = A.entry("RC-Relatedness-OffPeak")
    out = _show({**_TIMER_ON, "LoadState": "loaded", "ActiveState": "failed", "Result": "exit-code"}, _SERVICE_OK)
    with pytest.raises(A.AutomationError) as err:
        A.system_status(e, run=lambda args: (0, out, ""))
    assert f"reset-failed {A.system_unit(e)}.timer" in str(err.value) and "--user" not in str(err.value)


def test_the_unit_carries_the_path_of_the_key_file_and_no_value(tmp_path, monkeypatch):
    """#191 item 6: a job systemd starts gets the allowlist and nothing else, so provider jobs ran without keys.
    systemd reads the file itself; the unit file (world-readable) holds the path only."""
    monkeypatch.setenv(A.UNIT_ENV_FILE_ENV, "/etc/example/secrets.env")
    e = A.entry("RC-Relatedness-OffPeak")
    _linux(tmp_path, FakeSystemctl()).install(e)
    service = _unit(tmp_path, e.unit, "service")
    assert "EnvironmentFile=-/etc/example/secrets.env" in service
    assert sum(1 for ln in service.splitlines() if ln.startswith("EnvironmentFile=")) == 1


def test_no_key_file_line_without_the_variable(tmp_path, monkeypatch):
    monkeypatch.delenv(A.UNIT_ENV_FILE_ENV, raising=False)
    e = A.entry("RC-Relatedness-OffPeak")
    _linux(tmp_path, FakeSystemctl()).install(e)
    assert "EnvironmentFile" not in _unit(tmp_path, e.unit, "service")


def test_a_relative_key_file_is_refused(tmp_path, monkeypatch):
    """systemd would read it against ``/``, not the dashboard's cwd: a file that is silently not there is the very
    failure this line exists to prevent."""
    monkeypatch.setenv(A.UNIT_ENV_FILE_ENV, "secrets.env")
    e = A.entry("RC-Relatedness-OffPeak")
    _linux(tmp_path, FakeSystemctl()).install(e)
    assert "EnvironmentFile" not in _unit(tmp_path, e.unit, "service")
    assert A.unit_env_file() is None


def test_an_absurd_timestamp_is_a_time_we_do_not_have(tmp_path):
    """The reviewer's nit on #191: ``infinity`` in a harness made ``_show_value`` raise OverflowError."""
    assert A._show_value("@1e308") is None
    assert A._show_value("@1792900800") is not None


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


def test_linux_gets_the_systemd_backend_only_when_asked_for(linux_host, monkeypatch, caplog):
    """Opt-in: a server that already runs these jobs as system timers must not be offered a second schedule."""
    with caplog.at_level("WARNING", logger=A.logger.name):
        assert isinstance(A.get_scheduler(), A.UnavailableScheduler)
    assert caplog.text == ""              # asking for nothing is the default, not a mistake to warn about
    A.set_scheduler(None)
    monkeypatch.setenv("RC_SCHEDULER", "systemd-user")
    assert isinstance(A.get_scheduler(), A.LinuxScheduler)


def test_an_unknown_scheduler_choice_stays_unavailable(linux_host, monkeypatch):
    monkeypatch.setenv("RC_SCHEDULER", "systemd")
    assert isinstance(A.get_scheduler(), A.UnavailableScheduler)


@pytest.mark.parametrize("value", ["systemd", "Systemd-User"])
def test_an_unknown_scheduler_choice_says_so(linux_host, monkeypatch, caplog, value):
    """#191 item 5: a near miss used to read exactly like "this host has no scheduler", with nothing said anywhere."""
    monkeypatch.setenv("RC_SCHEDULER", value)
    with caplog.at_level("WARNING", logger=A.logger.name):
        assert isinstance(A.get_scheduler(), A.UnavailableScheduler)
    assert value in caplog.text and "systemd-user" in caplog.text


def test_asking_for_systemd_without_systemctl_says_so(linux_host, monkeypatch, caplog):
    monkeypatch.setenv("RC_SCHEDULER", "systemd-user")
    monkeypatch.setattr(A.shutil, "which", lambda name: None)
    with caplog.at_level("WARNING", logger=A.logger.name):
        assert isinstance(A.get_scheduler(), A.UnavailableScheduler)
    assert "systemctl" in caplog.text


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








