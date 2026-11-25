"""Relatedness reads the SEC reading service's ``company.profile`` answers where they are, as Value Chain does,
and keeps no profile table of its own (#894 step 3b; avo, 24 Nov 2026: "Relatedness da Value chain gibi olsun, ek
kopyalamaya gerek yok"). No model call either (avo, 16 Nov 2026).

Since #1520 (avo's "Sil simdi", 25 Nov 2026) there is no other path: ``relatedness_profiles`` and
``relatedness_attributes`` are retired (``rawstore.RETIRED_TABLES``) and the board's own writer is gone, so this
is the whole of how a profile reaches the board. The fixtures build the real layer and let the service read the
filing (``service_fixture``), so nothing here is faked below the writer's HTTP boundary.
"""
from __future__ import annotations

import pytest

from revenuechaser.core import rawstore
from revenuechaser.module_relatedness import config, engine, profile_v3, store
from revenuechaser.module_relatedness.tests.service_fixture import MSFT, ask_the_service  # noqa: F401
from revenuechaser.module_relatedness.tests.service_fixture import filings_only, layer, world  # noqa: F401
from revenuechaser.rcdata import read
from revenuechaser.rcdata.build.sec_reads import company_profile as cp
from revenuechaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401  (fixtures)


@pytest.fixture
def from_service(world):  # noqa: F811
    """The board, the layer and the service's writer. There is no second path to switch off any more (#1520)."""
    return world


def test_the_services_answer_is_the_boards_profile_and_nothing_is_copied(from_service):
    mock = from_service
    ask_the_service()                                       # the service reads the filing: one call, its own
    (answer,) = read.sec_reads([MSFT], cp.PROFILE_ID)

    profiles = engine.build_profiles(["MSFT"], usd_cap=1.0)
    assert len(mock.calls("/chat/completions")) == 1                     # the board asked nobody
    assert profiles["MSFT"] == profile_v3.to_attributes(answer["answer"]) and any(profiles["MSFT"].values())
    # The two tables the board kept its own copy in are retired: no code path names them, and the store file the
    # app opens no longer carries them (``rawstore.RETIRED_TABLES``, #1520).
    for name in ("relatedness_profiles", "relatedness_attributes"):
        assert name in rawstore.RETIRED_TABLES and name not in rawstore.MANIFEST

    (row,) = store.profile_rows(["MSFT"])
    assert (row["status"], row["provider"], row["prompt_version"]) == ("ok", "evren", config.PROMPT_VERSION)
    assert row["fetched_at"] == answer["fetched_at"]                     # when the service asked: the scoring gate
    assert row["label_source"] == {"input": "item", "from": "sec/reads"}
    assert store.input_hash(row["cache_key"]) == answer["input_hash"]
    assert store.profile_source(row["cache_key"])["accession"] == answer["accession"]
    assert store.load_profile_json(["MSFT"]) == {"MSFT": answer["answer"]}
    assert not store.is_stale(store.profile_meta(["MSFT"])["MSFT"], store.mode_stamp())


def test_no_tickers_reads_the_whole_board(from_service):
    """Themes and the Value Chain resolve-rate CLI ask for every profile: that is the board's universe."""
    ask_the_service()
    assert set(store.load_profiles()) == {"MSFT"}
    assert set(store.load_profile_json()) == {"MSFT"}
    assert store.load_profiles([]) == {}


def test_before_the_service_has_an_answer_there_is_no_profile_and_nobody_is_asked(from_service):
    """No answer, no profile: the board has no table of its own to fall back on and no writer to ask (#1520)."""
    mock = from_service
    assert engine.build_profiles(["MSFT"], usd_cap=1.0) == {}
    assert store.profile_rows(["MSFT"]) == [] and store.load_profiles(["MSFT"]) == {}
    assert mock.calls("/chat/completions") == []


def test_a_company_the_service_found_no_text_for_is_no_text_not_pending(from_service):
    """25 Nov 2026: 195 of the board's 199 "pending" were companies the service holds as ``no_text``. They are
    counted apart, as the board's own ``no_text`` rows were, and they are not news for the scoring gate."""
    from revenuechaser.module_value_chain.tests.test_value_chain_profile_edges_410 import answer_row, serve_answers
    serve_answers([answer_row(MSFT, None, status="no_text", attempts=0, fetched_at=9e9)], replace=True)
    assert store.profile_meta(["MSFT"])["MSFT"]["status"] == "no_text"
    assert not any(store.load_profiles(["MSFT"])["MSFT"].values())
    assert store.load_profile_json(["MSFT"]) == {}

    ask_the_service()                                       # a real answer later wins over the no_text row
    assert store.profile_meta(["MSFT"])["MSFT"]["status"] == "ok"
