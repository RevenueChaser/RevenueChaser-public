"""``rcdata/build/dirty.py``: what changed in Parquet since the live file was built (#446 step 2).

Nothing builds on this yet: a dataset that declares no ``dirty`` is wholly dirty, so every kind is still built
whole. These tests pin the contract the incremental steps (3 onwards) will read.
"""
from __future__ import annotations

import os
import sys
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from RevenueChaser.rcdata import serving
from RevenueChaser.rcdata.build import audit, base, dirty


class _Ds:
    """A dataset as ``dirty`` sees one: a name, and optionally its own declarations."""

    def __init__(self, name: str, **declared):
        self.name = name
        for key, value in declared.items():
            setattr(self, key, value)


def _build(kind: str = "market", rows: int = 3) -> None:
    with serving.build(kind) as b:
        b.con.execute("CREATE TABLE t (i INTEGER)")
        b.con.execute(f"INSERT INTO t SELECT range FROM range({rows})")
        b.swap({"t": rows})


def _partition(name: str, mtime: float | None = None) -> Path:
    path = base.parquet_root() / "src" / "ds" / "year=2026" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"not really parquet")
    if mtime is not None:
        os.utime(path, (mtime, mtime))
    return path


# ── a dataset's dirty set ─────────────────────────────────────────────────────────────────────────────────────

def test_a_dataset_that_declares_nothing_is_wholly_dirty():
    assert dirty.of(_Ds("sec/ftd"), None) is dirty.ALL


def test_a_dataset_that_declares_dirty_is_asked():
    ds = _Ds("sec/ftd", dirty=lambda ctx: dirty.Dirty(keys=frozenset({"AAPL"})))
    answer = dirty.of(ds, None)
    assert answer.keys == {"AAPL"} and answer.all is False


def test_a_dirty_set_narrows_by_day_range_too():
    """A cumulative table's dirty set is a range of days; a restated table's is a key (the two axes)."""
    days = ((date(2026, 11, 1), date(2026, 11, 5)),)
    ds = _Ds("alpaca/bars", dirty=lambda ctx: dirty.Dirty(ranges=days))
    answer = dirty.of(ds, None)
    assert answer.ranges == days and answer.keys == frozenset() and answer.all is False


def test_a_dataset_that_answers_none_is_wholly_dirty():
    assert dirty.of(_Ds("sec/ftd", dirty=lambda ctx: None), None) is dirty.ALL


def test_a_dataset_that_answers_the_wrong_shape_raises():
    """A bare set read as a narrowing would serve a partial table, so it is a mistake, not a dirty set."""
    with pytest.raises(TypeError, match="not a Dirty"):
        dirty.of(_Ds("sec/ftd", dirty=lambda ctx: {"AAPL"}), None)


def test_everything_is_dirty_when_neither_axis_is_narrowed():
    assert dirty.ALL.all is True and dirty.Dirty().all is True


# ── changed partitions ────────────────────────────────────────────────────────────────────────────────────────

def test_changed_partitions_names_only_the_files_written_after_the_cutoff():
    now = time.time()
    old = _partition("old.parquet", now - 600)
    new = _partition("new.parquet", now + 600)
    assert dirty.changed_partitions(now) == [new]
    assert sorted(dirty.changed_partitions(None)) == sorted([new, old]), "no cutoff: every partition is dirty"


def test_changed_partitions_can_be_narrowed_to_one_subtree():
    now = time.time()
    mine = _partition("mine.parquet", now + 600)
    other = base.parquet_root() / "elsewhere" / "part-0.parquet"
    other.parent.mkdir(parents=True, exist_ok=True)
    other.write_bytes(b"x")
    os.utime(other, (now + 600, now + 600))
    assert dirty.changed_partitions(now, under=mine.parent.parent.parent) == [mine]


def test_changed_partitions_of_a_missing_parquet_root_is_empty():
    assert dirty.changed_partitions(None, under=base.parquet_root() / "never-written") == []


# ── the live file's build stamp ────────────────────────────────────────────────────────────────────────────────

def test_live_built_at_is_none_until_a_build_has_been_swapped_in():
    assert dirty.live_built_at("market") is None
    _build()
    assert dirty.live_built_at("market") == pytest.approx(time.time(), abs=120)


def test_the_build_stamp_is_the_builds_start_not_its_swap():
    """A partition written while a build runs must come out dirty next time (the long build's race)."""
    with serving.build("market") as b:
        b.con.execute("CREATE TABLE t (i INTEGER)")
        b.con.execute("INSERT INTO t VALUES (1)")
        written = _partition("during-the-build.parquet")
        b.swap({"t": 1})
    built_at = dirty.live_built_at("market")
    assert built_at is not None
    assert built_at <= os.path.getmtime(written), "the stamp must precede what the build read"
    assert dirty.changed_partitions(built_at) == [written]


# ── when a whole rebuild is the only safe build ────────────────────────────────────────────────────────────────

def test_a_kind_with_no_live_file_needs_a_whole_rebuild():
    why = dirty.full_rebuild_reason("market", datasets=())
    assert why and "serving schema version" in why


def test_a_live_file_of_another_serving_version_needs_a_whole_rebuild(monkeypatch):
    _build()
    monkeypatch.setitem(serving.SERVING_SCHEMA_VERSION, "market",
                        serving.SERVING_SCHEMA_VERSION["market"] + 1)
    assert dirty.full_rebuild_reason("market", datasets=())


# ── #649: a version bump rebuilds only its own kind ─────────────────────────────────────────────────────────────

def _fingerprints_with_edit(monkeypatch, edited: Path) -> tuple[dict, dict]:
    """Every kind's rules fingerprint as the code is, and again with ``edited``'s bytes changed."""
    def all_kinds() -> dict:
        return {k: dirty.rules_fingerprint(base.kind_datasets(k)) for k in serving.KINDS}
    before = all_kinds()
    real = Path.read_bytes
    target = edited.resolve()
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self: real(self) + (b"\n# edited\n" if self.resolve() == target else b""))
    return before, all_kinds()


def test_a_version_bump_leaves_every_kinds_rules_fingerprint_unchanged(monkeypatch):
    from RevenueChaser.rcdata import serving_versions
    assert serving.SERVING_SCHEMA_VERSION is serving_versions.SERVING_SCHEMA_VERSION
    before, after = _fingerprints_with_edit(monkeypatch, Path(serving_versions.__file__))
    assert before == after


def test_an_edit_to_the_serving_base_or_dirty_code_changes_every_kinds_rules_fingerprint(monkeypatch):
    for module in (serving, base, dirty):
        before, after = _fingerprints_with_edit(monkeypatch, Path(module.__file__))
        monkeypatch.undo()
        assert all(before[k] != after[k] for k in serving.KINDS), module.__name__


def test_a_version_bump_makes_only_its_own_kind_whole(monkeypatch):
    from RevenueChaser.rcdata import serving_versions        # where a bump is now made
    _build("market")
    _build("spine")
    versions = serving_versions.SERVING_SCHEMA_VERSION
    monkeypatch.setitem(versions, "market", versions["market"] + 1)
    assert dirty.full_rebuild_reason("market", datasets=())
    assert dirty.full_rebuild_reason("spine", datasets=()) is None


def test_a_current_live_file_needs_no_whole_rebuild():
    _build()
    assert dirty.full_rebuild_reason("market", datasets=()) is None


def test_a_dataset_may_ask_for_a_whole_rebuild():
    _build()
    quiet = _Ds("sec/ftd")
    loud = _Ds("wrds/prices", full_rebuild_reason=lambda ctx: "the source restated its history")
    why = dirty.full_rebuild_reason("market", datasets=(quiet, loud))
    assert why == "wrds/prices: the source restated its history"


def test_a_dataset_that_asks_for_nothing_leaves_the_build_incremental():
    _build()
    ds = _Ds("sec/ftd", full_rebuild_reason=lambda ctx: None)
    assert dirty.full_rebuild_reason("market", datasets=(ds,)) is None


# ── the mtime shortcut's two known gaps, red until the manifest lands ──────────────────────────────────────────

@pytest.mark.xfail(reason="mtime signal: a copy carries the old mtime over; the (path, size, mtime) manifest "
                          "catches it (#446, before step 3)", strict=True)
def test_a_partition_copied_in_with_its_old_mtime_is_dirty():
    _build()
    built_at = dirty.live_built_at("market")
    copied = _partition("from-another-machine.parquet", built_at - 3600)   # as cp -p / rsync -t leaves it
    assert copied in dirty.changed_partitions(built_at)


@pytest.mark.xfail(reason="mtime signal: a deleted partition leaves its rows in the live file with nothing to "
                          "mark them; the manifest's 'in the manifest, not on disk' branch catches it "
                          "(#446, before step 3)", strict=True)
def test_a_partition_deleted_after_the_build_is_dirty():
    old = _partition("went-away.parquet", time.time() - 600)
    _build()
    built_at = dirty.live_built_at("market")
    old.unlink()
    assert dirty.changed_partitions(built_at), "the kind still serves rows no partition backs any more"


@pytest.mark.parametrize("name, sibling", [("alpaca/bars", "alpaca/bars_revision"),
                                           ("sec/cover_shares", "sec/cover_shares_dei"),
                                           ("openfigi/map", "openfigi/map_ticker"),
                                           ("prices/serving", "cboe/index"),
                                           ("spine/security", "sec/nport"),
                                           ("spine/security", "sec/filings"),
                                           ("ownership/serve", "wrds/sec_idhist"),
                                           ("ownership/serve", "openfigi/map")])
def test_read_dirs_names_the_sibling_folder_a_build_reads(name, sibling):
    """price_revision, stg_sec_dei and stg_figi_ticker come from a folder beside the dataset's own: a build packed or
    tracked by read_dirs alone lost them (rc-rebuild, 17 Nov 2026: price_revision 17472 -> 1551 rows)."""
    from RevenueChaser.rcdata.build import DATASETS
    assert base.parquet_root().joinpath(*sibling.split("/")) in dirty.read_dirs(DATASETS[name])


# ── one fingerprint per dataset, not one per kind (#814) ───────────────────────────────────────────────────────

def _of(kind: str, name: str):
    return next(d for d in base.kind_datasets(kind) if d.name == name)


def _module_path(ds) -> Path:
    return Path(sys.modules[type(ds).__module__].__file__).resolve()


def _homes(ds) -> set[Path]:
    return {Path(sys.modules[name].__file__).resolve() for name in dirty.home_modules(ds)}


def _with_edit(monkeypatch, edited: Path, measure):
    """``measure()`` as the code is, and again with ``edited``'s bytes changed (a comment: it still parses)."""
    before = measure()
    real = Path.read_bytes
    target = edited.resolve()
    monkeypatch.setattr(Path, "read_bytes",
                        lambda self: real(self) + (b"\n# edited\n" if self.resolve() == target else b""))
    return before, measure()


def test_a_dataset_answers_for_the_files_of_its_own_package_its_code_reaches():
    """The #814 case: an edit to ``ownership/regsho`` restated ``ownership/serve``'s ten 13F tables — 2,352 s and
    a 23.8 GB spill on homesrv, 12 Nov 2026 — because the fingerprint was one per kind."""
    serve, regsho = _of("ownership", "ownership/serve"), _of("ownership", "regsho/threshold")
    served = {p.name for p in dirty.code_files(serve)}
    assert {"serve.py", "common.py", "sec13f.py"} <= served
    assert served.isdisjoint({"regsho.py", "finra.py", "ftd.py", "ibkr.py", "form4.py", "nport.py"})
    reached = {p.name for p in dirty.code_files(regsho)}
    assert "regsho.py" in reached and "serve.py" not in reached


def test_a_dataset_answers_for_no_file_outside_its_own_package():
    """The package is the boundary a kind's fingerprint had, and this narrows it; it never widens it."""
    for kind in serving.KINDS:
        for d in base.kind_datasets(kind):
            folders = {p.parent for p in _homes(d)}
            assert {p.parent for p in dirty.code_files(d)} <= folders, d.name


def test_every_dataset_answers_for_the_module_it_lives_in_and_the_one_its_class_is_in():
    """``spine/wrds`` defines one class several datasets are built from, and each lives in a module of its own
    whose constants are as much its rules as the class is."""
    for kind in serving.KINDS:
        for d in base.kind_datasets(kind):
            files = set(dirty.code_files(d))
            assert _module_path(d) in files, d.name
            assert _homes(d) <= files, d.name


def test_an_edit_to_a_file_a_dataset_does_not_reach_leaves_its_fingerprint_alone(monkeypatch):
    serve = _of("ownership", "ownership/serve")
    unreached = _module_path(_of("ownership", "regsho/threshold"))
    before, after = _with_edit(monkeypatch, unreached, lambda: dirty.dataset_fingerprint(serve))
    assert before == after


def test_an_edit_to_a_file_a_dataset_does_reach_changes_its_fingerprint(monkeypatch):
    serve = _of("ownership", "ownership/serve")
    reached = _module_path(serve).parent / "common.py"
    before, after = _with_edit(monkeypatch, reached, lambda: dirty.dataset_fingerprint(serve))
    assert before != after


def test_an_edit_to_the_shared_build_code_changes_the_shared_fingerprint(monkeypatch):
    """What every kind's rows depend on stays one fingerprint, and a change to it is still a whole build."""
    import RevenueChaser.rcdata.build as build_pkg
    for module in (serving, base, dirty, build_pkg):
        before, after = _with_edit(monkeypatch, Path(module.__file__), dirty.shared_fingerprint)
        monkeypatch.undo()
        assert before != after, module.__name__


def test_the_fingerprints_are_the_shared_one_and_one_per_dataset():
    datasets = base.kind_datasets("ownership")
    out = dirty.fingerprints(datasets)
    assert set(out) == {dirty.SHARED} | {d.name for d in datasets}
    assert out[dirty.SHARED] == dirty.shared_fingerprint()
    # Two datasets may share a fingerprint when they share their code: a change to it restates both, which is the
    # answer. What may never happen is a dataset with no module of its own in the package, because that one falls
    # back to every build file and is restated by every deploy.
    for kind in serving.KINDS:
        for d in base.kind_datasets(kind):
            assert dirty.home_modules(d), d.name


# ── what the plan does with a dataset whose code changed ───────────────────────────────────────────────────────

def _plan_ctx():
    return SimpleNamespace(changed=None, dataset="test/one", notes=[])


def _put_rules(kind: str, rows: dict[str, str]) -> None:
    con = duckdb.connect(str(serving.live_path(kind)))
    try:
        con.execute(f"CREATE OR REPLACE TABLE {dirty.RULES_TABLE} (dataset TEXT, fingerprint TEXT)")
        for name, value in rows.items():
            con.execute(f"INSERT INTO {dirty.RULES_TABLE} VALUES (?, ?)", (name, value))
    finally:
        con.close()


def _two(**extra) -> list:
    one = _Ds("test/one", dirty=lambda ctx: dirty.Dirty(keys=frozenset({"A"})), **extra)
    two = _Ds("test/two", dirty=lambda ctx: dirty.Dirty(keys=frozenset({"B"})))
    return [one, two]


def test_a_dataset_whose_own_code_changed_is_restated_and_the_kind_is_not_built_whole():
    _build()
    datasets = _two()
    held = dirty.fingerprints(datasets)
    _put_rules("market", {**held, "test/one": "the code of a deploy ago"})
    plan = dirty.plan("market", _plan_ctx(), datasets)
    assert plan.reason is None, plan.reason
    assert plan.recoded == ("test/one",)
    assert plan.dirty["test/one"].all is True
    assert plan.dirty["test/two"].keys == {"B"}, "the rest of the kind keeps its dirty set"
    assert "restated for new build code: test/one" in plan.note()


def test_a_change_to_the_shared_build_code_is_still_a_whole_build():
    _build()
    datasets = _two()
    _put_rules("market", {**dirty.fingerprints(datasets), dirty.SHARED: "the shared code of a deploy ago"})
    plan = dirty.plan("market", _plan_ctx(), datasets)
    assert plan.reason and "shared build code" in plan.reason
    assert plan.recoded == () and plan.dirty == {}


def test_no_build_code_changed_leaves_every_dataset_its_own_dirty_set():
    _build()
    datasets = _two()
    _put_rules("market", dirty.fingerprints(datasets))
    plan = dirty.plan("market", _plan_ctx(), datasets)
    assert plan.reason is None and plan.recoded == ()
    assert plan.dirty["test/one"].keys == {"A"} and plan.dirty["test/two"].keys == {"B"}


def test_a_keyed_dataset_is_restated_by_its_own_code_change_but_still_bails_on_an_unknown_one():
    """``dirty_keyed`` guards against a keyed dataset that cannot say what changed, which is no answer. A code
    change is an answer — everything of that dataset — and its build reloads its tables from the partitions."""
    _build()
    datasets = _two(dirty_keyed=True)
    _put_rules("market", {**dirty.fingerprints(datasets), "test/one": "the code of a deploy ago"})
    assert dirty.plan("market", _plan_ctx(), datasets).reason is None

    unknown = [_Ds("test/one", dirty=lambda ctx: dirty.ALL, dirty_keyed=True),
               _Ds("test/two", dirty=lambda ctx: dirty.Dirty(keys=frozenset({"B"})))]
    _put_rules("market", dirty.fingerprints(unknown))
    why = dirty.plan("market", _plan_ctx(), unknown).reason
    assert why and "no narrower dirty set" in why


def test_a_live_file_from_before_the_per_dataset_fingerprints_is_trusted_once():
    """It carries the one-column table of its day; reading that as a changed dataset would rebuild every kind
    whole on the deploy that lands this."""
    _build()
    datasets = _two()
    con = duckdb.connect(str(serving.live_path("market")))
    try:
        con.execute(f"CREATE OR REPLACE TABLE {dirty.RULES_TABLE} (fingerprint TEXT)")
        con.execute(f"INSERT INTO {dirty.RULES_TABLE} VALUES ('one hash for the whole kind')")
    finally:
        con.close()
    assert dirty.live_rules("market") is None
    plan = dirty.plan("market", _plan_ctx(), datasets)
    assert plan.reason is None and plan.recoded == ()


# ── the keys an audit found a difference for (#446 step 5) ─────────────────────────────────────────────────────

def _put_audit_dirty(kind: str, table: str, keys: list[str]) -> None:
    con = duckdb.connect(str(serving.live_path(kind)))
    try:
        audit.ensure_tables(con)
        con.execute(f'INSERT INTO {audit.DIRTY} SELECT ?, unnest(?::TEXT[]), 1.0', (table, keys))
    finally:
        con.close()


def test_the_plan_hands_a_dataset_the_keys_an_audit_found_a_difference_for():
    """The dataset adds them in its own key space: ``market_series``' dirty keys are ``<source>/<year>``, not the
    ``series_id`` its audit subject reads, so the plan hands them over instead of merging them itself."""
    _build()
    seen: dict[str, dict] = {}

    def reads_them(ctx):
        seen["audited"] = ctx.audited
        return dirty.CLEAN

    datasets = [_Ds("test/one", tables=("t",), dirty=reads_them),
                _Ds("test/two", tables=("other",), dirty=lambda ctx: dirty.CLEAN)]
    _put_audit_dirty("market", "t", ["AAPL", "MSFT"])
    _put_rules("market", dirty.fingerprints(datasets))
    plan = dirty.plan("market", _plan_ctx(), datasets)
    assert plan.reason is None
    assert plan.audited["test/one"] == {"AAPL", "MSFT"}
    assert plan.audited["test/two"] == frozenset(), "another dataset's table is not its business"
    assert seen["audited"]["test/one"] == {"AAPL", "MSFT"}, "a dataset's own dirty can read them"
    assert plan.dirty["test/one"] is dirty.CLEAN, "the plan hands the keys over, it does not widen the set itself"


def test_a_live_file_with_no_audit_behind_it_hands_over_nothing():
    _build()
    datasets = [_Ds("test/one", tables=("t",), dirty=lambda ctx: dirty.CLEAN)]
    _put_rules("market", dirty.fingerprints(datasets))
    plan = dirty.plan("market", _plan_ctx(), datasets)
    assert plan.audited == {"test/one": frozenset()}


def test_a_wholly_dirty_dataset_still_gets_the_keys_and_its_set_stays_all():
    """Handing the keys over costs nothing when the dataset is rebuilt whole anyway, and the set is untouched."""
    _build()
    datasets = [_Ds("test/one", tables=("t",), dirty=lambda ctx: dirty.ALL)]
    _put_audit_dirty("market", "t", ["AAPL"])
    _put_rules("market", dirty.fingerprints(datasets))
    plan = dirty.plan("market", _plan_ctx(), datasets)
    assert plan.audited["test/one"] == {"AAPL"}
    assert plan.dirty["test/one"].all is True and plan.dirty["test/one"].keys == frozenset()
