"""#212: the builder refuses to start while there is no fresh verified backup, and a fetch-only run is not gated.

The gate is read once, before the writer turn, because no wait makes a stale copy fresh. A fetch-only run writes
raw files and Parquet partitions and opens no serving file, so it keeps running: the next build reads them again.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from RevenueChaser.core import config
from RevenueChaser.rcdata import backup, ops
from RevenueChaser.rcdata.build import __main__ as cli


@pytest.fixture
def stale(tmp_path, monkeypatch):
    """A backup folder whose newest verified copy is far past the limit."""
    monkeypatch.setattr(config, "RAW_STORE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv(backup.GATE_ENV, raising=False)
    out = backup.step_dir(backup.STEP_DUCKDB)
    out.mkdir(parents=True, exist_ok=True)
    old = datetime.now(timezone.utc) - timedelta(days=backup.STALE_DAYS + 3)
    (out / backup.MANIFEST_NAME).write_text(json.dumps({"files": {}, "last_ok": old.isoformat()}), encoding="utf-8")


def test_a_build_does_not_start_and_says_why(stale, capsys, monkeypatch):
    def no_turn(*a, **kw):
        raise AssertionError("the turn must not be taken while the backup is stale")
    monkeypatch.setattr(cli, "_take_the_turn", no_turn)
    assert cli.main(["run", "--once"]) == 3
    said = capsys.readouterr().err
    assert "builder not started" in said and "days old" in said
    assert ops.rows("build_requests") == []           # nothing queued, nothing written


def test_a_fetch_only_run_is_not_gated(stale, monkeypatch):
    """It opens no serving file, so a stale copy does not hold it; its own lock still does."""
    def no_gate(*a, **kw):
        raise AssertionError("a fetch-only run must not read the backup gate")
    monkeypatch.setattr(cli.base, "backup_problem", no_gate)
    monkeypatch.setattr(cli, "_take_fetch_locks", lambda stack, locks, wait: (False, "another fetch holds it"))
    assert cli.main(["run", "--dataset", "market_series", "--no-duckdb", "--wait", "0"]) == 3
