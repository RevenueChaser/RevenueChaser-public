"""Tests for the index membership registry (pure functions, no network)."""
import pytest

from revenuechaser.rcdata.tests import universe_store
from revenuechaser.core import index_registry as ir
from revenuechaser.core import rawstore


def test_index_memberships_inversion():
    indexes = {
        "sp500": {"AAPL", "MSFT"},
        "dow": {"AAPL"},
        "nasdaq": {"MSFT"},
    }
    memberships = ir._index_memberships(indexes)
    assert memberships["AAPL"] == ["S&P 500", "Dow Jones"]
    assert memberships["MSFT"] == ["S&P 500", "Nasdaq Composite"]
    assert "XXX" not in memberships


def test_the_labels_put_the_sp_indexes_first_and_name_every_russell_index():
    labels = list(ir.LABELS.values())
    assert labels[:3] == ["S&P 500", "Dow Jones", "S&P SmallCap 600"] and labels[-1] == "Nasdaq Composite"
    assert {"Russell 1000", "Russell 2000", "Russell 3000", "Russell Microcap", "Russell Midcap", "Russell Top 200",
            "Russell 1000 Growth", "Russell 1000 Value", "Russell 2000 Growth", "Russell 2000 Value",
            "Russell Midcap Growth", "Russell Midcap Value", "Russell Top 200 Growth", "Russell Top 200 Value",
            "Nasdaq-100 Top 30"} <= set(labels)


#: Group A (avo, 22 Nov 2026 23:17): the S&P and Dow Jones indexes read from their funds' files.
GROUP_A = {"sp100": "S&P 100", "sp500_growth": "S&P 500 Growth", "sp500_value": "S&P 500 Value",
           "sp500_ex_sp100": "S&P 500 ex S&P 100", "sp400_growth": "S&P MidCap 400 Growth",
           "sp400_value": "S&P MidCap 400 Value", "sp600_growth": "S&P SmallCap 600 Growth",
           "sp600_value": "S&P SmallCap 600 Value", "sp900_growth": "S&P 900 Growth", "sp900_value": "S&P 900 Value",
           "sp1500": "S&P Composite 1500", "sp_total_market": "S&P Total Market",
           "sp_hy_dividend_aristocrats": "S&P High Yield Dividend Aristocrats",
           "sp500_high_dividend": "S&P 500 High Dividend", "dj_us": "Dow Jones U.S.",
           "dj_us_select_dividend": "Dow Jones U.S. Select Dividend", "dj_us_select_reit": "Dow Jones U.S. Select REIT"}


def test_the_group_a_indexes_have_labels_after_the_headline_ones_and_before_russell():
    """Display order: the badge shows the first match, so the headline S&P labels stay first; the S&P family next,
    then Dow Jones, then Russell, and Nasdaq Composite last."""
    order = list(ir.LABELS)
    assert {s: ir.LABELS.get(s) for s in GROUP_A} == GROUP_A
    assert all(3 <= order.index(s) < order.index("russell_top200") for s in GROUP_A)
    assert max(order.index(s) for s in GROUP_A if s.startswith("sp")) < min(
        order.index(s) for s in GROUP_A if s.startswith("dj_"))
    assert len(set(ir.LABELS.values())) == len(ir.LABELS)             # no two slugs share a label


#: Group B: the S&P 500 sectors, the S&P Select Industry indexes and the Dow Jones U.S. Select industry indexes.
GROUP_B = {
    "sp500_energy": "S&P 500 Energy", "sp500_materials": "S&P 500 Materials",
    "sp500_industrials": "S&P 500 Industrials", "sp500_consumer_discretionary": "S&P 500 Consumer Discretionary",
    "sp500_consumer_staples": "S&P 500 Consumer Staples", "sp500_health_care": "S&P 500 Health Care",
    "sp500_financials": "S&P 500 Financials", "sp500_information_technology": "S&P 500 Information Technology",
    "sp500_communication_services": "S&P 500 Communication Services", "sp500_utilities": "S&P 500 Utilities",
    "sp500_real_estate": "S&P 500 Real Estate", "sp_biotech": "S&P Biotechnology Select Industry",
    "sp_oil_gas_exploration": "S&P Oil & Gas Exploration & Production Select Industry",
    "sp_metals_mining": "S&P Metals & Mining Select Industry",
    "sp_regional_banks": "S&P Regional Banks Select Industry",
    "sp_homebuilders": "S&P Homebuilders Select Industry", "sp_retail": "S&P Retail Select Industry",
    "sp_insurance": "S&P Insurance Select Industry", "sp_banks": "S&P Banks Select Industry",
    "sp_capital_markets": "S&P Capital Markets Select Industry",
    "sp_pharmaceuticals": "S&P Pharmaceuticals Select Industry",
    "sp_transportation": "S&P Transportation Select Industry",
    "dj_us_aerospace_defense": "Dow Jones U.S. Select Aerospace & Defense",
    "dj_us_home_construction": "Dow Jones U.S. Select Home Construction",
    "dj_us_insurance": "Dow Jones U.S. Select Insurance",
    "dj_us_medical_equipment": "Dow Jones U.S. Select Medical Equipment",
    "dj_us_health_care_providers": "Dow Jones U.S. Select Health Care Providers"}


def test_the_group_b_indexes_have_labels_s_and_p_before_dow_jones_before_russell():
    order = list(ir.LABELS)
    assert {s: ir.LABELS.get(s) for s in GROUP_B} == GROUP_B
    sp = [order.index(s) for s in GROUP_B if s.startswith("sp")]
    dj = [order.index(s) for s in GROUP_B if s.startswith("dj_")]
    assert 3 <= min(sp) and max(sp) < order.index("dj_us") < min(dj) and max(dj) < order.index("russell_top200")


def test_index_for_with_registry():
    reg = {"AAPL": {"index": ["S&P 500"]}}
    assert ir.index_for("aapl", reg) == ["S&P 500"]
    assert ir.index_for("MSFT", reg) == []


def test_annotate_cards_sets_index():
    cards = [{"ticker": "AAPL"}, {"ticker": "MSFT"}]
    reg = {"AAPL": {"index": ["S&P 500", "Dow Jones"]}}
    ir.annotate_cards(cards, reg)
    assert cards[0]["index"] == ["S&P 500", "Dow Jones"]
    assert cards[1]["index"] == []


def test_save_and_load_index(rawstore_tmp_db):
    """Since #642 PR 6 ``load_index`` is the spine's membership; this store holds no ``dow`` rows, so it is None."""
    universe_store.membership("sp500", {"AAPL", "MSFT"})
    assert ir.load_index("sp500") == {"AAPL", "MSFT"}
    assert ir.load_index("dow") is None








