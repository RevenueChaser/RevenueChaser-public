"""What is due: ``run`` without ``--dataset`` queues every due dataset before it drains the queue.

A dataset is due (``is_due``) when nothing holds it and its last run is old enough:

- an attended dataset is never due: it runs only from the CLI (PR 5). Since #1361 no WRDS dataset is one -- that
  login asks for no Duo push here -- so they follow their cadence; what is left is ``delisted/serving``, which
  declares it to stay off the hourly pass (#1219). A WRDS dataset whose
  last run failed **today** (New York) is not due again before the next day (#344: no hourly login retries; #1115:
  not for ever either, because a failure after the WRDS calls -- a refused serving swap -- would otherwise stop a
  daily dataset writing any check row at all until a person noticed). So at most one retry a day, and a run by a
  person (Fetch or CLI) that does not fail clears it at once;
- a dataset that ``starts_by_hand`` (every spine dataset) is not due until it has built once (a ``changed`` or
  ``unchanged`` check from a CLI run or a Fetch), so the first hourly pass after a deploy does not start it before
  the attended steps, and a first attempt that failed is not retried every hour before a person has seen it work;
- a pause in ``dataset_schedule`` holds it: its request is not queued; ``base.run_request`` skips a request of a
  paused dataset that was queued anyway (a Fetch, the CLI's), with a ``skipped: paused`` check row (PR #222);
- so does ``dataset_schedule.next_due`` while it is later than today in New York (a hold until that day);
- so does ``EARLIEST_NY_HOUR`` before its hour in New York (``wrds/prices``: the Compustat snapshot holds the
  session's bar only from the early morning there, and the dataset runs once a New York day);
- never built (no ``dataset_check`` row), or a last check that ``failed`` or was ``skipped`` (the day cap writes one,
  and so does the pause skip): due; except a failure of a ``DAY_CAPPED`` provider's dataset (Alpha Vantage) that
  holds no raw file for the day yet, due again only on the next New York day (with the day's raw file held a rerun
  costs no call, so a failed build or swap retries on the next pass);
- ``daily`` (the default, and what an unknown cadence reads as): due once the dataset's own ``default_as_of()`` has
  reached the last check's ``next_check_due`` (the next session after the as-of it ran for), so the SPX slice and the
  market series (as-of: the latest complete session, #643 F4) run on the first pass after each session completes.
  A check with no ``next_check_due`` (past the calendar's table) is due once the as-of is newer than the one it ran
  for, so a calendar run out does not make a dataset due every hour;
- its kind's automation (``ops.kind_automation``, set on the Settings page), or the dataset's own when it has one
  (``ops.dataset_automation``, #527: the source's Automated select; "as the file" is no row), decides what the hourly pass queues:
  ``off`` (the default) queues nothing for the kind, ``raw`` / ``parquet`` queue the same partial run a Fetch's ▾
  asks for, ``full`` the whole run. Under a partial mode a check the partial run itself wrote (a ``skipped`` with
  its stage note) counts as the run for the cadence, so the hourly pass does not queue the dataset again every
  hour; under ``full`` it stays due, so the next pass builds the rest. A person's Fetch is not touched by any of it;
- ``hourly`` (#643 F1, for the hourly economic calendar and headlines, and group 3's Earnings refresh): due once the
  run that wrote the last check started ``HOURLY_MIN`` minutes ago or more (``job_runs2.started_at`` through the
  check's ``run_id``; ``dataset_check`` holds only a day). Start, not finish: a run that took ten minutes would
  otherwise miss every second hourly pass. A check with no run behind it is due;
- a dataset in ``CHECK_DATES`` (``(month, day)`` pairs in New York) ignores its cadence: it is due once the newest
  of those dates has passed and no check since then succeeded, and only in ``NIGHT_HOURS`` (New York, = 02-05 in
  Amsterdam), so a heavy quarterly source (N-PORT) runs at night a few days after its release; a check that failed
  waits for the next night;
- ``weekly`` / ``monthly`` / ``quarterly``: due 7 / 30 / 91 days after the last check's ``checked_on``. The cadence is the
  ``dataset_schedule`` row's, else the dataset's own ``cadence`` attribute (the spine's weekly sources), else daily.

The request goes in through ``ops.enqueue_once`` (check and insert in one ``BEGIN IMMEDIATE``), so a dataset that
already has a request queued or running gets no second one, whoever queued the first.
"""
from __future__ import annotations

import sys
from datetime import date

from ...core import calendar
from .. import ops
from . import base

CADENCES = ("hourly", "daily", "weekly", "monthly", "quarterly")
DEFAULT_CADENCE = "daily"
#: ``quarterly`` (#775, for the 13F institution map): 91 days, the shortest calendar quarter, so a
#: dataset that ran on the first day of a quarter is due again inside the next one.
CYCLE_DAYS = {"weekly": 7, "monthly": 30, "quarterly": 91}
#: Under 60 so a pass that starts a few minutes early (timer jitter, a long pass before it) still finds it due.
HOURLY_MIN = 55
REQUESTED_BY = "schedule"
ATTENDED_WHY = "attended: run from the CLI on the server (a person logs in; WRDS_USERNAME must be set)"
WRDS_FAILED_WHY = ("the last WRDS run failed today: again on the next New York day (no hourly retry, so no hourly "
                   "login; the last snapshot stays); a run by a person (Fetch or CLI) that does not fail clears it")
#: Providers whose day is too small to retry a failure every hourly pass (Alpha Vantage: 25 calls a day, shared by
#: the earnings calendar and the listing status): a failed check is due again on the next New York day (#349 S6).
DAY_CAPPED = frozenset({"alphavantage"})
#: Datasets checked on fixed days, not on a cadence. Kept here, not on the dataset: a change to the dataset's own
#: module is a rule change and restates what that dataset serves (``dirty.dataset_fingerprint``). N-PORT: the SEC posts a quarter's set on the
#: 3rd-9th of Jan/Apr/Jul/Oct (2024-2026; 2025q3 came 18 Nov, a shutdown), so the night of the 15th (avo, 17 Nov 2026:
#: "Senede 4 defa baksın").
CHECK_DATES = {"sec/nport": ((1, 15), (4, 15), (7, 15), (10, 15))}
#: The New York hours a ``CHECK_DATES`` dataset may start in: 20:00-22:59, 02:00-04:59 in Amsterdam.
NIGHT_HOURS = range(20, 23)
#: The earliest New York hour a dataset may be due in, where its source publishes on its own clock. Compustat's
#: daily security file gets a session's bar in the early morning New York -- WRDS stamps the product
#: "Data Last Updated: Nov. 19, 2026, 3:40 a.m.", and the snapshots this box holds agree: 01:23 NY was byte for byte
#: the one before it, while 07:15, 08:17 and 15:20 NY each held the previous session. ``wrds/prices`` runs once a
#: New York day (as-of today, next check the next session), so a pass at 00:05 would spend that day's run on a
#: snapshot one session short and leave the boards' Fetch without the bar it freezes on (avo, 19 Nov 2026).
EARLIEST_NY_HOUR = {"wrds/prices": 5}
BY_HAND_WHY = "starts by hand: not due until a first run from the CLI or a Fetch has built it"
#: The stage notes a partial run leaves (``base.skip_note``), by the modes whose run they complete: a raw + Parquet
#: run also completes a raw-only mode, a raw-only run does not complete a raw + Parquet one.
STAGE_DONE = {"raw": (base.NO_PARQUET_NOTE, base.NO_DUCKDB_NOTE), "parquet": (base.NO_DUCKDB_NOTE,)}


def _stage_done(check: dict, mode: str) -> bool:
    return check["result"] == "skipped" and str(check.get("note") or "").startswith(STAGE_DONE.get(mode, ()))


def _day_raw_held(ds) -> bool:
    """True when ``ds`` already holds its raw file for ``default_as_of()``: a rerun reuses it at no call, so a failed
    build or swap may retry on the next hourly pass (review S6a of #349). A dataset with no ``raw_path`` holds none."""
    raw_path = getattr(sys.modules[type(ds).__module__], "raw_path", None)
    return bool(raw_path and raw_path(ds.default_as_of()).exists())


def _dated(ds, check: dict | None) -> tuple[bool, str]:
    """``is_due`` for a ``CHECK_DATES`` dataset: the newest date passed, nothing checked since, at night."""
    today = calendar.today_ny()
    last = max(date(y, m, d) for y in (today.year - 1, today.year) for m, d in CHECK_DATES[ds.name]
               if date(y, m, d) <= today).isoformat()
    on = str(check["checked_on"])[:10] if check else ""
    if on >= last and check["result"] != "failed":
        return False, f"checked on {on}, after its check date {last}"
    if check and check["result"] == "failed" and on >= today.isoformat():
        return False, "failed today: again the next night"
    if calendar._now().astimezone(calendar.NY).hour not in NIGHT_HOURS:
        return False, f"check date {last} passed: waits for the night"
    return True, f"check date {last} passed"


def is_due(ds, mode: str = "full") -> tuple[bool, str]:
    """``(due, why)`` for dataset ``ds``, from its ``dataset_schedule`` row and its newest ``dataset_check`` row;
    ``mode`` is its kind's automation (``ops.KIND_MODES``)."""
    if getattr(ds, "attended", False):
        return False, ATTENDED_WHY
    if mode == "off":                       # after attended: the Settings row reads "by hand only" first too
        return False, f"automation off for {ds.kind}"
    if getattr(ds, "starts_by_hand", False) and not ops.ever_built(ds.name) \
            and not (mode in STAGE_DONE and _stage_done(ops.latest_check(ds.name) or {"result": None}, mode)):
        # Under a partial mode a person's first staged run is its first run: the storage fetch builds nothing, so
        # waiting for a build would keep the source off the hourly fetch for good (avo, 24 Nov 2026).
        return False, BY_HAND_WHY
    schedule = ops.schedule_get(ds.name) or {}
    if schedule.get("paused_at") is not None:
        return False, f"paused by {schedule.get('paused_by') or '?'}"
    today = calendar.today_ny().isoformat()
    hold = schedule.get("next_due")
    if hold and str(hold) > today:
        return False, f"held until {hold}"
    hour = EARLIEST_NY_HOUR.get(ds.name)
    if hour is not None and calendar._now().astimezone(calendar.NY).hour < hour:
        return False, f"waits for {hour:02d}:00 New York (the source publishes a session's bar in the morning)"
    check = ops.latest_check(ds.name)
    if ds.name in CHECK_DATES:
        return _dated(ds, check)
    if check is None:
        return True, "never built"
    if "wrds" in getattr(ds, "providers", ()) and check["result"] == "failed" \
            and str(check.get("checked_on"))[:10] >= today:
        # One failure never becomes an hourly login, but it does not hold a daily dataset for
        # ever either (#1115: a transient serving-swap refusal on 17 Nov 2026 left ``wrds/prices`` writing no check
        # row at all on 18 and 19 Nov, so the served bars stopped at 16 Nov). One retry a New York day.
        return False, WRDS_FAILED_WHY
    if check["result"] == "failed" and DAY_CAPPED & set(getattr(ds, "providers", ())) \
            and str(check.get("checked_on"))[:10] >= today and not _day_raw_held(ds):
        return False, "failed today: again on the next New York day (the provider allows 25 calls a day)"
    if check["result"] in ("failed", "skipped") and not _stage_done(check, mode):
        return True, f"the last check {'failed' if check['result'] == 'failed' else 'was skipped'}"
    cadence = schedule.get("cadence") if schedule.get("cadence") in CADENCES else getattr(ds, "cadence", None)
    cadence = cadence if cadence in CADENCES else DEFAULT_CADENCE
    if cadence == "daily":
        nxt = check.get("next_check_due")
        as_of = ds.default_as_of().isoformat()
        if not nxt:
            # No next session (past the calendar's table, base.next_due): once per newer as-of, never every hour.
            ran = check.get("source_as_of")
            if not ran:
                return True, "the last check names no as-of"
            ran = str(ran)[:10]
            if as_of > ran:
                return True, f"no next session known; as-of {as_of} is newer"
            return False, f"no next session known; ran for {ran}"
        return (True, f"next check {nxt} reached") if as_of >= nxt else (False, f"next check {nxt}")
    if cadence == "hourly":
        if mode in STAGE_DONE and not _stage_done(check, mode):
            # Under a partial mode the hour is the fetch's: a build of what it staged (the storage build at :05) is
            # no fetch, and counting from it made the :45 fetch skip every second hour (review of #1483)
            return True, "hourly: the newest check is a build, not a fetch"
        started = ops.run_started_at(check["run_id"]) if check.get("run_id") else None
        if started is None:
            return True, "hourly: the last check names no run"
        minutes = round(calendar._now().timestamp() - float(started)) // 60   # whole seconds first: float noise
        return minutes >= HOURLY_MIN, f"hourly: last run started {minutes} min ago"
    age = (calendar.today_ny() - date.fromisoformat(str(check["checked_on"])[:10])).days
    if age >= CYCLE_DAYS[cadence]:
        return True, f"{cadence}: last checked {age} days ago"
    return False, f"{cadence}: last checked {age} days ago"


#: The local hours (the machine's zone, Europe/Amsterdam on homesrv) the storage fetch takes a kind's sources at, for a
#: kind that is built on a timer of its own (avo, 24 Nov 2026: market fetched at 07:45 and 22:45, each just before its
#: build at 08:25 and 23:25, not hourly). A fetch that failed tries once more the next hour.
FETCH_HOURS = {"market": (7, 22)}


def _fetch_hour(ds) -> str | None:
    """Why the storage fetch leaves ``ds`` for a later hour, or None."""
    hours = FETCH_HOURS.get(ds.kind)
    if not hours:
        return None
    hour = calendar._now().astimezone().hour
    if hour in hours:
        return None
    check = ops.latest_check(ds.name)
    if (hour - 1) % 24 in hours and check is not None and check["result"] == "failed":
        return None                           # the one retry of a failed fetch
    return f"{ds.kind} is fetched at " + " and ".join(f"{h:02d}:45" for h in hours)


def _pass_mode(ds, mode: str, stage: str | None) -> tuple[str, str | None]:
    """``(mode, why not)`` for the split passes (avo, 24 Nov 2026: a storage fetch timer always on, a storage build
    timer he switches). ``fetch``: a ``full`` source is queued as ``parquet``, so the pass never builds DuckDB.
    ``build``: only a ``full`` source whose newest check is a Parquet stage is queued, and as ``full``: the build of
    what the fetch timer staged, at no provider call (the raw file is the resume marker)."""
    if stage == "fetch":
        return ("parquet" if mode == "full" else mode), _fetch_hour(ds)
    if stage == "build":
        if mode != "full":
            return mode, f"automation {mode}: the build pass builds only full sources"
        check = ops.latest_check(ds.name)
        if not (check and _stage_done(check, "parquet")):
            return mode, "no staged Parquet waiting for a build"
    return mode, None


def enqueue_due(datasets: dict | None = None, stage: str | None = None,
                kinds: tuple[str, ...] = ()) -> list[tuple[str, str, int | None, bool]]:
    """Queue every due dataset once; ``(name, why, request id or None, error)`` per dataset, in registry order.

    No id: not due, already queued or running, or an error (``why`` says which). ``error`` is True when the due check
    raised or ``ops.sqlite`` stayed locked past its busy timeout; one dataset's error does not stop the others.
    ``stage`` is the split pass (``run --fetch-only`` / ``--build-only``, ``_pass_mode``); None is the old whole pass.
    ``kinds``, when given, leaves every other kind's dataset out (``run --build-only --kind market``).
    """
    if datasets is None:
        from . import DATASETS as datasets
    out = []
    for name in datasets:                     # registry order: sources before the kind's derived datasets (PR A)
        if kinds and datasets[name].kind not in kinds:
            continue
        try:
            # avo, 10 Nov 2026 ("burada yaptigim her ayarin uygulanabilir oldugundan emin ol"): a dataset the fetch
            # switch or its file's switch holds is not queued at all, so a held file leaves no hourly skipped rows
            held = base.held_by_switch(name)
            if held is not None:
                out.append((name, f"not due (held: {ops.switch_words(*held)})", None, False))
                continue
            mode = ops.dataset_mode(name, datasets[name].kind)   # #527: a source's own mode wins over its kind's
            mode, not_now = _pass_mode(datasets[name], mode, stage)
            due, why = (False, not_now) if not_now else is_due(datasets[name], mode)
        except Exception as e:  # noqa: BLE001 - a calendar past its table for one dataset must not stop the rest
            out.append((name, f"due check failed: {type(e).__name__}: {e}"[:300], None, True))
            continue
        if not due:
            out.append((name, f"not due ({why})", None, False))
            continue
        try:
            params = {"build_only": True} if stage == "build" else base.STAGE_PARAMS[mode] or None
            rid = ops.enqueue_once(name, params, by=REQUESTED_BY)
        except ops.BUSY_ERRORS as e:
            # ops.sqlite held past busy_timeout, or Redis not answering (as in _run_queue): this dataset waits for
            # the next pass.
            out.append((name, f"due ({why}), not queued: ops store busy: {e}"[:300], None, True))
            continue
        out.append((name, f"due ({why}), " + (f"queued as request {rid}" if rid else "already queued or running"),
                    rid, False))
    return out
