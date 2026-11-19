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
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

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


@pytest.mark.parametrize("name", sorted(SHARING))
def test_the_file_still_shares_one_dashboard(name):
    """Each listed file defines its shared fixture, has one above function scope, and a test that takes it."""
    tree = _module(name)
    shared = SHARING[name]
    fixtures = _fixtures(tree)
    assert shared in fixtures, f"{name} no longer defines a {shared!r} fixture: the sharing was undone"
    wider = {n for n, scope in fixtures.items() if scope in ("module", "class", "package", "session")}
    assert wider, f"{name} has no fixture above function scope: nothing is shared"
    assert any(shared in {a.arg for a in t.args.args} for t in _tests(tree)), \
        f"no test in {name} takes {shared!r}"


@pytest.mark.parametrize("name", sorted(SHARING))
def test_a_sharing_test_asks_for_no_mutator(name):
    """A test on the shared dashboard may not also take a fixture that writes to a dashboard of its own."""
    tree = _module(name)
    shared = SHARING[name]
    fixtures = _fixtures(tree)
    # In a file that shadows ``dashboard`` at module scope, that name *is* the shared fixture, not a mutator.
    mutators = MUTATORS - {shared} - {n for n, scope in fixtures.items() if scope != "function"}
    for test in _tests(tree):
        args = {a.arg for a in test.args.args}
        if shared not in args:
            continue
        clash = args & mutators
        assert not clash, (
            f"{name}::{test.name} shares the dashboard but also takes {sorted(clash)}; "
            "a test that writes needs the function-scoped `dashboard` and must leave the shared group")
