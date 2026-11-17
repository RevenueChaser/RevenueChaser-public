"""M-ROT-2 (#374, A5 + #283): the Rotation RRG reads its closes from D01, one cross-section for live and backfill.

D-M3 "weekly, both" (avo 2026-10-15): every path resamples the stored daily closes to ISO weeks, completed weeks only
since A1 (avo 17 Nov 2026), and keeps the 1/4/12-week lookbacks. ``as_of_date`` is that session (rule B),
never the machine's ``date.today()``; a run that is not a complete session never replaces a complete stored one, and
an ETF with too little D01 history is a warning, not a partial run. Offline: a temp store, the calendar clock pinned,
a UW fake that records every call.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from RevenueChaser.app import runners
from RevenueChaser.app.jobs import JobMessage
from RevenueChaser.core import calendar, ledger, rawstore
from RevenueChaser.module_sector_rotation import engine, report as rot_report, store, universe
from RevenueChaser.module_sector_rotation.tests.bars_seed import ny as _at, seed as _seed, sessions as _sessions

UNIVERSE = {
    "SPY": {"name": "S&P 500", "group": "benchmark"},
    "XLK": {"name": "Technology", "group": "sector"},
    "XLF": {"name": "Financial Services", "group": "sector"},
    "XLE": {"name": "Energy", "group": "sector"},
    "SMH": {"name": "Semiconductors", "group": "theme"},
    "IBB": {"name": "Biotech", "group": "theme"},
}


class _UW:
    """Records every client call; RRG closes must not come from here."""

    def __init__(self):
        self.calls = []

    def etf_ohlc(self, ticker, days=0, candle_size="1d"):
        self.calls.append(("etf_ohlc", ticker, candle_size))
        return []

    def etf_ohlc_result(self, ticker, days=0, candle_size="1d"):
        self.calls.append(("etf_ohlc", ticker, candle_size))
        from RevenueChaser.core.providers.result import ProviderResult
        return ProviderResult("ok", [], None, "")

    def health(self):
        return {"calls": 0, "failed": 0, "auth_error": None, "failures": []}




def _stored(day: date) -> list[dict]:
    return (store.load_snapshot(day) or {}).get("etfs") or []


def _strip(rows: list[dict]) -> list[dict]:
    return sorted(({k: v for k, v in r.items() if k not in ("generated_at", "source")} for r in rows),
                  key=lambda r: r["ticker"])


# ── one cross-section, live and backfill ─────────────────────────────────────────────────────────────────────────────



def test_the_cross_section_uses_weekly_lookbacks_on_completed_iso_weeks():
    """A1 (avo 17 Nov 2026): a partial week is not on the map yet; lookbacks are 1/4/12 weeks, not 5/21/63 sessions."""
    days = _sessions(date(2025, 6, 2), date(2026, 10, 7))
    spy = [(d, 100.0) for d in days]
    rising = [(d, 100.0 + i) for i, d in enumerate(days)]
    weeks = engine.weekly_closes(rising, date(2026, 10, 7))
    friday = date(2026, 10, 2)
    assert weeks[-1] == dict(rising)[friday]                   # Wednesday's week is not complete: last Friday closes
    assert weeks[-2] == dict(rising)[friday - timedelta(days=7)]
    assert len(weeks) == len({d.isocalendar()[:2] for d, _ in rising}) - 1
    snaps = engine.cross_section({"XLK": weeks}, engine.weekly_closes(spy, date(2026, 10, 7)), date(2026, 10, 7))
    (s,) = snaps
    assert s.as_of_date == date(2026, 10, 7)
    assert s.rs_1w == round((weeks[-1] / weeks[-2] - 1) * 100, 2)
    assert s.rs_3m == round((weeks[-1] / weeks[-13] - 1) * 100, 2)


# ── the session date (#283) ──────────────────────────────────────────────────────────────────────────────────────────











# ── no UW candles ────────────────────────────────────────────────────────────────────────────────────────────────────



# ── depth ────────────────────────────────────────────────────────────────────────────────────────────────────────────







# ── backfill ─────────────────────────────────────────────────────────────────────────────────────────────────────────





# ── the Earnings dependency (rotation_quadrant_map) ──────────────────────────────────────────────────────────────────



