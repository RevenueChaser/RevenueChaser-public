"""C8 (#383 R3; card D option 2): one writer of ``swing_ohlc``, in core, with the F2b new-listing rule.

Before, two writers wrote the cache: Swing's ``indicators._write_ohlc`` (the per-ticker refetch, now only the SPY
fallback) and Co-movement's bulk ``fetch_bulk``. Only Swing's path had #261's guard (a short refetch never replaces
a longer stored history), and the guard took any refetch that shares no session with the stored bars for another
listing under a reused symbol. The F2b review found the gap: one bar right after the stored last bar shares no
session either, so a 500-bar history was replaced by 1 bar (card F2b, avo "30 gün şartı", 2026-10-15 20:13
Amsterdam). Now ``module_swing_potential/ohlc_cache.py`` is the one writer (Co-movement's row format, moved), both
paths write through
it, and a short series that shares no session is a new listing only when it starts more than 30 days after the
stored last bar. No visible change otherwise: same rows, same ``ts`` format, same replace-per-ticker write.
Offline: a temp store.
"""
from __future__ import annotations

import re
import time
import types
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from revenuechaser.core import rawstore
from revenuechaser.module_comovement import ohlc as comov_ohlc
from revenuechaser.module_swing_potential import indicators

ROOT = Path(__file__).resolve().parents[2]


def _frame(start: str, periods: int) -> pd.DataFrame:
    idx = pd.bdate_range(start, periods=periods)
    c = pd.Series(np.arange(periods, dtype=float) + 100.0, index=idx)
    return pd.DataFrame({"Open": c, "High": c * 1.01, "Low": c * 0.99, "Close": c, "Volume": 1.0e6})






STORED = _frame("2024-01-01", 500)                      # ends 2025-11-28 (a Friday)
LAST = STORED.index[-1]


# ── one writer ────────────────────────────────────────────────────────────────

def test_no_other_production_code_writes_swing_ohlc():
    pattern = re.compile(r"""(write_rows|replace_all|append_rows)\(\s*["']swing_ohlc["']|INTO\s+swing_ohlc""")
    writers = []
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT).as_posix()
        if "/tests/" in rel or rel.startswith(("scripts/", "module_testing/", ".")) \
                or rel == "module_swing_potential/ohlc_cache.py":
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="replace")):
            writers.append(rel)
    assert writers == []




# ── the rule (#261 + F2b) ─────────────────────────────────────────────────────











# ── both paths write through it ───────────────────────────────────────────────



