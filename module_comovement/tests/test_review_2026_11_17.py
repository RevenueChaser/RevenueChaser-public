"""The Co-movement review of 17 Nov 2026, checked on live data (claude-coordinator ``reviews/2026-11-17_1320_*``).

F6: a name with no bar in the last ``config.STALE_SESSIONS + 1`` sessions is not clustered; it is counted with the
missing bars. Live, 37 of 5,391 names were 3+ sessions behind and still clustered on a window that ended early.
F7: flat printers are judged on the run's window, not the whole stored history: a name that sat still long before
the window and trades today is clustered (``returns.flat_print_names`` already said "the window actually used").
F1/B: a group with no noise baseline says "not evaluated" instead of reading like a judged one.
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


def _members(p: dict) -> set[str]:
    return {m["ticker"] for groups in p["clusters"].values() for c in groups for m in c["members"]}


def _market_with(extra: dict) -> list[str]:
    ret = parity._market()
    for name, fn in extra.items():
        col = pd.Series(np.random.default_rng(len(name)).normal(0, 0.01, len(ret)), index=ret.index)
        ret[name] = fn(col)
    return parity._seed(ret)


def _behind(k: int):
    def cut(col):
        col.iloc[-k:] = np.nan          # a NaN return is no bar that day (parity._seed)
        return col
    return cut


@pytest.mark.parametrize("windowed", [True, False])
def test_a_name_sessions_behind_is_counted_not_clustered(rawstore_tmp_db, monkeypatch, windowed):
    monkeypatch.setattr(engine, "WINDOWED_REFRESH", windowed)
    k = config.STALE_SESSIONS
    tickers = _market_with({"LATE": _behind(k + 1), "EDGE": _behind(k)})
    p = engine.run(no_fetch=True, tickers=tickers, window=252)
    assert "LATE" not in _members(p) and "LATE" in p["dropped"]
    assert "EDGE" in _members(p)                                    # k sessions behind is still current
    assert p["funnel"]["missing_bars"] == len(p["dropped"]) - p["funnel"]["listed_recently"]


@pytest.mark.parametrize("windowed", [True, False])
def test_a_flat_stretch_before_the_window_does_not_drop_the_name(rawstore_tmp_db, monkeypatch, windowed):
    monkeypatch.setattr(engine, "WINDOWED_REFRESH", windowed)

    def old_halt(col):
        col.iloc[40:52] = 0.0           # 12 unchanged closes, long before a 252-session window
        return col

    def new_halt(col):
        col.iloc[-16:-4] = 0.0
        return col

    tickers = _market_with({"OLDHALT": old_halt, "NEWHALT": new_halt})
    p = engine.run(no_fetch=True, tickers=tickers, window=252)
    assert "NEWHALT" in p["flat_prints"] and "OLDHALT" not in p["flat_prints"]
    assert "OLDHALT" in _members(p)


@pytest.mark.skipif(shutil.which("node") is None, reason="node not on PATH")
def test_an_unjudged_group_says_not_evaluated(tmp_path):
    from revenuechaser.module_comovement import report

    payload = _report_payload(clusters={"20": [
        _report_cluster("1", mean=0.72, tickers=("AAA", "BBB"), significant=None, baseline_r=None)]})
    grid = _run_board_js(report.render_comovement_dashboard(payload), tmp_path)["grid"]
    assert "vs noise: not evaluated" in grid
