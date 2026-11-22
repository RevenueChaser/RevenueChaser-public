"""#894 step 4: Value Chain's company profiles come from the SEC reading service, not from the Relatedness table.

Before this the board read ``relatedness_profiles.profile_json`` and its ``accession`` column, so a profile
reached Value Chain only once the Relatedness board had imported it into its own table. The service owns every
SEC model read (avo, 15 Nov 2026), so the board reads ``read.sec_reads(..., "company.profile")`` instead, keyed
by the CIK its own corpus row states.
"""
from __future__ import annotations

import json

from revenuechaser.core import rawstore
from revenuechaser.module_value_chain import engine
from revenuechaser.module_value_chain.tests.test_value_chain_profile_edges_410 import (PROFILE, _filing,
                                                                                   _profile, serve_answers)
from revenuechaser.rcdata import read
from revenuechaser.rcdata.tests.conftest import market_roots  # noqa: F401  (fixture)


def _apple(edges: list[dict]) -> list[tuple]:
    return [(e["src"], e["relation"], e["source"]) for e in edges if e["dst_ticker"] == "AAPL"]


def test_the_board_reads_the_service_with_no_relatedness_row_at_all(rawstore_tmp_db, market_roots):  # noqa: F811
    """The point of the step: the service's answer alone gives the profile edges."""
    _filing()
    _profile()
    assert rawstore.get_all("relatedness_profiles") == []
    assert _apple(engine.build_edges()) == [("AMKR", "customer", "profile")]


def test_a_relatedness_row_the_service_does_not_have_gives_no_profile_edge(rawstore_tmp_db,
                                                                          market_roots):  # noqa: F811
    """The old table is no longer a source: a row only there is not read."""
    _filing()
    rawstore.write_rows("relatedness_profiles", [{"ticker": "AMKR", "cik": "1", "model": "m",
                                                  "prompt_version": "v3d", "fetched_at": 1.0, "cache_key": "k",
                                                  "status": "ok", "profile_json": json.dumps(PROFILE),
                                                  "accession": "acc-old"}])
    serve_answers([], replace=True)
    assert _apple(engine.build_edges()) == []


def test_the_answer_is_found_by_cik_and_not_by_ticker(rawstore_tmp_db, market_roots):  # noqa: F811
    """The service answers by CIK; the board works in tickers. A zero-padded CIK is the same company."""
    _filing(cik="0000001047127")
    _profile(cik="1047127")
    assert _apple(engine.build_edges()) == [("AMKR", "customer", "profile")]


def test_a_partial_answer_is_a_profile(rawstore_tmp_db, market_roots):  # noqa: F811
    """``relatedness_profiles`` holds a partial answer too (the Relatedness import writes one), so filtering it
    here would lose edges the board serves today."""
    _filing()
    _profile(status="partial", missing_chunks="1")
    assert _apple(engine.build_edges()) == [("AMKR", "customer", "profile")]


def test_an_answer_with_no_json_is_no_profile(rawstore_tmp_db, market_roots):  # noqa: F811
    """A row the service holds with no parsed answer is not a profile, and carries no accession to an edge.

    Asserted on the map and not on the edges: with no profile at all the board draws no profile edge either way,
    so an edge assertion here would pass on the merge-base and prove nothing (``red-on-base`` on the first push).
    """
    _filing()
    _profile(profile=None)
    assert engine._service_profiles([{"ticker": "AMKR", "cik": "1"}]) == ({}, {})
    assert _apple(engine.build_edges()) == []


def test_no_serving_file_reads_as_no_profiles(rawstore_tmp_db, market_roots):  # noqa: F811
    """A service that cannot be read reads as "no profiles", as the stored-table read did, so a run still serves
    what the filings themselves state instead of failing."""
    assert engine._service_profiles([{"ticker": "AMKR", "cik": "1"}]) == ({}, {})
    _filing()
    assert _apple(engine.build_edges()) == []          # #748: the text alone gives no edge


def test_a_read_that_raises_reads_as_no_profiles(rawstore_tmp_db, market_roots, caplog,
                                                 monkeypatch):  # noqa: F811
    """Not the same case as a missing file, which the reader answers with no rows: a broken table raises, and the
    board must still come out rather than fail the run."""
    def boom(*a, **k):
        raise RuntimeError("catalog error")

    monkeypatch.setattr(read, "sec_reads", boom)
    with caplog.at_level("ERROR"):
        assert engine._service_profiles([{"ticker": "AMKR", "cik": "1"}]) == ({}, {})
    assert "the SEC reading service could not be read" in caplog.text


def test_a_corpus_row_without_a_cik_asks_the_service_nothing(rawstore_tmp_db, market_roots,
                                                             monkeypatch):  # noqa: F811
    def refuse(*a, **k):
        raise AssertionError("the service was asked for a company with no CIK")

    monkeypatch.setattr(read, "sec_reads", refuse)
    assert engine._service_profiles([{"ticker": "AMKR", "cik": ""}]) == ({}, {})


def test_both_share_classes_of_one_cik_get_the_answer(rawstore_tmp_db, market_roots):  # noqa: F811
    """``build_edges`` keeps one ticker per CIK (#408); the map it is given names both, as the corpus does."""
    _profile(cik="1652044")
    rows = [{"ticker": "GOOG", "cik": "1652044"}, {"ticker": "GOOGL", "cik": "1652044"}]
    profiles, accessions = engine._service_profiles(rows)
    assert sorted(profiles) == ["GOOG", "GOOGL"] and sorted(accessions) == ["GOOG", "GOOGL"]


def test_the_question_id_is_the_registered_ones():
    """The board names the question as text, so that a board import does not pull the asker and its providers in.
    Nothing but this test ties the two spellings together."""
    from revenuechaser.rcdata.build.sec_reads import company_profile

    assert engine.PROFILE_QUESTION == company_profile.PROFILE_ID
