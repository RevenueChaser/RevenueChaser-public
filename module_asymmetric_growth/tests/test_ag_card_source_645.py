"""The card's provenance names no provider (#645).

Asymmetric Growth reads EDGAR only since avo's option A of 10 Nov 2026: ``_cached_financials`` returns the stored
SEC figures or None, and a name with no SEC annual data gets no card. So the card's ``source`` is EDGAR's, and the
old ``or "yfinance"`` default could only mislabel a card and have ``_summary`` count it under ``unreadable_sec``.

The guard is over the module's own source, not over a list of allowed files, so it is red on the base (#1213).
"""
from __future__ import annotations

import ast
import pathlib

from revenuechaser.module_asymmetric_growth import engine

PROVIDERS = ("yfinance", "yahoo", "unusual_whales", "finnhub", "polygon")


def _value_literals(path: pathlib.Path) -> list[str]:
    """Every string constant of ``path`` that is not a docstring: the values the module hands to a card."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            first = (node.body or [None])[0]
            if isinstance(first, ast.Expr) and isinstance(first.value, ast.Constant) \
                    and isinstance(first.value.value, str):
                docstrings.add(id(first.value))
    return [n.value for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and isinstance(n.value, str) and id(n) not in docstrings]


def test_the_engine_carries_no_provider_name_as_a_value() -> None:
    path = pathlib.Path(engine.__file__)
    named = sorted({p for text in _value_literals(path) for p in PROVIDERS if p in text.lower()})
    assert named == [], f"{path.name} names a provider in a value it can hand to a card: {named}"


def test_the_card_source_has_no_provider_default() -> None:
    assert engine.EDGAR_SOURCE == "sec_edgar"
    source = """        "source": financials.get("source"),"""
    assert source in pathlib.Path(engine.__file__).read_text(encoding="utf-8")
