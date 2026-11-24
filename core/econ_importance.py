"""How important a calendar event is: 3 high, 2 medium, 1 low (News board plan §4; FDA rows since #807).

One tested table, shared by every board that shows the calendar. ``economic_event`` has no importance field (UW's
calendar had none, and TradingView's and the Fed's rows keep its shape, #1433), so the level comes from the event's
name and type. Matching is on whole words of the lower-cased name, so
"PPI" never reads as "CPI". The owner reviews and edits the two keyword lists below.

SPX Gamma's week card keeps its own ``vol_calendar.HIGH_IMPACT`` for now: it marks PPI high, this table marks it
medium, and moving that card onto this table would change what the card shows.
"""
from __future__ import annotations

import re

HIGH = 3
MEDIUM = 2
LOW = 1

#: Phrases (whole words, lower case) that make an event high importance.
HIGH_PHRASES = (
    "cpi", "pce", "employment report", "employment situation", "nonfarm", "non farm", "gdp", "retail sales", "ism",
    "fomc", "fed interest rate", "rate decision", "unemployment rate", "inflation rate",
)
#: Whole names that are high on their own: TradingView calls the FOMC decision just "Interest Rate".
HIGH_NAMES = (" interest rate ",)
#: Phrases that make an event medium importance when no high phrase matched.
MEDIUM_PHRASES = (
    "ppi", "jolts", "jobless claims", "consumer sentiment", "inflation expectations", "housing starts",
)

_WORDS = re.compile(r"[a-z0-9]+")


def _words(text) -> str:
    return " " + " ".join(_WORDS.findall(str(text or "").lower())) + " "


def _has(words: str, phrases) -> bool:
    return any(f" {p} " in words for p in phrases)


def importance(event, kind) -> int:
    """The level of one calendar row from its ``event`` name and UW ``type`` (report, fed-speaker, fomc)."""
    words, k = _words(event), str(kind or "").strip().lower()
    if k == "fomc" or words in HIGH_NAMES or _has(words, HIGH_PHRASES):
        return HIGH
    if k == "fed-speaker":
        is_chair = " chair " in words and " vice chair " not in words
        return HIGH if is_chair else MEDIUM
    if _has(words, MEDIUM_PHRASES):
        return MEDIUM
    return LOW


#: An FDA catalyst's words (whole words, lower case) that make the row high importance: the dates a decision or a
#: public vote actually lands on. The owner reviews and edits these two lists like the economic ones above.
FDA_HIGH_PHRASES = (
    "pdufa", "decision", "approval", "adcom", "advisory committee", "advisory comm", "complete response letter",
)
#: FDA catalysts that are medium when no high phrase matched: a read-out or a filing, not a decision day.
FDA_MEDIUM_PHRASES = (
    "data", "results", "readout", "read out", "topline", "phase 3", "phase 2", "nda", "bla", "submission",
    "filing", "interim",
)


def fda_importance(catalyst, status=None) -> int:
    """The level of one FDA calendar row (#807) from its ``catalyst`` text and, failing that, its ``status``.

    UW's FDA calendar has no importance field either (``rcdata/build/uw_fda_calendar.py``), so the level comes from
    the words of the catalyst: a PDUFA date or an advisory-committee meeting is a date the market trades, a trial
    read-out or an application is medium, anything else low. First cut of #807; the lists above are the owner's to
    edit, like ``HIGH_PHRASES``.
    """
    words = _words(catalyst) if _words(catalyst).strip() else _words(status)
    if _has(words, FDA_HIGH_PHRASES):
        return HIGH
    if _has(words, FDA_MEDIUM_PHRASES):
        return MEDIUM
    return LOW


def dots(level: int) -> str:
    """The level as three dots, filled from the left: ``●●○`` for medium."""
    n = max(LOW, min(HIGH, int(level)))
    return "●" * n + "○" * (HIGH - n)
