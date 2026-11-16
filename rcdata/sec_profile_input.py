"""The text a company profile is read from: the pure half (#894).

Moved here from ``module_relatedness/engine.py`` unchanged: the SEC reading service builds the question
``company.profile`` from it (``rcdata/build/sec_reads/company_profile.py``) and the Relatedness board still imports
the same functions, so the two cannot send different bytes for one filing.
"""
from __future__ import annotations

import re

from . import sec_profile as profile_v3
from .sec_sections import MIN_ITEM_CHARS

#: The floor under which a text is not sent to the writer at all (#313): a sliced Item 1 under it is a
#: table-of-contents fragment, and a model asked from it writes the profile from the company name.
MIN_INPUT_CHARS = MIN_ITEM_CHARS


def text_status(item_text: str | None) -> str | None:
    """None when the text is long enough to profile, else why it is not: ``no_text`` or ``short_text``."""
    text = (item_text or "").strip()
    if not text:
        return "no_text"
    return "short_text" if len(text) < MIN_INPUT_CHARS else None


# ── the B input (#400 WP6; avo's decision C, 8 Nov 2026; the pilot's rounds 1-3) ────────────────────────────────
MAX_SENTENCES = 40
MAX_XBRL_CUSTOMERS = 15
_DROP_HEADINGS = re.compile(r"^\s*(available information|information about our executive officers|executive officers"
                            r"( of the registrant)?|human capital( resources| management)?|our employees|employees)\s*$",
                            re.I)
_TAGGY = re.compile(r"\b[a-z][\w-]*:[A-Za-z]\w*")
_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z])")
_KEY = re.compile(r"\b(customers?|suppliers?|vendors?|sole[- ]source|single[- ]source|concentration|"
                  r"distributors?|contract manufactur\w*|foundr(y|ies)|accounted for (approximately )?\d+|"
                  r"\d+(\.\d+)?\s?% of (our )?(total |net |consolidated )?(sales|revenues?))\b", re.I)


def clean_input(text: str) -> str:
    """The profile's text: without the sections that say nothing about the business, and without a tail of XBRL
    tags or number tables (ONEG, RCON). Pure, so ``_input_hashes`` hashes what ``_prepare`` sends."""
    secs = profile_v3._sections(text or "")
    keep = [sec for sec in secs if not _DROP_HEADINGS.match(sec.strip().splitlines()[0] if sec.strip() else "")]
    lines = "".join(keep).rstrip().split("\n")
    popped = False
    while lines:
        ln = lines[-1].replace("\u200b", "").strip()
        dense = sum(c.isdigit() or c in "¥$€£,.%()-" for c in ln) / max(len(ln.replace(" ", "")), 1)
        if ln and not _TAGGY.search(ln) and dense < 0.5:
            break
        lines.pop()
        popped = True
    # A text with nothing to drop is sent as it is, so its hash and its kept profile stay the same.
    return "\n".join(lines) if popped or len(keep) < len(secs) else (text or "")


def filing_sentences(whole: str, item: str) -> list[str]:
    """The filing's customer / supplier / concentration sentences that ``item`` does not already hold, at most 40."""
    have = re.sub(r"\s+", " ", item or "")
    out, seen = [], set()
    for sent in _SENT.split(re.sub(r"\s+", " ", whole or "")):
        sent = sent.strip()
        if not (40 <= len(sent) <= 500) or not _KEY.search(sent) or sent[:120] in have or sent.lower()[:120] in seen:
            continue
        seen.add(sent.lower()[:120])
        out.append(sent)
        if len(out) >= MAX_SENTENCES:
            break
    return out
