"""#379 D2 (avo's card "Kolon + header"): every Co-movement run row names the Fetch that made it, and a Fetch writes
one header-only ``result_runs`` row.

- ``comov_runs`` gains ``run_id``, ``session_date`` (rule B on the run's ``as_of``) and ``dropped_json`` (the
  short-history, no-price and flat-print lists a reload cannot rebuild). Additive ALTER, no schema bump: a store
  that predates them reads NULL.
- One header per Fetch, written by the Fetch runner after the precompute, listing every ``as_of`` the Fetch stored
  or served (its own window plus the precompute windows). ``precompute`` itself, the store-only recompute and a
  Refresh write none (06 rule 9; the Refresh paths are also in ``app/tests/test_refresh_never_records_383.py``).

Offline, temp store.
"""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from RevenueChaser.core import calendar, rawstore
from RevenueChaser.module_comovement import config, engine
from RevenueChaser.module_comovement.tests import prices_bars
from RevenueChaser.module_comovement.tests.test_comovement import (
    _market_two_groups, _seed_ohlc, _seed_universe)

B = "module_comovement"


@pytest.fixture
def market(rawstore_tmp_db):
    """Two residual groups on a SPY factor, 400 sessions; tickers exclude SPY."""
    ret = _market_two_groups(n=400)
    tickers = [t for t in ret.columns if t != "SPY"]
    _seed_universe(tickers)
    _seed_ohlc(ret)
    return ret, tickers


@pytest.fixture
def runner(market, monkeypatch):
    from RevenueChaser.app import runners
    from RevenueChaser.module_comovement import ohlc

    monkeypatch.setattr(ohlc, "fetch_bulk", lambda tickers=None, no_fetch=False, **kw:
                        {"requested": 0, "fetched": 0, "no_fetch": no_fetch})
    return runners




def _runs() -> list[dict]:
    return rawstore.query("SELECT * FROM comov_runs ORDER BY as_of", db="comovement")


# ── the run columns ─────────────────────────────────────────────────────────
def test_a_stored_run_names_its_run_session_and_drop_lists(market):
    p = engine.run(no_fetch=True, persist=True, run_id="fetch-1")
    row = _runs()[0]
    assert row["run_id"] == "fetch-1"
    assert row["session_date"] == calendar.session_for(datetime.fromisoformat(p["as_of"])).session_date
    assert json.loads(row["dropped_json"]) == {
        "dropped": p["dropped"], "no_prices": p["no_prices"], "flat_prints": p["flat_prints"]}


def test_the_drop_lists_are_the_runs_own(market):
    """A name with too few bars is in the stored list, not an empty one."""
    ret, tickers = market
    _seed_ohlc(ret[["A1"]].tail(20).rename(columns={"A1": "SHORT"}))
    _seed_universe([*tickers, "SHORT"])
    p = engine.run(no_fetch=True, persist=True, run_id="fetch-1")
    assert "SHORT" in p["dropped"]
    assert json.loads(_runs()[0]["dropped_json"])["dropped"] == p["dropped"]


def test_a_persisting_run_with_no_id_gets_a_fresh_one(market):
    engine.run(no_fetch=True, persist=True)
    assert _runs()[0]["run_id"]


def test_one_precompute_shares_one_id_across_its_windows(market):
    engine.precompute()
    ids = {r["run_id"] for r in _runs()}
    assert len(_runs()) == 2 and len(ids) == 1 and None not in ids


def test_precompute_reports_each_windows_as_of(market):
    fetch = engine.run(no_fetch=True, persist=True, run_id="fetch-1")         # 252
    served: dict[int, str] = {}
    assert engine.precompute(run_id="fetch-1", as_ofs=served) == {126: "computed", 252: "reused"}
    assert served[252] == fetch["as_of"]
    assert served[126] == next(r["as_of"] for r in _runs() if r["window_days"] == 126)


def test_a_store_that_predates_the_columns_reads_null(isolate_rawstore):
    """The additive ALTER (``_reconcile_table``): an old row keeps its values and reads NULL in the new columns."""
    new = ("run_id", "session_date", "dropped_json")
    old = [c for c in rawstore.MANIFEST["comov_runs"]["columns"] if c.split()[0] not in new]
    with rawstore.connect(db="comovement") as conn:
        conn.execute(f"CREATE TABLE comov_runs ({', '.join(old)})")
        conn.execute("INSERT INTO comov_runs (as_of, window_days, config_hash) VALUES "
                     "('2026-10-01T20:00:00.000000+00:00', 252, 'abc')")
    rawstore.ensure_table("comov_runs")
    row = rawstore.query("SELECT * FROM comov_runs", db="comovement")[0]
    assert row["window_days"] == 252 and row["config_hash"] == "abc"
    assert row["run_id"] is None and row["session_date"] is None and row["dropped_json"] is None


# ── the header: Fetch only, once, after the precompute ──────────────────────














