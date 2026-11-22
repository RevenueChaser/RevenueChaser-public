"""Automations registry: every scheduled task RevenueChaser owns, and the one installer.

The Settings board lists one row per entry of ``REGISTRY`` and lets the user install,
enable, disable, remove or run a task by its exact registry name. Nothing here runs by
itself: ``default_install`` only marks a row, and no code path installs a task on
import, dashboard start, Refresh, GET or in a test (``inventory.collect`` never calls
the scheduler; e2e installs ``FakeScheduler``).

Two sides:

- ``Scheduler``: the interface to the OS scheduler. ``LinuxScheduler`` drives systemd user
  timers, one ``.service`` and ``.timer`` pair per registry task (#158); ``FakeScheduler``
  backs the tests and the e2e dashboard; ``UnavailableScheduler`` is the answer on a host
  without one (a state, not an error). The Windows Task Scheduler backend was removed with
  the rest of the Windows-era code (#1225).
- ``run_task``: the command every task actually runs
  (``python -m revenuechaser.core.automations run <name>``). It appends the job's
  output and exit code to the entry's ``log_path`` so a red row has a reason.

Registry names are stable: a task that writes tables records them as ``job_runs.registry_name`` (#129 A1).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time as _time
from dataclasses import dataclass, field
from datetime import datetime, time as dtime, timedelta, timezone, tzinfo
from pathlib import Path
from typing import Callable

from revenuechaser.core import config

logger = logging.getLogger(__name__)

ACTIONS = ("install", "enable", "disable", "remove", "run")

# The last-result codes a row reports. The two non-zero ones come from the Task Scheduler era and are
# still the values ``FakeScheduler`` and the systemd status mapping use.
RESULT_OK = 0
RESULT_RUNNING = 0x41301      # SCHED_S_TASK_RUNNING
RESULT_NOT_YET_RUN = 0x41303  # SCHED_S_TASK_HAS_NOT_RUN

_LOG_MAX_BYTES = 256 * 1024
_TAIL_LINES = 5
_TAIL_WIDTH = 200
_EXIT_RE = re.compile(r"^=== (\S+) exit (-?\d+)\s*$")
# Exit code of a chained task whose predecessor's run of tonight did not exit 0 (failed, blocked, missing or overdue).
CHAIN_BLOCKED = 5


# --- registry ---------------------------------------------------------------

@dataclass(frozen=True)
class TaskSettings:
    """The run conditions a row installs with: only what the systemd timer and service honour (#579)."""
    start_when_available: bool = True
    time_limit_hours: int = 4
    time_limit_minutes: int | None = None  # set: the limit in minutes instead of ``time_limit_hours``
    no_time_limit: bool = False    # set: no limit at all (#527); both fields above are then ignored

    @property
    def limit_minutes(self) -> int | None:
        """The limit in minutes, or None when the task has none."""
        if self.no_time_limit:
            return None
        return self.time_limit_minutes if self.time_limit_minutes is not None else self.time_limit_hours * 60

    def summary(self) -> str:
        # only what the systemd timer and service honour (#579): Persistent= and TimeoutStartSec=
        parts = ["catches up a missed run" if self.start_when_available else "skips a missed run"]
        parts.append("no time limit" if self.no_time_limit else
                     f"{self.time_limit_minutes} min limit" if self.time_limit_minutes is not None
                     else f"{self.time_limit_hours} h limit")
        return ", ".join(parts)


@dataclass(frozen=True)
class AutomationEntry:
    name: str                      # the registry name, always ``RC-...``
    label: str
    args: tuple[str, ...]          # ``python <args>``
    time: str                      # local HH:MM
    description: str
    tables_written: tuple[str, ...] = ()
    offpeak_gated: bool = False
    default_install: bool = False  # a marker only: nothing installs on its own
    settings: TaskSettings = field(default_factory=TaskSettings)
    days: tuple[str, ...] = ()     # weekly on these days (English day names, e.g. "Saturday"); empty = daily
    after: str | None = None       # the nightly chain (#129): run only once this registry task's run of tonight exited 0
    chain_wait_minutes: int = 120  # how long a chained task waits for that run before it gives up
    hourly: bool = False           # every hour at ``time``'s minute (its hour is ignored); never chained, no ``days``
    unit_name: str | None = None   # the systemd unit (and nothing else) under another name than ``name``
    fortnightly: bool = False      # words only: the server's timer carries the fortnight (1st and 3rd week), not this row

    @property
    def unit(self) -> str:
        """The systemd unit name of the row's ``.service`` / ``.timer`` pair."""
        return self.unit_name or self.name

    @property
    def schedule(self) -> str:
        if self.hourly:
            return f"hourly at :{self.time[-2:]} (local)"
        if self.days == _WEEKDAYS:
            text = f"Monday to Friday {self.time} (local)"     # five days a week is not "weekly" (16 Nov 2026)
        elif self.days:
            every = "every other" if self.fortnightly else "weekly"
            text = f"{every} {', '.join(self.days)} {self.time} (local)"
        else:
            text = f"daily {self.time} (local)"
        return f"{text}, after {self.after}" if self.after else text

    @property
    def command(self) -> str:
        return "python " + " ".join(self.args)

    @property
    def log_path(self) -> Path:
        return config.OUTPUT_DIR / "logs" / f"{self.name}.log"


_WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday")
# The market-store builder (#206, PR 2): one pass over the request queue every hour; the builder decides per dataset
# from ``ops.dataset_schedule`` whether anything is due (avo's rule: scheduled jobs run hourly). It writes only the
# market store and records its own ``ops.job_runs2`` rows, so ``tables_written`` is empty: no old ``job_runs`` row.
BUILDER_UNIT = "life-rc-builder"
# The weekly backup (avo, 8 Nov 2026): one job, every step, onto the HDD, the newest 4 copies kept. Its unit pair is
# installed from the home-server repository, not from the Settings page (one name, one timer).
BACKUP_WEEKLY_UNIT = "life-rc-backup-weekly"
# The daily copy of avo's watch lists (decision C, 17 Nov 2026; timer avo 18 Nov): home-server units too.
BACKUP_WATCHLISTS_DAILY_UNIT = "life-rc-backup-watchlists-daily"
# The SEC reads' nightly check (avo, 16 Nov 2026: "grafana jobs ve rc settings de job olarak gozukmeli"): a job of its
# own, so it has a row on the Settings page and on the Grafana Jobs board. Its unit pair is in the home-server repository.
SEC_READ_UNIT = "life-rc-sec-read"

REGISTRY: tuple[AutomationEntry, ...] = (
    AutomationEntry(
        name="RC-Relatedness-OffPeak", label="Relatedness profiling (weekly, Sunday)",
        args=("-m", "revenuechaser.scripts.board_fetch", "relatedness"), time="22:15", days=("Sunday",),
        description=("Relatedness profiling with the board's writer (Settings, #360: EVREN by default, no call cap), "
                     "incremental (only changed filings), then every pair scored (~27 s CPU for 5,111 profiles, "
                     "measured on the server 20 Nov 2026, #884) and the "
                     "board rendered. Weekly, Sunday 22:15 (avo 20 Nov 2026: \"Tamam haftalik\"; that is also what "
                     "the installed homesrv timer has had since 16 Nov, while these words still said every other "
                     "Sunday 07:30). With DeepSeek it is capped at 10 USD (avo, 2 Nov 2026) and defers itself "
                     "outside off-peak hours. The run happens in the dashboard (POST /run/module_relatedness, the "
                     "one writer, with that cap): the task waits for the store to be idle, then queues it and "
                     "waits. Until #1255 it opened the board file itself and a peer holding it ended the week's "
                     "run on StoreLockedError after ~29 s; now a busy store exits 3 and nothing is written, and "
                     "with the dashboard down it exits 1."),
        tables_written=("relatedness_profiles", "relatedness_attributes", "relatedness_scores",
                        "llm_cache", "chain_filings", "chain_meta"),
        offpeak_gated=True),
    AutomationEntry(
        name="RC-Forecast-Outcomes", label="Forecast outcomes",
        args=("-m", "revenuechaser.scripts.forecast_outcomes", "--nightly"), time="23:35",
        description="Recomputes the 30- and 90-day outcome (reference open, "
                    "MFE, MAE, open/closed) of every frozen pick not closed yet, from the stored bars; no calls "
                    "(#380 S0). 23:35 is its own trigger (avo, #620). A busy forecast-outcomes lock exits 3, and nothing was "
                    "written.",
        tables_written=("forecast_outcomes",)),
    AutomationEntry(
        name="RC-Forecast-Baselines", label="Forecast baselines",
        args=("-m", "revenuechaser.scripts.forecast_baselines", "--nightly"), time="23:50",
        after="RC-Forecast-Outcomes",
        description="Once tonight's outcomes run exited 0, recomputes the baselines still open: what each freeze "
                    "date's own universe did over the same 30- and 90-day windows, and the same names split into ten "
                    "trailing-volatility deciles, from the stored bars and the universe change history; no calls "
                    "(#25 HR-1). Chained on RC-Forecast-Outcomes, the other writer of the 23:35 slot, so "
                    "the two never run together; 23:50 is its own trigger.",
        tables_written=("forecast_baselines",)),
    AutomationEntry(
        name="RC-IBKR-Login-Check", label="IBKR Gateway login check",
        args=("-m", "revenuechaser.scripts.ibkr_login_check"), time="09:15",
        description="Looks at whether the IBKR Gateway is still logged in: one TCP connection to the "
                    "configured host and port, the TWS API version handshake and startApi up to nextValidId - no "
                    "account, position, order or execution is ever asked for. Writes no table and no store "
                    "file, only its own record under .cache/ibkr_login/, which the Data Health card reads "
                    "(#162). It exits 0 whatever it finds: a session that expired on its weekly cycle is not "
                    "a failed job. Off until RC_IBKR_LOGIN_CHECK is set, and then it contacts nothing but "
                    "RC_IBKR_HOST:RC_IBKR_PORT (127.0.0.1:4001 by default).",
        # #527: the installed unit's limit (home-server units/life-rc-ibkr-login-check.service: 5min), not 1 h.
        settings=TaskSettings(time_limit_minutes=5)),
    AutomationEntry(
        name="RC-Build", label="Market-store builder (hourly)",
        args=("-m", "revenuechaser.rcdata.build", "run", "--once"), time="00:05", hourly=True,
        unit_name=BUILDER_UNIT,
        description="One pass of the market-store builder (rcdata): takes the queued build requests in order (Fetch, "
                    "Backfill from the Settings page, and the datasets the schedule makes due), builds each serving "
                    "file as a new file and swaps it in. It does not start while a job lock is held or another "
                    "builder runs (exit 3); a request a dead builder left running is failed at start. Writes only "
                    "the market store and ops.sqlite, with its own job_runs2 row per run.",
        # 2 h (avo 6 Nov 2026, #527): 166 runs since 20 Oct peaked at 107 min; at 50 min one was killed (2 Nov)
        settings=TaskSettings(time_limit_minutes=120)),
    AutomationEntry(
        name="RC-SEC-Read", label="SEC reads (nightly check)",
        args=("-m", "revenuechaser.rcdata.build", "run", "--once", "--dataset", "sec/reads"), time="01:10",
        unit_name=SEC_READ_UNIT,
        description="The SEC reader's daily check (avo, 16 Nov 2026): every night, once the US session is over, one "
                    "run of sec/reads. It asks the registered questions about the filings that are new since the "
                    "last run and retries what failed; a changed prompt or a question's first pass waits for a "
                    "request with reread. EVREN has no day cap, a DeepSeek question is asked at most 200 companies a "
                    "day and goes on the next night. With no question registered it asks nothing. 01:10 is five "
                    "minutes after the hourly builder pass, so the two do not start together; it waits up to 30 "
                    "minutes for the store's writer turn. Writes sec_reads.duckdb and its Parquet tree through the "
                    "builder, with its own job_runs2 row.",
        # 30 min waiting for the turn at most, then one 15-minute slice of asking (asker.SLICE_S) and the build
        settings=TaskSettings(time_limit_minutes=90)),
    AutomationEntry(
        name="RC-ValueChain-Sync", label="Value Chain links (nightly, after the SEC reads)",
        args=("-m", "revenuechaser.module_value_chain", "--nightly"), time="04:20", after="RC-SEC-Read",
        description="Rebuilds the Value Chain links once tonight's SEC reads exited 0 (avo, 17 Nov 2026: the SEC "
                    "engine first, then Value Chain; the Relatedness profiles of the Sunday run are read the night "
                    "after). It reads the SEC layer's annual reports, their XBRL customers and the stored profiles: "
                    "no download, no model call. Off the layer it exits 3 and asks for nothing. The rebuild runs in "
                    "the dashboard (POST /run/module_value_chain, the one writer): the task only queues it and "
                    "waits; with the dashboard down it exits 1. 04:20 is after the SEC reads' 90-minute limit "
                    "(the server's timer starts them at 02:35) and clear of the hourly builder pass. Writes boards/value_chain.duckdb (chain_mentions, chain_meta).",
        tables_written=("chain_mentions", "chain_meta"),
        chain_wait_minutes=20,
        settings=TaskSettings(time_limit_minutes=90)),
    AutomationEntry(
        name="RC-Relatedness-Score", label="Relatedness scoring (weekly, when the SEC reads brought something new)",
        args=("-m", "revenuechaser.module_relatedness", "--score"), time="07:30", days=("Saturday",),
        after="RC-SEC-Read",
        description=("Copies the SEC reading service's new company.profile answers into the board's profiles, then "
                     "rescores every pair, caches the new company vectors and writes the payload the board renders. "
                     "No model call, no download and no cost, whatever the board's writer is. A run whose profiles "
                     "are all older than the saved payload is skipped and nothing is written, so a week the service "
                     "read nothing costs nothing. Scoring every pair is ~27 s of CPU for 5,111 profiles (measured "
                     "on the server 20 Nov 2026, #884). Weekly, Saturday 07:30 (avo, 20 Nov 2026: \"Tamam "
                     "haftalik, uygun zamana koy\"): the week's filings are all read by then, the Sunday backups "
                     "and the weekday server jobs are elsewhere, and it still waits for that night's SEC reads to "
                     "exit 0 (their timer starts at 02:35 with a 90-minute limit)."),
        tables_written=("relatedness_profiles", "relatedness_attributes", "relatedness_embeddings",
                        "relatedness_scores"),
        chain_wait_minutes=60,
        settings=TaskSettings(time_limit_minutes=90)),
    AutomationEntry(
        name="RC-Backup-Weekly", label="Weekly backup",
        args=("-m", "revenuechaser.rcdata", "backup"),
        time="03:30", days=("Sunday",), unit_name=BACKUP_WEEKLY_UNIT,
        description="The one backup job (avo, 8 Nov 2026): every Sunday 03:30 it copies, verifies and keeps the "
                    "newest 4 of every file under RAW_STORE_BACKUP_DIR/weekly-v2/<step>/ on the HDD. The steps: "
                    "the DuckDB files the builder writes from Parquet (market, spine, ownership, prices, "
                    "fundamentals, options), the board-result DuckDBs (every boards/<board>.duckdb, each "
                    "CHECKPOINTed first), the needed ops tables (watch lists, "
                    "schedule, switches, automation rows, run records), the Unusual Whales raw files and the SPX "
                    "Gamma tree (one folder per week, unchanged files hard-linked), and edgar_docs as one verified "
                    "zip. Raw downloads and Parquet are not copied: they are fetched again. Nothing leaves the "
                    "machine. A step that fails is logged and the others still run. Before a deploy, "
                    "`rcdata backup --only <kind>` takes a copy by hand that is kept apart from the weekly ones. "
                    "Writes no table.",
        settings=TaskSettings(time_limit_minutes=60)),
    AutomationEntry(
        name="RC-Backup-Watchlists-Daily", label="Watch lists daily backup",
        args=("-m", "revenuechaser.rcdata", "backup", "--only", "watchlists-daily"),
        time="03:10", unit_name=BACKUP_WATCHLISTS_DAILY_UNIT,
        description="Decision C of the spine classification plan (avo, 17 Nov 2026; 03:10 on 18 Nov): every day "
                    "it copies boards/watchlists.duckdb (avo's own lists, nothing rebuilds them) into "
                    "RAW_STORE_BACKUP_DIR/weekly-v2/watchlists-daily/ on the HDD, only when the file changed since "
                    "the newest daily copy, verified, the newest 7 kept. An unchanged day writes nothing and is a "
                    "good run. The weekly copy of the same file goes on. Held by the Backup switch. Writes no table.",
        settings=TaskSettings(time_limit_minutes=15)),
    AutomationEntry(
        name="RC-SPX-Gamma-Fetch", label="SPX Gamma Fetch (nightly)",
        args=("-m", "revenuechaser.module_spx_gamma", "--nightly"), time="06:30", days=_WEEKDAYS,
        description="The SPX Gamma board's Fetch of the latest complete New York session (#291), so every session "
                    "keeps its raw day with the all-expiry ladder the band walls are read from, and the board moves "
                    "to it. About 70 Unusual Whales calls a session, plus the same per session the run's own backfill "
                    "fills (the last two weeks, missing days only). 06:30 Monday to Friday is after the builder's "
                    "first pass of the New York trading day (00:05) stored the previous session's Cboe SPX close, so "
                    "Monday fetches Friday; without that close, or inside the US session, it exits 3 and calls "
                    "nothing. A missed run is not caught up. The Fetch runs in the dashboard (POST /run/spxgamma, "
                    "the one writer): the task only queues it and waits; with the dashboard down it exits 1 and "
                    "nothing is fetched. The job writes the board file boards/spx_gamma.duckdb (raw day, Brier "
                    "record, GEX record, latest pointer; module_spx_gamma/store.py).",
        settings=TaskSettings(start_when_available=False, time_limit_minutes=30)),
    *(AutomationEntry(
        name=f"RC-Fetch-{label.replace(' ', '')}", label=f"{label} Fetch (nightly)",
        args=("-m", "revenuechaser.scripts.board_fetch", board), time=at, unit_name=f"life-rc-fetch-{board}",
        description=(f"The {label} board's Fetch after the nightly prices build (avo 17 Nov 2026, choice a), so the "
                     "forecast ledger freezes every session (#25). It asks nothing until the prices store holds SPY's "
                     "complete bar of the latest complete New York session (exit 3). The Fetch runs in the dashboard "
                     f"(POST /run/{route}, the one writer): the task only queues it and waits; with the dashboard "
                     "down it exits 1. The server's timer is installed switched off and is switched on per board once "
                     "that board's review and rule decisions are done."),
        settings=TaskSettings(time_limit_minutes=120))
      for board, label, route, at in (
          ("ag", "Asymmetric Growth", "module_asymmetric_growth", "05:00"),
          ("swing", "Swing", "swing", "05:10"),
          ("fundamentals", "Fundamentals", "module_fundamentals", "05:20"),
          ("comovement", "Co-movement", "module_comovement", "05:30"))),
    # avo 18 Nov 2026 ("Zamanlayiciyi kur"): Sector Rotation and Earnings Radar had no schedule, only their buttons,
    # so the quadrant snapshot sat at 6 Nov. Same task as the four above, switched ON at install.
    AutomationEntry(
        name="RC-News-Earnings-Weekly", label="News earnings (weekly)",
        args=("-m", "revenuechaser.scripts.board_fetch", "news-earnings"), time="09:00", days=("Sunday",),
        unit_name="life-rc-fetch-news-earnings", tables_written=("news_earnings",),
        description="The News board's Earnings tab (#886, avo 20 Nov 2026): every Sunday 09:00 it writes next "
                    "week's report day of every name on the News watch lists into boards/news.duckdb and renders "
                    "the page. Once a week, because a calendar of next week does not change by the hour. "
                    "Store-only: the days come from the Alpha Vantage earnings calendar the builder already "
                    "serves (fundamentals.earnings_event), the names from the watch lists; no provider is called "
                    "and no session is waited for. The pass runs in the dashboard (POST /run/news_earnings, the "
                    "one writer): the task only queues it and waits; with the dashboard down it exits 1. The "
                    "board's own Fetch runs the same pass, so a Fetch is never a week late.",
        settings=TaskSettings(time_limit_minutes=30)),
    # The News board's hourly reading (#1234, avo 21 Nov 2026 decision A): the EVREN model reads the hour's
    # stored headlines and the reading is stored as fixed-schema fields, each carrying its source sentence.
    AutomationEntry(
        name="RC-News-Reading-Hourly", label="News reading (hourly)",
        args=("-m", "revenuechaser.scripts.board_fetch", "news-reading"), time="00:20", hourly=True,
        unit_name="life-rc-fetch-news-reading", tables_written=("news_reading",),
        description="The News board's reading of the headline flow (#1234): every hour at :20 the EVREN model "
                    "reads the clock hour that has just finished and its reading is written to "
                    "boards/news.duckdb as fixed-schema fields (module_news/reading.FIELDS), each field carrying "
                    "the sentence it came from and the headline id it was copied from; a field the model cannot "
                    "source is dropped, not stored. One call an hour and no fee: the writer is EVREN "
                    "(core/llm_jobs job news.reading), and the pass refuses to run at all on a paid writer "
                    "unless it is started with paid=1, because an hourly pass is a standing cost. An hour with "
                    "no stored headline asks nothing. Store-only otherwise: the headlines come from the board's "
                    "own 5-minute passes and no provider is fetched. The pass runs in the dashboard "
                    "(POST /run/news_reading, the one writer): the task only queues it and waits; with the "
                    "dashboard down it exits 1.",
        settings=TaskSettings(time_limit_minutes=30)),
    AutomationEntry(
        name="RC-Fetch-SectorRotation", label="Sector Rotation Fetch (nightly)",
        args=("-m", "revenuechaser.scripts.board_fetch", "rotation"), time="05:40", unit_name="life-rc-fetch-rotation",
        description="The Sector Rotation board's Fetch after the nightly prices build (avo 18 Nov 2026), so the "
                    "quadrant snapshot Earnings Radar reads is the latest complete session's. It asks nothing until "
                    "the prices store holds SPY's complete bar of that session (exit 3). The Fetch runs in the "
                    "dashboard (POST /run/rotation, the one writer; it also queues the Money flow refresh): the task "
                    "only queues it and waits; with the dashboard down it exits 1. Stored closes only, no Unusual "
                    "Whales call.",
        settings=TaskSettings(time_limit_minutes=120)),
    AutomationEntry(
        name="RC-Fetch-EarningsRadar", label="Earnings Radar Fetch (nightly)",
        args=("-m", "revenuechaser.scripts.board_fetch", "earnings"), time="05:50", days=_WEEKDAYS,
        unit_name="life-rc-fetch-earnings",
        description="The Earnings Radar board's Fetch of the coming New York session's earnings (avo 18 Nov 2026), "
                    "Monday to Friday, after the Sector Rotation Fetch (05:40) stored the quadrants it reads. It asks "
                    "nothing until the prices store holds SPY's complete bar of the last session (exit 3). The Fetch "
                    "runs in the dashboard (POST /run/earnings with no dates: the server's today, which at 05:50 "
                    "Amsterdam is the coming session): the task only queues it and waits; with the dashboard down it "
                    "exits 1. The same Unusual Whales calls as one press of the board's Fetch button.",
        settings=TaskSettings(time_limit_minutes=120)),
)
_BY_NAME = {e.name: e for e in REGISTRY}


def _minutes(hhmm: str) -> int:
    h, m = (int(x) for x in hhmm.split(":"))
    return h * 60 + m


def check_chain(entries: tuple[AutomationEntry, ...]) -> None:
    """A chain step names an earlier registry entry (so no cycles) that runs daily (``chain_cutoff`` reads its time
    as a daily one, so a step after a weekly task would be blocked on every other day), is due 0 to under 12 h after
    its predecessor on the clock (a step due before it would be released by last night's run), and waits a positive
    time shorter than its own time limit."""
    seen: dict[str, AutomationEntry] = {}
    for e in entries:
        if e.hourly and (e.after is not None or e.days):
            raise ValueError(f"{e.name} runs hourly; an hourly row is neither chained nor weekly")
        if e.after is not None:
            if e.after == e.name:
                raise ValueError(f"{e.name} is chained on itself")
            if e.after not in seen:
                known = any(x.name == e.after for x in entries)
                raise ValueError(f"{e.name} is chained on {e.after}, which is "
                                 + ("not an earlier entry" if known else "unknown"))
            if seen[e.after].hourly:
                raise ValueError(f"{e.name} is chained on {e.after}, which runs hourly; a predecessor must run daily")
            if seen[e.after].days:
                raise ValueError(f"{e.name} is chained on {e.after}, which runs weekly "
                                 f"({', '.join(seen[e.after].days)}); a predecessor must run daily")
            gap = (_minutes(e.time) - _minutes(seen[e.after].time)) % (24 * 60)
            if gap >= 12 * 60:
                raise ValueError(f"{e.name} at {e.time} is not due within 12 h after {e.after} at "
                                 f"{seen[e.after].time} on the clock")
            if e.chain_wait_minutes <= 0:
                raise ValueError(f"{e.name} must wait a positive number of minutes")
            if e.settings.limit_minutes is not None and e.chain_wait_minutes >= e.settings.limit_minutes:
                raise ValueError(f"{e.name} waits {e.chain_wait_minutes} min, not less than its time limit")
        seen[e.name] = e


check_chain(REGISTRY)


class AutomationError(Exception):
    http_status = 500


class UnknownTask(AutomationError):
    http_status = 404


class UnknownAction(AutomationError):
    http_status = 400


class SchedulerUnavailable(AutomationError):
    http_status = 409


def entry(name: str) -> AutomationEntry:
    try:
        return _BY_NAME[name]
    except (KeyError, TypeError):
        raise UnknownTask("unknown automation") from None


# --- scheduler interface ------------------------------------------------------

@dataclass
class TaskStatus:
    state: str = "ready"             # ready | disabled | running
    last_run: str | None = None      # ISO text
    next_run: str | None = None
    last_result: int | None = None
    missed_runs: int = 0


class Scheduler:
    """What the panel needs from the OS scheduler. Names are always registry names."""
    available = True

    def status(self, name: str) -> TaskStatus | None:
        """``None`` when the task is not installed."""
        raise NotImplementedError

    def install(self, e: AutomationEntry) -> None:
        raise NotImplementedError

    def set_enabled(self, name: str, enabled: bool) -> None:
        raise NotImplementedError

    def remove(self, name: str) -> None:
        raise NotImplementedError

    def run(self, name: str) -> None:
        raise NotImplementedError


class UnavailableScheduler(Scheduler):
    available = False

    def status(self, name):
        return None

    def _no(self, *a, **k):
        raise SchedulerUnavailable("No scheduler is available on this host")

    install = set_enabled = remove = run = _no


class FakeScheduler(Scheduler):
    """In-memory scheduler; ``calls`` records every call, ``mutations`` the mutating ones."""

    def __init__(self, available: bool = True, tasks: dict[str, TaskStatus] | None = None):
        self.available = available
        self.tasks: dict[str, TaskStatus] = dict(tasks or {})
        self.calls: list[tuple] = []

    @property
    def mutations(self) -> list[tuple]:
        return [c for c in self.calls if c[0] != "status"]

    def status(self, name):
        self.calls.append(("status", name))
        return self.tasks.get(name)

    def install(self, e):
        self.calls.append(("install", e.name))
        self.tasks[e.name] = TaskStatus(state="ready", last_result=RESULT_NOT_YET_RUN,
                                        next_run=f"{e.time}")

    def set_enabled(self, name, enabled):
        self.calls.append(("enable" if enabled else "disable", name))
        if name in self.tasks:
            self.tasks[name].state = "ready" if enabled else "disabled"

    def remove(self, name):
        self.calls.append(("remove", name))
        self.tasks.pop(name, None)

    def run(self, name):
        self.calls.append(("run", name))
        if name in self.tasks:
            self.tasks[name].state = "running"


def package_parent() -> Path:
    """The dir whose child is ``revenuechaser``: the tasks' working directory."""
    return Path(__file__).resolve().parents[2]


# --- Linux: systemd user timers (#158) ----------------------------------------------
#
# One ``<name>.service`` (Type=oneshot, runs ``automations run <name>``) and one ``<name>.timer`` per registry entry,
# both under the user's systemd folder and both named by the exact registry name. ``run_task`` and the chain read the
# logs, not the scheduler, so they behave the same under either scheduler. A user timer runs only while the user's
# systemd instance does: on a server that runs logged off, ``loginctl enable-linger <user>`` once, by hand.

_SYSTEMD_DAYS = {"Monday": "Mon", "Tuesday": "Tue", "Wednesday": "Wed", "Thursday": "Thu", "Friday": "Fri",
                 "Saturday": "Sat", "Sunday": "Sun"}
_SHOW_TIMER = ("ActiveState", "Result", "NextElapseUSecRealtime", "LastTriggerUSec")
_SHOW_SERVICE = ("ActiveState", "Result", "ExecMainStatus", "ExecMainStartTimestamp")


# The variables a unit file may carry, and nothing else: unit files are world-readable and ``.env`` loads the API
# keys into the environment, so the environment is never copied. The data roots are written as this process resolved
# them, so a job systemd starts reads and writes the store and logs the panel reads; without them it would fall back
# to the checkout's own .store/.cache (``config._root``). The others are passed only when set.
UNIT_ENVIRONMENT = ("RC_STORE_DIR", "RC_CACHE_DIR", "RC_EDGAR_DOCS_DIR", "SPX_GAMMA_DATA_ROOT", "RAW_STORE_BACKUP_DIR",
                    "TZ")

# #191 item 6: the provider keys. A job systemd starts gets the allowlist above and nothing else, so on a host that
# keeps its keys in a file outside the checkout (homesrv: the dashboard service's own environment file) a provider job
# would run without them. ``RC_UNIT_ENV_FILE`` names that file and the unit carries the PATH only, never a value:
# unit files are world-readable, and systemd reads the file itself, as root, when the service starts. The ``-`` prefix
# makes a missing file a no-op rather than a failed start.
UNIT_ENV_FILE_ENV = "RC_UNIT_ENV_FILE"


def unit_env_file() -> str | None:
    """The absolute path an installed unit reads its remaining variables from, or None.

    A relative value is refused rather than resolved: systemd would read it against ``/``, not the dashboard's cwd,
    and a file that is silently not there is the failure this line exists to prevent."""
    value = (os.environ.get(UNIT_ENV_FILE_ENV) or "").strip()
    if not value:
        return None
    if not Path(value).is_absolute():
        logger.warning("%s=%r is not an absolute path; no EnvironmentFile= line is written", UNIT_ENV_FILE_ENV, value)
        return None
    return value


def _unit_environment() -> list[tuple[str, str]]:
    resolved = config.resolved_roots()
    out = []
    for name in UNIT_ENVIRONMENT:
        value = resolved.get(name) or os.environ.get(name)
        if value not in (None, ""):
            out.append((name, str(value)))
    return out


def _env_line(name: str, value: str) -> str:
    v = _unit_value(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'Environment="{name}={v}"'


def _systemctl(args: list[str]) -> tuple[int, str, str]:
    """``systemctl --user <args>`` as ``(returncode, stdout, stderr)``. Any failure to run becomes an
    ``AutomationError``."""
    env = dict(os.environ)
    if not env.get("XDG_RUNTIME_DIR") and hasattr(os, "getuid"):
        # A dashboard started outside a login session has no XDG_RUNTIME_DIR, and systemctl --user then cannot
        # find the user's bus. The user manager's runtime folder is always this one.
        env["XDG_RUNTIME_DIR"] = f"/run/user/{os.getuid()}"
    try:
        proc = subprocess.run(["systemctl", "--user", *args], capture_output=True, encoding="utf-8",
                              errors="replace", timeout=60, env=env)
    except (OSError, subprocess.SubprocessError) as exc:
        raise AutomationError(f"could not run systemctl: {exc}") from None
    return proc.returncode, proc.stdout or "", proc.stderr or ""


def _user_unit_dir() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or ""
    if not Path(base).is_absolute():                 # the XDG spec: a relative value is invalid and ignored
        base = str(Path.home() / ".config")
    return Path(base) / "systemd" / "user"


def on_calendar(e: AutomationEntry) -> str:
    """The entry's ``time`` and ``days`` as a systemd ``OnCalendar=`` spec, in the machine's local time."""
    if e.hourly:
        return f"*-*-* *:{e.time[-2:]}:00"
    days = ",".join(_SYSTEMD_DAYS[d] for d in e.days)
    return f"{days + ' ' if days else ''}*-*-* {e.time}:00"


#: A zone name a unit file may carry after ``OnCalendar=``: one word, no space and no ``%``.
_ZONE_RE = re.compile(r"^[A-Za-z0-9+_./-]+$")


def unit_timezone(env: list[tuple[str, str]] | None = None) -> str | None:
    """The zone an installed unit's ``OnCalendar=`` is read in, or None to leave it to the user manager's own zone."""
    pairs = _unit_environment() if env is None else env
    tz = next((v for k, v in pairs if k == "TZ"), "").strip()
    return tz if tz and _ZONE_RE.match(tz) else None


def on_calendar_line(e: AutomationEntry, tz: str | None = None) -> str:
    """The ``OnCalendar=`` value an install writes: the spec plus the zone the service carries (#191 item 4).

    ``TZ`` goes into the service, but a bare spec fires in the **user manager's** zone, while the chain cutoff and the
    job itself read ``TZ``: on a host whose two zones differ the timer fired at the wrong hour. Keep ``on_calendar``
    itself zone-free -- the Control board reads its minute field."""
    spec = on_calendar(e)
    return f"{spec} {tz}" if tz else spec


def _unit_value(value: str) -> str:
    """A value for a unit file line: one line, with ``%`` doubled so systemd expands no specifier in it."""
    value = str(value)
    if "\n" in value or "\r" in value or value.endswith("\\"):
        raise AutomationError("a unit file value cannot hold a line break or end in a backslash")
    return value.replace("%", "%%")


def _exec_arg(value: str) -> str:
    """One ``ExecStart=`` word: double-quoted, with ``\\``, ``"``, ``%`` and ``$`` escaped."""
    v = _unit_value(value).replace("\\", "\\\\").replace('"', '\\"').replace("$", "$$")
    return f'"{v}"'


def _show_value(v: str | None) -> str | None:
    """A ``systemctl show --timestamp=unix`` time as local ISO text; empty, ``n/a`` or 0 is ``None``."""
    v = (v or "").strip()
    if v.startswith("@"):
        v = v[1:]
    try:
        ts = float(v)
    except ValueError:
        return None
    if ts <= 0:
        return None
    if ts > 1e11:                    # a raw microsecond count, not seconds
        ts /= 1e6
    try:
        return datetime.fromtimestamp(ts, timezone.utc).astimezone().isoformat()
    except (OverflowError, OSError, ValueError):
        # A stamp outside the range a date can hold (``infinity`` in a harness) is a time we do not have, not a crash.
        return None


def parse_show(text: str) -> tuple[dict[str, str], dict[str, str]]:
    """``systemctl show <timer> <service>`` -> the two property blocks, in that order."""
    blocks: list[dict[str, str]] = [{}]
    for line in (text or "").splitlines():
        if not line.strip():
            if blocks[-1]:
                blocks.append({})
            continue
        key, sep, value = line.partition("=")
        if sep:
            blocks[-1][key.strip()] = value.strip()
    blocks = [b for b in blocks if b]
    if len(blocks) != 2 or "ActiveState" not in blocks[0] or "Result" not in blocks[1]:
        raise AutomationError("unreadable scheduler answer")
    return blocks[0], blocks[1]


def _reset_hint(unit: str, user: bool) -> str:
    """The command that clears a failed timer (#191 item 3). The panel offers an error row no button, so the row's own
    message has to name the way out; ``status`` only prints the failure again."""
    scope = "--user " if user else ""
    return f"clear it with: systemctl {scope}reset-failed {unit}"


def _task_status(t: dict[str, str], sv: dict[str, str], hint: str) -> TaskStatus:
    """A timer's and its service's ``systemctl show`` properties as a ``TaskStatus``; ``hint`` is what to do about a
    failed timer."""
    if t.get("ActiveState") == "failed" or t.get("Result", "success") != "success":
        # A failed timer never fires again until it is reset: an error row, never "disabled" (which it is not).
        raise AutomationError(f"the timer failed ({t.get('Result') or t.get('ActiveState')}); {hint}")
    started = _show_value(sv.get("ExecMainStartTimestamp"))
    triggered = _show_value(t.get("LastTriggerUSec"))
    if sv.get("ActiveState") in ("activating", "active", "reloading", "deactivating"):
        state, result = "running", RESULT_RUNNING
    else:
        state = "ready" if t.get("ActiveState") == "active" else "disabled"
        if started:
            try:
                code = int(sv.get("ExecMainStatus") or 0)
            except ValueError:
                raise AutomationError("unreadable scheduler answer") from None
            result = code if code or sv.get("Result") == "success" else 1
        elif triggered:
            result = None            # the manager restarted since: the exit code is gone, the logs keep it
        else:
            result = RESULT_NOT_YET_RUN
    return TaskStatus(state=state, last_run=started or triggered,
                      next_run=_show_value(t.get("NextElapseUSecRealtime")), last_result=result)


#: Registry names whose server unit is not ``life-`` + the name in lower case (home-server ``units/``).
SYSTEM_UNITS = {"RC-Relatedness-OffPeak": "life-rc-relatedness"}


def system_unit(e: AutomationEntry) -> str:
    """The SYSTEM unit a server installs for ``e`` from the home-server repository."""
    return e.unit_name or SYSTEM_UNITS.get(e.name) or "life-" + e.name.lower()


def _systemctl_system(args: list[str]) -> tuple[int, str, str]:
    """``systemctl <args>`` against the SYSTEM manager, unprivileged (``show`` needs no root), 10 s at most."""
    try:
        p = subprocess.run(["systemctl", *args], capture_output=True, encoding="utf-8", errors="replace",
                           timeout=10, check=False)
    except (OSError, subprocess.SubprocessError):
        return 1, "", ""
    return p.returncode, p.stdout or "", p.stderr or ""


def system_status(e: AutomationEntry, run: Callable[[list[str]], tuple[int, str, str]] = _systemctl_system
                  ) -> TaskStatus | None:
    """Read-only: the state of the server's own timer for ``e``, or None when the host has none.

    On homesrv the tasks are SYSTEM units installed from home-server, which no scheduler of this module manages,
    so the panel said "Scheduler unavailable" on every row (16 Nov 2026). Nothing here installs, switches or runs:
    that stays with the Grafana Jobs board."""
    unit = system_unit(e)
    rc, out, _ = run(["show", "--timestamp=unix",
                      "--property=" + ",".join(sorted({"LoadState", *_SHOW_TIMER, *_SHOW_SERVICE})),
                      f"{unit}.timer", f"{unit}.service"])
    if rc != 0:
        return None
    try:
        t, sv = parse_show(out)
    except AutomationError:
        return None
    if t.get("LoadState") != "loaded":
        return None
    return _task_status(t, sv, _reset_hint(f"{unit}.timer", user=False))


class LinuxScheduler(Scheduler):
    """systemd user timers, exact registry names only, one unit pair per entry."""

    def __init__(self, runner: Callable[[list[str]], tuple[int, str, str]] = _systemctl,
                 python: str | None = None, workdir: Path | str | None = None, unit_dir: Path | str | None = None):
        self._run = runner
        self._python = python or sys.executable
        self._workdir = str(workdir or package_parent())
        self.unit_dir = Path(unit_dir) if unit_dir else _user_unit_dir()

    def _exec(self, *args: str) -> str:
        rc, out, err = self._run(list(args))
        if rc != 0:
            raise AutomationError(((err or out or "").strip() or "scheduler call failed")[-400:])
        return out

    def _files(self, name: str) -> tuple[Path, Path]:
        unit = entry(name).unit
        return self.unit_dir / f"{unit}.service", self.unit_dir / f"{unit}.timer"

    def status(self, name):
        name = entry(name).name
        service, timer = self._files(name)
        try:
            if not (service.is_file() and timer.is_file()):
                return None
        except OSError as exc:
            raise AutomationError(f"the unit folder could not be read: {exc}") from None
        out = self._exec("show", "--timestamp=unix",
                         "--property=" + ",".join(sorted(set(_SHOW_TIMER + _SHOW_SERVICE))),
                         timer.name, service.name)
        return _task_status(*parse_show(out), _reset_hint(timer.name, user=True))

    def install(self, e):
        e = entry(e.name)
        s = e.settings
        env = _unit_environment()
        env_file = unit_env_file()
        service_text = "\n".join([
            "[Unit]",
            f"Description={_unit_value(e.label)} (RevenueChaser {e.name})",
            "",
            "[Service]",
            "Type=oneshot",
            f"WorkingDirectory={_unit_value(self._workdir)}",
            *(_env_line(k, v) for k, v in env),
            *([f"EnvironmentFile=-{_unit_value(env_file)}"] if env_file else []),
            "ExecStart=" + " ".join(_exec_arg(a) for a in
                                    (self._python, "-m", "revenuechaser.core.automations", "run", e.name)),
            ("TimeoutStartSec=infinity" if s.no_time_limit else
             f"TimeoutStartSec={int(s.time_limit_minutes)}min" if s.time_limit_minutes is not None
             else f"TimeoutStartSec={int(s.time_limit_hours)}h"),
            "",
        ])
        timer_text = "\n".join([
            "[Unit]",
            f"Description={_unit_value(e.schedule)} (RevenueChaser {e.name})",
            "",
            "[Timer]",
            f"OnCalendar={_unit_value(on_calendar_line(e, unit_timezone(env)))}",
            f"Unit={e.unit}.service",
            f"Persistent={'true' if s.start_when_available else 'false'}",
            # No WakeSystem=: a user timer cannot arm a wake alarm (CAP_WAKE_ALARM), and asking for one leaves the
            # timer failed and never run, so no row asks the machine to wake up for it.
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ])
        service, timer = self._files(e.name)
        # #191 item 1: a reinstall over a working pair that then fails puts that pair back, rather than removing it.
        before = {p: p.read_text(encoding="utf-8") for p in (service, timer) if p.is_file()}
        try:
            self.unit_dir.mkdir(parents=True, exist_ok=True)
            for path, text in ((service, service_text), (timer, timer_text)):
                tmp = path.with_name(path.name + ".tmp")
                try:
                    tmp.write_text(text, encoding="utf-8")
                    tmp.replace(path)
                finally:
                    tmp.unlink(missing_ok=True)
        except OSError as exc:
            try:
                self._roll_back(e.name, before)
            except AutomationError:
                pass
            raise AutomationError(f"the unit files could not be written: {exc}") from None
        try:
            self._exec("daemon-reload")
            self._exec("enable", "--now", timer.name)
        except AutomationError:
            # Roll back: a half-installed task reads as an error row, which the panel offers no button for.
            # #191 item 2: ``enable --now`` writes timers.target.wants/<name>.timer before the start can fail, so an
            # install that created the pair also takes that symlink away. A reinstall over an older pair does not: the
            # files go back to their old text and the symlink the first install made is still theirs.
            if not before:
                self._try("disable", timer.name)
            self._roll_back(e.name, before)
            self._try("daemon-reload")
            raise

    def _roll_back(self, name: str, before: dict) -> None:
        """Undo an install: the files it created go, the files it overwrote get their old text back."""
        if not before:
            self._unlink(name)
            return
        try:
            for path in self._files(name):
                if path in before:
                    path.write_text(before[path], encoding="utf-8")
                else:
                    path.unlink(missing_ok=True)
        except OSError as exc:
            raise AutomationError(f"the unit files could not be restored: {exc}") from None

    def _try(self, *args: str) -> AutomationError | None:
        try:
            self._exec(*args)
        except AutomationError as exc:
            return exc
        return None

    def _unlink(self, name: str) -> None:
        try:
            for path in self._files(name):
                path.unlink(missing_ok=True)
        except OSError as exc:
            raise AutomationError(f"the unit files could not be removed: {exc}") from None

    def set_enabled(self, name, enabled):
        self._exec("enable" if enabled else "disable", "--now", f"{entry(name).unit}.timer")

    def remove(self, name):
        """Disable, delete both files, reload. The files go even when systemctl fails (no bus), so Remove can always
        clean up what Install left; the first failure is still raised, so the panel says so."""
        name = entry(name).name
        failed = self._try("disable", "--now", f"{entry(name).unit}.timer")
        try:
            self._unlink(name)
        except AutomationError as exc:
            failed = failed or exc
        reloaded = self._try("daemon-reload")
        failed = failed or reloaded
        if failed:
            raise failed

    def run(self, name):
        self._exec("start", "--no-block", f"{entry(name).unit}.service")


# The Linux backend is opt-in: a server that already runs these jobs as system timers must not offer Install on every
# row, which would add a second schedule beside the first (the paid RC-Relatedness-OffPeak among them).
SCHEDULER_ENV = "RC_SCHEDULER"
SCHEDULER_SYSTEMD_USER = "systemd-user"


def _default_scheduler() -> Scheduler:
    choice = os.environ.get(SCHEDULER_ENV, "").strip()
    if sys.platform.startswith("linux"):
        if choice == SCHEDULER_SYSTEMD_USER:
            if shutil.which("systemctl"):
                return LinuxScheduler()
            logger.warning("%s=%s, but systemctl is not on PATH: the Automations panel stays unavailable",
                           SCHEDULER_ENV, SCHEDULER_SYSTEMD_USER)
        elif choice:
            # #191 item 5: "systemd" and "Systemd-User" used to read as "no scheduler", with nothing said anywhere.
            logger.warning("%s=%r is not a scheduler name; the only value this host accepts is %r, so the "
                           "Automations panel stays unavailable", SCHEDULER_ENV, choice, SCHEDULER_SYSTEMD_USER)
    return UnavailableScheduler()


_scheduler: Scheduler | None = None
_lock = threading.Lock()


def get_scheduler() -> Scheduler:
    global _scheduler
    with _lock:
        if _scheduler is None:
            _scheduler = _default_scheduler()
        return _scheduler


def set_scheduler(s: Scheduler | None) -> None:
    global _scheduler
    with _lock:
        _scheduler = s


# --- rows ---------------------------------------------------------------------

def static_row(e: AutomationEntry) -> dict:
    """The fixed fields of a row; reading them never touches the scheduler."""
    return {
        "name": e.name, "label": e.label, "schedule": e.schedule, "command": e.command,
        "tables_written": list(e.tables_written), "offpeak_gated": e.offpeak_gated,
        "default_install": e.default_install, "settings": e.settings.summary(),
        "log_path": str(e.log_path), "description": e.description, "after": e.after,
    }


def static_rows() -> list[dict]:
    return [static_row(e) for e in REGISTRY]


# --- the Stop a row offers (#165, avo's decision (a), 20 Nov 2026) --------------------
#
# The only stop is the **cooperative** cancel that already exists: ``POST /api/job/<id>/cancel`` over
# ``app.jobs.cancel`` and ``core.job_control.StopToken`` (#243, PL4). A queued job ends ``cancelled`` at once, a
# running one at its runner's next checkpoint, never mid-write; a running job whose runner has no checkpoint
# refuses. So nothing is added to ``ACTIONS``, ``Scheduler`` gains no ``stop``, and no privileged verb exists:
# option (c), a real kill of an OS-started run, was declined and is not a follow-up. What is served here is the
# answer to one question per row -- is there something to stop, and which job id stops it, or why is there none.

#: Which dashboard job each task that does **not** name its board posts. The board rows are read off their own
#: ``args`` (``scripts.board_fetch <board>`` -> ``board_fetch.ROUTES``), so a new board row needs no entry here.
_QUEUED_JOB_MODULES: dict[str, tuple[str, ...]] = {
    # Both say so in their own description: the task posts the run to the dashboard, the one writer, and waits.
    "RC-ValueChain-Sync": ("module_value_chain",),
    "RC-SPX-Gamma-Fetch": ("spxgamma",),
}

STOP_NOT_DASHBOARD = ("This job runs in a process of its own, started by the server's timer, so the dashboard "
                      "has nothing to stop. It ends at its unit's time limit.")
STOP_NOT_RUNNING = "No run of this job is queued or running in the dashboard now."
STOP_NO_CHECKPOINT = ("The run has started and this job has no checkpoint to stop at, so it is left to finish: "
                      "stopping it would leave a half-written store.")


def dashboard_job_modules(e: AutomationEntry) -> tuple[str, ...]:
    """The dashboard job a task queues, read off the task's own command, or ``()`` when it writes by itself.

    A ``scripts.board_fetch <board>`` task posts ``/run/<route>`` and polls the job (board_fetch's module
    docstring), and a dashboard job route carries its module's own name, so the route **is** the module.
    """
    if len(e.args) == 3 and e.args[1] == "revenuechaser.scripts.board_fetch":
        from revenuechaser.scripts.board_fetch import ROUTES    # lazy: core must not import scripts on import
        route = ROUTES.get(e.args[2])
        return (route,) if route else ()
    return _QUEUED_JOB_MODULES.get(e.name, ())


def stop_state(e: AutomationEntry, job: dict | None) -> dict:
    """Whether this row has a Stop, and what it stops. ``job`` is the queued/running dashboard job, if any.

    Pure, so ``core`` keeps knowing nothing about ``app.jobs``: the caller looks the job up and passes its view
    (``app.jobs.active_job``). The answer mirrors ``app.jobs.cancel`` exactly, so the panel never offers a button
    that the cancel route would answer 409 to.
    """
    none = {"can_stop": False, "job_id": None, "cancel_url": None, "reason": STOP_NOT_DASHBOARD}
    if not dashboard_job_modules(e):
        return none
    if job is None or job.get("status") not in ("queued", "running"):
        return {**none, "reason": STOP_NOT_RUNNING}
    if job["status"] == "running" and not job.get("cancellable"):
        return {**none, "job_id": job["id"], "reason": STOP_NO_CHECKPOINT}
    return {"can_stop": True, "job_id": job["id"], "cancel_url": f"/api/job/{job['id']}/cancel",
            "reason": ("Stops the run the dashboard is doing for this task: a queued one at once, a started one "
                       "at its next checkpoint. Nothing is interrupted mid-write.")}


def map_result(code: int | None) -> tuple[str, str]:
    """``(kind, text)``: ok | neutral | running | red | none."""
    if code is None:
        return "none", "—"
    if code == RESULT_OK:
        return "ok", "ok"
    if code == RESULT_NOT_YET_RUN:
        return "neutral", "not run yet"
    if code == RESULT_RUNNING:
        return "running", "running"
    return "red", f"failed (0x{code & 0xFFFFFFFF:X})"


def _read_tail(path: Path, nbytes: int = 8192) -> str:
    try:
        with open(path, "rb") as fh:
            fh.seek(0, 2)
            size = fh.tell()
            fh.seek(max(0, size - nbytes))
            return fh.read().decode("utf-8", errors="replace")
    except OSError:
        return ""


def log_tail(path: Path) -> list[str]:
    lines = [ln.rstrip() for ln in _read_tail(path).splitlines() if ln.strip()]
    return [ln[:_TAIL_WIDTH] for ln in lines[-_TAIL_LINES:]]


def last_success(path: Path) -> str | None:
    """ISO time of the last ``=== <iso> exit 0`` footer in the log, if any."""
    best = None
    for ln in _read_tail(path, 64 * 1024).splitlines():
        m = _EXIT_RE.match(ln)
        if m and int(m.group(2)) == 0:
            best = m.group(1)
    return best


def _age(iso: str | None, now: datetime) -> str:
    if not iso:
        return "never"
    try:
        t = datetime.fromisoformat(iso)
    except ValueError:
        return "—"
    if t.tzinfo is None:
        t = t.replace(tzinfo=timezone.utc)
    secs = max(0, int((now - t).total_seconds()))
    if secs < 3600:
        return f"{secs // 60} min ago"
    if secs < 172800:
        return f"{secs // 3600} h ago"
    return f"{secs // 86400} d ago"


def live_row(e: AutomationEntry, sched: Scheduler, now: datetime | None = None, system=None,
             active_job: Callable[[tuple[str, ...]], dict | None] | None = None) -> dict:
    """``system`` reads the server's own timer when no scheduler is connected (default ``system_status``); a row
    it answers is ``managed: "system"``: its state, last and next run are real, and the panel offers no button.

    ``active_job`` looks a queued or running dashboard job up by the modules the task queues (#165); without it
    every row's ``stop`` is the reason it has none, which is what a caller with no job queue should see.
    """
    now = now or datetime.now(timezone.utc)
    row = static_row(e)
    modules = dashboard_job_modules(e)
    job = active_job(modules) if (active_job and modules) else None
    row["stop"] = stop_state(e, job)
    managed = None
    try:
        st = sched.status(e.name) if sched.available else (system or system_status)(e)
        if st is not None and not sched.available:
            managed = "system"
            row.update(managed=managed, unit=system_unit(e))
    except AutomationError as exc:
        # One unreadable task is an error row, never "not installed" (which offers Install)
        # and never a failure of the whole list.
        row.update(state="error", result_kind="red", result_text=str(exc)[:400],
                   last_run=None, next_run=None, missed_runs=0,
                   last_success=last_success(e.log_path),
                   last_success_age=_age(last_success(e.log_path), now),
                   log_tail=log_tail(e.log_path))
        return row
    if not sched.available and managed is None:
        state = "unavailable"
    elif st is None:
        state = "not_installed"
    elif st.state == "disabled":
        state = "disabled"
    elif st.state == "running" or st.last_result == RESULT_RUNNING:
        state = "running"
    else:
        state = "enabled"
    kind, text = map_result(st.last_result if st else None)
    ok_at = last_success(e.log_path)
    if ok_at is None and st and st.last_result == RESULT_OK:
        ok_at = st.last_run
    row.update(
        state=state, result_kind=kind, result_text=text,
        last_run=st.last_run if st else None, next_run=st.next_run if st else None,
        missed_runs=st.missed_runs if st else 0,
        last_success=ok_at, last_success_age=_age(ok_at, now),
        log_tail=log_tail(e.log_path))
    return row


def live_state(sched: Scheduler | None = None, now: datetime | None = None, system=None,
               active_job: Callable[[tuple[str, ...]], dict | None] | None = None) -> dict:
    """``available`` is False only when nothing could be read: no scheduler and no server timer for any row."""
    sched = sched or get_scheduler()
    rows = [live_row(e, sched, now, system, active_job) for e in REGISTRY]
    served = any(r.get("managed") for r in rows)
    for r in rows:
        if served and r["state"] == "unavailable":
            # this host runs its tasks as server timers and has none for this row: not installed, and no button
            r.update(state="not_installed", managed="system", unit=None)
    return {"available": bool(sched.available) or served, "rows": rows}


def apply(name: str, action: str, sched: Scheduler | None = None) -> dict:
    """Run one panel action on one registry task and return its fresh row."""
    e = entry(name)
    if action not in ACTIONS:
        raise UnknownAction("unknown action")
    sched = sched or get_scheduler()
    if not sched.available:
        raise SchedulerUnavailable("No scheduler is available on this host")
    if action == "install":
        sched.install(e)
    elif action == "enable":
        sched.set_enabled(e.name, True)
    elif action == "disable":
        sched.set_enabled(e.name, False)
    elif action == "remove":
        sched.remove(e.name)
    else:
        sched.run(e.name)
    return live_row(e, sched)


# --- the nightly chain (#129 slice E) ----------------------------------------------
#
# A chained entry stays its own scheduled task with its own daily trigger, which is its
# not-before time. When it starts, it waits for its predecessor's run of tonight, read from the
# predecessor's log: the newest run that started at or after the predecessor's last scheduled
# time. That run exiting 0 releases the step; any other exit (a failure, or a step blocked in
# turn) blocks it at once; no such run within ``chain_wait_minutes`` blocks it too. A blocked
# step does not run its command and exits ``CHAIN_BLOCKED``, so its row is red with the reason
# in the log. The check runs when the task starts, not when it was scheduled, so a catch-up
# after a sleeping night waits for the predecessor's own catch-up.

CHAIN_POLL_SECONDS = 60
_START_RE = re.compile(r"^=== (\S+) start ")


@dataclass(frozen=True)
class RunRecord:
    start: datetime
    end: datetime | None   # None while the run is going (or when it died without a footer)
    rc: int | None


def chain_cutoff(hhmm: str, now: datetime, tz: tzinfo | None = None) -> datetime:
    """The last time at or before ``now`` that a daily ``hhmm`` task (local time) was due.

    ``tz`` None means the machine's local zone, which is what the timers trigger on.
    """
    h, m = (int(x) for x in hhmm.split(":"))
    if tz is None:
        local_now = now.astimezone()
        at = lambda d: datetime.combine(d, dtime(h, m)).astimezone()  # noqa: E731
    else:
        local_now = now.astimezone(tz)
        at = lambda d: datetime.combine(d, dtime(h, m), tzinfo=tz)  # noqa: E731
    cut = at(local_now.date())
    return cut if cut <= local_now else at(local_now.date() - timedelta(days=1))


def _parse_iso(text: str) -> datetime | None:
    try:
        t = datetime.fromisoformat(text)
    except ValueError:
        return None
    return t if t.tzinfo else t.replace(tzinfo=timezone.utc)


def last_run(path: Path) -> RunRecord | None:
    """The newest run in a task's log: its start, and its exit if a footer follows it."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    rec: RunRecord | None = None
    for ln in text.splitlines():
        m = _START_RE.match(ln)
        if m and (t := _parse_iso(m.group(1))) is not None:
            rec = RunRecord(start=t, end=None, rc=None)
            continue
        m = _EXIT_RE.match(ln)
        if m and rec is not None:   # the last footer of a run wins: run_task writes it after the child's output
            rec = RunRecord(start=rec.start, end=_parse_iso(m.group(1)), rc=int(m.group(2)))
    return rec


def wait_for_chain(e: AutomationEntry, *, clock: Callable[[], datetime] | None = None,
                   sleep: Callable[[float], None] | None = None,
                   tz: tzinfo | None = None) -> tuple[bool, str]:
    """``(released, log line)`` for a chained entry; see the block comment above."""
    clock = clock or (lambda: datetime.now(timezone.utc))
    sleep = sleep or _time.sleep
    pred = entry(e.after)
    started = clock()
    cutoff = chain_cutoff(pred.time, started, tz)
    deadline = started + timedelta(minutes=e.chain_wait_minutes)
    while True:
        r = last_run(pred.log_path)
        tonight = r is not None and r.start >= cutoff
        if tonight and r.rc is not None:
            line = f"{pred.name} exit {r.rc} at {r.end.isoformat() if r.end else '?'}"
            return r.rc == RESULT_OK, line
        if clock() >= deadline:
            state = "still running" if tonight else "no run started"
            return False, (f"{pred.name} has not succeeded since {cutoff.isoformat()} "
                           f"(waited {e.chain_wait_minutes} min; {state})")
        sleep(CHAIN_POLL_SECONDS)


# --- the command a task runs ----------------------------------------------------
#
# A task's command runs as a subprocess, so the dashboard's job registry (app/jobs.py) never sees it. Its records
# are its log and, since #136, one ``ops.job_runs2`` row per run (``job`` = the registry name, ``trigger`` =
# ``schedule``) with what the run did in ``counts``. The old ``job_runs`` row lived in the raw.duckdb that went with
# #860. A table writer still gets ``RC_RUN_ID`` and ``RC_RUN_SOURCE`` (``rawstore.task_run``), so the run ids it
# writes carry the task.
#
# ``counts`` comes from the step's own stdout: every CLI prints one JSON result object as its last line (``--report``
# is the file form of the same thing). The run reads back only what the subprocess appended to the log, from the
# offset the log stood at before it started, so a long run's output is never held in memory twice.

#: At most this much of a step's output is read back looking for its result line. A CLI prints the object last, and
#: a line longer than this is not one we can parse anyway.
COUNTS_TAIL_BYTES = 64 * 1024


def counts_from_output(text: str) -> dict | None:
    """The last line of ``text`` that is a JSON object, as a dict; None when there is none (#136).

    A step prints its result as one object on its own line. Anything else it logged — a warning, a progress line,
    a traceback — is not an object and is passed over, and a step that prints nothing parseable records no counts
    rather than a wrong one. An empty object counts as none: the column is for what a run did.
    """
    for line in reversed(text.splitlines()):
        line = line.strip()
        if not line.startswith("{") or not line.endswith("}"):
            continue
        try:
            got = json.loads(line)
        except ValueError:
            continue
        if isinstance(got, dict) and got:
            return got
    return None


def _counts_of_run(log: Path, offset: int) -> dict | None:
    """The result object the step printed, read from ``log`` after ``offset``. Never raises: a log that cannot be
    read back costs the counts, not the run's row."""
    try:
        size = log.stat().st_size
        with open(log, "rb") as fh:
            fh.seek(max(offset, size - COUNTS_TAIL_BYTES))
            tail = fh.read()
    except OSError:
        return None
    return counts_from_output(tail.decode("utf-8", "replace"))


def _run_log_start(run_id: str, name: str) -> bool:
    """Open the run's ``ops.job_runs2`` row; False when the ops records could not take it. Best-effort
    bookkeeping (#282): a task must run even with the ops store busy or absent."""
    try:
        from revenuechaser.rcdata import ops
        ops.start_run(run_id, None, "schedule", job=name)
    except Exception:  # noqa: BLE001 — bookkeeping, never the reason a task does not run
        logger.debug("could not open the run log row for %s", name, exc_info=True)
        return False
    return True


def _run_log_finish(run_id: str, rc: int, counts: dict | None) -> None:
    """Close the run's row with the exit code's status and its counts. Never raises, for the same reason."""
    try:
        from revenuechaser.rcdata import ops
        ops.finish_run(run_id, "done" if rc == RESULT_OK else "failed",
                       None if rc == RESULT_OK else f"exit {rc}", counts)
    except Exception:  # noqa: BLE001
        logger.debug("could not close the run log row %s", run_id, exc_info=True)


#: The registry rows the board's backup switch stops (#527); the fetch switch stops every other row but these and
#: ``SWITCH_EXEMPT``.
BACKUP_TASKS = frozenset({"RC-Backup-Weekly", "RC-Backup-Watchlists-Daily"})
#: A status read, not a fetch: the top bar's IBKR state comes from it, so it runs whatever the switches say.
SWITCH_EXEMPT = frozenset({"RC-IBKR-Login-Check"})


def switch_for(name: str) -> str | None:
    """Which board switch holds the task: ``"backup"``, ``"fetch"`` or None (#527)."""
    if name in SWITCH_EXEMPT:
        return None
    return "backup" if name in BACKUP_TASKS else "fetch"


def _switched_off(name: str) -> str | None:
    """``skipped: the <switch> switch is off (<by> at <when>)`` while the task's switch is off, else None. A switch
    that cannot be read does not stop the task: the switch is a convenience, the backup must not miss a night."""
    switch = switch_for(name)
    if switch is None:
        return None
    try:
        from revenuechaser.rcdata import ops
        off = ops.switch_off(switch)
    except Exception:  # noqa: BLE001
        return None
    return f"skipped: {ops.switch_words(switch, off)}" if off is not None else None


#: How much of a failed run's reason ``run_task`` echoes. ``homeops/runs.py`` keeps a job's last line as its
#: ``job_runs.message`` and cuts it at 500 characters.
REASON_MAX = 500


def last_reason(log: Path, start: int, limit: int = REASON_MAX) -> str:
    """The last line the command wrote to ``log`` from byte ``start`` on, without this runner's own ``=== `` lines.

    "" when the command said nothing, or the log cannot be read: a reason we do not have is never invented.
    """
    try:
        with open(log, "r", encoding="utf-8", errors="replace") as fh:
            fh.seek(start)
            said = [ln.strip() for ln in fh.read().splitlines()
                    if ln.strip() and not ln.startswith("=== ")]
    except OSError:
        return ""
    return said[-1][:limit] if said else ""


def run_task(name: str, python: str | None = None, cwd: Path | str | None = None, *,
             clock: Callable[[], datetime] | None = None, sleep: Callable[[float], None] | None = None,
             tz: tzinfo | None = None) -> int:
    """Run a registry entry's command, appending its output and exit code to its log.

    A chained entry first waits for its predecessor (``wait_for_chain``); blocked, it exits
    ``CHAIN_BLOCKED`` without running its command.

    The run also gets a row in the ops run log (#136): ``job`` is the registry name, and ``counts`` is the result
    object the step printed last (``counts_from_output``). A row is opened only for a run that reaches its command,
    so a switched-off or chain-blocked pass leaves none, as it leaves no output.

    The command's own output goes to the log and nowhere else, so a command that failed also has its exit code and
    its last line echoed on **this** process's stdout (#1119). On the server this runner is itself a child of
    ``jobrun``, which keeps a job's last line as its ``job_runs.message`` and writes it to its own log and the
    journal: without the echo a red hourly row says "exit 1" and names no reason in any of the three places a
    person looks, and only ``<entry>.log`` holds it.
    """
    import os
    import uuid

    e = entry(name)
    log = e.log_path
    log.parent.mkdir(parents=True, exist_ok=True)
    try:
        if log.stat().st_size > _LOG_MAX_BYTES:
            log.replace(log.with_suffix(".log.1"))
    except OSError:
        pass
    stamp = lambda: datetime.now(timezone.utc).isoformat(timespec="seconds")  # noqa: E731
    run_id = uuid.uuid4().hex[:12]

    with open(log, "a", encoding="utf-8") as fh:
        fh.write(f"=== {stamp()} start {e.name}\n")
        fh.flush()
        off = _switched_off(e.name)
        if off is not None:
            fh.write(off + "\n")
            fh.write(f"=== {stamp()} exit {RESULT_OK}\n")
            return RESULT_OK
        if e.after:
            fh.write(f"chain: waiting for {e.after} (up to {e.chain_wait_minutes} min)\n")
            fh.flush()
            released, line = wait_for_chain(e, clock=clock, sleep=sleep, tz=tz)
            if not released:
                fh.write(f"chain: blocked: {line}\n")
                fh.write(f"=== {stamp()} exit {CHAIN_BLOCKED}\n")
                return CHAIN_BLOCKED
            fh.write(f"chain: {line}\n")
            fh.flush()
        # Every command gets the chain id, whether or not it writes tables: it is what ties this run's row to the
        # rows of the runs it causes (a builder pass's dataset runs), and the step that writes no table has
        # children too (review of 20 Nov 2026, step 1). ``RC_RUN_ID`` stays what it was: the writer's stamp.
        env = {**os.environ}
        try:
            from revenuechaser.rcdata import ops as _ops
            env[_ops.CHAIN_ID_ENV] = run_id
        except Exception:  # noqa: BLE001 — bookkeeping, never the reason a task does not run
            logger.debug("could not read the chain variable's name for %s", e.name, exc_info=True)
        if e.tables_written:
            from revenuechaser.core import rawstore
            env.update({rawstore.RUN_ID_ENV: run_id, rawstore.RUN_SOURCE_ENV: e.name})
        logged = _run_log_start(run_id, e.name)
        fh.flush()
        before = fh.tell()                  # where the step's own output starts, for ``_counts_of_run`` and the echo
        try:
            rc = subprocess.run([python or sys.executable, *e.args],
                                cwd=str(cwd or package_parent()),
                                stdout=fh, stderr=subprocess.STDOUT, env=env,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                                ).returncode
        except OSError as exc:
            fh.write(f"could not start: {exc}\n")
            rc = 1
        fh.flush()
        if logged:
            _run_log_finish(run_id, rc, _counts_of_run(log, before))
        fh.write(f"=== {stamp()} exit {rc}\n")
    if rc != RESULT_OK:
        why = last_reason(log, before)
        print(f"{e.name} exit {rc}" + (f": {why}" if why else "") + f" (log: {log})", flush=True)
    return rc


def main(argv: list[str] | None = None) -> int:
    """``run <name>`` is what a task executes; ``install|remove <name>`` and ``list`` are
    entry points that act only on registry names (the Windows ``.ps1`` callers were removed, #1225).
    ``names`` prints the registry names one per line and never asks the scheduler, so a script that
    freezes or lists the tasks reads them from here instead of keeping its own copy (#164)."""
    args = list(sys.argv[1:] if argv is None else argv)
    try:
        if len(args) == 2 and args[0] == "run":
            return run_task(args[1])
        if len(args) == 2 and args[0] in ("install", "remove"):
            row = apply(args[1], args[0])
            print(f"{args[0]}: {row['name']} -> {row['state']}")
            return 0
        if args == ["names"]:
            print("\n".join(e.name for e in REGISTRY))
            return 0
        if args == ["list"]:
            for r in live_state()["rows"]:
                print(f"{r['name']:<26} {r['state']:<14} {r['schedule']}")
            return 0
    except AutomationError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print("usage: python -m revenuechaser.core.automations "
          "run|install|remove <registry-name> | list | names", file=sys.stderr)
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
