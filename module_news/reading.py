"""The hourly reading of the headline flow (#1234): EVREN reads the stored tape, and its reading is stored.

avo, 21 Nov 2026 (decision A on #1234): the EVREN model — no quota, no fee — reads the news stream hourly, and
**its reading is stored as fixed-schema fields where every field carries the sentence it came from**. Not a paid
model, and not free-text prose: a paragraph nobody can check is the thing this shape refuses.

The shape, and why it is this shape
-----------------------------------
One row per ``(window_end, field)`` of :data:`FIELDS` in ``boards/news.duckdb`` (``news_reading``). A field is a
**row, not a column**, so its sentence cannot be optional: every row carries ``quote`` (the sentence) and
``headline_id`` (the headline it was copied from), and :func:`store` refuses a row whose quote is empty or does
not occur in that headline. A model answer that names a headline the window did not hold, or writes a sentence of
its own, stores **nothing for that field** — it is counted in ``unsourced`` and said in the job's note. So a
stored reading is always traceable to the tape, and a reading that could not be traced is absent rather than
pretty.

The window is one clock hour, the hour that has just finished (``window_end`` is the hour boundary). A second
pass over the same hour upserts the same rows rather than writing a second reading, so the hourly timer, the
board's Fetch and a manual run cannot triple-count an hour.

What it costs
-------------
One call an hour, to the writer :mod:`core.llm_jobs` holds for the job ``news.reading`` — EVREN by default, which
has no fee and no call cap. An hour with no stored headline asks nothing at all. A paid writer is refused here
even when the Settings page names one: a scheduled pass is a standing cost, and a paid run needs avo's own word
each time (``CLAUDE.md``, Keys), so the pass stores nothing and says so unless it is started with
``allow_paid``.

Nothing here fetches a headline: the window is read from the board's own store
(:mod:`module_news.store_reads`), which the News passes fill.
"""
from __future__ import annotations

import json
import re
import time

from RevenueChaser.core import llm_jobs, llm_writers, rawstore
from RevenueChaser.module_news import store_reads

#: The LLM job id; its ``(provider, model)`` pair is the Settings choice (``core.llm_jobs``), EVREN by default.
JOB = "news.reading"
PROMPT_VERSION = "news.reading.v1"
#: The window: the clock hour that has just finished.
WINDOW_S = 3600
#: At most this many headlines go into one call, newest first (an hour of the broad tape runs to a few hundred).
MAX_HEADLINES = 200
MAX_TOKENS = 2_000
#: The longest a stored value may be; a field is a short answer, never a paragraph.
MAX_VALUE = 240
MAX_QUOTE = 400

#: The fixed schema: the field name, what it asks, and its closed value set (empty: short free text).
FIELDS: dict[str, tuple[str, tuple[str, ...]]] = {
    "tone": ("the tape's tone in this hour", ("risk_on", "risk_off", "mixed", "quiet")),
    "driver": ("the one thing moving the tape, in a few words", ()),
    "macro": ("what the macro, data or central-bank headlines said", ()),
    "rates": ("what the headlines say about yields or rate expectations", ()),
    "most_named": ("the ticker the hour named most, as a symbol", ()),
    "surprise": ("the headline of the hour that was not expected", ()),
    "watch": ("what to watch in the next hours, from these headlines alone", ()),
}

SYSTEM = (
    "You read a market news tape and fill a fixed form. You never add a field, never write a sentence of your "
    "own as evidence, and never guess. Answer with one JSON object whose keys are the form's field names. Each "
    "value is an object with three keys: \"value\" (your short answer), \"headline_id\" (the id of the one "
    "headline that shows it) and \"quote\" (that headline's own words, copied exactly, nothing added and nothing "
    "paraphrased). Leave a field out entirely when no headline in the list supports it — an omitted field is a "
    "correct answer, an unsupported one is not."
)


def window(now: float | None = None) -> tuple[float, float]:
    """``(start, end)`` of the hour that has just finished: both on the hour, so a re-run upserts its own rows."""
    end = float(int((time.time() if now is None else float(now)) // WINDOW_S) * WINDOW_S)
    return end - WINDOW_S, end


def _form() -> str:
    lines = []
    for name, (asks, choices) in FIELDS.items():
        lines.append(f"- {name}: {asks}" + (f"; value is one of {', '.join(choices)}" if choices else ""))
    return "\n".join(lines)


def prompt(rows: list[dict], start: float, end: float) -> str:
    """The one user message: the form, then the window's headlines as ``[id] (source) headline``."""
    listed = "\n".join(
        f"[{r['headline_id']}] ({r.get('source') or r.get('provider') or '?'}) {r.get('headline') or ''}"
        for r in rows)
    return (f"The form:\n{_form()}\n\n"
            f"The headlines of {int(start)}-{int(end)} (epoch seconds), newest first, "
            f"{len(rows)} of them:\n{listed}\n")


def _norm(text: str) -> str:
    """Lower case with runs of non-word characters collapsed: a quote is matched on words, not on punctuation."""
    return re.sub(r"[^0-9a-z]+", " ", str(text or "").lower()).strip()


def parse(reply: str, rows: list[dict]) -> tuple[list[dict], list[str]]:
    """``(fields, unsourced)`` from the model's reply, against the headlines it was given.

    A field is kept only when it is one of :data:`FIELDS`, its value is non-empty (and in the field's value set
    when it has one), its ``headline_id`` is one of ``rows`` and its ``quote`` really occurs in that headline.
    Everything else is named in ``unsourced`` and kept out of the store: an answer whose sentence cannot be found
    in the tape is not a reading, it is the model's own prose.
    """
    try:
        body = json.loads(reply or "")
    except ValueError:
        return [], ["the reply was not JSON"]
    if not isinstance(body, dict):
        return [], ["the reply was not a JSON object"]
    known = {str(r["headline_id"]): r for r in rows}
    out: list[dict] = []
    unsourced: list[str] = []
    for name, (_asks, choices) in FIELDS.items():
        said = body.get(name)
        if said is None:
            continue                                     # an omitted field is a correct answer
        if not isinstance(said, dict):
            unsourced.append(f"{name}: not an object")
            continue
        value = str(said.get("value") or "").strip()
        quote = str(said.get("quote") or "").strip()
        hid = str(said.get("headline_id") or "").strip()
        if not value:
            unsourced.append(f"{name}: no value")
            continue
        if choices and value not in choices:
            unsourced.append(f"{name}: {value!r} is not one of {', '.join(choices)}")
            continue
        headline = known.get(hid)
        if headline is None:
            unsourced.append(f"{name}: headline_id {hid!r} was not in the window")
            continue
        if not quote:
            unsourced.append(f"{name}: no quote")
            continue
        if _norm(quote) not in _norm(headline.get("headline") or ""):
            unsourced.append(f"{name}: the quote is not that headline's own words")
            continue
        out.append({"field": name, "value": value[:MAX_VALUE], "quote": quote[:MAX_QUOTE], "headline_id": hid,
                    "source": headline.get("source") or headline.get("provider"),
                    "published_at": headline.get("published_at")})
    return out, unsourced


def store(fields: list[dict], *, start: float, end: float, provider: str, model: str, headlines: int,
          run_id: str = "", now: float | None = None) -> int:
    """Write the hour's fields, and refuse one without its sentence.

    The refusal is a ``ValueError`` and not a dropped row on purpose: :func:`parse` is where an unsourced field is
    dropped, so a field that reaches here without a quote is a **code** mistake, and a store that quietly accepted
    it would be the end of the invariant this table exists for.
    """
    at = time.time() if now is None else float(now)
    rows = []
    for f in fields:
        if not str(f.get("quote") or "").strip() or not str(f.get("headline_id") or "").strip():
            raise ValueError(f"news_reading {f.get('field')!r}: every stored field carries the sentence it came "
                             f"from and the headline id it was copied from (#1234)")
        rows.append({"window_end": end, "field": f["field"], "window_start": start, "value": f["value"],
                     "quote": f["quote"], "headline_id": f["headline_id"], "source": f.get("source"),
                     "published_at": f.get("published_at"), "provider": provider, "model": model,
                     "prompt_version": PROMPT_VERSION, "headlines": int(headlines),
                     "run_id": run_id, "run_at": at})
    if rows:
        rawstore.write_rows(store_reads.READING, rows)
    return len(rows)


def run(*, run_id: str = "", now: float | None = None, allow_paid: bool = False) -> dict:
    """One hourly pass: read the finished hour's stored headlines, ask the writer once, store what it sourced.

    Returns the pass's own account: ``window_start``, ``window_end``, ``headlines``, ``stored``, ``unsourced``
    (the fields that were dropped, in words), ``provider``, ``model``, ``skipped`` and ``error``. It raises
    nothing a timer must handle: an hour with no headline, a paid writer and a writer that could not be reached
    are each a note, never a failed job — the pass runs 24 times a day and one bad hour is not an outage.
    """
    start, end = window(now)
    out: dict = {"window_start": start, "window_end": end, "headlines": 0, "stored": 0, "unsourced": [],
                 "provider": None, "model": None, "skipped": None, "error": None}
    rows = store_reads.headlines_in_window(start, end, MAX_HEADLINES)
    out["headlines"] = len(rows)
    if not rows:
        out["skipped"] = "no headline was stored in this hour"
        return out
    provider, model = llm_jobs.pair(JOB)
    out["provider"], out["model"] = provider, model
    if llm_writers.get(provider).paid and not allow_paid:
        out["skipped"] = (f"{provider} is a paid writer: an hourly pass is a standing cost, so it needs avo's own "
                          f"word (CLAUDE.md, Keys). Nothing was asked and nothing was stored.")
        return out
    try:
        reply = llm_jobs.client(JOB).complete(SYSTEM, prompt(rows, start, end), model=model,
                                              max_tokens=MAX_TOKENS, json_mode=True,
                                              prompt_version=PROMPT_VERSION)
    except llm_jobs.Error as exc:
        out["error"] = str(exc)
        return out
    fields, unsourced = parse(reply, rows)
    out["unsourced"] = unsourced
    out["stored"] = store(fields, start=start, end=end, provider=provider, model=model, headlines=len(rows),
                          run_id=run_id, now=now)
    return out


def latest_rows(limit_hours: int = 24, now: float | None = None) -> list[dict]:
    """The stored readings of the last ``limit_hours`` hours, newest hour first: what a reader asks for."""
    at = time.time() if now is None else float(now)
    return store_reads.readings_since(at - max(1, int(limit_hours)) * WINDOW_S)


def api_rows(hours: int = 24, now: float | None = None) -> list[dict]:
    """One object per hour, its fields inside it: the shape ``GET /api/news/reading`` and the MCP tool serve.

    Each field keeps its ``quote`` and ``headline_id``, because a reading without its sentences is the thing
    #1234 decided against.
    """
    windows: dict[float, dict] = {}
    for row in latest_rows(hours, now):
        end = float(row["window_end"])
        win = windows.setdefault(end, {"window_start": float(row["window_start"]), "window_end": end,
                                       "provider": row.get("provider"), "model": row.get("model"),
                                       "headlines": row.get("headlines"), "run_at": row.get("run_at"),
                                       "fields": {}})
        win["fields"][str(row["field"])] = {"value": row.get("value"), "quote": row.get("quote"),
                                            "headline_id": row.get("headline_id"), "source": row.get("source"),
                                            "published_at": row.get("published_at")}
    return [windows[end] for end in sorted(windows, reverse=True)]


__all__ = ["JOB", "FIELDS", "PROMPT_VERSION", "WINDOW_S", "SYSTEM", "window", "prompt", "parse", "store", "run",
           "latest_rows", "api_rows"]
