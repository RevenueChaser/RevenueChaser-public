"""The FDA calendar without Unusual Whales (#1433 lane F; avo's option A of 23 Nov 2026: "SEC 8-K + Federal Register").

``public/fda_calendar`` asks two keyless sources in one run and stages their rows in ``fda_event``'s own shape;
``uw/fda_calendar`` builds the served table from UW's folder and this one, keyed with ``source``. No model reads
anything: the dates come from fixed patterns, and a text no pattern reads is left out and counted.

- **PDUFA dates from the companies' own 8-Ks** (``source = 'sec'``). EDGAR full-text search
  (``efts.sec.gov/LATEST/search-index``) lists the 8-K documents of the last :data:`LOOKBACK_DAYS` that say "PDUFA"
  (32 for "PDUFA target action date" in the month to 23 Nov 2026, measured from homesrv); each document is fetched
  once and kept (``raw/public/fda_calendar/docs/``), and every sentence naming a PDUFA date gives a row: the ticker
  from the filer's EDGAR name, the date and its precision (a day, or a quarter, a half, mid- or late year, as UW's
  rows already say), the product named in the sentence when one is recognisable. When a company names a new date
  for the same product, its **newest** filing wins.
- **Advisory committee meetings from the Federal Register** (``source = 'federalregister'``). FDA's "Notice of
  Meeting" notices of the last :data:`ADCOMM_LOOKBACK_DAYS`, the meeting day read from the notice's ``dates`` field
  ("The meeting will be held on October 30, 2026, ..."). A notice names its committee, not a company, so the row's
  ``ticker`` is empty and its ``drug`` is the committee.

**Both in one run**, for the reason the economic calendar gives (``econ_calendar_sources.py``): the News board
retires what its newest fetch no longer lists. A run in which either source fails keeps nothing.

Raw: ``raw/public/fda_calendar/<YYYY-MM-DD>/<HHMMSS>.json.gz`` (the search answers, the notices, and the PDUFA
sentences of every document named). Parquet: ``parquet/public/fda_calendar/date=<YYYY-MM-DD>/part-0.parquet``.
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from ...core import calendar
from . import base
from . import dirty as dirty_set
from .fundamentals import common
from .uw_fda_calendar import DAY, HALF, LATE, MID, QUARTER, SCHEMA, TABLE

NAME = "public/fda_calendar"
SOURCES = ("sec", "federalregister")
EFTS_BASE = "https://efts.sec.gov"
FEDREG_BASE = "https://www.federalregister.gov"
#: 8-Ks this far back are read: a PDUFA date is set about ten months after a filing is accepted, and companies
#: repeat it in every quarter's results release, so nine months reach every date still ahead.
LOOKBACK_DAYS = 270
#: Meeting notices this far back: FDA publishes one 15 to 60 days before the meeting.
ADCOMM_LOOKBACK_DAYS = 120
#: A catalyst whose day is this far behind the snapshot is no longer on the calendar.
KEEP_PAST_DAYS = 7
EFTS_PAGE = 100                          # EDGAR full-text search's own page size
MAX_PAGES = 30                           # 3,000 hits: far past the measured month; an answer past it is an issue
_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august", "september", "october",
           "november", "december")
#: A month written whole or cut short ("December 4, 2026", "Dec. 4, 2026", "Sept. 4, 2026").
_MONTH = r"\b(" + "|".join(f"{m[:3].capitalize()}(?:{m[3:]}|t)?" for m in _MONTHS) + r")\.?\s+(\d{1,2}),?\s+(20\d\d)"
_DAY_RE = re.compile(_MONTH)
_ORD = {"first": 1, "1st": 1, "second": 2, "2nd": 2, "third": 3, "3rd": 3, "fourth": 4, "4th": 4}
_QUARTER_RE = re.compile(r"\b(first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\s+(?:of\s+)?(20\d\d)|"
                         r"\bQ([1-4])\s*(?:of\s+)?(20\d\d)", re.I)
_HALF_RE = re.compile(r"\b(first|second|1st|2nd)\s+half\s+(?:of\s+)?(20\d\d)|\b([12])H\s*(20\d\d)", re.I)
_MID_RE = re.compile(r"\bmid-?\s?(20\d\d)", re.I)
_LATE_RE = re.compile(r"\b(?:late|end\s+of)\s+(20\d\d)", re.I)
_TICKER = re.compile(r"\(([A-Z][A-Z0-9.\-]{0,9})(?:,\s*[A-Z0-9.\-]+)*\)\s+\(CIK")
#: A product as press releases write it, tried in this order: a code (``INO-3107``, never an exhibit's ``EX-99``),
#: a brand with its generic in brackets, the word after "NDA for" / "BLA of", the word before "with a PDUFA", and
#: last a word with an international non-proprietary name's ending (``relutrigine``, ``tab-cel``).
_CODE = re.compile(r"\b(?!EX-)([A-Z]{2,6}-\d{2,6}[A-Za-z0-9-]*)\b")
_BRAND = re.compile(r"\b([A-Z][A-Za-z0-9\-]{2,})(?:®|™)?\s*\(([a-z][a-z0-9\- ]{3,})\)")
_FOR = re.compile(r"\b(?:s?NDA|s?BLA)\)?\s+(?:for|of)\s+(?:the\s+)?([A-Za-z][A-Za-z0-9\-]{3,})")
_BEFORE = re.compile(r"\b([a-z][a-z\-]{5,}),?\s+with\s+(?:a|an|the)?\s*(?:\w+\s+){0,3}?\(?PDUFA")
_INN = re.compile(r"\b([a-z][a-z\-]{2,}(?:mab|nib|tide|gene|vec|cel|sen|stat|vir|cept|igine|amide|mycin|parin|tinib|"
                  r"lisib|ciclib|parib|zole|pine|done|stim|kin|ase|tant|sertib))\b")
_NOT_A_PRODUCT = {"treatment", "patients", "approval", "review", "company", "application", "therapy", "priority"}
_STATUS = re.compile(r"\b(sNDA|sBLA|NDA|BLA)\b")


def _text(value) -> str | None:
    if value is None:
        return None
    s = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html.unescape(str(value)))).strip()
    return s or None


def day_dir(day: date) -> Path:
    return base.raw_root() / "public" / "fda_calendar" / day.isoformat()


def doc_path(adsh: str, file_name: str) -> Path:
    return base.raw_root() / "public" / "fda_calendar" / "docs" / adsh / f"{file_name}.gz"


def partition_path(day: date) -> Path:
    return base.parquet_root() / "public" / "fda_calendar" / f"date={day.isoformat()}" / "part-0.parquet"


# ── Reading a date ───────────────────────────────────────────────────────────────────────────────────────────

def target(text: str) -> tuple[date | None, str | None, str | None]:
    """The first date ``text`` names, as ``(day, precision, the words that said it)``; Nones when it names none.

    A day beats a period when both are there ("on March 15, 2027, in the first half of 2027" is the day)."""
    m = _DAY_RE.search(text)
    if m:
        try:
            month = [n[:3] for n in _MONTHS].index(m.group(1)[:3].lower()) + 1
            return (date(int(m.group(3)), month, int(m.group(2))), DAY,
                    m.group(0))
        except ValueError:
            pass
    m = _QUARTER_RE.search(text)
    if m:
        q, year = (_ORD[m.group(1).lower()], m.group(2)) if m.group(1) else (int(m.group(3)), m.group(4))
        return date(int(year), 3 * (q - 1) + 1, 1), QUARTER, m.group(0)
    m = _HALF_RE.search(text)
    if m:
        h, year = (_ORD[m.group(1).lower()], m.group(2)) if m.group(1) else (int(m.group(3)), m.group(4))
        return date(int(year), 1 if h == 1 else 7, 1), HALF, m.group(0)
    m = _MID_RE.search(text)
    if m:
        return date(int(m.group(1)), 7, 1), MID, m.group(0)
    m = _LATE_RE.search(text)
    if m:
        return date(int(m.group(1)), 10, 1), LATE, m.group(0)
    return None, None, None


def period_end(when: date, precision: str | None) -> date:
    """The last day of the span a target names: a quarter's, a half year's, mid-year's (to September) or the year's."""
    months = {QUARTER: 3, HALF: 6, MID: 3, LATE: 3}.get(precision)
    if not months:
        return when
    month = when.month + months
    return date(when.year + (month > 12), (month - 1) % 12 + 1, 1) - timedelta(days=1)


def pdufa_sentences(document: str) -> list[str]:
    """The sentences of an 8-K document (HTML or text) that name a PDUFA date."""
    text = _text(document) or ""
    # A forward-looking-statements paragraph repeats the date without saying anything new: left out.
    return [s.strip() for s in re.split(r"(?<=[.;])(?<!U\.S\.)(?<!Inc\.)\s+(?=[A-Z(\u201c\"])", text)
            if "PDUFA" in s and "forward-looking" not in s.lower() and target(s)[0] is not None][:20]


def product(sentence: str) -> str | None:
    """The product a PDUFA sentence names, or None when no pattern finds one."""
    for pattern in (_CODE, _BRAND, _FOR, _BEFORE, _INN):
        for m in pattern.finditer(sentence):
            if m.group(1).lower() not in _NOT_A_PRODUCT:
                return m.group(1)
    return None


def ticker_of(display_name: str) -> str | None:
    m = _TICKER.search(display_name or "")
    return m.group(1) if m else None


# ── The two sources' rows ────────────────────────────────────────────────────────────────────────────────────

def sec_rows(hits: list[dict], sentences: dict[str, list[str]], day: date) -> tuple[list[dict], int]:
    """A row per PDUFA sentence of the hits' documents (newest filing wins per ticker and product), and the count
    of documents with no ticker."""
    by_key: dict[tuple, dict] = {}
    no_ticker = 0
    for hit in sorted(hits, key=lambda h: (h.get("file_date") or "", h.get("doc") or "")):   # oldest first
        ticker = ticker_of((hit.get("display_names") or [""])[0])
        doc = hit.get("doc") or ""
        if ticker is None:
            no_ticker += bool(sentences.get(doc))
            continue
        for sentence in sentences.get(doc, []):
            when, precision, words = target(sentence[sentence.find("PDUFA"):])
            if when is None:
                when, precision, words = target(sentence)
                # A date before the word is only a target when it lies after the filing (not "On May 1, we...").
                if when is not None and str(when) <= str(hit.get("file_date") or ""):
                    continue
            # A period target stays until its span ends ("Q4 2026" is still ahead on 20 November).
            if when is None or period_end(when, precision) < day - timedelta(days=KEEP_PAST_DAYS):
                continue
            # No product found: one row per ticker and date, so the same date read twice is one catalyst.
            name = product(sentence) or f"PDUFA {when.isoformat()}"
            status = _STATUS.search(sentence)
            by_key[(ticker, name)] = {
                "target_date": when, "ticker": ticker, "drug": name, "target_text": words,
                "target_precision": precision, "catalyst": "PDUFA Date",
                "application_status": status.group(1) if status else None, "description": sentence[:600],
                "source_link": hit.get("url"), "source": "sec"}
    named = {(r["ticker"], r["target_date"]) for r in by_key.values() if not r["drug"].startswith("PDUFA ")}
    # A date that one sentence names with its product and another without is one catalyst, the named one.
    return [r for r in by_key.values()
            if not (r["drug"].startswith("PDUFA ") and (r["ticker"], r["target_date"]) in named)], no_ticker


def fedreg_rows(results: list[dict], day: date) -> list[dict]:
    """A row per FDA advisory committee meeting notice whose meeting is not behind the snapshot."""
    out = {}
    for r in results:
        title = _text(r.get("title")) or ""
        if "advisory committee" not in title.lower() or "notice of meeting" not in title.lower() \
                or "tobacco" in title.lower():
            continue
        when, precision, words = target(_text(r.get("dates")) or "")
        if when is None or precision != DAY or when < day - timedelta(days=KEEP_PAST_DAYS):
            continue
        committee = title.split(";", 1)[0].strip()
        out[(when, committee)] = {
            "target_date": when, "ticker": "", "drug": committee, "target_text": words, "target_precision": DAY,
            "catalyst": "Advisory Committee Meeting", "description": (_text(r.get("abstract")) or "")[:600] or None,
            "source_link": r.get("html_url"), "source": "federalregister"}
    return list(out.values())


# ── The dataset ──────────────────────────────────────────────────────────────────────────────────────────────

def _json(r) -> object:
    try:
        return json.loads(r.content.decode("utf-8-sig"))
    except ValueError as e:
        raise base.SourceError(f"{r.url}: not JSON ({e})") from e


class PublicFdaCalendar:
    name = NAME
    kind = "market"
    providers = SOURCES
    tables: tuple[str, ...] = ()
    feeds = (TABLE,)                     # ``uw/fda_calendar`` builds the table from this dataset's Parquet
    cadence = "hourly"
    starts_by_hand = True                # a new dataset starts by hand (decision F4)
    backfill_needs_from = False

    def default_as_of(self) -> date:
        return calendar.today_ny()

    def _search(self, ctx: base.RunContext, as_of: date) -> list[dict]:
        params = {"q": '"PDUFA"', "forms": "8-K", "dateRange": "custom",
                  "startdt": (as_of - timedelta(days=LOOKBACK_DAYS)).isoformat(), "enddt": as_of.isoformat()}
        hits, total = [], None
        for page in range(MAX_PAGES):
            body = _json(common.get(ctx, "sec", f"{EFTS_BASE}/LATEST/search-index",
                                    params={**params, "from": page * EFTS_PAGE}, headers=common.sec_headers(),
                                    spacing=common.sec_spacing(ctx)))
            block = (body or {}).get("hits") or {}
            total = int((block.get("total") or {}).get("value") or 0)
            got = block.get("hits") or []
            for h in got:
                src, (adsh, _, file_name) = h.get("_source") or {}, str(h.get("_id") or "").partition(":")
                cik = (src.get("ciks") or [""])[0].lstrip("0")
                if not (adsh and file_name and cik):
                    continue
                hits.append({"adsh": adsh, "file": file_name, "doc": f"{adsh}:{file_name}",
                             "display_names": src.get("display_names") or [], "file_date": src.get("file_date"),
                             "url": f"{common.sec_www()}/Archives/edgar/data/{cik}/{adsh.replace('-', '')}/{file_name}"})
            if not got or (page + 1) * EFTS_PAGE >= total:
                return hits
        ctx.issue("truncated", as_of.isoformat(), f"EDGAR full-text search: {total} hits, read {len(hits)}")
        return hits

    def _sentences(self, ctx: base.RunContext, hits: list[dict]) -> dict[str, list[str]]:
        out = {}
        for h in hits:
            path = doc_path(h["adsh"], h["file"])
            if not path.exists():                 # a filed document never changes: fetched once, kept
                r = common.sec_get(ctx, h["url"], missing_object=True)     # paced: SEC answers a burst with 429
                if r is None:
                    continue
                base.write_raw(path, r.content)
            out[h["doc"]] = pdufa_sentences(base.read_raw(path).decode("utf-8", "replace"))
        return out

    def _notices(self, ctx: base.RunContext, as_of: date) -> list[dict]:
        params = [("per_page", "100"), ("order", "newest"),
                  ("conditions[agencies][]", "food-and-drug-administration"), ("conditions[type][]", "NOTICE"),
                  ("conditions[term]", '"Advisory Committee" "Notice of Meeting"'),
                  ("conditions[publication_date][gte]", (as_of - timedelta(days=ADCOMM_LOOKBACK_DAYS)).isoformat()),
                  *(("fields[]", f) for f in ("title", "dates", "abstract", "html_url", "publication_date",
                                              "document_number"))]
        body = _json(base.http_get(ctx, "federalregister", f"{FEDREG_BASE}/api/v1/documents.json", params=params))
        results = (body or {}).get("results") if isinstance(body, dict) else None
        if not isinstance(results, list):
            raise base.SourceError("Federal Register: no results list")
        return results

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        hits = self._search(ctx, as_of)
        sentences = self._sentences(ctx, hits)
        notices = self._notices(ctx, as_of)
        if not hits:
            ctx.issue("source_empty", as_of.isoformat(), "EDGAR full-text search named no 8-K with PDUFA")
            raise base.ProviderEmpty(f"{NAME}: no 8-K hits")
        now = time.time()
        raw = day_dir(as_of) / f"{datetime.fromtimestamp(now, timezone.utc):%H%M%S}.json.gz"
        return [base.write_raw_json(raw, {"snapshot_date": as_of.isoformat(), "fetched_at": now,
                                          "run_id": ctx.run_id, "hits": hits, "sentences": sentences,
                                          "notices": notices})]

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        doc = base.read_raw_json(raw)
        day = date.fromisoformat(doc["snapshot_date"])
        sec, no_ticker = sec_rows(doc["hits"], doc["sentences"], day)
        if no_ticker:
            ctx.issue("no_ticker", day.isoformat(), f"{no_ticker} 8-K documents with a PDUFA date and no ticker")
        rows = []
        for r in sec + fedreg_rows(doc["notices"], day):
            rows.append({"snapshot_date": day, "end_date": None, "end_text": None, "indication": None,
                         "notes": None, "outcome": None, "outcome_brief": None, "has_options": None,
                         "marketcap": None, "application_status": None, **r, "source_as_of": day,
                         "fetched_at": doc["fetched_at"], "run_id": doc["run_id"]})
        if not rows:
            raise base.SourceError(f"{NAME} {day}: no catalyst ahead in {raw.name}")
        con = base.scratch_con()
        try:
            base.rows_table(con, "snap", SCHEMA, rows)
            return [base.write_parquet(con, "SELECT * FROM snap ORDER BY target_date, ticker, drug, source",
                                       partition_path(day))]
        finally:
            con.close()

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        return [p for raw in sorted(raws, key=lambda r: (r.parent.name, r.name)) for p in self.to_parquet(ctx, raw)]

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        raise base.SourceError(f"{NAME} has no history: a day's row is what the sources said on that day")

    def dirty(self, ctx: base.RunContext):
        return dirty_set.CLEAN           # builds no table: its Parquet is the calendar dataset's dirty set

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        return {}                        # the table is ``uw/fda_calendar``'s to build

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        marks = ", ".join("?" for _ in SOURCES)
        rows = int(con.execute(f"SELECT count(*) FROM {TABLE} WHERE source IN ({marks})", list(SOURCES)).fetchone()[0])
        as_of = ctx.as_of or self.default_as_of()
        return {"dataset": NAME, "result": "changed" if rows else "unchanged",
                "source_as_of": as_of.isoformat(), "rows": rows, "added": 0, "removed": 0, "coverage": None}


DATASET = PublicFdaCalendar()
