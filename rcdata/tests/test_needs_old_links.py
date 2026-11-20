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
    "module_oipd", "module_relatedness", "module_sec_13f", "module_sector_rotation",
    "module_swing_potential", "module_uw_interaction", "module_value_chain",
})

#: ``{package: files (relative to it) that import core.providers}`` on 11 Nov 2026 (main 34ac3e55);
#: ``module_relatedness/naming.py`` left it on 20 Nov 2026 (#404: its writer comes from ``core.llm_jobs`` now).
#: ``module_spx_gamma/candles.py`` joined it on 20 Nov 2026 (#1213) -- the **one** line this ceiling has ever
#: gained, and it records no new link: ``live_spot`` has read Yahoo directly since 2026-10-22 (the owner's spot
#: exception), behind this guard's back, because it called the library instead of the provider. Routing it
#: through ``yfinance.attempt`` made the existing read visible, counted and 401-cured. The companion test below
#: now matches the raw libraries too, so a read cannot hide that way again.
PROVIDER_FILES = {
    "module_asymmetric_growth": {"engine.py"},
    "module_earnings_radar": {"macro_watch.py", "pipeline.py"},
    "module_financials": {"engines/comps_engine.py", "engines/credit_capacity_engine.py", "engines/dcf_engine.py",
                          "engines/quick_remarks_engine.py", "engines/three_statement_engine.py", "run.py"},
    "module_fundamentals": {"pipeline.py"},
    "module_news": {"headlines.py", "tape.py"},
    "module_oipd": {"engine.py"},
    "module_relatedness": {"__main__.py", "compare.py", "engine.py", "profiles.py", "store.py"},
    "module_sector_rotation": {"__main__.py", "engine.py"},
    "module_spx_gamma": {"candles.py", "run.py"},
    "module_swing_potential": {"indicators.py"},
    "module_uw_interaction": {"engine.py"},
    "module_value_chain": {"edgar_text.py", "engine.py", "health.py"},
}


#: Provider client libraries. A board package importing one of these reads a provider without going through
#: ``core.providers``, which the import check above cannot see (#1213).
#: A name is matched as a prefix of the dotted module path, so ``urllib.request`` is a client and
#: ``urllib.parse`` (pure string work, used by two boards for ``quote`` / ``urlsplit``) is not.
RAW_PROVIDER_LIBRARIES = (
    "yfinance", "httpx", "requests", "aiohttp", "pandas_datareader", "fredapi", "alpaca", "ib_insync", "ibapi",
    "websocket", "websockets", "feedparser", "ftplib", "urllib.request", "urllib.error",
)

#: Files that import an HTTP client to talk to **our own dashboard** on ``127.0.0.1`` -- a command-line trigger
#: (``POST /run/<job>`` then poll ``/api/job/<id>``), not a provider read. Measured on 20 Nov 2026 (#1213): these
#: three are every such file in a board package, and nothing else in a board package reaches a provider library
#: outside ``core.providers``.
LOCAL_DASHBOARD_CLIENTS = {
    "module_news": {"x_feed.py"},
    "module_spx_gamma": {"__main__.py"},
    "module_value_chain": {"__main__.py"},
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


def _is_raw_library(module: str) -> bool:
    """``module`` is one of the client libraries, or a submodule of one."""
    return any(module == name or module.startswith(name + ".") for name in RAW_PROVIDER_LIBRARIES)


def _imports_raw_library(node) -> bool:
    if isinstance(node, ast.Import):
        return any(_is_raw_library(a.name) for a in node.names)
    if isinstance(node, ast.ImportFrom) and node.module:
        return _is_raw_library(node.module)
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


def test_no_board_file_reads_a_provider_library_behind_the_guard():
    """A board file may not import a provider client library unless it is declared a provider file (#1213).

    The check above matches ``core.providers``, so a file that calls ``yfinance`` (or an HTTP client) directly is
    a provider read the ceiling never saw. ``module_spx_gamma/candles.py`` was exactly that for a month. The
    three command-line triggers that post to our own dashboard are named in ``LOCAL_DASHBOARD_CLIENTS``, with
    the host in their own source: they talk to ``127.0.0.1``, not to a provider.
    """
    undeclared: dict[str, list[str]] = {}
    for package in _packages():
        allowed = PROVIDER_FILES.get(package, set()) | LOCAL_DASHBOARD_CLIENTS.get(package, set())
        for _path, rel, tree in _sources(package):
            if rel in allowed:
                continue
            if any(_imports_raw_library(node) for node in ast.walk(tree)):
                undeclared.setdefault(package, []).append(rel)
    found = {p: sorted(f) for p, f in undeclared.items()}
    assert not found, (f"provider library imported outside core.providers: {found}; route the read through "
                       "core.providers and declare the file in PROVIDER_FILES")


def test_every_local_dashboard_client_really_talks_to_the_dashboard():
    """``LOCAL_DASHBOARD_CLIENTS`` is an exemption, so it is checked rather than trusted: each file must name a
    dashboard route, and a file that stops existing or stops importing a client leaves the list."""
    for package, files in LOCAL_DASHBOARD_CLIENTS.items():
        sources = {rel: tree for _path, rel, tree in _sources(package)}
        for rel in files:
            assert rel in sources, f"{package}/{rel} is gone; remove it from LOCAL_DASHBOARD_CLIENTS"
            assert any(_imports_raw_library(node) for node in ast.walk(sources[rel])), (
                f"{package}/{rel} imports no client library any more; remove it from LOCAL_DASHBOARD_CLIENTS")
            text = (boards.root() / package / rel).read_text(encoding="utf-8")
            assert 'DASHBOARD = "http://127.0.0.1' in text and "/run/" in text, (
                f"{package}/{rel} does not look like a dashboard trigger (a 127.0.0.1 base and a /run/ route); "
                "it may be a provider read")
