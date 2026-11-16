"""Value Chain reads the shared SEC layer (plan 2026-11-11 WP2a, #410 part 1; the form reader since #841).

``chain_filings`` held 377 filings; the layer holds every company's newest annual report. Since #841 the business
text is the SEC form reader's (``sec/forms``, ``filing_section``) and not ``sec/filings``' second cut of the same
documents (``filing_item``): on the layer the edges come from the form reader's section, the board's filing list is
its rows, and a Fetch downloads nothing into ``chain_filings`` (Relatedness's Fetch calls the same
``fetch_corpus``). Off the layer nothing changes. A free-text company name resolves to one ticker through the alias
rules, then the spine.
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import fundamentals_layer, rawstore
from RevenueChaser.core.providers import sec_edgar
from RevenueChaser.module_value_chain import aliases, engine
from RevenueChaser.module_value_chain.tests.test_value_chain_profile_edges_410 import _profile
from RevenueChaser.rcdata.build.fundamentals import companyfacts, filings
from RevenueChaser.rcdata.build.sec_forms import forms
from RevenueChaser.rcdata.tests import fund_fixture as fx
from RevenueChaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401  (fixtures)

STATED = "Direct sales to Apple accounted for 29.8% of our net sales. "


@pytest.fixture
def layer(monkeypatch, http_mock):  # noqa: F811
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec_edgar, "SEC_DATA_BASE", "https://data.sec.test")
    fx.spine()
    fx.sec_routes(http_mock, {"789019": fx.msft_facts()})
    ten_k = fx.ten_k().replace("<p>Item 1. Business</p><p>", "<p>Item 1. Business</p><p>" + STATED * 40, 1)
    fx.filing_routes(http_mock, {"789019": fx.submissions(789019, fx.MSFT_FILINGS, "MICROSOFT CORP")},
                     {"msft-10k.htm": ten_k, "msft-def14a.htm": fx.proxy()})
    fx.run(companyfacts.NAME, mode="backfill", to="2026-10-26")
    fx.run(filings.NAME, mode="backfill", to="2026-10-28")
    fx.run(forms.NAME, "2026-10-28")               # #841: the business text is the form reader's (``sec/forms``)
    assert fundamentals_layer.reads_layer()
    monkeypatch.setattr(engine, "_default_tickers", lambda: ["MSFT", "ORCL"])
    return http_mock


def test_a_layer_filer_gets_its_edges_from_its_profile_not_its_text(layer):
    # #748: the share sentence in the layer's text is no longer scanned; without a profile it gives no edge.
    assert not [e for e in engine.build_edges() if e["src"] == "MSFT" and e["dst_ticker"] == "AAPL"]
    _profile("MSFT")
    edges = [e for e in engine.build_edges() if e["src"] == "MSFT" and e["dst_ticker"] == "AAPL"]
    assert [(e["relation"], e["source"]) for e in edges] == [("customer", "profile")]
    assert rawstore.get_all("chain_filings") == []


def test_the_board_lists_the_layers_filings_without_text(layer):
    (row,) = engine._board_filings_rows()
    assert (row["ticker"], row["form"], row["filed"], row["accession"]) == ("MSFT", "10-K", "2025-07-30", fx.K25)
    assert "item_text" not in row and "text" not in row
    # #841: ``primary_doc`` is the form row's ``document``, the stored file the section was cut out of, and no
    # longer the SEC's primary-document name. The layer path never carried a URL either (``chain_filings`` stores
    # the full URL, the layer stored the bare name), so this is the same field with the form reader's value in it.
    assert row["primary_doc"] == f"{fx.K25}.html.gz"



def test_a_corpus_row_carries_the_period_its_filing_reports_on(layer):
    """Plan v31 step 1(h): the corpus row had ``form``, ``filed`` and ``accession`` but no period, which G-E's
    "as stated in the FY<year> <form>" needs. It is the form row's ``report_date``."""
    (row,) = engine._board_filings_rows()
    assert row["period_end"] == "2025-06-30"
    (full,) = next(engine._corpus_batches())
    assert full["period_end"] == "2025-06-30"

def test_the_corpus_is_the_form_reader_and_not_filing_item(layer, monkeypatch):
    """#841: the two read sites ask ``sec/forms`` only. ``filing_item`` is ``sec/filings``' own second cut of the
    same documents, and a board that still touched it would keep both rules alive at once."""
    from RevenueChaser.rcdata import read

    def refuse(*a, **k):
        raise AssertionError("the board must not read filing_item any more (#841)")

    monkeypatch.setattr(read, "filing_texts", refuse)
    monkeypatch.setattr(read, "filing_text", refuse)
    _profile("MSFT")
    assert [r["ticker"] for r in engine._board_filings_rows()] == ["MSFT"]
    assert any(e["dst_ticker"] == "AAPL" for e in engine.build_edges())


def test_a_row_cut_with_another_rules_version_is_read_and_logged(layer, monkeypatch, caplog):
    """The pin may sit ahead of the stored cut (``splitter``'s docstring). Such a row is the corpus all the same:
    dropping it would empty the board instead of showing what it has."""
    monkeypatch.setattr(engine.splitter, "VERSION", "ours-9")
    with caplog.at_level("WARNING"):
        rows = engine._board_filings_rows()
    assert [r["ticker"] for r in rows] == ["MSFT"]
    assert "not ours-9" in caplog.text


def test_a_fetch_downloads_nothing_on_the_layer(layer):
    got = engine.fetch_corpus()
    assert (got["corpus"], got["cached"], got["pending"], got["fetched"]) == ("layer", 1, 1, 0)
    assert rawstore.get_all("chain_filings") == []


def test_the_layer_is_not_the_corpus_before_sec_forms_has_built(layer, monkeypatch):
    from RevenueChaser.rcdata import ops
    built = ops.ever_built
    monkeypatch.setattr(ops, "ever_built", lambda name: name != forms.NAME and built(name))
    assert fundamentals_layer.reads_layer() and engine._board_filings_rows() == []
    assert engine.fetch_corpus(no_fetch=True).get("corpus") is None


def test_a_missing_slice_with_a_suspect_flag_has_no_text():
    """``quality`` can carry the suspect flags (#835), so the guard reads the label through ``splitter.base``:
    ``missing;suspect:S1`` is still missing and its stored text is not scanned."""
    rawstore.write_rows("chain_filings", [{"ticker": "MSFT", "cik": "789019", "form": "10-K", "filed": "2025-07-30",
                                           "accession": "a", "primary_doc": "u", "item_text": STATED,
                                           "quality": "missing;suspect:S1", "fetched_at": 1.0}])
    assert not [e for e in engine.build_edges() if e["dst_ticker"] == "AAPL"]


def test_off_the_layer_the_corpus_is_chain_filings():
    rawstore.write_rows("chain_filings", [{"ticker": "MSFT", "cik": "789019", "form": "10-K", "filed": "2025-07-30",
                                           "accession": "a", "primary_doc": "u", "item_text": STATED,
                                           "quality": "ok", "fetched_at": 1.0}])
    _profile("MSFT")
    assert [r["ticker"] for r in engine._board_filings_rows()] == ["MSFT"]
    assert any(e["dst_ticker"] == "AAPL" for e in engine.build_edges())


SPINE = aliases.spine_names([{"ticker": "MCK", "name": "McKesson Corp"}, {"ticker": "ABC1", "name": "Acme Holdings"},
                             {"ticker": "ABC2", "name": "ACME Inc"}])


@pytest.mark.parametrize("name, ticker", [
    ("Apple Inc.", "AAPL"),                 # the alias list
    ("Mc Kesson Corporation", "MCK"),       # the spine
    ("Apple Pay", None),                    # a product, not a company
    ("Apple and Dell", None),               # two companies
    ("Acme", None),                         # a name two issuers share
    ("Customer A", None),
    ("", None),
])
def test_resolve(name, ticker):
    assert (aliases.resolve(name, SPINE) or {}).get("ticker") == ticker


def test_resolve_rate_counts_each_field():
    profiles = {"VRTX": {"customers": [{"name": "Mc Kesson Corporation"}, {"name": "Customer A"}],
                         "suppliers": [{"name": "Lonza"}], "named_competitors": ["Apple"]},
                "X": {"customers": [], "suppliers": None}}
    got = aliases.resolve_rate(profiles, SPINE)
    assert got["customers"] == {"names": 2, "resolved": 1, "rate": 0.5}
    assert got["suppliers"] == {"names": 1, "resolved": 0, "rate": 0.0}
    assert got["named_competitors"]["resolved"] == 1
    assert got["all"] == {"names": 4, "resolved": 2, "rate": 0.5}
