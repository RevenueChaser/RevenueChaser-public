"""The 16 Nov plan, steps 1 and 2 (Value Chain half): V2, V4, N6, #391.

On the SEC layer a Fetch downloads nothing, so its Pending came from the old download path's ``miss:`` keys and its
texts named controls and limits that are gone: Settings' "Fetch 10-K sync", "about 50 companies", "source: 10-K/20-F"
on a 40-F's link.
"""
from __future__ import annotations

from revenuechaser.core import universe
from revenuechaser.module_value_chain import engine, report


def test_on_the_layer_pending_ignores_the_old_miss_keys(rawstore_tmp_db, monkeypatch):
    monkeypatch.setattr(universe, "classification_universe", lambda **k: ["MSFT", "ORCL", "XYZ"])
    monkeypatch.setattr(engine, "stored_misses", lambda: {"ORCL": {"reason": "form_40f"}})
    monkeypatch.setattr(engine, "_stored_ciks", lambda: {"MSFT": "1", "ORCL": "2"})
    monkeypatch.setattr(engine, "_reads_layer", lambda: True)
    payload = engine._board_payload([], [], "x", None)
    assert (payload["pending"], payload["misses"], payload["no_cik"]) == (2, 0, 1)
    # Off the layer a recorded miss is still what the download path learned, and stays out of Pending.
    monkeypatch.setattr(engine, "_reads_layer", lambda: False)
    payload = engine._board_payload([], [], "x", None)
    assert (payload["pending"], payload["misses"], payload["no_cik"]) == (1, 1, 1)


def _html(**extra):
    return report.render_value_chain_dashboard({"filings": [], "edges": [], "universe_total": 0, "pending": 0,
                                                **extra})


def test_the_help_and_the_evidence_footer_say_what_the_board_reads_now():
    html = _html(corpus="layer")
    for gone in ("10-K sync", "about 50", "source: 10-K/20-F", "10-K Item 1"):
        assert gone not in html, gone
    assert "downloads nothing itself" in html
    assert "(10-K, 20-F or 40-F)" in html
    assert "downloads nothing itself" not in _html(corpus="chain_filings")

