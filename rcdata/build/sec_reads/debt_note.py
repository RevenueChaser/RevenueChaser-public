"""The question ``debt.note`` (#737): the scope and the inputs; the prompt and parse are ``rcdata/sec_debt_note.py``.

**Scope.** A company of the classification universe (``company_profile.companies``, the boards' operating-only set),
outside the two sectors the Fundamentals board never scores, whose newest annual record in the facts layer has no
``total_debt``. The debt note itself narrows it further: a company with no allowed debt block (see
``sec_debt_note.choose``), a 40-F, or a combined registrant gets a ``no_text`` row and no call. The board's own
"debt-free" reading is not repeated here: a filer that tags nothing and pays no interest seldom carries a debt
note, and when it does, the note is the better answer (``module_fundamentals.debt``: filed > note > inferred).

**Registered by ``rcdata.build``** (:func:`register_all`, after ``company_profile``'s two, so it runs last), so the
board's reader knows the current prompt version. Nothing is asked by that alone: the dataset ``starts_by_hand``, its automation is off, and a question's first pass waits for a
request that says ``reread`` (``reads._plan``, ``NEW_COMPANY_LIMIT``).

**The writer is the tool's one switch** (``questions.PROVIDER``), like ``company.profile``: EVREN, the gate with no
fee (avo, 19 Nov 2026: "Fundamentals icinde evren deepseek olmali"), unless the process names DeepSeek
(``RC_SEC_READS_PROVIDER=deepseek``), which is then capped at :data:`MAX_CALLS` calls a run with the day cap of
``reads.DAY_CAP`` on top. EVREN has neither cap (it has no quota, ``reads.UNCAPPED``). The stored answers do not
change hands: an ``ok`` answer is current whoever wrote it (``reads._text_key``), so nothing is asked again.
"""
from __future__ import annotations

import logging

from ... import read, sec_debt_note as note
from .. import base
from ..fundamentals import common
from . import company_profile
from .questions import PROVIDER, Input, Question, register

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


def _ready() -> None:
    why = (read.missing("fundamentals", "sec/companyfacts") or read.missing("sec_forms", "sec/forms"))
    if why is not None:
        raise base.SourceError(f"{ID}: {why}; nothing is asked")


def _no_total(ciks: list[str]) -> set[str]:
    """The companies of ``ciks`` whose newest filed annual record holds no ``total_debt``."""
    newest: dict[str, int] = {}
    with_total: set[tuple[str, int]] = set()
    for r in read.statements_many(ciks, 1, 0):
        if r.get("period_type") != "annual" or r.get("preliminary"):
            continue
        cik, year = common.norm_cik(r["cik"]), r.get("fiscal_year")
        if year is None:
            continue
        newest[cik] = max(newest.get(cik, year), year)
        if r.get("field") == "total_debt" and r.get("value") is not None:
            with_total.add((cik, year))
    return {cik for cik, year in newest.items() if (cik, year) not in with_total}


def scope() -> list[str]:
    _ready()
    comp = company_profile.companies()
    ciks = [c for c, row in comp.items() if row.get("sector") not in EXCLUDED_SECTORS]
    out: set[str] = set()
    for i in range(0, len(ciks), BATCH):
        out |= _no_total(ciks[i:i + BATCH])
    return sorted(out)


def _input(name: str, rows: list[dict]) -> Input | None:
    """One company's input from its newest annual report's note rows (with text), or None with the reason logged."""
    chosen = note.choose(rows)
    why = note.why_skipped(chosen)
    if why is not None:
        logger.info("%s: cik %s skipped: %s", ID, (rows or [{}])[0].get("cik"), why)
        return None
    first = chosen[0]
    message = note.build_user(name, first.get("form"), chosen)
    end = note.balance_date(chosen)
    names = "+".join(dict.fromkeys(str(r.get("local_name")) for r in chosen))
    return Input(accession=str(first.get("accession") or ""), document=str(first.get("document") or ""),
                 filing_date=first.get("filing_date"), report_date=end, text=message, messages=(message,),
                 rules_version=str(first.get("rules_version") or ""), kind=f"note:{names}@{end.isoformat()}",
                 form=str(first.get("form") or ""))


def inputs(ciks: list[str]) -> dict[str, Input]:
    """Each company's one message. The blocks are chosen on the rows without text, then only the chosen names are
    read with text, one company at a time (a filing holds ~76 blocks; its debt note is a few of them)."""
    _ready()
    comp = company_profile.companies()
    out: dict[str, Input] = {}
    for i in range(0, len(ciks), BATCH):
        by_cik: dict[str, list[dict]] = {}
        for r in read.form_notes(ciks[i:i + BATCH], text=False):
            by_cik.setdefault(common.norm_cik(r["cik"]), []).append(r)
        for cik, rows in by_cik.items():
            wanted = {str(r.get("local_name")) for r in note.choose(rows)}
            if not wanted:
                continue
            full = [r for n in sorted(wanted) for r in read.form_notes([cik], local_name=n)]
            inp = _input((comp.get(cik) or {}).get("name") or cik, full)
            if inp is not None:
                out[cik] = inp
    return out


DEBT_NOTE = Question(
    id=ID, owner=OWNER, system=note.system_prompt(), prompt_version=note.PROMPT_VERSION, scope=scope,
    inputs=inputs, parse=note.parse, provider="deepseek",
    max_calls=MAX_CALLS, chunk_chars=note.MAX_CHARS, max_tokens=1_000)


def register_all() -> None:
    """Register ``debt.note``. ``rcdata.build`` calls it at import, after ``company_profile.register_all``."""
    register(DEBT_NOTE)
