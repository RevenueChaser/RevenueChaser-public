"""Plan v31 step 1(e), 1(f) and G-F: what the board serves.

(e) customer and supplier rows only; (f) a profile edge only once the census clears ``SERVE_PROFILE_EDGES``, which
is off by default and read where the board is served, so the store keeps every edge; G-F (#284) the payload says
when a sync found no edge and kept the stored ones.
"""
from __future__ import annotations

from RevenueChaser.core import rawstore
from RevenueChaser.module_value_chain import config, engine, report


def _edge(dst, relation, source):
    return {"src": "AMKR", "dst_name": dst, "dst_ticker": dst, "relation": relation, "snippet": "s",
            "filed": "2026-02-01", "source": source}


EDGES = [_edge("AAPL", "customer", "xbrl"), _edge("TSM", "supplier", "profile"), _edge("INTC", "competitor", "profile"),
         _edge("MSFT", "other", "regex")]


def test_the_board_serves_customer_and_supplier_rows_and_no_profile_edge_by_default(rawstore_tmp_db):
    assert config.SERVE_PROFILE_EDGES is False
    payload = engine._board_payload([], EDGES, "x", None)
    assert [(e["dst_ticker"], e["source"]) for e in payload["edges"]] == [("AAPL", "xbrl")]
    assert payload["profile_hidden"] == 1


def test_the_switch_serves_profile_edges_without_a_resync(rawstore_tmp_db, monkeypatch):
    monkeypatch.setattr(config, "SERVE_PROFILE_EDGES", True)
    payload = engine._board_payload([], EDGES, "x", None)
    assert {(e["dst_ticker"], e["source"]) for e in payload["edges"]} == {("AAPL", "xbrl"), ("TSM", "profile")}
    assert payload["profile_hidden"] == 0


def test_the_store_keeps_what_the_board_holds_back(rawstore_tmp_db):
    rawstore.ensure_table("chain_mentions")
    rawstore.write_rows("chain_mentions", EDGES)
    assert {e["dst_ticker"] for e in engine.load_payload()["edges"]} == {"AAPL"}
    assert len(rawstore.get_all("chain_mentions")) == 4


def test_a_sync_that_kept_the_stored_edges_says_so(rawstore_tmp_db, monkeypatch):
    rawstore.ensure_table("chain_mentions")
    rawstore.write_rows("chain_mentions", [EDGES[0]])
    monkeypatch.setattr(engine, "fetch_corpus", lambda **k: {"no_fetch": False})

    def _kept(info=None):
        info.update(filings=3, kept=True, retired=0)
        return rawstore.get_all("chain_mentions")

    monkeypatch.setattr(engine, "build_edges", _kept)
    assert engine.run(no_fetch=False)["kept"] is True
    assert engine.load_payload()["kept"] is True                # a Refresh reads it from the store
    html = report.render_value_chain_dashboard(engine.load_payload())
    assert "Edges from an earlier run" in html


def test_a_sync_with_edges_is_not_kept(rawstore_tmp_db, monkeypatch):
    monkeypatch.setattr(engine, "fetch_corpus", lambda **k: {"no_fetch": False})
    monkeypatch.setattr(engine, "build_edges", lambda info=None: info.update(kept=False) or [EDGES[0]])
    assert engine.run(no_fetch=False)["kept"] is False
    assert "Edges from an earlier run" not in report.render_value_chain_dashboard(engine.load_payload())


def test_the_board_says_how_many_profile_links_wait_for_the_census():
    html = report.render_value_chain_dashboard({"as_of": "", "filings": [], "edges": [], "profile_hidden": 7})
    assert "Profile relationships not yet verified: 7 links" in html
    assert "not yet verified" not in report.render_value_chain_dashboard({"as_of": "", "filings": [], "edges": []})
