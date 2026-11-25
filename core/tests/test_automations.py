"""Automations registry and the scheduler interface (#130).

Nothing here touches a real scheduler: the tests go through ``FakeScheduler`` and a fake
``systemctl``.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from revenuechaser.core import automations as A

ROOT = Path(__file__).resolve().parents[2]
NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setattr(A.config, "OUTPUT_DIR", tmp_path)
    A.set_scheduler(None)
    yield
    A.set_scheduler(None)


# --- registry ---------------------------------------------------------------

# The Earnings inputs entries, one per schedule (#620).


_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")


def test_the_forecast_baselines_row_is_chained_on_the_outcomes_run():
    """#25 HR-1: the baselines read the same stored bars and write raw.duckdb, so they wait for tonight's
    RC-Forecast-Outcomes instead of running beside it, on their own 23:50 trigger, and write
    ``forecast_baselines`` alone."""
    e = A.entry("RC-Forecast-Baselines")
    assert (e.after, e.time, e.days) == ("RC-Forecast-Outcomes", "23:50", ())
    assert e.args == ("-m", "revenuechaser.scripts.forecast_baselines", "--nightly")
    assert e.schedule == "daily 23:50 (local), after RC-Forecast-Outcomes"
    assert e.tables_written == ("forecast_baselines",)
    assert e.chain_wait_minutes == 120 and not e.default_install and not e.offpeak_gated
    names = [x.name for x in A.REGISTRY]
    assert names.index("RC-Forecast-Outcomes") + 1 == names.index("RC-Forecast-Baselines")    # after it, never before


def test_no_row_is_marked_default_install():
    """RC-Store-Backup was the one default install; it retired with the weekly backup (avo, 8 Nov 2026)."""
    assert [e.name for e in A.REGISTRY if e.default_install] == []


def test_unknown_name_is_rejected():
    with pytest.raises(A.UnknownTask):
        A.entry("RC-Nope")
    with pytest.raises(A.UnknownTask):
        A.entry(None)  # type: ignore[arg-type]


# --- result mapping + row states ------------------------------------------------

@pytest.mark.parametrize("code,kind", [
    (None, "none"), (0, "ok"), (0x41303, "neutral"), (0x41301, "running"),
    (1, "red"), (0x80070002, "red")])
def test_result_mapping(code, kind):
    assert A.map_result(code)[0] == kind


def test_static_rows_never_touch_the_scheduler():
    f = A.FakeScheduler()
    A.set_scheduler(f)
    rows = A.static_rows()
    assert [r["name"] for r in rows] == [e.name for e in A.REGISTRY]
    assert f.calls == []
    assert "state" not in rows[0]


def test_get_scheduler_is_unavailable_without_systemd(monkeypatch):
    monkeypatch.setattr(A.sys, "platform", "linux")
    monkeypatch.setattr(A.shutil, "which", lambda name: None)
    assert A.get_scheduler().available is False


# --- actions --------------------------------------------------------------------


# --- the command a task runs ------------------------------------------------------


def test_registry_names_are_unit_name_safe():
    for e in A.REGISTRY:
        assert re.fullmatch(r"RC-[A-Za-z0-9-]+", e.name), e.name


def test_every_registry_tables_written_is_a_manifest_table():
    from revenuechaser.core import rawstore
    for e in A.REGISTRY:
        for table in e.tables_written:
            assert table in rawstore.MANIFEST, f"{e.name} names {table}, not in MANIFEST"


# --- one bad row does not take the panel down (coordinator review) -----------------

def test_one_failing_row_does_not_fail_the_others():
    class Mixed(A.FakeScheduler):
        def status(self, name):
            if name == "RC-Relatedness-OffPeak":
                raise A.AutomationError("boom")
            return super().status(name)

    rows = A.live_state(Mixed(), NOW)["rows"]
    assert [r["state"] for r in rows] == ["error"] + ["not_installed"] * (len(A.REGISTRY) - 1)
    assert "boom" in rows[0]["result_text"]


# ── #162: the IBKR Gateway login check ──────────────────────────────────────────────────────────

def test_the_ibkr_login_check_writes_no_table():
    """It records only its own file under .cache/, so it can never queue behind or hold the
    dashboard's single DuckDB writer."""
    entry = A.entry("RC-IBKR-Login-Check")
    assert entry.tables_written == ()
    assert entry.offpeak_gated is False
    assert entry.after is None, "it depends on no other run: it reports a state, it does not build data"


def test_the_ibkr_login_check_runs_the_module_it_claims_to():
    entry = A.entry("RC-IBKR-Login-Check")
    assert entry.command == "python -m revenuechaser.scripts.ibkr_login_check"


def test_the_ibkr_login_check_description_says_what_it_never_asks_for():
    """The one guard a reader of the Automations panel has against scope creep into account data."""
    text = A.entry("RC-IBKR-Login-Check").description
    for phrase in ("account", "position", "order", "execution", "RC_IBKR_LOGIN_CHECK"):
        assert phrase in text, f"the description no longer names {phrase!r}"


def test_the_ibkr_login_check_is_not_installed_by_default():
    assert A.entry("RC-IBKR-Login-Check").default_install is False


# --- the market-store builder as a service (PR 2 step 2) ----------------------------------------------------------

class _FakeSystemctl:
    def __init__(self):
        self.calls: list[list[str]] = []

    def __call__(self, args):
        self.calls.append(list(args))
        return 0, "", ""


def test_the_storage_build_runs_every_hour_at_05_and_the_storage_fetch_at_45():
    """avo, 24 Nov 2026: the hourly pass split in two timers, a fetch that never builds and a build he switches."""
    f = A.entry("RC-Store-Fetch")
    assert f.args == ("-m", "revenuechaser.rcdata.build", "run", "--once", "--fetch-only")
    assert f.hourly and f.time == "00:45" and f.unit_name == A.STORE_FETCH_UNIT == "life-rc-store-fetch"
    e = A.entry("RC-Build")
    assert e.args == ("-m", "revenuechaser.rcdata.build", "run", "--once", "--build-only")
    assert e.hourly and e.time == "00:05" and e.schedule == "hourly at :05 (local)"
    m = A.entry("RC-Build-Market")
    assert m.args[-3:] == ("--build-only", "--kind", "market") and m.unit_name == A.MARKET_BUILD_UNIT
    assert m.time == "09:25" and not m.hourly
    assert e.settings.time_limit_minutes == 120
    assert e.tables_written == (), "it writes the market store, never the old one: no job_runs row (job_runs2 instead)"
    assert e.after is None and not e.default_install
    assert e.unit_name == "life-rc-builder"


def test_the_weekly_backup_row_runs_sunday_0330_every_step_for_at_most_60_minutes():
    """avo, 8 Nov 2026: one weekly backup of everything onto the HDD, the newest 4 copies kept. It replaces the
    nightly RC-Build-Backup (04:30, serving files only) and the weekly RC-Build-Backup-Heavy."""
    e = A.entry("RC-Backup-Weekly")
    assert e.args == ("-m", "revenuechaser.rcdata", "backup"), "no --only: every step runs"
    assert (e.time, e.days) == ("03:30", ("Sunday",))
    assert e.schedule == "weekly Sunday 03:30 (local)"
    assert A.on_calendar(e) == "Sun *-*-* 03:30:00"
    assert e.settings.time_limit_minutes == 60 and e.tables_written == ()
    assert e.unit_name == "life-rc-backup-weekly" == A.BACKUP_WEEKLY_UNIT
    assert not e.default_install and e.after is None and not e.hourly
    for gone in ("RC-Build-Backup", "RC-Build-Backup-Heavy"):
        with pytest.raises(A.UnknownTask):
            A.entry(gone)
    assert not hasattr(A, "BUILDER_BACKUP_UNIT") and not hasattr(A, "BUILDER_BACKUP_HEAVY_UNIT")


def _minutes_of(hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return h * 60 + m


def test_linux_renders_the_builder_rows_as_life_rc_builder_units(tmp_path):
    sc = _FakeSystemctl()
    s = A.LinuxScheduler(runner=sc, python="/srv/rc/.venv/bin/python", workdir="/srv/rc", unit_dir=tmp_path / "u")
    s.install(A.entry("RC-Build"))
    s.install(A.entry("RC-Backup-Weekly"))
    files = sorted(p.name for p in (tmp_path / "u").iterdir())
    assert files == ["life-rc-backup-weekly.service", "life-rc-backup-weekly.timer",
                     "life-rc-builder.service", "life-rc-builder.timer"]
    service = (tmp_path / "u" / "life-rc-builder.service").read_text(encoding="utf-8")
    timer = (tmp_path / "u" / "life-rc-builder.timer").read_text(encoding="utf-8")
    assert 'ExecStart="/srv/rc/.venv/bin/python" "-m" "revenuechaser.core.automations" "run" "RC-Build"' in service
    assert "Type=oneshot" in service and "TimeoutStartSec=120min" in service
    assert "OnCalendar=*-*-* *:05:00" in timer and "Unit=life-rc-builder.service" in timer
    backup_service = (tmp_path / "u" / "life-rc-backup-weekly.service").read_text(encoding="utf-8")
    backup_timer = (tmp_path / "u" / "life-rc-backup-weekly.timer").read_text(encoding="utf-8")
    assert '"run" "RC-Backup-Weekly"' in backup_service and "TimeoutStartSec=60min" in backup_service
    assert "OnCalendar=Sun *-*-* 03:30:00" in backup_timer and "Unit=life-rc-backup-weekly.service" in backup_timer
    for text in (service, timer, backup_service, backup_timer):      # valid unit text: sections, key=value lines
        lines = [ln for ln in text.splitlines() if ln.strip()]
        assert lines[0] == "[Unit]"
        assert all(ln.startswith("[") and ln.endswith("]") or "=" in ln for ln in lines)
    assert ["enable", "--now", "life-rc-builder.timer"] in sc.calls
    assert ["enable", "--now", "life-rc-backup-weekly.timer"] in sc.calls
    sc.calls.clear()
    s.set_enabled("RC-Build", False)
    s.run("RC-Build")
    s.remove("RC-Build")
    assert sc.calls == [["disable", "--now", "life-rc-builder.timer"], ["start", "--no-block", "life-rc-builder.service"],
                        ["disable", "--now", "life-rc-builder.timer"], ["daemon-reload"]]
    assert sorted(p.name for p in (tmp_path / "u").iterdir()) == ["life-rc-backup-weekly.service",
                                                                   "life-rc-backup-weekly.timer"]


def test_a_chain_step_cannot_wait_on_an_hourly_row():
    step = A.AutomationEntry(name="RC-X", label="x", args=("-c", "pass"), time="00:30", description="d",
                             after="RC-Build")
    with pytest.raises(ValueError, match="hourly"):
        A.check_chain(A.REGISTRY + (step,))


def test_the_spx_gamma_fetch_runs_on_weekdays_after_the_stored_close():
    """#291: the scheduled SPX Gamma Fetch keeps a raw day (all expiries) for every session. The builder stores the
    market series on the first pass of each trading day (00:05 New York, ``rcdata/build/due.py``), so 06:30
    Amsterdam Monday to Friday finds the previous session's Cboe SPX close: Monday fetches Friday. A Saturday run
    would never find Friday's close (no trading day, no builder pass). Not chained: the CLI waits for that close
    itself (exit 3, no UW call)."""
    e = A.entry("RC-SPX-Gamma-Fetch")
    assert e.args == ("-m", "revenuechaser.module_spx_gamma", "--nightly")
    assert e.time == "06:30" and e.days == A._WEEKDAYS and e.after is None and not e.hourly
    assert e.tables_written == () and e.default_install is False
    assert e.settings.start_when_available is False
    assert e.schedule == "Monday to Friday 06:30 (local)"      # five days a week is not "weekly"


def test_the_weekly_backup_is_the_only_row_running_rcdata_backup_and_takes_every_step():
    """One job, every step (avo, 8 Nov 2026): a new step or DuckDB kind lands in the weekly run by itself."""
    rows = [e for e in A.REGISTRY if list(e.args)[:3] == ["-m", "revenuechaser.rcdata", "backup"]]
    assert [e.name for e in rows] == ["RC-Backup-Weekly", "RC-Backup-Watchlists-Daily"]
    assert "--only" not in rows[0].args and "--subdir" not in rows[0].args
    # the one other row is the daily watch-list copy, which never runs a weekly step (decision C, 17 Nov 2026)
    assert rows[1].args[3:] == ("--only", "watchlists-daily")


def test_the_daily_watchlists_backup_runs_every_day_0310_under_the_backup_switch():
    """avo, 18 Nov 2026 (card A): every day 03:10, before the weekly 03:30, held by the Backup switch."""
    e = A.entry("RC-Backup-Watchlists-Daily")
    assert (e.time, e.days, e.hourly, e.after) == ("03:10", (), False, None)
    assert e.schedule == "daily 03:10 (local)" and A.on_calendar(e) == "*-*-* 03:10:00"
    assert e.unit == A.BACKUP_WATCHLISTS_DAILY_UNIT == "life-rc-backup-watchlists-daily"
    assert e.settings.time_limit_minutes == 15 and e.tables_written == () and not e.default_install
    assert A.switch_for(e.name) == "backup"


def test_a_task_with_no_time_limit_says_so_and_installs_none():
    """#527: ``no_time_limit`` reads "no time limit", installs ``TimeoutStartSec=infinity``, and a chained task
    after it is not held to a limit it does not have."""
    s = A.TaskSettings(no_time_limit=True)
    assert s.limit_minutes is None
    assert "no time limit" in s.summary() and "h limit" not in s.summary()
    assert A.TaskSettings(start_when_available=False).summary() == "skips a missed run, 4 h limit"
    # #579: the jobs run as systemd units, so no Windows run-condition words reach the Settings page
    assert not any(w in e.settings.summary() for e in A.REGISTRY for w in ("battery", "AC power", "PC", "logged on"))
    assert A.TaskSettings(time_limit_minutes=50).limit_minutes == 50
    assert A.TaskSettings(time_limit_hours=2).limit_minutes == 120


def test_the_ibkr_login_check_limit_is_the_installed_unit_s_five_minutes():
    """#527: the registry said 1 h while homesrv runs ``TimeoutStartSec=5min`` (home-server
    units/life-rc-ibkr-login-check.service); the board shows the registry, so it follows the unit."""
    assert A.entry("RC-IBKR-Login-Check").settings.limit_minutes == 5


def test_the_sec_reads_nightly_check_is_a_job_of_its_own():
    """avo, 16 Nov 2026: the SEC daily check shows as a job on the Settings page and on the Grafana Jobs board."""
    e = A.entry("RC-SEC-Read")
    assert list(e.args) == ["-m", "revenuechaser.rcdata.build", "run", "--once", "--dataset", "sec/reads"]
    assert (e.time, e.days, e.hourly, e.after) == ("01:10", (), False, None)
    assert e.unit == A.SEC_READ_UNIT == "life-rc-sec-read"
    assert e.schedule == "daily 01:10 (local)" and e.settings.limit_minutes == 90
    assert A.on_calendar(e).endswith("*-*-* 01:10:00")
    # five minutes after the hourly builder pass, so the two do not race for the builder lock every night
    assert A.entry("RC-Build").time[-2:] == "05"


SHOW = ("LoadState=loaded\nActiveState=active\nResult=success\nNextElapseUSecRealtime=1794787800000000\n"
        "LastTriggerUSec=1794701400000000\n\n"
        "LoadState=loaded\nActiveState=inactive\nResult=success\nExecMainStatus=0\n"
        "ExecMainStartTimestamp=1794701400000000\n")
NOT_FOUND = ("LoadState=not-found\nActiveState=inactive\nResult=success\n\n"
             "LoadState=not-found\nActiveState=inactive\nResult=success\n")


def test_a_host_with_no_scheduler_shows_the_servers_own_timers_read_only():
    """16 Nov 2026 (homesrv): every row said "Scheduler unavailable" though the timers run as system units."""
    asked = []

    def run(args):
        asked.append(args[-2:])
        return 0, SHOW if "life-rc-sec-read.timer" in args else NOT_FOUND, ""

    def system(e):
        return A.system_status(e, run)

    state = A.live_state(A.UnavailableScheduler(), NOW, system)
    rows = {r["name"]: r for r in state["rows"]}
    sec = rows["RC-SEC-Read"]
    assert (sec["state"], sec["managed"], sec["unit"], sec["result_text"]) == (
        "enabled", "system", "life-rc-sec-read", "ok")
    assert sec["last_run"] and sec["next_run"]
    # a row this server has no timer for is "not installed", with no button either (managed, no unit)
    assert (rows["RC-Build"]["state"], rows["RC-Build"]["managed"], rows["RC-Build"]["unit"]) == (
        "not_installed", "system", None)
    assert state["available"] is True
    assert ["life-rc-relatedness.timer", "life-rc-relatedness.service"] in asked
    assert ["life-rc-forecast-outcomes.timer", "life-rc-forecast-outcomes.service"] in asked
    nothing = A.live_state(A.UnavailableScheduler(), NOW, lambda e: None)
    assert nothing["available"] is False and {r["state"] for r in nothing["rows"]} == {"unavailable"}


def test_a_connected_scheduler_never_asks_the_system_manager():
    def boom(e):
        raise AssertionError("the system manager was asked")
    rows = A.live_state(A.FakeScheduler(), NOW, boom)["rows"]
    assert {r["state"] for r in rows} == {"not_installed"} and not any("managed" in r for r in rows)


def test_relatedness_reads_weekly_sunday_and_its_trigger_says_the_same():
    """avo, 20 Nov 2026: "Tamam haftalik" -- weekly, Sunday. It ends a three-way disagreement: these words said
    every other Sunday 07:30 (his 15 Nov word), while the installed homesrv timer has been weekly Sunday 22:15
    since 16 Nov. No fortnight is carried anywhere now, so the row's own trigger says what the server does."""
    e = A.entry("RC-Relatedness-OffPeak")
    assert e.schedule == "weekly Sunday 22:15 (local)"
    assert not e.fortnightly
    assert A.on_calendar(e).endswith("*-*-* 22:15:00") and "Sun" in A.on_calendar(e)
    assert A.entry("RC-Backup-Weekly").schedule == "weekly Sunday 03:30 (local)"
