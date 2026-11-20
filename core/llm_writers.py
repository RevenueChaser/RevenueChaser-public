"""The LLM writers (#360, framework D9, avo 1-2 Nov 2026): which provider and model an LLM job can run on.

One row per writer: its chat module, a short model list (the first is its default) and the one credential it needs.
This is the single registry; which writer a given job runs on is :mod:`core.llm_jobs` (#404). EVREN is the default
and has no fee, DeepSeek is paid (off-peak gated, USD cap).

It lives in ``core`` since #404: every LLM job reads it, not the Relatedness board alone.

An option is available when its credential is present. Only the variable NAME is ever reported (``missing``),
never a value: the check is presence only, like ``core.credentials.problem``.
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass

from RevenueChaser.core import credentials


@dataclass(frozen=True)
class Writer:
    slug: str
    label: str
    module: str                  # the chat client: ``complete(system, user, ...)`` and ``MODEL``
    models: tuple[str, ...]      # the first is the default
    credential: str              # the variable named when it is absent
    paid: bool = False


WRITERS: dict[str, Writer] = {
    # One default each, a name of home-server etc/litellm/config.yaml, the one model list (avo 15 Nov 2026); Flash only.
    "evren": Writer("evren", "EVREN (no fee)", "RevenueChaser.core.providers.evren",
                    ("evren-deepseek-v4.1-flash",), "LITELLM_RC_KEY"),
    "deepseek": Writer("deepseek", "DeepSeek API (paid, off-peak)", "RevenueChaser.core.providers.deepseek",
                       ("deepseek-v4-flash",), "LITELLM_RC_KEY", paid=True),
}
DEFAULT = "evren"


def get(slug: str) -> Writer:
    if slug not in WRITERS:
        raise ValueError(f"unknown profile writer {slug!r}; one of {', '.join(WRITERS)}")
    return WRITERS[slug]


def client(slug: str):
    """The chat module of ``slug`` (imported on demand)."""
    return importlib.import_module(get(slug).module)


def all_models() -> tuple[str, ...]:
    """Every model of every writer, in registry order (the setting's closed set; the pair rule narrows it)."""
    return tuple(dict.fromkeys(m for w in WRITERS.values() for m in w.models))


def missing(slug: str) -> str | None:
    """The NAME of the absent credential of ``slug``, or ``None`` when it is present. Never a value."""
    w = get(slug)
    return None if credentials.key_for(slug) else w.credential


def missing_text(slug: str) -> str | None:
    name = missing(slug)
    return None if name is None else f"{name} is not set on this box"


def options() -> list[dict]:
    """One row per writer for a settings UI: ``provider``, ``label``, ``models``, ``available``, ``missing``."""
    out = []
    for slug, w in WRITERS.items():
        name = missing(slug)
        out.append({"provider": slug, "label": w.label, "models": list(w.models), "paid": w.paid,
                    "available": name is None, "missing": name})
    return out
