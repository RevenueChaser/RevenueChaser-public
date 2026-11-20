"""Does a profile edge's own quote state the relation the edge claims? (#1142)

The census of 20 Nov 2026 (200 served-candidate profile edges, every one read against its filing:
``notes/revenuechaser/2026-11-20_0110_value-chain-profile-edge-census.md`` in claude-coordinator) found 28 wrong
edges. Five were a name matched to the wrong listed company, which ``aliases`` owns. The other 23 are wrong in the
profile answer itself: the quote names a partner, a landlord, a lender or a joint venture; the named company deals
with a third party and not with the filer; it is a prospect, an example, or the relation runs the other way.

Every rule below reads the **quote** -- the sentence the profile cited -- and nothing else, so it is a repo-only
check with no model call and no re-read of a filing. Each one was written against the quotes of that census and
measured on all 195 marked edges: together they refuse 18 of the 23, and 2 edges the labeller called right (one of
them ``YELP->CXM``, which the owner himself marked borderline) plus 4 he called doubtful. The numbers are
in-sample by construction -- the rules were written from these quotes -- so the gate of plan v31 section 6 is
re-measured on a fresh sample, not on this one.

A refusal is not a repair: the edge is dropped, because a quote that states another relation is no evidence for
this one. ``reason`` is kept for the count a run reports.
"""
from __future__ import annotations

import re

# Words that identify no company on their own, so they are not looked for in the quote.
_STOP = re.compile(
    r"^(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|llc|lp|group|holdings?|the|and|"
    r"international|technologies|technology|pharmaceuticals|laboratories|labs|systems|sa|nv|ag|&)$", re.I)

#: How much of the quote is read before the name: one clause, not the whole paragraph.
BEFORE_CHARS = 170
_AFTER_CHARS = 160

# A full stop that ends a sentence, and not the one inside "Inc.", "Corp." or an initial ("J. Smith").
_SENT_END = re.compile(r"(?<!\b[A-Z])(?<!\bInc)(?<!\bCorp)(?<!\bCo)(?<!\bLtd)(?<!\bNo)[.;]\s")

_FIRST_PERSON = re.compile(r"\b(we|our|ours|us|the Compan(?:y|y's))\b", re.I)
# A buyer/seller word in the clause: it is the profile's own evidence, so a "partner" nearby does not refuse it
# (census row 59, a customer list that reads "... and system integrators such as Northrop Grumman ...").
_TRADE_WORD = re.compile(r"\b(customers?|clients?|sales to|sold to|revenue from|purchas\w+)\b", re.I)


def name_tokens(name: str) -> list[str]:
    """The words of a company name that can be looked for in a quote ("3D Systems" -> ``['3D']``)."""
    words = re.findall(r"[A-Za-z0-9&]+", name or "")
    out = [w for w in words if len(w) > 2 and not _STOP.match(w)]
    return out or [w for w in words if len(w) >= 2]


def name_position(quote: str, name: str) -> int | None:
    """Where the quote first names the company, or None when it does not (a quote cut short by its length cap)."""
    found = [m.start() for t in name_tokens(name)
             for m in [re.search(r"\b" + re.escape(t) + r"\b", quote or "", re.I)] if m]
    return min(found) if found else None


def sentence(quote: str, pos: int) -> str:
    """The sentence of ``quote`` that holds ``pos``."""
    start = 0
    for m in _SENT_END.finditer(quote, 0, pos):
        start = m.end()
    end = m.start() if (m := _SENT_END.search(quote, pos)) else len(quote)
    return quote[start:end]


def refuse(edge: dict) -> str | None:
    """The reason the edge's quote does not state the claimed relation, or None when it does.

    A quote that does not name the company at all is **not** refused: 4 of the 5 such edges in the census were
    right and their quote was simply cut at its length cap, so the absence says nothing.
    """
    quote, name, relation = edge.get("snippet") or "", edge.get("dst_name") or "", edge.get("relation")
    pos = name_position(quote, name)
    if pos is None:
        return None
    before = quote[max(0, pos - BEFORE_CHARS):pos]
    after = quote[pos:pos + _AFTER_CHARS]
    sent = sentence(quote, pos)

    # A company that may buy or sell one day: "a small number of potential hyperscaler tenants, such as ...",
    # "have been evaluated by Stoneridge". A role word is required, so a drug's "potential treatment" is not one.
    if re.search(r"\b(?:potential|prospective|possible|future)\s+(?:\w+\s+){0,2}"
                 r"(?:customers?|clients?|tenants?|suppliers?|partners?|buyers?|users?|licensees?|offtakers?)\b",
                 sent, re.I) or re.search(
            r"\b(?:evaluat(?:ing|ed|ion)|may become|could become|trial basis|in discussions)\b", sent, re.I):
        return "prospect"
    # A right the filer holds and has not used: "retaining the right to supply antigens to third parties
    # (including Abbott Laboratories ...)".
    if re.search(r"\bright to (?:supply|sell|purchase|buy|distribute)\b", before, re.I):
        return "retained_right"
    # A name given to illustrate a market: "Examples of companies in this space include Microsoft ...".
    if re.search(r"^\s*examples?\b|\bcompanies in this space\b|\bsuch companies as\b", quote, re.I):
        return "example"
    # Someone else's statement about the company: "According to the American Urological Association, Merck ...".
    if re.match(r"\s*according to\b", sent, re.I):
        return "attribution"
    # A deal between two other parties: "a research collaboration between Pfizer Inc. and Ligand Pharmaceuticals".
    m = re.search(r"\bbetween\b[^;]{0,120}\band\b", sent, re.I)
    if m and not _FIRST_PERSON.search(sent) and pos >= quote.find(sent) + m.start():
        return "between_others"
    # A description of the industry, not of the filer's own chain: "The market for these devices ... is highly
    # fragmented with primary supply chains concentrated across a few larger manufacturers ... such as Plexus".
    if re.search(r"\b(the market for|highly fragmented|supply chains concentrated|competitive landscape)\b",
                 before, re.I):
        return "market_description"
    # The company built the thing named, or runs the programme the quote is about, which says nothing about
    # buying from the filer: "REACT developed by Facebook", "a ... licensing program operated by IMAX Corporation".
    # A physical asset someone operates is left alone ("The field is operated by PEDEVCO Corp.", a real supplier).
    if re.search(r"\b(developed|owned)\s+by\s*$", before, re.I) or re.search(
            r"\b(program|programme|platform|service|network|exchange)\s+(?:operated|managed|run)\s+by\s*$",
            before, re.I):
        return "other_party_role"
    # The company stands behind a third party's obligations: "credit support provided by Google, which supports
    # Fluidstack's payment ... obligations".
    if re.search(r"\b(credit support|guarant(?:ee|y|or)|backstop)\b", before, re.I):
        return "credit_support"
    if re.search(r"\bjoint venture\b|\b50/50\b", before, re.I):
        return "joint_venture"
    if re.search(r"\b(lenders?|term loan|revolving|credit agreement|credit facility|loan facility)\b", before, re.I):
        return "lender"
    # The filer's shop sits beside the company's store: "Many of our Company stores benefit from customer traffic
    # generated by Walmart retail stores ... these host stores".
    if re.search(r"\b(host stores?|landlord)\b", before + after, re.I):
        return "landlord"
    # A brand the filer sold or bought as an asset: "we sold the General Motors (GM) credit card program".
    if re.search(r"\bsold the\b[^;]{0,40}$", before, re.I):
        return "asset_sold"
    # A co-owner of the filer's own asset: "... 51% interest ... with Cameco owning 49%".
    if re.search(r"^[^;]{0,40}\b(owning|owns)\s+\d", after, re.I):
        return "co_owner"
    # One name given as an example of a partner, reseller or integrator, with no buyer/seller word in the clause:
    # "with partners such as Apple, Levi's, and Ulta Beauty". "partners include X" is left alone: the owner reads a
    # distribution or platform partner as a real link (20 Nov 2026), and that is how those quotes are written.
    if re.search(r"\b(partners?|partnerships?|resellers?|system integrators?|franchisees?)\b[^;]{0,60}"
                 r"\bsuch as\b[^;]{0,120}$", before, re.I) \
            and not _TRADE_WORD.search(before):
        return "partner_list"
    # The quote puts the company on the other side of the chain from the relation claimed.
    if relation == "customer" and (re.search(r"\bdistributors?\b[^;]{0,80}\b(for|of)\s*$", before, re.I)
                                   or re.search(r"^[^;]{0,40}-\s?branded", after, re.I)):
        return "direction_supplier_side"
    if relation == "supplier" and re.search(r"\bdistribut(?:ors?|ion|e|es)\b", before, re.I) and re.search(
            r"\b(distribute|sell|market|resell)\s+(?:our|the Company's)\b", after, re.I):
        return "direction_customer_side"
    return None
