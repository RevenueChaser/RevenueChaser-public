"""v2 step 3 (#1241, epic #1238): ``write_board`` writes the v2 envelope beside the K10 payload.

The envelope is the door's contract (`core/v2_envelope.py`):
``{schema_version, board, run_id, data_asof, built_at, private, renderer, layout, data}``, with ``data`` the
payload exactly as the old page already gets it. The proof of done for the step is a hash: the envelope's
``data``, serialised the way the payload file is serialised, is byte for byte the payload file's content. Nothing
about the old dashboard moves: the payload file keeps its name, its bytes and its gzip settings, and no route
changes.
"""
from __future__ import annotations

import gzip
import hashlib
import json

from revenuechaser.core import reporting_common as rc
from revenuechaser.core import v2_envelope as env

PAYLOAD = {"rows": [{"ticker": "AAA", "name": "Ä & <b>"}], "n": 1, "data_as_of": "2026-11-20"}


def _read(path):
    return json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))


def test_the_envelope_is_written_next_to_the_payload_with_the_contract_keys_in_order(tmp_path):
    html = tmp_path / "relatedness_latest.html"
    rc.write_board(html, "<html>x</html>", PAYLOAD, run_id="abc123")
    ep = env.envelope_path(html)
    assert ep == tmp_path / "relatedness_latest.v2.json.gz"
    got = _read(ep)
    assert list(got) == ["schema_version", "board", "run_id", "data_asof", "built_at",
                         "private", "renderer", "layout", "data"]
    assert got["schema_version"] == env.ENVELOPE_SCHEMA_VERSION
    assert got["board"] == "module_relatedness"      # the dashboard's module key, not the file stem
    assert got["run_id"] == "abc123"
    assert got["data_asof"] == "2026-11-20"
    assert got["private"] is False and got["renderer"] == "generic" and got["layout"] is None
    assert got["data"] == PAYLOAD


def test_the_envelopes_data_hash_equals_the_payload_files_hash(tmp_path):
    """The step's proof of done, asserted in the suite as well as on the box."""
    html = tmp_path / "sec_13f_latest.html"
    rc.write_board(html, "", PAYLOAD, run_id="r1")
    payload_bytes = gzip.decompress(rc.payload_path(html).read_bytes())
    data_bytes = env.data_bytes(_read(env.envelope_path(html)))
    assert hashlib.sha256(data_bytes).hexdigest() == hashlib.sha256(payload_bytes).hexdigest()


def test_the_payload_file_keeps_its_own_bytes(tmp_path):
    """The old page reads the payload file; writing an envelope may not touch what it gets."""
    a, b = tmp_path / "a_latest.html", tmp_path / "b_latest.html"
    rc.write_board(a, "", PAYLOAD, run_id="r1")
    rc.write_board(b, "", PAYLOAD, run_id="r2")
    assert rc.payload_path(a).read_bytes() == rc.payload_path(b).read_bytes()
    assert env.envelope_path(a).exists() and env.envelope_path(b).exists()


def test_write_board_without_a_payload_drops_a_stale_envelope(tmp_path):
    html = tmp_path / "x_latest.html"
    rc.write_board(html, "<html>1</html>", PAYLOAD)
    rc.write_board(html, "<html>2</html>")
    assert not rc.payload_path(html).exists()
    assert not env.envelope_path(html).exists()


def test_drop_board_data_removes_both_files(tmp_path):
    html = tmp_path / "x_latest.html"
    rc.write_board(html, "<html>1</html>", PAYLOAD)
    rc.drop_board_data(html)
    assert not rc.payload_path(html).exists()
    assert not env.envelope_path(html).exists()
    rc.drop_board_data(html)                      # missing files are not an error


def test_the_run_id_comes_from_the_store_writer_when_the_caller_names_none(tmp_path, monkeypatch):
    """So the envelope joins to its ``job_runs`` row, like every row a job writes (rawstore.writer_run_id)."""
    from revenuechaser.core import rawstore
    monkeypatch.setattr(rawstore, "writer_run_id", lambda: "job-77")
    html = tmp_path / "comovement_latest.html"
    rc.write_board(html, "", PAYLOAD)
    assert _read(env.envelope_path(html))["run_id"] == "job-77"


def test_private_and_bespoke_are_carried_through(tmp_path):
    html = tmp_path / "x_latest.html"
    rc.write_board(html, "", {"rows": []}, run_id="r", private=True, renderer=env.BESPOKE)
    got = _read(env.envelope_path(html))
    assert got["private"] is True and got["renderer"] == env.BESPOKE


def test_data_asof_is_read_by_the_documented_key_probe():
    assert env.data_asof({"data_as_of": "A", "as_of": "B", "generated_at": "C"}) == "A"
    assert env.data_asof({"as_of": "B", "generated_at": "C"}) == "B"
    assert env.data_asof({"generated_at": "C"}) == "C"
    assert env.data_asof({"cols": [], "rows": []}) is None      # SEC 13F has no as-of key today
    assert env.data_asof({"as_of": None, "generated_at": "C"}) == "C"


def test_every_registered_board_names_the_file_the_dashboard_serves():
    """One spelling of each board's artifact: ``v2_envelope.BOARDS`` against the dashboard's own route table.

    A board renamed or repointed in ``app/dashboard.py`` without its envelope entry would write the envelope
    under a board key no door could ask for.
    """
    from revenuechaser.app import dashboard
    for board, stem in env.BOARDS.items():
        served = dashboard._module_file(board)
        assert served is not None, board
        assert served.name == f"{stem}.html", board
        assert env.board_of(served) == board


def test_every_board_that_writes_a_payload_names_its_as_of():
    """A payload write names the envelope's as-of, because the payload file itself carries only the rows.

    The rule is over source: every ``write_board`` / ``_write_board`` call that hands over a payload (three or
    more positional arguments, or a starred ``(html, payload)`` pair) passes ``asof=``. Read from the files, not
    from a list kept here, so a new board's write trips it on the PR that adds the board.
    """
    import ast
    from pathlib import Path

    repo = Path(__file__).resolve().parents[2]
    missing = []
    for path in [repo / "app" / "runners.py", *sorted(repo.glob("module_*/report.py"))]:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
            if name not in ("write_board", "_write_board"):
                continue
            writes_payload = len(node.args) >= 3 or any(isinstance(a, ast.Starred) for a in node.args)
            if writes_payload and not any(k.arg == "asof" for k in node.keywords):
                missing.append(f"{path.relative_to(repo)}:{node.lineno}")
    assert missing == [], "payload written with no as-of for its v2 envelope: " + ", ".join(missing)


def test_a_board_schema_refuses_an_envelope_with_no_as_of():
    """The per-board schemas pin ``data_asof`` to a string: the door gets a date or refuses the file."""
    import json
    from pathlib import Path

    from revenuechaser.v2 import validate

    schemas = Path(__file__).resolve().parents[2] / "v2" / "schemas"
    board = json.loads((schemas / "module_relatedness.schema.json").read_text(encoding="utf-8"))
    generic = json.loads((schemas / "envelope.schema.json").read_text(encoding="utf-8"))
    written = env.build("module_relatedness", {"companies": []}, run_id="r1")
    assert written["data_asof"] is None
    assert validate.errors(written, generic) == []        # the contract allows null
    assert validate.errors(written, board) != []          # a board's own schema does not
