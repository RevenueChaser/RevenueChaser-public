"""No empty-over-good writes (PL2 / N1).

A provider failure used to arrive as ``[]`` / ``{}`` and be saved over the last
good stored rows, and the job still ended "done". The runners now keep the
stored rows and end with a ``JobMessage`` that names what was kept and why.
(The holdings sync's cases went with the holdings job, #642 PR 5.)
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.app import runners
from revenuechaser.app.jobs import JobMessage

class TestMoneyFlow:
    def _patch_paths(self, tmp_path, monkeypatch):
        out = tmp_path / "cache"
        latest = out / "sector_rotation" / "sector_rotation_latest.json"
        monkeypatch.setattr(runners, "OUTPUT_DIR", out)
        monkeypatch.setattr(runners, "MONEY_FLOW_LATEST", latest)
        return latest

    def test_empty_result_keeps_the_stored_leaderboard(self, tmp_path, monkeypatch):
        import revenuechaser.module_sector_rotation.money_flow as mf
        latest = self._patch_paths(tmp_path, monkeypatch)
        latest.parent.mkdir(parents=True)
        good = {"inflows": [{"ticker": "UP"}], "outflows": [{"ticker": "DN"}],
                "generated_at": "2026-09-01T00:00:00", "as_of": "2026-08-29"}
        latest.write_text(json.dumps(good), encoding="utf-8")
        monkeypatch.setattr(mf, "compute_money_flow", lambda **k: {
            "inflows": [], "outflows": [], "generated_at": None, "as_of": None})
        with pytest.raises(JobMessage, match=r"(?i)kept"):
            runners.run_money_flow_latest(uw=None)
        assert json.loads(latest.read_text(encoding="utf-8")) == good

    def test_non_empty_result_is_written(self, tmp_path, monkeypatch):
        import revenuechaser.module_sector_rotation.money_flow as mf
        latest = self._patch_paths(tmp_path, monkeypatch)
        monkeypatch.setattr(mf, "compute_money_flow", lambda **k: {
            "inflows": [{"ticker": "NEW"}], "outflows": [], "generated_at": None, "as_of": "2026-09-29"})
        runners.run_money_flow_latest(uw=None)
        assert json.loads(latest.read_text(encoding="utf-8"))["inflows"] == [{"ticker": "NEW"}]


