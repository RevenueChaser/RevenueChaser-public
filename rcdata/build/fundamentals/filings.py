"""``sec/filings``: each Tier A company's filing list (8-K items) and the documents the SEC form reader cuts.

**The filing list.** ``GET <RC_SEC_DATA_BASE>/submissions/CIK<10 digits>.json`` (``filings.recent``: accession, form,
filing and report dates, primary document, 8-K items), re-read when the SEC daily index (``sec_index.py``) shows the
company filed anything the stored list does not hold (the index read back to the day after the last whole run when
that is longer ago than a week, ``sec_index.lookback``), and for a Tier A company never read, up to ``NEW_PER_RUN`` a
run. The day each list was read is served (``fundamental_company.submissions_as_of``), so "no 8-K event" can be told
from "not read lately" (the Fundamentals review's F2).

**The documents.** The primary document of the newest annual report (10-K, else 20-F, else 40-F) and of the newest
proxy (DEF 14A), plus a 40-F's Annual Information Form exhibits, fetched once each (the raw file is the resume
marker) and stored on disk.

**This layer no longer cuts them (#858).** It did: ``document_sections`` sliced the business section with the Value
Chain board's splitter and stored ``whole``, ``proxy``, ``business`` and ``aif`` as ``filing_item``'s
``kind = 'document'`` rows - a second cut of the very documents ``sec/forms`` cuts, by the same rule, in a second
table, with the cap and the ``capped`` label of whichever version that board pinned. One cutter now: ``sec/forms``
reads these stored documents and serves ``filing_section`` with ``rules_version`` on every row, and
``rcdata.read.filing_text`` / ``filing_documents`` / ``filing_texts`` read that table. What stays here is the
filing list, the 8-K items, and the annual report's inline XBRL (``ixbrl.py``), which is read from the primary
document and is not a cut.

Requests go through the shared SEC bucket and are counted under ``sec``. Backfill: every Tier A company with no
filing list yet, and its two documents, resumable.

Raw: ``raw/sec/filings/submissions/<cik>/<as-of>.json.gz`` (with a ``.meta.json``: the accessions it holds) and
``raw/sec/filings/documents/<cik>/<accession>.html.gz``. Parquet: ``parquet/sec/filings/cik=<cik>/filings.parquet``
(one row per filing and 8-K item), ``.../segments.parquet`` / ``.../customers.parquet`` (the annual report's inline
XBRL, ``ixbrl.py``: revenue by segment, product and country, and major customers' shares), each replaced whole from
the newest list, and ``.../header.parquet`` (the list's company header: SEC SIC, state of incorporation, the
business address's state and country; #645 G2, the fundamentals freeze). ``documents.parquet`` is no longer
written; the files an earlier build left behind are read by nothing and are removed on the owner's word.

Staging: ``stg_sec_filings``, ``stg_sec_segments``, ``stg_sec_customers``, ``stg_sec_header``.
"""
from __future__ import annotations

import re
import time
from datetime import date, timedelta
from pathlib import Path

import duckdb

from ....core import calendar
from .. import base
from .. import dirty as dirty_set
from . import KIND, common, edgar_codes, ixbrl, sec_index

NAME = "sec/filings"
NEW_PER_RUN = 9000
ANNUAL_FORMS = ("10-K", "10-KT", "20-F", "40-F")             # newest by filing date; a 10-K first on one day
PROXY_FORMS = ("DEF 14A",)
#: How many AIF exhibits of one 40-F are kept. shortcut: one filing has never been seen with more than one, so the
#: largest is taken; upgrade the number if a filer splits its Annual Information Form across exhibits.
_AIF_PER_FILING = 1
#: This dataset cuts nothing since #858: the one cutter is ``sec/forms``, which reads the very documents fetched
#: here and serves ``filing_section``. What went with it: ``document_sections`` (``whole``, ``proxy``,
#: ``business``, ``aif``), the ``kind = 'document'`` rows of ``filing_item``, the ``capped`` label, and the cap
#: constants this layer borrowed from the Value Chain board (``caps_text``, ``max_text_chars``), so
#: ``module_value_chain/splitter.py``'s pin no longer reaches the fundamentals build at all. The documents
#: themselves are still fetched and stored on disk, by :meth:`Filings.fetch` and :func:`read_exhibits` - that is
#: what ``sec/forms`` cuts.
STAGING = {"filings": "stg_sec_filings", "segments": "stg_sec_segments",
           "customers": "stg_sec_customers", "header": "stg_sec_header"}

FILING = [("cik", "TEXT"), ("accession", "TEXT"), ("form", "TEXT"), ("filing_date", "DATE"), ("report_date", "DATE"),
          ("primary_document", "TEXT"), ("item", "TEXT"), ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"),
          ("run_id", "TEXT")]
# The annual report's inline XBRL (``ixbrl.py``): revenue by segment, product and country, and major customers.
_FILED = [("cik", "TEXT"), ("accession", "TEXT"), ("form", "TEXT"), ("filing_date", "DATE")]
_STAMPS = [("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]
SEGMENT = _FILED + [("axis", "TEXT"), ("member", "TEXT"), ("segment", "TEXT"), ("concept", "TEXT"),
                    ("value", "DOUBLE"), ("unit", "TEXT"), ("period_start", "DATE"), ("period_end", "DATE")] + _STAMPS
# The company header of the newest list: SIC as the SEC assigns it, the state (or country) of incorporation as EDGAR
# codes it, and the business address as a state (US, Canada) and an ISO country (``edgar_codes``).
HEADER = [("cik", "TEXT"), ("sic", "TEXT"), ("sic_description", "TEXT"), ("state_of_incorporation", "TEXT"),
          ("state_of_incorporation_description", "TEXT"), ("business_state", "TEXT"),
          ("business_country", "TEXT")] + _STAMPS
CUSTOMER = _FILED + [("customer", "TEXT"), ("member", "TEXT"), ("benchmark", "TEXT"), ("share", "DOUBLE"),
                     ("period_start", "DATE"), ("period_end", "DATE")] + _STAMPS


def min_text_chars() -> int:
    from ....module_value_chain import config
    return int(config.MIN_ITEM_CHARS)


def submissions_url(cik: str) -> str:
    return f"{common.sec_data()}/submissions/CIK{common.cik10(cik)}.json"


def document_url(cik: str, accession: str, primary: str) -> str:
    return f"{common.sec_www()}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{primary}"


def _subs_dir(cik: str) -> Path:
    return common.raw_dir(NAME) / "submissions" / str(cik)


def _doc_path(cik: str, accession: str) -> Path:
    return common.raw_dir(NAME) / "documents" / str(cik) / f"{accession}.html.gz"


def _exhibit_path(cik: str, accession: str, name: str) -> Path:
    return common.raw_dir(NAME) / "documents" / str(cik) / f"{accession}.{name}.gz"


def index_url(cik: str, accession: str) -> str:
    """The filing's own file listing. Only a 40-F needs it: every other form this layer reads keeps what it wants
    in the primary document."""
    return f"{common.sec_www()}/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/index.json"


#: An exhibit of a 40-F whose name says it is the Annual Information Form -- the Canadian filing that carries the
#: business description when the 40-F itself does not. Measured on two real filings (5 Nov 2026): Brookfield files
#: it as ``a2025-40xfex991aif.htm`` while Canadian Natural writes everything into the primary document, so both
#: shapes exist and the primary document is fetched either way.
#: An ``ex99`` alone is not enough. Brookfield's 40-F (read 5 Nov 2026) files 99.1 as the Annual Information
#: Form, 99.2 as the financial statements and 99.3 as the MD&A, and the statements are the largest of the three --
#: so "the biggest ex99" picks the wrong one. A name that says ``aif`` is taken first; only when none does is
#: ``99.1`` taken, by its number.
#: shortcut: three named limits. (1) The name is the only signal, because ``index.json`` carries no reliable
#: exhibit *type*; upgrade by reading the filing's ``<CIK>-index.htm`` description column. (2) The 99.1/99.2/99.3
#: order is **one filer's** layout, not a rule of the form. (3) Only ``.htm`` and ``.html`` are considered, so a
#: filer who files the AIF as a PDF is missed (``read_exhibits`` raises ``aif_not_named`` when it can tell).
#: #751 (measured 12 Nov 2026 on the 49 40-Fs with no exhibit stored): 25 name 99.1 ``…xex99d1.htm`` (or
#: ``ex99z1``), and 10 spell the form out (``a2025annualinformationform.htm``, ``ballard993123125annualinfo.htm``).
_AIF_NAME = re.compile(r"aif|annual[-_]?info", re.I)
_EX_99_1 = re.compile(r"ex(?:hibit)?[-_]?99[._dz-]?1(?![0-9])", re.I)
_EX_1 = re.compile(r"(?<![a-z])d?ex(?:hibit)?[-_]?0?1(?![0-9-])", re.I)     # RY files its AIF as Exhibit 1, dex1.htm (#400 WP3)
_EX_99_ANY = re.compile(r"ex(?:hibit)?[-_]?99", re.I)


def stored_exhibits(cik: str, accession: str, primary: str | None = None) -> list[Path]:
    """The AIF exhibit files fetched for one filing, in the order :func:`aif_exhibits` chose them.

    Read from the stored ``index.json`` rather than guessed from file names: the fallback branch picks a name with
    no ``aif`` in it (``ex99-1.htm``), which a name filter cannot find again -- so the exhibit was fetched, stored,
    and never typed.
    """
    index = _exhibit_path(cik, accession, "index.json")
    if not index.exists():
        return []
    names = aif_exhibits(base.read_raw_json(index), primary)[:_AIF_PER_FILING]
    return [pth for pth in (_exhibit_path(cik, accession, name) for name in names) if pth.exists()]


def aif_exhibits(listing: dict, primary: str | None = None) -> list[str]:
    """The names of a 40-F's Annual Information Form exhibits in its ``index.json``, largest first; [] when none.

    A name that says ``aif`` wins outright. Only when no name does is ``99.1`` taken, so the statements exhibit
    (99.2) and the MD&A (99.3) are never mistaken for the business description. ``primary`` is left out: the
    index lists the 40-F itself, which is already read as the document, and a primary named like an AIF would
    otherwise be fetched and typed twice.
    """
    items = ((listing or {}).get("directory") or {}).get("item") or []
    pages = [(int(i.get("size") or 0), str(i.get("name") or "")) for i in items
             if str(i.get("name") or "").lower().endswith((".htm", ".html")) and str(i.get("name")) != primary]
    return [name for _, name in sorted(_chosen(pages), reverse=True)]


def _chosen(pages: list[tuple[int, str]]) -> list[tuple[int, str]]:
    named = [(size, name) for size, name in pages if _AIF_NAME.search(name)]
    return (named or [(size, name) for size, name in pages if _EX_99_1.search(name)]
            or [(size, name) for size, name in pages if _EX_1.search(name)])


def picked_by_name(listing: dict, name: str, primary: str | None = None) -> bool:
    """True when ``name`` was chosen because it says ``aif``, False when only its number chose it.

    The number is one filer's layout and not a rule of the form, so a by-number pick is a guess: a filer who
    keeps the Annual Information Form in the primary document and files its statements as 99.1 would get an
    ``aif`` row that is the statements. Carried onto the row's ``quality`` so the guesses can be counted.
    """
    return bool(_AIF_NAME.search(name))


def missed_exhibits(listing: dict, primary: str | None = None) -> int:
    """How many ``ex99`` pages the filing has when :func:`aif_exhibits` chose none -- the one case this can tell
    apart from "the AIF is in the primary document", and worth an issue rather than silence."""
    if aif_exhibits(listing, primary):
        return 0
    items = ((listing or {}).get("directory") or {}).get("item") or []
    return sum(1 for i in items if _EX_99_ANY.search(str(i.get("name") or "")))


def _subs_raws(cik: str) -> list[Path]:
    folder = _subs_dir(cik)
    return sorted(folder.glob("*.json.gz")) if folder.is_dir() else []


def _newest_list(cik: str) -> date | None:
    raws = _subs_raws(cik)
    return date.fromisoformat(raws[-1].name.split(".", 1)[0]) if raws else None


def _held(cik: str) -> set[str]:
    raws = _subs_raws(cik)
    return set(base.read_raw_json(common.meta_path(raws[-1])).get("accessions") or []) if raws else set()


def parse(cik: str, body: dict) -> list[dict]:
    """The filings of one submissions answer (``filings.recent``): ``{cik, accession, form, filing_date,
    report_date, primary_document, items}``; ``SourceError`` for a body that is not the documented shape."""
    if not isinstance(body, dict) or not isinstance((body.get("filings") or {}).get("recent"), dict):
        raise base.SourceError(f"sec submissions {cik}: not the documented shape")
    recent = body["filings"]["recent"]
    c = str(int(str(cik).strip()))

    def col(name: str, i: int):
        vals = recent.get(name) or []
        return vals[i] if i < len(vals) else None

    def text(v) -> str | None:
        v = None if v is None else str(v).strip()
        return v or None

    def day(v) -> date | None:
        try:
            return date.fromisoformat(str(v)[:10])
        except (TypeError, ValueError):
            return None

    rows = []
    for i, acc in enumerate(recent.get("accessionNumber") or []):
        acc = text(acc)
        if acc:   # a row without an accession is dropped
            rows.append({"cik": c, "accession": acc, "form": text(col("form", i)),
                         "filing_date": day(col("filingDate", i)), "report_date": text(col("reportDate", i)),
                         "primary_document": text(col("primaryDocument", i)), "items": text(col("items", i))})
    return rows


def header(cik: str, body: dict) -> dict:
    """The company header of one submissions answer (``HEADER``'s columns, no stamps); a missing key is None."""
    address = ((body.get("addresses") or {}).get("business") or {}).get("stateOrCountry")
    return {"cik": cik, "sic": str(body.get("sic") or "").strip() or None,
            "sic_description": body.get("sicDescription") or None,
            "state_of_incorporation": body.get("stateOfIncorporation") or None,
            "state_of_incorporation_description": body.get("stateOfIncorporationDescription") or None,
            "business_state": edgar_codes.state(address), "business_country": edgar_codes.country(address)}


def pick(rows: list[dict], forms: tuple[str, ...]) -> dict | None:
    """The newest filing of ``forms`` by filing date (on one day the earlier form in ``forms``); an amendment never
    counts (as Value Chain's ``pick_filing``)."""
    best, best_rank = None, None
    for r in rows:
        if r["form"] not in forms or not r.get("primary_document"):
            continue
        rank = (str(r["filing_date"]), -forms.index(r["form"]))
        if best is None or rank > best_rank:
            best, best_rank = r, rank
    return best


def read_list(ctx: base.RunContext, cik: str, as_of: date) -> Path | None:
    raw = _subs_dir(cik) / f"{as_of.isoformat()}.json.gz"
    if raw.exists():
        return raw
    r = common.sec_get(ctx, submissions_url(cik), missing=(404,))
    if r is None:
        ctx.issue("no_submissions", cik, "the SEC answered 404 for the filing list")
        return None
    try:
        body = r.json()
    except ValueError as e:
        raise base.SourceError(f"sec submissions {cik}: the answer is not JSON") from e
    rows = parse(cik, body)
    base.write_raw_json(common.meta_path(raw), {"cik": cik, "as_of": as_of.isoformat(), "fetched_at": time.time(),
                                                "run_id": ctx.run_id, "url": submissions_url(cik),
                                                "accessions": sorted(r["accession"] for r in rows)})
    return base.write_raw_json(raw, body)


def read_documents(ctx: base.RunContext, cik: str, raw: Path, as_of: date) -> int:
    """Fetch the newest annual report and proxy of the list in ``raw`` that are not stored yet; how many fetched."""
    rows = parse(cik, base.read_raw_json(raw))
    fetched = 0
    for forms in (ANNUAL_FORMS, PROXY_FORMS):
        f = pick(rows, forms)
        if f is None:
            continue
        path = _doc_path(cik, f["accession"])
        if not path.exists():
            url = document_url(cik, f["accession"], f["primary_document"])
            r = common.sec_get(ctx, url, missing_object=True)  # /Archives/: a missing document answers 403
            if r is None:
                ctx.issue("document_missing", f"{cik}:{f['accession']}",
                          f"the archive holds no {f['primary_document']}")
            else:
                base.write_raw_json(common.meta_path(path), {"cik": cik, "accession": f["accession"],
                                                             "form": f["form"], "as_of": as_of.isoformat(),
                                                             "url": url, "fetched_at": time.time(),
                                                             "run_id": ctx.run_id})
                base.write_raw(path, r.content)
                fetched += 1
        # A 40-F may keep its business description in an Annual Information Form exhibit instead of the primary
        # document (``aif_exhibits``), and the primary document is now read either way.
        if f["form"] == "40-F":
            fetched += read_exhibits(ctx, cik, f, as_of)
    return fetched


def read_exhibits(ctx: base.RunContext, cik: str, f: dict, as_of: date) -> int:
    """Fetch a 40-F's AIF exhibits that are not stored yet; how many were fetched. One index request per filing."""
    first = _exhibit_path(cik, f["accession"], "index.json")
    if first.exists():
        listing = base.read_raw_json(first)
    else:
        r = common.sec_get(ctx, index_url(cik, f["accession"]), missing_object=True)
        if r is None:
            ctx.issue("index_missing", f"{cik}:{f['accession']}", "the archive holds no index.json")
            return 0
        listing = r.json()
        base.write_raw_json(first, listing)
    missed = missed_exhibits(listing, f.get("primary_document"))
    if missed:
        ctx.issue("aif_not_named", f"{cik}:{f['accession']}",
                  f"{missed} ex99 page(s) and none named an Annual Information Form")
    fetched = 0
    for name in aif_exhibits(listing, f.get("primary_document"))[:_AIF_PER_FILING]:
        path = _exhibit_path(cik, f["accession"], name)
        if path.exists():
            continue
        url = document_url(cik, f["accession"], name)
        r = common.sec_get(ctx, url, missing_object=True)
        if r is None:
            ctx.issue("document_missing", f"{cik}:{f['accession']}:{name}", f"the archive holds no {name}")
            continue
        base.write_raw_json(common.meta_path(path), {"cik": cik, "accession": f["accession"], "form": f["form"],
                                                     "exhibit": name, "by_name": picked_by_name(listing, name),
                                                     "as_of": as_of.isoformat(), "url": url,
                                                     "fetched_at": time.time(), "run_id": ctx.run_id})
        base.write_raw(path, r.content)
        fetched += 1
    return fetched


class Filings:
    name = NAME
    kind = KIND
    providers = (common.SEC,)
    tables: tuple[str, ...] = ()
    cadence = "daily"
    backfill_needs_from = False
    starts_by_hand = True

    def default_as_of(self) -> date:
        return calendar.today_ny()

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        companies = common.ciks(common.universe())
        if not companies:
            ctx.notes.append("no Tier A companies yet (no spine file)")
            return []
        filed: dict[str, set[str]] = {}
        days = sec_index.lookback(ctx, NAME, as_of, lambda: min(filter(None, map(_newest_list, companies)),
                                                                default=None))
        for f in sec_index.filings(ctx, as_of, ciks=set(companies), lookback=days):
            filed.setdefault(f["cik"], set()).add(f["accession"])
        due = sorted((c for c, accs in filed.items() if accs - _held(c)), key=int)
        new = [c for c in companies if c not in due and not _subs_raws(c)]
        out, docs = [], 0
        for cik in due + new[:NEW_PER_RUN]:
            raw = read_list(ctx, cik, as_of)
            if raw is not None:
                out.append(raw)
                docs += read_documents(ctx, cik, raw, as_of)
        ctx.notes.append(f"{len(due)} filing lists re-read, {min(len(new), NEW_PER_RUN)} new, {docs} documents"
                         + (f"; {len(new) - NEW_PER_RUN} new left for the next run" if len(new) > NEW_PER_RUN else ""))
        sec_index.mark_scanned(ctx, NAME, as_of)
        return out

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        out, docs = [], 0
        for cik in common.ciks(common.universe()):
            raws = _subs_raws(cik)
            raw = raws[-1] if raws else read_list(ctx, cik, end)
            if raw is None:
                continue
            docs += read_documents(ctx, cik, raw, end)
            # Every company this holds a list for, not only the ones fetched from this run: the rows are typed
            # from raw, so a company whose documents were already on disk still has to be rewritten to gain a
            # row shape it did not have before (the ``whole`` row, 5 Nov 2026).
            out.append(raw)
        ctx.notes.append(f"backfill: {len(out)} filing lists, {docs} documents")
        self.to_parquet_all(ctx, out)

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        return self.to_parquet_all(ctx, [raw])

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        newest: dict[str, Path] = {}
        for raw in raws:
            cik = raw.parent.name
            if cik not in newest or raw.name > newest[cik].name:
                newest[cik] = raw
        out = []
        for cik, raw in sorted(newest.items()):
            meta = base.read_raw_json(common.meta_path(raw))
            stamps = {"source_as_of": date.fromisoformat(meta["as_of"]), "fetched_at": float(meta["fetched_at"]),
                      "run_id": meta["run_id"]}
            body = base.read_raw_json(raw)
            rows = parse(cik, body)
            filing_rows = []
            for r in rows:
                items = [i.strip() for i in str(r.get("items") or "").split(",") if i.strip()] or [None]
                filing_rows += [{**r, "item": i, **stamps} for i in items]
            segment_rows, customer_rows = self._documents(cik, rows)
            folder = common.parquet_dir(NAME) / f"cik={cik}"
            con = duckdb.connect()
            try:
                base.rows_table(con, "filings", FILING, filing_rows)
                out.append(base.write_parquet(con, "SELECT * FROM filings ORDER BY filing_date, accession, item",
                                              folder / "filings.parquet"))
                base.rows_table(con, "segments", SEGMENT, segment_rows)
                out.append(base.write_parquet(con, "SELECT * FROM segments ORDER BY axis, member",
                                              folder / "segments.parquet"))
                base.rows_table(con, "customers", CUSTOMER, customer_rows)
                out.append(base.write_parquet(con, "SELECT * FROM customers ORDER BY customer, benchmark",
                                              folder / "customers.parquet"))
                base.rows_table(con, "header", HEADER, [{**header(cik, body), **stamps}])
                out.append(base.write_parquet(con, "SELECT * FROM header", folder / "header.parquet"))
            finally:
                con.close()
        return out

    @staticmethod
    def _documents(cik: str, rows: list[dict]) -> tuple[list[dict], list[dict]]:
        """The annual report's segment and customer rows (its inline XBRL).

        No text row any more (#858): the documents are on disk for ``sec/forms`` to cut, and this layer reads them
        for their inline XBRL only. An exhibit carries none, so only the primary document is parsed.
        """
        segments, customers = [], []
        f = pick(rows, ANNUAL_FORMS)
        if f is None:
            return segments, customers
        path = _doc_path(cik, f["accession"])
        if not path.exists():
            return segments, customers
        meta = base.read_raw_json(common.meta_path(path))
        html = base.read_raw(path).decode("utf-8", "replace")
        stamps = {"source_as_of": date.fromisoformat(meta["as_of"]),
                  "fetched_at": float(meta["fetched_at"]), "run_id": meta["run_id"]}
        filed = {k: f.get(k) for k in ("cik", "accession", "form", "filing_date")}
        found_segments, found_customers = ixbrl.parse(html)
        segments += [{**filed, **r, "segment": r["label"], **stamps} for r in found_segments]
        customers += [{**filed, **r, **stamps} for r in found_customers]
        return segments, customers

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        folder = common.parquet_dir(NAME)
        ciks = common.dirty_ciks(ctx, con)
        common.stage_glob(con, STAGING["filings"], FILING, folder, "cik=*/filings.parquet", ciks=ciks)
        common.stage_glob(con, STAGING["segments"], SEGMENT, folder, "cik=*/segments.parquet", ciks=ciks)
        common.stage_glob(con, STAGING["customers"], CUSTOMER, folder, "cik=*/customers.parquet", ciks=ciks)
        common.stage_glob(con, STAGING["header"], HEADER, folder, "cik=*/header.parquet", ciks=ciks)
        return {}

    dirty_keyed = True

    def dirty(self, ctx: base.RunContext):
        """The companies whose ``cik=<cik>`` partitions changed since the live file was built (#446)."""
        return dirty_set.keyed(ctx, self)

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        cols = ["cik", "accession", "item", "quality"]
        added, removed = common.compare_live(con, f"SELECT {', '.join(cols)} FROM filing_item", "filing_item", cols,
                                             dirty_only=common.dirty_ciks(ctx, con) is not None)
        # From the served table, not the staging: on a build over the live copy the staging holds only the dirty
        # companies, and every filing-list row is a ``kind = 'item'`` row of ``filing_item`` either way.
        as_of = con.execute("SELECT max(source_as_of) FROM filing_item WHERE kind = 'item'").fetchone()[0]
        listed = con.execute("SELECT count(DISTINCT cik) FROM filing_item WHERE kind = 'item'").fetchone()[0]
        tier_a = con.execute("SELECT count(DISTINCT cik) FROM fundamental_company").fetchone()[0]
        recent = con.execute(f"""SELECT count(DISTINCT c.cik) FROM fundamental_company c
                                 WHERE c.submissions_as_of >= DATE '{(ctx.as_of or self.default_as_of())
                                 - timedelta(days=sec_index.LOOKBACK_DAYS)}'""").fetchone()[0]
        qualities = dict(con.execute("SELECT quality, count(*) FROM filing_item WHERE kind = 'document' "
                                     "GROUP BY 1").fetchall())
        ctx.notes.append(f"{listed} of {tier_a} Tier A companies have a filing list ({recent} read in the last "
                         f"{sec_index.LOOKBACK_DAYS} days); documents by quality: "
                         + (", ".join(f"{k} {v}" for k, v in sorted(qualities.items())) or "none"))
        return {"dataset": NAME, "result": "changed" if added or removed else "unchanged",
                "source_as_of": (as_of or ctx.as_of or self.default_as_of()).isoformat(),
                "rows": common.count(con, "filing_item", "kind = 'item'"), "added": added, "removed": removed,
                "coverage": round(listed / tier_a, 4) if tier_a else None}


DATASET = Filings()
