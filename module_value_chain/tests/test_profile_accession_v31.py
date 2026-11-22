"""Plan v31 step 1(d): a Relatedness profile names the filing it was written from, and its Value Chain edges carry it.

G-D needs it: a profile edge is only as current as the annual report the writer read, and the board can only say
which one when the edge names its accession.
"""
from __future__ import annotations

from revenuechaser.core import rawstore
from revenuechaser.module_relatedness import config, store
from revenuechaser.module_value_chain import engine
from revenuechaser.module_value_chain.tests.test_value_chain_profile_edges_410 import PROFILE, _filing, _profile
from revenuechaser.rcdata.tests.conftest import market_roots  # noqa: F401  (fixture)

ATTRS = {f: ["x"] for f in config.PROFILE_FIELDS}


def test_save_profile_stores_the_accession_and_a_plain_resave_keeps_it(rawstore_tmp_db):
    store.save_profile("NVDA", "1045810", ATTRS, "ck", "m", accession="0001045810-26-000010")
    assert rawstore.get("relatedness_profiles", "NVDA")["accession"] == "0001045810-26-000010"
    store.save_profile("NVDA", "1045810", ATTRS, "ck", "m", status="ok", attempts=2)     # the attempt-count re-save
    assert rawstore.get("relatedness_profiles", "NVDA")["accession"] == "0001045810-26-000010"


def test_a_store_without_the_column_keeps_its_json_on_a_resave(rawstore_tmp_db):
    """Review of #956: a table that predates ``accession`` must not lose ``profile_json`` on a plain re-save (#400).
    Within one process the schema is ensured once, so the re-save may refuse; what it must never do is write the
    row with its JSON read as None."""
    import contextlib

    store.save_profile("NVDA", "1045810", ATTRS, "ck", "m", profile_json={"summary": "s"}, label_source={"a": 1})
    rawstore.execute("ALTER TABLE relatedness_profiles DROP COLUMN accession", db="relatedness")
    with contextlib.suppress(Exception):
        store.save_profile("NVDA", "1045810", ATTRS, "ck", "m", status="ok", attempts=2)
    row = rawstore.get("relatedness_profiles", "NVDA")
    assert (row["profile_json"], row["label_source"]) == ({"summary": "s"}, {"a": 1})


def test_profile_edges_carry_the_accession():
    edges = engine.profile_edges("AMKR", PROFILE, "2026-02-01", accession="acc-1")
    assert edges and {e["accession"] for e in edges} == {"acc-1"}
    assert {e["accession"] for e in engine.profile_edges("AMKR", PROFILE, "2026-02-01")} == {None}


def test_the_answers_accession_reaches_chain_mentions(rawstore_tmp_db, market_roots):  # noqa: F811
    """#894 step 4: the accession an edge carries is the service answer's, not a column of the board's old table."""
    _filing()
    _profile(accession="acc-1")
    engine.build_edges()
    stored = [r for r in rawstore.get_all("chain_mentions") if r["src"] == "AMKR"]
    assert stored and {r["accession"] for r in stored} == {"acc-1"}


def test_the_profile_writer_stores_the_accession_of_the_filing_it_read(rawstore_tmp_db, monkeypatch):
    from revenuechaser.module_relatedness import engine as rel, profiles
    from revenuechaser.module_relatedness.tests.test_relatedness import long_body
    from revenuechaser.rcdata.tests import spine_fixture

    spine_fixture.write_security([])          # a profile run needs a spine (#642 D3)

    monkeypatch.setattr(config, "PROFILES_FROM", "own")       # the board's own writer; the mirror has its own test
    monkeypatch.setattr(rel, "_cik_for", lambda ts: {t: t for t in ts})
    monkeypatch.setattr(rel, "_filing_text", lambda t: (t, long_body("we make gpus")))
    monkeypatch.setattr(rel, "_filing_source", lambda t: {"cik": "1045810", "accession": "acc-9", "form": "10-K",
                                                          "filed": "2026-02-01"})
    monkeypatch.setattr(profiles, "profile_for", lambda *a, **k: dict(ATTRS))
    rel.build_profiles(["NVDA"], provider="deepseek", usd_cap=1.0)
    assert rawstore.get("relatedness_profiles", "NVDA")["accession"] == "acc-9"
