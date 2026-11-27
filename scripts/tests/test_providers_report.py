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


def test_every_dataset_card_is_read_with_a_label():
    """``screen.py``'s ``DATASETS`` is the registry that holds the jobs ``NAME`` alone misses."""
    cards = providers_report.dataset_cards()
    flat = {name: label for rows in cards.values() for name, label in rows}
    # the six the NAME-only scan missed (endpoint review, 27 Nov 2026, claude-coordinator PR #1524)
    for missed in ("wrds/funda", "wrds/fundq", "wrds/segments", "wrds/exrt",
                   "yfinance/float", "tradingview/float"):
        assert missed in flat, missed
    assert len(flat) > 40, "the DATASETS map was not parsed"
    assert all(flat.values()), "a dataset card was read without its label"


def test_a_name_that_is_a_label_and_not_a_fetch_is_not_read_as_a_dataset():
    """``wrds/compustat`` and ``wrds/crsp`` tag ``price_bar_daily``'s rows; neither is a job."""
    flat = {n for rows in providers_report.dataset_cards().values() for n, _ in rows}
    assert "wrds/compustat" not in flat and "wrds/crsp" not in flat
    assert "wrds/prices" in flat                                   # the fetch those two labels come from


def test_every_dataset_card_prefix_is_a_provider_or_one_of_our_own_lanes():
    cards = providers_report.dataset_cards()
    known = set(providers_report.needs_by_provider())
    _, internal = providers_report.builders(known)
    lanes = {job.split("/", 1)[0] for job in internal}
    unplaced = set(cards) - known - lanes
    assert not unplaced, f"a dataset card names something that is neither: {sorted(unplaced)}"


def test_a_reader_declared_outside_rcdata_is_reported():
    """``module_news/x_lane.py`` declares ``PROVIDER = "x-follow"`` and has no ``Need(...)`` of its own."""
    outside = providers_report.module_providers()
    assert "x-follow" in outside and outside["x-follow"].startswith("module_news/")
    inv = providers_report.inventory()
    row = next(p for p in inv["providers"] if p["provider"] == "x-follow")
    assert row["in_need_catalog"] is False and row["declared_outside_rcdata"]


def test_the_source_enum_is_read_and_not_mistaken_for_the_provider_list():
    """``core/datasets.py``'s ``Source`` is a per-dataset label: it names fewer providers than the code has."""
    inv = providers_report.inventory()
    enum = inv["source_enum"]
    assert {"uw", "sec", "yfinance"} <= set(enum)
    assert len(enum) < inv["totals"]["providers_in_code"]
    assert "derived" in inv["source_enum_not_a_provider"]
