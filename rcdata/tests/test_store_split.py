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


def test_the_passes_pick_their_mode(stager):  # noqa: F811
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
