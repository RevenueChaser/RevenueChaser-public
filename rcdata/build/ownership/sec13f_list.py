"""``sec/13f_list``: the SEC's Official List of Section 13(f) Securities, one text file per quarter (#926).

The list names the securities a 13F filer reports for a quarter; a CUSIP a filer reports that is not on it is a typo,
a stale CUSIP or a security that does not belong in a 13F. Nothing is dropped for it (avo, 16 Nov 2026: the plan's
"mark first"): ``ownership/serve`` counts, per 13F period, the CUSIPs and dollars not on that quarter's list as a
``cusip_not_listed`` build issue, the Data/Health card's.

The page (``PAGE_PATH``) links a PDF for every quarter since 1996 and a text file since 2020q1 (some named
``-txt.txt``); only the text files are read. Each held quarter is not asked again, so a run after the first asks
the page and the new quarter only. Fixed width: the CUSIP in columns 1-9, ``*`` in column 10 when options on it are
listed too, the issuer in 11-40, the class in 41-60; a row marked ``*D*`` was deleted from the list and is not on it.

Raw: ``raw/sec/13f_list/<yyyy>q<n>.txt``. Parquet: ``parquet/sec/13f_list/part-0.parquet`` (``quarter``, ``cusip``,
``has_options``, ``issuer``, ``description``), every held quarter, written again whole. No served table: ``serve``
reads the Parquet, so the list costs no serving schema bump.
"""
from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path

import duckdb

from ....core import calendar
from .. import base, dirty
from . import KIND, sec

NAME = "sec/13f_list"
PAGE_PATH = "/rules-regulations/staff-guidance/official-list-section-13f-securities"
PAGE_ENV = "RC_SEC_13F_LIST_URL"
LINK = re.compile(r'href="([^"]*/13flist(\d{4}q[1-4])(?:-txt)?\.txt)"', re.I)
ROW = re.compile(rb"^[0-9A-Z]{9}[ *]")
SCHEMA = [("quarter", "TEXT"), ("cusip", "TEXT"), ("has_options", "BOOLEAN"), ("issuer", "TEXT"),
          ("description", "TEXT")]


def page_url() -> str:
    return os.getenv(PAGE_ENV) or sec.www_base() + PAGE_PATH


def raw_dir() -> Path:
    return base.raw_root() / "sec" / "13f_list"


def parquet_path() -> Path:
    return base.parquet_root() / "sec" / "13f_list" / "part-0.parquet"


def links(html: str, page: str) -> dict[str, str]:
    """``{quarter: absolute URL}`` of the text files the page links (the first link of a quarter wins)."""
    from urllib.parse import urljoin
    out: dict[str, str] = {}
    for href, quarter in LINK.findall(html):
        out.setdefault(quarter.lower(), urljoin(page, href))
    return out


def parse(quarter: str, body: bytes) -> list[dict]:
    """The rows of one quarter's list still on it (a ``*D*`` row was deleted)."""
    rows = []
    for line in body.splitlines():
        if not ROW.match(line) or b"*D*" in line:
            continue
        text = line.decode("latin-1")
        rows.append({"quarter": quarter, "cusip": text[:9], "has_options": text[9] == "*",
                     "issuer": text[10:40].strip() or None, "description": text[40:60].strip() or None})
    return rows


class Sec13fList:
    name = NAME
    kind = KIND
    providers = (sec.PROVIDER,)
    tables: tuple[str, ...] = ()
    # The official 13(f) list is read for the ``cusip_not_listed`` build issue only, never for a served row.
    feeds: tuple[str, ...] = ()
    cadence = "quarterly"
    backfill_needs_from = False
    starts_by_hand = True             # the first run asks 27 files: the server thread's, after a backup

    def default_as_of(self) -> date:
        return calendar.today_ny()

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        pacer = sec.Pacer(ctx)
        page = page_url()
        listed = links(sec.get(ctx, pacer, page).text, page)
        if not listed:
            raise base.SourceError(f"13(f) list: {page} links no 13flist<yyyy>q<n>.txt (its shape changed?)")
        out = []
        for quarter, url in sorted(listed.items()):
            path = raw_dir() / f"{quarter}.txt"
            if path.exists():
                continue
            body = sec.get(ctx, pacer, url).content
            if not any(ROW.match(line) for line in body.splitlines()[:20]):
                raise base.SourceError(f"13(f) list {quarter}: {url} is not the fixed-width list, not kept")
            out.append(base.write_raw(path, body))
        ctx.pending[NAME] = out
        ctx.notes.append(f"13(f) list: {len(listed)} quarter(s) listed, {len(out)} new")
        return out

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        # The page lists every quarter: a backfill is one run.
        self.to_parquet_all(ctx, self.fetch(ctx, end))

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        return self.to_parquet_all(ctx, [raw])

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        """One file of every held quarter, written again whole (some 25,000 rows a quarter)."""
        held = sorted(raw_dir().glob("*.txt")) if raw_dir().exists() else []
        if not held:
            return []
        rows = [r for path in held for r in parse(path.stem, base.read_raw(path))]
        con = base.scratch_con()
        try:
            base.rows_table(con, "rows", SCHEMA, rows)
            return [base.write_parquet(con, "SELECT * FROM rows ORDER BY quarter, cusip", parquet_path())]
        finally:
            con.close()

    def dirty(self, ctx: base.RunContext):
        return dirty.ALL

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        return {}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        rows = quarters = 0
        if parquet_path().exists():
            rows, quarters = base.scratch_con().execute(
                f"SELECT count(*), count(DISTINCT quarter) FROM read_parquet({base.sql_path(parquet_path())})"
            ).fetchone()
        return {"dataset": NAME, "result": "changed" if ctx.pending.get(NAME) else "unchanged",
                "source_as_of": (ctx.as_of or self.default_as_of()).isoformat(), "rows": rows,
                "note": f"{quarters} quarter(s) held"}


DATASET = Sec13fList()
