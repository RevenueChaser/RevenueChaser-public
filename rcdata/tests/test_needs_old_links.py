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

from revenuechaser.rcdata.needs import boards

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
    # ``run.py`` and ``engines/quick_remarks_engine.py`` left it on 21 Nov 2026 (#645: Yahoo is dropped, so the
    # board makes no provider call at all). The four that stay import ``core.providers.validator``, which is pure
    # arithmetic over a statement record and reads nothing.
    "module_financials": {"engines/comps_engine.py", "engines/credit_capacity_engine.py", "engines/dcf_engine.py",
                          "engines/three_statement_engine.py"},
    "module_fundamentals": {"pipeline.py"},
    "module_news": {"headlines.py", "tape.py"},
    "module_oipd": {"engine.py"},
    # ``compare.py`` and ``profiles.py`` left it on 26 Nov 2026 (#1520): both files are gone with the board's
    # own profile writer, so nothing of them imports ``core.providers`` any more.
    "module_relatedness": {"__main__.py", "engine.py", "store.py"},
    "module_sector_rotation": {"__main__.py", "engine.py"},
    "module_spx_gamma": {"candles.py", "run.py"},
    # ``indicators.py`` left it on 21 Nov 2026 (#645): ``load_ticker_info`` was the board's last Yahoo read and
    # had no caller since #996, so nothing in the package imports ``core.providers`` any more.
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
#: were every such file in a board package, and nothing else in a board package reaches a provider library
#: outside ``core.providers``. ``module_news/x_feed.py`` was the third until the Grok lane was removed
#: (21 Nov 2026); the package keeps an empty entry, so a new local trigger there is still a deliberate line.
LOCAL_DASHBOARD_CLIENTS = {
    "module_news": set(),
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


def test_a_board_file_that_touches_a_client_library_goes_through_core_providers():
    """A board file may not read a provider library directly (#1213), in one check with its own exemptions.

    The check above matches ``core.providers``, so a file that calls ``yfinance`` (or an HTTP client) itself is a
    provider read the ceiling never saw: that was ``module_spx_gamma/candles.py`` for a month, and it is why the
    rule here is **both** -- a file that imports a client library must also go through the provider, where the
    counting (#299) and the 401 cure (#402) live, and be declared in ``PROVIDER_FILES``.

    ``LOCAL_DASHBOARD_CLIENTS`` is the one exemption, and it is checked rather than trusted: each named file must
    still exist, still import a client, and still carry a 127.0.0.1 base with a ``/run/`` route. Everything is
    one test on purpose -- an exemption's own hygiene is not evidence about a change, so it does not get an id of
    its own that ``red_on_base`` would have to call green.
    """
    raw_reads: dict[str, list[str]] = {}
    for package in _packages():
        exempt = LOCAL_DASHBOARD_CLIENTS.get(package, set())
        for _path, rel, tree in _sources(package):
            if not any(_imports_raw_library(node) for node in ast.walk(tree)):
                continue
            if rel in exempt:
                continue
            if not any(_imports_providers(node) for node in ast.walk(tree)):
                raw_reads.setdefault(package, []).append(rel)
    found = {p: sorted(f) for p, f in raw_reads.items()}
    assert not found, (f"client library read outside core.providers: {found}; route the read through "
                       "core.providers (counted, 401-cured) and declare the file in PROVIDER_FILES")

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
