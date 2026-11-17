"""The question ``debt.note``: a company's total borrowings, read from the debt note of its newest annual report (#737).

This is the pure half: which note blocks are read, the prompt, the message and the parse. The SEC reading service
asks it (``rcdata/build/sec_reads/debt_note.py``) and the Fundamentals board reads the answer
(``module_fundamentals/debt.py`` ``note_debt``). Like ``sec_notes`` and ``sec_locator`` it imports nothing but the
standard library, so a board that reads :data:`PROMPT_VERSION` does not pay for the builder.

**Why.** A filer that tags no debt total in its facts but tags a current line only, or pays interest, has debt the
facts cannot sum, so its leverage and ROIC stay unknown. Its debt note states the total. Design: the Fable review of
16 Nov 2026 (``/mnt/project-files/RevenueChaser/fundamentals/2026-11-16_2010_debt-note-fable-review.md`` §2) and avo's
decisions of 16 Nov 20:48 (``2026-11-16_2048_debt-note-decisions.md``); IFRS 20-F filers were added to the scope on
16 Nov 23:34 ("ikisini de yap").

**The answer** keeps money as the note displays it plus its ``scale``; the model never multiplies. ``total_usd`` is
the one derived value: the total less finance leases (decision 5: reported, never counted), times the scale, filled
only for a ``stated`` answer in USD (decision 7: another currency is stored, not used).
"""
from __future__ import annotations

import json
import math
import re
from datetime import date

PROMPT_VERSION = "debt.note-1"

#: The note blocks read, by exact local name (the 13 Nov census, review §2). us-gaap first, then IFRS.
DISCLOSURES = (
    "DebtDisclosureTextBlock", "LongTermDebtTextBlock", "ShortTermDebtTextBlock",
    "ConvertibleDebtDisclosureTextBlock", "ConvertibleDebtTextBlock", "NotesPayableTextBlock",
    "NotesPayableDisclosureTextBlock", "ConvertibleNotesTextBlock", "ConvertibleNotesDisclosureTextBlock",
    "ConvertibleNotesPayableTextBlock", "ConvertibleNotesPayableDisclosureTextBlock", "LineOfCreditTextBlock",
    "LineOfCreditFacilityTextBlock", "CreditFacilitiesTextBlock", "RevolvingCreditFacilityTextBlock",
    "MortgageNotesPayableDisclosureTextBlock", "SubordinatedBorrowingsDisclosureTextBlock",
    "DisclosureOfBorrowingsExplanatory", "DisclosureOfDetailedInformationAboutBorrowingsExplanatory",
    "DisclosureOfLongTermBorrowingsExplanatory",
)
#: Read only when a company has none of :data:`DISCLOSURES`.
TABLES = ("ScheduleOfDebtTableTextBlock", "ScheduleOfDebtInstrumentsTextBlock", "ScheduleOfShortTermDebtTextBlock",
          "ScheduleOfLineOfCreditFacilitiesTextBlock", "LongTermDebtTableTextBlock", "ConvertibleDebtTableTextBlock")
#: Never read, whatever else the name says: an investment the company holds, a receivable, a maturity schedule.
DENY = ("Securities", "Investment", "Receivable", "CreditLoss", "Allowance", "TroubledDebt", "TransferOf",
        "FairValue", "Extinguishment", "Conversion", "IssuanceCost", "InterestExpense", "BorrowingCosts",
        "DebtToEquity", "Maturities")
#: The forms read. A 40-F's notes are in an exhibit the cutter does not parse (decision 3: stays unknown).
FORMS = ("10-K", "10-K/A", "10-KT", "10-KT/A", "20-F", "20-F/A")
#: One company is one call: a total cannot be merged across chunks, so a longer note is skipped, never split.
MAX_CHARS = 60_000

STATUSES = ("stated", "none_stated", "not_in_text")
SCALES = (1, 1_000, 1_000_000, 1_000_000_000)
#: Two parts that should add to a total may differ by this share (rounding in the note).
TOLERANCE = 0.01

SYSTEM = (
    "You read the debt note of a company's annual report and return its total borrowings as ONE JSON object.\n"
    "Read only the text you are given. Use the column for the balance sheet date in the header, never a prior year.\n"
    "Count only what the company OWES: notes, bonds, loans, term loans, convertible notes, commercial paper, drawn "
    "credit lines and finance lease liabilities. Never count investments it holds, receivables, guarantees, undrawn "
    "facility limits, operating leases or interest.\n"
    "Use the carrying amount (net of discount and issuance costs) when the note shows it; use principal only when no "
    "carrying amount is given. When the note already gives a total, use it; do not add its lines again.\n"
    "Give money exactly as the note displays it, with its scale (1, 1000, 1000000 or 1000000000 for \"in thousands\", "
    "\"in millions\" and so on). Never multiply, never estimate.\n"
    "Fields:\n"
    "  status: \"stated\" (a total is readable), \"none_stated\" (the note says nothing is outstanding) or "
    "\"not_in_text\" (the text gives no balances)\n"
    "  balance_date: YYYY-MM-DD, the date of the column you read\n"
    "  currency: ISO 4217 code, as the note states it\n"
    "  scale: 1, 1000, 1000000 or 1000000000\n"
    "  total_debt: number or null, all borrowings at balance_date, current plus non-current, finance leases included\n"
    "  long_term, current: numbers or null, the two parts when the note splits them\n"
    "  finance_leases: number or null, the finance lease liabilities inside total_debt\n"
    "  basis: \"carrying\" or \"principal\"\n"
    "  quote: the line or lines of the note that carry the total, verbatim, at most 300 characters\n"
    "Return JSON only."
)

_FENCE = re.compile(r"^\s*```(?:json)?\s*|\s*```\s*$", re.IGNORECASE)
_DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


def system_prompt() -> str:
    return f"{SYSTEM}\n\nPrompt version: {PROMPT_VERSION}."


def denied(local_name: str) -> bool:
    return any(word in str(local_name) for word in DENY)


def choose(rows: list[dict]) -> list[dict]:
    """The rows of one company's newest annual report that are read: its allowed top-level disclosures, else its
    allowed top-level tables, in document order. Empty when the form is not read or nothing is allowed."""
    rows = [r for r in rows if r.get("top_level") and r.get("form") in FORMS and not denied(r.get("local_name"))]
    for allowed in (DISCLOSURES, TABLES):
        picked = [r for r in rows if r.get("local_name") in allowed]
        if picked:
            return sorted(picked, key=lambda r: (str(r.get("document")), r.get("seq") or 0))
    return []


def balance_date(rows: list[dict]) -> date | None:
    """The one period end the chosen blocks share, or None when one is missing or two differ."""
    ends = {r.get("period_end") for r in rows}
    if len(ends) != 1 or None in ends:
        return None
    end = next(iter(ends))
    return end if isinstance(end, date) else date.fromisoformat(str(end)[:10])


def why_skipped(rows: list[dict]) -> str | None:
    """Why a company's chosen blocks are not sent, or None when they are: no block, no shared balance date, one name
    under two contexts with different text (a combined registrant), or a note over :data:`MAX_CHARS`."""
    if not rows:
        return "no debt note"
    if balance_date(rows) is None:
        return "no single balance date"
    texts: dict[str, set] = {}
    for r in rows:
        texts.setdefault(str(r.get("local_name")), set()).add(str(r.get("text") or "").strip())
    if any(len(t) > 1 for t in texts.values()):
        return "two registrants"
    if len(build_user("", "", rows)) > MAX_CHARS:
        return "note too long"
    return None


def build_user(name: str, form: str | None, rows: list[dict]) -> str:
    """The one message: a header, then each block once (an exact duplicate is dropped), in document order."""
    end = balance_date(rows)
    parts = [f"Company: {name}", f"Form: {form or ''}", f"Balance sheet date: {end.isoformat() if end else ''}", ""]
    seen: set[str] = set()
    for r in rows:
        text = str(r.get("text") or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        parts += [f"=== {r.get('local_name')} ===", text, ""]
    return "\n".join(parts).rstrip() + "\n"


def _num(v):
    """A finite number >= 0, None for null; ``False`` for anything else (a reply that cannot be used)."""
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0:
        return False
    return float(v)


def _close(a: float, b: float) -> bool:
    return abs(a - b) <= TOLERANCE * max(abs(a), abs(b), 1.0)


def parse(raw) -> dict | None:
    """The reply as a checked answer, or None when it cannot be used (never raises).

    Checked: a JSON object, a known status and scale, a date, a currency code, every money field a number >= 0 or
    null, ``stated`` with a total above 0, ``long_term + current`` within 1% of the total when both are given, and
    finance leases not above the total. ``not_in_text`` and ``none_stated`` are answers, not failed replies.
    """
    if isinstance(raw, str):
        raw = _FENCE.sub("", raw.strip())
    try:
        data = json.loads(raw) if isinstance(raw, str) else raw
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict) or data.get("status") not in STATUSES:
        return None
    status = data["status"]
    money = {k: _num(data.get(k)) for k in ("total_debt", "long_term", "current", "finance_leases")}
    if any(v is False for v in money.values()):
        return None
    if status != "stated":
        return {"status": status, "total_usd": None}
    scale, day = data.get("scale"), str(data.get("balance_date") or "")
    currency = str(data.get("currency") or "").strip().upper()
    if isinstance(scale, bool) or scale not in SCALES or not _DAY.match(day) or not _CURRENCY.match(currency):
        return None
    try:
        date.fromisoformat(day)
    except ValueError:
        return None
    total = money["total_debt"]
    if not total:
        return None
    if money["long_term"] is not None and money["current"] is not None \
            and not _close(money["long_term"] + money["current"], total):
        return None
    if money["finance_leases"] is not None and money["finance_leases"] > total * (1 + TOLERANCE):
        return None
    # Decision 5: finance leases are reported, never counted. A total that is only leases gives no figure.
    borrowings = total - (money["finance_leases"] or 0.0)
    return {"status": status, "balance_date": day, "currency": currency, "scale": int(scale), **money,
            "basis": "principal" if data.get("basis") == "principal" else "carrying",
            "quote": str(data.get("quote") or "")[:300],
            "total_usd": borrowings * scale if currency == "USD" and borrowings > 0 else None}
