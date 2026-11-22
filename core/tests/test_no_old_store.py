"""#860: the old store files are gone, and nothing may lead back to them.

avo, 15 Nov 2026: "Eskiye ait herseyi sil" and "yeni hic birsey eskiye bagli olamamali". ``.store/raw.duckdb``,
``edgar.duckdb``, ``history.duckdb`` and ``.store/prices.duckdb`` went in one PR with every code path to them; the
store keeps only the board files (``.store/boards/<board>.duckdb``). The serving files under ``RC_MARKET_DIR``
(including the new ``prices.duckdb`` there) are rcdata's and are not what this test is about.

This test fails a change that brings a link back:

- the store resolves only board files, and every MANIFEST table lives in one (``store_schema`` is in each);
- no code outside the tests names an old store file in a string, or sends a store call to an old file;
- no code imports a module that went with the old files, and none of those files comes back.

Comments and docstrings may still tell the history; only code is checked.
"""
from __future__ import annotations

import ast
import re
import subprocess
from pathlib import Path

import pytest

from revenuechaser.core import rawstore

_REPO = Path(__file__).resolve().parents[2]
OLD_DBS = ("raw", "edgar", "history", "prices")
#: The old files by name. ``prices.duckdb`` alone is the serving file's name too, so it counts only under ``.store``.
_OLD_FILE = re.compile(r"(?<![\w.])(?:raw|edgar|history)\.duckdb|\.store[/\\]+prices\.duckdb")

#: The modules that read or wrote only the old files, removed by #860. None may be imported or come back.
REMOVED_MODULES = frozenset({
    "app/universe_cli.py", "core/board_sources.py", "core/company_profile.py", "core/edgar_bulk.py",
    "core/edgar_store.py", "core/history.py", "core/identity/__main__.py", "core/identity/apply.py",
    "core/identity/cache.py", "core/identity/conflicts.py", "core/identity/gics.py", "core/identity/master.py",
    "core/identity/refresh.py", "core/identity/sic_sector.py", "core/identity/sources/fdic.py",
    "core/identity/sources/nasdaq.py", "core/identity/sources/sec.py", "core/identity/sources/sp1500.py",
    "core/identity/sources/spdr.py", "core/identity/sources/uw_sector.py", "core/identity/sources/yahoo_sector.py",
    "core/identity_cusip.py", "core/index_levels.py", "core/index_lists.py", "core/nightly_inputs.py",
    "core/providers/cache.py", "core/quotes.py", "core/run_counts.py", "core/sec_files.py", "core/sec_submissions.py",
    "core/sic_registry.py", "core/universe_fetch.py", "core/vendor_data.py",
    "module_asymmetric_growth/history.py", "module_comovement/history.py", "module_earnings_radar/earnings_store.py",
    "module_earnings_radar/history.py", "module_earnings_radar/inputs/__init__.py",
    "module_earnings_radar/inputs/_common.py", "module_earnings_radar/inputs/cftc_cot.py",
    "module_earnings_radar/inputs/earnings_calendar.py", "module_earnings_radar/inputs/estimates.py",
    "module_earnings_radar/inputs/macro.py", "module_earnings_radar/inputs/short_interest.py",
    "module_earnings_radar/inputs/vol_index.py", "module_financials/history.py", "module_fundamentals/history.py",
    "module_leaps/history.py", "module_oipd/history.py", "module_relatedness/history.py", "module_sec_13f/history.py",
    "module_sec_13f/universe_info.py", "module_sector_rotation/history.py", "module_spx_gamma/history.py",
    "module_swing_potential/history.py", "module_swing_potential/ohlc_cache.py", "module_value_chain/history.py",
    "module_value_chain/sync.py", "scripts/compact_store.py", "scripts/daily_bars.py", "scripts/index_lists.py",
    "scripts/migrate_board_store.py", "scripts/migrate_rawdata_to_duckdb.py", "scripts/nightly_inputs.py",
})


def _dotted(rel: str) -> str:
    mod = "revenuechaser." + rel[:-3].replace("/", ".")
    return mod[: -len(".__init__")] if mod.endswith(".__init__") else mod


_REMOVED_DOTTED = frozenset(_dotted(r) for r in REMOVED_MODULES)


def _code_files():
    """Every tracked Python file that is code, not a test: the tests may still build an old file to prove it is
    refused, and dot folders (``.bookkeeping``, ``.claude``) hold notes, not code."""
    out = subprocess.run(["git", "ls-files", "*.py"], cwd=_REPO, capture_output=True, text=True, check=True).stdout
    for rel in out.split():
        parts = rel.split("/")
        if parts[0].startswith(".") or parts[0] == "module_testing" or "tests" in parts or parts[-1] == "conftest.py":
            continue
        path = _REPO / rel
        if path.exists():
            yield rel, ast.parse(path.read_text(encoding="utf-8"))


def _docstrings(tree) -> set[int]:
    """The string nodes that are prose: docstrings and bare string statements."""
    return {id(n.value) for n in ast.walk(tree) if isinstance(n, ast.Expr) and isinstance(n.value, ast.Constant)}


def _module_of(rel: str, node: ast.ImportFrom) -> str:
    if not node.level:
        return node.module or ""
    base = _dotted(rel).split(".")
    if not rel.endswith("__init__.py"):          # a package's __init__ is the package; a module sits inside one
        base = base[:-1]
    base = base[: len(base) - (node.level - 1)]
    return ".".join(base + ([node.module] if node.module else []))


@pytest.mark.parametrize("db", OLD_DBS)
def test_the_store_refuses_an_old_file(db):
    assert db not in rawstore.BOARD_DBS
    with pytest.raises(rawstore.RawStoreError):
        rawstore._db_path(db)


def test_every_manifest_table_lives_in_a_board_file():
    stray = {n: s.get("db") for n, s in rawstore.MANIFEST.items()
             if s.get("db") not in rawstore.BOARD_DBS and n != "store_schema"}
    assert not stray, f"MANIFEST tables outside the board files: {stray}"


def test_no_code_names_an_old_store_file():
    found = []
    for rel, tree in _code_files():
        prose = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in prose \
                    and _OLD_FILE.search(node.value):
                found.append(f"{rel}:{node.lineno}: {node.value[:80]!r}")
    assert not found, "code names an old store file:\n" + "\n".join(found)


def test_no_store_call_is_sent_to_an_old_file():
    found = []
    for rel, tree in _code_files():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            for kw in node.keywords:
                if kw.arg == "db" and isinstance(kw.value, ast.Constant) and kw.value.value in OLD_DBS:
                    found.append(f"{rel}:{node.lineno}: db={kw.value.value!r}")
    assert not found, "store calls sent to an old file:\n" + "\n".join(found)


def test_no_removed_module_comes_back():
    back = sorted(r for r in REMOVED_MODULES if (_REPO / r).exists())
    assert not back, f"modules removed with the old store are back: {back}"


def test_no_code_imports_a_removed_module():
    found = []
    for rel, tree in _code_files():
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                mod = _module_of(rel, node)
                names = [mod, *(f"{mod}.{a.name}" for a in node.names)]
            elif isinstance(node, ast.Constant) and isinstance(node.value, str):
                names = [node.value]                       # importlib.import_module("revenuechaser....")
            else:
                continue
            hit = [n for n in names if n in _REMOVED_DOTTED]
            if hit:
                found.append(f"{rel}:{node.lineno}: {hit[0]}")
    assert not found, "code imports a module removed with the old store:\n" + "\n".join(found)
