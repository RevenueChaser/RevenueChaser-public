"""#1205, the Runs tab reads ``job_runs2``: one line per run with its steps, grouped by chain, a day total, and
the RevenueChaser half of the run-record audit.

The tab's own shell (its filters, its clamps, its phone layout, the escaping of a stored value) is
``test_runs_tab.py``; this file is about what the page now holds. Nothing here touches the network, and every row
is written through ``ops``, so the test runs on whichever backend CI configures.
"""
from __future__ import annotations

import time

import pytest

from RevenueChaser.app import activity, dashboard, runview
from RevenueChaser.rcdata import ops

DAY = 86_400.0


@pytest.fixture()
def client():
    dashboard.app.config["TESTING"] = True
    return dashboard.app.test_client()


def _stored(run_id, *, dataset=None, job=None, trigger="schedule", started=1_792_700_000.0, finished=None,
            status="ok", steps=None, counts=None, error=None, chain=None):
    counts = dict(counts or {})
    if steps is not None:
        counts["steps"] = steps
    return {"run_id": run_id, "dataset": dataset, "job": job, "trigger": trigger, "pid": 11, "host": "box",
            "started_at": started, "finished_at": finished, "status": status, "error": error,
            "counts": counts, "params": {"chain": chain or run_id}}


# ── one run becomes one line ──────────────────────────────────────────────────

def test_a_builder_run_is_named_by_its_dataset_and_carries_its_steps():
    row = runview.view_row(_stored("r1", dataset="prices/price_bar_daily", started=100.0, finished=400.0,
                                   steps={"start": 0.5, "fetch": 120.0, "build": 170.0},
                                   counts={"rows": 7}, chain="pass1"))
    assert row["module"] == "prices/price_bar_daily" and row["kind"] == "build"
    assert row["duration_s"] == 300.0 and row["chain"] == "pass1"
    assert row["steps"] == [{"name": "start", "seconds": 0.5}, {"name": "fetch", "seconds": 120.0},
                            {"name": "build", "seconds": 170.0}], "the order the steps ran is the order shown"
    assert row["counts"] == {"rows": 7}, "the steps have their own column: they are not left in Counts too"
    assert row["params"] == {}, "the chain has its own column as well"


def test_a_task_and_a_dashboard_job_are_told_apart_by_their_trigger():
    assert runview.view_row(_stored("r2", job="RC-Build"))["kind"] == "task"
    assert runview.view_row(_stored("r3", job="module_news", trigger="dashboard"))["kind"] == "dashboard"


def test_a_run_with_no_end_has_no_duration_and_a_step_that_is_not_a_number_is_left_out():
    row = runview.view_row(_stored("r4", dataset="d", finished=None, status="running",
                                   steps={"fetch": 12.0, "build": "soon"}))
    assert row["duration_s"] is None
    assert row["steps"] == [{"name": "fetch", "seconds": 12.0}], "a step is shown as recorded or not at all"


def test_a_run_recorded_before_the_step_record_simply_has_no_steps():
    assert runview.view_row(_stored("r5", dataset="d", steps=None))["steps"] == []


# ── the chain ─────────────────────────────────────────────────────────────────

def test_a_pass_and_the_dataset_runs_it_caused_are_one_chain_with_its_span_and_busy_time():
    rows = [runview.view_row(r) for r in [
        _stored("pass1", job="RC-Build", started=1_000.0, finished=1_600.0, status="done"),
        _stored("d1", dataset="a", started=1_010.0, finished=1_210.0, chain="pass1"),
        _stored("d2", dataset="b", started=1_210.0, finished=1_590.0, chain="pass1"),
    ]]
    [chain] = runview.chains(rows)
    assert chain["chain"] == "pass1" and chain["name"] == "RC-Build" and chain["runs"] == 3
    assert chain["seconds"] == 600.0, "the span is the first start to the last end"
    assert chain["busy_s"] == 1180.0, "busy is the sum of the runs, which is more when they overlap"
    assert chain["bad"] == 0 and chain["status"] == "done"
    assert chain["run_ids"] == ["pass1", "d1", "d2"]


def test_a_chain_still_running_has_no_span_and_says_so():
    rows = [runview.view_row(r) for r in [
        _stored("pass1", job="RC-Build", started=1_000.0, finished=None, status="running"),
        _stored("d1", dataset="a", started=1_010.0, finished=1_210.0, chain="pass1"),
    ]]
    [chain] = runview.chains(rows)
    assert chain["seconds"] is None and chain["finished_at"] is None and chain["running"] == 1
    assert chain["status"] == "running"


def test_a_failed_run_makes_its_chain_a_failed_chain():
    rows = [runview.view_row(r) for r in [
        _stored("pass1", job="RC-Build", started=1_000.0, finished=1_600.0, status="done"),
        _stored("d1", dataset="a", started=1_010.0, finished=1_210.0, status="failed", chain="pass1"),
    ]]
    [chain] = runview.chains(rows)
    assert chain["bad"] == 1 and chain["status"] == "failed"


def test_the_newest_chain_comes_first():
    rows = [runview.view_row(r) for r in [
        _stored("old", dataset="a", started=1_000.0, finished=1_100.0),
        _stored("new", dataset="b", started=9_000.0, finished=9_100.0),
    ]]
    assert [c["chain"] for c in runview.chains(rows)] == ["new", "old"]


# ── the day total ─────────────────────────────────────────────────────────────

def test_the_day_strip_counts_runs_time_and_failures_per_day():
    now = time.time()
    rows = [runview.view_row(r) for r in [
        _stored("a", dataset="a", started=now, finished=now + 60.0),
        _stored("b", dataset="b", started=now + 1.0, finished=now + 31.0, status="failed"),
        _stored("c", dataset="c", started=now + 2.0, finished=None, status="running"),
        _stored("d", dataset="d", started=now - DAY, finished=now - DAY + 10.0),
    ]]
    today, yesterday = runview.days(rows)
    assert today["runs"] == 3 and today["seconds"] == 90.0 and today["failed"] == 1 and today["running"] == 1
    assert yesterday["runs"] == 1 and yesterday["seconds"] == 10.0
    assert today["day"] > yesterday["day"], "newest day first"


# ── the record audit (the RC half of home-server #519) ────────────────────────

def test_a_chain_whose_own_run_left_no_row_is_counted():
    rows = [runview.view_row(_stored("d1", dataset="a", chain="ghost"))]
    got = runview.audit(rows, exists=set())
    assert got["checked"] and got["missing_root"] == 1 and got["missing_chains"] == ["ghost"]


def test_a_root_that_started_before_the_page_is_not_a_gap():
    """The audit asks the store whether the root run has a row, not the page it happens to have read."""
    rows = [runview.view_row(_stored("d1", dataset="a", chain="older"))]
    assert runview.audit(rows, exists={"older"})["missing_root"] == 0


def test_a_row_with_no_chain_id_is_counted_and_named():
    row = runview.view_row(_stored("d1", dataset="a"))
    row["chain"] = None                                    # a row written before the chain id existed (#1198)
    got = runview.audit([row], exists=set())
    assert got["no_chain"] == 1 and got["no_chain_runs"] == ["d1"]


def test_a_run_that_is_its_own_chain_root_is_never_a_gap():
    rows = [runview.view_row(_stored("solo", dataset="a"))]
    assert runview.audit(rows, exists=set()) == {"checked": True, "no_chain": 0, "no_chain_runs": [],
                                                 "missing_root": 0, "missing_chains": [], "rows": 1}


def test_an_unreadable_store_is_not_checked_rather_than_zero_gaps(monkeypatch):
    def boom(_ids):
        raise RuntimeError("ops is busy")

    monkeypatch.setattr(ops, "runs_exist", boom)
    got = runview.audit([runview.view_row(_stored("d1", dataset="a", chain="ghost"))])
    assert got["checked"] is False and got["missing_root"] == 0, "a gap is never invented from a failed read"


# ── the reader, over the real store ───────────────────────────────────────────

def _write(run_id, *, dataset=None, job=None, trigger="schedule", status="ok", counts=None, chain=None):
    """A run as its writer records it: ``start_run`` then ``finish_run`` (``core/automations`` and the builder)."""
    import os
    if chain:
        os.environ[ops.CHAIN_ID_ENV] = chain
    try:
        ops.start_run(run_id, dataset, trigger, job=job)
    finally:
        os.environ.pop(ops.CHAIN_ID_ENV, None)
    ops.finish_run(run_id, status, None, counts)


def test_the_tab_lists_what_the_store_holds_with_the_steps_and_the_chain():
    _write("pass1", job="RC-Build")
    _write("ds1", dataset="prices/price_bar_daily", counts={"rows": 3, "steps": {"fetch": 9.0, "build": 21.0}},
           chain="pass1")
    got = runview.read()
    assert got["ok"] and got["read"] == 2 and {r["run_id"] for r in got["rows"]} == {"pass1", "ds1"}
    ds = next(r for r in got["rows"] if r["run_id"] == "ds1")
    assert ds["steps"] == [{"name": "fetch", "seconds": 9.0}, {"name": "build", "seconds": 21.0}]
    assert ds["chain"] == "pass1" and ds["duration_s"] is not None
    [chain] = got["chains"]
    assert chain["chain"] == "pass1" and chain["runs"] == 2 and chain["name"] == "RC-Build"
    assert got["audit"]["checked"] and got["audit"]["missing_root"] == 0
    assert got["days"] and got["days"][0]["runs"] == 2


def test_problems_only_keeps_the_failed_runs_and_the_name_filter_keeps_its_dataset():
    _write("ok1", dataset="prices/price_bar_daily")
    _write("bad1", dataset="sec/reads", status="failed")
    _write("bad2", job="module_news", trigger="dashboard", status="error")
    assert {r["run_id"] for r in runview.read(problems=True)["rows"]} == {"bad1", "bad2"}
    assert {r["run_id"] for r in runview.read(query="prices")["rows"]} == {"ok1"}
    assert runview.read(query="prices")["read"] == 3, "the window read is named, so a 0 is never read as never"


def test_the_api_serves_the_rows_the_chains_and_the_audit(client):
    _write("ds1", dataset="prices/price_bar_daily", counts={"steps": {"fetch": 4.0}})
    data = client.get("/api/runs").get_json()
    assert [r["run_id"] for r in data["rows"]] == ["ds1"]
    assert data["chains"][0]["runs"] == 1 and data["audit"]["checked"] and "days" in data


def test_a_builder_run_is_not_a_press_on_a_board():
    """``/api/activity/boards`` counts the Fetches pressed on a board; a dataset run and a task are neither."""
    rows = [{"module": "module_news", "kind": "dashboard", "status": "done", "started_at": 10.0},
            {"module": "module_news", "kind": "build", "status": "ok", "started_at": 20.0},
            {"module": "RC-Build", "kind": "task", "status": "done", "started_at": 30.0}]
    got = activity.pressed_by_board(rows)
    assert got["module_news"] == {"runs": 1, "last": 10.0, "bad": 0}
    assert activity.SYSTEM not in got


def test_a_cancelled_dashboard_run_counts_as_a_bad_one():
    """The dashboard's own words reach this counter for the first time (#1205): before, only ``failed`` did."""
    got = activity.pressed_by_board([{"module": "module_news", "status": "cancelled", "started_at": 1.0}])
    assert got["module_news"]["bad"] == 1


# ── the page ──────────────────────────────────────────────────────────────────

def test_the_page_shows_the_day_strip_the_steps_column_and_the_chain_switch(client):
    html = client.get("/view/runs").get_data(as_text=True)
    assert '<th scope="col">Steps</th>' in html
    assert 'id="runs-tiles"' in html and 'id="runs-chains"' in html
    assert "Group by chain" in html
    assert "runs with no record" in html, "the audit has a tile of its own"
    for sink in (".innerHTML", ".outerHTML", "insertAdjacentHTML", "document.write"):
        assert sink not in html, "a step name and a chain id are stored text: they go in through textContent"
