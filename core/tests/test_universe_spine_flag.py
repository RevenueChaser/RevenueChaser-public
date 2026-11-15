"""``core/universe.py`` reads the identity spine only (#642 PR 6 removed ``RC_UNIVERSE_SOURCE`` and the old store
path): membership, names, classification and types through ``rcdata.read`` and, with no prices store here, the market
fields (cap, price, quote) from the old ``equity_universe`` (the prices store's: ``test_universe_market_prices``).

Every test here is the **membership rule** that applies where the spine holds no ``my_universe`` list: Tiers A and B
whole (PR 2, avo 30 Oct 2026). The test spine's ``spine/security`` build writes that list, so ``drop_my_universe``
drops it. The list path is ``core/tests/test_universe_my_universe.py``."""
from __future__ import annotations

import pytest

from RevenueChaser.core import rawstore, universe
from RevenueChaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401 - market roots per test
from RevenueChaser.rcdata.tests.test_spine_security import built, run_all  # noqa: F401 - the 10 names

CAPS = {"MSFT": 3.1e12, "ETN": 1.3e11, "HEI": 3.0e10, "HEI-A": 2.0e10, "NVR": 2.5e10, "TM": 2.4e11,
        "CNA": 1.2e10, "FDX": 6.5e10, "WFC": 2.3e11, "SPY": 6.0e11, "WFC-PC": 1.0e9}






def drop_my_universe() -> None:
    """Make the built spine the one this module's rule is about: no ``my_universe`` table, so the tiers decide.

    A function and not a fixture on purpose: ``spine`` is imported by other modules
    (``test_bar_scope_spine``, ``test_universe_market_prices``), and a fixture it depended on would have to be
    imported into every one of them by name.
    """
    import duckdb

    from RevenueChaser.core import spine_reads
    from RevenueChaser.rcdata import serving
    con = duckdb.connect(str(serving.live_path("spine")))
    try:
        con.execute("DROP TABLE IF EXISTS my_universe")
    finally:
        con.close()
    spine_reads.clear()




@pytest.mark.usefixtures("spine")
def test_the_spine_universe_is_its_listed_names_by_cap_and_a_board_may_ask_for_operating_ones():
    names = universe.classification_universe(0, operating_only=True)
    assert names[:3] == ["MSFT", "TM", "WFC"] and "OLDONLY" not in names
    assert not {"SPY", "WFC-PC"} & set(names)                               # etp and preferred, as before
    assert "VYLR" in names and names[-1] == "VYLR"                          # no cap in the old store: last
    # No market-cap floor (avo, 29 Oct 2026): the default is the whole set, VYLR's missing cap included.
    assert universe.classification_universe(operating_only=True) == names
    assert (universe.classification_universe(3e8, operating_only=True)
            == [t for t in names if CAPS.get(t, 0) >= 3e8])
    # PR 2 (avo, 30 Oct 2026): the universe itself is every A+B type, the ETF and the preferred included.
    every = universe.classification_universe(0)
    assert {"SPY", "WFC-PC"} <= set(every) and set(every) - {"SPY", "WFC-PC"} == set(names)


@pytest.mark.usefixtures("spine")
def test_rows_names_and_classification_come_from_the_spine():
    rows = {r["ticker"]: r for r in universe.classification_universe_rows(0)}
    assert rows["MSFT"] == {"ticker": "MSFT", "market_cap": 3.1e12, "sector": "Technology",
                            "industry": "Software & Services", "security_type": rows["MSFT"]["security_type"]}
    assert rows["SPY"]["security_type"] == "etp"
    gics = universe.spine_gics(["TM", "nvr"])
    assert (gics["TM"].sector, gics["NVR"].industry) == ("Consumer Cyclical", "Consumer Durables & Apparel")
    assert universe.excluded_tickers() == {"SPY", "WFC-PC"}
    cached = {r["ticker"]: r for r in universe.load_cached_universe()}
    assert cached["MSFT"]["name"] == "MICROSOFT CORP" and cached["MSFT"]["price"] == 10.0


@pytest.mark.usefixtures("spine")
def test_the_funnel_counts_add_up_on_the_spine():
    c = universe.universe_counts(3e8)
    assert c["scanned_total"] == 12                      # the 14 SEC rows less the OTC and the no-exchange name
    assert c["scanned_total"] == c["below_floor"] + c["no_market_cap"] + c["floor_total"]
    assert c["floor_total"] == c["funds_etfs"] + c["spacs"] + c["other_securities"] + c["operating_total"]
    assert (c["funds_etfs"], c["other_securities"], c["no_market_cap"]) == (1, 1, 1)
    assert c["classification_total"] == c["floor_total"] == len(universe.classification_universe(3e8))
    assert c["operating_total"] == len(universe.classification_universe(3e8, operating_only=True))


@pytest.mark.usefixtures("spine")
def test_filter_fields_take_the_index_badges_from_the_spine_membership():
    fields = universe.filter_fields(["MSFT", "HEI", "NOPE"])
    assert fields["MSFT"]["index"] == ["S&P 500", "Nasdaq Composite"]
    assert fields["MSFT"]["sector"] == "Technology" and fields["MSFT"]["market_cap"] == 3.1e12
    assert fields["HEI"]["index"] == []                   # the MidCap 400 has no filter label yet (filter unchanged)
    assert fields["NOPE"]["sector"] == "Unclassified"








