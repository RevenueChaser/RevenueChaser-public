"""The forecast-ledger freeze hook in the Earnings Fetch (#580).

``run_earnings_range`` freezes as its last step, after the board file is written, with the cards the pipeline
returned and the running job's id. The Earnings Radar has no Refresh, so every run is a Fetch. A refused freeze is a
``core.ledger`` note, never a ``JobMessage``; a freeze error propagates, so the job shows it.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from revenuechaser.app import jobs, runners
from revenuechaser.core import ledger

DAY = date(2026, 10, 16)
POST_CLOSE = datetime(2026, 10, 14, 21, 0, tzinfo=timezone.utc)
CARDS = [type("C", (), {"ticker": "AAA"})()]


class FakePipeline:
    input_sources: dict = {}

    def __init__(self, *a, **k):
        self.screener_result = None
        self._filter_stats = {"total": 1, "filtered": 0, "passed": 1, "bypassed": 0, "by_reason": {}}
        self.input_sources = {}

    def run(self, *a, **k):
        return list(CARDS)


@pytest.fixture
def order(monkeypatch):
    """Stub the calendar read, the pipeline and the renderer; record the order of every step."""
    calls: list[str] = []
    from revenuechaser.module_earnings_radar import report as er_report

    monkeypatch.setattr(runners, "_fetch_calendar_range",
                        lambda uw, start, end: (calls.append("calendar"), ([{"ticker": "AAA"}], {}))[1])
    monkeypatch.setattr(runners, "_load_watchlist", lambda: set())
    monkeypatch.setattr(runners, "EarningsPipeline", FakePipeline)
    monkeypatch.setattr(runners, "_compute_nrc_results", lambda cards: {})
    monkeypatch.setattr(runners, "_uw_health", lambda uw: None)
    monkeypatch.setattr(runners, "_provider_gap_text", lambda uw: None)
    monkeypatch.setattr(er_report, "export_html", lambda *a, **k: calls.append("render"))
    monkeypatch.setattr(er_report, "screener_problem", lambda r: None)
    ledger.take_notes()
    return calls


@pytest.fixture
def freezer(monkeypatch, order):
    """Replace the freeze with a spy that records its call and arguments."""
    from revenuechaser.module_earnings_radar import freeze as er_freeze
    seen: dict = {}

    def spy(cards, **kw):
        order.append("freeze")
        seen.update({"cards": cards, **kw})
        return ledger.Outcome("earnings_radar", "Earnings Radar", frozen=len(cards), forecast_date=DAY)

    monkeypatch.setattr(er_freeze, "freeze_cards", spy)
    return seen


def test_a_fetch_freezes_last_with_the_cards(order, freezer):
    runners.run_earnings_range(None, DAY, DAY)
    assert order == ["calendar", "render", "freeze"]
    assert [c.ticker for c in freezer["cards"]] == ["AAA"]
    assert len(freezer["run_id"]) == 12


def test_the_run_id_is_the_running_jobs_id(order, freezer, monkeypatch):
    monkeypatch.setattr(jobs, "_ensure_worker", lambda: None)
    monkeypatch.setattr(jobs, "_ensure_long_worker", lambda: None)
    jobs.register("t_earnings_run_id", lambda uw, **p: runners.run_earnings_range(uw, DAY, DAY), [],
                  requires_uw=False)
    jid = jobs.submit("t_earnings_run_id")
    jobs.execute(jid)
    assert jobs.get(jid)["status"] == "done"
    assert freezer["run_id"] == jid


def test_a_freeze_exception_propagates_and_fails_the_job(order, monkeypatch):
    from revenuechaser.module_earnings_radar import freeze as er_freeze

    def boom(cards, **kw):
        raise RuntimeError("ledger write failed")

    monkeypatch.setattr(er_freeze, "freeze_cards", boom)
    with pytest.raises(RuntimeError, match="ledger write failed"):
        runners.run_earnings_range(None, DAY, DAY)
