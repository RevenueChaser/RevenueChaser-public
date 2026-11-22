"""Tier rule v4 (#1334, draft K-D): a blank SEC exchange takes the linked Compustat security's exchange.

The SEC company-tickers file leaves the exchange empty for listed names now and then, and the row came out Tier D
for that reason alone. CFR (Cullen/Frost), IBOC and TXCP are S&P 400 members and were Tier D on the live spine of
20 Nov 2026 (build ``20261120T060917Z-210667c3``); each is already named by the ``member_not_tier_a`` build issue,
which is the accept of K-D: no index member is Tier D."""
from __future__ import annotations

from RevenueChaser.rcdata.build.spine import tier


def test_a_blank_sec_exchange_takes_the_compustat_exchange():
    """11 NYSE, 14 Nasdaq and 21 Cboe BZX make the row listed, so its type decides A or B.

    The boundaries are asserted here, inside the rule's own test, rather than as tests of their own: each of them
    holds on the base too, where this rule does not exist yet.
    """
    # CFR's shape: a blank exchange, an operating type, Compustat says NYSE
    assert tier.tier("", "common", 11) == "A"
    assert tier.tier(None, "common", 14) == "A"
    assert tier.tier(None, None, 21) == "A"                 # an untyped name is never hidden
    assert tier.tier("", "etp", 14) == "B"                  # listed, excluded type
    assert tier.tier("   ", "common", 11) == "A"            # whitespace is no exchange either
    # The boundaries. 12 (NYSE American) does not fill in, because the SEC file's own "NYSE American" is not in
    # LISTED either; 19 (over the counter) is COMPUSTAT_OTC's code and demotes a listed row, it does not promote a
    # blank one; an unknown code and no code at all leave Tier D alone.
    assert tier.tier("", "common", 12) == "D"
    assert tier.tier("", "common", 19) == "D"
    assert tier.tier("", "common", 17) == "D"
    assert tier.tier("", "common", None) == "D"
    assert tier.tier(None, "common") == "D"
    # And the rule reads Compustat **only** where the SEC file is silent: an exchange it names still decides.
    assert tier.tier("OTC", "common", 11) == "C"
    assert tier.tier("LSE", "common", 11) == "D"
    assert tier.tier("NYSE", "common", 19) == "C"


def test_the_map_holds_only_the_codes_the_sec_name_of_which_is_listed():
    """A filled-in code must not grant a tier the SEC file would not, so every name in the map passes
    :func:`tier.listed` and no code of :data:`tier.COMPUSTAT_OTC` is in it."""
    assert set(tier.COMPUSTAT_LISTED) == {11, 14, 21}
    assert all(tier.listed(name) for name in tier.COMPUSTAT_LISTED.values())
    assert not set(tier.COMPUSTAT_LISTED) & set(tier.COMPUSTAT_OTC)
    # The rule changed what a row's ``tier`` column says, so its version is stamped anew on every row.
    assert tier.VERSION == 4
