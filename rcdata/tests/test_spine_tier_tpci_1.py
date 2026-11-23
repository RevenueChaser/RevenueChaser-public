"""Tier rule v8: Compustat's issue type ``1`` is a preferred share, so Tier B.

Measured on the live spine of 23 Nov 2026 (build ``20261123T102655Z-a7577e6a``, rule v7): of the 586 rows linked to a
Compustat security of tpci ``1``, 335 were already typed preferred (Tier B); 113 Tier A rows stayed ``unknown``, and
their tickers carry the Nasdaq/NYSE preferred suffixes (P 49, O 15, N 12, M 10, L 7: SMCIP, CHTRP, FRMEP, BHFAN).
That leaves 27 Tier A rows of unknown type, under #1334's 30. avo, 23 Nov 2026 10:28 Amsterdam: "basla hepsine".
"""
from __future__ import annotations

from revenuechaser.rcdata.build.spine import tier


def test_compustat_issue_type_1_is_a_preferred_share():
    assert tier.security_type("SMCIP", "Super Micro Computer, Inc.", None, "1") == ("preferred", "compustat_tpci(1)")
    assert tier.tier("Nasdaq", "preferred") == "B"
    assert tier.security_type("DTG", "DTE ENERGY CO", None, "R")[0] == "etp"     # v7 unchanged
    # the rule changed what a row's ``tier`` column says, so its version is stamped anew on every row
    assert tier.VERSION == 8
