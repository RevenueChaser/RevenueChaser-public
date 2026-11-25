"""Relatedness off-peak boundary and CLI (no HTTP).

The $ cap test went with the board's own profile writer (#1520): the board calls no model now, so there is
nothing here for a cap to limit. The off-peak gate and the CLI are still the board's own.
"""
from __future__ import annotations

import pytest

from revenuechaser.core.providers import deepseek
from revenuechaser.module_relatedness import engine


@pytest.fixture(autouse=True)
def _deepseek_board(monkeypatch):
    """These CLI runs are DeepSeek's: the board's writer is DeepSeek here (#360 made EVREN the default)."""
    from revenuechaser.core.providers import deepseek as _ds
    from revenuechaser.module_relatedness import settings as rel_settings
    monkeypatch.setattr(rel_settings, "writer", lambda: ("deepseek", _ds.MODEL))


def test_cli_status(rawstore_tmp_db, capsys):
    from revenuechaser.module_relatedness import __main__ as cli
    assert cli.main(["--status"]) == 0
    assert "DeepSeek" in capsys.readouterr().out


def test_cli_status_announces_peak_override(rawstore_tmp_db, capsys, monkeypatch):
    from revenuechaser.core import offpeak
    from revenuechaser.module_relatedness import __main__ as cli
    monkeypatch.setattr(offpeak, "is_off_peak", lambda now=None: False)
    monkeypatch.setattr(deepseek, "peak_override_active", lambda now=None: True)
    cli.main(["--status"])
    assert "Peak override ON" in capsys.readouterr().out


def test_cli_status_is_quiet_without_override(rawstore_tmp_db, capsys, monkeypatch):
    from revenuechaser.core import offpeak
    from revenuechaser.module_relatedness import __main__ as cli
    monkeypatch.setattr(offpeak, "is_off_peak", lambda now=None: False)
    cli.main(["--status"])  # the autouse fixture points the gate at an empty temp file
    assert "Peak override" not in capsys.readouterr().out


def test_cli_lock_skip_is_non_zero_but_a_peak_stop_is_green(monkeypatch, capsys):
    """#130/#118 C13 + C-F1: a skipped (locked) run exits 1; a peak/pending run exits 0."""
    from revenuechaser.module_relatedness import __main__ as cli

    def locked(**k):
        raise engine.AlreadyRunning("Another Relatedness run is already in progress.")

    monkeypatch.setattr(cli.engine, "run", locked)
    assert cli.main(["--run"]) == 1
    assert "skipped" in capsys.readouterr().out

    monkeypatch.setattr(cli.engine, "run", lambda **k: {
        "n": 4, "pending": 6, "next_off_peak": "2026-09-21 01:00",
        "stopped_reason": "peak"})
    assert cli.main(["--run"]) == 0
    out = capsys.readouterr().out
    assert '"pending": 6' in out and "next_off_peak" in out
