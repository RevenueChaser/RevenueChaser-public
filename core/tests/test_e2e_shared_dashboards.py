"""The read-only e2e tests share a dashboard, and a sharing test cannot write to it (#896 step 3).

A dashboard subprocess is the e2e tier's unit of cost: an empty-store test, which boots one and reads a single
page, took about 6.3 s on the 19 Nov 2026 run. Before this change 68 of the tier's tests booted one each. The
fix is a module-scoped fixture built on ``harness.shared.shared_dashboard``, seeded and run once, which the
tests that only read then share.

Sharing is safe only while every sharer reads. This guard is static and starts nothing: it reads the e2e files
with ``ast`` and asserts (1) the listed files still share, and (2) no sharing test also asks for a fixture that
would change what a later sharer sees. A test that needs to write takes the function-scoped ``dashboard`` and
stays out of the shared group — ``test_board_uw_interaction`` has four such tests, each with its reason beside
it in the file.

One test function, deliberately, and it checks ``harness.shared.write_13f_totals`` before anything else.
``scripts/red_on_base.py`` copies a PR's own test files into the merge-base worktree, so a static check that
only reads ``test_*.py`` passes on the base whatever the PR did, and proves nothing there. ``harness/shared.py``
is not a test module, so it *is* the base's version: the helper check is this guard's red-first half, and the
static half rides with it under one id.
"""
from __future__ import annotations

import ast
from pathlib import Path

E2E = Path(__file__).resolve().parents[2] / "module_testing" / "e2e"

#: The files whose read-only tests share one dashboard, and the fixture each sharer takes.
SHARING = {
    "test_board_leaps.py": "dashboard",             # module-scoped, shadows the conftest fixture
    "test_board_sec_13f.py": "served",
    "test_board_oipd.py": "built",
    "test_board_uw_interaction.py": "ran_shared",
    "test_board_earnings_radar.py": "fetched_shared",
    "test_board_comovement.py": "fetched",          # shared before #896
    "test_board_sector_rotation.py": "fetched",
    "test_phone_shell.py": "dashboard",
    "test_spx_gamma_phone.py": "board",            # shared before #896
}

#: Function-scoped fixtures that change the store, the cache or the subprocess. A test that takes one of these
#: has a dashboard of its own by definition, so taking it *and* a shared fixture is the leak this guard catches.
MUTATORS = {"dashboard", "clear_cache", "serve_13f_totals", "e2e_dirs", "dead_uw_token"}


def _module(name: str) -> ast.Module:
    return ast.parse((E2E / name).read_text(encoding="utf-8"))


def _fixtures(tree: ast.Module) -> dict[str, str]:
    """``{fixture name: scope}`` for every fixture the module defines."""
    out: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            text = ast.unparse(dec)
            if "fixture" not in text:
                continue
            scope = "function"
            for candidate in ("session", "package", "module", "class"):
                if f'"{candidate}"' in text or f"'{candidate}'" in text:
                    scope = candidate
            out[node.name] = scope
    return out


def _tests(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name.startswith("test_")]


def test_the_read_only_e2e_tests_share_a_dashboard_and_never_write_to_it():
    """One test, not one per file, and the helper check first — see the note on red-on-base above.

    The helper is read with ``ast`` rather than imported: the e2e harness is not meant to be loaded by the unit
    tier, and its shape is all this guard needs.
    """
    harness = ast.parse((E2E / "harness" / "shared.py").read_text(encoding="utf-8"))
    seeder = next((n for n in harness.body
                   if isinstance(n, ast.FunctionDef) and n.name == "write_13f_totals"), None)
    assert seeder is not None, \
        "harness.shared.write_13f_totals is gone: the 13F sharing has no seeder a module-scoped fixture can call"
    params = [a.arg for a in seeder.args.args]
    assert params[:2] == ["dashboard", "totals"], \
        f"write_13f_totals must take (dashboard, totals) so either scope can seed; got {params}"

    problems: list[str] = []
    for name, shared_fixture in sorted(SHARING.items()):
        tree = _module(name)
        fixtures = _fixtures(tree)
        tests = _tests(tree)
        if shared_fixture not in fixtures:
            problems.append(f"{name}: no {shared_fixture!r} fixture; the sharing was undone")
            continue
        if not {n for n, scope in fixtures.items() if scope in ("module", "class", "package", "session")}:
            problems.append(f"{name}: no fixture above function scope, so nothing is shared")
        if not any(shared_fixture in {a.arg for a in t.args.args} for t in tests):
            problems.append(f"{name}: no test takes {shared_fixture!r}")
        # In a file that shadows ``dashboard`` at module scope, that name *is* the shared fixture.
        mutators = MUTATORS - {shared_fixture} - {n for n, scope in fixtures.items() if scope != "function"}
        for test in tests:
            args = {a.arg for a in test.args.args}
            if shared_fixture in args and (args & mutators):
                problems.append(
                    f"{name}::{test.name} shares the dashboard but also takes {sorted(args & mutators)}; "
                    "a test that writes needs the function-scoped `dashboard` and must leave the shared group")
    assert not problems, "\n".join(problems)
