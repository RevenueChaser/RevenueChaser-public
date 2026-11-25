"""The control board's "next" and "since" words per dataset (#492 slice B1, step 2): when the hourly pass first runs
a dataset, by the same rules as ``rcdata.build.due.is_due``, in Amsterdam time with New York in brackets."""
from __future__ import annotations

from datetime import datetime, timezone

from revenuechaser.module_settings import control
from revenuechaser.module_settings.tests.test_control_view import NOW, _build
from revenuechaser.rcdata.serving import KINDS

ON = {"state": "on", "last": None, "next": None, "minute": 7}
OFF = {**ON, "state": "off"}
UNKNOWN = {"state": None, "last": None, "next": None, "minute": None}
OPEN = {"paused": False, "paused_by": None, "paused_at": None}


def words(check=None, kind="today_ny", cadence="daily", *, schedule=OPEN, attended=False, starts_by_hand=False,
          timer=ON, now=NOW, mode="full", starts=None, slot=None):
    return control.next_run_words(schedule, check, kind, cadence, attended=attended, starts_by_hand=starts_by_hand,
                                  timer=timer, now=now, mode=mode, starts=starts, slot=slot)


def ok(**kw):
    return {"result": "changed", "checked_on": "2026-10-29", "next_check_due": None, **kw}


def test_a_paused_dataset_skips_until_resume():
    assert words(ok(), schedule={**OPEN, "paused": True}) == "skips until Resume"


def test_an_attended_dataset_runs_by_hand_only():
    assert words(ok(), attended=True) == "by hand only"


def test_a_dataset_that_starts_by_hand_waits_for_its_first_fetch():
    assert words(None, starts_by_hand=True) == "not before a first Fetch"
    assert words(ok(next_check_due="2026-11-13"), starts_by_hand=True) == "Fri 13 Nov, 06:07 (00:07 New York)"


def test_a_dataset_whose_day_starts_in_the_new_york_evening_runs_on_the_night_pass():
    """The SEC reads' check (avo, 16 Nov 2026): the day starts at 19:00 New York, so the pass is 01:xx Amsterdam."""
    from datetime import time
    assert words(ok(next_check_due="2026-11-13"), starts=time(19, 0)) == "Sat 14 Nov, 01:07 (19:07 New York)"


def test_an_hourly_dataset_runs_on_every_pass():
    assert words(ok(), cadence="hourly") == "every hourly pass (:07)"
    assert words(ok(), cadence="hourly", timer=OFF) == "timer off · every hourly pass (:07)"


def test_a_timer_not_known_gives_no_time():
    assert words(ok(), timer=UNKNOWN) == "next pass not known"
    assert words(ok(), timer=None) == "next pass not known"


def test_a_today_ny_dataset_runs_at_the_new_york_days_first_pass_on_its_next_check_date():
    # 13 Nov 2026: both zones on winter time, six hours apart.
    assert words(ok(next_check_due="2026-11-13")) == "Fri 13 Nov, 06:07 (00:07 New York)"


def test_a_complete_session_dataset_waits_for_the_close_and_the_settle_time():
    # 16:00 + COMPLETE_MARGIN (30 min) = 16:30 New York; the first :07 pass after it is 17:07.
    assert words(ok(next_check_due="2026-11-13"), "latest_complete_session") == "Fri 13 Nov, 23:07 (17:07 New York)"


def test_a_daily_dataset_with_no_next_date_is_a_recurring_rule_right_on_a_dst_gap_day():
    # 30 Oct 2026: Amsterdam is on winter time already, New York not yet: five hours apart.
    assert words(ok()) == "every trading day, 05:07 (00:07 New York)"
    later = datetime(2026, 11, 12, 12, 0, tzinfo=timezone.utc)
    assert words(ok(), now=later) == "every trading day, 06:07 (00:07 New York)"


def test_weekly_and_monthly_count_from_the_check_day():
    assert words(ok(checked_on="2026-11-06"), cadence="weekly", now=datetime(2026, 11, 7, tzinfo=timezone.utc)) \
        == "Fri 13 Nov, 06:07 (00:07 New York)"
    assert words(ok(checked_on="2026-10-20"), cadence="monthly") == "Thu 19 Nov, 06:07 (00:07 New York)"


def test_a_dataset_due_now_runs_on_the_next_pass():
    assert words(ok(next_check_due="2026-10-29")) == "due · Fri 30 Oct, 19:07 (14:07 New York)"
    assert words(None) == "due · Fri 30 Oct, 19:07 (14:07 New York)"
    assert words({"result": "failed", "checked_on": "2026-10-30"}) == "due · Fri 30 Oct, 19:07 (14:07 New York)"


def test_a_timer_that_is_off_prefixes_the_time():
    assert words(ok(next_check_due="2026-11-13"), timer=OFF) == "timer off · Fri 13 Nov, 06:07 (00:07 New York)"


def test_since_words_say_who_paused_and_when_in_amsterdam_time():
    paused = {"paused": True, "paused_by": "avo", "paused_at": "2026-10-30T09:15:00+00:00"}
    tail = " · a running fetch stops before its next provider call; the files it fetched stay"   # #492 PR (ii)
    assert control.since_words(paused) == "paused · since Fri 30 Oct, 10:15 by avo" + tail
    assert control.since_words({**paused, "paused_at": None}) == "paused · since not recorded yet by avo" + tail
    assert control.since_words(OPEN) == "fetch on"
    assert control.since_words(None) == "fetch on"


def test_every_dataset_row_has_next_and_since_words():
    rows = [r for f in _build(kind_modes=lambda: {k: {"kind": k, "mode": "full"} for k in KINDS})["files"]
            for r in f["datasets"]]
    assert rows and all(isinstance(r["next_words"], str) and isinstance(r["since_words"], str) for r in rows)
    by = {r["dataset"]: r for r in rows}
    # #1361: not "by hand only" any more. The exact words depend on this fixture's check rows, so only the
    # thing the change guarantees is asserted.
    assert by["wrds/prices"]["next_words"] != "by hand only"
    assert by["sec/13f"]["next_words"] == "not before a first Fetch"
    assert by["alpaca/bars"]["since_words"] == "fetch on"


def test_the_as_of_kind_is_read_from_the_datasets_code():
    from revenuechaser.module_settings import newdata
    ds = newdata._datasets()
    assert control.as_of_kind(ds["market_series"]) == "latest_complete_session"
    assert control.as_of_kind(ds["alpaca/bars"]) == "latest_complete_session"
    assert control.as_of_kind(object()) is None


def test_a_kind_whose_automation_is_off_says_so_instead_of_a_pass():
    assert words(ok(), mode="off") == "automation off · Fetch only"
    assert words(None, starts_by_hand=True, mode="off") == "automation off · Fetch only"


def test_a_partial_runs_own_skip_waits_for_its_next_check_like_a_build():
    from revenuechaser.rcdata.build import base
    stage = {"result": "skipped", "checked_on": "2026-10-29", "next_check_due": None,
             "note": base.skip_note(1, raw_only=True)}
    assert not words(stage, mode="raw").startswith("due")
    assert words(stage, mode="full").startswith("due")


def test_a_start_time_moves_the_next_run_to_its_first_pass_after_it():
    """avo, 24 Nov 2026: a daily dataset starts at its time once its next session is in; a weekly one on its day."""
    thursday = datetime(2026, 10, 29, 17, 31, tzinfo=timezone.utc).timestamp()
    nightly = {"at": "22:00", "weekday": None, "set_at": thursday}
    assert words(ok(next_check_due="2026-10-30"), slot=nightly) == "Fri 30 Oct, 22:07 (17:07 New York)"
    monday = {"at": "09:00", "weekday": 0, "set_at": thursday}
    assert words(ok(), cadence="weekly", slot=monday) == "Mon 2 Nov, 09:07 (03:07 New York)"
    assert words(ok(), cadence="monthly", slot=monday) == "Sat 28 Nov, 06:07 (00:07 New York)"   # no start: by days


def test_a_files_fetch_hours_move_the_next_run_to_its_first_hour():
    """avo, 24 Nov 2026 (a fetch time per DuckDB) and home-server #649: market at 07:45 and 22:45 Amsterdam."""
    at45 = {**ON, "minute": 45}
    plain = control.next_run_words(OPEN, ok(next_check_due="2026-11-13"), "today_ny", "daily", attended=False,
                                   starts_by_hand=False, timer=at45, now=NOW)
    assert plain == "Fri 13 Nov, 06:45 (00:45 New York)"
    timed = control.next_run_words(OPEN, ok(next_check_due="2026-11-13"), "today_ny", "daily", attended=False,
                                   starts_by_hand=False, timer=at45, now=NOW, hours=(7, 22))
    assert timed == "Fri 13 Nov, 07:45 (01:45 New York)"
    hourly = control.next_run_words(OPEN, ok(), "today_ny", "hourly", attended=False, starts_by_hand=False,
                                    timer=at45, now=NOW, hours=(7, 22))
    assert hourly == "at 07:45 and 22:45"


def test_the_jobs_detail_reads_the_storage_fetch_timer_not_the_builder(monkeypatch):
    """home-server #649: the Jobs column read the old builder's :05; a dataset's next run is the :45 fetch's."""
    from revenuechaser.module_settings import metrics
    asked = []
    monkeypatch.setattr(control, "read_timer", lambda entry=control.BUILDER_ENTRY: asked.append(entry) or {})
    metrics.FETCH_TIMER._reader()
    assert asked == [control.FETCH_ENTRY] and metrics.FETCH_TIMER is not metrics.TIMER
