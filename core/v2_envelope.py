"""The v2 envelope: what a board hands the v2 door, around the payload the old page already reads.

Run plan row 3 (claude-coordinator ``plans/2026-11-21_0230_revenuechaser_v2-run-plan.md``, #1241, epic #1238).
``reporting_common.write_board`` writes it as a second file next to the HTML and the K10 payload::

    {schema_version, board, run_id, data_asof, built_at, private, renderer, layout, data}

``data`` is the payload, unchanged and serialised exactly as the payload file serialises it, so the two files
always agree: ``sha256(data_bytes(envelope)) == sha256(gzip.decompress(payload_file))`` is the step's proof of
done and a test in ``core/tests/test_v2_envelope.py``.

Why each key:

- ``schema_version`` — the envelope's own version. Not the store's ``_SCHEMA_VERSION``: this file is a regenerable
  artifact under ``.cache/``, so a bump here needs no store checkpoint.
- ``board`` — the dashboard's module key (``module_relatedness``), the name ``app/dashboard.TABS`` and the payload
  route already use, so the door asks for a board by the one name the system has for it.
- ``run_id`` — ``rawstore.writer_run_id()``: the dashboard job that wrote it, so the envelope joins to its
  ``job_runs`` row and the door can refuse an envelope whose build is not the served one (the "payload drift" risk
  of the v2 review; the run plan keys on ``run_id`` where the design plan said ``source_build``).
- ``data_asof`` — the payload's own as-of value, by the ordered key probe below; ``None`` where a board carries
  none (SEC 13F's payload is ``{cols, rows, fields}``).
- ``built_at`` — when this file was written, UTC. A freshness line on a screen reads ``data_asof``, never this.
- ``private`` — ``True`` marks data that never reaches the AI chat, a mock, a fixture or a log (the portfolio of
  run plan row 16 is the first one). Every board today is ``False``.
- ``renderer`` — ``generic`` for a board the v2 renderers draw from ``layout``; ``bespoke`` for one with its own
  code, which Android reaches as a web view and ``parity.json`` does not claim.
- ``layout`` — the panel/table/chart description the generic renderers read. ``None`` until they exist (run plan
  row 8); the key is in the contract from the start so the schemas keep their shape.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

ENVELOPE_SCHEMA_VERSION = 1

# Next to the HTML, like the payload (``reporting_common.PAYLOAD_SUFFIX``), and gzip for the same reason: the door
# serves it as stored.
ENVELOPE_SUFFIX = ".v2.json.gz"

GENERIC, BESPOKE = "generic", "bespoke"
RENDERERS = (GENERIC, BESPOKE)

# The six boards that write a K10 payload today: the dashboard's module key -> its artifact file stem
# (``app/runners.py`` constants, served by ``app/dashboard._module_file``). One schema per entry lives in
# ``v2/schemas/<board>.schema.json``; ``v2/tests/test_v2_schemas.py`` fails an entry without one, and
# ``core/tests/test_v2_envelope.py`` fails a stem the dashboard does not serve.
BOARDS: dict[str, str] = {
    "module_asymmetric_growth": "asymmetric_growth_latest",
    "module_comovement": "comovement_latest",
    "module_fundamentals": "fundamentals_latest",
    "module_relatedness": "relatedness_latest",
    "module_sec_13f": "sec_13f_latest",
    "module_swing_potential": "swing_potential_latest",
}
_BY_STEM = {stem: board for board, stem in BOARDS.items()}

# In this order, first non-empty wins. ``data_as_of`` is the data's own date where a board has one (Swing,
# Fundamentals); ``as_of`` is the run's session (Co-movement, Relatedness); ``generated_at`` is the fallback for a
# payload that only knows when it was built.
ASOF_KEYS = ("data_as_of", "data_asof", "as_of", "asof", "generated_at")

# One spelling of the payload's JSON form, used for the payload file and for ``data`` inside the envelope. Equal
# options are what makes the two hashes equal.
JSON_ARGS = {"ensure_ascii": False, "default": str, "separators": (",", ":")}


def envelope_path(html_path) -> Path:
    """The board's envelope file: next to its HTML, ``<stem>.v2.json.gz``."""
    p = Path(html_path)
    return p.with_name(p.stem + ENVELOPE_SUFFIX)


def board_of(html_path) -> str:
    """The board key for an artifact path: its registered module key, else the file stem without ``_latest``."""
    stem = Path(html_path).stem
    if stem in _BY_STEM:
        return _BY_STEM[stem]
    return stem[: -len("_latest")] if stem.endswith("_latest") else stem


def data_asof(payload) -> str | None:
    """The payload's own as-of value by ``ASOF_KEYS``, as a string; ``None`` when it carries none."""
    if not isinstance(payload, dict):
        return None
    for key in ASOF_KEYS:
        value = payload.get(key)
        if value not in (None, ""):
            return value if isinstance(value, str) else str(value)
    return None


def build(board: str, payload, *, run_id: str, renderer: str = GENERIC, private: bool = False,
          layout=None, built_at: str | None = None, asof: str | None = None) -> dict:
    """The envelope dict for one board's payload, keys in contract order.

    ``asof`` overrides the key probe for a board whose payload hides its date deeper (none today).
    """
    if renderer not in RENDERERS:
        raise ValueError(f"renderer must be one of {RENDERERS}: {renderer!r}")
    return {
        "schema_version": ENVELOPE_SCHEMA_VERSION,
        "board": board,
        "run_id": run_id,
        "data_asof": (str(asof) if not isinstance(asof, str) else asof) if asof is not None
                     else data_asof(payload),
        "built_at": built_at or time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "private": bool(private),
        "renderer": renderer,
        "layout": layout,
        "data": payload,
    }


def data_bytes(envelope: dict) -> bytes:
    """``envelope["data"]`` as the payload file stores it, for the hash that ties the two files together."""
    return json.dumps(envelope["data"], **JSON_ARGS).encode("utf-8")
