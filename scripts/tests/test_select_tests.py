"""scripts/select_tests.py: which tests a PR's changed files can reach, or FULL when that is not safe to say.

The selection follows imports (direct and transitive, top-level or inside a function, and module names
written as strings: the e2e dashboard subprocess and the import_module registries). Every case that cannot
be answered from that graph runs the full suite.
"""
from __future__ import annotations

import ast
import os
import re
import subprocess
from pathlib import Path

import pytest

from RevenueChaser.scripts import select_tests as mod

_REPO = Path(__file__).resolve().parents[2]


def _runs(sel, test: str) -> bool:
    return sel.mode == "FULL" or test in sel.unit


def test_rcdata_ops_reaches_the_e2e_tests_that_broke_on_pr_381():
    """PR #381 changed rcdata/ops.py and these three e2e tests failed; none of them imports ops directly."""
    reached = mod.reached_tests(["rcdata/ops.py"])
    for name in ("test_settings_newdata.py", "test_spx_gamma_rcdata.py", "test_watchlist_pair.py"):
        assert f"module_testing/e2e/{name}" in reached, name
    assert mod.select(["rcdata/ops.py"]).mode == "FULL"  # the root conftest imports ops


def test_an_e2e_test_that_reaches_the_app_only_through_the_dashboard_fixture_is_selected():
    """test_board_oipd imports opd_math only; the board code runs in the dashboard the e2e conftest starts."""
    sel = mod.select(["module_oipd/report.py"])
    assert _runs(sel, "module_testing/e2e/test_board_oipd.py"), sel.reason
    assert "module_testing/e2e/test_board_oipd.py" in sel.e2e or sel.mode == "FULL"


def test_a_change_reaching_a_conftest_selects_every_test_below_it(tmp_path):
    root = _mini_repo(tmp_path, {
        "pkg/__init__.py": "", "pkg/fix.py": "", "pkg/other.py": "",
        "pkg/tests/conftest.py": "from RevenueChaser.pkg import fix\n",
        "pkg/tests/test_x.py": "", "pkg/tests/deep/test_y.py": "from RevenueChaser.pkg import other\n",
        "pkg2/tests/test_z.py": "",
    })
    sel = mod.select(["pkg/fix.py"], root=root)
    assert (sel.mode, sel.unit) == ("SELECTIVE", ["pkg/tests/deep/test_y.py", "pkg/tests/test_x.py"])


def test_a_change_reaching_the_root_conftest_runs_the_full_suite(tmp_path):
    root = _mini_repo(tmp_path, {
        "conftest.py": "def f():\n    from RevenueChaser.pkg import a\n",
        "pkg/__init__.py": "", "pkg/a.py": "", "pkg/tests/test_a.py": "from RevenueChaser.pkg import a\n",
    })
    assert mod.select(["pkg/a.py"], root=root).mode == "FULL"


def test_a_narrow_change_runs_fewer_tests_than_the_full_suite():
    sel = mod.select(["module_relatedness/naming.py"])
    assert sel.mode == "SELECTIVE", sel.reason
    assert "module_relatedness/tests/test_naming.py" in sel.unit
    assert len(sel.unit) < len(mod.all_tests(_REPO)) / 10


@pytest.mark.parametrize("doc, reader", [
    ("docs/data_retrieval.md", "core/tests/test_doc_constants.py"),
    ("docs/rules/00_overview.md", "module_earnings_radar/tests/test_confidence_wording_df06.py"),
    ("docs/rules/redesign.md", "module_earnings_radar/tests/test_cleanup_199.py"),
    ("docs/data_architecture.md", "core/tests/test_store_schema_refuse.py"),
])
def test_a_doc_a_test_reads_selects_that_test(doc, reader):
    assert _runs(mod.select([doc]), reader)


def test_a_markdown_file_nothing_reads_selects_nothing(tmp_path):
    root = _mini_repo(tmp_path, {"pkg/a.py": "", "pkg/tests/test_a.py": "", "docs/notes.md": "x", "pkg/notes.md": "y"})
    sel = mod.select(["docs/notes.md"], root=root)
    assert (sel.mode, sel.unit, sel.e2e) == ("SELECTIVE", [], [])


@pytest.mark.parametrize("path", [
    "conftest.py", "module_testing/e2e/conftest.py", "requirements.txt", "pytest.ini",
    ".github/workflows/tests.yml", "scripts/select_tests.py",
    "rcdata/tests/fixtures/cftc_tff.json", "module_testing/e2e/harness/provider_fixtures/unusual_whales/option_trades.json",
])
def test_shared_config_and_fixtures_run_the_full_suite(path):
    assert mod.select([path]).mode == "FULL"


def test_a_deleted_module_runs_the_full_suite(tmp_path):
    """Its importers are not in the graph any more, so the tests that still import it cannot be found."""
    root = _mini_repo(tmp_path, {
        "pkg/__init__.py": "", "pkg/a.py": "", "pkg/tests/test_a.py": "from RevenueChaser.pkg import a\n",
        "pkg/tests/test_gone.py": "from RevenueChaser.pkg import gone\n",
    })
    assert mod.select(["pkg/gone.py", "pkg/a.py"], root=root).mode == "FULL"


def test_a_data_file_maps_to_the_tests_reaching_a_module_that_names_it(tmp_path):
    root = _mini_repo(tmp_path, {
        "pkg/__init__.py": "", "pkg/a.py": 'PATH = "data/table.csv"\n',
        "pkg/tests/test_a.py": "from RevenueChaser.pkg import a\n",
        "pkg/data/table.csv": "x\n", "pkg/data/orphan.csv": "x\n",
        "templates/base.html": "", "templates/page.html": '{% extends "base.html" %}',
        "pkg/b.py": 'PAGE = "page.html"\n', "pkg/tests/test_b.py": "from RevenueChaser.pkg import b\n",
    })
    assert mod.select(["pkg/data/table.csv"], root=root).unit == ["pkg/tests/test_a.py"]
    assert mod.select(["templates/base.html"], root=root).unit == ["pkg/tests/test_b.py"]
    assert mod.select(["pkg/data/orphan.csv"], root=root).mode == "FULL"


def test_a_basename_matches_only_as_a_whole_file_name(tmp_path):
    """Review of #383: a substring match let "a.js" be named by "data.json"."""
    root = _mini_repo(tmp_path, {
        "pkg/__init__.py": "", "pkg/b.py": 'P = "data.json"\n', "pkg/tests/test_b.py": "from RevenueChaser.pkg import b\n",
        "static/a.js": "", "pkg/data.json": "{}",
    })
    assert mod.select(["static/a.js"], root=root).mode == "FULL"
    assert mod.select(["pkg/data.json"], root=root).unit == ["pkg/tests/test_b.py"]


def test_a_basename_two_files_share_runs_the_full_suite(tmp_path):
    """Which of the two a Python file reads cannot be told from the name."""
    root = _mini_repo(tmp_path, {
        "pkg/__init__.py": "", "pkg/b.py": 'P = "index.html"\n', "pkg/tests/test_b.py": "from RevenueChaser.pkg import b\n",
        "one/index.html": "", "two/index.html": "",
    })
    assert mod.select(["one/index.html"], root=root).mode == "FULL"


def test_two_binary_files_with_one_name_run_the_full_suite(tmp_path):
    root = _mini_repo(tmp_path, {
        "pkg/__init__.py": "", "pkg/b.py": 'P = "logo.png"\n', "pkg/tests/test_b.py": "from RevenueChaser.pkg import b\n",
    })
    for d in ("one", "two"):
        (root / d).mkdir()
        (root / d / "logo.png").write_bytes(b"\x89PNG\xff\xfe")
    assert mod.select(["one/logo.png"], root=root).mode == "FULL"


def _mini_repo(tmp_path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def test_code_no_test_reaches_runs_the_full_suite(tmp_path):
    root = _mini_repo(tmp_path, {
        "pkg/__init__.py": "", "pkg/a.py": "", "pkg/lonely.py": "",
        "pkg/tests/__init__.py": "", "pkg/tests/test_a.py": "from RevenueChaser.pkg import a\n",
    })
    assert mod.select(["pkg/a.py"], root=root).unit == ["pkg/tests/test_a.py"]
    assert mod.select(["pkg/lonely.py"], root=root).mode == "FULL"
    # Per changed file (review of #383): a tested file beside it does not hide it.
    assert mod.select(["pkg/a.py", "pkg/lonely.py"], root=root).mode == "FULL"


def test_a_file_that_does_not_parse_runs_the_full_suite(tmp_path):
    root = _mini_repo(tmp_path, {
        "pkg/__init__.py": "", "pkg/a.py": "def (:\n",
        "pkg/tests/test_a.py": "from RevenueChaser.pkg import a\n",
    })
    assert mod.select(["pkg/a.py"], root=root).mode == "FULL"
    assert mod.select(["pkg/tests/test_a.py"], root=root).mode == "FULL"


def test_importing_a_submodule_runs_its_packages(tmp_path):
    root = _mini_repo(tmp_path, {
        "pkg/__init__.py": "X = 1\n", "pkg/sub/__init__.py": "", "pkg/sub/leaf.py": "",
        "pkg/tests/test_leaf.py": "from RevenueChaser.pkg.sub import leaf\n",
    })
    assert mod.select(["pkg/__init__.py"], root=root).unit == ["pkg/tests/test_leaf.py"]


def test_relative_lazy_and_string_imports_are_edges(tmp_path):
    root = _mini_repo(tmp_path, {
        "pkg/__init__.py": "", "pkg/a.py": "", "pkg/b.py": "", "pkg/c.py": "", "pkg/entry.py": "",
        "pkg/hop.py": "from . import a\n",
        "pkg/tests/__init__.py": "",
        "pkg/tests/test_rel.py": "from .. import hop\n",
        "pkg/tests/test_lazy.py": "def test():\n    from RevenueChaser.pkg import b\n",
        "pkg/tests/test_str.py": 'TARGET = "RevenueChaser.pkg.entry"\nREG = "pkg.c:run"\n',
    })
    assert mod.select(["pkg/a.py"], root=root).unit == ["pkg/tests/test_rel.py"]
    assert mod.select(["pkg/b.py"], root=root).unit == ["pkg/tests/test_lazy.py"]
    assert mod.select(["pkg/entry.py"], root=root).unit == ["pkg/tests/test_str.py"]
    assert mod.select(["pkg/c.py"], root=root).unit == ["pkg/tests/test_str.py"]


def test_every_dynamic_import_outside_tests_names_its_targets_as_string_literals():
    """The string-literal edges cover this registry; a new import_module site must be checked the same way."""
    sites = set()
    for p in _REPO.rglob("*.py"):
        rel = p.relative_to(_REPO).as_posix()
        if {".git", ".store", ".cache"} & set(p.parts) or "/tests/" in f"/{rel}" or p.name == "conftest.py":
            continue
        if re.search(r"\bimport_module\(|__import__\(", p.read_text(encoding="utf-8")):
            sites.add(rel)
    assert sites == {"core/llm_writers.py"}


def test_the_workflow_names_each_run_full_or_selective():
    wf = (_REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    assert "name: unit (${{ needs.plan.outputs.mode }})" in wf
    assert "name: e2e (${{ needs.plan.outputs.mode }})" in wf
    assert "scripts/select_tests.py" in wf
    assert "full-ci" in wf


def test_the_merge_gate_check_is_green_only_for_a_full_run_that_passed():
    """Review of #383: without it every check of an unlabelled PR is green and reads like the gate."""
    wf = (_REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    gate = wf.split("\n  merge-gate:\n", 1)[1]
    assert "needs: [plan, unit, e2e, earlier-gate]" in gate
    # Delta review of #383: a skipped check counts as passed, so the gate runs (and fails) when plan did not succeed.
    # Only a label run with no earlier gate on the head skips it (review 9 Nov 2026, F7).
    assert "\n    if: always() && (needs.earlier-gate.result == 'skipped' || needs.earlier-gate.outputs.last != '')\n" in gate
    script = "\n".join(line[10:] for line in gate.split("run: |\n", 1)[1].splitlines() if line.startswith(" " * 10))
    for (plan, mode, unit, e2e), code in {
        ("success", "FULL", "success", "success"): 0, ("success", "SELECTIVE", "success", "success"): 1,
        ("success", "FULL", "success", "failure"): 1, ("success", "FULL", "cancelled", "success"): 1,
        ("skipped", "", "skipped", "skipped"): 1, ("failure", "", "skipped", "skipped"): 1,
        ("success", "SKIP", "skipped", "skipped"): 0,
    }.items():
        env = {**os.environ, "PLAN": plan, "MODE": mode, "UNIT": unit, "E2E": e2e}
        assert subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True).returncode == code, plan


def _gate_script() -> str:
    wf = (_REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    gate = wf.split("\n  merge-gate:\n", 1)[1]
    return "\n".join(line[10:] for line in gate.split("run: |\n", 1)[1].splitlines() if line.startswith(" " * 10))


@pytest.mark.parametrize("earlier, code", [("success", 0), ("failure", 1), ("cancelled", 1), ("", 1)])
def test_a_label_other_than_full_ci_keeps_the_heads_earlier_gate_result(earlier, code):
    """Review of #383: a triage label after a green FULL run must not turn the head's merge-gate red.

    The run such a label starts tests nothing, so its gate repeats the latest completed merge-gate on the same head,
    which job earlier-gate looks up. With none ("") the gate job is skipped by its ``if`` (review 9 Nov 2026, F7);
    the script itself still fails on "", should it ever run.
    """
    wf = (_REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    lookup = wf.split("\n  earlier-gate:\n", 1)[1].split("\n  merge-gate:\n", 1)[0]
    assert "checks: read" in lookup and "check_name=merge-gate" in lookup and '.conclusion != "skipped"' in lookup
    assert "if: github.event.action == 'labeled' && github.event.label.name != 'full-ci'" in lookup
    env = {**os.environ, "OTHER_LABEL": "true", "last": earlier,
           "PLAN": "skipped", "MODE": "", "UNIT": "skipped", "E2E": "skipped"}
    assert subprocess.run(["bash", "-e", "-c", _gate_script()], env=env, capture_output=True).returncode == code


def test_every_test_file_lands_in_exactly_one_unit_shard():
    """Review 9 Nov 2026, F6: the unit tier runs as 6 jobs; a file in no shard would never run, one in two twice."""
    wf = (_REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    unit = wf.split("\n  unit:\n", 1)[1].split("\n  e2e:\n", 1)[0]
    n = 6
    assert "shard: [0, 1, 2, 3, 4, 5]" in unit and f"RC_SHARD: ${{{{ matrix.shard }}}}/{n}" in unit
    assert "fail-fast: false" in unit and f"${{{{ matrix.shard }}}}/{n}\n" in unit
    files = [p.relative_to(_REPO).as_posix() for p in _REPO.rglob("test_*.py") if ".git" not in p.parts]
    homes = {f: [i for i in range(n) if mod.in_shard(f"{f}::test_x[1]", f"{i}/{n}")] for f in files}
    assert all(len(h) == 1 for h in homes.values())
    assert all(sum(h == [i] for h in homes.values()) > len(files) / (2 * n) for i in range(n)), "a shard far too small"


def test_the_measured_files_split_the_unit_time_evenly():
    """#896: by hash the six shards held 437 to 827 s of tests; the measured files are placed by time instead."""
    import json
    seconds = json.loads(mod.DURATIONS.read_text(encoding="utf-8"))
    assert seconds and all(isinstance(v, (int, float)) and v >= 0 for v in seconds.values())
    loads = [0.0] * 6
    for rel, s in seconds.items():
        homes = [i for i in range(6) if mod.in_shard(f"{rel}::t", f"{i}/6")]
        assert len(homes) == 1, rel
        loads[homes[0]] += s
    assert max(loads) <= 1.05 * sum(loads) / 6, [round(x) for x in loads]


def test_a_file_without_a_measured_time_keeps_its_hash_shard(monkeypatch, tmp_path):
    import zlib
    (tmp_path / "d.json").write_text('{"a/test_heavy.py": 100, "a/test_light.py": 1}', encoding="utf-8")
    monkeypatch.setattr(mod, "DURATIONS", tmp_path / "d.json")
    mod._measured_homes.cache_clear()
    try:
        assert mod.in_shard("a/test_heavy.py::t", "0/2") and mod.in_shard("a/test_light.py::t", "1/2")
        new = "b/test_new.py"
        assert mod.in_shard(f"{new}::t", f"{zlib.crc32(new.encode()) % 2}/2")
    finally:
        mod._measured_homes.cache_clear()
    assert mod.in_shard("a/test_a.py::t", "0/1")
    with pytest.raises(ValueError):
        mod.in_shard("a/test_a.py::t", "4/4")


def test_any_selector_error_falls_back_to_full(monkeypatch, capsys):
    """Review of #383: an unexpected error must not fail the plan job, which would leave the push with no test run."""
    monkeypatch.delenv("GITHUB_OUTPUT", raising=False)
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    monkeypatch.setattr(mod, "changed_files", lambda base: ["pkg/a.py"])

    def boom(changed):
        raise RecursionError("maximum recursion depth exceeded")

    monkeypatch.setattr(mod, "select", boom)
    assert mod.main(["origin/main"]) == 0
    out = capsys.readouterr().out
    assert '"mode": "FULL"' in out and "RecursionError" in out


def _e2e(*names: str) -> list[str]:
    return sorted(mod.E2E_DIR + n for n in names)


def test_a_board_change_no_longer_reaches_the_root_conftest_through_app_runners():
    """15 Nov 2026: the root conftest's autouse fixture imports app.runners, which imports every board, so every board
    change ran FULL. The edge now stops at app/runners.py itself and the six config modules the fixture repoints."""
    sel = mod.select(["module_oipd/report.py"])
    assert sel.mode == "SELECTIVE", sel.reason
    assert "module_oipd/tests/test_report_pool.py" in sel.unit
    assert len([u for u in sel.unit if not u.startswith(mod.E2E_DIR)]) < len(mod.all_tests(_REPO)) / 2
    assert mod.select(["app/runners.py"]).mode == "FULL"
    assert mod.select(["module_oipd/config.py"]).mode == "FULL"


def test_the_root_conftest_reads_list_matches_its_board_artifact_pairs():
    tree = ast.parse((_REPO / "conftest.py").read_text(encoding="utf-8"))
    pairs = next(n.value for n in ast.walk(tree) if isinstance(n, ast.Assign)
                 and any(getattr(t, "id", "") == "BOARD_ARTIFACT_PAIRS" for t in n.targets))
    assert {f"{m}.config" for _, m in ast.literal_eval(pairs)} == set(mod._ROOT_CONFTEST_READS)
    assert "app.runners" in (_REPO / "conftest.py").read_text(encoding="utf-8")


def test_a_change_inside_one_board_runs_only_that_boards_e2e_and_the_shell():
    sel = mod.select(["module_oipd/report.py"])
    assert sel.e2e == _e2e("test_board_oipd.py", *mod.E2E_ALWAYS)


def test_a_board_another_board_imports_runs_the_importers_e2e_too():
    """module_earnings_radar imports module_sector_rotation directly, not only through app/."""
    sel = mod.select(["module_sector_rotation/__init__.py"])
    assert sel.mode == "SELECTIVE", sel.reason
    assert mod.E2E_DIR + "test_board_sector_rotation.py" in sel.e2e
    assert mod.E2E_DIR + "test_board_earnings_radar.py" in sel.e2e
    assert mod.E2E_DIR + "test_board_value_chain.py" not in sel.e2e


@pytest.mark.parametrize("changed", [["app/dashboard.py"], ["module_oipd/report.py", "core/provenance.py"]])
def test_a_change_outside_the_board_folders_keeps_every_reached_e2e_test(changed):
    sel = mod.select(changed)
    assert sel.mode == "SELECTIVE", sel.reason
    assert len(sel.e2e) == len([t for t in mod.all_tests(_REPO) if t.startswith(mod.E2E_DIR)])


def test_a_settings_change_runs_every_e2e_test():
    """module_settings has no row on purpose: the Settings board shows every board."""
    assert "module_settings" not in mod.E2E_BY_BOARD
    assert mod._board_e2e(["module_settings/newdata.py"], _REPO) is None


def test_every_board_folder_and_every_e2e_file_has_its_place_in_the_board_table():
    boards = {p.name for p in _REPO.glob("module_*") if p.is_dir()} - {"module_testing", "module_settings"}
    assert boards == set(mod.E2E_BY_BOARD), "a board folder needs a row in select_tests.E2E_BY_BOARD"
    e2e = {Path(t).name for t in mod.all_tests(_REPO) if t.startswith(mod.E2E_DIR)}
    placed = set(mod.E2E_ALWAYS) | set(mod.E2E_HARNESS) | {n for row in mod.E2E_BY_BOARD.values() for n in row}
    assert e2e == placed, f"missing: {sorted(e2e - placed)}; gone: {sorted(placed - e2e)}"


def test_the_full_ci_label_is_removed_after_one_finished_full_run():
    wf = (_REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    job = wf.split("\n  full-ci-once:\n", 1)[1].split("\n  merge-gate:\n", 1)[0]
    assert "needs.plan.outputs.mode == 'FULL'" in job and "contains(github.event.pull_request.labels.*.name, 'full-ci')" in job
    assert "needs.unit.result != 'cancelled'" in job and "needs.e2e.result != 'cancelled'" in job
    assert 'labels/full-ci"' in job and "pull-requests: write" in job
    assert "unlabeled" not in wf.split("\njobs:\n", 1)[0], "removing the label must not start a run"


def test_a_push_to_main_skips_only_on_a_green_note_for_its_own_tree():
    wf = (_REPO / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
    plan = wf.split("\n  plan:\n", 1)[1].split("\n  unit:\n", 1)[0]
    assert "if: github.event_name == 'push'" in plan and "grep -qxF \"tested-tree $tree\"" in plan
    assert 'select(.conclusion == "success")' in plan and "check_name=merge-gate" in plan
    assert 'echo "mode=SKIP"' in plan
    gate = wf.split("\n  merge-gate:\n", 1)[1]
    assert 'echo "::notice title=tested-tree::tested-tree $TREE"' in gate
    for job in ("unit", "e2e"):
        body = wf.split(f"\n  {job}:\n", 1)[1]
        assert body.split("\n", 2)[1] == "    if: needs.plan.outputs.mode != 'SKIP'", job
