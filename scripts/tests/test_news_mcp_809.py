"""The News board's MCP server (#809, slice N3 of #783): ``python -m revenuechaser.scripts.news_mcp``.

Four tools over the dashboard's three read-only routes, JSON-RPC over stdio. The dashboard is mocked at the HTTP
boundary (``mock_httpx``), which is the only boundary this server has: it reads two URLs and calls no model.

The third tool is the point of the slice: the headlines inside a window around one event, each with how many
minutes from the event it was published. The fourth (#1234) reads back what the hourly EVREN reading already
wrote, so a model asking today can see what the tape said this morning without re-reading it.
"""
from __future__ import annotations

import io
import json

import pytest

from revenuechaser.scripts import news_mcp

EVENT_TS = 1_795_000_000.0
EVENTS = {"ok": True, "days": 7, "rows": [
    {"event_ts": EVENT_TS, "event": "Initial Jobless Claims", "type": "report", "importance": 2,
     "forecast": "232K", "prev": "227K", "hm": "14:30"},
    {"event_ts": EVENT_TS + 3 * 86400, "event": "IOVA Lifileucel: PDUFA Date", "type": "fda", "importance": 3,
     "ticker": "IOVA", "application_status": "NDA", "target_precision": "day"}]}
HEADLINES = {"ok": True, "rows": [
    {"headline_id": "a", "published_at": EVENT_TS + 600, "headline": "Claims come in light", "lane": "market"},
    {"headline_id": "b", "published_at": EVENT_TS - 1800, "headline": "Ahead of the claims print",
     "lane": "market"}]}


READING = {"ok": True, "hours": 24, "fields": ["tone", "driver"], "windows": [
    {"window_start": EVENT_TS - 3600, "window_end": EVENT_TS, "provider": "evren", "headlines": 42,
     "fields": {"tone": {"value": "risk_off", "quote": "Claims come in light", "headline_id": "a"}}}]}


class _Answer:
    """What ``httpx.get`` hands back: the body as JSON, nothing else this server reads."""

    def __init__(self, payload):
        self._payload, self.status_code = payload, 200

    def json(self):
        return self._payload


@pytest.fixture
def served(monkeypatch):
    """The dashboard's two routes, mocked at the HTTP boundary. Every call's URL and query is kept, so a test can
    read what the server actually asked for; ``mock_httpx`` matches on the URL alone and would not show that."""
    asked: list[str] = []

    def answer(url, *args, **kwargs):
        params = kwargs.get("params") or {}
        asked.append(str(url) + ("?" + "&".join(f"{k}={v}" for k, v in params.items()) if params else ""))
        if "/events" in str(url):
            return _Answer(EVENTS)
        return _Answer(READING if "/reading" in str(url) else HEADLINES)

    monkeypatch.setattr("httpx.get", answer)
    return asked


def _call(name: str, arguments: dict | None = None) -> dict:
    out = news_mcp.call_tool(name, arguments or {})
    assert out.get("isError") is not True, out["content"][0]["text"]
    return json.loads(out["content"][0]["text"])


def test_the_handshake_names_the_server_and_its_four_tools():
    got = news_mcp.handle({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}})
    assert got["result"]["serverInfo"]["name"] == "revenuechaser-news"
    assert got["result"]["capabilities"] == {"tools": {}}
    listed = news_mcp.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})["result"]["tools"]
    assert [t["name"] for t in listed] == ["recent_headlines", "coming_events", "headlines_around_event",
                                           "stored_reading"]
    assert all(t["description"] and t["inputSchema"]["type"] == "object" for t in listed)


def test_a_notification_is_never_answered_and_an_unknown_method_is_an_error():
    assert news_mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None
    err = news_mcp.handle({"jsonrpc": "2.0", "id": 3, "method": "nope"})["error"]
    assert err["code"] == -32601 and "nope" in err["message"]


def test_recent_headlines_asks_for_a_window_and_may_name_one_ticker(served):
    out = _call("recent_headlines", {"ticker": "nvda", "hours": 6, "limit": 5})
    assert out["ticker"] == "NVDA" and out["hours"] == 6 and out["count"] == 2
    assert out["headlines"][0]["headline"] == "Claims come in light"
    asked = served[0]
    assert "/api/news/headlines" in asked and "ticker=NVDA" in asked and "limit=5" in asked


def test_coming_events_passes_the_days_and_the_types(served):
    out = _call("coming_events", {"days": 30, "types": ["fda"]})
    assert out["days"] == 30 and out["count"] == 2
    assert "/api/news/events" in served[0] and "types=fda" in served[0] and "days=30" in served[0]
    assert _call("coming_events", {})["days"] == news_mcp.DEFAULT_DAYS


def test_the_join_reads_a_window_around_the_event_and_says_how_far_each_headline_is(served):
    out = _call("headlines_around_event", {"event_ts": EVENT_TS, "window_minutes": 60})
    assert out["event_ts"] == EVENT_TS and out["window_minutes"] == 60 and out["count"] == 2
    assert [h["minutes_from_event"] for h in out["headlines"]] == [10.0, -30.0]
    asked = served[0]
    assert f"from={EVENT_TS - 3600}" in asked and f"to={EVENT_TS + 3600}" in asked


@pytest.mark.parametrize("name, args, says", [
    ("headlines_around_event", {}, "event_ts is needed"),
    ("headlines_around_event", {"event_ts": "soon"}, "epoch second"),
    ("recent_headlines", {"hours": "many"}, "whole number"),
    ("no_such_tool", {}, "no such tool"),
    ("recent_headlines", {"nonsense": 1}, "nonsense"),
])
def test_a_bad_ask_is_the_tools_own_error_and_never_a_crash(served, name, args, says):
    out = news_mcp.call_tool(name, args)
    assert out["isError"] is True and says in out["content"][0]["text"]


def test_every_window_is_capped(served):
    assert _call("recent_headlines", {"hours": 10_000})["hours"] == news_mcp.MAX_HOURS
    assert _call("coming_events", {"days": 999})["days"] == news_mcp.MAX_DAYS
    out = _call("headlines_around_event", {"event_ts": EVENT_TS, "window_minutes": 99_999})
    assert out["window_minutes"] == news_mcp.MAX_WINDOW_MIN


def test_a_dashboard_that_is_not_running_is_the_tools_own_error(monkeypatch):
    import httpx

    def refuse(url, *args, **kwargs):
        raise httpx.ConnectError("connection refused")

    monkeypatch.setattr("httpx.get", refuse)
    out = news_mcp.call_tool("coming_events", {})
    assert out["isError"] is True and "dashboard did not answer" in out["content"][0]["text"]
    assert "python -m revenuechaser.app.dashboard" in out["content"][0]["text"]


def test_the_server_answers_one_message_a_line_and_survives_a_bad_one(served):
    lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize"}),
             "not json at all",
             json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
             json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                         "params": {"name": "coming_events", "arguments": {"days": 7}}})]
    out = io.StringIO()
    assert news_mcp.serve(io.StringIO("\n".join(lines) + "\n"), out) == 0
    answers = [json.loads(line) for line in out.getvalue().splitlines()]
    assert [a["id"] for a in answers] == [1, None, 2], "the notification is the one with no answer"
    assert answers[1]["error"]["code"] == -32700
    assert json.loads(answers[2]["result"]["content"][0]["text"])["count"] == 2


def test_the_stored_reading_tool_reads_the_hours_windows_with_their_sentences(served):
    out = _call("stored_reading", {"hours": 6})
    assert out["hours"] == 6 and out["count"] == 1 and out["fields"] == ["tone", "driver"]
    field = out["windows"][0]["fields"]["tone"]
    assert (field["value"], field["quote"], field["headline_id"]) == ("risk_off", "Claims come in light", "a")
    assert served == ["http://127.0.0.1:8000/api/news/reading?hours=6"]


def test_the_stored_reading_tool_clamps_its_window_and_needs_no_argument(served):
    assert _call("stored_reading")["hours"] == news_mcp.DEFAULT_READ_HOURS
    assert _call("stored_reading", {"hours": 10_000})["hours"] == news_mcp.MAX_READ_HOURS
    assert _call("stored_reading", {"hours": 0})["hours"] == 1

