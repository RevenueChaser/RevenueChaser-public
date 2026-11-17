"""avo 17 Nov 2026 (choice a): each board Fetches by itself after the nightly prices build, timer switched on per board.

The task asks nothing until the prices store holds SPY's complete bar of the latest complete session (the freeze's own
anchor), then queues the board's Fetch on the dashboard, the one writer, and waits.
"""
from __future__ import annotations

import json

import pytest

from RevenueChaser.core import automations
from RevenueChaser.scripts import board_fetch as cli


class _Resp:
    def __init__(self, status_code, payload):
        self.status_code, self._payload = status_code, payload

    def json(self):
        return self._payload


@pytest.fixture
def seams(monkeypatch):
    """The dashboard at the HTTP boundary, and a prices store that is ready unless a test says otherwise."""
    seen: dict = {"posts": [], "job": {"status": "done", "notes": ["Froze 3 Swing rows for 2026-11-16."]}}
    monkeypatch.setattr(cli, "_POLL_S", 0)
    monkeypatch.setattr(cli.ledger, "d01_has_session", lambda session, ticker: ticker == "SPY")

    def fake_post(url, data=None, headers=None, timeout=None):
        seen["posts"].append((url, headers))
        return _Resp(202, {"ok": True, "job_id": "j1"})

    def fake_get(url, timeout=None):
        assert url.endswith("/api/job/j1")
        return _Resp(200, {"ok": True, "job": seen["job"]})

    monkeypatch.setattr(cli.httpx, "post", fake_post)
    monkeypatch.setattr(cli.httpx, "get", fake_get)
    return seen


def _line(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_a_ready_store_queues_the_board_fetch_and_reports_the_freeze(seams, capsys):
    assert cli.main(["swing"]) == 0
    assert seams["posts"] == [("http://127.0.0.1:8000/run/swing", {"X-RC-Panel": "cli"})]
    line = _line(capsys)
    assert (line["status"], line["board"], line["notes"]) == ("done", "swing", ["Froze 3 Swing rows for 2026-11-16."])


def test_without_the_session_s_spy_bar_the_task_asks_for_nothing(seams, monkeypatch, capsys):
    monkeypatch.setattr(cli.ledger, "d01_has_session", lambda session, ticker: False)
    assert cli.main(["ag"]) == cli.EXIT_NOT_READY
    assert seams["posts"] == [] and _line(capsys)["status"] == "not_ready"


def test_a_failed_job_exits_1(seams, capsys):
    seams["job"] = {"status": "error", "error": "boom"}
    assert cli.main(["fundamentals"]) == 1 and _line(capsys)["message"] == "boom"


def test_one_registry_row_and_unit_per_board_each_running_its_own_route():
    for board, route in cli.ROUTES.items():
        (e,) = [e for e in automations.REGISTRY if e.args == ("-m", "RevenueChaser.scripts.board_fetch", board)]
        assert e.unit == f"life-rc-fetch-{board}" and route in e.description and not e.after
