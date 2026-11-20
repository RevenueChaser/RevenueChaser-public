"""The incremental calendar build: ``market.economic_event`` and ``market.fda_event`` -> ``news.news_events`` and
``news.news_highlight``.

Plan 2026-11-09 §5 and the incremental rule (DECISIONS S16, migration plan §10):

- Only the rows fetched after the last build (``news_meta`` key ``calendar_mark``) are read.
- Each event key ``(event_ts, event, type)`` is upserted: its first sighting is kept, its last sighting, forecast and
  previous value move forward.
- An event the newest fetch no longer lists, inside the time span that fetch covers, is marked ``retired_at``; it is
  never deleted. A fetch with no rows (a failed or empty sweep) retires nothing.
- The highlight of an Amsterdam day is its most important live event; on a tie a release beats a Fed speech, then
  the earliest wins.

The FDA lane (#807) is the same pass over ``market.fda_event``: one ``news_events`` row a catalyst, ``type``
``fda``, its own mark (``fda_mark``) and the same upsert-and-retire rule. A catalyst's day is UW's target date at
midnight Amsterdam; the day's real precision travels in ``target_precision``, so nothing reads a quarter as a time.
An FDA row is never a day's highlight: the highlight is the economic calendar's (plan §5).

No network: the builder's hourly ``uw/economic_calendar`` and ``uw/fda_calendar`` serve the rows (avo, 11 Nov
2026: "Raw tamamen kalkmalı"; the raw ``economic_calendar`` table and its D37 sweep are retired).
"""
from __future__ import annotations

import re
import time
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from RevenueChaser.core import econ_importance, rawstore
from RevenueChaser.rcdata import read as market_read

AMS = ZoneInfo("Europe/Amsterdam")
MARK_KEY = "calendar_mark"
FDA_MARK_KEY = "fda_mark"
#: The ``type`` of an FDA row in ``news_events`` (#807); the economic rows keep UW's own report/fomc/fed-speaker.
FDA_TYPE = "fda"
EVENTS, HIGHLIGHT, META = "news_events", "news_highlight", "news_meta"
_EVENT_COLS = ("event_ts", "event", "type", "importance", "forecast", "prev", "reported_period", "first_seen",
               "last_seen", "retired_at", "run_id", "run_at")
_FDA_COLS = _EVENT_COLS + ("ticker", "drug", "catalyst", "target_text", "target_precision", "indication", "status",
                           "outcome", "url")


def local_day(ts: float) -> date:
    return datetime.fromtimestamp(float(ts), timezone.utc).astimezone(AMS).date()


def _mark(key: str = MARK_KEY) -> float:
    rows = rawstore.query(f"SELECT value FROM {META} WHERE key = ?", [key], db="news")
    try:
        return float(rows[0]["value"]) if rows else 0.0
    except (TypeError, ValueError):
        return 0.0


def _new_raw(mark: float) -> list[dict]:
    return market_read.economic_events(fetched_after=mark)


def _stored(keys: list[tuple]) -> dict[tuple, dict]:
    if not keys:
        return {}
    lo, hi = min(k[0] for k in keys), max(k[0] for k in keys)
    rows = rawstore.query(f"SELECT * FROM {EVENTS} WHERE event_ts BETWEEN ? AND ?", [lo, hi], db="news")
    return {(r["event_ts"], r["event"], r["type"]): r for r in rows}


# ── the FDA lane (#807) ───────────────────────────────────────────────────────────────────────────────────────────

def day_start(day) -> float:
    """Midnight Amsterdam of ``day`` as epoch seconds: the ``event_ts`` of an FDA catalyst, which has a date and no
    time of its own."""
    d = day if isinstance(day, date) else date.fromisoformat(str(day)[:10])
    return datetime(d.year, d.month, d.day, tzinfo=AMS).timestamp()


def fda_event_name(row: dict) -> str:
    """The ``event`` text of an FDA row: ``IOVA Lifileucel: PDUFA Date``. The company and the drug stay in their own
    columns too; this is the name the board shows and the key it is upserted by."""
    head = " ".join(str(x) for x in (row.get("ticker"), row.get("drug")) if x)
    tail = row.get("catalyst") or row.get("application_status")
    return f"{head}: {tail}" if tail else head


def _fda_rows(mark: float) -> list[dict]:
    return market_read.fda_events(fetched_after=mark)


def _fda_pass(now: float, run_id: str) -> dict:
    """One incremental pass over ``market.fda_event``, the same rule as the economic one: upsert by
    ``(event_ts, event, 'fda')``, retire inside the newest fetch's span, never delete."""
    mark = _mark(FDA_MARK_KEY)
    raw = _fda_rows(mark)
    if not raw:
        return {"fda_read": 0, "fda_upserted": 0, "fda_retired": 0}
    newest_fetch = max(float(r["fetched_at"]) for r in raw)
    newest_keys = {(day_start(r["target_date"]), fda_event_name(r), FDA_TYPE)
                   for r in raw if float(r["fetched_at"]) == newest_fetch}
    seen: dict[tuple, dict] = {}
    for r in raw:                                   # oldest first, so the latest sighting of a key wins
        seen[(day_start(r["target_date"]), fda_event_name(r), FDA_TYPE)] = r
    stored = _stored(list(seen))
    rows = []
    for key, r in seen.items():
        old = stored.get(key) or {}
        rows.append({
            "event_ts": key[0], "event": key[1], "type": FDA_TYPE,
            "importance": econ_importance.fda_importance(r.get("catalyst"), r.get("application_status")),
            "forecast": None, "prev": None, "reported_period": None,
            "first_seen": old.get("first_seen") or float(r["fetched_at"]),
            "last_seen": float(r["fetched_at"]), "retired_at": None, "run_id": run_id, "run_at": now,
            "ticker": r.get("ticker"), "drug": r.get("drug"), "catalyst": r.get("catalyst"),
            "target_text": r.get("target_text"), "target_precision": r.get("target_precision"),
            "indication": r.get("indication") or r.get("description"),
            # ``application_status``, never ``status``: ``rcdata.read`` stamps every row it hands back
            # with a ``status`` of its own (the dataset's freshness word), so reading that name here
            # would store "changed" in the column the board shows (#807).
            "status": r.get("application_status"),
            "outcome": r.get("outcome") or r.get("outcome_brief"), "url": r.get("source_link"),
        })
    lo, hi = min(k[0] for k in newest_keys), max(k[0] for k in newest_keys)
    retired = 0
    for row in rows:
        if lo <= row["event_ts"] <= hi and (row["event_ts"], row["event"], FDA_TYPE) not in newest_keys:
            row["retired_at"] = now
            retired += 1
    live = rawstore.query(f"SELECT * FROM {EVENTS} WHERE event_ts BETWEEN ? AND ? AND retired_at IS NULL "
                          f"AND type = ?", [lo, hi, FDA_TYPE], db="news")
    for r in live:
        key = (r["event_ts"], r["event"], r["type"])
        if key not in seen:
            rows.append({**{c: r.get(c) for c in _FDA_COLS}, "retired_at": now, "run_id": run_id, "run_at": now})
            retired += 1
    rawstore.write_rows(EVENTS, rows)
    rawstore.write_rows(META, [{"key": FDA_MARK_KEY, "value": repr(newest_fetch), "run_at": now}])
    return {"fda_read": len(raw), "fda_upserted": len(rows) - retired, "fda_retired": retired}


def build(now: float | None = None, run_id: str | None = None) -> dict:
    """One incremental pass over both lanes. Returns counts: ``read``, ``upserted``, ``retired``, ``highlights``, and
    the FDA lane's own ``fda_read``, ``fda_upserted``, ``fda_retired`` (#807)."""
    now = time.time() if now is None else now
    run_id = run_id or f"news-{int(now)}"
    mark = _mark()
    raw = _new_raw(mark)
    if not raw:
        fda = _fda_pass(now, run_id)
        hl = _highlights({local_day(now)}, now, run_id)
        return {"read": 0, "upserted": 0, "retired": 0, "highlights": hl, **fda}

    newest_fetch = max(float(r["fetched_at"]) for r in raw)
    newest = [r for r in raw if float(r["fetched_at"]) == newest_fetch]
    seen: dict[tuple, dict] = {}
    for r in raw:                                   # oldest first, so the latest sighting of a key wins
        key = (float(r["event_ts"]), r["event"], r["type"])
        seen[key] = r
    stored = _stored(list(seen))
    rows = []
    for key, r in seen.items():
        old = stored.get(key) or {}
        rows.append({
            "event_ts": key[0], "event": key[1], "type": key[2],
            "importance": econ_importance.importance(key[1], key[2]),
            "forecast": r.get("forecast"), "prev": r.get("prev"), "reported_period": r.get("reported_period"),
            "first_seen": old.get("first_seen") or float(r["fetched_at"]),
            "last_seen": float(r["fetched_at"]), "retired_at": None, "run_id": run_id, "run_at": now,
        })

    # Retire: inside the newest fetch's span, every key that fetch no longer lists — a live stored one, or one seen only
    # in an older fetch of this batch. It keeps its row with ``retired_at`` set; nothing is deleted.
    newest_keys = {(float(r["event_ts"]), r["event"], r["type"]) for r in newest}
    lo, hi = min(k[0] for k in newest_keys), max(k[0] for k in newest_keys)
    retired = 0
    for row in rows:
        if lo <= row["event_ts"] <= hi and (row["event_ts"], row["event"], row["type"]) not in newest_keys:
            row["retired_at"] = now
            retired += 1
    live = rawstore.query(f"SELECT * FROM {EVENTS} WHERE event_ts BETWEEN ? AND ? AND retired_at IS NULL "
                          f"AND type <> ?", [lo, hi, FDA_TYPE], db="news")
    for r in live:
        key = (r["event_ts"], r["event"], r["type"])
        if key not in seen:
            rows.append({**{c: r.get(c) for c in _EVENT_COLS}, "retired_at": now, "run_id": run_id, "run_at": now})
            retired += 1

    rawstore.write_rows(EVENTS, rows)
    rawstore.write_rows(META, [{"key": MARK_KEY, "value": repr(newest_fetch), "run_at": now}])
    fda = _fda_pass(now, run_id)
    days = {local_day(k[0]) for k in seen} | {local_day(now)}
    hl = _highlights(days, now, run_id)
    return {"read": len(raw), "upserted": len(rows) - retired, "retired": retired, "highlights": hl, **fda}


def _highlights(days: set[date], now: float, run_id: str) -> int:
    """Store the highlight of each Amsterdam day in ``days`` with live events: most important, a release before a Fed
    speech, then earliest. Returns the count."""
    if not days:
        return 0
    lo = min(days)
    start = datetime(lo.year, lo.month, lo.day, tzinfo=AMS).timestamp()
    live = rawstore.query(f"SELECT * FROM {EVENTS} WHERE event_ts >= ? AND retired_at IS NULL AND type <> ? "
                          f"ORDER BY event_ts", [start, FDA_TYPE], db="news")   # the highlight is economic (#807)
    by_day: dict[date, list[dict]] = {}
    for r in live:
        d = local_day(r["event_ts"])
        if d in days:
            by_day.setdefault(d, []).append(r)
    out = []
    for d, events in by_day.items():
        top = min(events, key=lambda e: (-(e.get("importance") or 1), str(e.get("type")).lower() == "fed-speaker",
                                         e["event_ts"]))
        out.append({"session_date": d.isoformat(), "event_ts": top["event_ts"], "event": top["event"],
                    "type": top["type"], "importance": top.get("importance"), "forecast": top.get("forecast"),
                    "prev": top.get("prev"), "text": explain(top), "text_source": "template",
                    "run_id": run_id, "run_at": now})
    rawstore.write_rows(HIGHLIGHT, out)
    return len(out)


# ── the highlight's text (plan decision B: a template, no model call) ────────────────────────────────────────────
_MEANS = (
    (("core", "cpi"), "Measures the change in consumer prices excluding food and energy; one of the inflation "
                      "readings the Fed watches most closely."),
    (("cpi",), "Measures the change in consumer prices; the release that moves rate expectations most."),
    (("pce",), "The inflation measure the Fed targets: the personal consumption expenditures price index."),
    (("ppi",), "Measures the change in producer prices; read as a leading indicator of consumer inflation."),
    (("nonfarm",), "The monthly change in non-farm payrolls; the most important gauge of the labour market."),
    (("employment", "report"), "The monthly employment report: new jobs, the unemployment rate and wages."),
    (("employment", "situation"), "The monthly employment report: new jobs, the unemployment rate and wages."),
    (("jobless", "claims"), "Weekly initial jobless claims; an early read on sudden shifts in the labour market."),
    (("jolts",), "Job openings; shows how strong demand for labour is."),
    (("gdp",), "The economy's quarterly growth rate."),
    (("retail", "sales"), "Retail sales; the monthly pulse of consumer spending."),
    (("ism",), "The purchasing managers' survey; above 50 means expansion."),
    (("inflation", "expectations"), "Households' forward-looking inflation expectations; the Fed watches whether "
                                    "expectations stay anchored."),
    (("consumer", "sentiment"), "The consumer confidence survey; an early signal on the willingness to spend."),
    (("housing", "starts"), "New housing starts; a gauge of the rate-sensitive housing market."),
    (("fomc",), "The Fed's rate decision; it can set the direction of every market."),
    (("rate", "decision"), "The Fed's rate decision; it can set the direction of every market."),
)


_NUM = re.compile(r"^(-?)(\d+(?:\.\d+)?)(%|[KMBT])?$")


def served_value(value) -> str | None:
    """A served value as the board writes it: ``3.9%`` stays ``3.9%``, ``1.25M`` stays ``1.25M`` (avo, 19 Nov 2026:
    the boards are English, so the Turkish ``%3,9`` writing is gone). Anything else is passed through as served."""
    if value is None:
        return None
    text = str(value).strip()
    m = _NUM.match(text)
    if not m:
        return text
    sign, num, unit = m.group(1), m.group(2), m.group(3) or ""
    return f"{sign}{num}{unit}"


def explain(event: dict) -> str:
    """Two short sentences: what the release measures, then its previous value and forecast when known."""
    words = econ_importance._words(event.get("event"))
    kind = str(event.get("type") or "").lower()
    means = next((text for keys, text in _MEANS if all(f" {k} " in words for k in keys)), None)
    if means is None and kind == "fed-speaker":
        means = "A speech by a Fed official; watched for hints about the path of rates."
    if means is None:
        means = "Today's highlight on the US economic calendar."
    prev, fc = served_value(event.get("prev")), served_value(event.get("forecast"))
    tail = []
    if prev:
        tail.append(f"Previous value {prev}")
    if fc:
        tail.append(f"forecast {fc}")
    elif prev:
        tail.append("no forecast published")
    return means + (" " + ", ".join(tail) + "." if tail else "")
