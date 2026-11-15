"""The spine universe's market fields from the prices store (PR 7, G2): each listed name's market cap and price are
its newest in ``prices.duckdb`` (``rcdata.read.latest_market``), the old ``equity_universe`` by ticker where the
prices store has none; ``quote`` stays the old table's. An operating company's cap is its issuer's (every listed
class, as Yahoo's was); a fund's is its own, since one trust's CIK files many funds."""
from __future__ import annotations

from datetime import date

import os

import duckdb
import pytest

from RevenueChaser.core import rawstore, spine_reads, universe
from RevenueChaser.core.reporting_common import universe_provenance_html
from RevenueChaser.core.tests.test_universe_spine_flag import CAPS
from RevenueChaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401 - market roots per test
from RevenueChaser.rcdata.tests.test_spine_security import built  # noqa: F401 - the 10 names

NEWEST = date(2026, 10, 27)
# ticker -> (security id, newest bar session, close, own cap, issuer cap); a cap of None is a bar with no shares.
PRICES = {
    "MSFT": ("012141:01", NEWEST, 500.0, 3.7e12, 3.7e12),
    "HEI": ("005567:01", NEWEST, 200.0, 1.5e10, 2.6e10),
    "HEI-A": ("005567:02", NEWEST, 160.0, 1.1e10, 2.6e10),
    "VYLR": ("040001:01", NEWEST, 3.0, 4.0e8, 4.0e8),            # no cap in the old store: the prices store gives one
    "SPY": ("sym:SPY", NEWEST, 585.0, 6.1e11, 9.0e12),          # the trust's CIK sums other funds: its own cap counts
    "FDX": ("011234:01", NEWEST, 300.0, None, None),            # a bar but no shares yet: price new, cap old
    "ETN": ("016478:01", date(2026, 9, 1), 999.0, 9.9e11, 9.9e11),   # far behind the store's newest session: old
}






@pytest.mark.usefixtures("prices")
def test_the_caps_come_from_the_prices_store_and_the_old_table_where_it_has_none():
    rows = {r["ticker"]: r["market_cap"] for r in universe.classification_universe_rows(0)}
    assert rows["MSFT"] == 3.7e12                                  # the prices store's newest
    assert rows["HEI"] == rows["HEI-A"] == 2.6e10                   # the issuer's two listed classes
    assert rows["VYLR"] == 4.0e8 and "VYLR" in universe.classification_universe()     # now above the floor
    assert rows["TM"] == CAPS["TM"]                                 # not in the prices store: the old table's
    assert rows["FDX"] == CAPS["FDX"]                               # a bar with no shares: the old table's cap
    assert rows["ETN"] == CAPS["ETN"]                               # behind the store's newest session: the old one
    assert universe.classification_universe(0, operating_only=True)[:3] == ["MSFT", "TM", "WFC"]
    assert universe.classification_universe(0)[:3] == ["MSFT", "SPY", "TM"]      # PR 2: the fund is a universe name




@pytest.mark.usefixtures("prices")
def test_the_funnel_counts_the_prices_stores_caps():
    c = universe.universe_counts(3e8)
    assert c["no_market_cap"] == 0                                  # VYLR, the one name with no cap, has one now
    assert c["scanned_total"] == c["below_floor"] + c["no_market_cap"] + c["floor_total"]
    assert c["classification_total"] == len(universe.classification_universe(3e8))


@pytest.mark.usefixtures("spine")
def test_without_a_prices_store_the_old_table_is_read_as_before():
    rows = {r["ticker"]: r["market_cap"] for r in universe.classification_universe_rows(0)}
    assert rows["MSFT"] == CAPS["MSFT"] and rows["VYLR"] is None




