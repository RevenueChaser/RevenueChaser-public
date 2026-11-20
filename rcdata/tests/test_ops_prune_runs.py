"""``ops.prune_runs``: the run rows are kept one year, and the deleter is the hourly builder pass.

avo, 20 Nov 2026 ("Bir yil yeterli ama her seyi tuttugundan emin ol, hangi service yapacak bunu?"): ``job_runs2``,
``build_requests`` and ``dataset_check`` had no retention rule at all (review of 20 Nov 2026, finding R5). They are
the inside view of the runs homesrv keeps in ``ops.db job_runs`` for 365 days, so they get the same year, and the
hourly builder pass deletes them, because it is the writer of this store.

These tests run on whichever backend is configured (CI: Redis), so both get the same rules.
"""
from __future__ import annotations

import time

import pytest

from RevenueChaser.rcdata import ops

DAY = 86400.0


def _run(run_id, dataset="market_series", started=None, finish="ok"):
    ops.start_run(run_id, dataset, "hourly")
    if started is not None:
        _age(run_id, started)
    if finish is not None:
        ops.finish_run(run_id, finish)
    return run_id


def _age(run_id, started):
    """Move one run's start back in time; a public call cannot, and the clock is what the rule reads."""
    row = next(r for r in ops.rows("job_runs2") if r["run_id"] == run_id)
    ops.put_rows("job_runs2", [{**row, "started_at": started}])


def test_a_finished_run_older_than_a_year_goes_and_a_newer_one_stays():
    now = time.time()
    _run("old", started=now - 400 * DAY)
    _run("fresh", started=now - 10 * DAY)
    assert ops.prune_runs()["job_runs2"] == 1
    assert [r["run_id"] for r in ops.rows("job_runs2")] == ["fresh"]


def test_the_default_is_one_year():
    assert ops.RUN_ROWS_DAYS == 365


def test_a_run_that_has_not_finished_is_never_deleted_however_old():
    now = time.time()
    _run("running", started=now - 400 * DAY, finish=None)
    assert ops.prune_runs(days=0)["job_runs2"] == 0
    assert [r["run_id"] for r in ops.rows("job_runs2")] == ["running"]


def test_a_queued_or_running_request_is_never_deleted_however_old():
    queued = ops.enqueue("market_series", None, by="cli")
    taken = ops.enqueue("prices/serving", None, by="cli")
    ops.next_request(only=("prices/serving",))                     # now running
    done = ops.enqueue("funds/etf_holdings", None, by="cli")
    ops.next_request(only=("funds/etf_holdings",))
    ops.finish_request(done, "done")
    assert ops.prune_runs(days=0)["build_requests"] == 1
    assert sorted(r["id"] for r in ops.rows("build_requests")) == sorted((queued, taken))


def test_the_check_rows_a_board_reads_as_a_datasets_state_are_kept_whatever_their_age(monkeypatch):
    """The boards read the newest check row, the newest that is not ``skipped`` and the newest that built. A dataset
    that last built two years ago must still read true, so those three rows are kept however old they are."""
    monkeypatch.setattr(ops, "_today", lambda: "2020-01-01")
    ops.record_check("market_series", "changed", rows=10)          # the newest that built
    ops.record_check("market_series", "failed", note="boom")       # the newest that is not skipped
    ops.record_check("market_series", "skipped", note="paused")    # the newest of all
    ops.record_check("market_series", "changed", rows=1, checked_on="2019-01-01")   # older, superseded: goes
    monkeypatch.setattr(ops, "_today", lambda: "2026-11-20")
    assert ops.prune_runs()["dataset_check"] == 1
    kept = [(r["result"], r["checked_on"]) for r in ops.rows("dataset_check")]
    assert kept == [("changed", "2020-01-01"), ("failed", "2020-01-01"), ("skipped", "2020-01-01")]
    assert ops.latest_check("market_series")["result"] == "skipped"
    assert ops.latest_unskipped_check("market_series")["result"] == "failed"
    assert ops.latest_good_check("market_series")["result"] == "changed"


def test_a_prune_of_an_empty_store_deletes_nothing_and_says_so():
    assert ops.prune_runs() == {"job_runs2": 0, "build_requests": 0, "dataset_check": 0}


def test_how_far_the_kept_history_reaches_is_readable():
    now = time.time()
    _run("old", started=now - 300 * DAY)
    _run("new")
    ops.enqueue("market_series", None, by="cli")
    ops.record_check("market_series", "changed", checked_on="2026-01-02")
    seen = ops.oldest_run_rows()
    assert seen["job_runs2"] == pytest.approx(now - 300 * DAY, abs=5)
    assert seen["job_runs2_rows"] == 2 and seen["build_requests_rows"] == 1
    assert seen["dataset_check"] == "2026-01-02" and seen["dataset_check_rows"] == 1
