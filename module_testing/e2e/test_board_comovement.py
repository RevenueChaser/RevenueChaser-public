"""Co-movement board, end to end.

The board is store-backed: membership comes from D01 (``price_bars_daily``, since
the #379 D01 switch), metadata from ``equity_universe``. These tests seed those
tables directly, the way Daily Bars and the universe pull leave them, and prove
the contract in docs/data_retrieval.md:

1. Fetch persists a dated run and renders the board, and downloads nothing
   (Daily Bars is D01's one writer).
2. Refresh rebuilds a deleted artifact from the store with zero provider calls.
3. Only what reached .store survives a restart.
"""
from __future__ import annotations

from RevenueChaser.rcdata.tests import universe_store
import time
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from .harness.dashboard_driver import Dashboard, JobResult
from .harness.shared import clear_cache_dir, shared_dashboard, store_of

# The tests that only read what one default Fetch left behind share it (``fetched``); this mark keeps them on one
# worker under ``--dist loadgroup``. A test that switches the window, restarts, saves settings or watches the
# Fetch's own provider calls keeps its own dashboard (``seeded_comovement``).
SHARED = pytest.mark.xdist_group("e2e-comovement-shared-fetch")


def _returns(n=200, seed=7):
    """Four tight groups of four names each (#97: a group is named only when its industry is enriched
    versus the cut, so two equal groups in eight names, lift 2, would stay neutral)."""
    rng = np.random.default_rng(seed)
    data = {}
    for group in (("A1", "A2", "A3", "A4"), ("B1", "B2", "B3", "B4"),
                  ("C1", "C2", "C3", "C4"), ("D1", "D2", "D3", "D4")):
        base = rng.normal(0, 0.01, n)
        for t in group:
            data[t] = base + rng.normal(0, 0.0004, n)
    return pd.DataFrame(data, index=pd.date_range("2025-09-01", periods=n, freq="D"))


def _benchmarks(index, seed=7):
    """Benchmark columns (SPY/DIA/QQQ) on the same dates.

    D01 holds all three (Daily Bars keeps the benchmarks), so the Remove-market
    control has data.
    """
    rng = np.random.default_rng(seed + 1)
    return pd.DataFrame(
        {b: rng.normal(0, 0.008, len(index)) for b in ("SPY", "DIA", "QQQ")},
        index=index)


_INDUSTRY = {"A1": "Semiconductors", "A2": "Semiconductors", "A3": "Semiconductors",
             "A4": "Semiconductors", "B1": "Banks - Diversified", "B2": "Banks - Diversified",
             "B3": "Banks - Diversified", "B4": "Banks - Diversified",
             **{f"C{i}": "Oil & Gas E&P" for i in range(1, 5)},
             **{f"D{i}": "Utilities - Regulated Electric" for i in range(1, 5)}}




def _seed() -> None:
    ret = _returns()
    tickers = list(ret.columns)

    universe_store.replace([{
        "ticker": t, "market_cap": 1.0e10, "sector": "Financial Services" if t[0] == "B" else "Technology",
        "price": 10.0, "name": t + " Inc", "industry": _INDUSTRY[t], "quote": {"symbol": t},
    } for t in tickers])

    now = time.time()
    rows = []
    for t in tickers:
        price = 100 * np.exp(ret[t].cumsum())
        for ts, p in price.items():
            rows.append({"ticker": t, "ts": ts.isoformat(), "open": p, "high": p,
                         "low": p, "close": float(p), "volume": 1.0, "cached_at": now})
    bench = _benchmarks(ret.index)
    for t in bench.columns:
        price = 100 * np.exp(bench[t].cumsum())
        for ts, p in price.items():
            rows.append({"ticker": t, "ts": ts.isoformat(), "open": p, "high": p,
                         "low": p, "close": float(p), "volume": 1.0, "cached_at": now})
    from RevenueChaser.module_comovement.tests.prices_bars import write_bars
    write_bars(rows)


@dataclass
class Fetched:
    dashboard: Dashboard
    result: JobResult


@pytest.fixture(scope="module")
def _fetched_once(tmp_path_factory, mock_provider):
    with shared_dashboard(tmp_path_factory, mock_provider, "comovement-shared") as dash:
        with store_of(dash):
            _seed()
        yield Fetched(dashboard=dash, result=dash.run_job("/run/module_comovement"))


@pytest.fixture
def fetched(_fetched_once):
    """The seeded store after ONE default Fetch, shared by the read-only tests of this module."""
    f = _fetched_once
    assert f.result.ok, f"comovement fetch failed: {f.result}\n{f.dashboard.logs()}"
    return f


class TestFetch:
    @SHARED
    def test_fetch_persists_a_run(self, fetched):
        dashboard, result = fetched.dashboard, fetched.result
        assert result.ok, f"comovement fetch failed: {result}\n{dashboard.logs()}"
        # the Fetch's own run (1y, reused by the precompute) + the 6m precompute (#95)
        assert dashboard.table_count("comov_runs") == 2
        assert dashboard.table_count("comov_members") > 0



    @SHARED
    def test_the_board_renders_clusters(self, fetched):
        html = fetched.dashboard.view("module_comovement").text
        assert "Co-movement" in html
        assert "A1" in html and "B1" in html

    @SHARED
    def test_the_board_names_each_group_by_its_industry(self, fetched):
        html = fetched.dashboard.view("module_comovement").text
        # At the broad cut the four banks are one group, named after their shared industry text (#266).
        # (The four semiconductor names are not a group on this seed, and the finer cuts leave single names.)
        assert '"cluster_label": "Banks - Diversified 100%, ×4.0", "cluster_n": 4' in html
        assert "sub_industry" not in html and "industry_group" not in html




class TestRefreshIsOfflineAndFaithful:
    # The three shared tests empty the cache and Refresh rebuilds it, so a later shared test finds it whole again.
    @SHARED
    def test_refresh_rebuilds_a_deleted_artifact(self, fetched):
        dashboard = fetched.dashboard
        clear_cache_dir(dashboard.cache_dir)
        assert not dashboard.artifact("comovement_latest.html").exists()
        r = dashboard.view("module_comovement", refresh=True)
        assert r.status_code == 200
        assert "Co-movement" in r.text
        # The empty-state page also says "Co-movement": only the rebuilt artifact and its clusters prove the rebuild.
        assert dashboard.artifact("comovement_latest.html").exists(), "Refresh did not rebuild the artifact"
        assert "A1" in r.text and "B1" in r.text

    @SHARED
    def test_refresh_makes_no_network_calls(self, fetched, provider_routes):
        dashboard = fetched.dashboard
        clear_cache_dir(dashboard.cache_dir)
        before = provider_routes.request_count
        r = dashboard.view("module_comovement", refresh=True)
        assert r.status_code == 200
        assert provider_routes.request_count == before, (
            "refresh reached the network: "
            f"{[q.path for q in provider_routes.requests()[before:]]}")


    @SHARED
    def test_refresh_does_not_write_the_store(self, fetched):
        dashboard = fetched.dashboard
        before = dashboard.table_count("comov_runs")
        clear_cache_dir(dashboard.cache_dir)
        r = dashboard.view("module_comovement", refresh=True)
        assert r.status_code == 200
        assert dashboard.table_count("comov_runs") == before, (
            "Refresh wrote a comov_runs row; docs/data_retrieval.md says Refresh writes .cache only")


class TestEmptyStore:
    def test_a_board_with_no_data_renders_an_empty_state(self, dashboard):
        r = dashboard.view("module_comovement")
        assert r.status_code == 200
        assert "No clusters yet" in r.text


# ── window control + editable settings (#40 Part B) ──────────────────────────
import re  # noqa: E402





def _step(html: str, prefix: str) -> int:
    from RevenueChaser.module_testing.e2e.test_board_settings import _card_steps

    hits = {k: v for k, v in _card_steps(html).items() if k.startswith(prefix)}
    assert len(hits) == 1, f"expected one card row starting {prefix!r}, got {hits}"
    return next(iter(hits.values()))




def _board(dashboard, **params):
    return dashboard.view("module_comovement", **params).text




