"""#1156: a customer label that names a subsidiary resolves to the subsidiary's listed parent.

``resolve`` matched a counterparty name against the hand-kept aliases and the spine's registrant names only, so a
name that is no registrant of its own reached no ticker however plainly it belongs to a listed company:
"Harris Teeter Supermarkets Inc" is Kroger's, "LinkedIn Corp" is Microsoft's, "Caremark LLC" is CVS's. The
headroom measurement over the live ``customer_share`` rows found 92 such customer labels carrying one current
parent in the spine; ``SUBSIDIARIES`` holds the 79 that a by-hand check of every pair kept.

``SUBSIDIARIES`` is read **last**, so it can only fill a gap: every test here also asserts the two rules that
keeps -- a name the spine resolves is untouched, and a name that holds two companies or no company still resolves
to nothing.
"""
from __future__ import annotations

from revenuechaser.module_value_chain import aliases


def _sec(ticker, name, cik=None, tier="A", security_type="common"):
    return {"ticker": ticker, "name": name, "cik": cik, "tier": tier, "security_type": security_type}


SPINE = aliases.spine_names([_sec("KR", "KROGER CO", cik="56873"),
                             _sec("MSFT", "MICROSOFT CORP", cik="789019"),
                             _sec("CVS", "CVS HEALTH Corp", cik="64803")])


def test_a_subsidiary_name_resolves_to_its_listed_parent():
    for name, ticker in (("Harris Teeter Supermarkets Inc", "KR"),
                         ("LinkedIn Corp", "MSFT"),
                         ("Caremark LLC", "CVS")):
        assert aliases.resolve(name, SPINE) == {"name": name, "ticker": ticker}
    # The guards of the rule, asserted here rather than as tests of their own, because they already hold on the
    # merge-base and ``red_on_base.py`` asks every new test to be red there. A name that names no one company
    # still reaches no ticker, and a name the table does not hold is unchanged.
    assert aliases.resolve("Customer A", {}) is None            # anonymised
    assert aliases.resolve("employers", {}) is None             # a kind of counterparty (#1142)
    assert aliases.resolve("Apple and Dell", {}) is None        # two companies in one name
    assert aliases.resolve("Some Private Supplier GmbH", {}) is None
    # A legal form that makes the name another company sharing the key: "Safeway plc" is the British supermarket
    # Morrisons bought, not the US Safeway Inc that Albertsons owns (8 rows on the live store).
    assert aliases.resolve("Safeway PLC", {}) is None
    assert aliases.resolve("Safeway plc", {}) is None
    assert (aliases.resolve("Safeway Inc", {}) or {}).get("ticker") == "ACI"


def test_the_table_is_read_last_and_changes_no_name_the_spine_resolves():
    # "Kroger Co" is on the spine and must still answer from the spine, not from the table.
    assert (aliases.resolve("KROGER CO", SPINE) or {}).get("ticker") == "KR"
    # A former name whose own registrant is still listed stays with that registrant: "Seagen Inc" is in the
    # table as Pfizer's, and a spine that still carries Seagen wins.
    seagen = aliases.spine_names([_sec("SGEN", "Seagen Inc", cik="1060736")])
    assert (aliases.resolve("Seagen Inc", seagen) or {}).get("ticker") == "SGEN"
    # With no such registrant, the table answers.
    assert (aliases.resolve("Seagen Inc", {}) or {}).get("ticker") == "PFE"


def test_every_key_is_a_whole_normalised_name_and_no_generic_word():
    for key, ticker in aliases.SUBSIDIARIES.items():
        assert key == aliases._key(key), f"{key} is not a normalised key"
        assert len(key) >= 2, f"{key} is too short to identify a company"
        assert key not in aliases.GENERIC_PARTIES, f"{key} names a kind of counterparty"
        assert ticker and ticker == ticker.upper(), f"{key} -> {ticker!r} is no ticker"
        # The table never re-states an alias: ``find_aliases`` runs first and would win anyway.
        assert key not in {a.replace(" ", "") for a in aliases.ALIASES}, f"{key} is already an alias"
    # Every refused form guards a key the table actually holds.
    for key in aliases.SUBSIDIARY_REFUSED_FORMS:
        assert key in aliases.SUBSIDIARIES, f"{key} guards nothing"


def test_a_parent_takes_every_one_of_its_subsidiary_names():
    # The shape the measurement found most often: one parent, several subsidiary and former names.
    assert {aliases.SUBSIDIARIES[k] for k in ("MERCKSHARPDOHME", "ACCELERONPHARMA", "PROMETHEUSBIOSCIENCES")} == {"MRK"}
    assert {aliases.SUBSIDIARIES[k] for k in ("SAFEWAY", "VONSCOMPANIES", "STARMARKETS")} == {"ACI"}
