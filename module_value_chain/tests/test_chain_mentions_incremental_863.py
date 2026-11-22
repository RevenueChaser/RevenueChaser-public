"""``build_edges`` writes ``chain_mentions`` incrementally (#863, plan 2026-11-08 §10 rule 3).

The board file's table is never rewritten whole: the run's edges are upserted by key and only the stored keys of
the tickers the run scanned that it no longer produces are deleted, in the same transaction.
"""
from __future__ import annotations

from revenuechaser.core import rawstore
from revenuechaser.module_value_chain import engine
from revenuechaser.module_value_chain.tests.test_value_chain import _TEN_K
from revenuechaser.module_value_chain.tests.test_value_chain_profile_edges_410 import _profile
from revenuechaser.rcdata.tests.conftest import market_roots  # noqa: F401  (fixture)

_NVDA_FILING = {"ticker": "NVDA", "cik": "1", "form": "10-K", "filed": "2026-02-01", "accession": "acc",
                "primary_doc": "http://x", "item_text": _TEN_K, "quality": "ok"}


def _edge(src, dst_name, relation="supplier"):
    return {"src": src, "dst_name": dst_name, "dst_ticker": "", "relation": relation, "snippet": "s",
            "filed": "2025-02-01"}


def _keys():
    return {(r["src"], r["dst_name"], r["relation"]) for r in rawstore.get_all("chain_mentions")}


def test_a_scanned_ticker_retires_only_the_keys_it_no_longer_produces(rawstore_tmp_db, market_roots):  # noqa: F811
    rawstore.ensure_table("chain_mentions")
    rawstore.write_rows("chain_mentions", [_edge("NVDA", "GONE CORP")])
    rawstore.write_rows("chain_filings", [_NVDA_FILING])
    _profile("NVDA")                       # the run's edges come from a profile since the text scans went (#748)
    info: dict = {}
    edges = engine.build_edges(info)
    assert ("NVDA", "GONE CORP", "supplier") not in _keys()
    assert info["retired"] == 1
    assert _keys() == {(e["src"], e["dst_name"], e["relation"]) for e in edges}


def test_a_ticker_the_run_did_not_scan_keeps_its_edges(rawstore_tmp_db):
    rawstore.ensure_table("chain_mentions")
    rawstore.write_rows("chain_mentions", [_edge("AAPL", "FOXCONN")])
    rawstore.write_rows("chain_filings", [_NVDA_FILING])
    info: dict = {}
    edges = engine.build_edges(info)
    assert ("AAPL", "FOXCONN", "supplier") in _keys()
    assert info["retired"] == 0
    # what is returned is what the store holds, so the board, n_mentions and a later Refresh agree
    assert {(e["src"], e["dst_name"], e["relation"]) for e in edges} == _keys()


def test_a_text_less_filing_does_not_retire_its_tickers_edges(rawstore_tmp_db):
    rawstore.ensure_table("chain_mentions")
    rawstore.write_rows("chain_mentions", [_edge("AMD", "TSMC")])
    rawstore.write_rows("chain_filings", [_NVDA_FILING, {**_NVDA_FILING, "ticker": "AMD", "cik": "2",
                                                         "quality": "missing", "item_text": ""}])
    engine.build_edges()
    assert ("AMD", "TSMC", "supplier") in _keys()
