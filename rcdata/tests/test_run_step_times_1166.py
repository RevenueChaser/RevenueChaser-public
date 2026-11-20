"""Where a run's time went, and which chain it belongs to (review of 20 Nov 2026, step 1).

One ``job_runs2`` row already spans a dataset's whole run, fetch to swap, so the total is there. What was not kept
is **the time of each step inside it** (``start``, ``fetch``, ``parquet`` or ``backfill``, ``build``, ``check``,
``swap``, ``after_swap``): ``RunContext.step`` was read only when a run failed (#1119). It now stamps the clock as
it changes, and the seconds per step go into ``job_runs2.counts["steps"]`` -- the column exists since ops schema
v3 and the builder path left it empty, so no schema bump.

And nothing tied the rows of one chain together: an hourly ``RC-Build`` task row and the dataset runs it caused
shared no key. ``core/automations.run_task`` now hands its own run id to the command it starts
(``ops.CHAIN_ID_ENV``), and every run row keeps it in ``params["chain"]``; a run nobody started is the root of its
own chain, so the key is never missing.

The datasets here are fakes registered over ``DATASETS``, as in ``test_build_batch.py``: no call, no Parquet tree.
"""
from __future__ import annotations

from datetime import date

import pytest

from RevenueChaser.rcdata import ops
from RevenueChaser.rcdata import build as build_pkg
from RevenueChaser.rcdata.build import __main__ as cli
from RevenueChaser.rcdata.build import base, due

AS_OF = date(2026, 11, 6)


class Clock:
    """A clock the fake dataset moves itself, so a step's seconds are a measured number and not the wall clock."""

    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now

    def tick(self, seconds: float) -> None:
        self.now += seconds


class Fake:
    providers: tuple[str, ...] = ()

    #: seconds each step takes on the test clock
    COST = {"fetch": 4.0, "parquet": 2.0, "build": 8.0, "check": 1.0}

    def __init__(self, name: str, kind: str = "market", *, clock: Clock, fails: str | None = None):
        self.name, self.kind, self.clock, self.fails = name, kind, clock, fails
        self.tables = (f"t_{name.replace('/', '_')}",)

    def default_as_of(self) -> date:
        return AS_OF

    def _spend(self, step: str) -> None:
        self.clock.tick(self.COST[step])
        if self.fails == step:
            raise base.SourceError(f"{self.name}: sec.gov said 504")

    def fetch(self, ctx, as_of):
        self._spend("fetch")
        return []

    def to_parquet_all(self, ctx, raws):
        self._spend("parquet")
        return []

    def build(self, ctx, con):
        self._spend("build")
        con.execute(f"CREATE OR REPLACE TABLE {self.tables[0]} AS SELECT 1 AS x")
        return {self.tables[0]: 1}

    def check(self, ctx, con):
        self._spend("check")
        return {"dataset": self.name, "result": "changed", "rows": 1, "added": 1, "removed": 0}


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def fakes(monkeypatch, clock):
    base.parquet_root().mkdir(parents=True, exist_ok=True)
    reg = {n: Fake(n, clock=clock) for n in ("m/one", "m/two")}
    monkeypatch.setattr(build_pkg, "DATASETS", reg)
    monkeypatch.setattr(due, "enqueue_due", lambda *a, **k: [])
    return reg


def _steps(run_id: str) -> dict:
    [row] = [r for r in ops.rows("job_runs2") if r["run_id"] == run_id]
    return (ops._loads(row["counts"]) or {}).get("steps") or {}


def _params(run_id: str) -> dict:
    [row] = [r for r in ops.rows("job_runs2") if r["run_id"] == run_id]
    return ops._loads(row["params"]) or {}


# --- the step times ---------------------------------------------------------------------------------


def test_the_context_counts_the_seconds_of_every_step_it_passes_through(clock):
    ctx = base.RunContext(run_id="r1", dataset="m/one", clock=clock)
    clock.tick(3.0)                      # before the first step: the claim, the pause and cap reads
    ctx.step = "fetch"
    clock.tick(4.0)
    ctx.step = "parquet"
    clock.tick(2.0)
    ctx.step = "build"
    clock.tick(8.0)
    ctx.step = "check"
    clock.tick(1.0)
    assert ctx.step_times() == {"start": 3.0, "fetch": 4.0, "parquet": 2.0, "build": 8.0, "check": 1.0}
    assert list(ctx.step_times()) == ["start", "fetch", "parquet", "build", "check"]


def test_a_step_set_to_what_it_already_is_goes_on_counting(clock):
    """``build_kind_many`` sets the step on every member of a pass, so the lead sees the same value twice."""
    ctx = base.RunContext(run_id="r1", dataset="m/one", clock=clock)
    ctx.step = "build"
    clock.tick(5.0)
    ctx.step = "build"
    clock.tick(5.0)
    assert ctx.step_times()["build"] == 10.0


def test_a_step_entered_twice_adds_up(clock):
    ctx = base.RunContext(run_id="r1", dataset="m/one", clock=clock)
    ctx.step = "fetch"
    clock.tick(2.0)
    ctx.step = "build"
    clock.tick(1.0)
    ctx.step = "fetch"
    clock.tick(3.0)
    assert ctx.step_times()["fetch"] == 5.0


def test_the_step_in_hand_is_counted_up_to_now_without_ending_it(clock):
    ctx = base.RunContext(run_id="r1", dataset="m/one", clock=clock)
    ctx.step = "fetch"
    clock.tick(2.0)
    assert ctx.step_times()["fetch"] == 2.0
    clock.tick(3.0)
    assert ctx.step_times()["fetch"] == 5.0


def test_a_run_writes_its_step_times_into_its_run_row(fakes, clock):
    row = base.run_request({"dataset": "m/one", "params": {}}, trigger="test", clock=clock)
    assert row["result"] == "changed"
    steps = _steps(row["run_id"])
    assert steps["fetch"] == 4.0 and steps["parquet"] == 2.0 and steps["build"] == 8.0 and steps["check"] == 1.0
    assert steps["swap"] >= 0.0
    assert sum(steps.values()) >= 15.0


def test_a_failed_run_keeps_the_time_of_the_steps_it_reached(fakes, clock):
    fakes["m/one"].fails = "build"
    row = base.run_request({"dataset": "m/one", "params": {}}, trigger="test", clock=clock)
    assert row["result"] == "failed"
    steps = _steps(row["run_id"])
    assert steps["fetch"] == 4.0 and steps["parquet"] == 2.0 and steps["build"] == 8.0
    assert "check" not in steps and "swap" not in steps


def test_every_member_of_a_batch_pass_gets_its_own_step_times(fakes):
    """One build serves the whole pass, so every member's row names the build, the check and the swap it shared.

    The clock here is the real one (the queue makes the contexts), so this asks for the steps, not for seconds.
    """
    for name in ("m/one", "m/two"):
        ops.enqueue(name, None, by="test")
    assert cli._run_queue(None, once=True) == 0
    rows = [r for r in ops.rows("job_runs2") if r["dataset"] in ("m/one", "m/two")]
    assert len(rows) == 2
    for row in rows:
        steps = _steps(row["run_id"])
        assert set(steps) >= {"fetch", "parquet", "build", "check", "swap"}
        assert all(v >= 0.0 for v in steps.values())


# --- the chain id -----------------------------------------------------------------------------------


def test_a_run_nobody_started_is_the_root_of_its_own_chain(monkeypatch):
    monkeypatch.delenv(ops.CHAIN_ID_ENV, raising=False)
    ops.start_run("r1", "m/one", "cli", {"mode": "daily"})
    assert _params("r1") == {"mode": "daily", "chain": "r1"}


def test_a_run_under_a_task_carries_the_task_s_run_id(monkeypatch):
    monkeypatch.setenv(ops.CHAIN_ID_ENV, "task42")
    ops.start_run("r1", "m/one", "schedule")
    ops.start_run("r2", "m/two", "schedule")
    ops.start_run("t1", None, "schedule", job="RC-Build")
    assert _params("r1")["chain"] == _params("r2")["chain"] == _params("t1")["chain"] == "task42"


def test_a_chain_id_the_caller_named_is_not_overwritten(monkeypatch):
    monkeypatch.setenv(ops.CHAIN_ID_ENV, "task42")
    ops.start_run("r1", "m/one", "queue", {"chain": "asked-for"})
    assert _params("r1")["chain"] == "asked-for"


def test_a_blank_chain_variable_is_no_chain(monkeypatch):
    monkeypatch.setenv(ops.CHAIN_ID_ENV, "   ")
    assert ops.chain_id() is None
    ops.start_run("r1", "m/one", "cli")
    assert _params("r1")["chain"] == "r1"


def test_a_dataset_run_of_a_pass_joins_the_task_s_chain(fakes, clock, monkeypatch):
    """What the Runs tab will group by (step 2): the task's row and the runs it caused under one key."""
    monkeypatch.setenv(ops.CHAIN_ID_ENV, "task42")
    row = base.run_request({"dataset": "m/one", "params": {"mode": "daily"}}, trigger="schedule", clock=clock)
    assert _params(row["run_id"]) == {"mode": "daily", "chain": "task42"}
