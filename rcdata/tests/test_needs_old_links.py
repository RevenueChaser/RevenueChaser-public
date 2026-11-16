"""The boards' links to providers may only shrink (#642 PR 1, F6 of the group-1 review).

Two ceilings, each read from the boards' own source (tests left out), never trusted:

- ``boards.UNDECLARED`` can lose a board, never gain one.
- **Providers:** every file in a board package that imports ``core.providers`` must be listed in ``PROVIDER_FILES``.

Every list is exact, so a PR that removes a link also removes its line here and the lists shrink with the work.
The third ceiling, the old-store tables each board and shared file named, went with those files (#860): no table of
``raw``, ``edgar``, ``history`` or ``prices.duckdb`` is left to name, and ``core/tests/test_no_old_store.py`` now
fails any code that names one of those files again.
"""
from __future__ import annotations

import ast

from RevenueChaser.rcdata.needs import boards

#: ``boards.UNDECLARED`` on 11 Nov 2026. Remove a board here when it migrates; never add one.
UNDECLARED_CEILING = frozenset({
    "module_asymmetric_growth", "module_financials", "module_fundamentals",
    "module_news", "module_oipd", "module_relatedness", "module_sec_13f", "module_sector_rotation",
    "module_swing_potential", "module_uw_interaction", "module_value_chain",
})

#: ``{package: files (relative to it) that import core.providers}`` on 11 Nov 2026 (main 34ac3e55).
PROVIDER_FILES = {
    "module_asymmetric_growth": {"engine.py"},
    "module_earnings_radar": {"macro_watch.py", "pipeline.py"},
    "module_financials": {"engines/comps_engine.py", "engines/credit_capacity_engine.py", "engines/dcf_engine.py",
                          "engines/quick_remarks_engine.py", "engines/three_statement_engine.py", "run.py"},
    "module_fundamentals": {"pipeline.py"},
    "module_leaps": {"scan.py"},
    "module_news": {"headlines.py", "tape.py"},
    "module_oipd": {"engine.py"},
    "module_relatedness": {"__main__.py", "compare.py", "engine.py", "naming.py", "profiles.py", "store.py"},
    "module_sector_rotation": {"__main__.py", "engine.py"},
    "module_spx_gamma": {"run.py"},
    "module_swing_potential": {"indicators.py", "pipeline.py"},
    "module_uw_interaction": {"engine.py"},
    "module_value_chain": {"edgar_text.py", "engine.py", "health.py"},
}


def _packages() -> list[str]:
    return [*boards.board_packages(), "module_settings"]


def _sources(package: str):
    for path in boards._board_sources(package):
        yield path, str(path.relative_to(boards.root() / package)).replace("\\", "/"), ast.parse(
            path.read_text(encoding="utf-8"))


def _imports_providers(node) -> bool:
    if isinstance(node, ast.ImportFrom) and node.module:
        parts = node.module.split(".")
        return "providers" in parts or (parts[-1] == "core" and any(a.name == "providers" for a in node.names))
    if isinstance(node, ast.Import):
        return any("providers" in a.name.split(".") for a in node.names)
    return False


def _scan() -> dict[str, set[str]]:
    providers: dict[str, set[str]] = {}
    for package in _packages():
        for _path, rel, tree in _sources(package):
            if any(_imports_providers(node) for node in ast.walk(tree)):
                providers.setdefault(package, set()).add(rel)
    return providers


def test_undeclared_only_shrinks():
    grew = boards.UNDECLARED - UNDECLARED_CEILING
    assert not grew, f"boards added to UNDECLARED: {sorted(grew)}; a new board declares READS instead"


def test_the_ceiling_names_no_board_that_has_migrated():
    stale = UNDECLARED_CEILING - boards.UNDECLARED
    assert not stale, f"migrated, remove from UNDECLARED_CEILING: {sorted(stale)}"


def test_no_board_file_gains_a_provider_import_and_a_removed_one_leaves_the_list():
    found = _scan()
    new = {p: sorted(f - PROVIDER_FILES.get(p, set())) for p, f in found.items() if f - PROVIDER_FILES.get(p, set())}
    assert not new, f"new provider imports in boards: {new}; a board reads stored data, the builder fetches"
    gone = {p: sorted(f - found.get(p, set())) for p, f in PROVIDER_FILES.items() if f - found.get(p, set())}
    assert not gone, f"no longer importing providers, remove from PROVIDER_FILES: {gone}"


