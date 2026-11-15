"""Opus review M1 (PR 6): "Loading universe…" asks the universe the boards read, not the old table.

``_universe_loading`` and Asymmetric Growth's no-card Refresh probed ``equity_universe`` directly. On the spine that
table is empty and stays empty (its refresh is retired), so opening a board while its own Fetch ran showed "Loading
universe… the board fills in when the universe job finishes" over a loaded spine, and an AG Refresh before the
first Fetch said "no stored universe". Both now ask ``universe.has_universe()``.
"""
from __future__ import annotations

import pytest

from RevenueChaser.app import dashboard, jobs
from RevenueChaser.core import rawstore, universe
from RevenueChaser.module_asymmetric_growth import engine
from RevenueChaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401 - market roots per test
from RevenueChaser.rcdata.tests.test_spine_security import built, run_all  # noqa: F401 - the 10 names


def test_without_a_spine_a_board_fetch_says_loading(monkeypatch):
    monkeypatch.setattr(jobs, "has_active", lambda modules: True)
    assert universe.has_universe() is False
    assert dashboard._universe_loading("module_swing_potential") is True


