"""The envelope files on disk, as the door sees them: which boards exist, their metadata, and their bytes.

No HTTP and no framework here, so the unit tier tests the door's reading rules directly. The board keys and their
artifact stems come from ``core/v2_envelope.BOARDS`` — the contract step 3 wrote — so the door asks for a board by
the one name the dashboard, ``app/dashboard.TABS`` and the JSON Schemas already use. The door never names a stem
of its own, which is what keeps a board added later from needing an edit here.
"""
from __future__ import annotations

import gzip
import hashlib
import json
from pathlib import Path

from revenuechaser.core import v2_envelope

# The metadata keys of an envelope that the board list repeats. ``data`` is deliberately absent: the list is read
# on every screen load and a board's rows are tens of thousands of them.
LIST_KEYS = ("schema_version", "board", "run_id", "data_asof", "built_at", "private", "renderer")


class UnknownBoard(KeyError):
    """A board key that is not in the v2 contract — never a missing file."""


class NoEnvelope(FileNotFoundError):
    """A known board whose envelope has not been written yet, or was dropped by a Refresh."""


def board_keys() -> tuple[str, ...]:
    """Every board the door serves, in one order, so the list route and the version pointer agree."""
    return tuple(sorted(v2_envelope.BOARDS))


def artifacts_dir() -> Path:
    """Where the boards' artifacts live: ``core.config.OUTPUT_DIR`` (``RC_CACHE_DIR``), read on every call.

    Imported inside the function on purpose. ``core.config`` creates its roots at import time, so a module-level
    import here would make merely importing the door touch the filesystem — and in the e2e tier the roots are
    redirected per process.
    """
    from revenuechaser.core import config
    return Path(config.OUTPUT_DIR)


def envelope_path(board: str) -> Path:
    """The envelope file for ``board``: ``<artifacts>/<stem>.v2.json.gz``, the name ``write_board`` wrote."""
    try:
        stem = v2_envelope.BOARDS[board]
    except KeyError as exc:
        raise UnknownBoard(board) from exc
    return artifacts_dir() / f"{stem}{v2_envelope.ENVELOPE_SUFFIX}"


def stored_bytes(board: str) -> bytes:
    """The envelope exactly as it sits on disk (gzip), for serving it without recompressing per request."""
    path = envelope_path(board)
    try:
        return path.read_bytes()
    except FileNotFoundError as exc:
        raise NoEnvelope(board) from exc


def read(board: str) -> dict:
    """The envelope as a dict. Raises :class:`UnknownBoard` or :class:`NoEnvelope`, never a gzip error silently."""
    return json.loads(gzip.decompress(stored_bytes(board)))


def data_sha256(board: str) -> str:
    """``sha256`` of the envelope's ``data`` as the payload file stores it — the deploy's six-equal-pairs proof.

    The same bytes ``core.v2_envelope.data_bytes`` builds, so the hash the door reports and the hash of the
    dashboard's decompressed payload file are comparable without either side re-serialising the other's JSON.
    """
    return hashlib.sha256(v2_envelope.data_bytes(read(board))).hexdigest()


def summary(board: str) -> dict:
    """One row of the board list: the envelope's metadata plus where it is and how big, never its ``data``.

    A board with no envelope yet is a row with ``present: false``, not an error: the v2 screens ask the list what
    they may draw, and a board whose job has not run since the deploy is an ordinary state, not a fault.
    """
    if board not in v2_envelope.BOARDS:
        raise UnknownBoard(board)
    path = envelope_path(board)
    try:
        raw = path.read_bytes()
    except FileNotFoundError:
        return {"board": board, "present": False}
    envelope = json.loads(gzip.decompress(raw))
    row = {key: envelope.get(key) for key in LIST_KEYS}
    row.update(board=board, present=True, stored_bytes=len(raw), data_bytes=len(v2_envelope.data_bytes(envelope)))
    return row


def board_list() -> list[dict]:
    """Every board's row, in :func:`board_keys` order."""
    return [summary(board) for board in board_keys()]
