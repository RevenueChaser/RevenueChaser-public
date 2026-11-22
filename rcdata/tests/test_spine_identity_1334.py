"""Spine identity, #1334 (plan v4 step 6 and the spine part of step 7): K-B notes are Tier B, K-G delisted names
leave Tier A, K-C links a name whose Compustat company has no CIK, each behind the fresh-snapshot guard (X6)."""
from __future__ import annotations

import pytest

from revenuechaser.rcdata.build.spine import etf, tier


# ── K-B: a baby bond or a note is an exchange-traded product, so Tier B ──────────────────────────────────────

@pytest.mark.parametrize("name", ["Saratoga Investment Corp 8.125% Notes due 2027", "XYZ Corp 6.5% Senior Notes",
                                  "Some Bank Note due 2031"])
def test_a_note_by_its_sec_name_is_an_etp_and_tier_b(name):
    """The pattern is the one ``etf.ETN_NAME`` already reads (notes due, senior notes), so the two cannot drift."""
    assert etf.is_etn(name)
    assert tier.product_type("SAXX", name, "NYSE") == ("etp", "name_rule(note)")
    typ, _ = tier.security_type("SAXX", name, None, exchange="NYSE")
    assert typ == "etp" and tier.tier("NYSE", typ) == "B"


@pytest.mark.parametrize("name", ["NOTEWORTHY CORP", "Notes Holdings Inc", "SENIOR HOUSING PROPERTIES TRUST"])
def test_an_operating_name_with_the_word_note_stays_untyped(name):
    assert tier.product_type("XYZ", name, "NYSE") is None
