"""v2 step 6 (#1264): what the door reads off disk, and what it refuses to.

No HTTP here. These are the door's reading rules: which board keys exist, where an envelope file is, what a board
with no envelope yet looks like, and that the ``data`` hash the door reports is the hash of the dashboard's own
payload file — the deploy's six-equal-pairs proof, checked in CI on a written board instead of on the box.
"""
from __future__ import annotations

import gzip
import hashlib
import json

import pytest

from revenuechaser.core import reporting_common as rc
from revenuechaser.core import v2_envelope as env
from revenuechaser.v2.door import boards

PAYLOAD = {"as_of": "2026-11-20", "rows": [{"ticker": "AAPL", "score": 1.5}, {"ticker": "MSFT", "score": 0.25}]}


def _write(tmp_path, board: str = "module_relatedness", payload=PAYLOAD):
    """Write a real board artifact the way the dashboard's jobs do, and point the door's root at it."""
    html = tmp_path / f"{env.BOARDS[board]}.html"
    rc.write_board(html, "<html></html>", payload, run_id="run-1")
    return html


@pytest.fixture
def artifacts(tmp_path, monkeypatch):
    """The door's artifacts root, redirected at a scratch folder for one test."""
    monkeypatch.setattr(boards, "artifacts_dir", lambda: tmp_path)
    return tmp_path


def test_the_board_keys_are_the_envelope_contracts_boards_in_one_order():
    assert boards.board_keys() == tuple(sorted(env.BOARDS))
    assert boards.board_keys() == tuple(boards.board_keys()), "the order must not depend on a dict's insertion"


def test_the_door_names_no_artifact_stem_of_its_own(artifacts):
    """Every path the door builds comes from the contract's stem, so a board added there needs no edit here."""
    for board, stem in env.BOARDS.items():
        assert boards.envelope_path(board).name == f"{stem}{env.ENVELOPE_SUFFIX}"
        assert boards.envelope_path(board).parent == artifacts


def test_an_unknown_board_is_refused_before_the_filesystem_is_touched(artifacts):
    with pytest.raises(boards.UnknownBoard):
        boards.envelope_path("module_made_up")
    with pytest.raises(boards.UnknownBoard):
        boards.summary("module_made_up")


def test_a_known_board_with_no_envelope_is_a_missing_file_not_an_unknown_board(artifacts):
    with pytest.raises(boards.NoEnvelope):
        boards.read("module_relatedness")


def test_the_data_hash_equals_the_hash_of_the_dashboards_own_payload_file(artifacts):
    """The six-equal-pairs proof, on one board: the door's ``data`` is the payload file, byte for byte."""
    html = _write(artifacts)
    from_payload = hashlib.sha256(gzip.decompress(rc.payload_path(html).read_bytes())).hexdigest()
    assert boards.data_sha256("module_relatedness") == from_payload


def test_the_bytes_the_door_serves_are_the_bytes_on_disk(artifacts):
    _write(artifacts)
    raw = boards.stored_bytes("module_relatedness")
    assert raw == boards.envelope_path("module_relatedness").read_bytes()
    assert json.loads(gzip.decompress(raw))["data"] == PAYLOAD


def test_a_summary_carries_the_metadata_and_never_the_rows(artifacts):
    _write(artifacts)
    row = boards.summary("module_relatedness")
    assert "data" not in row and "rows" not in row
    assert row["present"] is True
    assert row["board"] == "module_relatedness"
    assert row["run_id"] == "run-1"
    assert row["data_asof"] == "2026-11-20"
    assert row["renderer"] == env.GENERIC
    assert row["private"] is False
    assert row["schema_version"] == env.ENVELOPE_SCHEMA_VERSION
    assert row["stored_bytes"] > 0 and row["data_bytes"] > 0


def test_a_board_whose_job_has_not_run_is_a_row_not_an_error(artifacts):
    _write(artifacts)
    rows = {row["board"]: row for row in boards.board_list()}
    assert set(rows) == set(env.BOARDS), "every board has a row, present or not"
    assert rows["module_relatedness"]["present"] is True
    assert rows["module_sec_13f"] == {"board": "module_sec_13f", "present": False}


def test_a_dropped_board_leaves_no_envelope_behind(artifacts):
    """``drop_board_data`` is what a Refresh calls; the door must then report the board as absent, not stale."""
    html = _write(artifacts)
    rc.drop_board_data(html)
    assert boards.summary("module_relatedness")["present"] is False


def test_the_artifacts_root_is_the_one_rc_cache_dir_and_not_a_second_spelling(monkeypatch, tmp_path):
    """The door reads ``core.config.OUTPUT_DIR``: the single place ``RC_CACHE_DIR`` is read."""
    from revenuechaser.core import config
    monkeypatch.setattr(config, "OUTPUT_DIR", tmp_path / "elsewhere")
    assert boards.artifacts_dir() == tmp_path / "elsewhere"
