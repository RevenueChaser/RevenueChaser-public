"""Tier rule v5: the Texas Stock Exchange (``TXSE``) is a listed exchange.

The SEC company-tickers file names ``TXSE`` for Texas companies that list there beside their old exchange: 15 rows
of the live spine of 22 Nov 2026 (build ``20261122T211433Z-5bc5051b``), all Tier D, ten of them in ``my_universe``
(CECO, CFR, DDS, ET, IBOC, OBK, SUN, SUNC, TXCP, USAC). CFR's SEC exchange was NYSE on 28 Oct and TXSE on 19 Nov.
avo, 22 Nov 2026 22:20 Amsterdam: "Bu arkadaşlar da eklensin listeye."
"""
from __future__ import annotations

from revenuechaser.rcdata.build.spine import tier


def test_txse_is_listed():
    assert tier.listed("TXSE")
    assert tier.tier("TXSE", "common") == "A"
    assert tier.tier("txse ", "common") == "A"              # the SEC file's case and spacing do not matter
    assert tier.tier("TXSE", "preferred") == "B"            # listed, excluded type
    assert tier.tier("TXSE", "mlp") == "A"
    assert tier.tier("TXSE", "common", 19) == "C"           # Compustat over the counter still demotes it
    # The rule changed what a row's ``tier`` column says, so its version is stamped anew on every row.
    assert tier.VERSION == 5
