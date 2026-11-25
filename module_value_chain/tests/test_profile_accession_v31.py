"""Plan v31 step 1(d): a Relatedness profile names the filing it was written from, and its Value Chain edges carry it.

G-D needs it: a profile edge is only as current as the annual report the writer read, and the board can only say
which one when the edge names its accession.

The accession is the **service answer's** since #894 step 4, and the board's own ``relatedness_profiles`` column is
gone (#1520), so the three tests that wrote that column through ``store.save_profile`` went with it. What they
guarded -- the accession reaching an edge -- is the second test below, over the service's answer.
"""
from __future__ import annotations

from revenuechaser.core import rawstore
from revenuechaser.module_value_chain import engine
from revenuechaser.module_value_chain.tests.test_value_chain_profile_edges_410 import PROFILE, _filing, _profile
from revenuechaser.rcdata.tests.conftest import market_roots  # noqa: F401  (fixture)


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
