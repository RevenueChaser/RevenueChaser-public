"""The question registry: a question is declared once, here, and the tool runs it for whoever asked.

"Kim neresinin okunmasini istiyorsa o araca soyler" (avo, 15 Nov 2026 11:14). The service owns its questions and
names them by content (plan 2026-11-15_1722 §4.1): one :class:`Question` is added with :func:`register`, and a
board only reads the answers through ``rcdata.read.sec_reads``. None is registered yet.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, Iterable

#: The providers the asker has a pool for (``asker.POOLS``). The Grok and Claude subscription writers are being
#: removed (RevenueChaser PR 876), so the tool does not build on them.
PROVIDERS = ("evren", "deepseek")
#: Each provider's model when a question names none. DeepSeek is always its Flash model, never Pro (avo, 15 Nov
#: 2026 12:01).
DEFAULT_MODEL = {"evren": "evren-deepseek-v4.1-flash", "deepseek": "deepseek-v4-flash"}  # config.yaml names
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
    #: What decides staleness when it is not ``text`` itself: the text without its context lines, so a reclassified
    #: sector or a re-extracted customer list does not pay for the answer again (the Relatedness rule,
    #: ``module_relatedness.profiles.input_hash``).
    hash_text: str | None = None
    #: What was read (``section:business``, ``whole:120000``, ``note:DebtDisclosureTextBlock``) and the filing's form,
    #: so a fallback is visible on the answer.
    kind: str = ""
    form: str = ""
    #: The user messages, ready to send, when the question's own cut of ``text`` is not what goes out: a prompt
    #: whose every part carries the company, its context and a part label, split on headings (the Relatedness
    #: profile). Empty: ``text`` is sent in ``Question.chunk_chars`` slices.
    messages: tuple[str, ...] = ()
    #: The staleness hash, when the question computed it itself and kept no text (``Question.fill``): a run then
    #: holds one company's text at a time instead of every company's (a whole document runs to 1.4M characters).
    hash: str = ""


def _one(parts: list[tuple[dict, int]]) -> dict:
    """The default merge: the one answer, or the chunks' answers in order (their lengths are not kept)."""
    answers = [answer for answer, _chars in parts]
    return answers[0] if len(answers) == 1 else {"chunks": answers}


@dataclass(frozen=True)
class Question:
    """One question. ``scope`` names the companies, ``inputs`` their text, ``parse`` turns a reply into an answer.

    ``parse`` returns None for an unusable reply (counted as an attempt, never stored over a good answer). A text
    longer than ``chunk_chars`` is asked in chunks; ``merge`` joins the chunks' answers, each given with the length
    of the message it answered (the profile weights a segment's share by it, ``sec_profile.merge_chunks``).

    ``max_calls`` is the most calls one run sends for this question; the companies past it wait for the next run.
    A DeepSeek question must name one: a paid call is capped in its own code (``CLAUDE.md``, Keys).

    ``fill(cik, input)`` is for a question whose ``inputs`` returns inputs with a ``hash`` and no text: it returns
    that company's input with its text and messages, and is called just before the company is asked.
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
    merge: Callable[[list[tuple[dict, int]]], dict] = field(default=_one)
    chunk_chars: int = CHUNK_CHARS
    max_tokens: int = MAX_TOKENS
    max_calls: int | None = None
    fill: Callable[[str, Input], Input] | None = None

    @property
    def writer_model(self) -> str:
        return self.model or DEFAULT_MODEL[self.provider]

    def chunks(self, text: str) -> list[str]:
        """The user messages the text is sent as: the exact bytes, so the input hash is theirs."""
        n = max(1, self.chunk_chars)
        return [self.user(text[i:i + n]) for i in range(0, len(text), n)] or [self.user("")]

    def messages(self, inp: Input) -> list[str]:
        """The user messages sent for ``inp``: its own ready ones, else the chunks of its text."""
        return list(inp.messages) or self.chunks(inp.text)

    def input_hash(self, inp: Input) -> str:
        """The staleness hash: the system prompt and every chunk of ``inp.hash_text`` (of what is sent, when it
        names none), or the input's own ``hash``. The same hash, no new call."""
        if inp.hash:
            return inp.hash
        h = hashlib.sha256(self.system.encode("utf-8"))
        for chunk in self.messages(inp) if inp.hash_text is None else self.chunks(inp.hash_text):
            h.update(b"\x00" + chunk.encode("utf-8"))
        return h.hexdigest()[:32]


QUESTIONS: dict[str, Question] = {}


def register(q: Question) -> Question:
    """Add ``q`` to the registry; refused in words for an unknown provider, a Pro model or a second ``id``."""
    if q.provider not in PROVIDERS:
        raise ValueError(f"{q.id}: provider {q.provider!r} has no pool; one of {', '.join(PROVIDERS)}")
    if q.provider == "deepseek" and re.search(r"(^|[^a-z])pro($|[^a-z])", q.writer_model.lower()):
        raise ValueError(f"{q.id}: DeepSeek is always Flash, never Pro (avo, 15 Nov 2026)")
    if q.provider == "deepseek" and not q.max_calls:
        raise ValueError(f"{q.id}: a DeepSeek question needs max_calls, the most calls one run may send")
    if q.id in QUESTIONS and QUESTIONS[q.id] is not q:
        raise ValueError(f"question {q.id!r} is already registered by {QUESTIONS[q.id].owner}")
    QUESTIONS[q.id] = q
    return q
