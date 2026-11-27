"""scripts/providers_report.py: the provider inventory is read from the code, and nothing else is.

The script exists because a hand-written list rots. These tests hold the two properties that make it worth
trusting: every provider the need catalog names is in the report, and our own serving lanes are not reported as
providers.
"""
from __future__ import annotations

import ast
import json
from pathlib import Path

from scripts import providers_report

ROOT = Path(providers_report.__file__).resolve().parent.parent


def _catalog_providers() -> set[str]:
    """The ``providers=`` names, read here a second way, so the test does not lean on the script's own parser."""
    src = (ROOT / "rcdata" / "needs" / "catalog.py").read_text(encoding="utf-8")
    found: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Need":
            for kw in node.keywords:
                if kw.arg == "providers":
                    found |= {
                        e.value for e in getattr(kw.value, "elts", [])
                        if isinstance(e, ast.Constant) and isinstance(e.value, str)
                    }
    return found


def test_every_catalog_provider_is_reported():
    inv = providers_report.inventory()
    reported = {p["provider"] for p in inv["providers"] if p["in_need_catalog"]}
    assert reported == _catalog_providers()
    assert inv["totals"]["providers_in_catalog"] == len(_catalog_providers())


def test_catalog_has_more_than_one_provider():
    """A parser that silently matches nothing would pass the equality above against an empty set."""
    assert len(_catalog_providers()) > 10


def test_our_own_serving_lanes_are_not_providers():
    inv = providers_report.inventory()
    names = {p["provider"] for p in inv["providers"]}
    for lane in ("prices", "ownership", "spine", "fundamentals", "delisted", "regsho", "funds", "public"):
        assert lane not in names, f"{lane} is a serving lane of ours, not a provider"
    assert any(job.startswith("prices/") for job in inv["internal_jobs"])


def test_providers_outside_the_catalog_are_flagged_not_dropped():
    """``openfigi`` is a builder's PROVIDER with no need of its own; a report that drops it is wrong."""
    inv = providers_report.inventory()
    outside = {p["provider"] for p in inv["providers"] if not p["in_need_catalog"]}
    assert "openfigi" in outside


def test_markdown_and_json_both_render():
    inv = providers_report.inventory()
    text = providers_report.markdown(inv)
    assert "| Provider |" in text and "`sec`" in text
    assert json.loads(json.dumps(inv))["totals"]["needs"] > 0


def test_market_sources_and_helpers_are_read():
    inv = providers_report.inventory()
    assert {"treasury", "bls", "cboe", "fred"} <= set(inv["market_sources"])
    assert "tickerinside" in inv["helper_modules"]
