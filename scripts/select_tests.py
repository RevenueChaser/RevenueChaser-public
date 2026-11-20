"""Which test files a change can reach, by import graph; FULL whenever that is not safe to say.

CI runs this on every pull request (``.github/workflows/tests.yml``, job ``plan``). A test file is selected when
it imports a changed module directly or transitively. An import counts wherever it is written: at the top, inside
a function, relative, or as a module name in a string (``"RevenueChaser.module_x.y"`` or ``"module_x.y:func"``),
which is how the e2e harness starts the dashboard subprocess and how the ``import_module`` registries name their
targets. Importing ``a.b.c`` also runs ``a`` and ``a.b``, so those are edges too.

A changed non-Python file maps to the Python files that name it (its basename appears in their text), through
templates and data files that name it in turn; the tests reaching those Python files are selected.

FULL (the whole unit and e2e suite) when:
  - a changed file is a conftest, requirements, pytest/setup config, a workflow, or this selector;
  - a changed non-Python file sits in a tests/fixtures/e2e folder (fixtures are read by glob, not by name);
  - a changed non-Markdown file is gone (deleted or renamed: its importers are not in the graph);
  - a changed non-Markdown file is named by no Python file, or shares its file name with another file
    (a name matches only whole: "a.js" is not named by "data.json");
  - any Python file does not parse (no graph);
  - the selector itself fails in any other way (git, an unexpected error);
  - a change reaches the root conftest (its fixtures run in every test);
  - a changed non-Markdown file reaches no test (checked per file, so a tested file beside it cannot hide it).

A change that reaches any other conftest selects every test below that conftest's folder: its fixtures run there
whatever the test imports. The e2e conftest starts the dashboard, so most changes reach every e2e test; a change that
stays inside board folders is narrowed to those boards' e2e files by ``E2E_BY_BOARD``.

Usage: ``python scripts/select_tests.py BASE_REF [--full REASON]`` diffs against the merge-base with BASE_REF
and prints the selection as JSON; under GitHub Actions it also writes the job outputs and the step summary.
"""
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
import sys
import zlib
from collections import Counter
from dataclasses import dataclass, field
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
PKG = "RevenueChaser"
E2E_DIR = "module_testing/e2e/"
_SKIP_DIRS = {".git", ".store", ".cache", "__pycache__", "node_modules", ".pytest_cache"}
_FULL_NAMES = {"conftest.py", "pytest.ini", "setup.py", "setup.cfg", "pyproject.toml", "docker-compose.yml"}
_FULL_PREFIXES = (".github/", "scripts/select_tests.py")
_FIXTURE_DIRS = {"tests", "fixtures", "e2e"}
_IGNORED_PREFIXES = (".hermes/", ".claude/")

# The root conftest's autouse ``isolate_board_artifacts`` imports ``app.runners`` only to repoint path attributes on it
# and on these boards' config modules (``conftest.BOARD_ARTIFACT_PAIRS``, named there by f-string, so the graph cannot
# see them). ``app.runners`` imports every board, so that one edge made every board change reach the root conftest and
# run FULL. The edge now stops at ``app/runners.py`` itself (a change to it is FULL) and at these config modules.
_ROOT_CONFTEST_RUNNERS = "app/runners.py"  # a path, not a dotted name: a dotted string is an import edge here
_ROOT_CONFTEST_READS = tuple(f"{m}.config" for m in (
    "module_fundamentals", "module_swing_potential", "module_comovement", "module_value_chain",
    "module_relatedness", "module_oipd"))

# Which e2e files drive which board. A change inside ``module_<board>/`` alone runs that board's files, the files of
# the boards that import it (followed through ``module_*`` code only), and E2E_ALWAYS, instead of every e2e test
# the dashboard fixture reaches. Any changed file outside these folders, or in a board with no row, runs every e2e
# test as before. scripts/tests/test_select_tests.py fails when a board folder or an e2e file is missing here.
E2E_BY_BOARD: dict[str, tuple[str, ...]] = {
    "module_asymmetric_growth": ("test_board_asymmetric_growth.py",),
    "module_comovement": ("test_board_comovement.py",),
    "module_earnings_radar": ("test_board_earnings_radar.py", "test_earnings_radar_phone.py"),
    "module_financials": ("test_board_financials.py",),
    "module_fundamentals": ("test_board_fundamentals.py",),
    "module_hit_rate": (),
    "module_leaps": ("test_board_leaps.py",),
    "module_news": (),
    "module_oipd": ("test_board_oipd.py",),
    "module_relatedness": (),
    "module_sec_13f": ("test_board_sec_13f.py", "test_watchlist_pair.py"),
    "module_sector_rotation": ("test_board_sector_rotation.py",),
    "module_spx_gamma": ("test_spx_gamma_phone.py", "test_spx_gamma_rcdata.py"),
    "module_swing_potential": ("test_board_swing.py",),
    "module_uw_interaction": ("test_board_uw_interaction.py",),
    "module_value_chain": ("test_board_value_chain.py",),
    "module_watchlists": ("test_watchlist_pair.py",),
    "module_welcome": (),
}
# The shell every board sits in (phone layout, panel header, Settings' row per board, screenshots).
E2E_ALWAYS = ("test_phone_shell.py", "test_panel_header_231.py",
              "test_board_settings.py", "test_screenshots.py")
# The harness's own tests: a harness change is under module_testing/, which runs every e2e test anyway.
E2E_HARNESS = ("test_cdp_browser.py", "test_chrome_timeout.py", "test_harness_env.py", "test_harness_parallel.py",
               "test_harness_yfinance.py", "test_settings_control.py", "test_settings_newdata.py")


@dataclass
class Selection:
    mode: str  # "FULL" or "SELECTIVE"
    reason: str
    unit: list[str] = field(default_factory=list)
    e2e: list[str] = field(default_factory=list)


def _files(root: Path):
    for p in root.rglob("*"):
        if p.is_file() and not _SKIP_DIRS & set(p.relative_to(root).parts):
            yield p.relative_to(root).as_posix()


def _module(rel: str) -> str:
    parts = rel[:-3].split("/")
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _is_test(rel: str) -> bool:
    name = rel.rsplit("/", 1)[-1]
    return name.endswith(".py") and (name.startswith("test_") or name.endswith("_test.py"))


def all_tests(root: Path = REPO) -> list[str]:
    return sorted(r for r in _files(root) if _is_test(r))


def _with_parents(name: str) -> list[str]:
    parts = name.split(".") if name else []
    return [""] + [".".join(parts[:i]) for i in range(1, len(parts) + 1)]


def _strip(name: str) -> str:
    return "" if name == PKG else name.removeprefix(PKG + ".")


def _imports(rel: str, tree: ast.AST, modules: set[str]) -> set[str]:
    """Every in-repo module ``rel`` imports, with the packages that importing it runs."""
    me = _module(rel)
    package = me if rel.endswith("__init__.py") else me.rpartition(".")[0]
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(_strip(a.name) for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package.split(".") if package else []
                base = base[:len(base) - (node.level - 1)] if node.level > 1 else base
                base = ".".join(base + ([node.module] if node.module else []))
            else:
                base = _strip(node.module or "")
            names.add(base)
            names.update(f"{base}.{a.name}".lstrip(".") for a in node.names)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) and len(node.value) < 200:
            # Dotted names only: a bare package name in a string is a label ("module_swing_potential"), not an import.
            name = node.value.split(":", 1)[0]
            if "." in name:
                names.add(_strip(name))
    return {p for n in names if n in modules for p in _with_parents(n)} & modules


@cache
def _graph(root: Path) -> dict[str, set[str]]:
    """Reverse import graph: module -> the files that import it. Raises when a file does not parse."""
    py = [r for r in _files(root) if r.endswith(".py")]
    modules = {_module(r) for r in py}
    importers: dict[str, set[str]] = {}
    for rel in py:
        tree = ast.parse((root / rel).read_text(encoding="utf-8"), filename=rel)
        for m in _imports(rel, tree, modules):
            importers.setdefault(m, set()).add(rel)
    runners = _module(_ROOT_CONFTEST_RUNNERS)
    if "conftest.py" in importers.get(runners, ()):
        importers[runners].discard("conftest.py")
        for m in _ROOT_CONFTEST_READS:
            if m in modules:
                importers.setdefault(m, set()).add("conftest.py")
    return importers


def _named_by(rel: str, texts: dict[str, str], root: Path) -> set[str] | None:
    """The Python files that name ``rel``, directly or through non-Markdown files that name it.

    None when a basename on the way belongs to two files: which one a reader opens cannot be told from the name.
    """
    bases = Counter(r.rsplit("/", 1)[-1] for r in _files(root))  # binary files too, not only ``texts``
    found, seen, todo = set(), {rel}, [rel]
    while todo:
        base = todo.pop().rsplit("/", 1)[-1]
        if bases[base] > 1 and not base.endswith(".md"):  # README.md is everywhere; a doc is matched by name
            return None
        name = re.compile(rf"(?<![\w.-]){re.escape(base)}(?![\w-])")
        for other, text in texts.items():
            if other in seen or base not in text or not name.search(text):
                continue
            seen.add(other)
            if other.endswith(".py"):
                found.add(other)
            elif not other.endswith(".md"):
                todo.append(other)
    return found


@cache
def _texts(root: Path) -> dict[str, str]:
    out = {}
    for rel in _files(root):
        try:
            out[rel] = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            pass
    return out


def select(changed: list[str], root: Path = REPO) -> Selection:
    changed = [c for c in changed if not c.startswith(_IGNORED_PREFIXES)]
    for rel in changed:
        name = rel.rsplit("/", 1)[-1]
        if name in _FULL_NAMES or name.startswith("requirements") or rel.startswith(_FULL_PREFIXES):
            return Selection("FULL", f"{rel} is shared test config")
        if rel == _ROOT_CONFTEST_RUNNERS:
            return Selection("FULL", f"{rel} is read by the root conftest's autouse fixture")
        if not (root / rel).is_file() and not rel.endswith(".md"):
            return Selection("FULL", f"{rel} is gone (deleted or renamed)")
        if not rel.endswith(".py") and _FIXTURE_DIRS & set(rel.split("/")[:-1]):
            return Selection("FULL", f"{rel} is a test fixture")
    seeds_of: dict[str, set[str]] = {}
    for rel in changed:
        seeds_of[rel] = {rel} if rel.endswith(".py") else _named_by(rel, _texts(root), root)
        if seeds_of[rel] is None:
            return Selection("FULL", f"{rel} shares its file name with another file")
        if not seeds_of[rel] and not rel.endswith(".md"):
            return Selection("FULL", f"{rel} is named by no Python file")
    try:
        reached = _reach(set().union(*seeds_of.values()), root)
        for rel, seeds in seeds_of.items():
            if not rel.endswith(".md") and not any(_is_test(r) or r.endswith("conftest.py") for r in _reach(seeds, root)):
                return Selection("FULL", f"{rel} changed and no test reaches it")
    except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
        return Selection("FULL", f"import graph failed: {exc}")
    if "conftest.py" in reached:
        return Selection("FULL", "the change reaches the root conftest.py")
    under = tuple(c.removesuffix("conftest.py") for c in reached if c.endswith("/conftest.py"))
    tests = sorted({r for r in reached if _is_test(r)} | {t for t in all_tests(root) if t.startswith(under)} if under
                   else {r for r in reached if _is_test(r)})
    e2e = [t for t in tests if t.startswith(E2E_DIR)]
    if (boards := _board_e2e(changed, root)) is not None:
        e2e = boards
    return Selection("SELECTIVE", f"{len(tests)} test files reach {len(changed)} changed files",
                     tests, e2e)


def _board_of(rel: str) -> str | None:
    top = rel.split("/", 1)[0]
    return top if top in E2E_BY_BOARD else None


def _board_e2e(changed: list[str], root: Path) -> list[str] | None:
    """The e2e files for a change that stays inside board folders, or None when every reached e2e file must run.

    The boards that import a changed board count too, followed through ``module_*`` code only: through ``app/`` or
    ``core/`` every board reaches every other (``app.runners`` imports them all).
    """
    code = [c for c in changed if not c.endswith(".md")]
    if not code or any(_board_of(c) is None for c in code):
        return None
    importers = _graph(root)
    boards, todo, seen = set(), [c for c in code if c.endswith(".py")], set()
    boards.update(_board_of(c) for c in code)
    while todo:
        for nxt in importers.get(_module(todo.pop()), ()):
            if nxt not in seen and _board_of(nxt) and not _is_test(nxt):
                seen.add(nxt)
                boards.add(_board_of(nxt))
                todo.append(nxt)
    names = set(E2E_ALWAYS).union(*(E2E_BY_BOARD[b] for b in boards))
    return sorted(E2E_DIR + n for n in names)


def _reach(seeds: set[str], root: Path) -> set[str]:
    """``seeds`` and every file that imports one of them, directly or transitively."""
    importers = _graph(root)
    reached, todo = set(seeds), list(seeds)
    while todo:
        for nxt in importers.get(_module(todo.pop()), ()):
            if nxt not in reached:
                reached.add(nxt)
                todo.append(nxt)
    return reached


def reached_tests(changed_py: list[str], root: Path = REPO) -> list[str]:
    """The test files that import any of ``changed_py`` by the graph alone (no conftest or FULL rules)."""
    return sorted(r for r in _reach(set(changed_py), root) if _is_test(r))


def changed_files(base: str, root: Path = REPO) -> list[str]:
    out = subprocess.run(["git", "diff", "--name-only", "--no-renames", f"{base}...HEAD"],
                         cwd=root, capture_output=True, text=True, check=True).stdout
    return [line for line in out.splitlines() if line]


def _github(sel: Selection, changed: list[str]) -> None:
    if out := os.environ.get("GITHUB_OUTPUT"):
        with open(out, "a", encoding="utf-8") as f:
            f.write(f"mode={sel.mode}\nunit={' '.join(sel.unit)}\ne2e={' '.join(sel.e2e)}\n")
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        lines = [f"## Test selection: {sel.mode}", "", f"Reason: {sel.reason}", ""]
        if sel.mode == "SELECTIVE":
            lines += [f"Changed files: {len(changed)}. Unit files: {len(sel.unit)}. E2E files: {len(sel.e2e)}.", "",
                      "Not a merge gate: label the PR `full-ci` for a FULL run on this head.", "", "<details><summary>Selected test files</summary>", ""]
            lines += [f"- `{t}`" for t in sel.unit] + ["", "</details>"]
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


DURATIONS = Path(__file__).with_name("test_durations.json")


@cache
def _measured_homes(n: int) -> dict[str, int]:
    """The measured files' shards: heaviest first, each to the lightest shard so far (ties to the lowest index).

    ``test_durations.json`` holds each file's summed test time, the mean over several FULL runs' junit artifacts
    (``scripts/durations.py`` writes it; every file, no floor). It depends only on that file, never on what was
    collected, so every shard computes the same split.

    The split balances the shards; it cannot shorten a shard below its longest single file, because ``--dist
    loadfile`` gives a whole file to one worker. ``durations.heaviest_share`` is that bound and
    ``scripts/tests/test_durations_table.py`` fails a file that crosses it (#1153).
    """
    try:
        seconds = json.loads(DURATIONS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    loads, homes = [0.0] * n, {}
    for rel, s in sorted(seconds.items(), key=lambda kv: (-kv[1], kv[0])):
        i = min(range(n), key=lambda j: (loads[j], j))
        homes[rel] = i
        loads[i] += s
    return homes


def in_shard(nodeid: str, shard: str) -> bool:
    """CI's unit matrix (``RC_SHARD="i/n"``, tests.yml job ``unit``): a test runs in shard ``i`` of ``n``.

    A whole file stays in one shard (``--dist loadfile`` relies on that). A file with a measured time is placed by
    ``_measured_homes`` (#896: by hash the six shards held 437 to 827 s of tests on 15 Nov 2026; by time, 594 to
    600 s of the measured files, and 959 s each once every file was measured -- #1153). Any other file hashes
    there, so adding a new file moves no other file.
    """
    i, n = (int(x) for x in shard.split("/"))
    if not 0 <= i < n:
        raise ValueError(f"RC_SHARD {shard!r}: want i/n with 0 <= i < n")
    rel = nodeid.split("::", 1)[0]
    home = _measured_homes(n).get(rel)
    return (zlib.crc32(rel.encode()) % n if home is None else home) == i


def main(argv: list[str]) -> int:
    base = argv[0] if argv else "origin/main"
    full = argv[argv.index("--full") + 1] if "--full" in argv else ""
    changed: list[str] = []
    if full:
        sel = Selection("FULL", full)
    else:
        try:
            changed = changed_files(base)
            sel = select(changed)
        except (subprocess.CalledProcessError, OSError) as exc:
            sel = Selection("FULL", f"git diff against {base} failed: {exc}")
        except Exception as exc:  # noqa: BLE001 - any selector bug must run FULL, never leave the push untested
            sel = Selection("FULL", f"selector failed: {exc!r}")
    print(json.dumps(sel.__dict__, indent=1))
    _github(sel, changed)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
