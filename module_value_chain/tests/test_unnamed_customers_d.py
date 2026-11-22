"""D (owner, 17 Nov 2026): a customer the filing does not name ("Customer One", "big customer") is no node on the
graph; the company's row says "also N unnamed customers". Serving only: the stored rows stay."""
from __future__ import annotations

import json

import pytest

from revenuechaser.core import rawstore
from revenuechaser.module_value_chain import aliases, config, engine, report


@pytest.mark.parametrize("name, want", [
    ("Customer A", True), ("Customer 1", True), ("Customer One", True), ("One customer", True),
    ("big customer", True), ("Largest Customer", True), ("Distributor B", True), ("customers", True),
    ("Apple Inc.", False), ("Customer Service Corp", False), ("McKesson Corporation", False), ("", False),
])
def test_unnamed(name, want):
    assert aliases.unnamed(name) is want


def _edge(dst_name, dst_ticker, source="profile"):
    return {"src": "MSFT", "dst_name": dst_name, "dst_ticker": dst_ticker, "relation": "customer",
            "snippet": "s", "filed": "2025-07-30", "source": source}


def test_the_board_hides_unnamed_customers_and_counts_them_on_the_row(rawstore_tmp_db, monkeypatch):
    monkeypatch.setattr(config, "SERVE_PROFILE_EDGES", True)
    rawstore.ensure_table("chain_meta")
    rawstore.write_rows("chain_meta", [{"key": "unnamed_customers",
                                        "value": json.dumps({"MSFT": ["Customer A", "customer one"]})}])
    edges = [_edge("Apple Inc.", "AAPL"), _edge("Customer One", ""), _edge("big customer", "")]
    filing = {"ticker": "MSFT", "form": "10-K", "filed": "2025-07-30", "quality": "ok", "primary_doc": "d"}
    payload = engine._board_payload([filing], edges, "x", None)
    assert [e["dst_ticker"] for e in payload["edges"]] == ["AAPL"]
    (row,) = payload["filings"]
    assert row["unnamed_customers"] == 3       # Customer A, Customer One (both sources), big customer
    html = report.render_value_chain_dashboard(payload)
    assert '"unnamed_customers": 3' in html
    assert "unnamed customers: the filing does not name them" in html


def test_a_sync_stores_the_unnamed_customers_for_a_refresh(rawstore_tmp_db, monkeypatch):
    monkeypatch.setattr(engine, "fetch_corpus", lambda **k: {"no_fetch": False})
    monkeypatch.setattr(engine, "build_edges",
                        lambda info=None: info.update(kept=False, unnamed={"MSFT": ["Customer B"]}) or [])
    engine.run(no_fetch=False)
    # chain_meta.value is a JSON column: it can read back as a dict
    assert engine._json_dict(rawstore.get("chain_meta", "unnamed_customers")["value"]) == {"MSFT": ["Customer B"]}
