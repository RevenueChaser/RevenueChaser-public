"""v2 step 3 (#1241): one JSON Schema per board, and a schema the envelope itself must satisfy.

``v2/schemas/`` is the door's and Android's one description of what a board sends (`parity.json` is generated from
these later, run plan row 18). The checks here are the CI gate the run plan asks for: a board that writes a payload
has a schema, every schema describes the envelope contract, and a written envelope validates against its board's
schema. The validator is `v2/validate.py` — a small subset of JSON Schema, because the repo carries no
``jsonschema`` dependency.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from RevenueChaser.core import reporting_common as rc
from RevenueChaser.core import v2_envelope as env
from RevenueChaser.v2 import validate

SCHEMAS = Path(__file__).resolve().parents[1] / "schemas"
ENVELOPE_KEYS = ["schema_version", "board", "run_id", "data_asof", "built_at",
                 "private", "renderer", "layout", "data"]


def _schema(board: str) -> dict:
    return json.loads((SCHEMAS / f"{board}.schema.json").read_text(encoding="utf-8"))


def test_every_board_that_writes_a_payload_has_a_schema():
    """The registry is in source (`v2_envelope.BOARDS`), not in this file, so a new board trips this on its own PR."""
    for board in env.BOARDS:
        assert (SCHEMAS / f"{board}.schema.json").exists(), board


def test_no_schema_file_describes_a_board_the_registry_does_not_name():
    named = {f"{b}.schema.json" for b in env.BOARDS} | {"envelope.schema.json"}
    assert {p.name for p in SCHEMAS.glob("*.schema.json")} == named


@pytest.mark.parametrize("name", ["envelope"] + sorted(env.BOARDS))
def test_each_schema_requires_the_whole_envelope_contract(name):
    schema = _schema(name)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert sorted(schema["required"]) == sorted(ENVELOPE_KEYS)
    assert sorted(schema["properties"]) == sorted(ENVELOPE_KEYS)
    assert schema["properties"]["schema_version"]["const"] == env.ENVELOPE_SCHEMA_VERSION
    assert schema["properties"]["renderer"]["enum"] == [env.GENERIC, env.BESPOKE]
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize("board", sorted(env.BOARDS))
def test_each_boards_schema_pins_its_own_board_key_and_its_payload_shape(board):
    schema = _schema(board)
    assert schema["properties"]["board"]["const"] == board
    data = schema["properties"]["data"]
    assert data["type"] == "object"
    assert data["required"], board          # a schema that requires nothing of ``data`` checks nothing


def test_a_written_envelope_validates_against_its_boards_schema(tmp_path):
    html = tmp_path / "relatedness_latest.html"
    # One entry per company, as ``module_relatedness/report._embed_companies`` builds them: a record, not a name.
    payload = {"as_of": "2026-11-20T10:00:00Z", "n": 1,
               "companies": [{"ticker": "AAA", "name": "Aaa Inc"}], "peers": {}}
    rc.write_board(html, "", payload, run_id="r1")
    written = json.loads(gzip.decompress(env.envelope_path(html).read_bytes()).decode("utf-8"))
    assert validate.errors(written, _schema("module_relatedness")) == []
    assert validate.errors(written, _schema("envelope")) == []


def test_the_validator_reports_what_is_wrong():
    schema = _schema("envelope")
    good = {k: None for k in ENVELOPE_KEYS}
    good.update({"schema_version": env.ENVELOPE_SCHEMA_VERSION, "board": "x", "run_id": "r",
                 "built_at": "2026-11-21T00:00:00Z", "private": False, "renderer": "generic",
                 "data": {}})
    assert validate.errors(good, schema) == []
    assert validate.errors({**good, "renderer": "fancy"}, schema)        # not in the enum
    assert validate.errors({**good, "private": "no"}, schema)            # not a boolean
    assert validate.errors({**good, "schema_version": 99}, schema)       # wrong const
    assert validate.errors({**good, "extra": 1}, schema)                 # additionalProperties
    assert validate.errors({k: v for k, v in good.items() if k != "board"}, schema)   # missing required
