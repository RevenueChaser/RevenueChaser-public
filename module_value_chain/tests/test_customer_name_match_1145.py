"""#1145: a Compustat customer name resolves although the two sides write the name differently.

Two losses the live measurement found (19,428 ``customer_share`` rows typed COMPANY, 5,101 resolved):

* one issuer's several listed lines carry the same registrant name, so ``spine_names`` called the name ambiguous
  ("Target Corp", "Ford Motor Co", "AT&T Inc"): rows of one CIK are one issuer, and the class #408 keeps wins;
* the legal form is spelled differently ("Home Depot Inc. (The)", "Lowe's Cos Inc", "Eli Lilly and Co").

Two issuers that really do share a name stay ambiguous unless exactly one of them is a Tier A operating company.

Every test here is red on the merge-base, which is what ``scripts/red_on_base.py`` asks for, so the guards (two
real namesakes, a name with no share line) are assertions inside the test of the rule they guard rather than
tests of their own. #1142's own guards -- "Rafael Technologies" is not Rafael Holdings, "employers" is no
company -- stay in ``test_alias_wrong_company_1142.py``, where they already run against this change.
"""
from __future__ import annotations

from revenuechaser.module_value_chain import aliases, engine


def _sec(ticker, name, cik=None, tier="A", security_type="common"):
    return {"ticker": ticker, "name": name, "cik": cik, "tier": tier, "security_type": security_type}


# A megacap whose preferred lines file under the same CIK and the same registrant name, the shape that made the
# live measurement's ambiguous labels.
PREFERRED = [_sec("BAC", "Bank of America Corp", cik="70858"),
             _sec("BAC-PRB", "Bank of America Corp", cik="70858", tier="B", security_type="preferred"),
             _sec("BAC-PRK", "Bank of America Corp", cik="70858", tier="B", security_type="preferred")]


def test_one_cik_with_several_listed_lines_is_one_issuer():
    names = aliases.spine_names(PREFERRED)
    assert aliases.resolve("Bank of America Corp", names) == {"name": "Bank of America Corp", "ticker": "BAC"}


def test_the_class_408_keeps_is_the_one_a_name_resolves_to():
    # Two real share classes of one CIK: ``SAME_ISSUER`` names the class the boards keep (#408).
    names = aliases.spine_names([_sec("FOX", "Fox Corp", cik="1754301"),
                                 _sec("FOXA", "Fox Corp", cik="1754301")])
    assert (aliases.resolve("Fox Corp", names) or {}).get("ticker") == "FOXA"


def test_two_issuers_sharing_a_name_resolve_to_the_one_tier_a_company():
    # "Target Corp" (TGT, Nasdaq/NYSE) against a tiny OTC namesake, whose only tie is the normalised key.
    names = aliases.spine_names([_sec("TGT", "Target Corp", cik="27419"),
                                 _sec("TGTGF", "Target Group Inc", cik="1586554", tier="C")])
    assert (aliases.resolve("Target Corp", names) or {}).get("ticker") == "TGT"

    # Two Tier A issuers that really do share a name, and two lines that are both off Tier A (the unsponsored
    # OTC lines of a foreign company), stay ambiguous: nothing says which one a filer means.
    two_a = aliases.spine_names([_sec("ABC1", "Acme Holdings", cik="1"), _sec("ABC2", "ACME Inc", cik="2")])
    assert aliases.resolve("Acme", two_a) is None
    otc = aliases.spine_names([_sec("HXSCL", "SK Hynix Inc", cik=None, tier="C"),
                               _sec("HXSCF", "SK Hynix Inc", cik=None, tier="C")])
    assert aliases.resolve("SK Hynix Inc", otc) is None


def test_the_share_line_of_a_cik_wins_over_its_notes_and_etns():
    # "COMCAST CORP" is CMCSA and CCZ (exchangeable notes, untyped); "JPMORGAN CHASE & CO" is JPM, six preferred
    # lines and two ETNs. The board shows the share line.
    names = aliases.spine_names([
        _sec("CCZ", "COMCAST CORP", cik="1166691", security_type="unknown"),
        _sec("CMCSA", "COMCAST CORP", cik="1166691"),
        _sec("AMJB", "JPMORGAN CHASE & CO", cik="19617", tier="B", security_type="etp"),
        _sec("JPM", "JPMORGAN CHASE & CO", cik="19617"),
        _sec("JPM-PC", "JPMORGAN CHASE & CO", cik="19617", tier="B", security_type="preferred")])
    assert (aliases.resolve("Comcast Corp", names) or {}).get("ticker") == "CMCSA"
    assert (aliases.resolve("JPMorgan Chase & Co", names) or {}).get("ticker") == "JPM"

    # Triton International has nothing listed but preferred lines: an edge to one of them is no edge, so the
    # name keeps nothing at all.
    only_preferred = aliases.spine_names([
        _sec("TRTN-PA", "Triton International Ltd", cik="1660734", tier="B", security_type="preferred"),
        _sec("TRTN-PB", "Triton International Ltd", cik="1660734", tier="B", security_type="preferred")])
    assert aliases.resolve("Triton International Ltd", only_preferred) is None


def test_compustat_writes_the_leading_the_in_brackets():
    names = aliases.spine_names([_sec("HD", "Home Depot, Inc.", cik="354950"),
                                 _sec("KR", "Kroger Co", cik="56873"),
                                 _sec("TJX", "TJX Companies, Inc.", cik="109198"),
                                 _sec("BA", "Boeing Co", cik="12927")])
    for label, ticker in (("Home Depot Inc. (The)", "HD"), ("Kroger Co. (The)", "KR"),
                          ("TJX Companies Inc (The)", "TJX"), ("Boeing Co (The)", "BA"),
                          ("The Home Depot, Inc.", "HD")):
        assert (aliases.resolve(label, names) or {}).get("ticker") == ticker, label


def test_cos_is_companies_and_and_is_an_ampersand():
    names = aliases.spine_names([_sec("LOW", "Lowe's Companies, Inc.", cik="60667"),
                                 _sec("LLY", "ELI LILLY & Co", cik="59478"),
                                 _sec("T", "AT&T Inc.", cik="732717")])
    for label, ticker in (("Lowe's Cos Inc", "LOW"), ("Eli Lilly and Co", "LLY"), ("AT&T Inc", "T")):
        assert (aliases.resolve(label, names) or {}).get("ticker") == ticker, label


def test_a_market_or_a_geography_is_no_customer():
    """Compustat's own ``customer_type`` keeps a segment name out, however well it matches a listed issuer.

    The three the live measurement found: "Financial Institutions" is a market and also Financial Institutions,
    Inc. (FISI); "Travel and leisure" is a market and also Travel & Leisure Co. (TNL); "Orange" is a geography
    (the county) and also Orange S.A. (ORANY).
    """
    names = aliases.spine_names([_sec("FISI", "FINANCIAL INSTITUTIONS INC", cik="862831"),
                                 _sec("TNL", "Travel & Leisure Co.", cik="1361658"),
                                 _sec("ORANY", "ORANGE", cik="1038143", security_type="adr")])
    rows = [{"customer": "Financial Institutions", "customer_type": "MARKET", "share": 0.3,
             "period_end": "2025-12-31", "source": "wrds/segments"},
            {"customer": "Travel and leisure", "customer_type": "MARKET", "share": 0.2,
             "period_end": "2025-12-31", "source": "wrds/segments"},
            {"customer": "Orange", "customer_type": "GEOREG", "share": 0.1, "period_end": "2025-12-31",
             "source": "wrds/segments"}]
    assert engine._xbrl_customer_edges("RAIL", rows, names) == []
    # The same names typed COMPANY are companies, and a row with no type is an annual report's XBRL member.
    typed = [{**rows[0], "customer_type": "COMPANY"}, {**rows[1], "customer_type": None}]
    assert {e["dst_ticker"] for e in engine._xbrl_customer_edges("RAIL", typed, names)} == {"FISI", "TNL"}


def test_the_customer_edge_takes_the_newly_resolved_name():
    rows = [{"customer": "Home Depot Inc. (The)", "share": 0.11, "period_end": "2025-12-31", "form": "10-K",
             "accession": "0000875320-26-000010", "document_date": "2026-02-12"},
            {"customer": "Bank of America Corp", "share": 0.08, "period_end": "2025-12-31", "form": "10-K",
             "accession": "0000875320-26-000010", "document_date": "2026-02-12"}]
    names = aliases.spine_names([_sec("HD", "Home Depot, Inc.", cik="354950"), *PREFERRED])
    assert {e["dst_ticker"] for e in engine._xbrl_customer_edges("SWK", rows, names)} == {"HD", "BAC"}
