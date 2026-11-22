"""#150: one Settings collect asks each store question once.

The row builders and each dataset's ``Health`` ask the same health summaries, and the row builder and
the Fresh cell ask the same newest date. ``test_identity_coverage_124`` compares one collect with another,
so a question asked twice in both passes there; these tests count the runs inside ONE collect.

Store only: the seeded store is a temp DuckDB per store file, no provider is asked.
"""
from __future__ import annotations

import sys
from collections import Counter

import pytest

from revenuechaser.core import datahealth, rawstore
from revenuechaser.module_settings import inventory

# Every summary a dataset row and a registry coverage both ask (core/datasets.py ``_summary_health``).
SUMMARIES = (
    "core.prices", "core.quotes", "core.vendor_data", "core.index_levels", "core.sec_files",
    "core.sec_submissions", "module_sector_rotation.etf_holdings",
)


def _module(dotted: str):
    __import__(f"revenuechaser.{dotted}")
    return sys.modules[f"revenuechaser.{dotted}"]




def test_scoped_treats_a_default_argument_and_an_omitted_one_as_one_call():
    """``f()``, ``f(None)`` and ``f(now=None)`` are one question: the key is the bound arguments."""
    runs = []

    @datahealth.scoped
    def summary(now=None):
        runs.append(now)
        return {"n": len(runs)}

    with datahealth.memo_scope():
        assert summary() == summary(None) == summary(now=None) == {"n": 1}
    assert runs == [None]










