"""Earnings and LEAPS (C26, #383; #746): the Earnings pipeline does not import the old LEAPS engine.

The card's LEAPS fields and drawer row are gone (C1, 16 Nov 2026): no label could ever reach them.
"""
from revenuechaser.module_earnings_radar import pipeline as pl


def test_the_pipeline_no_longer_imports_the_old_leaps_engine():
    import inspect
    assert "module_leaps" not in inspect.getsource(pl)
