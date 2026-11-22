"""Follow-up review of the Co-movement board (Fable, round 2, 17 Nov 2026), claude-coordinator ``reviews/2026-11-17_1622_*``.

N1: an unjudged group named a Fetch "at this window and horizon", but a Fetch only ever judges 1-day groups vs the S&P
500 at the default, 6-month and 1-year windows; the text now says so. N3: a stale name counts with the missing bars on
a Fetch and a Refresh alike, even when it listed inside the window.
"""
from __future__ import annotations

import shutil

import numpy as np
import pandas as pd
import pytest

from revenuechaser.module_comovement import config, engine
from revenuechaser.module_comovement.tests import test_recompute_parity as parity
from revenuechaser.module_comovement.tests.test_comovement import (_report_cluster, _report_payload,
                                                                    _run_board_js)


def test_a_stale_name_listed_inside_the_window_is_missing_bars_on_a_refresh(rawstore_tmp_db, monkeypatch):
    """The full read (a Fetch) already said "missing bars"; the windowed read (a Refresh) said "listed recently"."""
    monkeypatch.setattr(engine, "WINDOWED_REFRESH", True)
    ret = parity._market()
    col = pd.Series(np.random.default_rng(3).normal(0, 0.01, len(ret)), index=ret.index)
    col.iloc[:250] = np.nan                                    # listed inside a 252-session window
    col.iloc[-(config.STALE_SESSIONS + 1):] = np.nan           # and stale
    ret["NEWLATE"] = col
    tickers = parity._seed(ret)
    p = engine.run(no_fetch=True, tickers=tickers, window=252)
    assert "NEWLATE" in p["dropped"]
    assert p["funnel"]["listed_recently"] == 1                  # SHORT only
    assert p["funnel"]["missing_bars"] == len(p["dropped"]) - 1


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_unjudged_text_names_the_views_a_fetch_judges(tmp_path):
    from revenuechaser.module_comovement import report

    payload = _report_payload(clusters={"20": [
        _report_cluster("1", mean=0.72, tickers=("AAA", "BBB"), significant=None, baseline_r=None)]})
    grid = _run_board_js(report.render_comovement_dashboard(payload), tmp_path)["grid"]
    assert "6-month and 1-year windows" in grid and "at this window and horizon" not in grid


def test_the_multi_day_null_draws_from_residual_daily_returns():
    """N10 (Grok, round 2): at h > 1 the null shuffled raw daily returns while the groups it judges are residuals."""
    rng = np.random.default_rng(10)
    idx = pd.bdate_range("2025-01-02", periods=80)
    m = rng.normal(0, 0.01, 80)
    logp = {"SPY": np.cumsum(m)}
    for i in range(6):
        logp[f"N{i}"] = np.cumsum(1.2 * m + rng.normal(0, 0.004, 80))
    prices = pd.DataFrame({k: 100 * np.exp(v) for k, v in logp.items()}, index=idx)
    h = 5
    names = [f"N{i}" for i in range(6)]
    ret = np.log(prices[names] / prices[names].shift(h)).iloc[-60:]
    daily = engine._daily_under(prices, ret, h, "SPY", 5.0)
    spy = np.log(prices["SPY"] / prices["SPY"].shift(1)).loc[daily.index]
    assert daily.shape == (len(ret) + h - 1, len(names))
    assert all(abs(np.corrcoef(daily[c], spy)[0, 1]) < 0.2 for c in names)
