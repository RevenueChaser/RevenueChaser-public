"""The Relatedness board's profile writer (#360), read from the one LLM-job registry (#404).

The pair itself is no longer a setting of this board: since #404 every LLM job has its own pair on the
``llm_writers`` settings board (:mod:`revenuechaser.core.llm_jobs`, job ``relatedness.profiles``), so one screen
holds every job's writer and there is no second copy of the rule. This module stays the board's way in.
"""
from __future__ import annotations

from revenuechaser.core import board_settings, llm_jobs
from revenuechaser.core import llm_writers as writers

BOARD = "module_relatedness"
JOB = "relatedness.profiles"


def specs() -> dict[str, board_settings.Setting]:
    """No board-level knobs: the writer pair moved to the ``llm_writers`` board (#404)."""
    return {}


def rules(_v: dict) -> list[str]:
    return []


def writer() -> tuple[str, str]:
    """``(provider, model)`` the board runs with (the chosen pair, else EVREN and its default model)."""
    return llm_jobs.pair(JOB)


def chosen_model() -> str | None:
    """The chosen model, or ``None`` when the provider's own default applies (the chat module's ``MODEL`` then
    stays, which honours ``RC_<PROVIDER>_MODEL``)."""
    slug, model = writer()
    return model if model != writers.get(slug).models[0] else None
