"""Swing board review of 17 Nov 2026 (claude-coordinator reviews/2026-11-17_1432_revenuechaser_swing-board-review.md).

F2: a Fetch with no SPY baseline says so on the board instead of silently scoring RS as unknown.
F5: ``OPERATING_ONLY`` changes who is scanned (so every percentile): a saved value versions the ledger rows, and the
default board keeps its hash.
"""
from __future__ import annotations

import pandas as pd
import pytest

from RevenueChaser.core import screen_common as sc
from RevenueChaser.core.tests import screen_parity as scn
from RevenueChaser.module_swing_potential import pipeline
from RevenueChaser.module_swing_potential.report import render_swing_dashboard


@pytest.fixture
def scenario(rawstore_tmp_db, monkeypatch):
    scn.seed()
    scn.patch(monkeypatch)


def test_a_fetch_without_an_spy_baseline_says_so(scenario, monkeypatch):
    def no_spy(now=None):
        empty = pd.DataFrame()
        empty.attrs["fetch_failed"] = True
        return empty
    monkeypatch.setattr(sc, "load_spy", no_spy)
    payload = pipeline.run_scan()
    assert payload["summary"]["spy_missing"] is True
    assert payload["passing"]["weinstein"] == 0                     # RS vs SPY unknown: 5 of 5 cannot pass
    assert "SPY has no bar of the latest session" in render_swing_dashboard(payload)


def test_a_fetch_with_an_spy_baseline_says_nothing(scenario):
    payload = pipeline.run_scan()
    assert payload["summary"]["spy_missing"] is False
    assert "SPY has no bar of the latest session" not in render_swing_dashboard(payload)
