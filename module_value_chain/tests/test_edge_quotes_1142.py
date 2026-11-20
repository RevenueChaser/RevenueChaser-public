"""#1142: a profile edge whose own quote states another relation is not an edge.

Every quote below is from the census of 20 Nov 2026 (200 served-candidate profile edges read against their
filings, ``notes/revenuechaser/2026-11-20_0110_value-chain-profile-edge-census.md`` in claude-coordinator), with
the row number of the sample. The owner reads a channel, a distributor, a royalty and a dependency link as a real
link (20 Nov 2026), so those quotes must survive: they are the second half of this file.
"""
from __future__ import annotations

from RevenueChaser.module_value_chain import edge_quotes, engine


def _edge(name, quote, relation="customer"):
    return {"src": "AAA", "dst_name": name, "dst_ticker": "BBB", "relation": relation, "snippet": quote}


# --- the 23 wrong answers of the census, one quote per rule -------------------------------------------------

def test_a_prospect_is_no_edge():
    # row 2: a data centre's risk paragraph names the hyperscalers it hopes to let space to.
    assert edge_quotes.refuse(_edge("Oracle Corporation", (
        "our focus on the AI infrastructure segment introduces unique risks due to the high concentration of "
        "demand among a small number of potential hyperscaler tenants, such as Oracle Corporation"))) == "prospect"
    # row 98: "Valens chipsets for long vehicles have been evaluated by Stoneridge".
    assert edge_quotes.refuse(_edge("Stoneridge", "Valens chipsets for long vehicles have been evaluated by "
                                                 "Stoneridge, a leading designer and manufacturer")) == "prospect"


def test_a_drug_s_potential_treatment_is_not_a_prospect():
    # row 66, a doubtful-but-right edge: "potential" belongs to the therapy, not to the counterparty.
    assert edge_quotes.refuse(_edge("Alnylam Pharmaceuticals, Inc.", (
        "In March 2026, we entered into a multi-target research collaboration with Alnylam Pharmaceuticals, Inc. "
        "(Alnylam), to identify and validate novel gene targets for the potential treatment of cardiovascular "
        "disease."))) is None


def test_a_right_the_filer_has_not_used_is_no_edge():
    # row 93: GRFS may supply Abbott one day; it supplies Ortho.
    assert edge_quotes.refuse(_edge("Abbott Laboratories", (
        "we continue as exclusive supplier of antigens to Ortho, while retaining the right to supply antigens to "
        "third parties (including Abbott Laboratories, Siemens and OraSure Technologies)"),
        "customer")) == "retained_right"


def test_a_name_given_as_an_example_is_no_edge():
    # rows 11 and 146.
    assert edge_quotes.refuse(_edge("Microsoft", "Examples of companies in this space include Microsoft, Amazon "
                                                 "Web Services, and Google Cloud.")) == "example"
    assert edge_quotes.refuse(_edge("Facebook", "We use many frameworks, most notably REACT developed by "
                                                "Facebook", "supplier")) == "other_party_role"


def test_someone_else_s_statement_about_the_company_is_no_edge():
    # row 126: the filer is not a party to this sentence at all.
    assert edge_quotes.refuse(_edge("Merck & Co., Inc.", (
        "According to the American Urological Association, Merck & Co., Inc. is the sole manufacturer and "
        "supplier of TICE BCG in the U.S."), "supplier")) == "attribution"


def test_a_deal_between_two_other_parties_is_no_edge():
    # row 199.
    assert edge_quotes.refuse(_edge("Pfizer Inc.", (
        "Lasofoxifene was discovered through a research collaboration between Pfizer Inc. (“Pfizer”) and "
        "Ligand Pharmaceuticals (“Ligand”)."), "supplier")) == "between_others"


def test_a_description_of_the_market_is_no_edge():
    # row 161.
    assert edge_quotes.refuse(_edge("Plexus Manufacturing", (
        "The market for these devices and instruments is highly fragmented with primary supply chains "
        "concentrated across a few larger manufacturers and distributors, such as Cobalt Product Solutions, "
        "Sanmina Corporation and Plexus Manufacturing."), "supplier")) == "market_description"


def test_a_programme_another_company_runs_is_no_edge():
    # row 133.
    assert edge_quotes.refuse(_edge("IMAX Corporation", (
        "Pursuant to a consumer electronics device certification and licensing program operated by IMAX "
        "Corporation and DTS, Inc., since 2017, we have been offering consumers"), "supplier")) \
        == "other_party_role"


def test_a_guarantor_of_a_third_party_is_no_edge():
    # row 172.
    assert edge_quotes.refuse(_edge("Google", (
        "The Akela Fluidstack Leases benefit from substantial credit support provided by Google, which supports "
        "Fluidstack’s payment and performance obligations under the leases"), "supplier")) == "credit_support"


def test_a_joint_venture_a_lender_a_landlord_and_a_co_owner_are_no_edges():
    assert edge_quotes.refuse(_edge("GE Vernova Inc.", (            # row 179
        "We are commercializing and scaling manufacturing of our AirJoule systems through our global "
        "collaborations, including our 50/50 joint venture with GE Vernova Inc. (NYSE: GEV)"),
        "supplier")) == "joint_venture"
    assert edge_quotes.refuse(_edge("Delta Air Lines, Inc.", (      # row 136
        "Pursuant to the Credit Agreement, (i) the Lenders provided a term loan facility (the “Term Loan”) "
        "in the aggregate original principal amount of $390.0 million and (ii) Delta provided commitments for a "
        "revolving loan facility"), "supplier")) == "lender"
    assert edge_quotes.refuse(_edge("Walmart", (                    # row 24
        "Many of our Company stores benefit from customer traffic generated by Walmart retail stores, and if the "
        "customer traffic through these host stores decreases"))) == "landlord"
    assert edge_quotes.refuse(_edge("Cameco", (                     # row 167
        "We, together with institutional partners, hold an aggregate 51% interest (approximately 11% net to "
        "Brookfield Renewable) with Cameco owning 49%"), "supplier")) == "co_owner"


def test_a_brand_the_filer_sold_is_no_edge():
    # row 78: the quote names a credit-card programme, not a buyer.
    assert edge_quotes.refuse(_edge("General Motors", "During 2025, we sold the General Motors (GM) credit card "
                                                      "program to another issuer.")) == "asset_sold"


def test_one_name_in_a_list_of_partners_is_no_edge():
    # rows 18 and 30.
    assert edge_quotes.refuse(_edge("Ulta Beauty", (
        "We also sell merchandise through periodic exclusive design and creative partnerships, and shop-in-shop "
        "experiences, with partners such as Apple, Levi's, and Ulta Beauty"))) == "partner_list"
    assert edge_quotes.refuse(_edge("Microsoft", (
        "We work with agencies and partners across nine different partner categories, including System "
        "Integrators, Transformational partners and Resellers, which includes partners such as Microsoft, "
        "Accenture, Deloitte"))) == "partner_list"


def test_a_customer_list_is_not_a_partner_list():
    # row 59: "system integrators" names the kind of customer, and the clause says customers.
    assert edge_quotes.refuse(_edge("General Dynamics", (
        "A representative list of non-government customers during 2025 included tier one, large U.S. Government "
        "contractors and system integrators such as Northrop Grumman, Lockheed Martin, General Dynamics"))) is None


def test_the_other_side_of_the_chain_is_no_edge():
    # row 45: CAPL distributes ExxonMobil's fuel, so XOM is on the supplier side of a customer edge.
    assert edge_quotes.refuse(_edge("ExxonMobil", (
        "We are one of the ten largest independent distributors by motor fuel volume in the United States for "
        "ExxonMobil, BP and Marathon"))) == "direction_supplier_side"
    # row 139: Netflix distributes BILI's content, so it is not a supplier.
    assert edge_quotes.refuse(_edge("Netflix", (
        "We have also established business cooperation with overseas distributors, including Sony and Netflix, to "
        "distribute our original Chinese content to the global markets."), "supplier")) == "direction_customer_side"


# --- the links the owner reads as real (lenient reading, 20 Nov 2026) ---------------------------------------

def test_a_channel_a_distributor_a_royalty_and_a_dependency_survive():
    kept = [
        _edge("American Express", "Today, our FI partners include JPMorgan Chase Bank, National Association "
                                  "(\"Chase\"), Wells Fargo Bank and American Express Travel Related Services"),
        _edge("Thermo Fisher Scientific", "We sell our products directly to customers who are primarily located "
                                          "in North America, Europe and China, as well as through a distribution "
                                          "agreement with Thermo Fisher Scientific."),
        _edge("Marriott Vacations Worldwide Corporation", "For our timeshare properties, we receive royalty fees "
                                                          "under license agreements with Marriott Vacations "
                                                          "Worldwide Corporation and its affiliates"),
        _edge("PEDEVCO Corp.", "The field is operated by PEDEVCO Corp. (“PEDEVCO”).", "supplier"),
        _edge("London Stock Exchange Group", "they are distributed via Dow Jones's market data platform "
                                             "partners, including Bloomberg, London Stock Exchange Group and "
                                             "FactSet", "supplier"),
        _edge("Intel", "In September 2023, Tower and Intel signed an agreement under which Intel undertook to "
                       "build a capacity corridor at Tower’s instruction", "supplier"),
    ]
    assert [edge_quotes.refuse(e) for e in kept] == [None] * len(kept)


def test_a_quote_that_does_not_name_the_company_is_kept():
    # 4 of the 5 such edges in the census were right: the quote was simply cut at its 300-character cap.
    assert edge_quotes.refuse(_edge("Tyson Foods", "data – for example, farm management data – is "
                                                   "collected and verified through third-party auditors")) is None


# --- where the rule runs ------------------------------------------------------------------------------------

def test_profile_edges_drops_a_refused_edge_and_counts_it():
    profile = {"customers": [{"name": "Ulta Beauty", "quote": "with partners such as Apple, Levi's, and Ulta "
                                                              "Beauty"},
                             {"name": "Acme Widgets", "quote": "Acme is our largest customer"}]}
    refused: dict[str, int] = {}
    got = engine.profile_edges("TGT", profile, "2026-02-01", None, None, refused)
    assert [e["dst_name"] for e in got] == ["Acme Widgets"]
    assert refused == {"partner_list": 1}


def test_a_competitor_edge_is_not_checked():
    # The board serves customer and supplier only, and a competitor quote reads like a partner one.
    profile = {"named_competitors": [{"name": "Ulta Beauty", "quote": "with partners such as Apple, Levi's, and "
                                                                      "Ulta Beauty"}]}
    assert [e["relation"] for e in engine.profile_edges("TGT", profile)] == ["competitor"]
