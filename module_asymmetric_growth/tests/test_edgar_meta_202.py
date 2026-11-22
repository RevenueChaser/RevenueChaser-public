"""#202: a scoring failure in Asymmetric Growth must be counted and shown, not swallowed. (Its legacy
double-encoded ``edgar_financials.meta`` cases went with that store read, #642 PR 6.)"""
import logging

import pytest

from revenuechaser.module_asymmetric_growth import engine
from revenuechaser.module_asymmetric_growth.report import render_asymmetric_growth_hunter_html
from revenuechaser.module_asymmetric_growth.tests.test_score_ticker import _fin, _tech


def _quote():
    return {"regularMarketPrice": 100.0, "fiftyTwoWeekHigh": 105.0, "fiftyDayAverage": 90.0,
            "averageDailyVolume10Day": 160.0, "averageDailyVolume3Month": 100.0}


def test_a_programming_error_is_not_swallowed(monkeypatch):
    def boom(*a, **k):
        raise AttributeError("'str' object has no attribute 'get'")
    monkeypatch.setattr(engine, "_cached_financials", boom)
    with pytest.raises(AttributeError):
        engine.enrich_and_score("TEST", {"quote": _quote()}, no_fetch=True, spine={})


def test_a_provider_error_still_just_skips_the_ticker(monkeypatch):
    def down(*a, **k):
        raise ConnectionError("offline")
    monkeypatch.setattr(engine, "_cached_financials", down)
    assert engine.enrich_and_score("TEST", {"quote": _quote()}, no_fetch=True, spine={}) is None






def test_board_shows_the_dropped_count_escaped():
    base = {"asof": "2026-10-02T00:00:00", "universe_total": 1, "cards": [], "thresholds": engine.THRESHOLDS,
            "summary": {"scanned": 0, "score_errors": 3,
                        "score_error_types": {"<img src=x>": 3}}}
    page = render_asymmetric_growth_hunter_html(base)
    assert "3 ticker(s) could not be scored" in page
    assert "<img src=x>" not in page and "&lt;img src=x&gt;" in page
    clean = render_asymmetric_growth_hunter_html({**base, "summary": {"scanned": 0}})
    assert "could not be scored" not in clean
