"""Find Item 1 / Item 4 in a filing from its heading list, with the writer (avo, 8 Nov 2026).

The rule-based cut (``module_value_chain/splitter.py``) stays the default. Only when its cut is ``overrun`` (no stop
header followed the start), ``missing`` or ``short`` does the profile run ask the board's writer (EVREN by default, no
fee) where the business section starts and ends. The writer is sent the numbered heading lines of the whole document,
never its text, and answers two heading numbers; the text between them is the section.

Pure functions plus ``locate``, which makes the one call.
"""
from __future__ import annotations

from ..rcdata.sec_locator import (ASK_ON, MAX_HEADINGS, PROMPT_VERSION, SYSTEM, asks, build_user, cut,  # noqa: F401
                                  headings, parse, system_prompt)


def locate(ticker: str, name: str, form: str | None, text: str, *, budget=None, provider: str = "",
           model: str | None = None, client=None) -> str | None:
    """The business section of ``text`` (a whole filing) as the writer places it, or None.

    No ``provider`` means the registry's default writer, which has no fee (``profiles.llm``); it was the paid
    DeepSeek until 20 Nov 2026 (avo: "Fetch ve build sirasinda deepseek api kullanilan islem kalmasin").

    One call (counted by ``budget``), JSON mode, no thinking, cached like a profile chunk. A reply that names no
    usable pair of headings, or a section under the profile floor, is None: the caller keeps the rule cut."""
    from . import config, profiles

    heads = headings(text)
    if len(heads) < 2:
        return None
    if budget is not None and not budget.consume():
        raise profiles.BudgetExceeded()
    extra = {"model": model} if model else {}
    raw = profiles.llm(provider).complete(
        system_prompt(), build_user(name, form, heads), thinking=False, reasoning_effort=None, max_tokens=200,
        json_mode=True, use_cache=True, client=client, ticker=ticker, prompt_version=config.PROMPT_VERSION,
        validate=lambda c: parse(c, len(heads)) is not None, **extra)
    got = parse(raw, len(heads))
    if got is None:
        return None
    section = cut(text, heads, *got)
    return section if profiles.text_status(section) is None else None
