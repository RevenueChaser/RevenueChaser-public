"""Rebuild ``scripts/test_durations.json`` from FULL runs' junit artifacts (#1153).

``select_tests.in_shard`` places a measured test file by its time, so the six unit shards hold the same number of
seconds (``select_tests._measured_homes``). The table behind it used to be a hand edit from one run, which left
two kinds of error behind: files that had gone from the tree stayed in it, and every file under a second was
dropped, so the table named 274 of the tier's 873 files and covered 60 % of its time -- the rest was placed by
hash and carried the imbalance. This script is how the table is rebuilt instead.

Usage, from a checkout with ``gh`` signed in::

    python scripts/durations.py 44641662410 44647897294 44648787468

Each argument is a ``tests`` workflow run that ran the FULL unit tier. The script downloads that run's
``junit-unit-*`` artifacts, sums each test's time per file, and writes the mean over the runs given of the runs
that hold each file. Several runs are asked for on purpose: a GitHub runner's speed drifts by a fifth from one
run to the next (measured on #896, 19 Nov 2026), and one run alone would write that drift into the table.

**Every run given must have the same test tree.** A file a commit splits, renames or rewrites is not the same
file in an older run, and averaging the two writes a time nothing will ever cost: rebuilding over the three runs
before #1153's split and the one after it put ``test_ownership_serve.py`` at 424 s, the mean of its 500 s with 48
tests and its 195 s with 13. Rebuild from runs on one tree, newest first.

When a file is split, its successors have no run of their own yet: their entries are the measured means of the
tests that moved, apportioned by hand in the commit that splits them (#1153 did that for ``test_ownership_serve``
and ``test_prices_incremental``), and the next rebuild from a FULL run replaces the estimate with a measurement.

The times are the junit ``time`` of each test, which under ``pytest -n auto`` is wall time with the other workers
of its own shard beside it. That is the number the shard split wants: it is what the file will cost again in CI,
not what it would cost alone.
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
#: Where the table lives; ``select_tests.DURATIONS`` reads the same path.
TABLE = Path(__file__).with_name("test_durations.json")
#: CI's runner holds four workers under ``pytest -n auto`` (``unit`` in ``.github/workflows/tests.yml`` runs on
#: ``ubuntu-latest``, 4 vCPU as of 19 Nov 2026), so a shard's busy time is its own time over four -- unless one
#: file is longer than that, because ``--dist loadfile`` gives a whole file to one worker.
RUNNER_WORKERS = 4
#: A file may cost this much of a shard's per-worker share before it is the tier's floor on its own and wants
#: splitting. At 1.0 a file exactly fills its worker while the other three empty; the room above it is for the
#: drift between runs.
MAX_FILE_SHARE = 1.25


def path_of(classname: str) -> str | None:
    """The test file a junit ``classname`` names, or ``None``.

    pytest writes the dotted module (``rcdata.tests.test_ownership_serve``) and appends the class when the test
    sits in one, so the file is the prefix up to the last segment that starts with ``test_``.
    """
    parts = classname.split(".")
    for i in range(len(parts) - 1, -1, -1):
        if parts[i].startswith("test_"):
            return "/".join(parts[: i + 1]) + ".py"
    return None


def file_seconds(xml_text: str) -> dict[str, float]:
    """One junit file's seconds per test file."""
    out: Counter[str] = Counter()
    for case in ET.fromstring(xml_text).iter("testcase"):
        rel = path_of(case.get("classname") or "")
        if rel:
            out[rel] += float(case.get("time") or 0.0)
    return dict(out)


def merge(tables: list[dict[str, float]], exists=None) -> dict[str, float]:
    """The mean over the tables that hold each file, for the files still in the tree.

    A file one run skipped (a test added since, a SELECTIVE shard) is averaged over the runs that ran it, never
    over the runs given, so a missing run does not halve its time. A file no longer in the tree is dropped: a
    stale entry holds a shard's place for a file that will never run there.
    """
    exists = exists or (lambda rel: (REPO / rel).is_file())
    names = {rel for t in tables for rel in t}
    out = {}
    for rel in sorted(names):
        seen = [t[rel] for t in tables if t.get(rel)]
        if seen and exists(rel):
            out[rel] = round(sum(seen) / len(seen), 1)
    return out


def heaviest_share(seconds: dict[str, float], shards: int = 6, workers: int = RUNNER_WORKERS) -> float:
    """The longest file over a shard's per-worker share: above :data:`MAX_FILE_SHARE` it sets the tier's floor."""
    if not seconds:
        return 0.0
    return max(seconds.values()) / (sum(seconds.values()) / shards / workers)


#: ``gh api --jq``: the run's junit-unit artifacts as "<id> <name>" lines.
_ARTIFACT_JQ = r'.artifacts[] | select(.name|startswith("junit-unit")) | "\(.id) \(.name)"'


def _artifacts(run_id: str) -> list[tuple[str, str]]:
    out = subprocess.run(["gh", "api", f"repos/alsanvolkan/revenuechaser-public/actions/runs/{run_id}/artifacts",
                          "--jq", _ARTIFACT_JQ],
                         check=True, capture_output=True, text=True).stdout.split("\n")
    return [tuple(line.split(" ", 1)) for line in out if line.strip()]


def _run_table(run_id: str, work: Path) -> dict[str, float]:
    table: Counter[str] = Counter()
    for art_id, name in _artifacts(run_id):
        zip_path = work / f"{run_id}-{name}.zip"
        with open(zip_path, "wb") as fh:
            subprocess.run(["gh", "api", f"repos/alsanvolkan/revenuechaser-public/actions/artifacts/{art_id}/zip"],
                           check=True, stdout=fh)
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                if member.endswith(".xml"):
                    for rel, s in file_seconds(zf.read(member).decode("utf-8")).items():
                        table[rel] += s
    if not table:
        raise SystemExit(f"run {run_id}: no junit-unit artifact held a test")
    return dict(table)


def main(argv: list[str]) -> int:
    if not argv:
        raise SystemExit(__doc__)
    with tempfile.TemporaryDirectory() as tmp:
        tables = [_run_table(run_id, Path(tmp)) for run_id in argv]
    merged = merge(tables)
    TABLE.write_text(json.dumps(merged, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    total = sum(merged.values())
    print(f"{TABLE.relative_to(REPO)}: {len(merged)} files, {total:.0f} s of tests over {len(argv)} run(s)")
    print(f"per shard {total / 6:.0f} s, per worker {total / 6 / RUNNER_WORKERS:.0f} s; "
          f"longest file {max(merged.values()):.0f} s = {heaviest_share(merged):.2f} of that share")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
