"""The index lists job and route (#302, D24): long lane, needs UW, the sp600 first fill is a named parameter."""
from __future__ import annotations

import pytest

from RevenueChaser.app import dashboard, runners
from RevenueChaser.app.jobs import JobMessage
from RevenueChaser.core.tests.panel_client import panel_test_client


def _client():
    return panel_test_client(dashboard.app)


@pytest.fixture
def submitted(monkeypatch):
    import RevenueChaser.app.dashboard as d

    class _UW:
        def verify(self):
            return (True, None)

        def close(self):
            pass

    monkeypatch.setattr(d, "_uw", lambda: _UW())
    captured: list[tuple] = []
    monkeypatch.setattr(d.jobs, "submit", lambda module, params: captured.append((module, params)) or "stubjob")
    return captured


def test_registered_long_lane_and_requires_uw():
    from RevenueChaser.app import jobs
    assert jobs._LANE["index_lists"] == "long"
    assert jobs._REQUIRES_UW["index_lists"] is True










def _result(statuses: dict, locked: bool = False) -> dict:
    return {"run_id": "r1", "locked": locked, "slugs": {
        s: {"status": st, "members": 500, "floor": 400, "appended": 0} for s, st in statuses.items()}}






