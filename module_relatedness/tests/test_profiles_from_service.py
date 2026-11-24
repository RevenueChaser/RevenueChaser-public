"""Relatedness reads the SEC reading service's ``company.profile`` answers where they are, as Value Chain does,
and copies none into its own tables (#894 step 3b; avo, 24 Nov 2026: "Relatedness da Value chain gibi olsun, ek
kopyalamaya gerek yok"). No model call either (avo, 16 Nov 2026).
"""
from __future__ import annotations

import pytest

from revenuechaser.core import rawstore
from revenuechaser.module_relatedness import config, engine, profile_v3, store
from revenuechaser.module_relatedness.tests.test_sec_forms_reader_841 import filings_only, layer  # noqa: F401
from revenuechaser.module_relatedness.tests.test_service_profile_bytes import MSFT, ask_the_service, world  # noqa: F401
from revenuechaser.rcdata import read
from revenuechaser.rcdata.build.sec_reads import company_profile as cp
from revenuechaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401  (fixtures)


@pytest.fixture
def from_service(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "PROFILES_FROM", "service")
    return world


def test_the_services_answer_is_the_boards_profile_and_nothing_is_copied(from_service):
    board, mock = from_service
    ask_the_service()                                       # the service reads the filing: one call, its own
    (answer,) = read.sec_reads([MSFT], cp.PROFILE_ID)

    profiles = engine.build_profiles(["MSFT"], usd_cap=1.0)
    assert board == [] and len(mock.calls("/chat/completions")) == 1      # the board asked nobody
    assert profiles["MSFT"] == profile_v3.to_attributes(answer["answer"]) and any(profiles["MSFT"].values())
    assert rawstore.get_all("relatedness_profiles") == []                # the point of the step
    assert rawstore.get_all("relatedness_attributes") == []

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


def test_a_row_only_in_the_old_table_is_not_read_and_no_model_is_asked(from_service):
    """The board's own table is no longer a source on the service path: before the service has an answer there is
    no profile, whatever the table still holds, and nobody is asked for one."""
    board, mock = from_service
    rawstore.write_rows("relatedness_profiles", [{"ticker": "MSFT", "cik": MSFT, "model": "m",
                                                  "prompt_version": config.PROMPT_VERSION, "fetched_at": 1.0,
                                                  "cache_key": "k", "status": "ok"}])
    assert engine.build_profiles(["MSFT"], usd_cap=1.0) == {}
    assert store.profile_rows(["MSFT"]) == [] and store.load_profiles(["MSFT"]) == {}
    assert board == [] and mock.calls("/chat/completions") == []
