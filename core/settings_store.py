"""Where a board's saved setting overrides come from (#404).

Nothing is stored here yet: the ``board_settings`` table that held the overrides, and the Save and Reset that
wrote them, went with the old store (#860), so every board runs on its config defaults and this returns nothing.
It exists as its own module so that the readers of a saved value do not all have to import
:mod:`core.board_settings`, which reaches every board module to collect its specs. ``core.llm_jobs`` is such a
reader — every LLM job calls it — and the import would have put every board on the path of the root conftest's
own imports, which makes CI run the whole suite for any board change (``scripts/select_tests.py``).

When a settings store lands, this is the one place that reads it.
"""
from __future__ import annotations


def overrides(board: str) -> dict[str, str]:
    """The values saved for ``board``, by setting key. Empty until a settings store exists (#860)."""
    return {}
