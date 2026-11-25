"""``uw/fda_calendar``: Unusual Whales' FDA calendar, one call an hour (#807, slice N2 of #783).

``GET /market/fda-calendar``: rows of ``ticker``, ``drug``, ``status`` (NDA, BLA), ``catalyst`` (PDUFA Date, Advisory
Committee Meeting, ...), ``start_date`` and ``end_date``, plus ``indication``, ``description``, ``notes``,
``outcome``, ``outcome_brief``, ``source_link``, ``has_options`` and ``marketcap`` (the field names are UW's own,
``docs/openapi.yaml`` schema ``FDA Calendar``; its ``required`` five are ticker, drug, status, start_date and
end_date). The endpoint pages nothing: one call with ``limit`` (max 500) brings the list, so the sweep is one
request.

Like the economic calendar, the answer is a snapshot UW revises (an outcome filled in, a PDUFA date moved), so a day
is kept as the **newest** fetch of that New York day: each fetch replaces the day's partition whole.

**A target date is not always a day.** UW's own date formats are ``YYYY-Q[1-4]``, ``YYYY-H[1-2]``, ``YYYY-MID``,
``YYYY-LATE`` and ``YYYY-MM-DD``. The provider's text is kept as served in ``target_text`` **and** resolved to a day
in ``target_date`` with ``target_precision`` recording what the text really said (``day``, ``quarter``, ``half``,
``mid``, ``late``), so nothing reads a quarter as a day without being told (#807).

Raw: ``raw/uw/fda_calendar/<YYYY-MM-DD>/<HHMMSS>.json.gz`` (New York day, UTC time of the fetch): one file per fetch,
so the hourly cadence (``due.py``) is not stopped by the day's first file. Parquet:
``parquet/uw/fda_calendar/date=<YYYY-MM-DD>/part-0.parquet``. Serving: ``fda_event``, keyed
``(snapshot_date, target_date, ticker, drug)``.
"""
from __future__ import annotations

import logging
import re
import time
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

from ...core import calendar
from . import base, partitions
from . import dirty as dirty_set
from .uw_economic_calendar import TRANSPORT_RETRY_PAUSE_S, _transport_failure

logger = logging.getLogger(__name__)

NAME = "uw/fda_calendar"
TABLE = "fda_event"
ENDPOINT = "/market/fda-calendar"
#: UW clamps anything above 500; the whole forward calendar is well inside one page.
PAGE_LIMIT = 500
SCHEMA = [("snapshot_date", "DATE"), ("target_date", "DATE"), ("ticker", "TEXT"), ("drug", "TEXT"),
          ("target_text", "TEXT"), ("target_precision", "TEXT"), ("end_date", "DATE"), ("end_text", "TEXT"),
          # ``application_status``, not ``status``: ``rcdata.read`` stamps every row it hands back with a ``status``
          # of its own (the dataset's freshness), so a served column of that name never reaches a reader.
          ("catalyst", "TEXT"), ("application_status", "TEXT"), ("indication", "TEXT"), ("description", "TEXT"),
          ("notes", "TEXT"), ("outcome", "TEXT"), ("outcome_brief", "TEXT"), ("source_link", "TEXT"),
          ("has_options", "BOOLEAN"), ("marketcap", "DOUBLE"),
          ("source", "TEXT"), ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]
# Market 6 (#1433): ``source`` joined the key, because ``public/fda_calendar`` (``fda_calendar_sources.py``) stages
# the SEC's and the Federal Register's rows in this table's shape and this dataset builds the table from both folders.
KEY = ("snapshot_date", "target_date", "ticker", "drug", "source")
#: The Parquet folders the table is built from (``parquet/<folder>/fda_calendar``) and the ``source`` values each
#: one writes.
FOLDERS = {"uw": ("uw",), "public": ("sec", "federalregister")}
COMPARE = [c for c, _ in SCHEMA if c not in ("fetched_at", "run_id", "source_as_of")]

#: What a target date's text says, and the day it resolves to. A quarter, a half year, "MID" and "LATE" resolve to
#: the first day of the period they name, and ``target_precision`` says which period that was, so a reader can tell
#: "15 Jan 2027" from "some time in Q1 2027".
DAY = "day"
QUARTER = "quarter"
HALF = "half"
MID = "mid"
LATE = "late"
#: Mid-year is read as the start of July and late-year as the start of October (the quarter and half rules give the
#: same kind of answer: the first day of the span the text names).
_MID_MONTH, _LATE_MONTH = 7, 10

_DAY_RE = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_QUARTER_RE = re.compile(r"^(\d{4})-Q([1-4])$", re.I)
_HALF_RE = re.compile(r"^(\d{4})-H([1-2])$", re.I)
_MID_RE = re.compile(r"^(\d{4})-MID$", re.I)
_LATE_RE = re.compile(r"^(\d{4})-LATE$", re.I)


def day_dir(day: date) -> Path:
    return base.raw_root() / "uw" / "fda_calendar" / day.isoformat()


def partition_path(day: date) -> Path:
    return base.parquet_root() / "uw" / "fda_calendar" / f"date={day.isoformat()}" / "part-0.parquet"


def _text(value) -> str | None:
    s = None if value is None else str(value).strip()
    return s or None


def _number(value) -> float | None:
    """A served number (``marketcap`` comes as text) as a float; None when it is not one."""
    raw = _text(value)
    if raw is None:
        return None
    try:
        return float(raw.replace(",", ""))
    except ValueError:
        return None


def _bool(value) -> bool | None:
    if isinstance(value, bool):
        return value
    raw = _text(value)
    if raw is None:
        return None
    low = raw.lower()
    return True if low in ("true", "1", "yes") else (False if low in ("false", "0", "no") else None)


def target_day(value) -> tuple[date | None, str | None]:
    """UW's target-date text as ``(day, precision)``; ``(None, None)`` when the text is none of its formats.

    ``2027-01-15`` -> day precision ``day``; ``2027-Q2`` -> 1 Apr 2027, ``quarter``; ``2027-H2`` -> 1 Jul 2027,
    ``half``; ``2027-MID`` -> 1 Jul 2027, ``mid``; ``2027-LATE`` -> 1 Oct 2027, ``late``. A quarter is never written
    as if it were a day: the precision travels with it.
    """
    raw = _text(value)
    if raw is None:
        return None, None
    m = _DAY_RE.match(raw)                      # UW's own format is a plain date; a datetime text is read as its day
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3))), DAY
        except ValueError:
            return None, None
    m = _QUARTER_RE.match(raw)
    if m:
        return date(int(m.group(1)), 3 * (int(m.group(2)) - 1) + 1, 1), QUARTER
    m = _HALF_RE.match(raw)
    if m:
        return date(int(m.group(1)), 1 if m.group(2) == "1" else 7, 1), HALF
    m = _MID_RE.match(raw)
    if m:
        return date(int(m.group(1)), _MID_MONTH, 1), MID
    m = _LATE_RE.match(raw)
    if m:
        return date(int(m.group(1)), _LATE_MONTH, 1), LATE
    return None, None


class UWFdaCalendar:
    name = NAME
    kind = "market"
    providers = ("uw",)
    tables = (TABLE,)
    parquet_reads = ("public/fda_calendar",)
    cadence = "hourly"

    def default_as_of(self) -> date:
        return calendar.today_ny()          # the snapshot's day, not a session: the calendar changes on any day

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        ctx.check_cap("uw")
        params = {"limit": PAGE_LIMIT}
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
            raise base.SourceError(f"UW {ENDPOINT}: no rows")   # the FDA calendar is never empty
        now = time.time()
        raw = day_dir(as_of) / f"{datetime.fromtimestamp(now, timezone.utc):%H%M%S}.json.gz"
        return [base.write_raw_json(raw, {"request": {"endpoint": ENDPOINT, "params": params},
                                          "snapshot_date": as_of.isoformat(), "fetched_at": now,
                                          "run_id": ctx.run_id, "body": body})]

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        doc = base.read_raw_json(raw)
        day = date.fromisoformat(doc["snapshot_date"])
        body = doc["body"]
        items = [i for i in (body.get("data", []) if isinstance(body, dict) else body) if isinstance(i, dict)]
        rows, seen, unkeyed, repeats = [], set(), 0, 0
        for item in items:
            ticker, drug = _text(item.get("ticker")), _text(item.get("drug"))
            target, precision = target_day(item.get("start_date"))
            if target is None or ticker is None or drug is None:
                unkeyed += 1
                continue
            key = (target, ticker, drug)
            if key in seen:
                repeats += 1                # two catalysts of one drug on one day: the first row stands (#807's key)
                continue
            seen.add(key)
            end, _end_precision = target_day(item.get("end_date"))
            rows.append({"snapshot_date": day, "target_date": target, "ticker": ticker, "drug": drug,
                         "target_text": _text(item.get("start_date")), "target_precision": precision,
                         "end_date": end, "end_text": _text(item.get("end_date")),
                         "catalyst": _text(item.get("catalyst")),
                         "application_status": _text(item.get("status")),
                         "indication": _text(item.get("indication")),
                         "description": _text(item.get("description")), "notes": _text(item.get("notes")),
                         "outcome": _text(item.get("outcome")), "outcome_brief": _text(item.get("outcome_brief")),
                         "source_link": _text(item.get("source_link")),
                         "has_options": _bool(item.get("has_options")), "marketcap": _number(item.get("marketcap")),
                         "source": "uw", "source_as_of": day, "fetched_at": doc["fetched_at"],
                         "run_id": doc["run_id"]})
        if unkeyed:
            ctx.issue("unkeyed", day.isoformat(), f"{unkeyed} rows without a readable target date, ticker or drug")
        if repeats:
            ctx.issue("duplicate", day.isoformat(), f"{repeats} rows repeat a (target date, ticker, drug) key")
        if not rows:
            raise base.SourceError(f"UW {ENDPOINT} {day}: no usable row in {raw.name}")
        con = base.scratch_con()
        try:
            base.rows_table(con, "snap", SCHEMA, rows)
            # The day's newest fetch replaces it whole, so an event UW dropped is gone from that day too and the
            # day's count can fall: ``fda_event`` is in ``serving.SHRINKS_BY_CHOICE`` for the same reason
            # ``economic_event`` is. An empty table is still refused by the swap, and an empty answer from UW never
            # reaches here (``fetch`` raises on it).
            return [base.write_parquet(con, "SELECT * FROM snap ORDER BY target_date, ticker, drug",
                                       partition_path(day))]
        finally:
            con.close()

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        # Oldest first by file name (the fetch time), so a day's newest fetch is the one that stays.
        return [p for raw in sorted(raws, key=lambda r: (r.parent.name, r.name)) for p in self.to_parquet(ctx, raw)]

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        raise base.SourceError(f"{NAME} has no history: UW serves the calendar as it stands now")

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


def _source_dir(folder: str) -> Path:
    return base.parquet_root() / folder / "fda_calendar"


def _where(key: str) -> str:
    """The served rows of partition ``<folder>/<snapshot day>``: that folder's sources on that day."""
    folder, day = key.split("/")
    if folder not in FOLDERS:
        raise ValueError(f"not an fda_event folder: {folder!r}")
    sources = ", ".join(f"'{s}'" for s in FOLDERS[folder])
    return f"source IN ({sources}) AND snapshot_date = DATE '{date.fromisoformat(day).isoformat()}'"


DATASET = UWFdaCalendar()
