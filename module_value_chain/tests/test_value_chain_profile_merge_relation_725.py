"""#725: ``merge_profile`` keys the profile's edges by (counterparty, relation), not by counterparty alone.

``chain_mentions`` is keyed ``(src, dst_name, relation)``, so one company can be both a customer and a competitor
of the same filer. Keying only by the company made the profile's first edge swallow every other relation of that
company: an XBRL customer edge (with its share of revenue) vanished whenever the profile named the same company as
a competitor, and a profile edge in a second relation could never pick up a stated share.
"""
from __future__ import annotations

from RevenueChaser.module_value_chain import engine

_XBRL_CUSTOMERS = [{"customer": "Intel", "share": 0.2, "period_end": "2025-12-31",
                    "document_date": "2026-02-01", "form": "10-K", "accession": "a"}]


def _by_key(edges: list[dict]) -> dict[tuple[str, str], dict]:
    return {(e["dst_ticker"] or e["dst_name"], e["relation"]): e for e in edges}


def test_an_xbrl_customer_survives_a_profile_that_calls_the_same_company_a_competitor():
    profile = {"named_competitors": ["Intel"]}
    regex = engine.filing_edges("AMKR", "", "2026-02-01", _XBRL_CUSTOMERS)
    assert _by_key(regex)[("INTC", "customer")]["share_pct"] == 20.0      # the input really holds it

    got = _by_key(engine.merge_profile(regex, engine.profile_edges("AMKR", profile, "2026-02-01")))
    assert set(got) == {("INTC", "competitor"), ("INTC", "customer")}
    assert got[("INTC", "customer")]["source"] == "xbrl"
    assert got[("INTC", "customer")]["share_pct"] == 20.0
    assert got[("INTC", "competitor")]["source"] == "profile"


def test_for_a_pair_both_state_the_xbrl_row_is_kept_and_no_share_is_copied():
    """Plan v31 step 1(b): the filer's tagged line wins over the model's reading of the same pair, and the profile row is
    not given the XBRL share (it used to take it, so a served share could sit under a quote that never stated it)."""
    profile = {"customers": [{"name": "Intel", "share": None, "quote": "Intel is our largest"}]}
    got = _by_key(engine.merge_profile(engine.filing_edges("AMKR", "", "2026-02-01", _XBRL_CUSTOMERS),
                                       engine.profile_edges("AMKR", profile, "2026-02-01")))
    assert set(got) == {("INTC", "customer")}
    assert (got[("INTC", "customer")]["source"], got[("INTC", "customer")]["share_pct"]) == ("xbrl", 20.0)


def test_a_relation_only_the_profile_states_keeps_its_own_share():
    """The profile names Intel as a customer and as a supplier; the XBRL line covers the customer side only."""
    profile = {"customers": [{"name": "Intel", "share": None, "quote": "q1"}],
               "suppliers": [{"name": "Intel", "share": None, "quote": "q2"}]}
    got = _by_key(engine.merge_profile(engine.filing_edges("AMKR", "", "2026-02-01", _XBRL_CUSTOMERS),
                                       engine.profile_edges("AMKR", profile, "2026-02-01")))
    assert set(got) == {("INTC", "customer"), ("INTC", "supplier")}
    assert (got[("INTC", "customer")]["source"], got[("INTC", "customer")]["share_pct"]) == ("xbrl", 20.0)
    assert (got[("INTC", "supplier")]["source"], got[("INTC", "supplier")]["share_pct"]) == ("profile", None)
