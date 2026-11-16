"""#408: two share classes of one issuer write one set of edges, not two.

GOOG and GOOGL carry the same filing (one CIK) and the same profile, so each wrote the same edges: "Links drawn"
counted them twice and a focal company saw two incoming lines for one filing.
"""
from __future__ import annotations

from RevenueChaser.core import rawstore
from RevenueChaser.module_value_chain import engine
from RevenueChaser.module_value_chain.tests.test_value_chain_profile_edges_410 import _profile


def _filing(ticker: str, cik: str = "1652044") -> dict:
    return {"ticker": ticker, "cik": cik, "form": "10-K", "filed": "2026-02-01", "accession": "a",
            "primary_doc": "u", "item_text": "We make search and cloud products.", "quality": "ok",
            "fetched_at": 1.0}


def test_two_share_classes_write_one_set_of_edges(rawstore_tmp_db):
    rawstore.write_rows("chain_filings", [_filing("GOOG"), _filing("GOOGL")])
    _profile("GOOG")
    _profile("GOOGL")
    edges = engine.build_edges()
    assert edges                                                  # the input really gives edges
    assert {e["src"] for e in edges} == {"GOOGL"}                 # the class aliases.SAME_ISSUER names
    keys = [(e["dst_name"], e["relation"]) for e in edges]
    assert len(keys) == len(set(keys))


def test_a_stored_row_of_the_twin_is_retired(rawstore_tmp_db):
    rawstore.ensure_table("chain_mentions")
    rawstore.write_rows("chain_mentions", [{"src": "GOOG", "dst_name": "Apple Inc.", "dst_ticker": "AAPL",
                                            "relation": "customer", "snippet": "s", "filed": "2025-02-01"}])
    rawstore.write_rows("chain_filings", [_filing("GOOG"), _filing("GOOGL")])
    _profile("GOOG")
    _profile("GOOGL")
    engine.build_edges()
    assert not [r for r in rawstore.get_all("chain_mentions") if r["src"] == "GOOG"]


def test_an_unlisted_pair_keeps_the_first_ticker_and_other_issuers_are_untouched(rawstore_tmp_db):
    rawstore.write_rows("chain_filings", [_filing("UAA", "1336917"), _filing("UA", "1336917"),
                                          _filing("AMKR", "1047127")])
    for t in ("UA", "UAA", "AMKR"):
        _profile(t)
    assert {e["src"] for e in engine.build_edges()} == {"UA", "AMKR"}
