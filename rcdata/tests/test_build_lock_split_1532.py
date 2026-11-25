"""The build-lock split, option A (#1532, avo 25 Nov 2026).

One lock, ``rcdata_build``, used to be held for a whole run, so a long model read -- ``sec/reads``, a ``debt.note``
reread -- kept every other build waiting for as long as it asked. Option A splits the run in two: a long read
collects fetch-only (``--no-duckdb``) under its own ``rcdata_fetch_<dataset>`` lock, and a short locked build
writes the serving file.

The three rules this file holds, each one of avo's answers in the thread:

* a dataset whose fetch is a long model read is refused the locked turn (the split itself);
* data staged more than ``due.STAGE_GAP_MAX_H`` hours ago is built on the next pass, whatever its automation mode
  says (Q1: "24 saat");
* a build does not start while a *heavy* dataset is being fetched (Q4: the accepted OOM risk's one condition).

No provider call: every test stops at the queue, at the gate, or on a fake dataset.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from revenuechaser.core import calendar, job_lock
from revenuechaser.rcdata import ops
from revenuechaser.rcdata import build as build_pkg
from revenuechaser.rcdata.build import __main__ as cli
from revenuechaser.rcdata.build import base, due

AS_OF = date(2026, 11, 25)
WED_EVENING = datetime(2026, 11, 25, 22, 0, tzinfo=timezone.utc)

pytestmark = pytest.mark.usefixtures("kinds_full")


class Fake:
    """A dataset that sends no call and builds one one-row table (the fake of ``test_build_heavy_812``)."""
    providers: tuple[str, ...] = ()

    def __init__(self, name: str, kind: str = "market", *, long_read: bool = False, heavy: bool = False,
                 log: list | None = None):
        self.name, self.kind, self.log = name, kind, log if log is not None else []
        self.long_read, self.heavy = long_read, heavy
        self.tables = (f"t_{name.replace('/', '_')}",)

    def default_as_of(self) -> date:
        return AS_OF

    def fetch(self, ctx, as_of):
        self.log.append(self.name)
        return []

    def to_parquet_all(self, ctx, raws):
        return []

    def build(self, ctx, con):
        con.execute(f"CREATE OR REPLACE TABLE {self.tables[0]} AS SELECT 1 AS x")
        return {self.tables[0]: 1}

    def check(self, ctx, con):
        return {"dataset": self.name, "result": "changed", "rows": 1, "added": 1, "removed": 0}


@pytest.fixture
def fakes(monkeypatch):
    base.parquet_root().mkdir(parents=True, exist_ok=True)
    log: list = []
    reg = {"m/read": Fake("m/read", long_read=True, log=log),
           "m/plain": Fake("m/plain", log=log),
           "m/heavy": Fake("m/heavy", heavy=True, log=log)}
    monkeypatch.setattr(build_pkg, "DATASETS", reg)
    monkeypatch.setattr(calendar, "_now", lambda: WED_EVENING)
    return reg, log


def _row(rid: int) -> dict:
    return next(r for r in ops.rows("build_requests") if r["id"] == rid)


def _queued() -> list[tuple[str, dict | None]]:
    import json
    return [(r["dataset"], json.loads(r["params"]) if r["params"] else None)
            for r in ops.rows("build_requests")]


# ── The split: a long read never fetches inside the builder lock ───────────────────────────────────────────────
def test_a_long_read_that_would_also_build_is_refused_and_fetches_nothing(fakes):
    reg, log = fakes
    rid = ops.enqueue("m/read", None, by="test")
    assert cli._run_queue(None, once=True) == 0
    assert log == [], "the read must not start inside the locked turn"
    note = ops.latest_check("m/read")["note"]
    assert "long model read" in note and "--no-duckdb" in note and "rcdata_fetch_m_read" in note
    assert _row(rid)["status"] == "done" and ops.latest_check("m/read")["result"] == "skipped"


def test_the_same_long_read_runs_when_it_builds_nothing(fakes):
    reg, log = fakes
    rid = ops.enqueue("m/read", {"no_duckdb": True}, by="test")
    assert cli._run_queue(None, once=True) == 0
    assert log == ["m/read"], "fetch-only is the route the split leaves open"
    assert _row(rid)["status"] == "done"
    assert base.NO_DUCKDB_NOTE in str(ops.latest_check("m/read")["note"])


def test_a_build_of_what_the_read_staged_is_allowed(fakes):
    """The short locked build: no fetch, no model call, and it is not refused."""
    reg, log = fakes
    ops.enqueue("m/read", {"build_only": True}, by="test")
    assert cli._run_queue(None, once=True) == 0
    assert log == [] and ops.latest_check("m/read")["result"] == "changed"


def test_an_ordinary_dataset_is_untouched_by_the_rule(fakes):
    reg, log = fakes
    ops.enqueue("m/plain", None, by="test")
    assert cli._run_queue(None, once=True) == 0
    assert log == ["m/plain"] and ops.latest_check("m/plain")["result"] == "changed"


def test_the_long_read_flag_reaches_the_real_registry():
    """``sec/reads`` is the pass that held the lock for hours; it declares the flag."""
    from revenuechaser.rcdata.build import DATASETS
    assert "sec/reads" in base.long_read_names()
    assert not base.long_read(DATASETS["market_series"])
    assert base.long_read(None) is False


def test_the_fetch_lock_name_is_the_one_the_cli_takes():
    assert base.fetch_lock_name("sec/reads") == "rcdata_fetch_sec_reads"
    assert cli._fetch_lock_names(type("A", (), {"dataset": "sec/reads", "datasets": None})()) == \
        [base.fetch_lock_name("sec/reads")]


# ── Q1: the 24-hour gap ceiling ───────────────────────────────────────────────────────────────────────────────
def test_the_ceiling_is_twenty_four_hours(fakes):
    assert due.STAGE_GAP_MAX_H == 24.0


@pytest.mark.parametrize("hours, overdue", [(1.0, False), (23.9, False), (24.0, True), (72.0, True)])
def test_a_stage_is_overdue_once_it_passes_the_ceiling(fakes, monkeypatch, hours, overdue):
    ops.record_check("m/plain", "skipped", note=base.NO_DUCKDB_NOTE, run_id="r1")
    monkeypatch.setattr(ops, "run_started_at",
                        lambda run_id: WED_EVENING.timestamp() - hours * 3600.0)
    check = ops.latest_check("m/plain")
    assert (due.stage_overdue(check) is not None) is overdue
    assert due.stage_overdue({"result": "changed", "note": None}) is None, "a build is no stage"


def test_a_stage_under_a_partial_mode_is_built_once_the_ceiling_passes(fakes, monkeypatch):
    """The gap this fixes: under ``parquet`` automation the stage note counted as the mode's finished run, so the
    source staged every hour and was never built."""
    ops.kind_mode_set("market", "parquet", by="avo")
    ops.record_check("m/plain", "skipped", note=base.NO_DUCKDB_NOTE, run_id="r1")
    monkeypatch.setattr(ops, "run_started_at", lambda run_id: WED_EVENING.timestamp() - 2 * 3600.0)
    due.enqueue_due()
    assert _queued() == [], "a fresh stage waits for its ordinary build"
    monkeypatch.setattr(ops, "run_started_at", lambda run_id: WED_EVENING.timestamp() - 30 * 3600.0)
    [(name, why, rid, _)] = [r for r in due.enqueue_due() if r[0] == "m/plain"]
    assert rid is not None and "gap ceiling" in why
    assert _queued() == [("m/plain", {"build_only": True})], "the build of what was staged, at no provider call"


def test_the_fetch_pass_does_not_stage_over_an_overdue_stage(fakes, monkeypatch):
    """A fresh stage every hour would keep the newest check young and the ceiling would never fire."""
    ops.kind_mode_set("market", "full", by="avo")
    ops.record_check("m/plain", "skipped", note=base.NO_DUCKDB_NOTE, run_id="r1")
    monkeypatch.setattr(ops, "run_started_at", lambda run_id: WED_EVENING.timestamp() - 30 * 3600.0)
    [(name, why, rid, _)] = [r for r in due.enqueue_due(stage="fetch") if r[0] == "m/plain"]
    assert rid is None and "not staged over" in why and _queued() == []


def test_the_build_pass_takes_an_overdue_stage_whatever_the_mode_says(fakes, monkeypatch):
    ops.kind_mode_set("market", "raw", by="avo")
    ops.record_check("m/plain", "skipped", note=base.NO_PARQUET_NOTE, run_id="r1")
    monkeypatch.setattr(ops, "run_started_at", lambda run_id: WED_EVENING.timestamp() - 40 * 3600.0)
    [(name, why, rid, _)] = [r for r in due.enqueue_due(stage="build") if r[0] == "m/plain"]
    assert rid is not None and _queued() == [("m/plain", {"build_only": True})]


def test_an_off_source_is_left_to_avos_own_hand(fakes, monkeypatch):
    """``off`` is avo's word that this source is built by hand; the ceiling does not overrule a switch."""
    ops.kind_mode_set("market", "off", by="avo")
    ops.record_check("m/plain", "skipped", note=base.NO_DUCKDB_NOTE, run_id="r1")
    monkeypatch.setattr(ops, "run_started_at", lambda run_id: WED_EVENING.timestamp() - 90 * 3600.0)
    assert _queued() == [] and all(r[2] is None for r in due.enqueue_due())


def test_a_stage_whose_run_row_is_gone_is_aged_by_its_own_day(fakes, monkeypatch):
    ops.record_check("m/plain", "skipped", note=base.NO_DUCKDB_NOTE, checked_on="2026-11-20", run_id=None)
    assert due.stage_age_h(ops.latest_check("m/plain")) >= 24.0


# ── Q4: no build beside a heavy fetch ─────────────────────────────────────────────────────────────────────────
def test_a_heavy_datasets_fetch_lock_holds_the_build_turn_off(fakes):
    reg, _ = fakes
    assert base.idle_problem() is None
    with job_lock.acquire(base.fetch_lock_name("m/heavy"), wait=0) as got:
        assert got
        problem = base.idle_problem()
        assert problem and "heavy" in problem and "m/heavy" in problem
    assert base.idle_problem() is None, "the turn is free again once the fetch ends"


def test_a_light_datasets_fetch_runs_beside_a_build(fakes):
    """What makes the split worth having: a light fetch-only run and a build do go side by side."""
    with job_lock.acquire(base.fetch_lock_name("m/plain"), wait=0) as got:
        assert got and base.idle_problem() is None


def test_another_locks_turn_is_not_held_off_by_a_heavy_fetch(fakes):
    """The condition is the builder's: a heavy fetch is a memory neighbour, not a writer of anyone's file."""
    with job_lock.acquire(base.fetch_lock_name("m/heavy"), wait=0) as got:
        assert got and base.idle_problem("relatedness") is None
