"""Tier rule v7: Compustat's issue type ``R`` (exchange-traded debt: notes, baby bonds, ETNs, CORTS trusts) is an
exchange-traded product, so Tier B.

Measured on the live spine of 23 Nov 2026 (build ``20261123T050634Z-66011bee``): 157 Tier A rows typed ``unknown``
came in through the ticker link (K-C); Compustat's tpci is ``R`` for 156 of them, and 128 of their Compustat names
read as notes (DTG "2021 S E 4.375 J S D DU 2081", PRS "PRUDN FIN INC 5.625 JR SB NT"). Every active US ``R``
security of the 22 Nov snapshot (321) is a note, an ETN or a trust certificate. avo, 23 Nov 2026 10:02 Amsterdam: "evet".
"""
from __future__ import annotations

from revenuechaser.rcdata.build.spine import tier


def test_compustat_issue_type_r_is_an_exchange_traded_product():
    assert tier.security_type("DTG", "DTE ENERGY CO", None, "R") == ("etp", "compustat_tpci(R)")
    assert tier.tier("NYSE", tier.security_type("PRS", "PRUDENTIAL FINANCIAL INC", None, "R")[0]) == "B"
    # the codes read before are unchanged, and a name a rule already typed keeps that type
    assert tier.security_type("MSFT", "MICROSOFT CORP", None, "0")[0] == "common"
    assert tier.security_type("ZZZZ", "SOME BANK", None, "Q")[0] in tier.UNTYPED
    # the rule changed what a row's ``tier`` column says, so its version is stamped anew on every row
    assert tier.VERSION == 7
