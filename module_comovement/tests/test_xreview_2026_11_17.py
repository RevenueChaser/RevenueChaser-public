"""The Grok xReview of the Co-movement board, 17 Nov 2026 (``/mnt/project-files/xreview-comovement.md``).

MAJOR: ``residualize`` fitted each name's market beta on unclipped returns, so one ``|log r| > 1`` print (live: 311
such days, WOK's collapse, INHD's missed reverse split) set the beta that every residual of the name then carried; the
winsorising after it could not undo that. The fit now reads clipped returns; the residuals stay unclipped.
MINOR: a clustered name ``filter_fields`` does not know stays on its card (a reload already stubbed it), and a corrupt
stored null is logged instead of silently leaving every group unjudged.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from RevenueChaser.core import universe as universe_mod
from RevenueChaser.module_comovement import engine
from RevenueChaser.module_comovement import returns as returns_mod
from RevenueChaser.module_comovement.tests import test_recompute_parity as parity


def test_one_extreme_print_does_not_set_the_beta():
    rng = np.random.default_rng(17)
    idx = pd.bdate_range("2025-01-02", periods=252)
    m = pd.Series(rng.normal(0, 0.01, 252), index=idx)
    m.iloc[100] = 0.03
    y = 1.0 * m + rng.normal(0, 0.005, 252)
    y.iloc[100] += 3.0                                   # a missed reverse split on a +3 % market day
    resid = returns_mod.residualize(y.to_frame("X"), m, winsor_k=5.0)["X"]
    rest = resid.drop(idx[100])
    assert abs(np.corrcoef(rest, m.drop(idx[100]))[0, 1]) < 0.1    # the market is out of the other 251 days
    assert resid.iloc[100] > 2.9                                     # the print itself is kept, unclipped
    raw = returns_mod.residualize(y.to_frame("X"), m)["X"].drop(idx[100])
    assert np.corrcoef(raw, m.drop(idx[100]))[0, 1] < -0.5           # plain OLS: the print bent the beta


def test_a_name_filter_fields_does_not_know_stays_on_its_card(rawstore_tmp_db, monkeypatch):
    tickers = parity._seed(parity._market())
    real = universe_mod.filter_fields
    monkeypatch.setattr(universe_mod, "filter_fields",
                        lambda names, *a, **k: {t: v for t, v in real(names, *a, **k).items() if t != "B0N00"})
    p = engine.run(no_fetch=True, tickers=tickers, window=252)
    for groups in p["clusters"].values():
        for c in groups:
            assert len(c["members"]) == c["n"]
    assert any(m["ticker"] == "B0N00" for c in p["clusters"]["5"] for m in c["members"])


def test_a_corrupt_stored_null_is_logged(monkeypatch, caplog):
    monkeypatch.setattr(engine.rawstore, "query", lambda *a, **k: [{"null_json": "[1, 2]"}])
    with caplog.at_level(logging.WARNING, logger=engine.logger.name):
        assert engine._persisted_null("abc") == {}
    assert "not valid JSON" in caplog.text
