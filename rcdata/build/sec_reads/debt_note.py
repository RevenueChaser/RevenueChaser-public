"""The question ``debt.note`` (#737): the scope and the inputs; the prompt and parse are ``rcdata/sec_debt_note.py``.

**Scope** (avo, 16 Nov 2026, decision 1, kept on 24 Nov 2026 23:43, card D2 "A"). A company of the classification
universe (``company_profile.companies``, the boards' operating-only set), outside the two sectors the Fundamentals
board never scores, whose newest annual record in the facts layer has no ``total_debt``, tags no long-term or whole
debt line (:data:`NONCURRENT_LINES`; those wait for #830's fallback flag) and **either** tags a current or short-term
line (:data:`CURRENT_LINES`) **or** reports interest above :data:`INTEREST_FLOOR_USD`. Measured 25 Nov 2026 on homesrv
(review plan step 2): of 971 ``no_text`` companies under the old, wider scope, 668 tagged nothing and paid no
interest and 108 had a total by then, so their missing note was the right answer. The debt note narrows it further:
a company with no allowed debt block (see ``sec_debt_note.choose``), a 40-F, or a combined registrant gets a
``no_text`` row and no call.

**Registered by ``rcdata.build``** (:func:`register_all`, after ``company_profile``'s two, so it runs last), so the
board's reader knows the current prompt version. Nothing is asked by that alone: the dataset ``starts_by_hand``, its automation is off, and a question's first pass waits for a
request that says ``reread`` (``reads._plan``, ``NEW_COMPANY_LIMIT``).

**The writer is this question's own choice** on the Settings page (``core.llm_jobs``, #404), like
``company.profile``; its default is the tool's switch ``questions.PROVIDER``: EVREN, the gate with no
fee (avo, 19 Nov 2026: "Fundamentals icinde evren deepseek olmali"), unless the process names DeepSeek
(``RC_SEC_READS_PROVIDER=deepseek``), which is then capped at :data:`MAX_CALLS` calls a run with the day cap of
``reads.DAY_CAP`` on top. EVREN has neither cap (it has no quota, ``reads.UNCAPPED``). The stored answers do not
change hands: an ``ok`` answer is current whoever wrote it (``reads._text_key``), so nothing is asked again.
"""
from __future__ import annotations

import logging

from ... import read, sec_debt_note as note
from .. import base
from ..fundamentals import common, facts
from . import company_profile
from .questions import Input, Question, register, writer_for

logger = logging.getLogger(__name__)

ID = "debt.note"
OWNER = "module_fundamentals"
#: ``module_fundamentals.config.EXCLUDED_SECTORS``: the board drops them before EDGAR is read, and a bank's
#: "debt" note is not this number. Copied, not imported: ``rcdata`` imports no board module.
EXCLUDED_SECTORS = ("Financial Services", "Real Estate")
#: The most calls one DeepSeek run sends; the rest wait for the next run. EVREN is uncapped, like the other two
#: questions, because it has no quota (avo, 16 Nov 2026).
MAX_CALLS = 200
#: Companies whose note rows one read holds at once.
BATCH = 200
#: Decision 1's lines. A current or short-term line alone gives no total (``facts`` docstring), so its filer owes an
#: amount the facts cannot sum. ``rcdata`` imports no board module, so the floor and the interest labels are copied
#: from ``module_fundamentals.debt`` (``INTEREST_FLOOR_USD``, ``INTEREST_FIELDS``).
CURRENT_LINES = ("debt_current", "lt_debt_current", "short_term_borrowings", "convertible_debt_current") \
    + facts.FALLBACK_CURRENT_DEBT + facts.FALLBACK_SHORT_TERM_DEBT
NONCURRENT_LINES = tuple(f for f in facts.DEBT_LINES if f not in CURRENT_LINES) \
    + facts.FALLBACK_WHOLE_DEBT + facts.FALLBACK_LONG_TERM_DEBT
INTEREST_FIELDS = ("interest_expense", "interest_expense_borrowings", "interest_expense_other")
INTEREST_FLOOR_USD = 100_000.0


def _ready() -> None:
    why = (read.missing("fundamentals", "sec/companyfacts") or read.missing("sec_forms", "sec/forms"))
    if why is not None:
        raise base.SourceError(f"{ID}: {why}; nothing is asked")


def _in_scope(fields: dict) -> bool:
    """Decision 1 on one newest annual record (``{field: value}``): no total, no non-current line, and a current or
    short-term line or interest above the floor."""
    if fields.get("total_debt") is not None or any(fields.get(f) is not None for f in NONCURRENT_LINES):
        return False
    return any(fields.get(f) is not None for f in CURRENT_LINES) \
        or any((v := fields.get(f)) is not None and v > INTEREST_FLOOR_USD for f in INTEREST_FIELDS)


def _no_total(ciks: list[str]) -> set[str]:
    """The companies of ``ciks`` whose newest filed annual record is in decision 1's scope (:func:`_in_scope`)."""
    newest: dict[str, int] = {}
    fields: dict[tuple[str, int], dict] = {}
    for r in read.statements_many(ciks, 1, 0):
        if r.get("period_type") != "annual" or r.get("preliminary"):
            continue
        cik, year = common.norm_cik(r["cik"]), r.get("fiscal_year")
        if year is None:
            continue
        newest[cik] = max(newest.get(cik, year), year)
        if r.get("value") is not None:
            fields.setdefault((cik, year), {})[r.get("field")] = float(r["value"])
    return {cik for cik, year in newest.items() if _in_scope(fields.get((cik, year), {}))}


def scope() -> list[str]:
    _ready()
    comp = company_profile.companies()
    ciks = [c for c, row in comp.items() if row.get("sector") not in EXCLUDED_SECTORS]
    out: set[str] = set()
    for i in range(0, len(ciks), BATCH):
        out |= _no_total(ciks[i:i + BATCH])
    return sorted(out)


#: A company with no ``form_notes`` row at all: it filed no annual report this service has read.
NO_ROWS = "no note rows"
#: Its rows hold no form :data:`sec_debt_note.FORMS` reads (a 40-F filer, say).
NO_ANNUAL_FORM = "no annual form"
#: Its annual rows are all nested inside another block.
NO_TOP_LEVEL = "no top-level note"
#: Its top-level annual blocks are all on :data:`sec_debt_note.DENY`, or none carries a name
#: :func:`sec_debt_note.choose` reads (``DISCLOSURES`` or ``TABLES``).
NO_ALLOWED_NAME = "no allowed note name"


def _why_nothing_chosen(rows: list[dict]) -> str:
    """Why :func:`sec_debt_note.choose` picked nothing from a company's rows. ``choose`` drops a row before
    ``why_skipped`` can judge it, so the three pre-choice reasons are named from the rows themselves."""
    if not any(r.get("form") in note.FORMS for r in rows):
        return NO_ANNUAL_FORM
    if not any(r.get("top_level") and r.get("form") in note.FORMS for r in rows):
        return NO_TOP_LEVEL
    return NO_ALLOWED_NAME


def _input(name: str, rows: list[dict]) -> Input | str:
    """One company's input from its newest annual report's note rows (with text), or the reason it has none.

    The reason used to go to the log alone, where no row and no count could reach it (#1419); it is returned now
    and stored on the company's ``no_text`` row. It is still logged, because the log is read while a run goes on.
    """
    chosen = note.choose(rows)
    why = note.why_skipped(chosen)
    if why is not None:
        logger.info("%s: cik %s skipped: %s", ID, (rows or [{}])[0].get("cik"), why)
        return why
    first = chosen[0]
    message = note.build_user(name, first.get("form"), chosen)
    end = note.balance_date(chosen)
    names = "+".join(dict.fromkeys(str(r.get("local_name")) for r in chosen))
    return Input(accession=str(first.get("accession") or ""), document=str(first.get("document") or ""),
                 filing_date=first.get("filing_date"), report_date=end, text=message, messages=(message,),
                 rules_version=str(first.get("rules_version") or ""), kind=f"note:{names}@{end.isoformat()}",
                 form=str(first.get("form") or ""))


def inputs(ciks: list[str]) -> tuple[dict[str, Input], dict[str, str]]:
    """``(each company's one message, why a company has none)``. The blocks are chosen on the rows without text,
    then only the chosen names are read with text, one company at a time (a filing holds ~76 blocks; its debt note
    is a few of them).

    Every company without an input names its reason (#1419). Three of them come before a note is chosen, and
    ``sec_debt_note.why_skipped`` cannot tell them apart, because :func:`sec_debt_note.choose` has already dropped
    the rows it would have judged: no note row at all, no annual form among them, and no top-level block. Naming
    them here keeps the stored reasons a vocabulary the backlog can be counted by (Grok round 1, 26 Nov 2026);
    ``why_skipped``'s own words carry the rest.
    """
    _ready()
    comp = company_profile.companies()
    out: dict[str, Input] = {}
    whys: dict[str, str] = {}
    for i in range(0, len(ciks), BATCH):
        by_cik: dict[str, list[dict]] = {}
        for r in read.form_notes(ciks[i:i + BATCH], text=False):
            by_cik.setdefault(common.norm_cik(r["cik"]), []).append(r)
        for cik in ciks[i:i + BATCH]:
            if common.norm_cik(cik) not in by_cik:
                whys[common.norm_cik(cik)] = NO_ROWS
        for cik, rows in by_cik.items():
            chosen = note.choose(rows)
            wanted = {str(r.get("local_name")) for r in chosen}
            if not wanted:
                whys[cik] = _why_nothing_chosen(rows)
                continue
            full = [r for n in sorted(wanted) for r in read.form_notes([cik], local_name=n)]
            inp = _input((comp.get(cik) or {}).get("name") or cik, full)
            if isinstance(inp, str):
                whys[cik] = inp
            else:
                out[cik] = inp
    return out, whys


DEBT_NOTE = Question(
    id=ID, owner=OWNER, system=note.system_prompt(), prompt_version=note.PROMPT_VERSION, scope=scope,
    inputs=inputs, parse=note.parse, provider=writer_for(ID)[0], model=writer_for(ID)[1],
    max_calls=MAX_CALLS if writer_for(ID)[0] == "deepseek" else None, chunk_chars=note.MAX_CHARS, max_tokens=1_000)


def register_all() -> None:
    """Register ``debt.note``. ``rcdata.build`` calls it at import, after ``company_profile.register_all``."""
    register(DEBT_NOTE)
