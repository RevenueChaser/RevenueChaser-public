"""#118 PR C — the Relatedness job's messages and exit codes, and the one current-theme-run reader.

C13/P5 the CLI's and the dashboard runner's messages, C24 one reader of the current theme run. Offline, no call.

What this file held until #1520: the cost cap (C14/N4), the stop event (P6), the unparseable cached reply (P2),
the prompt-version cache miss (C22) and the EVREN pool cap. Every one of them was a rule of the board's own
profile writer, which is gone; the SEC reading service carries them and ``rcdata/tests/test_sec_reads.py`` tests
them. The CLI's own handling of a ``stopped_reason`` stays, because the payload keys stay.
"""
from __future__ import annotations

import pytest

from revenuechaser.core import rawstore
from revenuechaser.module_relatedness import engine


@pytest.fixture(autouse=True)
def _deepseek_board(monkeypatch):
    """These CLI runs name DeepSeek as the board's writer (#360 made EVREN the default). It reaches no model:
    since #1520 the writer is a label on the payload, not a call this board makes."""
    from revenuechaser.core.providers import deepseek as _ds
    from revenuechaser.module_relatedness import settings as rel_settings
    monkeypatch.setattr(rel_settings, "writer", lambda: ("deepseek", _ds.MODEL))




# ── C13 + P5 + C-F1: job messages and exit codes ─────────────────────────────
def test_cli_run_exits_zero_and_reports_a_peak_stop(rawstore_tmp_db, monkeypatch, capsys):
    import json as _json
    from revenuechaser.module_relatedness import __main__ as cli

    monkeypatch.setattr(engine, "run", lambda **k: {
        "n": 4, "pending": 6, "next_off_peak": "2026-09-21 01:00",
        "stopped_reason": "peak"})
    assert cli.main(["--run"]) == 0          # a peak stop is the normal state: green (C-F1)
    out = _json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["done"] == 4 and out["pending"] == 6
    assert out["next_off_peak"] == "2026-09-21 01:00"
    assert out["stopped_reason"] == "peak"


def test_cli_run_exits_zero_at_the_cost_cap_and_when_work_is_pending(rawstore_tmp_db, monkeypatch, capsys):
    """The per-run cost cap and names with no text leave pending work, but not a failure (C-F1)."""
    import json as _json
    from revenuechaser.module_relatedness import __main__ as cli

    monkeypatch.setattr(engine, "run", lambda **k: {
        "n": 4, "pending": 6, "next_off_peak": None})   # cap stop: no stopped_reason
    assert cli.main(["--run"]) == 0
    out = _json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["done"] == 4 and out["pending"] == 6


def test_cli_run_exits_one_for_an_auth_stop(rawstore_tmp_db, monkeypatch, capsys):
    import json as _json
    from revenuechaser.module_relatedness import __main__ as cli

    monkeypatch.setattr(engine, "run", lambda **k: {
        "n": 0, "pending": 8, "next_off_peak": None,
        "stopped_reason": "auth", "error": "DeepSeek rejected the API key (HTTP 401)"})
    assert cli.main(["--run"]) == 1          # a bad credential the next run cannot fix (C-F1)
    out = _json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["stopped_reason"] == "auth" and "401" in out["error"]


def test_cli_run_exits_one_for_a_transient_stop(rawstore_tmp_db, monkeypatch, capsys):
    import json as _json
    from revenuechaser.module_relatedness import __main__ as cli

    monkeypatch.setattr(engine, "run", lambda **k: {
        "n": 3, "pending": 5, "next_off_peak": None,
        "stopped_reason": "transient", "error": "DeepSeek HTTP 503"})
    assert cli.main(["--run"]) == 1          # repeated transient failures stop the run (P6, C-F1)
    out = _json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["stopped_reason"] == "transient"


def test_cli_run_clean_exits_zero(rawstore_tmp_db, monkeypatch, capsys):
    import json as _json
    from revenuechaser.module_relatedness import __main__ as cli

    monkeypatch.setattr(engine, "run", lambda **k: {
        "n": 5, "pending": 0, "next_off_peak": None})
    assert cli.main(["--run"]) == 0
    out = _json.loads(capsys.readouterr().out.strip().splitlines()[-1])
    assert out["n"] == 5 and out["pending"] == 0


def test_dashboard_runner_raises_jobmessage_for_stopped_or_pending_work(monkeypatch):
    from revenuechaser.app import jobs, runners

    monkeypatch.setattr(engine, "run", lambda **k: {
        "n": 4, "pending": 6, "next_off_peak": "2026-09-21 01:00",
        "stopped_reason": "peak", "companies": [], "peers": {}})
    with pytest.raises(jobs.JobMessage) as exc:
        runners.run_relatedness(None, no_fetch=False)
    msg = str(exc.value)
    assert "4" in msg and "6" in msg and "2026-09-21 01:00" in msg


def test_dashboard_runner_refresh_with_pending_work_does_not_raise(monkeypatch):
    """C-F6: the JobMessage is for a Fetch; a Refresh with pending work returns the board silently."""
    from revenuechaser.app import jobs, runners

    monkeypatch.setattr(engine, "run", lambda **k: {
        "n": 4, "pending": 6, "next_off_peak": None,
        "stopped_reason": "peak", "companies": [], "peers": {}})
    path = runners.run_relatedness(None, no_fetch=True)   # must not raise jobs.JobMessage
    assert path == runners.RELATEDNESS_LATEST


# ── C24: one current-theme-run reader ────────────────────────────────────────
def _seed_theme_run(run_id, is_current, coarse_label, medium_label, ticker):
    rawstore.write_rows("theme_runs", [{
        "id": run_id, "created_at": "2026-01-01", "k_fine": 1, "k_medium": 1,
        "k_coarse": 1, "jaccard": 1.0, "is_current": is_current}])
    rawstore.write_rows("relatedness_themes", [
        {"theme_id": f"{run_id}:c0", "level": "coarse", "parent_id": "",
         "label": coarse_label, "size": 5},
        {"theme_id": f"{run_id}:m0", "level": "medium", "parent_id": f"{run_id}:c0",
         "label": medium_label, "size": 20},
    ])
    rawstore.write_rows("ticker_themes", [
        {"ticker": ticker, "theme_id": f"{run_id}:c0", "theme": coarse_label,
         "level": "coarse", "theme_run_id": run_id},
        {"ticker": ticker, "theme_id": f"{run_id}:m0", "theme": medium_label,
         "level": "medium", "theme_run_id": run_id},
    ])


def test_one_current_theme_run_reader_and_one_coarse_label(rawstore_tmp_db):
    from revenuechaser.core import universe
    from revenuechaser.module_relatedness import themes
    from revenuechaser.module_sector_rotation import theme_focus

    _seed_theme_run("old", 0, "Old Coarse", "Old Child", "OLD")
    _seed_theme_run("cur", 1, "Financials (2)", "Regional Banks", "JPM")

    assert universe.current_theme_run() == "cur"     # the one public reader
    assert themes.current_run_id() == "cur"

    cat = universe.theme_catalog()
    assert cat["cur:c0"]["label"] == "Regional Banks"    # sector-named -> largest child
    assert "Old Coarse" not in {t["label"] for t in cat.values()}

    levels = engine._theme_levels()
    assert levels["JPM"]["coarse"] == "Regional Banks"   # label from theme_catalog
    assert "OLD" not in levels                            # only the current run

    catalog = theme_focus.coarse_theme_catalog()
    assert "Regional Banks" in catalog
    assert "Financials (2)" not in catalog
