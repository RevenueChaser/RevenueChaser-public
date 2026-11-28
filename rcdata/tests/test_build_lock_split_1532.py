"""The build-lock split, option A (#1532, avo 25 Nov 2026).

One lock, ``rcdata_build``, used to be held for a whole run, so a queued pass that fetched a long model read --
``sec/reads``, a ``debt.note`` reread -- kept every other build waiting for as long as it asked. Option A splits
the pass in two: it stages such a dataset fetch-only (``--no-duckdb``), under that dataset's own
``rcdata_fetch_<dataset>`` lock, and then queues the short locked build of what was staged. A run a person asks
for by name, and a Fetch press, are untouched -- theirs is one turn on purpose.

The three rules this file holds, each one of avo's answers in the thread:

* a pass never fetches a ``long_read`` dataset and builds it in the same turn (the split itself);
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
from revenuechaser.rcdata.build import DATASETS, base, due

MS = "market_series"
AS_OF = date(2026, 11, 25)
#: Wed 25 Nov 2026, 18:00 New York (the session is complete), the evening avo took the decision.
WED_EVENING = datetime(2026, 11, 25, 23, 0, tzinfo=timezone.utc)

#: ``kinds_full`` gives every dataset its own ``full`` automation row, and a dataset's own row wins over its
#: kind's (#527), so these tests set the mode with ``ops.dataset_mode_set``, never ``kind_mode_set``.
pytestmark = pytest.mark.usefixtures("kinds_full")


@pytest.fixture
def one_source(monkeypatch):
    """The real ``market_series`` alone, with the clock fixed: the pass's own rules are what these tests read."""
    monkeypatch.setattr(build_pkg, "DATASETS", {MS: DATASETS[MS]})
    monkeypatch.setattr(calendar, "_now", lambda: WED_EVENING)
    return DATASETS[MS]


@pytest.fixture
def long_source(one_source, monkeypatch):
    """``market_series`` standing in for a long model read, so the rule is read off the pass and not off the one
    dataset that declares the flag today."""
    monkeypatch.setattr(one_source, "long_read", True, raising=False)
    return one_source


def _staged_check(hours_ago: float, monkeypatch, *, note: str | None = None) -> None:
    """One staged check ``hours_ago`` old. ``next_check_due`` is the session after this one, so the cadence itself
    does not make the dataset due: what these tests read is the stage rule, not the calendar."""
    ops.record_check(MS, "skipped", note=note or base.NO_DUCKDB_NOTE, run_id="r1",
                     source_as_of=AS_OF.isoformat(), next_check_due="2026-11-27")
    monkeypatch.setattr(ops, "run_started_at", lambda run_id: WED_EVENING.timestamp() - hours_ago * 3600.0)


def _queued() -> list[tuple[str, dict | None]]:
    import json
    return [(r["dataset"], json.loads(r["params"]) if r["params"] else None)
            for r in ops.rows("build_requests")]


def _one(rows: list[tuple]) -> tuple:
    [row] = [r for r in rows if r[0] == MS]
    return row


# ── The split: a pass stages a long read, then builds what it staged ──────────────────────────────────────────
def test_a_pass_stages_a_long_read_instead_of_building_it_in_one_turn(long_source):
    name, why, rid, error = _one(due.enqueue_due())
    assert rid is not None and not error, why
    assert _queued() == [(MS, {"no_duckdb": True})], "the pass holds no builder lock through the read"


def test_the_next_pass_queues_the_short_build_of_what_was_staged(long_source, monkeypatch):
    _staged_check(1.0, monkeypatch)
    name, why, rid, error = _one(due.enqueue_due())
    assert rid is not None and not error, why
    assert "long model read's stage" in why
    assert _queued() == [(MS, {"build_only": True})], "the build is its own short turn, at no provider call"


def test_an_ordinary_source_still_fetches_and_builds_in_one_turn(one_source):
    name, why, rid, error = _one(due.enqueue_due())
    assert rid is not None and not error, why
    assert _queued() == [(MS, None)], "only a long read is split"


def test_the_build_pass_takes_a_long_reads_stage_whatever_the_mode_says(long_source, monkeypatch):
    ops.dataset_mode_set(MS, "parquet", by="avo")
    _staged_check(1.0, monkeypatch)
    name, why, rid, error = _one(due.enqueue_due(stage="build"))
    assert rid is not None and not error, why
    assert _queued() == [(MS, {"build_only": True})]


def test_the_long_read_flag_reaches_the_real_registry():
    """``sec/reads`` is the pass that held the lock for hours; it declares the flag."""
    assert "sec/reads" in base.long_read_names()
    assert not base.long_read(DATASETS[MS])
    assert base.long_read(None) is False


def test_the_fetch_lock_name_is_the_one_the_cli_takes():
    from revenuechaser.rcdata.build import __main__ as cli
    assert base.fetch_lock_name("sec/reads") == "rcdata_fetch_sec_reads"
    assert cli._fetch_lock_names(type("A", (), {"dataset": "sec/reads", "datasets": None})()) == \
        [base.fetch_lock_name("sec/reads")]


# ── Q1: the 24-hour gap ceiling ───────────────────────────────────────────────────────────────────────────────
def test_the_ceiling_is_twenty_four_hours():
    assert due.STAGE_GAP_MAX_H == 24.0


@pytest.mark.parametrize("hours, overdue", [(1.0, False), (23.9, False), (24.0, True), (72.0, True)])
def test_a_stage_is_overdue_once_it_passes_the_ceiling(one_source, monkeypatch, hours, overdue):
    _staged_check(hours, monkeypatch)
    assert (due.stage_overdue(ops.latest_check(MS)) is not None) is overdue
    assert due.stage_overdue({"result": "changed", "note": None}) is None, "a build is no stage"
    assert due.stage_overdue(None) is None


def test_a_stage_under_a_partial_mode_is_built_once_the_ceiling_passes(one_source, monkeypatch):
    """The gap this fixes: under ``parquet`` automation the stage note counted as the mode's finished run, so the
    source staged every hour and was never built at all."""
    ops.dataset_mode_set(MS, "parquet", by="avo")
    _staged_check(2.0, monkeypatch)
    assert _one(due.enqueue_due())[2] is None and _queued() == [], "a fresh stage waits for its ordinary build"
    monkeypatch.setattr(ops, "run_started_at", lambda run_id: WED_EVENING.timestamp() - 30 * 3600.0)
    name, why, rid, error = _one(due.enqueue_due())
    assert rid is not None and not error, why
    assert "gap ceiling" in why
    assert _queued() == [(MS, {"build_only": True})], "the build of what was staged, at no provider call"


def test_the_fetch_pass_stages_on_over_an_overdue_stage(one_source, monkeypatch):
    """avo, 28 Nov 2026: "fetch her zaman devam etmeli build acik olmasa bile" -- with the build timer off, the fetch
    pass still fetches; it used to leave an overdue dataset alone, so no new data came in until a build ran."""
    _staged_check(30.0, monkeypatch)
    assert due.stage_overdue(ops.latest_check(MS)) is not None
    assert due._pass_mode(one_source, "full", "fetch") == ("parquet", None)
    assert due._pass_mode(one_source, "parquet", "fetch") == ("parquet", None)


def test_a_newer_stage_does_not_make_the_waiting_data_look_young(one_source, monkeypatch):
    """The fetch pass stages on, so the ceiling ages the first stage since the last build, not the newest."""
    ops.record_check(MS, "changed", run_id="built", source_as_of="2026-11-20")
    ops.record_check(MS, "skipped", note=base.NO_DUCKDB_NOTE, run_id="old", source_as_of="2026-11-23")
    ops.record_check(MS, "skipped", note="skipped: paused", run_id="pause", source_as_of="2026-11-24")
    ops.record_check(MS, "failed", note="a fetch that failed builds nothing", run_id="pause", source_as_of="2026-11-24")
    ops.record_check(MS, "skipped", note=base.NO_DUCKDB_NOTE, run_id="new", source_as_of=AS_OF.isoformat())
    started = {"old": 50.0, "pause": 20.0, "new": 1.0, "built": 120.0}
    monkeypatch.setattr(ops, "run_started_at", lambda run_id: WED_EVENING.timestamp() - started[run_id] * 3600.0)
    assert due.stage_overdue(ops.latest_check(MS)) == pytest.approx(50.0)
    ops.record_check(MS, "changed", run_id="built", source_as_of=AS_OF.isoformat())
    ops.record_check(MS, "skipped", note=base.NO_DUCKDB_NOTE, run_id="new", source_as_of=AS_OF.isoformat())
    assert due.stage_overdue(ops.latest_check(MS)) is None, "a build ends the wait"


def test_the_build_pass_takes_an_overdue_raw_only_stage_too(one_source, monkeypatch):
    ops.dataset_mode_set(MS, "raw", by="avo")
    _staged_check(40.0, monkeypatch, note=base.NO_PARQUET_NOTE)
    name, why, rid, error = _one(due.enqueue_due(stage="build"))
    assert rid is not None and not error, why
    assert _queued() == [(MS, {"build_only": True})]


def test_an_off_source_is_left_to_avos_own_hand(one_source, monkeypatch):
    """``off`` is avo's word that this source is built by hand; the ceiling does not overrule a switch."""
    ops.dataset_mode_set(MS, "off", by="avo")
    _staged_check(90.0, monkeypatch)
    name, why, rid, error = _one(due.enqueue_due())
    assert rid is None and "automation off" in why and _queued() == []


def test_a_stage_whose_run_row_is_gone_is_aged_by_its_own_day(one_source):
    ops.record_check(MS, "skipped", note=base.NO_DUCKDB_NOTE, checked_on="2026-11-20", run_id=None)
    assert due.stage_age_h(ops.latest_check(MS)) >= 24.0


# ── Q4: no build beside a heavy fetch ─────────────────────────────────────────────────────────────────────────
class Fake:
    """A dataset that sends no call (the fake of ``test_build_heavy_812``); only its flags are read here."""
    providers: tuple[str, ...] = ()

    def __init__(self, name: str, *, heavy: bool = False):
        self.name, self.kind, self.heavy = name, "market", heavy
        self.tables = (f"t_{name.replace('/', '_')}",)

    def default_as_of(self) -> date:
        return AS_OF


@pytest.fixture
def two_datasets(monkeypatch):
    monkeypatch.setattr(build_pkg, "DATASETS", {"m/heavy": Fake("m/heavy", heavy=True), "m/plain": Fake("m/plain")})


def test_a_heavy_datasets_fetch_lock_holds_the_build_turn_off(two_datasets):
    assert base.idle_problem() is None
    with job_lock.acquire(base.fetch_lock_name("m/heavy"), wait=0) as got:
        assert got
        problem = base.idle_problem()
        assert problem and "heavy" in problem and "m/heavy" in problem
    assert base.idle_problem() is None, "the turn is free again once the fetch ends"


def test_a_light_datasets_fetch_runs_beside_a_build(two_datasets):
    """What makes the split worth having: a light fetch-only run and a build do go side by side."""
    with job_lock.acquire(base.fetch_lock_name("m/plain"), wait=0) as got:
        assert got and base.idle_problem() is None


def test_another_locks_turn_is_not_held_off_by_a_heavy_fetch(two_datasets):
    """The condition is the builder's: a heavy fetch is a memory neighbour, not a writer of anyone's file."""
    with job_lock.acquire(base.fetch_lock_name("m/heavy"), wait=0) as got:
        assert got and base.idle_problem("relatedness") is None
