"""#145 (27-1) in the Asymmetric Growth engine: the universe load honours ``no_fetch``.

``fetch_universe_stats(no_fetch=True)`` is the store-only read behind a Refresh and the plain-load self-heal.
It returns the stored universe or an empty result, and never calls the Yahoo screener, whatever ``refresh`` says.
"""
from __future__ import annotations

import pytest

from revenuechaser.rcdata.tests import universe_store
from revenuechaser.core import rawstore
from revenuechaser.module_asymmetric_growth import engine


@pytest.fixture
def screener(monkeypatch):
    """Records every screener call; a call is a failure for a store-only load."""
    calls: list[int] = []
    import yfinance
    monkeypatch.setattr(yfinance, "screen", lambda *a, **k: calls.append(1) or {"quotes": [], "total": 0})
    monkeypatch.setattr("time.sleep", lambda s: None)
    return calls












def test_the_hunter_reports_an_unloaded_store_on_a_refresh(rawstore_tmp_db, screener):
    result = engine.run_asymmetric_growth_hunter(None, no_fetch=True)
    assert screener == []
    assert result["cards"] == [] and result["universe_total"] == 0
    assert result["no_data_reason"] == "no_universe_stored"
    assert "No stored universe yet" in result["no_data_message"]






def test_the_empty_board_shows_the_scans_message_not_click_refresh():
    from revenuechaser.module_asymmetric_growth.report import render_asymmetric_growth_hunter_html
    from revenuechaser.core.scan_quality import no_data_message
    msg = no_data_message("no_universe_stored")
    html = render_asymmetric_growth_hunter_html({
        "asof": "2026-10-03T00:00:00", "universe_total": 0, "summary": {}, "cards": [], "thresholds": engine.THRESHOLDS,
        "no_data_reason": "no_universe_stored", "no_data_message": msg})
    assert "No stored universe yet" in html
    assert "Click Refresh to retry" not in html


def test_an_unscored_but_stored_board_has_a_fallback_message():
    from revenuechaser.module_asymmetric_growth.report import render_asymmetric_growth_hunter_html
    html = render_asymmetric_growth_hunter_html({
        "asof": "2026-10-03T00:00:00", "universe_total": 3, "summary": {}, "cards": [], "thresholds": engine.THRESHOLDS})
    assert "No companies could be scored from the stored data" in html
