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
    seen: dict = {"posts": [], "idle": [{"idle": True, "reasons": []}], "job": {"status": "done", "notes": ["Froze 3 Swing rows for 2026-11-16."]}}
    monkeypatch.setattr(cli, "_POLL_S", 0)
    monkeypatch.setattr(cli.ledger, "d01_has_session", lambda session, ticker: ticker == "SPY")

    def fake_post(url, data=None, headers=None, timeout=None):
        seen["posts"].append((url, headers))
        seen["form"] = data
        return _Resp(202, {"ok": True, "job_id": "j1"})

    def fake_get(url, timeout=None):
        if url.endswith("/api/idle"):
            return _Resp(200, seen["idle"].pop(0) if len(seen["idle"]) > 1 else seen["idle"][0])
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
    """One row per board, each naming the dashboard route it posts, and none of them chained."""
    for board, route in cli.ROUTES.items():
        (e,) = [e for e in automations.REGISTRY if e.args == ("-m", "RevenueChaser.scripts.board_fetch", board)]
        assert f"/run/{route}" in e.description and not e.after
        # Relatedness profiling kept the unit its installed timer already had (#1255); the rest are life-rc-fetch-*.
        assert automations.system_unit(e) == ("life-rc-relatedness" if board == "relatedness"
                                             else f"life-rc-fetch-{board}")


def test_the_fetch_waits_while_the_builder_holds_its_lock(seams, capsys):
    """17 Nov 2026: the builder runs hourly, so the task waits on ``/api/idle`` before it asks for anything."""
    seams["idle"] = [{"idle": False, "reasons": ["job lock rcdata_build held by pid 7"]}, {"idle": True, "reasons": []}]
    assert cli.main(["comovement"]) == 0
    assert len(seams["posts"]) == 1 and seams["idle"] == [{"idle": True, "reasons": []}]


def test_a_store_still_busy_at_the_deadline_asks_for_nothing(seams, monkeypatch, capsys):
    monkeypatch.setattr(cli, "_WAIT_S", -1)
    seams["idle"] = [{"idle": False, "reasons": ["job lock rcdata_build held by pid 7"]}]
    assert cli.main(["comovement"]) == cli.EXIT_NOT_READY
    line = _line(capsys)
    assert seams["posts"] == [] and line["status"] == "not_ready" and "rcdata_build" in line["reason"]


@pytest.mark.parametrize("board", ["rotation", "earnings"])
def test_sector_rotation_and_earnings_radar_fetch_on_their_own_routes(seams, capsys, board):
    """avo 18 Nov 2026: the two boards that only had a button get the same nightly task, on the dashboard's routes."""
    assert cli.main([board]) == 0
    assert seams["posts"] == [(f"http://127.0.0.1:8000/run/{board}", {"X-RC-Panel": "cli"})]


def test_earnings_radar_runs_on_weekdays_only_after_sector_rotation():
    by = {e.name: e for e in automations.REGISTRY}
    rot, er = by["RC-Fetch-SectorRotation"], by["RC-Fetch-EarningsRadar"]
    assert er.days == automations._WEEKDAYS and not rot.days and rot.time < er.time


# ── #1255: the weekly Relatedness profiling run ──────────────────────────────

def test_the_relatedness_run_waits_for_the_store_rather_than_opening_it(seams, capsys):
    """The run that died on StoreLockedError now waits on /api/idle and then asks the dashboard, the one writer."""
    seams["idle"] = [{"idle": False, "reasons": ["another store process: pid 834460"]}, {"idle": True, "reasons": []}]
    assert cli.main(["relatedness"]) == 0
    assert seams["posts"] == [("http://127.0.0.1:8000/run/module_relatedness", {"X-RC-Panel": "cli"})]


def test_it_sends_the_cap_its_registry_row_used_to_pass_on_the_command_line(seams):
    """avo's 10 USD (2 Nov 2026), which counts only when the board's writer is DeepSeek."""
    assert cli.main(["relatedness"]) == 0
    assert seams["form"] == {"usd_cap": "10"}


@pytest.mark.parametrize("board", ["swing", "relatedness"])
def test_each_board_posts_exactly_the_form_fields_its_route_takes(seams, board):
    """The cap belongs to the one row that had it; every other route takes its arguments from the board."""
    assert cli.main([board]) == 0
    assert seams["form"] == cli.FORM.get(board)
    assert set(cli.FORM) == {"relatedness"}, "a second board with a field needs its own words here"


def test_it_waits_for_no_session_bar(seams, monkeypatch):
    """Profiles are scored against each other, so there is no SPY bar to wait for -- and Sunday 22:15 has none."""
    monkeypatch.setattr(cli.ledger, "d01_has_session", lambda session, ticker: False)
    assert cli.main(["relatedness"]) == 0 and len(seams["posts"]) == 1


def test_a_store_busy_all_window_postpones_the_run_instead_of_failing_it(seams, monkeypatch, capsys):
    """Exit 3 is "nothing was written", which the Jobs board reads as neutral; exit 1 was a red weekly row."""
    monkeypatch.setitem(cli._BOARD_WAIT_S, "relatedness", -1)
    seams["idle"] = [{"idle": False, "reasons": ["another store process: pid 834460"]}]
    assert cli.main(["relatedness"]) == cli.EXIT_NOT_READY
    assert seams["posts"] == [] and "834460" in _line(capsys)["reason"]


def test_its_window_fits_inside_the_unit_s_four_hour_limit(seams):
    """life-rc-relatedness.service has TimeoutStartSec=4h: a longer wait would be killed mid-poll."""
    assert cli._WAIT_S < cli._BOARD_WAIT_S["relatedness"] < 4 * 3600
