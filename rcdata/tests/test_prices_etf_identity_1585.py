"""#1585 (avo 27 Nov 2026, option A): the prices build checks every universe fund's claimed gvkey:iid against the
one the spine's ``etf`` row gives, and names each disagreement; nothing it serves changes."""
from __future__ import annotations

import duckdb

from revenuechaser.rcdata.build.prices import serving as prices_serving


def _con(etf, spine=(), series=(), alias=(), universe_etf=None):
    """The five temp tables the check reads, in the build's shapes (``_spine``, ``_universe``, ``GVKEY_ALIAS``)."""
    con = duckdb.connect()
    con.execute("CREATE TABLE stg_etf (ticker TEXT, aum DOUBLE, is_etn BOOLEAN, is_cef BOOLEAN, gvkey TEXT, iid TEXT)")
    con.executemany("INSERT INTO stg_etf VALUES (?, 1e9, NULL, NULL, ?, ?)", list(etf))
    con.execute("CREATE TABLE stg_spine (ticker TEXT, cik TEXT, tier TEXT, security_type TEXT, gvkey TEXT, iid TEXT, "
                "composite_figi TEXT, security_id TEXT, cusip TEXT, is_etf BOOLEAN, inception DATE)")
    con.executemany("INSERT INTO stg_spine (ticker, gvkey, iid, security_id) VALUES (?, ?, ?, ?)", list(spine))
    con.execute("CREATE TABLE _etf_tic_series (gid TEXT, tic TEXT, pick BIGINT)")
    con.executemany("INSERT INTO _etf_tic_series VALUES (?, ?, ?)", list(series))
    con.execute("CREATE TABLE _gvkey_alias (gid TEXT, security_id TEXT)")
    con.executemany("INSERT INTO _gvkey_alias VALUES (?, ?)", list(alias))
    con.execute("CREATE TABLE _universe_etf (ticker TEXT, tic TEXT)")
    tickers = universe_etf if universe_etf is not None else [t for t, _, _ in etf]
    con.executemany("INSERT INTO _universe_etf VALUES (?, ?)", [(t, t) for t in tickers])
    return con


def _kinds(con):
    return {(kind, key) for kind, key, _ in prices_serving.etf_identity_issues(con)}


def test_a_ticker_series_that_differs_from_the_spine_is_named():
    con = _con([("XYZ", "111111", "01")], series=[("222222:01", "XYZ", 1)])
    found = prices_serving.etf_identity_issues(con)
    assert [(k, t) for k, t, _ in found] == [("etf_identity_disagrees", "XYZ")]
    assert "111111:01" in found[0][2] and "ticker series 222222:01" in found[0][2]


def test_a_matching_claim_is_no_issue():
    con = _con([("XYZ", "111111", "01")], series=[("111111:01", "XYZ", 1)])
    assert _kinds(con) == set()


def test_a_cusip_alias_through_the_fetch_id_that_differs_is_named():
    con = _con([("ABC", "333333", "01")], alias=[("444444:01", "sym:ABC")])
    assert _kinds(con) == {("etf_identity_disagrees", "ABC")}


def test_one_matching_and_one_differing_claim_is_still_named():
    """Every claim is compared, not the first one found."""
    con = _con([("ABC", "333333", "01")], spine=[("ABC", "333333", "01", "333333:01")],
               alias=[("555555:01", "333333:01")])
    assert _kinds(con) == {("etf_identity_disagrees", "ABC")}


def test_a_spine_gid_no_path_claims_is_unclaimed():
    con = _con([("NEW", "666666", "01")])
    assert _kinds(con) == {("etf_identity_unclaimed", "NEW")}


def test_a_fund_the_spine_keys_without_a_gvkey_is_not_checked():
    """DVAL's shape: a figi- or cik-only etf row has no gvkey:iid to compare (#1600)."""
    con = _con([("DVAL", None, None)], alias=[("777777:01", "sym:DVAL")])
    assert _kinds(con) == set()


def test_a_fund_outside_the_universe_is_not_checked():
    con = _con([("OUT", "888888", "01")], series=[("999999:01", "OUT", 1)], universe_etf=[])
    assert _kinds(con) == set()


def test_a_build_without_the_temp_tables_finds_nothing():
    assert prices_serving.etf_identity_issues(duckdb.connect()) == []


def test_both_kinds_are_registered_for_ops():
    assert {"etf_identity_disagrees", "etf_identity_unclaimed"} <= set(prices_serving.ISSUE_KINDS)
