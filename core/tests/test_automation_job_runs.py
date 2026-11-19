"""A scheduled run leaves a run-log row and stamps its writes with that row's id (#129 A1, #136).

``run_task`` runs a registry command as a subprocess, so the dashboard's job registry (``app/jobs.py``) never sees
it. It therefore records the run itself and hands the id to the child as ``RC_RUN_ID`` (``RC_RUN_SOURCE`` = the
registry name). In the child, ``ledger.new_run_id`` and the store's change capture use that id, so the rows the job
writes join to the run.

The row used to be ``job_runs`` in the old raw.duckdb and went with it (#860). Since #136 it is a row of
``ops.job_runs2``: ``job`` is the registry name, ``trigger`` is ``schedule``, and ``counts`` is the result object
the step printed last. Every run that reaches its command gets one, whether or not it writes tables — the row is
the record of the run, not of a store write.
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
















def test_the_shipped_backup_records_no_table_write():
    assert A.entry("RC-Backup-Weekly").tables_written == ()


# --- the run-log row (#136) ------------------------------------------------------------------------------------

_PRINTS_RESULT = ("import json; print('working'); "
                  "print(json.dumps({'rows': 93714, 'written': 93714}))")


def test_a_scheduled_run_records_its_row_with_the_counts_it_printed(monkeypatch, tmp_path):
    """The gap this closes: a scheduled step printed its result and nothing recorded it, so the Runs tab could not
    say how much a run did (#136)."""
    from RevenueChaser.rcdata import ops
    e = _entry(code=_PRINTS_RESULT)
    _only(monkeypatch, e)
    assert A.run_task(e.name, cwd=tmp_path) == 0
    [run] = ops.job_runs()
    assert run["job"] == "RC-Writer" and run["trigger"] == "schedule" and run["status"] == "done"
    assert run["counts"] == {"rows": 93714, "written": 93714}
    assert run["error"] is None and run["finished_at"] is not None
    # The builder's own readers do not see it: it has no dataset.
    assert ops.last_builder_run() is None


def test_a_failed_scheduled_run_records_its_exit_code(monkeypatch, tmp_path):
    from RevenueChaser.rcdata import ops
    e = _entry(code="import sys; print('{\"rows\": 2}'); sys.exit(2)")
    _only(monkeypatch, e)
    assert A.run_task(e.name, cwd=tmp_path) == 2
    [run] = ops.job_runs()
    assert run["status"] == "failed" and run["error"] == "exit 2" and run["counts"] == {"rows": 2}


def test_a_step_that_prints_no_object_records_no_counts(monkeypatch, tmp_path):
    from RevenueChaser.rcdata import ops
    e = _entry(code="print('done, 4 rows'); print('[1, 2]')")
    _only(monkeypatch, e)
    assert A.run_task(e.name, cwd=tmp_path) == 0
    [run] = ops.job_runs()
    assert run["status"] == "done" and run["counts"] is None


def test_a_switched_off_pass_records_no_row(monkeypatch, tmp_path):
    """No command ran, so there is no run to log."""
    from RevenueChaser.rcdata import ops
    e = _entry(code=_PRINTS_RESULT)
    _only(monkeypatch, e)
    monkeypatch.setattr(A, "_switched_off", lambda name: "skipped: the fetch switch is off (avo at 12:00)")
    assert A.run_task(e.name, cwd=tmp_path) == A.RESULT_OK
    assert ops.job_runs() == []


def test_an_ops_store_that_refuses_the_row_does_not_stop_the_task(monkeypatch, tmp_path):
    """Bookkeeping is best-effort (#282): the task runs and exits as it would have."""
    from RevenueChaser.rcdata import ops
    e = _entry(code=_PRINTS_RESULT)
    _only(monkeypatch, e)

    def refuse(*a, **k):
        raise RuntimeError("ops store is busy")

    monkeypatch.setattr(ops, "start_run", refuse)
    assert A.run_task(e.name, cwd=tmp_path) == 0
    assert "working" in e.log_path.read_text(encoding="utf-8")


def test_the_last_printed_object_is_the_result():
    assert A.counts_from_output('{"rows": 1}\nnoise\n{"rows": 2}\n') == {"rows": 2}
    assert A.counts_from_output("Traceback...\n{not json}\n") is None
    assert A.counts_from_output("{}") is None                     # an empty object is no count at all
    assert A.counts_from_output("") is None
    assert A.counts_from_output('  {"a": 1}  ') == {"a": 1}




# --- the child's side ------------------------------------------------------------------------------------------

def test_outside_a_scheduled_run_ids_stay_fresh():
    assert rawstore.task_run() is None
    assert ledger.new_run_id() != ledger.new_run_id()
    assert rawstore._change_writer()[1] is None




def test_a_dashboard_job_id_still_wins_over_the_task(monkeypatch):
    monkeypatch.setenv(rawstore.RUN_ID_ENV, "abc123def456")
    monkeypatch.setattr(rawstore, "_CHANGE_WRITER", lambda: ("job000000001", "universe"))
    assert rawstore._change_writer() == ("job000000001", "universe")
