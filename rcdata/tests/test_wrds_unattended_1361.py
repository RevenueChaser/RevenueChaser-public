"""#1361: no WRDS dataset is ``attended`` any more, so the hourly builder runs them on their cadence.

The switch ``RC_WRDS_UNATTENDED`` and ``base.wrds_attended()`` are gone (avo, 22 Nov 2026: that login asks for no
Duo push here, so the parameter had nothing to guard). What these tests keep holding is everything the removal
must **not** have broken: the one-retry-a-day rule for a failed WRDS run, which is keyed on the provider and not
on ``attended``; the worker login's connect timeout; and the fact that ``delisted/serving`` still declares
``attended`` for its own reason (#1219), so the CLI runner still has something to drain.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest

from RevenueChaser.core import calendar
from RevenueChaser.rcdata import ops
from RevenueChaser.rcdata.build import DATASETS, base, due
from RevenueChaser.rcdata.build.spine import wrds

WRDS = sorted(n for n in DATASETS if n.startswith("wrds/"))


@pytest.fixture
def midday_ny(monkeypatch):
    """The clock pinned to 12:00 New York, through the one clock seam (``core.calendar._now``).

    ``due.EARLIEST_NY_HOUR`` holds ``wrds/prices`` until 05:00 New York, before the failed-run rules are even
    read, so a test of those rules that runs on the machine's own clock passes or fails by the hour CI started:
    run 44696572824 began at 02:48 New York and the two tests below failed on ``main`` too.
    """
    fixed = datetime(2026, 11, 19, 17, 0, tzinfo=timezone.utc)      # 12:00 New York, a Thursday
    monkeypatch.setattr(calendar, "_now", lambda: fixed)
    return fixed


def test_the_switch_and_its_helper_are_gone():
    # The whole point of #1361: nothing reads an env var to decide this any more.
    assert not hasattr(base, "wrds_attended")
    assert not hasattr(base, "WRDS_UNATTENDED_ENV")


def test_no_wrds_dataset_is_attended():
    assert len(WRDS) >= 5
    assert not any(base.attended(DATASETS[n]) for n in WRDS)
    assert not set(WRDS) & base.attended_names()


def test_the_attended_gate_no_longer_holds_them():
    # ``is_due`` may still hold a WRDS dataset for another reason (the New York hour, a failed run, a pause);
    # what it must never say again is that a person has to be at a terminal.
    assert all(due.is_due(DATASETS[n])[1] != due.ATTENDED_WHY for n in WRDS)


def test_delisted_is_still_attended_so_the_cli_has_work():
    # #1219 uses ``attended`` as "never due on its own", which #1361 deliberately leaves alone. If this ever
    # becomes the empty set, the ``attended`` CLI command has nothing left to drain and should go with it.
    assert base.attended_names() == frozenset({"delisted/serving"})
    assert due.is_due(DATASETS["delisted/serving"])[1] == due.ATTENDED_WHY


def test_worker_login_has_a_connect_timeout(monkeypatch):
    monkeypatch.delenv("PGCONNECT_TIMEOUT", raising=False)
    assert wrds.worker_env()["PGCONNECT_TIMEOUT"] == str(wrds.CONNECT_TIMEOUT_S) == "120"
    monkeypatch.setenv("PGCONNECT_TIMEOUT", "30")
    assert wrds.worker_env()["PGCONNECT_TIMEOUT"] == "30"


def test_an_empty_inherited_timeout_still_gets_the_default(monkeypatch):
    monkeypatch.setenv("PGCONNECT_TIMEOUT", "")
    assert wrds.worker_env()["PGCONNECT_TIMEOUT"] == "120"


@pytest.mark.parametrize("name", WRDS)
def test_a_failed_run_waits_for_a_person_instead_of_retrying_hourly(midday_ny, name):
    # Review must-fix 1: a failed WRDS run must not be due again every hour (one login each). The rule is keyed
    # on ``"wrds" in ds.providers`` (``due.py``), not on ``attended``, which is why #1361 does not touch it.
    ops.record_check(name, "changed", source_as_of="2026-10-01", checked_on="2026-10-01")
    ops.record_check(name, "failed", note="WRDS login failed")
    is_due, why = due.is_due(DATASETS[name])
    assert is_due is False and why == due.WRDS_FAILED_WHY
    ops.record_check(name, "changed", source_as_of="2026-10-01", checked_on="2026-10-01")
    assert due.is_due(DATASETS[name])[1] != due.WRDS_FAILED_WHY       # a person's successful run clears it


@pytest.mark.parametrize("name", WRDS)
def test_a_failure_of_an_earlier_day_is_retried_once_that_day(midday_ny, name):
    # #1115: a transient serving-swap refusal on 17 Nov 2026 held ``wrds/prices`` for ever, so a daily dataset wrote
    # no check row at all on 18 and 19 Nov and the served bars stopped at 16 Nov. The hold is the day's, not always.
    ops.record_check(name, "changed", source_as_of="2026-10-01", checked_on="2026-10-01")
    ops.record_check(name, "failed", note="SwapRefused: market_cap_daily shrinks", checked_on="2026-10-02")
    is_due, why = due.is_due(DATASETS[name])
    assert is_due is True and why != due.WRDS_FAILED_WHY
    ops.record_check(name, "failed", note="SwapRefused: market_cap_daily shrinks")   # today: held for the rest of it
    assert due.is_due(DATASETS[name]) == (False, due.WRDS_FAILED_WHY)


def test_the_attended_cli_still_drains_what_is_left(monkeypatch, capsys):
    # The trap #1361 had to avoid: the old guard returned "nothing to do" whenever the WRDS switch was on, before
    # the queue was drained, so ``delisted/serving`` requests would have waited for ever. It must now refuse only
    # for the want of a terminal, and say nothing-to-do only when no dataset declares ``attended`` at all.
    from RevenueChaser.rcdata.build import __main__ as cli
    monkeypatch.setattr(cli, "at_a_terminal", lambda: False)
    assert cli.main(["attended"]) == 3
    assert "needs a terminal" in capsys.readouterr().err
    monkeypatch.setattr(base, "attended_names", lambda: frozenset())
    assert cli.main(["attended"]) == 0
    assert "no dataset declares attended" in capsys.readouterr().err
