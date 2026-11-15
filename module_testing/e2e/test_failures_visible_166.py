"""#166 end to end: a failing Unusual Whales call is named on the job and the board, and never becomes data.

Each test breaks one provider call through the mock server and drives the real dashboard:

* Money Flow ranks the stored bars since M-ROT-3 (#374), the prices store's since PR 9: an ETF the store lacks flags
  the leaderboard partial on the board, it never replaces the newest complete leaderboard in result history, and no
  candle is asked for;
* the range backfill reads the stored bars since M-ROT-2 (#374), so no candle answer reaches it: with SPY absent from
  the prices store it writes no day and says why, and an ETF the store lacks is left out of the days it writes, with
  no provider call;
* the second page of an expiry's option chain answers 500: OIPD fits what it has, warns, and does not save it.

The healthy path is asserted next to each failure so a fix that blanks everything cannot pass.
"""
from __future__ import annotations

import hashlib
import math
import os
import re
import shutil
import subprocess
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import parse_qs

import numpy as np
import pytest

from . import harness

from RevenueChaser.module_oipd import opd_math

CANDLES = 200
THEME_HOLDINGS = [{"ticker": t, "name": f"{t} Corp", "weight": str(w), "updated": "2026-09-01"}
                  for t, w in (("AAA", 9), ("BBB", 6), ("CCC", 3))]
BOOM = {"error": "boom"}


# ── fixtures ─────────────────────────────────────────────────────────────────────────────

def _synthetic_ohlc(ticker: str) -> list[dict]:
    seed = int(hashlib.sha256(ticker.encode()).hexdigest()[:8], 16)
    drift = ((seed % 21) - 10) / 1000.0
    start, price, rows = date(2026, 2, 1), 100.0, []
    for i in range(CANDLES):
        price *= 1.0 + drift + (((seed >> i % 16) & 3) - 1.5) / 2000.0
        rows.append({"date": (start + timedelta(days=i)).isoformat(), "open": round(price * 0.995, 4),
                     "high": round(price * 1.01, 4), "low": round(price * 0.99, 4),
                     "close": round(price, 4), "total_volume": 1_000_000 + i})
    return rows


@pytest.fixture
def routes(provider_routes):
    """OHLC for any ticker, three holdings for every ETF."""
    provider_routes.route("/api/stock/", payload=lambda path: {
        "data": _synthetic_ohlc(path.strip("/").split("/")[2] if len(path.strip("/").split("/")) > 2 else "SPY")})
    provider_routes.route("/api/etfs/", payload={"data": THEME_HOLDINGS})
    return provider_routes


def _break(routes, ticker: str) -> None:
    routes.route(f"/api/stock/{ticker}/ohlc", payload=BOOM, status=500)


def _heal(routes, ticker: str) -> None:
    routes._routes.pop(f"/api/stock/{ticker}/ohlc", None)


def _query(dashboard, sql: str, params=()) -> list[tuple]:
    """One query on the file that holds the table after its FROM (board tables have their own file, S9)."""
    import re

    import duckdb
    conn = duckdb.connect(str(dashboard.db_file(re.search(r"\bFROM\s+(\w+)", sql).group(1))), read_only=True)
    try:
        return conn.execute(sql, list(params)).fetchall()
    finally:
        conn.close()


def _api_moneyflow(dashboard) -> dict:
    return dashboard.get("/api/moneyflow").json()




def _drop_bars(ticker: str) -> None:
    """Remove ``ticker``'s stored bars from the prices store ``_seed_bars`` pointed at."""
    from RevenueChaser.rcdata.tests import prices_store
    prices_store.delete_bars(ticker)




def _candle_calls(routes) -> list[str]:
    return [q.path for q in routes.requests("/api/stock/") if "/ohlc" in q.path]


# ── SPY candles down ─────────────────────────────────────────────────────────────────────



# ── one ETF down ─────────────────────────────────────────────────────────────────────────



# ── the board note (headless Chrome) ─────────────────────────────────────────────────────

def _chrome() -> str | None:
    override = os.environ.get("RC_CHROME")
    if override:
        return override if Path(override).exists() or shutil.which(override) else None
    for name in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        if shutil.which(name):
            return shutil.which(name)
    return None


@pytest.fixture
def chrome() -> str:
    path = _chrome()
    if path is None:
        msg = "no Chrome/Chromium for the money-flow note: set RC_CHROME or install google-chrome / chromium"
        if os.environ.get("CI", "").lower() == "true":
            pytest.fail(msg)
        pytest.skip(msg)
    return path


def _dump_dom(chrome: str, url: str, profile: Path) -> str:
    out = subprocess.run(
        [chrome, "--headless", "--no-sandbox", "--disable-gpu", "--no-first-run", "--disable-extensions",
         f"--user-data-dir={profile}",
         # as in ``test_board_sec_13f``: a board's CDN plotly request would pause the virtual clock
         "--host-resolver-rules=MAP * ~NOTFOUND, EXCLUDE localhost, EXCLUDE 127.0.0.1",
         "--virtual-time-budget=6000", "--dump-dom", url],
        capture_output=True, text=True, encoding="utf-8", timeout=harness.CHROME_TIMEOUT_S)
    assert "<html" in out.stdout.lower(), f"Chrome dumped no DOM: {out.stderr[-1500:]}"
    return out.stdout


def _note(dom: str) -> str | None:
    m = re.search(r'<div id="mf-note"[^>]*>(.*?)</div>', dom, re.S)
    return m.group(1) if m else None




# ── OIPD: the second page of an expiry fails ─────────────────────────────────────────────

_SPOT, _R, _TICKER = 100.0, 0.04, "TST"
_TRUE = dict(a=0.02, b=0.12, rho=-0.5, m=0.0, sigma=0.15)


def _expiries():
    today = date.today()
    return [(today + timedelta(days=n)).isoformat() for n in (30, 60, 120)]


def _contracts_for(expiry: str) -> list[dict]:
    """About 600 contracts per expiry: more than one 500-row page, so a second page exists."""
    d = (date.fromisoformat(expiry) - date.today()).days
    T = d / 365.0
    F = _SPOT * math.exp(_R * T)
    out = []
    for K in np.arange(70.0, 130.0, 0.2):
        k = math.log(K / F)
        iv = math.sqrt(float(opd_math.svi_w(k, **_TRUE)) / T)
        for cp in ("C", "P"):
            price = opd_math.black76_price(F, K, T, _R, iv, cp)
            out.append({
                "option_symbol": f"{_TICKER}{expiry[2:4]}{expiry[5:7]}{expiry[8:10]}{cp}{int(round(K * 1000)):08d}",
                "nbbo_bid": round(price * 0.99, 4), "nbbo_ask": round(price * 1.01, 4),
                "last_price": round(price, 4), "implied_volatility": round(iv, 5),
                "open_interest": 100, "volume": 10, "delta": 0.5, "last_tape_time": "2026-09-23T20:00:00Z"})
    return out


@pytest.fixture
def oipd_routes(provider_routes):
    exps = _expiries()
    chains = {e: _contracts_for(e) for e in exps}
    state = {"fail_page2_for": set()}

    def contracts(path, query, body):
        q = parse_qs(query)
        expiry = (q.get("expiry") or [""])[0]
        # UW pages from 0 (#255): no ``page`` is page 0, the second page is ``page=1``.
        page, limit = int((q.get("page") or ["0"])[0]), int((q.get("limit") or ["500"])[0])
        if page >= 1 and expiry in state["fail_page2_for"]:
            return 500, BOOM
        rows = chains.get(expiry, [])
        return 200, {"data": rows[page * limit: (page + 1) * limit]}

    provider_routes.route(f"/api/stock/{_TICKER}/expiry-breakdown", payload={
        "data": [{"expiry": e, "open_interest": 10000, "volume": 500, "chains": 50} for e in exps]})
    provider_routes.route_fn(f"/api/stock/{_TICKER}/option-contracts", contracts)
    provider_routes.route(f"/api/stock/{_TICKER}/ohlc/1d", payload={"data": [
        {"date": "2026-09-29", "market_time": "r", "open": _SPOT, "high": _SPOT, "low": _SPOT,
         "close": _SPOT, "volume": 1000}]})
    provider_routes.fail_page2_for = state["fail_page2_for"]
    return provider_routes


class TestOipdSecondPageFails:
    def test_a_healthy_fetch_pages_and_saves_the_chain(self, dashboard, oipd_routes):
        res = dashboard.run_job("/run/module_oipd", ticker=_TICKER)
        assert res.ok, res
        assert dashboard.table_count("oipd_chain") > 0
        pages = [q.query for q in oipd_routes.requests(f"/api/stock/{_TICKER}/option-contracts")]
        assert any("page=1" in q for q in pages), "the fixture must really have a second page"

    def test_a_failed_second_page_warns_and_saves_nothing(self, dashboard, oipd_routes):
        bad = _expiries()[1]
        oipd_routes.fail_page2_for.add(bad)
        res = dashboard.run_job("/run/module_oipd", ticker=_TICKER)
        assert res.ok, res
        html = dashboard.view("module_oipd").text
        assert bad in html and "page 2" in html and "truncated" in html
        assert "Partial chain: not saved" in html
        assert dashboard.table_count("oipd_chain") == 0

    def test_a_failed_second_page_leaves_the_stored_chain_alone(self, dashboard, oipd_routes):
        assert dashboard.run_job("/run/module_oipd", ticker=_TICKER).ok
        def snapshot():
            return (_query(dashboard, "SELECT count(*) FROM oipd_chain"),
                    _query(dashboard, "SELECT ticker, fetched_at FROM oipd_meta"))

        stored = snapshot()
        assert stored[0][0][0] > 0 and stored[1]
        oipd_routes.fail_page2_for.add(_expiries()[0])
        assert dashboard.run_job("/run/module_oipd", ticker=_TICKER).ok
        assert snapshot() == stored

    def test_every_chain_request_failing_says_the_request_failed(self, dashboard, oipd_routes):
        oipd_routes.route(f"/api/stock/{_TICKER}/option-contracts", payload=BOOM, status=500)
        res = dashboard.run_job("/run/module_oipd", ticker=_TICKER)
        assert res.ok, res
        html = dashboard.view("module_oipd").text
        assert "Unusual Whales request failed" in html and "check the ticker" not in html
