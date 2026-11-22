"""``core/index_registry.py`` reads the identity spine (build plan PR 6): the badges, the filter's index list and
``load_index`` come from ``rcdata.read`` only; the old store's ``index_constituents`` (``core/index_lists.py``) is
never read by the registry since #642 PR 6 removed ``RC_UNIVERSE_SOURCE``."""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from revenuechaser.core import index_registry as ir
from revenuechaser.core import universe
from revenuechaser.rcdata import read
from revenuechaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401 - market roots per test
from revenuechaser.rcdata.tests.test_spine_security import built, run_all  # noqa: F401 - the 10 names


def test_the_registry_does_not_import_the_old_store():
    tree = ast.parse(Path(ir.__file__).read_text(encoding="utf-8"))
    imported = {a.name for n in ast.walk(tree) if isinstance(n, (ast.Import, ast.ImportFrom)) for a in n.names}
    assert "rawstore" not in imported and not hasattr(ir, "rawstore")
