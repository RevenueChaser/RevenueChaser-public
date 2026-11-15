"""The question registry: a question is declared once, here, and the tool runs it for whoever asked.

"Kim neresinin okunmasini istiyorsa o araca soyler" (avo, 15 Nov 2026 11:14): a board adds one :class:`Question` with
:func:`register` and reads the answers through ``rcdata.read.sec_reads``. Its prompt and parser stay next to the
board's rules in review, but run only inside the tool. Step 1 registers none.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterable

#: The providers the asker has a pool for (``asker.POOLS``). The Grok and Claude subscription writers are being
#: removed (RevenueChaser PR 876), so the tool does not build on them.
PROVIDERS = ("evren", "deepseek")
#: Each provider's model when a question names none. DeepSeek is always its Flash model, never Pro (avo, 15 Nov
#: 2026 12:01).
DEFAULT_MODEL = {"evren": "deepseek-v4.1-flash", "deepseek": "deepseek-flash"}
CHUNK_CHARS = 60_000
MAX_TOKENS = 8_000


@dataclass(frozen=True)
class Input:
    """The text one company's question is asked about, and the filing it came from."""

    accession: str
    document: str
    filing_date: date | None
    text: str
    #: The cutter version of the text (``filing_section.rules_version``), so a re-cut shows on the answer.
    rules_version: str = ""


def _one(parts: list[dict]) -> dict:
    return parts[0] if len(parts) == 1 else {"chunks": parts}


@dataclass(frozen=True)
class Question:
    """One question. ``scope`` names the companies, ``inputs`` their text, ``parse`` turns a reply into an answer.

    ``parse`` returns None for an unusable reply (counted as an attempt, never stored over a good answer). A text
    longer than ``chunk_chars`` is asked in chunks; ``merge`` joins the chunks' answers.
    """

    id: str
    owner: str
    system: str
    prompt_version: str
    scope: Callable[[], Iterable[str]]
    inputs: Callable[[list[str]], dict[str, Input]]
    parse: Callable[[str], dict | None]
    provider: str = "evren"
    model: str = ""
    user: Callable[[str], str] = field(default=lambda chunk: chunk)
    merge: Callable[[list[dict]], dict] = field(default=_one)
    chunk_chars: int = CHUNK_CHARS
    max_tokens: int = MAX_TOKENS

    @property
    def writer_model(self) -> str:
        return self.model or DEFAULT_MODEL[self.provider]

    def chunks(self, text: str) -> list[str]:
        """The user messages the text is sent as: the exact bytes, so the input hash is theirs."""
        n = max(1, self.chunk_chars)
        return [self.user(text[i:i + n]) for i in range(0, len(text), n)] or [self.user("")]

    def input_hash(self, text: str) -> str:
        """The hash of what is sent (system prompt and every chunk): the same bytes, the same hash, no new call."""
        h = hashlib.sha256(self.system.encode("utf-8"))
        for chunk in self.chunks(text):
            h.update(b"\x00" + chunk.encode("utf-8"))
        return h.hexdigest()[:32]


QUESTIONS: dict[str, Question] = {}


def register(q: Question) -> Question:
    """Add ``q`` to the registry; refused in words for an unknown provider, a Pro model or a second ``id``."""
    if q.provider not in PROVIDERS:
        raise ValueError(f"{q.id}: provider {q.provider!r} has no pool; one of {', '.join(PROVIDERS)}")
    if q.provider == "deepseek" and "pro" in q.writer_model.lower():
        raise ValueError(f"{q.id}: DeepSeek is always Flash, never Pro (avo, 15 Nov 2026)")
    if q.id in QUESTIONS and QUESTIONS[q.id] is not q:
        raise ValueError(f"question {q.id!r} is already registered by {QUESTIONS[q.id].owner}")
    QUESTIONS[q.id] = q
    return q
