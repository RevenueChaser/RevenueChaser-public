"""A scheduled run leaves a ``job_runs`` row and stamps its writes with that row's id (#129 A1).

``run_task`` runs a registry command as a subprocess, so the dashboard's job registry (``app/jobs.py``) never sees
it. ``run_task`` therefore upserts the run's own row (``trigger = 'scheduled'``, ``registry_name``) when the command
starts and when it ends, and hands the id to the child as ``RC_RUN_ID`` (``RC_RUN_SOURCE`` = the registry name).
In the child, ``ledger.new_run_id`` and the store's change capture use that id, so the rows the job writes join to
the row. Only an entry that writes tables records a row: the backup leaves the store as it copied it.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from RevenueChaser.core import automations as A
from RevenueChaser.core import ledger, rawstore

AMS = ZoneInfo("Europe/Amsterdam")


@pytest.fixture(autouse=True)
def _cache(tmp_path, monkeypatch):
    monkeypatch.setattr(A.config, "OUTPUT_DIR", tmp_path)
    monkeypatch.delenv(rawstore.RUN_ID_ENV, raising=False)
    monkeypatch.delenv(rawstore.RUN_SOURCE_ENV, raising=False)
    A.set_scheduler(None)
    yield
    A.set_scheduler(None)


_SHOW_ENV = "import os; print('env', os.environ.get('RC_RUN_ID'), os.environ.get('RC_RUN_SOURCE'))"


def _entry(name="RC-Writer", code=_SHOW_ENV, tables=("equity_universe",), **kw):
    return A.AutomationEntry(name=name, label="w", args=("-c", code), time="23:00", description="d",
                             tables_written=tables, **kw)


def _only(monkeypatch, *entries):
    monkeypatch.setattr(A, "_BY_NAME", {e.name: e for e in entries})
















def test_the_shipped_backup_records_no_row():
    assert A.entry("RC-Backup-Weekly").tables_written == ()




# --- the child's side ------------------------------------------------------------------------------------------

def test_outside_a_scheduled_run_ids_stay_fresh():
    assert rawstore.task_run() is None
    assert ledger.new_run_id() != ledger.new_run_id()
    assert rawstore._change_writer()[1] is None




def test_a_dashboard_job_id_still_wins_over_the_task(monkeypatch):
    monkeypatch.setenv(rawstore.RUN_ID_ENV, "abc123def456")
    monkeypatch.setattr(rawstore, "_CHANGE_WRITER", lambda: ("job000000001", "universe"))
    assert rawstore._change_writer() == ("job000000001", "universe")
