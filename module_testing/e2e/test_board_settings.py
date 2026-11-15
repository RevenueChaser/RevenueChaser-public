"""Settings / Data health board, end to end.

The board is store-only: it renders on first load with no Fetch, and Refresh
must re-derive it from ``raw.duckdb`` / ``edgar.duckdb`` with zero network. The
temp store is seeded through ``rawstore`` (the value-chain pattern) so the
inventory has a known hole: two NULL market caps, one of which (MU) the
standalone ``/run/universe-stats`` job can fill and one of which (NOCAP) it must
never invent a value for.
"""
from __future__ import annotations

from RevenueChaser.rcdata.tests import universe_store
import json
import pathlib
import time
from datetime import datetime, timezone

import httpx
import pytest

_APP = "module_settings"
_ARTIFACT = "settings_latest.html"


def _hole(n: int) -> str:
    """The exact universe hole cell: count + its ``null market cap`` label."""
    return f'warnv">{n}</span><span class="hlabel">null market cap'






class TestView:
    def test_the_tab_is_in_the_shell(self, dashboard):
        r = dashboard.get("/")
        assert r.status_code == 200
        assert "Settings" in r.text


class TestRefreshIsOfflineAndFaithful:

    def test_refresh_rebuilds_a_deleted_artifact(self, dashboard, rendered, clear_cache):
        clear_cache()
        assert not dashboard.artifact(_ARTIFACT).exists()
        r = dashboard.view(_APP, refresh=True)
        assert r.status_code == 200
        assert "Settings" in r.text
        # Serving 200 is not enough: Refresh must re-derive and re-write the
        # artifact. Without this, a refresh that answered from memory (or from a
        # stale handle) would still look green while leaving no file on disk.
        assert dashboard.artifact(_ARTIFACT).exists()

    def test_refresh_makes_no_network_calls(self, dashboard, rendered, provider_routes,
                                            clear_cache):
        clear_cache()
        before_provider = provider_routes.request_count
        before_yf = dashboard.yf_calls()
        r = dashboard.view(_APP, refresh=True)
        assert r.status_code == 200
        assert provider_routes.request_count == before_provider, (
            "refresh reached the network: "
            f"{[q.path for q in provider_routes.requests()[before_provider:]]}")
        assert dashboard.yf_calls() == before_yf, (
            "refresh reached yfinance: "
            f"{dashboard.yf_calls()[len(before_yf):]}")

    def test_refresh_survives_a_restart(self, dashboard, rendered, clear_cache):
        clear_cache()
        dashboard.restart()
        r = dashboard.view(_APP, refresh=True)
        assert r.status_code == 200
        assert "Settings" in r.text




@pytest.fixture
def served_spine(dashboard):
    """A one-row ``spine.duckdb`` in the dashboard's own market dir: the lookup reads served files only.

    ``seeded_settings`` fills the old store, which this lookup never opens, so without this a known name
    would answer 404 and the offline check would prove nothing about a real answer.
    """
    import duckdb
    path = pathlib.Path(dashboard.env["RC_MARKET_DIR"]) / "spine.duckdb"
    path.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(path))
    try:
        con.execute("CREATE TABLE IF NOT EXISTS security (ticker VARCHAR, name VARCHAR, cik VARCHAR, "
                    "sector VARCHAR, industry VARCHAR, tier VARCHAR)")
        # ``seeded_settings`` may already have created this table with the spine's whole schema and put AAPL in
        # it (``universe_store``). So: name the columns, and replace the row rather than add a second one.
        con.execute("DELETE FROM security WHERE ticker = 'AAPL'")
        con.execute("INSERT INTO security (ticker, name, cik, sector, industry, tier) "
                    "VALUES ('AAPL', 'Apple Inc.', '0000320193', 'Technology', 'Hardware', 'A')")
    finally:
        con.close()
    return path




class TestEmptyStore:
    def test_a_board_with_no_data_renders_an_empty_state(self, dashboard):
        r = dashboard.view(_APP)
        assert r.status_code == 200
        assert "Settings" in r.text


def _verdicts(html: str, bodies: list) -> list:
    """Run the board's own ``settingsJobVerdict`` (under node) on real API bodies."""
    import json
    import re
    import shutil
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    m = re.search(r"function settingsJobVerdict\(.*?\n}\n", html, re.S)
    assert m, "the served Settings board has no settingsJobVerdict"
    script = (m.group(0) + "\nvar b = " + json.dumps(bodies)
              + ";\nconsole.log(JSON.stringify(b.map(settingsJobVerdict)));\n")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])




# ── Board inputs: the Settings card must tell the same story as the board ────
_STEP_LEGACY = {"scanned": "scanned_total", "below_floor": "below_floor",
                "no_market_cap": "no_market_cap",
                # R4 (#87): the security-type rows, then the note (shown, never counted)
                "funds_etfs": "funds_etfs", "spacs": "spacs",
                "other_securities": "other_securities", "unknown_type": "unknown_type",
                "no_prices": "no_prices",
                "listed_recently": "listed_recently", "missing_bars": "missing_bars",
                "flat": "flat",
                "clustered": "clustered"}


def _card_rows(html: str) -> list[tuple[str, str, int]]:
    """The Co-movement card's funnel rows: ``(kind, label, count)``.

    ``kind`` is ``"note"`` for a note row (a ⚠ marker, a Settings link, a positive
    count) and ``"step"`` for every counted row (drops are shown as ``−N``).
    """
    import html as _html
    import re

    m = re.search(r'<div class="bcard" id="board-module_comovement">(.*?)</div></div>'
                  r'(?=<div class="bcard"|\s*</div>|\s*<script)', html, re.S)
    assert m, "the Settings board has no Co-movement card"
    rows = []
    for cls, inner in re.findall(r'<div class="(frow2[^"]*)">(.*?)</div>', m.group(1), re.S):
        label = re.match(r"<span>([^<]*)", inner).group(1)
        num = re.search(r'<span class="num">[−]?([\d,]+)</span>', inner).group(1)
        kind = "note" if "note" in cls.split() else "step"
        rows.append((kind, _html.unescape(label.replace("⚠", "")).strip(),
                     int(num.replace(",", ""))))
    return rows


def _card_steps(html: str) -> dict[str, int]:
    """Counted step label -> count shown on the Co-movement card."""
    return {label: n for kind, label, n in _card_rows(html) if kind == "step"}


def _card_notes(html: str) -> dict[str, int]:
    """Note label -> count shown on the Co-movement card."""
    return {label: n for kind, label, n in _card_rows(html) if kind == "note"}


_FUND = "FUNDX"


class TestBoardInputs:
    def _seed_and_fetch(self, dashboard):
        import numpy as np
        import RevenueChaser.core.rawstore as rawstore
        from RevenueChaser.module_testing.e2e import test_board_comovement as cm

        ret = cm._returns()
        tickers = list(ret.columns)
        universe_store.replace([{
            "ticker": t, "market_cap": 1.0e10, "sector": "Technology", "price": 10.0,
            "name": t + " Inc", "industry": cm._INDUSTRY.get(t, ""), "quote": {"symbol": t},
        } for t in tickers + [_FUND]])
        # Identity R4 (#87): a closed-end fund at the floor (the type step is non-zero)
        # and one operating name with no master row (the unknown-type note is non-zero).
        now = time.time()
        rows = []
        for frame in (ret, cm._benchmarks(ret.index)):
            for t in frame.columns:
                price = 100 * np.exp(frame[t].cumsum())
                for ts, p in price.items():
                    rows.append({"ticker": t, "ts": ts.isoformat(), "open": p,
                                 "high": p, "low": p, "close": float(p),
                                 "volume": 1.0, "cached_at": now})
        from RevenueChaser.module_comovement.tests.prices_bars import write_bars
        write_bars(rows)
        result = dashboard.run_job("/run/module_comovement")
        assert result.ok, f"comovement fetch failed: {result}\n{dashboard.logs()}"





_PANEL = {"X-RC-Panel": "automations"}


