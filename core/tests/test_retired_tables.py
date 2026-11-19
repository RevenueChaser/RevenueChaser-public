"""No live SQL names a retired table of the removed stores (#209 T2).

``#860`` (15 Nov 2026) removed ``raw.duckdb``, ``edgar.duckdb``, ``history.duckdb`` and ``.store/prices.duckdb``
with every code path to them. ``test_no_old_store.py`` keeps those **files**, and the modules that went with them,
from coming back. Nothing kept a **table name** from coming back: a reader of ``swing_ohlc`` could be written
today and CI would not say so. This is that half.

What it reads: every ``.py`` in the tree, parsed with ``ast``; of its string constants, only the ones that look
like SQL, and never a docstring. A retired name in a comment or a docstring is **provenance and stays** — several
modules say in prose which table they used to read and which issue took its last reader, and that prose is the
only record outside ``.bookkeeping/``. Searching prose would delete the history to satisfy the guard.

``rawstore.RETIRED_TABLES`` is the list, and it is deliberately short: measured 19 Nov 2026, the old stores'
42 recorded table names leave 35 outside ``MANIFEST``, but most of those 35 are worn by something live — an
``rcdata`` bridge view under the old name (decision D4), a key of the serving layer's old-name mapping, a provider
method, a module. The constant's own comment lists each trap. Fifteen names are retired with nothing live wearing
them, and those are the ones guarded.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from RevenueChaser.core import rawstore

_REPO = Path(__file__).resolve().parents[2]

#: Folders with no live SQL in them: the bookkeeping notes record the old stores on purpose, and a test may name a
#: retired table to prove it is refused.
SKIP = ("/.bookkeeping/", "/.hermes/", "/.git/", "/tests/", "/test_")

#: A string counts as SQL only with one of these in it. Narrow on purpose: a docstring that merely mentions a
#: table is not SQL, and a false positive here would be answered by deleting provenance.
SQL_MARKERS = ("select ", "insert into", "update ", "delete from", "create table", "create or replace view",
               "create view", " from ", " join ")


def _sql_strings(tree: ast.AST) -> list[str]:
    """Every string constant that looks like SQL, with the docstrings removed first."""
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str) and id(node) not in docstrings:
            low = node.value.lower()
            if any(m in low for m in SQL_MARKERS):
                out.append(node.value)
    return out


def _files() -> list[Path]:
    return [p for p in _REPO.rglob("*.py")
            if not any(part in f"/{p.relative_to(_REPO).as_posix()}" for part in SKIP)]


def test_the_retired_list_is_real_and_disjoint_from_the_manifest():
    """Each retired name carries its reason, and none of them is a table the store still keeps."""
    assert rawstore.RETIRED_TABLES, "RETIRED_TABLES is empty: the #209 T2 guard has nothing to guard"
    for name, why in rawstore.RETIRED_TABLES.items():
        assert name == name.lower() and " " not in name, f"{name!r} is not a table name"
        assert len(why) > 20, f"{name} has no reason beside it; say which issue took its last reader"
    clash = sorted(set(rawstore.RETIRED_TABLES) & set(rawstore.MANIFEST))
    assert not clash, f"these are both retired and in MANIFEST, so one of the two is wrong: {clash}"


def test_no_live_sql_names_a_retired_table():
    found: list[str] = []
    for path in _files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                      # not ours to police
            continue
        for sql in _sql_strings(tree):
            low = sql.lower()
            for name in rawstore.RETIRED_TABLES:
                if name in low:
                    rel = path.relative_to(_REPO).as_posix()
                    found.append(f"{rel}: SQL names the retired {name!r} "
                                 f"({rawstore.RETIRED_TABLES[name]})")
    assert not found, (
        "a retired table is back in live SQL:\n  " + "\n  ".join(sorted(set(found)))
        + "\n\nThe table is gone with its store (#860). Read the serving layer instead, or, if the name is a live "
          "rcdata bridge view now, take it off rawstore.RETIRED_TABLES and say why there.")


@pytest.mark.parametrize("name", ["swing_ohlc", "sec_company_tickers", "ticker_payload_cache"])
def test_the_names_the_issue_itself_named_are_guarded(name):
    """#209's evidence named these three readers; the guard covers all three."""
    assert name in rawstore.RETIRED_TABLES
