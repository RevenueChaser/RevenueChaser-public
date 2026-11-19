"""#1098, #1100: a build step never opens a DuckDB connection without a memory limit.

A ``duckdb.connect()`` carries DuckDB's own default limit — 80 % of the machine's RAM — and no ``temp_directory``,
so a step that outgrows the box grows until the kernel ends the build instead of spilling. That holds whether the
database is in memory (a bare ``duckdb.connect()``) or a file (``duckdb.connect(path)``, which the quarterly SEC
set readers used for a whole typed zip), and nothing in the build connection's own ``memory_limit``
(``serving.build_config``) covers either. Every step opens its scratch connection through ``base.scratch_con``
(``serving.connect_scratch``) or, for a database on a file, ``serving.connect_scratch_file``; both carry the same
adaptive limit and a spill folder of their own.

So this fails **any** ``duckdb.connect`` outside ``rcdata/serving.py``, not only the argument-less one: #1100
found three file-backed connections that the first version of this test could not see.

Only code is checked: a comment or a docstring may still name the old call.
"""
from __future__ import annotations

import ast
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
#: Where the one allowed ``duckdb.connect`` of a scratch connection lives.
ALLOWED = {Path("rcdata/serving.py")}


def _calls(path: Path) -> list[int]:
    """The lines of ``path`` holding a ``duckdb.connect`` call, with arguments or without."""
    tree = ast.parse(path.read_text(encoding="utf-8"))
    lines = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if (isinstance(func, ast.Attribute) and func.attr == "connect"
                and isinstance(func.value, ast.Name) and func.value.id == "duckdb"):
            lines.append(node.lineno)
    return lines


def test_no_build_code_opens_an_unlimited_duckdb_connection():
    offenders = []
    for path in sorted((_REPO / "rcdata").rglob("*.py")):
        relative = path.relative_to(_REPO)
        if relative in ALLOWED or "tests" in relative.parts:
            continue
        offenders += [f"{relative}:{line}" for line in _calls(path)]
    assert offenders == [], ("these open DuckDB with no memory limit and no spill folder; use base.scratch_con() "
                             "or serving.connect_scratch_file(): " + ", ".join(offenders))
