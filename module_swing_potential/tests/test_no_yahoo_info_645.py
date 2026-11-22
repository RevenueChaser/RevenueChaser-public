"""The Swing indicators module reads nothing from Yahoo (#645, after #996).

The board's last Yahoo link was ``load_ticker_info``: one ``.info`` request per scored name, cached in
``swing_info``. #996 took its caller -- ``_compute_row`` reads the company name off the spine row -- and the
function stayed behind with no non-test caller, importing ``yfinance`` and the 401 watcher and keeping a cache
table in ``boards/swing_potential.duckdb``. This is written over the module's **source**, not over an allowlist,
so it is red on a base that still holds the function.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from revenuechaser.core import rawstore

_REPO = Path(__file__).resolve().parents[2]
_INDICATORS = _REPO / "module_swing_potential" / "indicators.py"


def _imported_modules(path: Path) -> set[str]:
    """Every module name the file imports, at module level or inside a function."""
    out: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            out.add(node.module)
            out.update(f"{node.module}.{a.name}" for a in node.names)
    return out


def test_the_indicators_module_imports_no_yahoo():
    """``yfinance``, the provider client and the 401 watcher are all gone: the file is pure again."""
    imported = _imported_modules(_INDICATORS)
    named = sorted(m for m in imported if "yfinance" in m or "yf_session" in m or "info_fallback" in m)
    assert not named, f"module_swing_potential/indicators.py still imports Yahoo: {named}"


def test_no_function_of_the_module_fetches_ticker_info():
    from revenuechaser.module_swing_potential import indicators
    assert not hasattr(indicators, "load_ticker_info"), (
        "#645: the board takes the company name from the spine row; nothing reads Yahoo .info")


def test_the_info_cache_is_no_longer_a_table_of_the_store():
    """The cache went with its only writer, so the store does not keep it and a reader is refused by name."""
    assert "swing_info" not in rawstore.MANIFEST
    assert "swing_info" in rawstore.RETIRED_TABLES
    with pytest.raises(rawstore.RawStoreError):
        rawstore.get("swing_info", "AAPL")


def test_the_board_declares_no_yahoo_dataset():
    """Settings' Data inventory listed the cache as a yfinance dataset of the Swing file; it has none now."""
    from revenuechaser.core import datasets
    swing = [d for d in datasets.REGISTRY if d.db == "swing_potential"]
    assert swing, "the Swing board has no dataset at all; this test is reading the wrong field"
    assert all(d.source is not datasets.Source.yfinance for d in swing), \
        [d.key for d in swing if d.source is datasets.Source.yfinance]
