"""Sector Rotation board, end to end — with the week-range picker.

This board is the reason the harness exists. Its range picker was shipped
broken twice: `run_rotation_latest` backfilled the requested window and then
rendered *every* stored date, and `/api/rotation/weeks` only listed weeks that
already had snapshots, so "Fetch Data Range" could never reach a new week.
Both passed the entire unit suite.

Since M-ROT-2 (#374) the RRG and the range backfill read their closes from the stored daily bars, since PR 9 (G3)
the prices store's (``price_bar_daily``): the test process seeds them into the dashboard's prices store the way the
prices build leaves them, and no Fetch asks the provider for a candle of a rotation ETF.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date, timedelta

import pytest

from .harness.dashboard_driver import Dashboard, JobResult
from .harness.shared import clear_cache_dir, shared_dashboard, store_of

# The tests that only read what one default Fetch left behind share it (``fetched``); this mark keeps them on one
# worker under ``--dist loadgroup``. A test that fetches a range, restarts or needs an empty store keeps its own
# dashboard.
SHARED = pytest.mark.xdist_group("e2e-sector-rotation-shared-fetch")

CANDLES = 200  # enough history for the 3-month RS lookback


def _synthetic_ohlc(ticker: str) -> list[dict]:
    """Deterministic candles whose drift is seeded by the ticker.

    Different ETFs must land in different RRG quadrants, otherwise the board
    renders one indistinguishable blob and the assertions prove nothing.
    """
    seed = int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)
    drift = ((seed % 21) - 10) / 1000.0  # -1%..+1% per step
    start = date(2026, 2, 1)
    price = 100.0
    rows = []
    for i in range(CANDLES):
        price *= 1.0 + drift + (((seed >> i % 16) & 3) - 1.5) / 2000.0
        d = start + timedelta(days=i)
        rows.append({
            "date": d.isoformat(),
            "open": round(price * 0.995, 4),
            "high": round(price * 1.01, 4),
            "low": round(price * 0.99, 4),
            "close": round(price, 4),
            "total_volume": 1_000_000 + i,
        })
    return rows


def _route_ohlc(mock) -> None:
    """Serve OHLC for any ticker the rotation universe asks for."""
    def handler(path: str):
        # /api/stock/<ticker>/ohlc/<candle_size>
        parts = path.strip("/").split("/")
        ticker = parts[2] if len(parts) > 2 else "SPY"
        return {"data": _synthetic_ohlc(ticker)}

    mock.route("/api/stock/", payload=handler)
    mock.route("/api/etfs/", payload={"data": []})


@pytest.fixture
def ohlc_routes(provider_routes):
    _route_ohlc(provider_routes)
    return provider_routes


def _seed_bars():
    """Prices-store bars for SPY and every rotation ETF, ~19 months up to the latest complete session."""
    import revenuechaser.core.rawstore as rawstore
    from revenuechaser.core import calendar
    from revenuechaser.module_sector_rotation import engine
    from revenuechaser.module_sector_rotation.tests.bars_seed import seed

    rawstore.ensure_all_tables()
    session = calendar.latest_complete_session()
    for t in ["SPY", *engine.rrg_tickers()]:
        seed(t, session, start=session - timedelta(days=580))
    return session


def _rotation_candle_calls(routes, since: int = 0) -> list[str]:
    """Provider candle requests for a rotation ETF (``/api/stock/<ticker>/ohlc/...``) after the first ``since``."""
    return _rotation_candle_paths([q.path for q in routes.requests()[since:]])


def _rotation_candle_paths(paths: list[str]) -> list[str]:
    from revenuechaser.core import rotation_reference
    out = []
    for path in paths:
        parts = path.strip("/").split("/")
        if len(parts) > 3 and parts[3] == "ohlc" and parts[2] in rotation_reference.rotation_etfs():
            out.append(path)
    return out


@dataclass
class Fetched:
    dashboard: Dashboard
    result: JobResult
    session: date                   # the session the seeded bars end on
    requests: list[str]             # every provider path asked for since the dashboard started, Fetch included


@pytest.fixture(scope="module")
def _fetched_once(tmp_path_factory, mock_provider):
    with shared_dashboard(tmp_path_factory, mock_provider, "sector-rotation-shared") as dash:
        with store_of(dash):
            session = _seed_bars()
        _route_ohlc(mock_provider)
        result = dash.run_job("/run/rotation")
        # The Fetch also queued the money-flow job (app/dashboard.py, run_rotation);
        # its OHLC requests must not land in a later "no network" window.
        dash.wait_until_idle()
        yield Fetched(dashboard=dash, result=result, session=session,
                      requests=[q.path for q in mock_provider.requests()])


@pytest.fixture
def fetched(_fetched_once):
    """ONE default Fetch on a seeded store, shared by the read-only tests of this module."""
    f = _fetched_once
    assert f.result.ok, f"rotation fetch failed: {f.result}\n{f.dashboard.logs()}"
    return f


@SHARED
class TestFetch:
    def test_fetch_persists_a_snapshot(self, fetched):
        assert fetched.dashboard.table_count("rotation_snapshots") > 0

    def test_the_board_renders_the_universe(self, fetched):
        html = fetched.dashboard.view("module_sector_rotation").text
        assert "XLK" in html

    def test_provenance_reports_a_data_date(self, fetched):
        assert fetched.dashboard.data_as_of("module_sector_rotation") is not None

    def test_the_rrg_is_the_latest_session_from_the_prices_store(self, fetched):
        """M-ROT-2: the snapshot is dated by the session (#283), and no rotation ETF candle is requested (A5)."""
        assert _newest_stored(fetched.dashboard) == fetched.session.isoformat()
        assert [p for p in _rotation_candle_paths(fetched.requests) if p.endswith("/1w")] == []


class TestRefreshIsOfflineAndFaithful:
    # The two shared tests empty the cache and Refresh rebuilds it, so a later shared test finds it whole again.
    @SHARED
    def test_refresh_rebuilds_a_deleted_artifact(self, fetched):
        dash = fetched.dashboard
        clear_cache_dir(dash.cache_dir)
        r = dash.view("module_sector_rotation", refresh=True)
        assert r.status_code == 200
        assert "XLK" in r.text

    @SHARED
    def test_refresh_makes_no_network_calls(self, ohlc_routes, fetched):
        dash = fetched.dashboard
        clear_cache_dir(dash.cache_dir)
        before = ohlc_routes.request_count
        assert dash.view("module_sector_rotation", refresh=True).status_code == 200
        assert ohlc_routes.request_count == before, (
            "refresh reached the network: "
            f"{[q.path for q in ohlc_routes.requests()[before:]]}")


class TestWeekPicker:
    """`/api/rotation/weeks` feeds the "Fetch Data Range" calendar."""



    @SHARED
    def test_fetched_weeks_are_flagged(self, fetched):
        weeks = fetched.dashboard.get("/api/rotation/weeks").json()["weeks"]
        assert any(w["has_data"] for w in weeks), \
            "a completed fetch must show up as a week with data"




def _header_date(html: str) -> str:
    """The date the board header names (the first field of ``<div class="meta">``)."""
    import re
    return re.search(r'<div class="meta">(\d{4}-\d{2}-\d{2})', html).group(1)


def _rendered_rows(html: str) -> int:
    """Snapshot rows the board actually rendered (one ``rs_ratio`` each)."""
    return html.count("rs_ratio")


def _stored(dashboard, what: str, start: str = None, end: str = None):
    import duckdb
    dashboard.wait_until_idle()    # /run/rotation also queues moneyflow; every job writes its job_runs row (#282)
    conn = duckdb.connect(str(dashboard.db_file("rotation_snapshots")))
    try:
        if start and end:
            return conn.execute(
                f"SELECT {what} FROM rotation_snapshots "
                "WHERE as_of_date >= ? AND as_of_date <= ?", [start, end]).fetchone()[0]
        return conn.execute(f"SELECT {what} FROM rotation_snapshots").fetchone()[0]
    finally:
        conn.close()


def _stored_rows(dashboard, start: str = None, end: str = None) -> int:
    return _stored(dashboard, "count(*)", start, end)


def _stored_tickers(dashboard, start: str = None, end: str = None) -> int:
    return _stored(dashboard, "count(DISTINCT ticker)", start, end)


def _newest_stored(dashboard, start: str = None, end: str = None) -> str:
    return _stored(dashboard, "max(as_of_date)", start, end)
