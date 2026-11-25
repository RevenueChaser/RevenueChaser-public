"""``uw/economic_calendar``: Unusual Whales' economic calendar (this week and next), one call an hour (#643 F3).

``GET /market/economic-calendar``: rows of ``event``, ``type`` (fed-speaker, fomc or report), ``time`` (UTC text),
``forecast``, ``prev`` and ``reported_period``. The calendar is a snapshot that UW revises during the day (a forecast
filled in, a time moved), so a day is kept as the **newest** fetch of that New York day: each fetch replaces the
day's partition whole, and a revision the old nightly table lost (it kept the first write of a key) is kept here.

**The call names its window** (:data:`DAYS_BACK` / :data:`DAYS_AHEAD` as ``min_date`` / ``max_date``), and that is
not a tidying: the parameterless call is **forward-only**, so it answers nothing at all whenever UW's forward
window is empty. Measured 21 Nov 2026 08:35 UTC on our own key: the parameterless call returned **0 rows** while
``min_date=2026-11-17&max_date=2026-11-28`` returned 34 rows (18 distinct) for 17-20 Nov and none after -- UW's
forward calendar was genuinely empty, and the past days it had published were reachable the whole time and never
asked for. Two things follow. The dataset no longer goes blank on an empty forward window, and the days behind
today are stored, which is what a reaction join needs (#809 reads a headline next to the release it reacts to).
This provider ignores a parameter it does not support without an error (#746), so :meth:`to_parquet` **checks the
window on the rows it was given** rather than trusting that it was applied, and records an ``outside_window`` build
issue for a day that falls outside it; the 21 Nov measurement is what says it is honoured. The rows are still
**stored**, because a row outside the window is a correct calendar row and the window is robustness rather than a
correctness filter. The answer repeats rows across the window (16 of the 34 were repeats): the key's ``seen`` set
already drops them.

Raw: ``raw/uw/economic_calendar/<YYYY-MM-DD>/<HHMMSS>.json.gz`` (New York day, UTC time of the fetch): one file per
fetch, so the hourly cadence (``due.py``) is not stopped by the day's first file. Parquet:
``parquet/uw/economic_calendar/date=<YYYY-MM-DD>/part-0.parquet``. Serving: ``economic_event``, keyed
``(snapshot_date, event_ts, event, type)``; ``event_ts`` is UW's ``time`` as epoch seconds. Not named
``economic_calendar``: that is the old raw table ``needs/screen.py`` retires.
"""
from __future__ import annotations

import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from ...core import calendar
from . import base, partitions
from . import dirty as dirty_set

logger = logging.getLogger(__name__)

NAME = "uw/economic_calendar"
TABLE = "economic_event"
ENDPOINT = "/market/economic-calendar"
SCHEMA = [("snapshot_date", "DATE"), ("event_ts", "DOUBLE"), ("event", "TEXT"), ("type", "TEXT"),
          ("event_time", "TEXT"), ("forecast", "TEXT"), ("prev", "TEXT"), ("reported_period", "TEXT"),
          ("source", "TEXT"), ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]
# Market 6 (#1433): ``source`` joined the key, because ``public/economic_calendar`` (``econ_calendar_sources.py``)
# stages TradingView's and the Fed's rows in this table's shape and this dataset builds the table from both folders.
KEY = ("snapshot_date", "event_ts", "event", "type", "source")
#: The Parquet folders the table is built from (``parquet/<folder>/economic_calendar``) and the ``source`` values
#: each one writes.
FOLDERS = {"uw": ("uw",), "public": ("tradingview", "fed")}
COMPARE = [c for c, _ in SCHEMA if c not in ("fetched_at", "run_id", "source_as_of")]
# A transport failure (ConnectTimeout, ReadTimeout: no HTTP status) gets one more ladder after this pause. Measured on
# homesrv 10-11 Nov 2026: the run's first UW call failed at :05:08-:05:56 three times while option_list answered at
# :07:27 in the same run, so a glitch outlives the client's own ~46 s ladder but not a minute and a half more.
TRANSPORT_RETRY_PAUSE_S = 90.0
#: The window the call names, in days around the snapshot's New York day. Back: enough that the released days a
#: reaction join reads are stored, and short enough that one call still covers it. Ahead: UW's own forward window is
#: "this week and next", so 21 days asks for all of it and nothing is gained by asking for more.
DAYS_BACK = 7
DAYS_AHEAD = 21
#: A row's UTC day may fall one day outside the New York window at either edge, because the window is named in New
#: York days and ``time`` is UTC: a 00:30 UTC row belongs to the previous New York day.
WINDOW_SLACK_DAYS = 1


def day_dir(day: date) -> Path:
    return base.raw_root() / "uw" / "economic_calendar" / day.isoformat()


def partition_path(day: date) -> Path:
    return base.parquet_root() / "uw" / "economic_calendar" / f"date={day.isoformat()}" / "part-0.parquet"


def _text(value) -> str | None:
    s = None if value is None else str(value).strip()
    return s or None


def event_ts(value) -> float | None:
    """UW's UTC time text (``2026-10-16 12:30:00+00:00`` or ``...Z``) as epoch seconds; None when unreadable."""
    raw = _text(value)
    if raw is None:
        return None
    try:
        t = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (t if t.tzinfo else t.replace(tzinfo=timezone.utc)).timestamp()


def window_params(as_of: date) -> dict[str, str]:
    """``min_date`` / ``max_date`` around the snapshot's New York day, as UW's calendar takes them."""
    return {"min_date": (as_of - timedelta(days=DAYS_BACK)).isoformat(),
            "max_date": (as_of + timedelta(days=DAYS_AHEAD)).isoformat()}


def outside_window(days: list[date], as_of: date) -> list[date]:
    """The days of ``days`` that the window of ``as_of`` does not cover, with :data:`WINDOW_SLACK_DAYS` either side.

    **What this catches and what it cannot.** A provider that ignored ``min_date`` / ``max_date`` and answered its
    whole calendar is caught here, which is why the check exists at all: this provider drops a parameter it does not
    support without saying so (#746), so every filter we send is verified on the rows that come back. A provider that
    ignored them the *other* way, answering only its forward window, is **not** detectable from the rows -- that
    answer is a subset of the window we asked for, and it is also exactly what an empty past would look like. So a
    clean run here is evidence the window was not widened, never evidence it was applied.
    """
    low = as_of - timedelta(days=DAYS_BACK + WINDOW_SLACK_DAYS)
    high = as_of + timedelta(days=DAYS_AHEAD + WINDOW_SLACK_DAYS)
    return sorted({d for d in days if d < low or d > high})


class UWEconomicCalendar:
    name = NAME
    kind = "market"
    providers = ("uw",)
    tables = (TABLE,)
    parquet_reads = ("public/economic_calendar",)
    cadence = "hourly"

    def default_as_of(self) -> date:
        return calendar.today_ny()          # the snapshot's day, not a session: the calendar changes on any day

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        ctx.check_cap("uw")
        params = window_params(as_of)
        res = ctx.uw_client().get_result(ENDPOINT, params)
        if res.status != "ok" and _transport_failure(res.error):
            logger.warning("UW %s: %s, trying again in %.0f s", ENDPOINT, res.error.get("error"),
                           TRANSPORT_RETRY_PAUSE_S)
            ctx.sleep(TRANSPORT_RETRY_PAUSE_S)
            res = ctx.uw_client().get_result(ENDPOINT, params)
        if res.status != "ok":
            raise base.SourceError(f"UW {ENDPOINT}: {res.error}")
        body = res.data
        items = body.get("data", []) if isinstance(body, dict) else body
        if not isinstance(items, list) or not items:
            # Two weeks of calendar are never empty, so an empty answer is not stored. It is also not this pass's
            # failure (21 Nov 2026: UW answered 200 with no rows and the whole hourly pass exited 1): the dataset
            # is skipped, the issue stays open while the gap lasts, and the next pass asks again.
            ctx.issue("source_empty", as_of.isoformat(),
                      f"UW {ENDPOINT} answered 200 with no rows for {params['min_date']}..{params['max_date']}")
            raise base.ProviderEmpty(f"UW {ENDPOINT}: no rows")
        now = time.time()
        raw = day_dir(as_of) / f"{datetime.fromtimestamp(now, timezone.utc):%H%M%S}.json.gz"
        return [base.write_raw_json(raw, {"request": {"endpoint": ENDPOINT, "params": params},
                                          "snapshot_date": as_of.isoformat(),
                                          "fetched_at": now, "run_id": ctx.run_id, "body": body})]

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        doc = base.read_raw_json(raw)
        day = date.fromisoformat(doc["snapshot_date"])
        body = doc["body"]
        items = [i for i in (body.get("data", []) if isinstance(body, dict) else body) if isinstance(i, dict)]
        rows, seen, unkeyed = [], set(), 0
        for item in items:
            ts, event, kind = event_ts(item.get("time")), _text(item.get("event")), _text(item.get("type"))
            if ts is None or event is None or kind is None:
                unkeyed += 1
                continue
            if (ts, event, kind) in seen:
                continue                    # UW lists one event twice: the first row stands
            seen.add((ts, event, kind))
            rows.append({"snapshot_date": day, "event_ts": ts, "event": event, "type": kind,
                         "event_time": _text(item.get("time")), "forecast": _text(item.get("forecast")),
                         "prev": _text(item.get("prev")), "reported_period": _text(item.get("reported_period")),
                         "source": "uw", "source_as_of": day, "fetched_at": doc["fetched_at"],
                         "run_id": doc["run_id"]})
        if unkeyed:
            ctx.issue("unkeyed", day.isoformat(), f"{unkeyed} rows without a time, an event or a type")
        stray = outside_window([datetime.fromtimestamp(r["event_ts"], timezone.utc).date() for r in rows], day)
        if stray:
            # Recorded, not raised, and that is a measured correction rather than a softening. A row outside the
            # window is still a correct calendar row -- the window is robustness, not a correctness filter -- so
            # failing the dataset over it would drop good data to punish a provider's parameter habit. An open
            # ``build_issues`` row is what says the filter was not honoured, and it stays open while it lasts.
            # The first version did raise, and CI said why that was wrong: ``test_rate_event_overlap_e5d`` keys its
            # stored sweep at 2026-01-15 and puts its events in October, because for a *snapshot* the sweep day is
            # a key and not a claim about when the events are. A builder that refuses that shape refuses the truth
            # about itself.
            window = window_params(day)
            ctx.issue("outside_window", day.isoformat(),
                      f"{len(stray)} day(s) outside {window['min_date']}..{window['max_date']}: "
                      f"{', '.join(d.isoformat() for d in stray[:5])}")
        if not rows:
            raise base.SourceError(f"UW {ENDPOINT} {day}: no usable row in {raw.name}")
        con = base.scratch_con()
        try:
            base.rows_table(con, "snap", SCHEMA, rows)
            # The day's newest fetch replaces it whole: an event UW dropped is gone from that day too.
            # A day's newest fetch holds fewer rows than its first one whenever an event has rolled out of UW's
            # forward window, so the swap's 1% shrink guard (serving.MAX_SHRINK) refused the whole ``market``
            # build every hour on 14 Nov 2026 (114 rows against 126 live). ``economic_event`` is in
            # serving.SHRINKS_BY_CHOICE since: the source chooses the day's list, and a count that cannot only
            # grow is not evidence of a partial Parquet tree. An empty table is still refused by the swap, and an
            # empty answer from UW never reaches here (``fetch`` raises on it).
            return [base.write_parquet(con, "SELECT * FROM snap ORDER BY event_ts, event, type", partition_path(day))]
        finally:
            con.close()

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        # Oldest first by file name (the fetch time), so a day's newest fetch is the one that stays.
        return [p for raw in sorted(raws, key=lambda r: (r.parent.name, r.name)) for p in self.to_parquet(ctx, raw)]

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        # Not "UW serves only this week and next", which the 21 Nov 2026 measurement disproved: a named window
        # does answer for days behind today. A **snapshot** still cannot be backfilled, which is the real reason.
        # What UW says about 17 Nov today is today's view of it -- the forecast as finally revised -- and storing
        # that under 17 Nov would claim we knew it then. The window above only widens today's snapshot.
        raise base.SourceError(f"{NAME} has no history: a day's row is what UW said on that day, and only "
                               f"a fetch made that day can say it")

    def dirty(self, ctx: base.RunContext):
        if getattr(ctx, "changed", None) is None:
            return dirty_set.ALL
        keys = {f"{folder}/{day}" for folder in FOLDERS
                for day in dirty_set.keys_of(ctx.changed, _source_dir(folder), "date")}
        return dirty_set.Dirty(keys=frozenset(keys)) if keys else dirty_set.CLEAN

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        parts = {f"{folder}/{p.parent.name.split('=', 1)[1]}": p
                 for folder in FOLDERS for p in _source_dir(folder).glob("date=*/part-0.parquet")}
        return partitions.load(ctx, con, NAME, TABLE, SCHEMA, KEY, parts, _where)

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        added, removed = partitions.compare(ctx, con, self.kind, NAME, TABLE, COMPARE, _where)
        rows = int(con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0])
        as_of = ctx.as_of or self.default_as_of()
        return {"dataset": NAME, "result": "changed" if added or removed else "unchanged",
                "source_as_of": as_of.isoformat(), "rows": rows, "added": added, "removed": removed,
                "coverage": None}


def _transport_failure(error: dict | None) -> bool:
    """True for a failure with no HTTP answer (timeout, refused connection); never for an HTTP error or an open
    breaker, which a second ladder would not change."""
    return bool(error) and error.get("status") is None and error.get("error") != "breaker_open"


def _source_dir(folder: str) -> Path:
    return base.parquet_root() / folder / "economic_calendar"


def _where(key: str) -> str:
    """The served rows of partition ``<folder>/<snapshot day>``: that folder's sources on that day."""
    folder, day = key.split("/")
    if folder not in FOLDERS:
        raise ValueError(f"not an economic_event folder: {folder!r}")
    sources = ", ".join(f"'{s}'" for s in FOLDERS[folder])
    return f"source IN ({sources}) AND snapshot_date = DATE '{date.fromisoformat(day).isoformat()}'"


DATASET = UWEconomicCalendar()
