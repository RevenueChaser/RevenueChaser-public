"""The News board's read-only MCP server (#809, slice N3 of #783): ``python -m revenuechaser.scripts.news_mcp``.

avo, 12 Nov 2026: the news flow is not a screen, it is handed to an AI to interpret. This server is the handle.
It speaks MCP over stdio (JSON-RPC 2.0, one message a line) and offers four tools:

- ``recent_headlines`` — the stored headlines of the last hours, optionally of one name;
- ``coming_events`` — the calendar rows still to come, economic and FDA (#807);
- ``headlines_around_event`` — the join, and the point of the slice: the headlines published in a window around
  one event. A headline read next to the release it reacts to is worth more than two unrelated lists;
- ``stored_reading`` — what the hourly EVREN reading already wrote for the last hours (#1234): fixed-schema
  fields, each carrying the sentence it came from, so "what did it say this morning" has an answer.

It reads the dashboard's own read-only routes (``/api/news/headlines``, ``/api/news/events``), which read
``boards/news.duckdb`` and fetch nothing. **Nothing is written back and no model is called here**: the hourly
reading of #1234 is written by the dashboard job ``news_reading`` (``module_news/reading.py``), the one writer,
and this server only reads what it stored.

Stdlib and ``httpx`` only: no MCP SDK is installed in this tree, and the protocol here is three methods wide.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import datetime, timezone

import httpx

DASHBOARD = "http://127.0.0.1:8000"       # app.dashboard.main's port; read-only routes need no X-RC-Panel header
TIMEOUT_S = 30.0
PROTOCOL = "2024-11-05"
SERVER = {"name": "revenuechaser-news", "version": "1"}
#: How far either side of an event the join reads by default, and the widest it will read.
WINDOW_MIN, MAX_WINDOW_MIN = 120, 24 * 60
DEFAULT_HOURS, MAX_HOURS = 24, 31 * 24
DEFAULT_DAYS, MAX_DAYS = 7, 31
DEFAULT_LIMIT, MAX_LIMIT = 50, 200
DEFAULT_READ_HOURS, MAX_READ_HOURS = 24, 31 * 24

TOOLS = [
    {"name": "recent_headlines",
     "description": "The market and stock headlines the News board has stored, newest first. Optionally one "
                    "ticker's own. Reads stored rows only; it fetches nothing.",
     "inputSchema": {"type": "object", "properties": {
         "ticker": {"type": "string", "description": "A symbol such as NVDA. Left out: every name."},
         "hours": {"type": "integer", "description": f"How far back to read, 1 to {MAX_HOURS}. "
                                                     f"Default {DEFAULT_HOURS}."},
         "limit": {"type": "integer", "description": f"At most this many headlines, 1 to {MAX_LIMIT}. "
                                                     f"Default {DEFAULT_LIMIT}."}}}},
    {"name": "coming_events",
     "description": "The calendar rows still to come: US economic releases and FDA catalysts, oldest first, with "
                    "the time in Amsterdam, the importance (3 high, 2 medium, 1 low), forecast and previous "
                    "value. An FDA row carries its ticker, drug, catalyst, indication and application status, and "
                    "its target_precision says whether the day is a real day or a quarter.",
     "inputSchema": {"type": "object", "properties": {
         "days": {"type": "integer", "description": f"How many days ahead, 1 to {MAX_DAYS}. Default "
                                                    f"{DEFAULT_DAYS}."},
         "types": {"type": "array", "items": {"type": "string"},
                   "description": "Only these types, e.g. [\"fda\"] or [\"report\", \"fomc\"]. Left out: every "
                                  "type the board holds."}}}},
    {"name": "headlines_around_event",
     "description": "The headlines published around one calendar event: the join between the two lists above. "
                    "Give the event's epoch second (event_ts from coming_events) and how many minutes either "
                    "side to read.",
     "inputSchema": {"type": "object", "properties": {
         "event_ts": {"type": "number", "description": "The event's epoch second."},
         "window_minutes": {"type": "integer", "description": f"Minutes either side, 1 to {MAX_WINDOW_MIN}. "
                                                              f"Default {WINDOW_MIN}."},
         "ticker": {"type": "string", "description": "Only this name's headlines. Left out: every name."},
         "limit": {"type": "integer", "description": f"At most this many headlines, 1 to {MAX_LIMIT}. "
                                                     f"Default {DEFAULT_LIMIT}."}},
         "required": ["event_ts"]}},
    {"name": "stored_reading",
     "description": "What the hourly reading of the headline flow already wrote (#1234): one window an hour, "
                    "newest first, each with the same fixed fields (tone, driver, macro, rates, most_named, "
                    "surprise, watch). Every field carries the value, the sentence it came from and that "
                    "headline's id, so a reading can be checked against the tape. A field no headline supported "
                    "is absent. Reads stored rows only; it calls no model.",
     "inputSchema": {"type": "object", "properties": {
         "hours": {"type": "integer", "description": f"How far back to read, 1 to {MAX_READ_HOURS}. "
                                                     f"Default {DEFAULT_READ_HOURS}."}}}},
]


class ToolError(Exception):
    """What a tool says when the ask itself is wrong; the answer carries it as the tool's own error."""


def _clamp(value, low: int, high: int, default: int) -> int:
    if value is None:
        return default
    try:
        return max(low, min(int(value), high))
    except (TypeError, ValueError):
        raise ToolError(f"expected a whole number, got {value!r}") from None


def _get(path: str, params: dict) -> dict:
    """One read-only GET at the dashboard. A dashboard that is not running is the tool's own error, never a crash."""
    try:
        answer = httpx.get(f"{DASHBOARD}{path}", params=params, timeout=TIMEOUT_S)
    except httpx.HTTPError as exc:
        raise ToolError(f"the dashboard did not answer ({exc}); start it with "
                        f"python -m revenuechaser.app.dashboard") from None
    try:
        body = answer.json()
    except ValueError:
        raise ToolError(f"{path} answered {answer.status_code} and no JSON") from None
    if not body.get("ok"):
        raise ToolError(str(body.get("error") or f"{path} answered {answer.status_code}"))
    return body


def recent_headlines(ticker=None, hours=None, limit=None) -> dict:
    hours = _clamp(hours, 1, MAX_HOURS, DEFAULT_HOURS)
    limit = _clamp(limit, 1, MAX_LIMIT, DEFAULT_LIMIT)
    now = time.time()
    params = {"from": now - hours * 3600, "to": now, "limit": limit}
    if ticker:
        params["ticker"] = str(ticker).strip().upper()
    rows = _get("/api/news/headlines", params)["rows"]
    return {"hours": hours, "ticker": params.get("ticker"), "count": len(rows), "headlines": rows}


def coming_events(days=None, types=None) -> dict:
    days = _clamp(days, 1, MAX_DAYS, DEFAULT_DAYS)
    params: dict = {"days": days}
    if types:
        if isinstance(types, str):
            types = [types]
        params["types"] = ",".join(str(t).strip() for t in types if str(t or "").strip())
    rows = _get("/api/news/events", params)["rows"]
    return {"days": days, "count": len(rows), "events": rows}


def headlines_around_event(event_ts=None, window_minutes=None, ticker=None, limit=None) -> dict:
    if event_ts is None:
        raise ToolError("event_ts is needed: take it from coming_events")
    try:
        at = float(event_ts)
    except (TypeError, ValueError):
        raise ToolError(f"event_ts must be an epoch second, got {event_ts!r}") from None
    window = _clamp(window_minutes, 1, MAX_WINDOW_MIN, WINDOW_MIN)
    limit = _clamp(limit, 1, MAX_LIMIT, DEFAULT_LIMIT)
    params = {"from": at - window * 60, "to": at + window * 60, "limit": limit}
    if ticker:
        params["ticker"] = str(ticker).strip().upper()
    rows = _get("/api/news/headlines", params)["rows"]
    for r in rows:
        r["minutes_from_event"] = round((float(r["published_at"]) - at) / 60, 1)
    return {"event_ts": at, "event_utc": datetime.fromtimestamp(at, timezone.utc).isoformat(),
            "window_minutes": window, "ticker": params.get("ticker"), "count": len(rows), "headlines": rows}


def stored_reading(hours=None) -> dict:
    hours = _clamp(hours, 1, MAX_READ_HOURS, DEFAULT_READ_HOURS)
    body = _get("/api/news/reading", {"hours": hours})
    windows = body["windows"]
    return {"hours": hours, "fields": body.get("fields") or [], "count": len(windows), "windows": windows}


HANDLERS = {"recent_headlines": recent_headlines, "coming_events": coming_events,
            "headlines_around_event": headlines_around_event, "stored_reading": stored_reading}


def call_tool(name: str, arguments: dict) -> dict:
    """One tool call as MCP writes its result: the answer as JSON text, or the tool's own error."""
    handler = HANDLERS.get(name)
    if handler is None:
        return {"content": [{"type": "text", "text": f"no such tool: {name}"}], "isError": True}
    try:
        out = handler(**{k: v for k, v in (arguments or {}).items()})
    except ToolError as exc:
        return {"content": [{"type": "text", "text": str(exc)}], "isError": True}
    except TypeError as exc:                       # an argument the tool does not take
        return {"content": [{"type": "text", "text": f"{name}: {exc}"}], "isError": True}
    return {"content": [{"type": "text", "text": json.dumps(out, ensure_ascii=False, default=str)}]}


def handle(message: dict) -> dict | None:
    """One JSON-RPC message in, its answer out; ``None`` for a notification, which is never answered."""
    method, mid = message.get("method"), message.get("id")
    if mid is None:
        return None
    if method == "initialize":
        return {"jsonrpc": "2.0", "id": mid,
                "result": {"protocolVersion": PROTOCOL, "capabilities": {"tools": {}}, "serverInfo": SERVER}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = message.get("params") or {}
        return {"jsonrpc": "2.0", "id": mid,
                "result": call_tool(str(params.get("name") or ""), params.get("arguments") or {})}
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"method not found: {method}"}}


def serve(stdin=None, stdout=None) -> int:
    """Read one JSON message a line and answer it, until the input ends. A line that is not JSON is answered with
    a parse error and the server keeps going: one bad line never ends the session."""
    stdin, stdout = stdin or sys.stdin, stdout or sys.stdout
    for line in stdin:
        if not line.strip():
            continue
        try:
            message = json.loads(line)
        except ValueError:
            answer = {"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "parse error"}}
        else:
            answer = handle(message) if isinstance(message, dict) else {
                "jsonrpc": "2.0", "id": None, "error": {"code": -32600, "message": "invalid request"}}
        if answer is not None:
            stdout.write(json.dumps(answer, ensure_ascii=False, default=str) + "\n")
            stdout.flush()
    return 0


def main(argv: list[str] | None = None) -> int:
    return serve()


if __name__ == "__main__":
    raise SystemExit(main())
