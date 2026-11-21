"""scripts/drop_board_artifacts.py: the start-up cut of the rendered board pages (#266 part 2).

Two things must hold, and they pull in opposite directions. Every board the dashboard can re-derive from the
store has to lose its page, or a deploy keeps serving the pre-deploy one. And a board that only a Fetch can
rebuild must keep it, or the cut spends the provider calls the issue chose this option to avoid.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from RevenueChaser.app import dashboard, runners
from RevenueChaser.scripts import drop_board_artifacts as mod


@pytest.fixture
def cache(tmp_path, monkeypatch):
    """Point every board artifact at ``tmp_path``, so the real cache root of this process is untouched."""
    for name in dir(runners):
        value = getattr(runners, name)
        if name.endswith("_LATEST") and isinstance(value, Path) and value.suffix == ".html":
            monkeypatch.setattr(runners, name, tmp_path / value.name)
    return tmp_path


def _write(path: Path, text: str = "x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _write_board(html: Path) -> list[Path]:
    return [_write(p) for p in mod.artifacts_of(html)]


def test_earnings_radar_is_kept_because_only_a_fetch_rebuilds_it():
    """Its page is the one artifact in the set that a plain load cannot replace without a provider call.

    ``view()`` has no store-only branch for it (it is absent from ``_STORE_REFRESHABLE``), so a dropped page
    serves the "no data yet" state until someone presses Fetch, which calls Unusual Whales.
    """
    assert "module_earnings_radar" not in mod.droppable_boards()
    assert "module_earnings_radar" in mod.kept_boards()


def test_every_droppable_board_has_a_store_only_rebuild_in_view():
    """The set is exactly the boards ``view()`` rebuilds with no network when their artifact is missing."""
    special = {"module_sec_13f", "module_sector_rotation"}      # named in view()'s own `not f.exists()` branch
    for board in mod.droppable_boards():
        assert board in dashboard._MODEL_ONLY_RENDERERS or board in special, board


def test_a_board_that_keeps_its_page_is_never_in_both_sets():
    assert not set(mod.droppable_boards()) & set(mod.kept_boards())


def test_apply_drops_a_droppable_board_and_leaves_everything_else(cache, capsys):
    boards = mod.droppable_boards()
    assert "module_relatedness" in boards                       # a store-only board, as the fixture assumes
    victims = [p for html in boards.values() for p in _write_board(html)]
    kept = [p for html in mod.kept_boards().values() for p in _write_board(html)]
    bystanders = [
        _write(cache / "relatedness_20261121T101500.html"),     # a timestamped archive
        _write(cache / "sec_13f" / "0001067983-26-000011.zip"), # a downloaded filing
        _write(cache / "uw_interaction" / "uw_interaction_latest.json"),  # a provider answer, not a re-render
        _write(cache / "storage_picture" / "storage_picture_latest.json"),
        _write(cache / "spx_gamma" / "spx_gamma_20261120.png"),
        _write(cache / "logs" / "dashboard.log"),
    ]

    assert mod.main(["--apply"]) == 0

    assert [p for p in victims if p.exists()] == []
    assert all(p.exists() for p in kept), [p.name for p in kept if not p.exists()]
    assert all(p.exists() for p in bystanders), [p.name for p in bystanders if not p.exists()]
    out = capsys.readouterr().out
    assert "module_earnings_radar" in out                       # the report names what it kept and why
    assert f"dropped {len(victims)}" in out


def test_report_only_removes_nothing(cache, capsys):
    written = [p for html in mod.droppable_boards().values() for p in _write_board(html)]

    assert mod.main([]) == 0

    assert all(p.exists() for p in written)
    assert "report only" in capsys.readouterr().out


def test_nothing_on_disk_is_not_an_error(cache, capsys):
    assert mod.main(["--apply"]) == 0
    assert "nothing to drop" in capsys.readouterr().out
