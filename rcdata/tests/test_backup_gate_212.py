"""#212: no live write without a fresh verified backup.

The record is the weekly backup's own manifest (``<RAW_STORE_BACKUP_DIR>/weekly-v2/duckdb/.manifest.json``), whose
``last_ok`` is stamped only by a run in which every copy verified. ``backup.stale_problem`` turns it into the one
sentence the builder and the Settings route both refuse with; the gate is silent where no backup folder is
configured (a developer's machine, CI) and where it is switched off.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from revenuechaser.core import config
from revenuechaser.rcdata import backup
from revenuechaser.rcdata.build import base

NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "RAW_STORE_BACKUP_DIR", str(tmp_path / "backups"))
    monkeypatch.delenv(backup.GATE_ENV, raising=False)
    return tmp_path / "backups"


def _manifest(data: dict, step: str = backup.STEP_DUCKDB) -> None:
    out = backup.step_dir(step)
    out.mkdir(parents=True, exist_ok=True)
    (out / backup.MANIFEST_NAME).write_text(json.dumps(data), encoding="utf-8")


def _verified(days_ago: float) -> None:
    _manifest({"files": {}, "last_ok": (NOW - timedelta(days=days_ago)).isoformat()})


def test_no_backup_folder_configured_holds_nothing(monkeypatch):
    """CI and a developer's machine have no backup folder: the gate must not stop every build there.

    The switch is deleted first, so "not configured" is the only reason the answer can be None. Without that it
    was the suite's own ``RC_BUILD_BACKUP_GATE=0`` that passed this test, and a mutant that drops the
    "not configured" escape survived it (mutation round 2).
    """
    monkeypatch.delenv(backup.GATE_ENV, raising=False)
    monkeypatch.setattr(config, "RAW_STORE_BACKUP_DIR", "")
    assert backup.gate_on() is True                      # the switch is not what makes this None
    assert backup.stale_problem(NOW) is None


def test_a_fresh_verified_copy_lets_the_write_through(folder):
    _verified(1)
    assert backup.stale_problem(NOW) is None


def test_a_copy_exactly_at_the_limit_still_lets_the_write_through(folder):
    _verified(backup.STALE_DAYS)
    assert backup.stale_problem(NOW) is None


def test_a_copy_past_the_limit_refuses_and_names_its_age_and_day(folder):
    _verified(backup.STALE_DAYS + 1)
    problem = backup.stale_problem(NOW)
    assert problem is not None
    assert f"{backup.STALE_DAYS + 1} days old" in problem
    assert (NOW - timedelta(days=backup.STALE_DAYS + 1)).date().isoformat() in problem
    assert f"the limit is {backup.STALE_DAYS}" in problem


def test_no_manifest_at_all_refuses(folder):
    problem = backup.stale_problem(NOW)
    assert problem is not None and "no verified backup" in problem
    assert str(backup.step_dir(backup.STEP_DUCKDB) / backup.MANIFEST_NAME) in problem


@pytest.mark.parametrize("data", [
    {"files": {}, "last_run": NOW.isoformat(), "last_error": "prices: did not verify"},  # ran, nothing verified
    {"files": {}, "last_ok": "not a time"},
    {"files": {}, "last_ok": 20261120},
    {},
])
def test_a_manifest_with_no_good_run_refuses(folder, data):
    """A manifest that records a failed run, or a stamp that cannot be read, is "no backup" and never a fresh one."""
    _manifest(data)
    problem = backup.stale_problem(NOW)
    assert problem is not None and "no verified backup" in problem


def test_an_unreadable_manifest_refuses(folder):
    out = backup.step_dir(backup.STEP_DUCKDB)
    out.mkdir(parents=True, exist_ok=True)
    (out / backup.MANIFEST_NAME).write_text("{half writ", encoding="utf-8")
    assert backup.stale_problem(NOW) is not None


def test_a_stamp_without_a_zone_is_read_as_utc(folder):
    _manifest({"files": {}, "last_ok": (NOW - timedelta(days=1)).replace(tzinfo=None).isoformat()})
    assert backup.last_verified(backup.STEP_DUCKDB) == NOW - timedelta(days=1)
    assert backup.stale_problem(NOW) is None


def test_the_switch_turns_the_gate_off_and_only_the_value_zero_does(folder, monkeypatch):
    monkeypatch.setenv(backup.GATE_ENV, "0")
    assert backup.gate_on() is False and backup.stale_problem(NOW) is None
    monkeypatch.setenv(backup.GATE_ENV, "1")
    assert backup.gate_on() is True and backup.stale_problem(NOW) is not None


def test_the_builders_gate_reads_the_same_record(folder):
    _verified(backup.STALE_DAYS + 2)
    assert base.backup_problem(NOW) == backup.stale_problem(NOW)
    _verified(0)
    assert base.backup_problem(NOW) is None


def test_the_limit_is_the_red_line_the_settings_card_draws():
    """One number, so the card cannot say "ok" while the builder refuses (``module_settings/newdata.py``)."""
    from revenuechaser.module_settings import newdata
    assert backup.STALE_DAYS == newdata.BACKUP_ALERT_DAYS
