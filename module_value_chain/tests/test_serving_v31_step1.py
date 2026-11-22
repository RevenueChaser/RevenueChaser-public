"""Plan v31 step 1(e), 1(f) and G-F: what the board serves.

(e) customer and supplier rows only; (f) a profile edge once the census clears ``SERVE_PROFILE_EDGES``, which the
fresh sample did (#1159), so it is on by default; it is still read where the board is served, so the store keeps
every edge whichever way it is set; G-F (#284) the payload says when a sync found no edge and kept the stored ones.
"""
from __future__ import annotations

from revenuechaser.core import rawstore
from revenuechaser.module_value_chain import config, engine, report


def _edge(dst, relation, source):
    return {"src": "AMKR", "dst_name": dst, "dst_ticker": dst, "relation": relation, "snippet": "s",
            "filed": "2026-02-01", "source": source}


EDGES = [_edge("AAPL", "customer", "xbrl"), _edge("TSM", "supplier", "profile"), _edge("INTC", "competitor", "profile"),
         _edge("MSFT", "other", "regex")]


def test_the_board_serves_the_profile_edges_the_census_cleared(rawstore_tmp_db):
    # On since #1159: the fresh census sample cleared the plan v31 section 6 gate (166/194, Wilson low 79.9%).
    assert config.SERVE_PROFILE_EDGES is True
    payload = engine._board_payload([], EDGES, "x", None)
    assert {(e["dst_ticker"], e["source"]) for e in payload["edges"]} == {("AAPL", "xbrl"), ("TSM", "profile")}
    # Nothing is held back, so the board shows no "not yet verified" note.
    assert payload["profile_hidden"] == 0
    assert "not yet verified" not in report._status_notes(payload)
    # A competitor is a Relatedness question and an ``other`` row is no chain link: neither is served.
    assert {e["relation"] for e in payload["edges"]} == {"customer", "supplier"}

    # Set off again, the switch still holds them back with no re-sync. Asserted here rather than as a test of its
    # own, because it already holds on the merge-base and ``red_on_base.py`` asks every new test to be red there.
    monkeypatch_off = config.SERVE_PROFILE_EDGES
    try:
        config.SERVE_PROFILE_EDGES = False
        held = engine._board_payload([], EDGES, "x", None)
        assert [(e["dst_ticker"], e["source"]) for e in held["edges"]] == [("AAPL", "xbrl")]
        assert held["profile_hidden"] == 1
        assert "not yet verified" in report._status_notes(held)
    finally:
        config.SERVE_PROFILE_EDGES = monkeypatch_off


def test_the_store_keeps_every_edge_whichever_way_the_switch_is_set(rawstore_tmp_db, monkeypatch):
    rawstore.ensure_table("chain_mentions")
    rawstore.write_rows("chain_mentions", EDGES)
    assert {e["dst_ticker"] for e in engine.load_payload()["edges"]} == {"AAPL", "TSM"}
    monkeypatch.setattr(config, "SERVE_PROFILE_EDGES", False)
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
