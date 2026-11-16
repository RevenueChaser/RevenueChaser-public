"""A Relatedness profile run mirrors the SEC reading service's ``company.profile`` answers and calls no model
(avo, 16 Nov 2026; #894, plan §12.3 step 4).
"""
from __future__ import annotations

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_relatedness import config, engine, profile_v3, store
from RevenueChaser.module_relatedness.tests.test_sec_forms_reader_841 import filings_only, layer  # noqa: F401
from RevenueChaser.module_relatedness.tests.test_service_profile_bytes import MSFT, ask_the_service, world  # noqa: F401
from RevenueChaser.rcdata import read
from RevenueChaser.rcdata.build.sec_reads import company_profile as cp
from RevenueChaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401  (fixtures)


@pytest.fixture
def from_service(world, monkeypatch):  # noqa: F811
    monkeypatch.setattr(config, "PROFILES_FROM", "service")
    return world


def test_a_run_before_the_service_has_an_answer_changes_nothing_and_calls_no_model(from_service):
    board, mock = from_service
    engine.build_profiles(["MSFT"], usd_cap=1.0)
    assert board == [] and mock.calls("/chat/completions") == []
    assert not rawstore.get("relatedness_profiles", "MSFT")


def test_the_services_answer_becomes_the_boards_profile(from_service):
    board, mock = from_service
    ask_the_service()                                       # the service reads the filing: one call, its own
    (answer,) = read.sec_reads([MSFT], cp.PROFILE_ID)

    profiles = engine.build_profiles(["MSFT"], usd_cap=1.0)
    assert board == [] and len(mock.calls("/chat/completions")) == 1      # the board asked nobody
    assert profiles["MSFT"] == profile_v3.to_attributes(answer["answer"]) and any(profiles["MSFT"].values())
    row = rawstore.get("relatedness_profiles", "MSFT")
    assert (row["status"], row["provider"], row["prompt_version"]) == ("ok", "evren", config.PROMPT_VERSION)
    assert row["profile_json"] == answer["answer"]
    assert row["label_source"] == {"input": "item", "from": "sec/reads"}
    assert store.input_hash(row["cache_key"]) == answer["input_hash"]
    assert store.profile_source(row["cache_key"])["accession"] == answer["accession"]
    assert row["accession"] == answer["accession"]         # the column Value Chain reads (#956)
    assert not store.is_stale(store.profile_meta(["MSFT"])["MSFT"], store.mode_stamp())

    engine.build_profiles(["MSFT"], usd_cap=1.0)            # the same answer again: the row is left alone
    assert rawstore.get("relatedness_profiles", "MSFT")["fetched_at"] == row["fetched_at"]
