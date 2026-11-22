"""#278 Earnings Radar writer: the dashboard Fetch records its run in result history. Offline, temp stores.

Fetch only (a Refresh never records: Earnings has none, it is live-only); a history failure is a job note and never
blocks the Fetch; a Fetch that ends in a JobMessage (no events, no cards) still gets its header.
"""
from __future__ import annotations

import json
from datetime import date

import pytest

from revenuechaser.app import runners
from revenuechaser.app.jobs import JobMessage
from revenuechaser.core import ledger, rawstore
from revenuechaser.module_earnings_radar.models import TradeCard

BOARD = "module_earnings_radar"


@pytest.fixture
def run(monkeypatch, rawstore_tmp_db):
    ledger.take_notes()
    path = runners.OUTPUT_DIR / "t278" / "earnings_radar_latest.html"
    path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(runners, "EARNINGS_LATEST", path)
    monkeypatch.setattr(runners, "_load_watchlist", lambda: {"AAA"})
    monkeypatch.setattr(runners, "_freeze_run_id", lambda: "job42")
    monkeypatch.setattr("revenuechaser.module_sector_rotation.engine.rotation_quadrant_map",
                        lambda uw: {"XLK": "LEADING"})
    order = []

    def fake_export(cards, events, nrc, filename=None, filter_stats=None, provider_health=None, notice=None, run_at=None):
        order.append("board")
        runners.EARNINGS_LATEST.write_text("<html>board</html>", encoding="utf-8")

    monkeypatch.setattr("revenuechaser.module_earnings_radar.report.export_html", fake_export)
    state = {"cards": [], "stats": None, "order": order}

    class Pipe:
        def __init__(self, tickers, uw, raw_cal, etf_quadrant_map=None):
            self.tickers = tickers
            self._filter_stats = state["stats"] or {"total": len(tickers), "passed": len(state["cards"]),
                                                    "bypassed": 0, "filtered": 0, "by_reason": {}, "excluded": []}

        def run(self, use_preselect=True):
            return list(state["cards"])

    monkeypatch.setattr(runners, "EarningsPipeline", Pipe)
    state["events"] = [{"ticker": "AAA", "earnings_date": date(2026, 10, 8), "earnings_time": "AMC", "source": "UW"}]
    monkeypatch.setattr(runners, "_fetch_calendar_range", lambda uw, s, e: (list(state["events"]), {}))
    return state


class _UW:
    def __init__(self, **health):
        self._h = {"calls": 100, "failed": 0, "failures": [], "auth_error": None, "breaker_open": False,
                   "skipped_calls": 0, **health}
        self.auth_error = self._h["auth_error"]

    def health(self):
        return self._h

    def screener_batch(self, tickers):
        return {}


def _card(t="AAA"):
    return TradeCard(ticker=t, earnings_date=date(2026, 10, 8), earnings_time="AMC", final_action="WATCH_ONLY",
                     raw_packet_json="{}")


def _fetch(uw=None):
    return runners.run_earnings_range(uw or _UW(), date(2026, 10, 8), date(2026, 10, 8))


def test_the_earnings_board_has_no_refresh_path():
    from revenuechaser.app import dashboard
    assert BOARD not in dashboard._STORE_REFRESHABLE
