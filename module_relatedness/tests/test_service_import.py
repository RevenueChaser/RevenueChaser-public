"""The stored Relatedness profiles handed to the SEC reading service: the dry run (#894). The dry run
writes nothing; the write puts the rows in the service's Parquet tree, and an imported row is not asked again.
"""
from __future__ import annotations

import json

from revenuechaser.core import rawstore
from revenuechaser.module_relatedness import engine, service_import, store
from revenuechaser.module_relatedness.tests.test_sec_forms_reader_841 import filings_only, layer  # noqa: F401
from revenuechaser.module_relatedness.tests.test_service_profile_bytes import MSFT, ask_the_service, world  # noqa: F401
from revenuechaser.rcdata import read, sec_profile
from revenuechaser.rcdata.build.sec_reads import company_profile as cp
from revenuechaser.rcdata.build.sec_reads import reads
from revenuechaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401  (fixtures)


def test_a_stored_profile_is_imported_with_the_services_hash_and_is_not_asked_again(world):
    board, mock = world
    engine.build_profiles(["MSFT"], usd_cap=1.0)
    stored = rawstore.get("relatedness_profiles", "MSFT")

    plan = service_import.plan()
    assert plan["counts"] == {"companies": 1, "imported": 1, "no_profile": 0, "text_changed": 0, "no_text": 0,
                              "hash of today": 1}
    (row,) = plan["rows"]
    assert row["input_hash"] == cp.PROFILE.inputs([MSFT])[MSFT].hash
    assert row["input_hash"] != store.input_hash(stored["cache_key"])         # the two formulas never agree
    assert (row["status"], row["fetched_at"], row["prompt_version"]) == ("ok", stored["fetched_at"], "v3d")
    assert json.loads(row["answer"]) == stored["profile_json"]
    assert read.sec_reads([MSFT], cp.PROFILE_ID) == []                        # the plan wrote nothing

    assert service_import.write() == plan["counts"]
    assert read.sec_reads([MSFT], cp.PROFILE_ID) == []                        # served after the next build
    ask_the_service()
    assert mock.calls("/chat/completions") == []
    (served,) = read.sec_reads([MSFT], cp.PROFILE_ID)
    assert (served["answer"], served["run_id"]) == (stored["profile_json"], service_import.RUN_ID)
    assert service_import.write() == plan["counts"] and len(reads.held(cp.PROFILE_ID)) == 1   # twice changes nothing


def test_a_profile_stored_before_the_candidates_sentence_left_the_prompt_is_imported_too(world, monkeypatch):
    """#748 changed the system prompt and kept ``v3d``; the stored hash is over the system prompt."""
    engine.build_profiles(["MSFT"], usd_cap=1.0)
    stored = rawstore.get("relatedness_profiles", "MSFT")
    key = store._key_mode(stored["cache_key"])
    user = sec_profile.build_user("MICROSOFT CORP", engine._filing_input("MSFT")["hash_text"])
    assert key["input_hash"] == store.prompt_hash(service_import.SYSTEMS["today"], user)

    def keyed(input_hash: str) -> None:
        rawstore.execute("UPDATE relatedness_profiles SET cache_key = ? WHERE ticker = 'MSFT'",
                         [json.dumps({**key, "input_hash": input_hash}, sort_keys=True)], db="relatedness")

    keyed(store.prompt_hash(service_import.SYSTEMS["before #748"], user))
    counts = service_import.plan()["counts"]
    assert (counts["imported"], counts["hash of before #748"]) == (1, 1)

    keyed(store.prompt_hash(service_import.SYSTEMS["today"], user + " and a new paragraph"))
    plan = service_import.plan()
    assert (plan["counts"]["imported"], plan["counts"]["text_changed"], plan["rows"]) == (0, 1, [])
