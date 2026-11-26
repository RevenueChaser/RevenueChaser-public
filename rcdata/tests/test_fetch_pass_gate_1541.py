"""The hourly storage fetch pass is not a builder (#1541, avo 26 Nov 2026: "kapıdan çıkar").

``--no-duckdb`` and ``--fetch-only`` both write raw files and Parquet partitions and open no serving file, but
only the first was ever treated that way: ``__main__`` read ``args.no_duckdb``, which the hourly pass does not
set, so the pass that runs every hour at ``:45`` took the build gate (``base.idle_problem``) and held
``base.BUILDER_LOCK`` for its whole fetch. Three things followed, and each one is a test here:

* a job lock on the market store refused the tick outright (exit 3), and a refused tick writes no check row, so
  ``due._fetch_hour``'s one retry -- which fires only on a ``failed`` row -- could never fire: the window was
  lost until the next day;
* the pass marked a builder's presence, so the real builder would not start beside it;
* ``base.heavy_fetch_problem`` -- avo's one condition for accepting option A on 25 Nov 2026, "no build while a
  heavy dataset is being fetched" -- reads the ``rcdata_fetch_<dataset>`` locks, and the hourly pass took none.
  It could only ever fire for a fetch somebody ran by hand.

So the pass now goes the way ``--no-duckdb`` goes: no gate, no builder lock, and one
``rcdata_fetch_<dataset>`` lock per dataset of the batch, held across its fetch. The datasets are the fakes of
``test_build_batch.py``: they send no call.
"""
from __future__ import annotations

from datetime import date

import pytest

from revenuechaser.core import job_lock
from revenuechaser.rcdata import ops
from revenuechaser.rcdata import build as build_pkg
from revenuechaser.rcdata.build import __main__ as cli
from revenuechaser.rcdata.build import base, due

AS_OF = date(2026, 11, 25)


class Fake:
    """A dataset that sends no call and writes one one-row table; its ``fetch`` reads the locks of its own run."""
    providers: tuple[str, ...] = ()

    def __init__(self, name: str, *, heavy: bool = False, seen: dict | None = None):
        self.name, self.kind, self.heavy = name, "market", heavy
        self.tables = (f"t_{name.replace('/', '_')}",)
        self.seen = seen if seen is not None else {}

    def default_as_of(self) -> date:
        return AS_OF

    def fetch(self, ctx, as_of):
        self.seen[self.name] = {"locks": {n for n, _ in job_lock.holders()},
                                "idle_problem": base.idle_problem()}
        return []

    def to_parquet_all(self, ctx, raws):
        return []

    def build(self, ctx, con):                      # pragma: no cover - the fetch pass must never reach it
        con.execute(f"CREATE OR REPLACE TABLE {self.tables[0]} AS SELECT 1 AS x")
        return {self.tables[0]: 1}

    def check(self, ctx, con):                      # pragma: no cover - nor this
        return {"dataset": self.name, "result": "changed", "rows": 1, "added": 1, "removed": 0}


@pytest.fixture
def fakes(monkeypatch):
    """One light dataset and one heavy one, and the dict their fetches write what they saw into.

    ``due.enqueue_due`` is stubbed out: it would run its own rules over two datasets that declare none and fail
    the pass for a reason that has nothing to do with the gate (``enqueue_due`` keeps a per-dataset error as the
    row's ``error``, which exits 1). Each test queues the request it wants drained.
    """
    base.parquet_root().mkdir(parents=True, exist_ok=True)
    seen: dict = {}
    reg = {"m/plain": Fake("m/plain", seen=seen), "m/heavy": Fake("m/heavy", heavy=True, seen=seen)}
    monkeypatch.setattr(build_pkg, "DATASETS", reg)
    monkeypatch.setattr(due, "enqueue_due", lambda **kw: [])
    return reg, seen


def _fetch_pass() -> int:
    """The hourly storage tick, as ``life-rc-store-fetch`` runs it."""
    return cli.main(["run", "--once", "--fetch-only"])


def _status(rid: int) -> str:
    return next(r for r in ops.rows("build_requests") if r["id"] == rid)["status"]


# ── The gate: a job lock on the market store no longer loses the window ───────────────────────────────────────
def test_a_job_lock_on_the_market_store_does_not_refuse_the_hourly_fetch(fakes, capsys):
    """The defect's own line: ``builder not started: job lock held: rcdata_build`` and exit 3 for a pass that
    writes no serving file."""
    reg, seen = fakes
    rid = ops.enqueue("m/plain", None, by="schedule")
    with job_lock.acquire("rcdata_build", wait=0) as got:
        assert got, "the test needs the lock the real builder would hold"
        code = _fetch_pass()
    assert code != 3, "a fetch that opens no serving file is not held off by the builder's own lock"
    assert "builder not started" not in capsys.readouterr().err
    # ``skipped``, not ``done``: a fetch pass stages and builds nothing (``base.FETCH_ONLY_PASS``), which is what
    # the staged check row of ``test_build_lock_split_1532.py`` reads too. What matters here is that it ran at all.
    assert _status(rid) == "skipped" and "m/plain" in seen


def test_the_fetch_pass_does_not_hold_the_builder_lock_while_it_fetches(fakes):
    reg, seen = fakes
    ops.enqueue("m/plain", None, by="schedule")
    assert _fetch_pass() == 0
    assert base.BUILDER_LOCK not in seen["m/plain"]["locks"], \
        "holding it through a fetch is what kept every build waiting"


def test_the_fetch_pass_holds_its_own_dataset_lock_while_it_fetches_and_gives_it_back(fakes):
    """The lock is not bookkeeping: ``heavy_fetch_problem`` and a second run of the same dataset read it.

    Held **and** given back in one test on purpose: "given back" alone passes on a base that never takes the lock,
    so it would prove nothing (``red-on-base``, CLAUDE.md).
    """
    reg, seen = fakes
    ops.enqueue("m/plain", None, by="schedule")
    assert _fetch_pass() == 0
    assert base.fetch_lock_name("m/plain") in seen["m/plain"]["locks"]
    assert base.fetch_lock_name("m/plain") not in {n for n, _ in job_lock.holders()}


def test_two_fetch_passes_of_one_dataset_do_not_run_at_once(fakes):
    """What each lock's own name holds off, and the only thing it holds off. Nothing failed, so the tick is still
    exit 0: the request simply waits, as it does for a heavy dataset's turn (#812)."""
    reg, seen = fakes
    rid = ops.enqueue("m/plain", None, by="schedule")
    with job_lock.acquire(base.fetch_lock_name("m/plain"), wait=0) as got:
        assert got
        assert _fetch_pass() == 0
    assert "m/plain" not in seen, "the second run left it alone instead of fetching beside the first"
    assert _status(rid) == "queued", "and its request is left for the next tick"


# ── avo's condition (25 Nov 2026, option A Q4): no build beside a heavy fetch ─────────────────────────────────
def test_a_build_is_refused_while_the_hourly_pass_fetches_a_heavy_dataset(fakes):
    """``heavy_fetch_problem`` reads the dataset locks, so the condition only holds if the pass takes them."""
    reg, seen = fakes
    ops.enqueue("m/heavy", None, by="schedule")
    assert _fetch_pass() == 0
    problem = seen["m/heavy"]["idle_problem"]
    assert problem is not None and "heavy" in problem and "m/heavy" in problem


def test_a_build_runs_beside_the_hourly_pass_fetching_a_light_dataset(fakes):
    """What makes the split worth having, now for the scheduled fetch and not only a hand-run one."""
    reg, seen = fakes
    ops.enqueue("m/plain", None, by="schedule")
    assert _fetch_pass() == 0
    assert seen["m/plain"]["idle_problem"] is None


# ── The presence marker: the pass is not a builder, so it does not claim to be one ────────────────────────────
def test_the_fetch_pass_leaves_no_builder_presence_marker(fakes, monkeypatch):
    reg, seen = fakes
    marked: list = []
    from revenuechaser.core import rawstore
    monkeypatch.setattr(rawstore, "_register_presence", lambda p: marked.append(p))
    ops.enqueue("m/plain", None, by="schedule")
    assert _fetch_pass() == 0
    assert marked == [], "a marker here stops the real builder from starting"
