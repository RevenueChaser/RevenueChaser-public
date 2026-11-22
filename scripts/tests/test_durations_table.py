"""scripts/durations.py and the table it writes: the unit shards' measured times (#1153).

The table is what ``select_tests.in_shard`` places a file by, so three things about it are worth failing a run
over: it names files that are still in the tree, it covers nearly all of them, and no one file in it is long
enough to set the whole tier's floor on its own -- ``--dist loadfile`` gives a file to one worker, so a file
longer than a shard's per-worker share leaves the other three idle however evenly the shards are balanced.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from revenuechaser.scripts import durations as mod

_REPO = Path(__file__).resolve().parents[2]


def _table() -> dict[str, float]:
    return json.loads(mod.TABLE.read_text(encoding="utf-8"))


def _tracked_unit_files() -> set[str]:
    out = set()
    for p in _REPO.rglob("test_*.py"):
        rel = p.relative_to(_REPO).as_posix()
        if {".git", ".cache", ".store", "node_modules"} & set(p.parts) or "/e2e/" in f"/{rel}":
            continue
        out.add(rel)
    return out


def test_the_table_names_only_files_that_are_in_the_tree():
    """A stale entry holds a shard's place for a file that will never run there (two were, before #1153)."""
    gone = sorted(rel for rel in _table() if not (_REPO / rel).is_file())
    assert not gone, gone


def test_the_table_covers_nearly_every_unit_test_file():
    """Hand-built from one run, it named 274 of 873 files -- 60 % of the tier's time was placed by hash."""
    tracked = _tracked_unit_files()
    missing = tracked - set(_table())
    assert len(missing) <= len(tracked) // 10, f"{len(missing)} of {len(tracked)} unmeasured: {sorted(missing)[:10]}"


def test_no_measured_file_is_long_enough_to_set_the_unit_tiers_floor():
    """Measured 19 Nov 2026: ``test_ownership_serve.py`` alone was 2.09 shares, and the tier's walls 4.0-8.0 min."""
    table = _table()
    share = mod.heaviest_share(table)
    longest = max(table, key=table.get)
    assert share <= mod.MAX_FILE_SHARE, f"{longest} is {share:.2f} of a shard's per-worker share ({table[longest]} s)"


def test_the_class_suffix_of_a_junit_classname_is_not_part_of_the_file():
    assert mod.path_of("rcdata.tests.test_ownership_serve") == "rcdata/tests/test_ownership_serve.py"
    assert mod.path_of("app.tests.test_routes.TestWhenTheHeaderIsMissing") == "app/tests/test_routes.py"
    assert mod.path_of("conftest") is None


def test_a_files_seconds_are_its_tests_summed():
    xml = """<testsuites><testsuite>
      <testcase classname="a.tests.test_x" name="one" time="1.5"/>
      <testcase classname="a.tests.test_x.Klass" name="two" time="0.25"/>
      <testcase classname="a.tests.test_y" name="three" time="2"/>
      <testcase classname="broken" name="four" time="9"/>
    </testsuite></testsuites>"""
    assert mod.file_seconds(xml) == {"a/tests/test_x.py": 1.75, "a/tests/test_y.py": 2.0}


def test_a_file_one_run_skipped_is_averaged_over_the_runs_that_ran_it():
    """A SELECTIVE shard, or a test added between the runs, must not halve the file's time."""
    tables = [{"a.py": 10.0, "b.py": 4.0}, {"a.py": 20.0}]
    assert mod.merge(tables, exists=lambda rel: True) == {"a.py": 15.0, "b.py": 4.0}


def test_a_file_no_longer_in_the_tree_is_dropped():
    assert mod.merge([{"gone/test_x.py": 5.0}]) == {}


def test_the_heaviest_share_is_the_longest_file_over_a_shards_worker():
    """24 workers in all (6 shards x 4), so a file at a 24th of the tier's time exactly fills one."""
    table = {f"f{i}.py": 10.0 for i in range(24)}
    assert mod.heaviest_share(table) == pytest.approx(1.0)
    assert mod.heaviest_share({}) == 0.0
