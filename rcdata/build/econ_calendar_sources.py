"""The economic calendar without Unusual Whales (#1433 lane F, #1417 G-4): TradingView's calendar and the Fed's own.

``public/economic_calendar`` asks two keyless sources in one run and stages their rows in ``economic_event``'s own
shape; ``uw/economic_calendar`` builds the served table from UW's folder and this one, keyed with ``source``, so they
stand side by side while UW still answers, and ``rcdata.read`` prefers these rows for a snapshot day that has them.

- **TradingView** (``source = 'tradingview'``): ``GET economic-calendar.tradingview.com/events`` for the United States,
  the window UW was asked for (``DAYS_BACK`` / ``DAYS_AHEAD``). Every row is a release (``type = 'report'``). Measured
  23 Nov 2026 from homesrv: HTTP 200, 411 US rows for 16 Nov-5 Dec; 14 of UW's 17 events of 17-20 Nov had a row at the
  same time under another name ("Initial Jobless Claims" for UW's "Weekly Jobless Claims").
- **The Fed** (``source = 'fed'``): ``GET federalreserve.gov/json/calendar.json``, the Board's own calendar, for what
  TradingView does not carry: speeches and testimony (``fed-speaker``), the FOMC meeting, minutes and press conference
  (``fomc``) and the Beige Book (``report``). Its times are New York times. It lists the Board's own members only, so a
  regional bank president's speech has no source here (3 of UW's 17 events of 17-20 Nov).

**Both in one run, on purpose.** The News board retires every event its newest fetch no longer lists
(``module_news/calendar.py``), so two datasets fetched at two times would retire each other's rows every pass. One
run writes one raw file and one ``fetched_at`` for both, and a run in which either source fails keeps nothing.

A day is the newest fetch of that New York day, as UW's dataset keeps it; a snapshot is never backfilled.
Raw: ``raw/public/economic_calendar/<YYYY-MM-DD>/<HHMMSS>.json.gz``. Parquet:
``parquet/public/economic_calendar/date=<YYYY-MM-DD>/part-0.parquet``.
"""
from __future__ import annotations

import html
import json
import os
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import duckdb

from ...core import calendar
from . import base
from .uw_economic_calendar import DAYS_AHEAD, DAYS_BACK, SCHEMA, TABLE, event_ts

NAME = "public/economic_calendar"
SOURCES = ("tradingview", "fed")
NY = ZoneInfo("America/New_York")
TRADINGVIEW_BASE = os.getenv("RC_TRADINGVIEW_CALENDAR_BASE") or "https://economic-calendar.tradingview.com"
FED_BASE = os.getenv("RC_FED_BASE") or "https://www.federalreserve.gov"
#: The Board's event types as ``economic_event`` names them; every other type (statistical releases, conferences,
#: Board meetings) is not a market event and is left out.
FED_TYPES = {"Speeches": "fed-speaker", "Testimony": "fed-speaker", "FOMC": "fomc", "Beige": "report"}
_CLOCK = re.compile(r"(\d{1,2}):(\d{2})\s*([ap])\.?\s*m\.?", re.I)


def _text(value) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(value)))).strip()
    return s or None


def day_dir(day: date) -> Path:
    return base.raw_root() / "public" / "economic_calendar" / day.isoformat()


def partition_path(day: date) -> Path:
    return base.parquet_root() / "public" / "economic_calendar" / f"date={day.isoformat()}" / "part-0.parquet"


def tradingview_request(as_of: date) -> tuple[str, dict, dict]:
    # The endpoint answers only a request that names TradingView's own page as its origin (measured 23 Nov 2026).
    return (f"{TRADINGVIEW_BASE}/events",
            {"from": f"{as_of - timedelta(days=DAYS_BACK)}T00:00:00.000Z",
             "to": f"{as_of + timedelta(days=DAYS_AHEAD)}T23:59:59.000Z", "countries": "US"},
            {"Origin": "https://www.tradingview.com"})


def tradingview_rows(body) -> tuple[list[dict], int]:
    """TradingView's answer as ``economic_event`` fields, and the count of rows with no time or no title."""
    items = body.get("result") if isinstance(body, dict) else None
    out, unkeyed = [], 0
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("country") not in (None, "US"):
            continue
        ts, name = event_ts(item.get("date")), _text(item.get("title"))
        if ts is None or name is None:
            unkeyed += 1
            continue
        out.append({"event_ts": ts, "event": name, "type": "report", "event_time": _text(item.get("date")),
                    "forecast": _text(item.get("forecast")), "prev": _text(item.get("previous")),
                    "reported_period": _text(item.get("period")), "source": "tradingview"})
    return out, unkeyed


def fed_ts(month, days, clock) -> float | None:
    """The Fed's ``month`` (``2026-11``), ``days`` (``19``; the first day of ``8-9``) and New York ``time``
    (``9:25 a.m.``) as epoch seconds; None when any part is missing or unreadable."""
    m = re.fullmatch(r"(\d{4})-(\d{2})", str(month or "").strip())
    d = re.match(r"\s*(\d{1,2})", str(days or ""))
    t = _CLOCK.search(str(clock or ""))
    if not (m and d and t):
        return None
    hour = int(t.group(1)) % 12 + (12 if t.group(3).lower() == "p" else 0)
    try:
        return datetime(int(m.group(1)), int(m.group(2)), int(d.group(1)), hour, int(t.group(2)),
                        tzinfo=NY).timestamp()
    except ValueError:
        return None


def fed_rows(body) -> tuple[list[dict], int]:
    """The Fed calendar's market events as ``economic_event`` fields, and the count of rows with no time or title."""
    items = body.get("events") if isinstance(body, dict) else None
    out, unkeyed = [], 0
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict) or item.get("type") not in FED_TYPES:
            continue
        ts, name = fed_ts(item.get("month"), item.get("days"), item.get("time")), _text(item.get("title"))
        if ts is None or name is None:
            unkeyed += 1
            continue
        out.append({"event_ts": ts, "event": name, "type": FED_TYPES[item["type"]],
                    "event_time": datetime.fromtimestamp(ts, timezone.utc).isoformat(), "forecast": None,
                    "prev": None, "reported_period": _text(item.get("description")), "source": "fed"})
    return out, unkeyed


def _json(r) -> object:
    try:
        return json.loads(r.content.decode("utf-8-sig"))     # the Fed's file starts with a byte-order mark
    except ValueError as e:
        raise base.SourceError(f"{r.url}: not JSON ({e})") from e


class PublicEconomicCalendar:
    name = NAME
    kind = "market"
    providers = SOURCES
    tables: tuple[str, ...] = ()
    feeds = (TABLE,)                     # ``uw/economic_calendar`` builds the table from this dataset's Parquet
    cadence = "hourly"
    starts_by_hand = True                # a new dataset starts by hand (decision F4)
    backfill_needs_from = False

    def default_as_of(self) -> date:
        return calendar.today_ny()          # the snapshot's day, not a session: the calendar changes on any day

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        url, params, headers = tradingview_request(as_of)
        tv = _json(base.http_get(ctx, "tradingview", url, params=params, headers=headers))
        fed = _json(base.http_get(ctx, "fed", f"{FED_BASE}/json/calendar.json"))
        empty = [src for src, (rows, _) in (("tradingview", tradingview_rows(tv)), ("fed", fed_rows(fed))) if not rows]
        if empty:
            # Both or nothing (the module's note): a day missing one source would retire its rows on the News board.
            ctx.issue("source_empty", as_of.isoformat(), f"no usable row from {', '.join(empty)}")
            raise base.ProviderEmpty(f"{NAME}: no rows from {', '.join(empty)}")
        now = time.time()
        raw = day_dir(as_of) / f"{datetime.fromtimestamp(now, timezone.utc):%H%M%S}.json.gz"
        return [base.write_raw_json(raw, {"request": {"tradingview": {"url": url, "params": params},
                                                      "fed": {"url": f"{FED_BASE}/json/calendar.json"}},
                                          "snapshot_date": as_of.isoformat(), "fetched_at": now,
                                          "run_id": ctx.run_id, "tradingview": tv, "fed": fed})]

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        doc = base.read_raw_json(raw)
        day = date.fromisoformat(doc["snapshot_date"])
        tv, tv_unkeyed = tradingview_rows(doc["tradingview"])
        fed, fed_unkeyed = fed_rows(doc["fed"])
        if tv_unkeyed + fed_unkeyed:
            ctx.issue("unkeyed", day.isoformat(), f"{tv_unkeyed + fed_unkeyed} rows without a time or a name")
        # The Fed's file holds every year: only the window UW was asked for is kept, for both sources.
        low, high = day - timedelta(days=DAYS_BACK + 1), day + timedelta(days=DAYS_AHEAD + 1)
        rows, seen = [], set()
        for r in tv + fed:
            key = (r["event_ts"], r["event"], r["type"], r["source"])
            if key in seen or not low <= datetime.fromtimestamp(r["event_ts"], timezone.utc).date() <= high:
                continue
            seen.add(key)
            rows.append({"snapshot_date": day, **r, "source_as_of": day, "fetched_at": doc["fetched_at"],
                         "run_id": doc["run_id"]})
        if not rows:
            raise base.SourceError(f"{NAME} {day}: no row inside the window in {raw.name}")
        con = base.scratch_con()
        try:
            base.rows_table(con, "snap", SCHEMA, rows)
            return [base.write_parquet(con, "SELECT * FROM snap ORDER BY event_ts, event, type, source",
                                       partition_path(day))]
        finally:
            con.close()

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        # Oldest first by file name (the fetch time), so a day's newest fetch is the one that stays.
        return [p for raw in sorted(raws, key=lambda r: (r.parent.name, r.name)) for p in self.to_parquet(ctx, raw)]

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        raise base.SourceError(f"{NAME} has no history: a day's row is what the sources said on that day")

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        return {}                        # the table is ``uw/economic_calendar``'s to build

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        marks = ", ".join("?" for _ in SOURCES)
        rows = int(con.execute(f"SELECT count(*) FROM {TABLE} WHERE source IN ({marks})", list(SOURCES)).fetchone()[0])
        as_of = ctx.as_of or self.default_as_of()
        return {"dataset": NAME, "result": "changed" if rows else "unchanged",
                "source_as_of": as_of.isoformat(), "rows": rows, "added": 0, "removed": 0, "coverage": None}


DATASET = PublicEconomicCalendar()
