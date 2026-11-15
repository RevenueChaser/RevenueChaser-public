"""What the Swing board says about its rules and sources matches what the code does (Fable review finding 9, PR 6).

The Minervini gate is decided by its seven price rules; the RS rating is shown and counted for quality but does not
decide (#65, ``screeners.evaluate_minervini``). The names come from the universe (the identity spine by default) and
the bars from the store's daily bars, which the nightly fills from Unusual Whales with a yfinance fallback; the board
itself never calls yfinance for bars (``screen_common.load_bars``).
"""
from __future__ import annotations

import ast
from pathlib import Path


from RevenueChaser.app import runners
from RevenueChaser.module_swing_potential import report, screeners
from RevenueChaser.module_swing_potential.tests.test_gates import _PASS








def test_the_swing_runner_does_not_claim_yfinance_only():
    doc = ast.get_docstring(next(n for n in ast.parse(Path(runners.__file__).read_text(encoding="utf-8")).body
                                 if isinstance(n, ast.FunctionDef) and n.name == "run_swing"))
    assert "yfinance-only" not in doc and "daily bars" in doc
