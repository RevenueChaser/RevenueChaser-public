"""The questions ``business.locate`` and ``company.profile`` (#894; plan 2026-11-15_1722 §12.3 step 2).

``company.profile`` is the structured profile of a company, read from the business section of its newest annual
report (``rcdata/sec_profile.py``, prompt ``v3d``); the Relatedness and Value Chain boards read its answer.
``business.locate`` asks where that section is, from the document's heading list, for a filing whose rule cut is
suspect (``rcdata/sec_locator.py``); only ``company.profile`` reads its answer.

**Both are registered** by ``rcdata.build`` (:func:`register_all`; the owner's word, 16 Nov 2026). The stored
Relatedness profiles are imported first (``module_relatedness/service_import.py``). Until they are, a run asks
nothing by itself: a question with no ``ok`` answer under its prompt is on its first pass, which waits for
``reread`` (``reads.stale_reason``).

What is sent is what the Relatedness board sends today for the same filing, byte for byte; a test asks both and
compares the requests (``module_relatedness/tests/test_service_profile_bytes.py``). The board's own input code stays
in ``module_relatedness/engine.py`` until the board reads the service; until then the two are kept equal by that
test.

**One company's text at a time.** ``inputs`` returns each company's staleness hash and filing, never its text
(``Input.hash``); ``fill`` reads the text of the one company being asked.

**The staleness hash** is over the text alone: the cleaned business section, or the whole document for a filing the
locator is asked about, so the locator's answer never moves it. The context lines are outside it, and so is the
company's name (the service keys a company by its CIK; a rename or another share class speaking for it asks
nothing).
"""
from __future__ import annotations

import json
import logging
import os
from dataclasses import replace

from ... import read, sec_locator, sec_profile
from ...sec_profile_input import MAX_XBRL_CUSTOMERS, clean_input, filing_sentences, text_status
from .. import base
from ..fundamentals import common
from . import asker, reads
from .questions import Input, Question, register

logger = logging.getLogger(__name__)

PROFILE_ID, LOCATE_ID = "company.profile", "business.locate"
OWNER = "sec_reads"
#: The rule version the business sections must be cut with before anything is asked: a run on another cut would be
#: paid for again once ``sec/forms`` re-cuts (``module_relatedness.config.FORMS_RULES_VERSION``).
FORMS_RULES_VERSION = "ours-2"
#: The most of a business section a profile reads, or None for no cap (the owner's choice, 13 Nov 2026).
MAX_BUSINESS_CHARS: int | None = None
#: The most of a whole document, or of a located section, a profile reads: three chunks.
MAX_FALLBACK_CHARS = 120_000
#: The cutter's labels that say the business section is in another document: never profiled from its own text and
#: never sent to the locator.
NOT_IN_DOCUMENT = ("crossref",)
#: The note blocks of the same filing the prompt is given beside the text.
NOTE_BLOCKS = (("segment_block", "SegmentReportingDisclosureTextBlock"),
               ("concentration_block", "ConcentrationRiskDisclosureTextBlock"))
MAX_SEGMENT_LINES = 15
#: Companies whose business sections one read holds at once (each is up to ~50 KB of prose).
BATCH = 200
#: Which board's universe filter the scope follows (``core.universe.BOARD_OPERATING_ONLY``).
UNIVERSE_OF = "module_relatedness"


# ── the companies ───────────────────────────────────────────────────────────────────────────────────────────────

def companies() -> dict[str, dict]:
    """``{cik: {ticker, name, sic, sector, industry}}``: one row per company of the classification universe.

    The first ticker of a company in the universe's order (cap-descending) speaks for it, as on the board, and its
    spine row gives the name and the three context values. A ticker with no CIK has no filing and is left out, and
    so is a blank check (SIC 6770): nothing is sent for one.
    """
    from ....core import universe
    tickers = universe.classification_universe(operating_only=universe.BOARD_OPERATING_ONLY[UNIVERSE_OF])
    cik_of = {str(c["ticker"]).upper(): common.norm_cik(c.get("cik")) for c in read.fundamental_companies(tickers)}
    spine = {str(r["ticker"]).upper(): r for r in read.identity(tickers)}
    out: dict[str, dict] = {}
    seen: set[str] = set()
    for t in tickers:
        cik = cik_of.get(str(t).upper())
        if not cik or cik in seen:
            continue
        seen.add(cik)
        row = spine.get(str(t).upper()) or {}
        if sec_profile.is_shell(None, row.get("sic")):
            continue
        out[cik] = {"ticker": t, "name": str(row["name"]) if row.get("name") else t,
                    **{k: row.get(k) for k in ("sic", "sector", "industry")}}
    return out


def _ready() -> None:
    """Stop the run, asking nothing, when the spine cannot name the companies or ``sec/forms`` has not built."""
    why = read.missing("spine")
    if why is None:
        try:
            read.identity(["SPY"])
        except Exception as exc:  # noqa: BLE001 - any failure is a stop, said in words
            why = f"spine read failed: {exc}"
    why = why or read.missing("sec_forms", "sec/forms")
    if why is not None:
        raise base.SourceError(f"{PROFILE_ID}: {why}; nothing is asked")


# ── the text ────────────────────────────────────────────────────────────────────────────────────────────────────

def _whole(cik: str) -> dict | None:
    return next(iter(read.form_whole([cik])), None)


def _texts(doc: dict | None, whole_of) -> dict | None:
    """What a profile reads from a company's newest annual report, before the locator: ``{text, kind, doc, whole,
    hash_text}``, or None when nothing is long enough to send.

    ``doc`` is the ``business`` row; ``whole_of()`` reads the whole document only when it is needed: the section is
    too short, is in another document (``crossref``), or its cut asks the locator. ``whole`` is that document when
    the locator is asked (never for a ``crossref``), and then the staleness text is the whole document.
    """
    text = (doc or {}).get("text") or ""
    quality = (doc or {}).get("quality")
    elsewhere = str(quality or "").split(";", 1)[0] in NOT_IN_DOCUMENT
    short = text_status(text) is not None
    whole = None
    if short or elsewhere or sec_locator.asks(quality):
        whole = whole_of()
        if whole and text_status(whole.get("text")) is not None:
            whole = None
    if not short and not elsewhere:
        capped = text if MAX_BUSINESS_CHARS is None else text[:MAX_BUSINESS_CHARS]
        out = {"text": clean_input(capped), "kind": "section:business", "doc": doc}
    elif whole:
        out = {"text": clean_input(whole["text"][:MAX_FALLBACK_CHARS]), "kind": f"whole:{MAX_FALLBACK_CHARS}",
               "doc": whole}
    else:
        return None
    out["whole"] = None if elsewhere else whole
    out["hash_text"] = "locator\n" + whole["text"] if out["whole"] else out["text"]
    return out


def _locate_message(company: dict, got: dict) -> tuple[str, list] | None:
    """``(the locator's message, the heading list)`` of ``got``'s whole document, or None with under two headings."""
    heads = sec_locator.headings(got["whole"]["text"])
    if len(heads) < 2:
        return None
    return sec_locator.build_user(company["name"], (got["doc"] or {}).get("form"), heads), heads


def _located(cik: str, company: dict, got: dict, answers: dict) -> str | None:
    """The business section the locator placed in ``got``'s whole document, or None: no answer for this heading
    list, an answer of "no section", a range outside the list, or a section too short to profile."""
    made = _locate_message(company, got)
    if made is None:
        return None
    message, heads = made
    row = answers.get((cik, LOCATE.input_hash(_headings_input(got["whole"], message))))
    try:
        answer = json.loads(row["answer"]) if row else None
    except (TypeError, ValueError):
        answer = None
    start = (answer or {}).get("start")
    if not isinstance(start, int):
        return None
    end = len(heads) if answer.get("end") is None else answer["end"]
    if not isinstance(end, int) or not 0 <= start < end <= len(heads):
        return None
    section = sec_locator.cut(got["whole"]["text"], heads, start, end)
    return section if text_status(section) is None else None


def _locate_answers() -> dict[tuple, dict]:
    """The stored ``ok`` answers of ``business.locate`` by ``(cik, input hash)``, read from the Parquet tree: the
    run writes a question's answers there before the next question builds its inputs."""
    return {(r["cik"], r["input_hash"]): r for r in reads.held(LOCATE_ID).values()
            if r["status"] == asker.OK and r["prompt_version"] == LOCATE.prompt_version}


def _resolved(cik: str, company: dict, got: dict, answers: dict) -> dict:
    """``got`` with the locator's section in place of the rule cut when there is a usable one."""
    if got["whole"] is None:
        return got
    section = _located(cik, company, got, answers)
    if section is None:
        return got
    return {**got, "text": section[:MAX_FALLBACK_CHARS], "kind": "located", "doc": got["whole"]}


# ── the context lines (in the message, never in the hash) ───────────────────────────────────────────────────────

def _segment_note(cik: str, accession: str | None) -> str:
    """The filing's segment revenue (``segment_revenue`` from ``sec/filings``) as lines, newest period only."""
    rows = read.segments(cik, source="sec/filings")
    if accession:
        rows = [r for r in rows if r.get("accession") == accession] or rows
    if not rows:
        return ""
    newest = rows[0].get("period_end")
    lines = []
    for r in rows:
        if r.get("period_end") != newest:
            continue
        value = r.get("value")
        num = f"{value:,.0f}" if isinstance(value, (int, float)) else str(value)
        lines.append(f"{r.get('axis')}: {r.get('segment')} {num} {r.get('unit') or ''}".rstrip())
        if len(lines) >= MAX_SEGMENT_LINES:
            break
    return "\n".join(lines)


def _note_block(cik: str, local_name: str) -> str:
    parts = [str(r.get("text") or "").strip() for r in read.form_notes([cik], local_name=local_name)]
    return "\n".join(p for p in parts if p).strip()


def _extras(cik: str, text: str) -> dict:
    """The filing's customer sentences that ``text`` does not hold, its two note blocks and its XBRL customers."""
    out: dict = {}
    sents = filing_sentences((_whole(cik) or {}).get("text") or "", text)
    if sents:
        out["filing_sentences"] = sents
    for key, local_name in NOTE_BLOCKS:
        try:        # each block on its own: a notes read that fails must not take the customer lines with it
            block = _note_block(cik, local_name)
        except Exception as exc:  # noqa: BLE001 - optional context, said aloud
            logger.warning("%s: no %s for cik %s: %s", PROFILE_ID, key, cik, exc)
            continue
        if block:
            out[key] = block
    rows = read.customers(cik)
    newest = rows[0].get("period_end") if rows else None
    lines = [f"{r.get('customer')}: {r['share']:.1%} of {r.get('benchmark') or 'revenue'}"
             if isinstance(r.get("share"), float) else str(r.get("customer"))
             for r in rows if r.get("period_end") == newest][:MAX_XBRL_CUSTOMERS]
    if lines:
        out["xbrl_customers"] = lines
    return out


def _context(cik: str, company: dict, got: dict) -> dict:
    """What the prompt is given beside the text. Read against the rule cut, before the locator's section replaces
    it, as the board does; each part is optional, and a read that fails gives none of it."""
    out = {k: str(company[k]) for k in ("sic", "sector", "industry") if company.get(k)}
    doc = got["doc"] or {}
    try:
        note = _segment_note(doc.get("cik") or cik, doc.get("accession"))
        if note:
            out["segment_note"] = note
    except Exception:  # noqa: BLE001 - optional context
        logger.debug("%s: no segment note for cik %s", PROFILE_ID, cik, exc_info=True)
    try:
        out.update(_extras(cik, got["text"]))
    except Exception:  # noqa: BLE001 - optional context, as the rest of it
        logger.debug("%s: no filing extras for cik %s", PROFILE_ID, cik, exc_info=True)
    return out


# ── the inputs ──────────────────────────────────────────────────────────────────────────────────────────────────

def _doc_input(doc: dict, **more) -> Input:
    """An input that names ``doc`` as the filing it came from; ``more`` are its other fields."""
    return Input(accession=str(doc.get("accession") or ""), document=str(doc.get("document") or ""),
                 filing_date=doc.get("filing_date"), report_date=doc.get("report_date"),
                 rules_version=str(doc.get("rules_version") or ""), form=str(doc.get("form") or ""), **more)


def _headings_input(whole: dict, message: str) -> Input:
    return _doc_input(whole, text=message, messages=(message,), kind="headings")


def _hash(hash_text: str) -> str:
    return PROFILE.input_hash(Input("", "", None, "", hash_text=hash_text))


def survey(ciks: list[str], comp: dict[str, dict], *, located: bool = True):
    """``(cik, got)`` for every company of ``ciks`` with something to send, its business sections read ``BATCH`` at a
    time. ``got`` is :func:`_texts`' answer, with the locator's section in place when ``located``.

    Stops the run (asking nothing) when a business row is cut with another rule version than
    :data:`FORMS_RULES_VERSION`: the check runs over every company before the first is yielded.
    """
    wanted = [c for c in ciks if c in comp]
    off: list[tuple[str, str]] = []
    for i in range(0, len(wanted), BATCH):
        for d in read.form_business(wanted[i:i + BATCH], text=False):
            if str(d.get("rules_version")) != FORMS_RULES_VERSION:
                off.append((str(d.get("cik")), str(d.get("rules_version"))))
    if off:
        raise base.SourceError(
            f"{PROFILE_ID}: {len(off)} sec/forms business sections are cut with "
            f"{', '.join(sorted({v for _c, v in off}))}, not {FORMS_RULES_VERSION} (first CIKs: "
            f"{', '.join(sorted(c for c, _v in off)[:5])}); nothing is asked")
    answers = _locate_answers() if located else {}
    for i in range(0, len(wanted), BATCH):
        batch = wanted[i:i + BATCH]
        docs = {common.norm_cik(d["cik"]): d for d in read.form_business(batch)}
        for cik in batch:
            got = _texts(docs.get(cik), lambda cik=cik: _whole(cik))
            if got is not None:
                yield cik, (_resolved(cik, comp[cik], got, answers) if located else got)


class _Profile:
    """``company.profile``'s scope, inputs and fill. ``inputs`` remembers the companies it read, so ``fill`` does
    not read the universe again for each one."""

    def __init__(self) -> None:
        self.companies: dict[str, dict] = {}

    def scope(self) -> list[str]:
        _ready()
        return list(companies())

    def inputs(self, ciks: list[str]) -> dict[str, Input]:
        _ready()
        self.companies = companies()
        return {cik: _doc_input(got["doc"], text="", kind=got["kind"], hash=_hash(got["hash_text"]))
                for cik, got in survey(ciks, self.companies)}

    def fill(self, cik: str, inp: Input) -> Input:
        company = self.companies.get(cik) or companies()[cik]
        got = _texts(next(iter(read.form_business([cik])), None), lambda: _whole(cik))
        if got is None:
            raise base.SourceError(f"{PROFILE_ID}: cik {cik} has no text any more; its sec/forms row changed "
                                   "during the run")
        context = _context(cik, company, got)
        got = _resolved(cik, company, got, _locate_answers())
        chunks = sec_profile.split_chunks(got["text"])
        messages = tuple(sec_profile.build_user(company["name"], c, context, (i, len(chunks)))
                         for i, c in enumerate(chunks))
        return replace(inp, text=got["text"], messages=messages)


def _current_profiles() -> set[tuple[str, str]]:
    """``(cik, input hash)`` of every ``ok`` profile under the current prompt version, by any writer."""
    return {(r["cik"], r["input_hash"]) for r in reads.held(PROFILE_ID).values()
            if r["status"] == asker.OK and r["prompt_version"] == PROFILE.prompt_version}


def _locate_scope() -> list[str]:
    """The companies whose cut asks the locator and whose profile is not current: a filing already profiled pays
    nothing for a heading list."""
    _ready()
    comp = companies()
    current = _current_profiles()
    return [cik for cik, got in survey(list(comp), comp, located=False)
            if got["whole"] is not None and (cik, _hash(got["hash_text"])) not in current]


def _locate_inputs(ciks: list[str]) -> dict[str, Input]:
    comp = companies()
    out: dict[str, Input] = {}
    for cik, got in survey(ciks, comp, located=False):
        made = _locate_message(comp[cik], got) if got["whole"] is not None else None
        if made is not None:
            out[cik] = _headings_input(got["whole"], made[0])
    return out


# ── the questions ───────────────────────────────────────────────────────────────────────────────────────────────

def parse_locate(raw: str) -> dict | None:
    """``{"start": n, "end": m or None}``, or ``{"start": None, "end": None}`` for "there is no business section",
    which is an answer and not a failed reply. The shape only: whether the numbers lie inside the heading list is
    checked where the section is cut (``_located``), because a reply is parsed without its input."""
    try:
        data = json.loads(sec_locator.strip_fence(raw))
    except ValueError:
        return None
    if not isinstance(data, dict) or "start" not in data:
        return None
    if data["start"] is None:
        return {"start": None, "end": None}
    start = sec_locator._int(data["start"])
    end = None if data.get("end") is None else sec_locator._int(data["end"])
    if start is None or start < 0 or (data.get("end") is not None and end is None):
        return None
    return {"start": start, "end": end}


def _merge_profile(parts: list[tuple[dict, int]]) -> dict:
    return sec_profile.merge_chunks(parts)[0] or sec_profile.empty()


_PROFILE = _Profile()

#: The writer of both questions: EVREN (the owner's K3), or DeepSeek Flash for a process started with
#: ``RC_SEC_READS_PROVIDER=deepseek`` (the owner, 16 Nov 2026: the companies the import leaves are asked through
#: DeepSeek). A stored answer of either writer is current, so switching asks nothing again.
PROVIDER = os.environ.get("RC_SEC_READS_PROVIDER", "").strip().lower() or "evren"
#: The most calls one DeepSeek run sends per question (a paid call is capped in its own code): the import left 69
#: companies, a profile is a few calls each.
DEEPSEEK_MAX_CALLS = {LOCATE_ID: 150, PROFILE_ID: 800}


def _cap(question: str) -> int | None:
    return DEEPSEEK_MAX_CALLS[question] if PROVIDER == "deepseek" else None


LOCATE = Question(
    id=LOCATE_ID, owner=OWNER, system=sec_locator.system_prompt(), prompt_version=sec_locator.PROMPT_VERSION,
    scope=_locate_scope, inputs=_locate_inputs, parse=parse_locate, max_tokens=200,
    provider=PROVIDER, max_calls=_cap(LOCATE_ID))

PROFILE = Question(
    id=PROFILE_ID, owner=OWNER, system=sec_profile.system_prompt(), prompt_version=sec_profile.PROMPT_VERSION,
    scope=_PROFILE.scope, inputs=_PROFILE.inputs, fill=_PROFILE.fill, parse=sec_profile.parse,
    merge=_merge_profile, max_tokens=8000, provider=PROVIDER, max_calls=_cap(PROFILE_ID))

#: Run order: the locator's answers are in Parquet before the profile builds its inputs.
IN_ORDER = (LOCATE, PROFILE)


def register_all() -> None:
    """Register the two questions, the locator first. ``rcdata.build`` calls it at import."""
    for q in IN_ORDER:
        register(q)
