"""The storage fetch / storage build split (avo, 24 Nov 2026): ``run --fetch-only`` never builds a serving DuckDB,
``run --build-only`` builds only what a fetch staged, and every dataset run leaves a measurement line."""
from __future__ import annotations

import json

from revenuechaser.rcdata.build import base, due
from revenuechaser.rcdata.tests.test_no_duckdb import stager  # noqa: F401 - the fixture


def test_a_fetch_pass_never_builds_whatever_the_request_asked(stager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(base, "FETCH_ONLY_PASS", True)
    row = base.run_request({"dataset": stager.name, "params": {}})
    assert row["result"] == "skipped" and stager.built == []
    assert stager.steps == ["fetch", "to_parquet_all"]


def test_the_passes_pick_their_mode(stager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(due, "FETCH_HOURS", {})             # the hours are their own test, below
    assert due._pass_mode(stager, "full", "fetch") == ("parquet", None)
    assert due._pass_mode(stager, "raw", "fetch") == ("raw", None)
    assert due._pass_mode(stager, "full", None) == ("full", None)
    assert due._pass_mode(stager, "parquet", "build")[1]               # never built in full: not the build's
    assert due._pass_mode(stager, "full", "build")[1] == "no staged Parquet waiting for a build"
    base.run_request({"dataset": stager.name, "params": {"no_duckdb": True}})
    assert due._pass_mode(stager, "full", "build") == ("full", None)   # staged: the build takes it
    assert due.is_due(stager, "parquet")[0] is False                    # and the fetch does not fetch it again


def test_every_run_writes_one_measurement_line(stager, monkeypatch, tmp_path):  # noqa: F811
    monkeypatch.setenv("RC_MEASURE_DIR", str(tmp_path))
    base.run_request({"dataset": stager.name, "params": {"no_duckdb": True}})
    (log,) = tmp_path.glob("datasets-*.jsonl")
    (line,) = [json.loads(t) for t in log.read_text().splitlines()]
    assert line["dataset"] == stager.name and line["kind"] == "market" and line["status"] == "skipped"
    assert "fetch" in line["steps_s"] and line["parquet"]["files"] == 0


def test_a_by_hand_source_staged_once_by_a_person_is_due_for_the_fetch(stager, monkeypatch):  # noqa: F811
    monkeypatch.setattr(type(stager), "starts_by_hand", True, raising=False)
    assert due.is_due(stager, "parquet") == (False, due.BY_HAND_WHY)
    base.run_request({"dataset": stager.name, "params": {"no_duckdb": True}})
    assert due.is_due(stager, "parquet")[1] != due.BY_HAND_WHY
    assert due.is_due(stager, "full")[1] == due.BY_HAND_WHY             # a build still waits for a person's build


def test_an_hourly_source_is_due_for_the_fetch_after_a_build(stager, monkeypatch):  # noqa: F811
    """Review of #1483: the :05 build's check made the :45 fetch read "40 min ago" and skip every second hour."""
    from revenuechaser.rcdata import ops
    monkeypatch.setattr(type(stager), "cadence", "hourly")
    ops.record_check(stager.name, "unchanged", source_as_of="2026-10-28")
    assert due.is_due(stager, "parquet") == (True, "hourly: the newest check is a build, not a fetch")


def test_a_market_source_is_fetched_at_its_two_hours_and_retried_once(stager, monkeypatch):  # noqa: F811
    """avo, 24 Nov 2026: market at 07:45 and 22:45 (before its 08:25 / 23:25 build), not hourly."""
    from datetime import datetime
    from revenuechaser.core import calendar
    from revenuechaser.rcdata import ops

    def at(hour):
        monkeypatch.setattr(calendar, "_now", lambda: datetime(2026, 11, 24, hour, 45, tzinfo=due.AMS))
        return due._pass_mode(stager, "full", "fetch")[1]
    assert at(7) is None and at(22) is None
    assert at(12) == "market is fetched at 07:45 and 22:45 (FETCH_HOURS)" and at(8) is not None
    ops.record_check(stager.name, "failed", note="fetch failed")
    assert at(8) is None and at(9) is not None                 # one retry, the hour after
    assert due._pass_mode(stager, "full", "build")[1] is not None   # the build pass is not held by the hours


def test_a_build_only_request_builds_without_fetching(stager):  # noqa: F811
    """Review of #1494: the storage build's own request builds what was staged, with no second fetch."""
    row = base.run_request({"dataset": stager.name, "params": {"build_only": True}})
    assert stager.steps == [] and stager.built == [stager.name] and row["result"] == "changed"


def test_the_build_pass_queues_build_only_requests_the_fetch_never_takes(stager, monkeypatch):  # noqa: F811
    from revenuechaser.rcdata import ops
    monkeypatch.setattr(ops, "dataset_mode", lambda name, kind: "full")
    base.run_request({"dataset": stager.name, "params": {"no_duckdb": True}})
    (got,) = [r for r in due.enqueue_due({stager.name: stager}, stage="build") if r[2]]
    req = ops.next_request(stager.name)
    assert ops.params_of(req["params"]) == {"build_only": True}
    ops.finish_request(req["id"], "failed", note="test")
    ops.enqueue(stager.name, {"build_only": True}, by=due.REQUESTED_BY)
    assert ops.next_request(fetch_only=True, or_by=due.REQUESTED_BY) is None


def _at(monkeypatch, hour):
    from datetime import datetime
    from revenuechaser.core import calendar
    monkeypatch.setattr(calendar, "_now", lambda: datetime(2026, 11, 24, hour, 45, tzinfo=due.AMS))


def test_a_kinds_own_fetch_hours_win_and_every_hour_falls_back_to_the_code(stager, monkeypatch):  # noqa: F811
    """avo, 24 Nov 2026 ("fetch timer duckdb bazli olmali"): a DuckDB's hours set from Grafana win over FETCH_HOURS;
    dropping the row is the code's hours again, never every hour while the code names the kind."""
    from revenuechaser.rcdata import ops
    ops.fetch_hours_set("market", "9")
    _at(monkeypatch, 7)
    assert due._pass_mode(stager, "full", "fetch")[1] == "market is fetched at 09:45 (kind_fetch_hours)"
    _at(monkeypatch, 9)
    assert due._pass_mode(stager, "full", "fetch")[1] is None
    ops.fetch_hours_set("market", None)
    assert due.fetch_hours("market") == ((7, 22), "FETCH_HOURS")
    assert due._pass_mode(stager, "full", "fetch")[1] == "market is fetched at 07:45 and 22:45 (FETCH_HOURS)"
    assert due.fetch_hours("spine") == (None, "every hour")


def test_the_hour_is_read_on_the_amsterdam_clock(stager, monkeypatch):  # noqa: F811
    """06:45 UTC is 07:45 in Amsterdam in winter: market's hour, whatever zone the process runs in."""
    from datetime import datetime, timezone
    from revenuechaser.core import calendar
    monkeypatch.setattr(calendar, "_now", lambda: datetime(2026, 11, 24, 6, 45, tzinfo=timezone.utc))
    assert due._pass_mode(stager, "full", "fetch")[1] is None


def test_unreadable_fetch_hours_fail_the_due_check_and_never_fetch_hourly(stager, monkeypatch):  # noqa: F811
    from revenuechaser.rcdata import ops
    ops.fetch_hours_set("market", "seven")
    _at(monkeypatch, 12)
    ((name, why, rid, error),) = due.enqueue_due({stager.name: stager}, stage="fetch")
    assert rid is None and error and "ValueError" in why


def test_the_due_line_names_what_let_a_kind_through_its_hour(stager, monkeypatch):  # noqa: F811
    """The live check before FETCH_HOURS goes: a 07:45 tick says which list let market in."""
    from revenuechaser.rcdata import ops
    monkeypatch.setattr(ops, "dataset_mode", lambda name, kind: "full")
    _at(monkeypatch, 7)
    ((_, why, rid, _),) = due.enqueue_due({stager.name: stager}, stage="fetch")
    assert rid and "hour gate FETCH_HOURS 07,22" in why
    ops.finish_request(rid, "failed", note="test")
    ops.fetch_hours_set("market", "7,22")
    ((_, why, _, _),) = due.enqueue_due({stager.name: stager}, stage="fetch")
    assert "hour gate kind_fetch_hours 07,22" in why


def test_the_next_fetch_is_the_next_45_in_the_kinds_hours(monkeypatch):
    from datetime import datetime
    _at(monkeypatch, 8)
    assert due.next_fetch("market") == datetime(2026, 11, 24, 22, 45, tzinfo=due.AMS)
    assert due.next_fetch("spine", datetime(2026, 11, 24, 8, 50, tzinfo=due.AMS)) == \
        datetime(2026, 11, 24, 9, 45, tzinfo=due.AMS)
    assert due.next_fetch("spine", datetime(2026, 11, 24, 8, 45, tzinfo=due.AMS)).hour == 8


def test_fetch_hours_parse_only_whole_hours_and_not_all_24():
    import pytest
    assert due.parse_hours("22,7") == (7, 22) and due.parse_hours([7, "22"]) == (7, 22)
    for bad in ("", "24", "-1", "7.5", [True], [], list(range(24)), "seven"):
        with pytest.raises(ValueError):
            due.parse_hours(bad)
