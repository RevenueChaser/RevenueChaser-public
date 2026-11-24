"""The timer measurement log (avo, 24 Nov 2026: "Fetch kaç dakika sürüyor? Parquet'ler nereye yazılıyor? ... DuckDB ne
zaman kuruluyor?"): one JSON line per dataset run, appended to ``<folder>/datasets-<local date>.jsonl``.

Each line: when the run ended, the timer job that ran it (``LIFE_JOB``, set by home-server's jobrun), the dataset and
its kind, the result, the seconds per step (fetch, parquet, build, check), the Parquet files it wrote (count, rows,
bytes, seconds, their folders), the DuckDB build (seconds, spill peak) and the serving file's size after it. The
timer runs themselves (start, end, exit) are jobrun's ``timers-<date>.jsonl`` in the same folder.

Append-only and never pruned here: a week is a few MB, and avo asked for at least a week. Every write is best
effort: a log that cannot be written never fails a run.
"""
from __future__ import annotations

import contextvars
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path

from ...core import config

logger = logging.getLogger(__name__)

#: The folder; default ``timer-measure`` beside the raw root (on homesrv /mnt/data/apps/revenuechaser/data).
DIR_ENV = "RC_MEASURE_DIR"

_RUN: contextvars.ContextVar[dict | None] = contextvars.ContextVar("rcdata_measure", default=None)
_OPEN: dict[str, dict] = {}                       # run id -> its measures, until the run's line is written


def folder() -> Path:
    return Path(os.getenv(DIR_ENV, "").strip() or Path(config.MARKET_RAW_DIR).parent / "timer-measure")


def begin(run_id: str) -> None:
    """The run whose fetch is in hand: what ``parquet`` sees until the next ``begin`` belongs to it."""
    m = _OPEN.setdefault(run_id, {"parquet": {"files": 0, "rows": 0, "bytes": 0, "seconds": 0.0, "dirs": []}})
    _RUN.set(m)


def parquet(path: Path, seconds: float, rows: int | None) -> None:
    m = _RUN.get()
    if m is None:
        return
    try:
        p = m["parquet"]
        p["files"] += 1
        p["rows"] += rows or 0
        p["bytes"] += path.stat().st_size
        p["seconds"] = round(p["seconds"] + seconds, 3)
        if str(path.parent) not in p["dirs"] and len(p["dirs"]) < 5:
            p["dirs"].append(str(path.parent))
    except OSError:
        pass


def build(run_id: str, kind: str, seconds: float, spill_bytes: int) -> None:
    m = _OPEN.setdefault(run_id, {})
    m["build"] = {"kind": kind, "seconds": round(seconds, 1), "spill_peak_gb": round(spill_bytes / 1e9, 2)}


def finish(ctx, req: dict, check: dict, status: str, duckdb_bytes: int | None) -> None:
    """Write the run's line and forget it."""
    m = _OPEN.pop(ctx.run_id, {})
    if _RUN.get() is m:
        _RUN.set(None)
    steps = ctx.step_times()
    line = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "job": os.getenv("LIFE_JOB"),
            "dataset": ctx.dataset, "kind": check.get("kind") or _kind(ctx.dataset), "run_id": ctx.run_id,
            "requested_by": req.get("requested_by"), "params": req.get("params") or {}, "status": status,
            "result": check.get("result"), "note": (check.get("note") or "")[:200], "rows": check.get("rows"),
            "calls": check.get("calls"), "steps_s": steps, "fetch_s": steps.get("fetch") or steps.get("backfill"),
            "parquet": m.get("parquet"), "build": m.get("build"), "duckdb_bytes": duckdb_bytes}
    write("datasets", line)


def write(name: str, line: dict) -> None:
    try:
        d = folder()
        d.mkdir(parents=True, exist_ok=True)
        day = datetime.now().strftime("%Y-%m-%d")    # the machine's zone: TZ=Europe/Amsterdam in rc-paths.env
        with open(d / f"{name}-{day}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(line, default=str) + "\n")
    except Exception:  # noqa: BLE001 - the log never fails a run
        logger.warning("measure: line not written", exc_info=True)


def _kind(dataset: str) -> str | None:
    from . import DATASETS
    ds = DATASETS.get(dataset)
    return getattr(ds, "kind", None)

