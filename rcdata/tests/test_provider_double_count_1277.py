"""One provider call is counted by one side only (#1277).

A builder dataset counts every provider call it asks for with ``ctx.count``, and the day's spend ledger
(``core/providers/spend.py``) is the same ``provider_calls_daily`` row. So a dataset that reads through a
``core/providers`` client which also counts there books the call twice: ``rcdata.caps`` then stops the build at
half the reads the cap allows, and the Spend card overstates the day.

This is a rule over the builder's source, not a list of the files that break it: it reads the call sites and
asks whether each one says who owns the count. The two shapes of "mine", both pinned by their own tests in
``core/providers/tests/test_app_spend_166.py``:

* ``UWClient``: install ``on_request`` **and** ``on_response`` and the client counts nothing (the builder does it
  once for every dataset, ``rcdata/build/base.py`` ``uw_client``).
* ``core/providers/yfinance``: ask inside ``spend_owned_by_caller()``.
"""
from __future__ import annotations

import ast
from pathlib import Path

BUILD = Path(__file__).resolve().parents[1] / "build"

#: The module alias a builder file gives ``core.providers.yfinance``, whatever it imports it as.
_PROVIDER_MODULE = "yfinance"
#: The door that says the caller keeps its own book.
_DOOR = "spend_owned_by_caller"


def _aliases(tree: ast.AST) -> set[str]:
    """The names this module calls ``core.providers.yfinance`` by (``from ... import yfinance as yf_provider``)."""
    out = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == _PROVIDER_MODULE and (node.module or "").endswith("providers"):
                    out.add(alias.asname or alias.name)
    return out


def _unowned_calls(path: Path) -> list[str]:
    """``<file>:<line> <call>`` for every read of the provider module outside a ``_DOOR`` block."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names = _aliases(tree)
    if not names:
        return []
    owned: list[tuple[int, int]] = []          # the line spans of the door's blocks
    for node in ast.walk(tree):
        if not isinstance(node, ast.With):
            continue
        for item in node.items:
            call = item.context_expr
            name = call.func if isinstance(call, ast.Call) else call
            if isinstance(name, ast.Attribute) and name.attr == _DOOR:
                body_end = max(getattr(b, "end_lineno", b.lineno) for b in node.body)
                owned.append((node.body[0].lineno, body_end))
    bad = []
    for node in ast.walk(tree):
        if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)):
            continue
        target = node.func.value
        if not (isinstance(target, ast.Name) and target.id in names):
            continue
        if not node.func.attr.startswith("get_"):          # a read; the pure helpers cost nothing
            continue
        if any(start <= node.lineno <= end for start, end in owned):
            continue
        bad.append(f"{path.name}:{node.lineno} {target.id}.{node.func.attr}")
    return bad


def test_a_builder_read_of_the_yfinance_provider_module_says_who_counts_it():
    offenders = sorted(c for p in BUILD.rglob("*.py") for c in _unowned_calls(p))
    assert offenders == [], (
        "these builder reads go through core/providers/yfinance, which counts them on the day's spend ledger, "
        "while the dataset counts the same call with ctx.count into the same provider_calls_daily row (#1277). "
        f"Ask inside yf_provider.{_DOOR}(): " + ", ".join(offenders))


def test_the_rule_can_see_an_offender():
    """The guard above is only worth its line if it fails on the shape it forbids."""
    import tempfile
    src = (
        "from ....core.providers import yfinance as yf_provider\n"
        "def fetch(ctx):\n"
        "    ctx.count('yfinance', calls=1)\n"
        "    return yf_provider.get_fx_history('CAD', None)\n")
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "offender.py"
        path.write_text(src, encoding="utf-8")
        assert _unowned_calls(path) == ["offender.py:4 yf_provider.get_fx_history"]
        path.write_text(src.replace("    return yf_provider",
                                    "    with yf_provider.spend_owned_by_caller():\n"
                                    "        return yf_provider"), encoding="utf-8")
        assert _unowned_calls(path) == []
