"""``wrds/fundq``, ``wrds/funda``, ``wrds/segments``: Compustat's statements and segments, a check of the SEC; and
``wrds/exrt``, Compustat's daily exchange rates, staged beside Yahoo's (``WrdsExrt``).

**Run against the real source once** (the server run of 2026-10-29, PR 249: ``comp.fundq`` and ``comp.funda``
answered; ``seg_customer`` had no ``srcdate``). So the dataset whose columns were a guess, ``wrds/segments``, reads
WRDS's own catalog first (``catalog``: ``information_schema.columns``, one more query): a segment table's columns in
``optional`` that WRDS does not have are not asked (read as empty, said in the note). A table in none of its
libraries, or without a column it needs, fails the run with what WRDS has. The tests answer from a fake worker whose
catalog follows that run.

``wrds/firm_ratio`` (WRDS's Financial Ratios Suite, the debt-to-assets check) was dropped on 5 Nov 2026, avo's
decision: it served no table, only an agreement note, and its table was not in either library it was asked from on
the one real run. The SEC's own as-filed values (``sec/fsds``) are the check that stands.

**A check source, not a served value.** The served statement values are the SEC's (``sec/companyfacts``). What WRDS
adds: (1) **the revision table**: each monthly snapshot of ``fundq`` / ``funda`` against the one before, every value
that changed for a period both hold (a restatement, or a correction at Compustat), served as
``fundamental_revision``; a new period is not a revision; (2) **the agreement notes**: revenue (banks left out),
net income, diluted EPS and total debt (``dltt + dlc``) against the SEC's facts of the same period (Compustat's millions times a million, within 0.5%; EPS
within a cent; period ends within 7 days, for the 52/53-week years).

**Attended and monthly, on the spine's one WRDS worker** (``spine/wrds.py``: one login, at most one Duo push per
builder process, ``WRDS_USERNAME``, ``RC_WRDS_PYTHON``): never due; ``python -m RevenueChaser.rcdata.build backfill
wrds/fundq wrds/funda wrds/segments`` in a foreground terminal on the server. A run asks a table once its newest
snapshot is ``SNAPSHOT_DAYS`` old (the CLI's backfill asks it now); one query per table, for the Tier A gvkeys (the
spine's Compustat link), Compustat's standard rows (``COMPUSTAT_FILTER``), ``YEARS`` of periods. Every query counts
as one ``wrds`` call.

Raw: ``raw/wrds/<table>/<as-of>/<table>.jsonl.gz`` with a ``.meta.json`` sidecar (the query, rows, run), and
``.../catalog.jsonl.gz`` for the catalog read; an existing raw file is not asked again. Parquet:
``parquet/wrds/<table>/snapshot=<as-of>/<table>.parquet`` and, from the second snapshot on,
``.../revision=<as-of>/<table>.parquet`` (its changes against the snapshot before). Staging:
``stg_wrds_<table>`` (the newest snapshot) and ``stg_wrds_<table>_revision`` (every revision file).
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import duckdb

from ....core import calendar
from .. import base
from .. import dirty as dirty_set
from ..spine import wrds as wrds_session
from . import KIND, common, facts, fx_rates

PROVIDER = wrds_session.PROVIDER
SNAPSHOT_DAYS = 30
YEARS = 10
COMPUSTAT_FILTER = "indfmt = 'INDL' AND datafmt = 'STD' AND popsrc = 'D' AND consol = 'C'"
PERIOD_DAYS = 7
MONEY_TOLERANCE = 0.005
EPS_TOLERANCE = 0.01
MILLION = 1_000_000.0
#: SEC SIC 6000-6199: depository institutions and non-depository credit (JPM is 6021). Left out of the revenue
#: agreement only (#277): their served revenue is net, Compustat's ``revt`` gross.
BANK_SIC = (6000, 6199)
SEGMENT_LIBRARY = "comp_segments_hist_daily"
CATALOG = [("table_schema", "TEXT"), ("table_name", "TEXT"), ("column_name", "TEXT")]
SEGMENT_YEARS = 5
# Compustat's segment types: business and operating segments are one axis here, geographic the other.
SEGMENT_TYPES = {"BUSSEG": "business", "OPSEG": "business", "GEOSEG": "geographic"}
_GVKEY = re.compile(r"^\d{6}$")

REVISION = [("source", "TEXT"), ("gvkey", "TEXT"), ("datadate", "DATE"), ("item", "TEXT"), ("old_value", "DOUBLE"),
            ("new_value", "DOUBLE"), ("old_as_of", "DATE"), ("new_as_of", "DATE"), ("run_id", "TEXT")]
PROVENANCE = [("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]


def catalog(ctx: base.RunContext, dataset: str, as_of: date, tables: list[str]) -> dict[tuple[str, str], set[str]]:
    """WRDS's own columns of ``tables`` in every library this login can read, ``{(library, table): columns}``: one
    query on the shared worker (``information_schema.columns``), kept like a table's answer."""
    raw = common.raw_dir(dataset) / as_of.isoformat() / f"catalog{wrds_session.RAW_SUFFIX}"
    names = ", ".join(f"'{t}'" for t in tables)
    wrds_session._ask(ctx, raw, "SELECT table_schema, table_name, column_name FROM information_schema.columns "
                                f"WHERE table_name IN ({names})", as_of)
    con = base.scratch_con()
    try:
        rows = con.execute(wrds_session.raw_rows(raw, CATALOG)).fetchall()
    finally:
        con.close()
    out: dict[tuple[str, str], set[str]] = {}
    for library, table, column in rows:
        out.setdefault((library, table), set()).add(str(column).lower())
    return out


def locate(found: dict[tuple[str, str], set[str]], libraries: tuple[str, ...], table: str,
           needed: list[str]) -> tuple[str, set[str]]:
    """``(library, columns)``: the first of ``libraries`` that holds ``table`` in ``found`` (``catalog``). A
    ``SourceError`` names what WRDS has when none does, or when that table lacks a ``needed`` column."""
    for library in libraries:
        columns = found.get((library, table))
        if columns:
            missing = [c for c in needed if c not in columns]
            if missing:
                raise base.SourceError(f"wrds {library}.{table} has no {', '.join(missing)} "
                                       f"(it has {', '.join(sorted(columns))})")
            return library, columns
    elsewhere = sorted(lib for lib, t in found if t == table)
    raise base.SourceError(f"wrds {table} is not in {' or '.join(libraries)}; WRDS has it in "
                           f"{', '.join(elsewhere) or 'no library this login can read'}")


def _years_before(day: date, years: int) -> date:
    try:
        return day.replace(year=day.year - years)
    except ValueError:                                   # 29 February
        return day.replace(year=day.year - years, day=28)


class WrdsFund:
    """One WRDS table of the fundamentals layer: a full snapshot a month, its revisions, its agreement note."""

    kind = KIND
    providers = (PROVIDER,)
    tables: tuple[str, ...] = ()
    cadence = "monthly"
    attended = property(lambda self: base.wrds_attended())   # RC_WRDS_UNATTENDED=1: the builder runs it
    backfill_needs_from = False
    starts_by_hand = True

    def __init__(self, table: str, library: str, attrs: list[tuple[str, str]], items: list[str], key: list[str],
                 since: str, years: int, revisions: bool):
        self.table = table
        self.name = f"wrds/{table}"
        self.library = library
        self.items = items
        self.key = key
        self.schema = attrs + [(i, "DOUBLE") for i in items]
        self.since, self.years, self.revisions = since, years, revisions
        #: The served tables this dataset's rows reach (#326): the first-reported values are the revisions,
        #: and the segment set is the Compustat half of the segment and customer tables.
        self.feeds = ("fundamental_revision",) if revisions else ("segment_revenue", "customer_share")
        if table == "fundq":      # its ``rdq`` is the report day of ``earnings_report_history`` (#1181)
            self.feeds += ("earnings_report_history",)
        self.staging = f"stg_wrds_{table}"
        self.revision_staging = f"stg_wrds_{table}_revision"

    def default_as_of(self) -> date:
        return calendar.today_ny()

    # ── what is asked ──
    def sql(self, gvkeys: list[str], as_of: date, library: str | None = None) -> str:
        library = library or self.library
        cols = ", ".join(c for c, _ in self.schema)
        where = [COMPUSTAT_FILTER] if library == "comp" else []
        where += [f"gvkey IN ({', '.join(repr(g) for g in gvkeys)})",
                  f"{self.since} >= DATE '{_years_before(as_of, self.years).isoformat()}'"]
        return f"SELECT {cols} FROM {library}.{self.table} WHERE {' AND '.join(where)}"

    def _library(self, ctx: base.RunContext, as_of: date) -> str:
        """The library the table is asked from: Compustat's ``comp``, known, so nothing is asked for it."""
        return self.library

    def raw_path(self, as_of: date) -> Path:
        return common.raw_dir(self.name) / as_of.isoformat() / f"{self.table}{wrds_session.RAW_SUFFIX}"

    def snapshots(self) -> list[str]:
        folder = common.parquet_dir(self.name)
        if not folder.is_dir():
            return []
        return sorted(d.name.split("=", 1)[1] for d in folder.iterdir()
                      if d.name.startswith("snapshot=") and (d / f"{self.table}.parquet").is_file())

    def snapshot_file(self, as_of: str) -> Path:
        return common.parquet_dir(self.name) / f"snapshot={as_of}" / f"{self.table}.parquet"

    def held(self, as_of: date) -> list[Path]:
        """The raw files of the newest snapshot asked within ``SNAPSHOT_DAYS`` before ``as_of`` and not typed yet
        (every part's, with its sidecar), or []: a held answer is typed again rather than asked again (#503)."""
        root = common.raw_dir(self.name)
        typed = set(self.snapshots())
        for folder in sorted(root.iterdir() if root.is_dir() else [], reverse=True):
            try:
                day = date.fromisoformat(folder.name)
            except ValueError:
                continue
            if not 0 <= (as_of - day).days < SNAPSHOT_DAYS or folder.name in typed:
                continue
            raws = [self.raw_path(day, *part) for part in self._parts()]
            if all(r.exists() and common.meta_path(r).exists() for r in raws):
                return raws
        return []

    def _parts(self) -> list[tuple]:
        return [()]

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        held = self.held(as_of)
        if held:
            ctx.notes.append(f"raw snapshot of {held[0].parent.name} typed again, nothing asked (#503)")
            return held
        snaps = self.snapshots()
        if snaps and (as_of - date.fromisoformat(snaps[-1])).days < SNAPSHOT_DAYS \
                and not self.raw_path(as_of).exists():
            ctx.notes.append(f"snapshot of {snaps[-1]} is current (asked again after {SNAPSHOT_DAYS} days)")
            return []
        return self._full(ctx, as_of)

    def _full(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        gvkeys = sorted({str(r["gvkey"]) for r in common.universe() if _GVKEY.match(str(r.get("gvkey") or ""))})
        if not gvkeys:
            ctx.notes.append("no Tier A company has a Compustat link yet (wrds/sec_idhist): nothing asked")
            return []
        # The spine's resumable ask (one query on the shared worker, its sidecar first).
        return [wrds_session._ask(ctx, self.raw_path(as_of), self.sql(gvkeys, as_of, self._library(ctx, as_of)),
                                  as_of)]

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        # WRDS answers the whole history in one snapshot: a backfill is a snapshot as of the end day.
        self.to_parquet_all(ctx, self._full(ctx, end))

    # ── type ──
    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        return self.to_parquet_all(ctx, [raw])

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        out = []
        for raw in raws:
            meta = base.read_raw_json(common.meta_path(raw))
            as_of = meta["as_of"]
            con = base.scratch_con()
            try:
                rows = int(con.execute(f"SELECT count(*) FROM ({wrds_session.raw_rows(raw, self.schema)})")
                           .fetchone()[0])
                if not rows:
                    raise base.SourceError(f"wrds {self.table}: the snapshot came back empty")
                types = dict(self.schema)
                for col, n in wrds_session.untyped(con, raw, self.schema).items():
                    ctx.issue("value_untyped", f"{self.table}.{col}", f"{n} row(s) of {rows} nulled "
                                                                     f"(as {types[col]})")
                keys = ", ".join(self.key)
                every = ", ".join(f'"{c}" NULLS LAST' for c, _ in self.schema)
                select = (f"SELECT *, DATE '{as_of}' AS source_as_of, CAST({float(meta['fetched_at'])} AS DOUBLE) "
                          f"AS fetched_at, '{meta['run_id']}' AS run_id "
                          f"FROM ({wrds_session.raw_rows(raw, self.schema)}) "
                          f"QUALIFY row_number() OVER (PARTITION BY {keys} ORDER BY {every}) = 1 ORDER BY {keys}")
                out.append(base.write_parquet(con, select, self.snapshot_file(as_of)))
                before = [s for s in self.snapshots() if s < as_of]
                if self.revisions and before:
                    out.append(base.write_parquet(con, self._revision_sql(before[-1], as_of, meta["run_id"]),
                                                  common.parquet_dir(self.name) / f"revision={as_of}" /
                                                  f"{self.table}.parquet"))
            finally:
                con.close()
            ctx.pending.setdefault(self.name, []).append(as_of)
        return out

    def _revision_sql(self, old: str, new: str, run_id: str) -> str:
        """The values of snapshot ``new`` that differ from snapshot ``old``, for the periods both hold."""
        items = ", ".join(f'"{i}"' for i in self.items)

        def long(as_of: str) -> str:
            return (f"(UNPIVOT (SELECT gvkey, datadate, {items} FROM read_parquet("
                    f"{base.sql_path(self.snapshot_file(as_of))})) ON {items} INTO NAME item VALUE value)")
        both = (f"SELECT gvkey, datadate FROM read_parquet({base.sql_path(self.snapshot_file(old))}) INTERSECT "
                f"SELECT gvkey, datadate FROM read_parquet({base.sql_path(self.snapshot_file(new))})")
        return f"""
            SELECT '{self.name}' AS source, coalesce(o.gvkey, n.gvkey) AS gvkey,
                   coalesce(o.datadate, n.datadate) AS datadate, coalesce(o.item, n.item) AS item,
                   o.value AS old_value, n.value AS new_value, DATE '{old}' AS old_as_of, DATE '{new}' AS new_as_of,
                   '{run_id}' AS run_id
            FROM {long(old)} o FULL JOIN {long(new)} n
              ON n.gvkey = o.gvkey AND n.datadate = o.datadate AND n.item = o.item
            WHERE o.value IS DISTINCT FROM n.value
              AND (coalesce(o.gvkey, n.gvkey), coalesce(o.datadate, n.datadate)) IN ({both})
            ORDER BY gvkey, datadate, item"""

    # ── incremental (#446) ──
    def dirty(self, ctx: base.RunContext):
        """One snapshot a month, reloaded whole by every build, on the live copy too."""
        return dirty_set.ALL

    def full_rebuild_reason(self, ctx: base.RunContext) -> str | None:
        """A new monthly snapshot restates Compustat's history: the owner's rule is a whole build (#446 item 6)."""
        folder = common.parquet_dir(self.name)
        changed = getattr(ctx, "changed", None) or ()
        new = sorted({p.relative_to(folder).parts[0] for p in changed
                      if folder in p.parents and p.relative_to(folder).parts[0].startswith("snapshot=")})
        return f"a new monthly snapshot ({', '.join(new)})" if new else None

    # ── stage ──
    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        snaps = self.snapshots()
        folder = common.parquet_dir(self.name)
        common.stage_glob(con, self.staging, self.schema + PROVENANCE, folder,
                          f"snapshot={snaps[-1]}/{self.table}.parquet" if snaps else "snapshot=none/none")
        if self.revisions:
            common.stage_glob(con, self.revision_staging, REVISION, folder, f"revision=*/{self.table}.parquet")
        return {}

    # ── check ──
    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        added = removed = 0
        if self.revisions:
            cols = ["gvkey", "datadate", "item", "old_value", "new_value", "new_as_of"]
            where = f"source = '{self.name}'"
            added, removed = common.compare_live(
                con, f"SELECT {', '.join(cols)} FROM fundamental_revision WHERE {where}", "fundamental_revision",
                cols, where=where)
        as_of = con.execute(f"SELECT max(source_as_of) FROM {self.staging}").fetchone()[0]
        ctx.notes.append(self.note(con))
        on = ctx.as_of or self.default_as_of()
        return {"dataset": self.name, "result": "changed" if (ctx.pending.get(self.name) or added or removed)
                else "unchanged", "source_as_of": (as_of or on).isoformat(),
                "rows": common.count(con, self.staging), "added": added, "removed": removed}

    def note(self, con: duckdb.DuckDBPyConnection) -> str:
        period_type = facts.QUARTERLY if self.table == "fundq" else facts.ANNUAL
        sfx = "q" if self.table == "fundq" else ""
        parts = []
        for label, field, item, tolerance in (
                ("revenue", "revenue", f"revt{sfx}", None), ("net income", "net_income", f"ni{sfx}", None),
                ("diluted EPS", "eps_diluted", f"epsfx{sfx}", EPS_TOLERANCE)):
            n, ok = agreement(con, self.staging, item, field, period_type, tolerance,
                              first_reported=self.table == "funda", banks=label != "revenue")
            parts.append(f"{label} {ok} of {n}")
        note = f"WRDS {self.table} vs the SEC: {', '.join(parts)} agree (banks left out of revenue)"
        # #277 / plan step 9: the debt Compustat holds (long-term + current) against the SEC's derived total.
        n, ok = agreement(con, self.staging, (f"dltt{sfx}", f"dlc{sfx}"), "total_debt", period_type, None,
                          first_reported=self.table == "funda")
        note += f"; total debt {ok} of {n} agree"
        snaps = self.snapshots()
        if len(snaps) >= 2:
            n = con.execute(f"SELECT count(*) FROM {self.revision_staging} WHERE new_as_of = DATE '{snaps[-1]}'"
                            ).fetchone()[0]
            note += f"; {n} revision(s) in the snapshot of {snaps[-1]} against {snaps[-2]}"
        elif snaps:
            note += "; the first snapshot: no revisions yet"
        return note


def _links() -> str:
    return "(SELECT DISTINCT gvkey, cik FROM fundamental_company WHERE gvkey IS NOT NULL)"


def agreement(con: duckdb.DuckDBPyConnection, staging: str, item: str | tuple[str, ...], field: str,
              period_type: str, eps_tolerance: float | None, first_reported: bool = False,
              banks: bool = True) -> tuple[int, int]:
    """``(compared, agreeing)``: the periods where Compustat's ``item`` and the SEC's ``field`` both have a value
    (period ends within ``PERIOD_DAYS``). Money in millions at Compustat; EPS as is. ``first_reported``: compare the
    value the year's own report first gave (``first_value``), which ``funda`` keeps where the SEC serves a later
    restatement or split-adjusted figure (#277: 11 of 59 EPS years, 3 net income, 4 revenue on the 29 Oct sample).

    ``item`` as a tuple is the sum of those Compustat items, compared only where every one has a value (total debt
    is ``dltt + dlc``). ``banks`` False leaves out the filers whose SEC SIC is in ``BANK_SIC``: a bank's served
    revenue is its tagged ``Revenues``, net of interest expense, while Compustat's ``revt`` is gross, so every
    bank year would disagree for a reason that is not an error (#277, JPM)."""
    value = "coalesce(first_value, value)" if first_reported else "value"
    v = " + ".join(f's."{i}"' for i in ((item,) if isinstance(item, str) else item))
    skip = "" if banks else (" AND c.cik NOT IN (SELECT cik FROM fundamental_company WHERE "
                             f"TRY_CAST(sic AS INTEGER) BETWEEN {BANK_SIC[0]} AND {BANK_SIC[1]})")
    if eps_tolerance is None:
        ok = (f"abs(f.value - w.v * {MILLION}) <= {MONEY_TOLERANCE} * "
              f"greatest(abs(f.value), abs(w.v * {MILLION}))")
    else:
        ok = f"abs(f.value - w.v) <= {eps_tolerance}"
    n, agree = con.execute(f"""
        WITH w AS (SELECT c.cik, s.datadate, {v} AS v FROM {staging} s JOIN {_links()} c ON c.gvkey = s.gvkey
                   WHERE {v} IS NOT NULL{skip}),
             f AS (SELECT cik, period_end, {value} AS value FROM fundamental_fact
                   WHERE field = '{field}' AND period_type = '{period_type}' AND NOT preliminary)
        SELECT count(*), count(*) FILTER (WHERE {ok})
        FROM w JOIN f ON f.cik = w.cik AND abs(date_diff('day', f.period_end, w.datadate)) <= {PERIOD_DAYS}
        """).fetchone()
    return int(n or 0), int(agree or 0)


class WrdsSegments(WrdsFund):
    """``wrds/segments``: Compustat's segment sales (``wrds_segmerged``: business, operating and geographic
    segments) and major customers (``seg_customer``), ``SEGMENT_YEARS`` of fiscal years; per segment and year the
    newest source filing's row (``srcdate``, where the table has it). Served as rows of ``segment_revenue`` and
    ``customer_share`` (``source`` ``wrds/segments``) beside the annual report's own (``sec/filings``). Both tables
    answered from ``SEGMENT_LIBRARY`` on the server run of 2026-10-29; ``seg_customer`` had no ``srcdate``, so a
    part's columns are read from WRDS's catalog first and its ``optional`` ones that WRDS lacks are not asked."""

    # part -> (schema, key, extra filter, optional columns: read as empty when WRDS does not have them)
    PARTS = {
        "wrds_segmerged": ([("gvkey", "TEXT"), ("datadate", "DATE"), ("srcdate", "DATE"), ("stype", "TEXT"),
                            ("sid", "TEXT"), ("snms", "TEXT"), ("sales", "DOUBLE")],
                           ["gvkey", "datadate", "stype", "sid"],
                           "stype IN (" + ", ".join(f"'{t}'" for t in sorted(SEGMENT_TYPES)) + ")", {"srcdate"}),
        # Only gvkey and datadate are known to exist (PostgreSQL named srcdate, the third column asked, first).
        "seg_customer": ([("gvkey", "TEXT"), ("datadate", "DATE"), ("srcdate", "DATE"), ("cnms", "TEXT"),
                          ("ctype", "TEXT"), ("salecs", "DOUBLE"), ("stype", "TEXT"), ("sid", "TEXT")],
                         ["gvkey", "datadate", "cnms", "stype", "sid"], None, {"srcdate", "ctype", "stype", "sid"}),
    }
    STAGING = {"wrds_segmerged": "stg_wrds_segments", "seg_customer": "stg_wrds_customers"}

    def __init__(self):
        super().__init__("wrds_segmerged", SEGMENT_LIBRARY, [], [], [], "datadate", SEGMENT_YEARS, revisions=False)
        self.name = "wrds/segments"
        self.staging = self.STAGING["wrds_segmerged"]

    def raw_path(self, as_of: date, part: str = "wrds_segmerged") -> Path:
        return common.raw_dir(self.name) / as_of.isoformat() / f"{part}{wrds_session.RAW_SUFFIX}"

    def snapshot_file(self, as_of: str, part: str = "wrds_segmerged") -> Path:
        return common.parquet_dir(self.name) / f"snapshot={as_of}" / f"{part}.parquet"

    def _parts(self) -> list[tuple]:
        return [(p,) for p in self.PARTS]

    def snapshots(self) -> list[str]:
        folder = common.parquet_dir(self.name)
        if not folder.is_dir():
            return []
        return sorted(d.name.split("=", 1)[1] for d in folder.iterdir()
                      if d.name.startswith("snapshot=") and all((d / f"{p}.parquet").is_file() for p in self.PARTS))

    def _full(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        gvkeys = sorted({str(r["gvkey"]) for r in common.universe() if _GVKEY.match(str(r.get("gvkey") or ""))})
        if not gvkeys:
            ctx.notes.append("no Tier A company has a Compustat link yet (wrds/sec_idhist): nothing asked")
            return []
        found = catalog(ctx, self.name, as_of, list(self.PARTS))
        asked = {}
        for part, (schema, _, _, optional) in self.PARTS.items():
            _, columns = locate(found, (self.library,), part, [c for c, _ in schema if c not in optional])
            asked[part] = [c for c, _ in schema if c in columns]
            absent = [c for c, _ in schema if c not in columns]
            if absent:
                ctx.notes.append(f"{self.library}.{part} has no {', '.join(absent)} (read as empty)")
        out = []
        for part, (_, _, extra, _) in self.PARTS.items():
            where = [f"gvkey IN ({', '.join(repr(g) for g in gvkeys)})",
                     f"datadate >= DATE '{_years_before(as_of, self.years).isoformat()}'"] + ([extra] if extra else [])
            sql = f"SELECT {', '.join(asked[part])} FROM {self.library}.{part} WHERE {' AND '.join(where)}"
            out.append(wrds_session._ask(ctx, self.raw_path(as_of, part), sql, as_of))
        return out

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        out = []
        for raw in raws:
            part = raw.name[: -len(wrds_session.RAW_SUFFIX)]
            schema, key, _, _ = self.PARTS[part]
            meta = base.read_raw_json(common.meta_path(raw))
            as_of = meta["as_of"]
            con = base.scratch_con()
            try:
                keep = (" WHERE stype IN (" + ", ".join(f"'{t}'" for t in sorted(SEGMENT_TYPES)) + ")"
                        if part == "wrds_segmerged" else "")
                rows = f"SELECT * FROM ({wrds_session.raw_rows(raw, schema)}){keep}"
                if part == "wrds_segmerged" and not con.execute(f"SELECT count(*) FROM ({rows})").fetchone()[0]:
                    raise base.SourceError("wrds segments: the snapshot came back empty")
                for col, n in wrds_session.untyped(con, raw, schema).items():
                    ctx.issue("value_untyped", f"{part}.{col}", f"{n} row(s) nulled")
                # shortcut: without srcdate (seg_customer on WRDS today) two source filings of one key keep the row
                # first in column order, not the newer filing's; upgrade once the server's catalog.jsonl.gz shows
                # which column dates a customer row's source filing.
                every = ", ".join(f'"{c}" NULLS LAST' for c, _ in schema)
                select = (f"SELECT *, DATE '{as_of}' AS source_as_of, CAST({float(meta['fetched_at'])} AS DOUBLE) "
                          f"AS fetched_at, '{meta['run_id']}' AS run_id FROM ({rows}) "
                          f"QUALIFY row_number() OVER (PARTITION BY {', '.join(key)} "
                          f"ORDER BY srcdate DESC NULLS LAST, {every}) = 1 ORDER BY {', '.join(key)}")
                out.append(base.write_parquet(con, select, self.snapshot_file(as_of, part)))
            finally:
                con.close()
            ctx.pending.setdefault(self.name, []).append(as_of)
        return out

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        snaps = self.snapshots()
        for part, (schema, _, _, _) in self.PARTS.items():
            common.stage_glob(con, self.STAGING[part], schema + PROVENANCE, common.parquet_dir(self.name),
                              f"snapshot={snaps[-1]}/{part}.parquet" if snaps else "snapshot=none/none")
        return {}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        cols = ["cik", "axis", "member", "period_end", "value"]
        where = f"source = '{self.name}'"
        added, removed = common.compare_live(con, f"SELECT {', '.join(cols)} FROM segment_revenue WHERE {where}",
                                             "segment_revenue", cols, where=where)
        return {**super().check(ctx, con), "added": added, "removed": removed,
                "result": "changed" if (ctx.pending.get(self.name) or added or removed) else "unchanged"}

    def note(self, con: duckdb.DuckDBPyConnection) -> str:
        tier_a = con.execute("SELECT count(DISTINCT cik) FROM fundamental_company").fetchone()[0]
        companies, rows = con.execute(f"SELECT count(DISTINCT cik), count(*) FROM segment_revenue "
                                      f"WHERE source = '{self.name}'").fetchone()
        customers, shared = con.execute(f"SELECT count(*), count(share) FROM customer_share "
                                        f"WHERE source = '{self.name}'").fetchone()
        return (f"{companies} of {tier_a} Tier A companies with segments ({rows} segment-years); {customers} "
                f"customer rows, {shared} with a share of the SEC's revenue")


class WrdsExrt(WrdsFund):
    """``wrds/exrt``: Compustat's daily exchange rates (``comp.exrt_dly``), the whole history of the currencies the
    fundamentals layer converts (``fx_rates.CURRENCIES``), one snapshot a month.

    **Measured on homesrv, 20 Nov 2026 (#1181, step H of the WRDS plan):** every row's ``fromcurd`` is ``GBP``, so
    a rate in USD per unit is the cross ``exratd(GBP->USD) / exratd(GBP->CUR)``; the table runs from 1982-02-01,
    holds all 38 currencies we use, and its cross agrees with ``yfinance/fx`` within 1% on 91.4% of 9,947
    (currency, day) pairs of a year (weakest: KZT, SAR, PEN; fixing-time differences, medians within about 1%).

    **Compustat's rate is the one used wherever it has one** (DECISIONS F3; avo, 20 Nov 2026):
    ``fx_rates.held_rates`` reads the newest snapshot of this dataset first and Yahoo's file for the days it lacks.
    ``stg_wrds_exrt`` has the shape of ``stg_yf_fx`` (currency, day, USD per unit) and the check note says how the
    two agree over the newest year."""

    BASE = fx_rates.EXRT_BASE
    USD = fx_rates.USD
    TOLERANCE = 0.01
    YEAR_DAYS = 365

    def __init__(self):
        attrs = [("fromcurd", "TEXT"), ("tocurd", "TEXT"), ("datadate", "DATE"), ("exratd", "DOUBLE")]
        super().__init__(fx_rates.EXRT_TABLE, "comp", attrs, [], ["tocurd", "datadate"], "datadate", 0,
                         revisions=False)
        self.name = fx_rates.EXRT_NAME
        # The rates a non-USD filer's facts are put in USD with, like ``yfinance/fx``'s (``fx_rates.held_rates``).
        self.feeds = ("fundamental_fact", "peer_group", "customer_share")
        self.raw_staging = "stg_wrds_exrt_raw"
        self.staging = "stg_wrds_exrt"

    def sql(self, gvkeys=None, as_of=None, library: str | None = None) -> str:
        cols = ", ".join(c for c, _ in self.schema)
        wanted = ", ".join(repr(c) for c in sorted({*fx_rates.CURRENCIES, self.USD}))
        return (f"SELECT {cols} FROM {library or self.library}.{self.table} "
                f"WHERE fromcurd = '{self.BASE}' AND tocurd IN ({wanted})")

    def _full(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        return [wrds_session._ask(ctx, self.raw_path(as_of), self.sql(), as_of)]

    def full_rebuild_reason(self, ctx: base.RunContext) -> str | None:
        """A new snapshot is no reason to build the kind whole: the rates reach the facts when a company is typed
        again, not through this dataset's staging."""
        return None

    def cross(self, con: duckdb.DuckDBPyConnection) -> int:
        """``stg_wrds_exrt`` from the staged snapshot: USD per unit of each currency, by day. The base currency has
        no row of its own against itself that we rely on: its rate is the USD row's."""
        con.execute(f"CREATE OR REPLACE TEMP TABLE {self.staging} AS "
                    + fx_rates.cross_sql(self.raw_staging, stamps=True))
        return common.count(con, self.staging)

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        snaps = self.snapshots()
        common.stage_glob(con, self.raw_staging, self.schema + PROVENANCE, common.parquet_dir(self.name),
                          f"snapshot={snaps[-1]}/{self.table}.parquet" if snaps else "snapshot=none/none")
        self.cross(con)
        return {}

    def note(self, con: duckdb.DuckDBPyConnection) -> str:
        cols = ", ".join(f'"{c}" {t}' for c, t in fx_rates.SCHEMA)
        con.execute(f"CREATE TEMP TABLE IF NOT EXISTS {fx_rates.STAGING} ({cols})")     # a registry without Yahoo's
        currencies, first, newest = con.execute(
            f"SELECT count(DISTINCT currency), min(day), max(day) FROM {self.staging}").fetchone()
        if not currencies:
            return "WRDS exrt_dly: no snapshot yet"
        n, ok = con.execute(f"""
            SELECT count(*), count(*) FILTER (WHERE abs(w.usd_per_unit - y.usd_per_unit)
                                                    <= {self.TOLERANCE} * greatest(w.usd_per_unit, y.usd_per_unit))
            FROM {self.staging} w JOIN {fx_rates.STAGING} y ON y.currency = w.currency AND y.day = w.day
            WHERE w.day > DATE '{newest}' - INTERVAL {self.YEAR_DAYS} DAY AND y.usd_per_unit > 0""").fetchone()
        missing = sorted(set(fx_rates.CURRENCIES) - {r[0] for r in con.execute(
            f"SELECT DISTINCT currency FROM {self.staging}").fetchall()})
        return (f"WRDS exrt_dly ({self.BASE}-based, crossed to USD): {currencies} currencies, {first} to {newest}; "
                f"{int(ok or 0)} of {int(n or 0)} (currency, day) pairs of the newest year agree with Yahoo within "
                f"1%" + (f"; not at Compustat: {', '.join(missing)}" if missing else ""))


class WrdsAudit(WrdsFund):
    """``wrds/audit``: Audit Analytics' three event feeds, whole, one snapshot a month: financial restatements
    (``feed39_financial_restatements``), late-filing notices (``feed20_nt``, the NT 10-K / NT 10-Q forms) and
    director and officer changes (``feed17_director_and_officer_chan``).

    **Measured on homesrv, 20 Nov 2026 (#1181, step C of the WRDS plan):** ``company_fkey`` is the SEC's CIK (all
    digits, largest 2,108,359; 5,078 of our 5,292 CIKs are in the officer feed, 2,833 in the restatements, 2,166 in
    the late filings, against 35 to 53 expected by chance), so the rows need no link table. All three ended in the
    second half of September 2026, about two months behind the day they were read: a flag built from them is a
    history, and the fresh signal stays the 8-K's own item (``filing_item``).

    Of each feed's 219 to 249 columns only the event's own are asked: its key, the company, the filing day and
    form, and the columns that say what happened. No person's name and no disclosure text is asked. The flag
    columns stay text in the snapshot, exactly as WRDS answers. Whether a feed's key is unique is not measured, so
    a snapshot keeps every distinct row and the note says how many keys they are.

    **The coding, measured on the first snapshot (20 Nov 2026, #1181):** every ``res_*`` flag of ``SERVED`` and
    every ``is_*`` / ``interim`` flag holds 0 or 1 and nothing else, on 29,198 and 579,845 rows; ``action`` holds
    17 words (Appointed, Resigned, Retired, ...). ``res_board_approval`` and ``res_auditor_letter`` are Y / N / ND
    with 2,410 empty rows and mostly ND, so they are staged and not served. ``audit_flag`` (``tables.py``) serves
    what ``SERVED`` names. Not measured: how ``pe_date_num`` is written (served as a day only when it starts with
    eight digits that are one) and what ``nt_reas_keys`` holds (not served)."""

    LIBRARY = "audit_audit_comp"
    COMPANY = "company_fkey"
    # part -> (label of the note, the columns asked, the feed's own key)
    PARTS = {
        "feed39_financial_restatements": ("restatements", [
            ("restatement_notification_key", "TEXT"), ("company_fkey", "TEXT"), ("file_date", "DATE"),
            ("form_fkey", "TEXT"), ("res_begin_date", "DATE"), ("res_end_date", "DATE"),
            ("date_of_8k_402", "DATE"), ("res_accounting", "TEXT"), ("res_fraud", "TEXT"),
            ("res_clerical_errors", "TEXT"), ("res_other", "TEXT"), ("res_adverse", "TEXT"),
            ("res_improves", "TEXT"), ("res_sec_investigation", "TEXT"), ("res_board_approval", "TEXT"),
            ("res_auditor_letter", "TEXT"), ("quarterly_restated_only", "TEXT")],
            "restatement_notification_key"),
        "feed20_nt": ("late filings", [
            ("nt_notify_key", "TEXT"), ("company_fkey", "TEXT"), ("file_date", "DATE"), ("form_fkey", "TEXT"),
            ("pe_date_num", "TEXT"), ("nt_reas_keys", "TEXT"), ("nt_reas_titles", "TEXT")],
            "nt_notify_key"),
        "feed17_director_and_officer_chan": ("officer changes", [
            ("do_change_key", "TEXT"), ("do_off_pers_key", "TEXT"), ("company_fkey", "TEXT"),
            ("file_date", "DATE"), ("form_fkey", "TEXT"), ("eff_date", "DATE"), ("action", "TEXT"),
            ("title_standard", "TEXT"), ("is_ceo", "TEXT"), ("is_cfo", "TEXT"), ("is_coo", "TEXT"),
            ("is_president", "TEXT"), ("is_chair", "TEXT"), ("is_c_level", "TEXT"), ("is_bdmem_pers", "TEXT"),
            ("interim", "TEXT")],
            "do_change_key"),
    }
    STAGING = {"feed39_financial_restatements": "stg_wrds_restatements", "feed20_nt": "stg_wrds_late_filings",
               "feed17_director_and_officer_chan": "stg_wrds_officer_changes"}
    FIRST = "feed39_financial_restatements"
    #: What ``audit_flag`` serves of each feed: its ``kind``, the 0/1 columns that become a label in ``flags``
    #: (column -> label, the labels in alphabetical order), and the SQL of the columns only some feeds have.
    SERVED = {
        "feed39_financial_restatements": {
            "kind": "restatement", "period_start": "res_begin_date", "period_end": "res_end_date",
            "flags": {"res_accounting": "accounting", "res_adverse": "adverse",
                      "res_clerical_errors": "clerical_error", "res_fraud": "fraud", "res_improves": "improves",
                      "res_other": "other", "quarterly_restated_only": "quarterly_only",
                      "res_sec_investigation": "sec_investigation"}},
        "feed20_nt": {
            "kind": "late_filing",
            "period_end": "CAST(try_strptime(regexp_extract(pe_date_num, '^[0-9]{8}'), '%Y%m%d') AS DATE)",
            "flags": {}},
        "feed17_director_and_officer_chan": {
            "kind": "officer_change", "person_key": "do_off_pers_key", "effective_date": "eff_date",
            "action": "action",
            "flags": {"is_bdmem_pers": "board_member", "is_c_level": "c_level", "is_ceo": "ceo", "is_cfo": "cfo",
                      "is_chair": "chair", "is_coo": "coo", "interim": "interim", "is_president": "president"}},
    }
    KINDS = tuple(spec["kind"] for spec in SERVED.values())

    def __init__(self):
        super().__init__(self.FIRST, self.LIBRARY, [], [], [], "file_date", 0, revisions=False)
        self.name = "wrds/audit"
        self.feeds = ("audit_flag",)                     # our companies' events, one row each (``tables.py``)
        self.schema = self.PARTS[self.FIRST][1]
        self.staging = self.STAGING[self.FIRST]

    def raw_path(self, as_of: date, part: str = FIRST) -> Path:
        return common.raw_dir(self.name) / as_of.isoformat() / f"{part}{wrds_session.RAW_SUFFIX}"

    def snapshot_file(self, as_of: str, part: str = FIRST) -> Path:
        return common.parquet_dir(self.name) / f"snapshot={as_of}" / f"{part}.parquet"

    def _parts(self) -> list[tuple]:
        return [(p,) for p in self.PARTS]

    def snapshots(self) -> list[str]:
        folder = common.parquet_dir(self.name)
        if not folder.is_dir():
            return []
        return sorted(d.name.split("=", 1)[1] for d in folder.iterdir()
                      if d.name.startswith("snapshot=") and all((d / f"{p}.parquet").is_file() for p in self.PARTS))

    def sql(self, part: str = FIRST, as_of=None, library: str | None = None) -> str:
        cols = ", ".join(c for c, _ in self.PARTS[part][1])
        return f"SELECT {cols} FROM {library or self.library}.{part}"

    def _full(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        return [wrds_session._ask(ctx, self.raw_path(as_of, part), self.sql(part), as_of) for part in self.PARTS]

    def full_rebuild_reason(self, ctx: base.RunContext) -> str | None:
        """A new snapshot is no reason to build the kind whole: ``audit_flag`` is the one table that reads these
        feeds, and every build makes it again from the newest snapshot."""
        return None

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        out = []
        for raw in raws:
            part = raw.name[: -len(wrds_session.RAW_SUFFIX)]
            _, schema, _ = self.PARTS[part]
            meta = base.read_raw_json(common.meta_path(raw))
            as_of = meta["as_of"]
            con = base.scratch_con()
            try:
                rows = f"SELECT DISTINCT * FROM ({wrds_session.raw_rows(raw, schema)})"
                if not con.execute(f"SELECT count(*) FROM ({rows})").fetchone()[0]:
                    raise base.SourceError(f"wrds {part}: the snapshot came back empty")
                for col, n in wrds_session.untyped(con, raw, schema).items():
                    ctx.issue("value_untyped", f"{part}.{col}", f"{n} row(s) nulled")
                every = ", ".join(f'"{c}" NULLS LAST' for c, _ in schema)
                select = (f"SELECT *, DATE '{as_of}' AS source_as_of, CAST({float(meta['fetched_at'])} AS DOUBLE) "
                          f"AS fetched_at, '{meta['run_id']}' AS run_id FROM ({rows}) "
                          f"ORDER BY {self.COMPANY} NULLS LAST, file_date NULLS LAST, {every}")
                out.append(base.write_parquet(con, select, self.snapshot_file(as_of, part)))
            finally:
                con.close()
            ctx.pending.setdefault(self.name, []).append(as_of)
        return out

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        snaps = self.snapshots()
        for part, (_, schema, _) in self.PARTS.items():
            common.stage_glob(con, self.STAGING[part], schema + PROVENANCE, common.parquet_dir(self.name),
                              f"snapshot={snaps[-1]}/{part}.parquet" if snaps else "snapshot=none/none")
        return {}

    def served_sql(self, part: str) -> str:
        """The rows of one staged feed in ``audit_flag``'s column order, for the companies of
        ``fundamental_company`` (``company_fkey`` against the CIK, both without leading zeros). A row with no
        filing day or no key says nothing a board could place, so it is left out."""
        spec, key = self.SERVED[part], self.PARTS[part][2]
        labels = ", ".join(f"CASE WHEN TRY_CAST(s.\"{c}\" AS DOUBLE) = 1 THEN '{label}' END"
                           for c, label in spec["flags"].items())
        flags = f"[x for x in [{labels}] if x IS NOT NULL]" if labels else "CAST([] AS VARCHAR[])"
        return f"""
            SELECT o.cik, '{spec["kind"]}' AS kind, s."{key}" AS event_key, {spec.get("person_key", "NULL")} AS
                   person_key, s.file_date, s.form_fkey AS form, {spec.get("effective_date", "NULL")} AS
                   effective_date, {spec.get("period_start", "NULL")} AS period_start,
                   {spec.get("period_end", "NULL")} AS period_end, {spec.get("action", "NULL")} AS action,
                   {flags} AS flags, '{self.name}' AS source, s.source_as_of, s.fetched_at, s.run_id
            FROM {self.STAGING[part]} s
            JOIN (SELECT DISTINCT cik, ltrim(cik, '0') AS k FROM fundamental_company) o
              ON o.k = ltrim(s.{self.COMPANY}, '0')
            WHERE s.file_date IS NOT NULL AND s."{key}" IS NOT NULL"""

    def note(self, con: duckdb.DuckDBPyConnection) -> str:
        """Per feed: its rows, its keys, how many of our companies it holds (``company_fkey`` against the CIK, both
        without leading zeros) and its newest filing day."""
        ours = con.execute("SELECT count(DISTINCT ltrim(cik, '0')) FROM fundamental_company").fetchone()[0]
        parts = []
        for part, (label, _, key) in self.PARTS.items():
            stg = self.STAGING[part]
            rows, keys, newest = con.execute(
                f'SELECT count(*), count(DISTINCT "{key}"), max(file_date) FROM {stg}').fetchone()
            if not rows:
                continue
            held = con.execute(f"""
                SELECT count(*) FROM (SELECT DISTINCT ltrim(cik, '0') AS cik FROM fundamental_company) c
                WHERE c.cik IN (SELECT ltrim({self.COMPANY}, '0') FROM {stg})""").fetchone()[0]
            parts.append(f"{label} {rows} rows ({keys} keys), {held} of {ours} Tier A companies, newest {newest}")
        if not parts:
            return "WRDS audit feeds: no snapshot yet"
        return "WRDS audit feeds (company_fkey is the CIK): " + "; ".join(parts)


FUNDQ = WrdsFund("fundq", "comp",
                 [("gvkey", "TEXT"), ("datadate", "DATE"), ("fyearq", "INTEGER"), ("fqtr", "INTEGER"),
                  ("fyr", "INTEGER"), ("rdq", "DATE")],
                 ["revtq", "cogsq", "oiadpq", "niq", "epspxq", "epsfxq", "atq", "dlttq", "dlcq", "cheq", "ceqq"],
                 ["gvkey", "datadate"], "datadate", YEARS, revisions=True)
FUNDA = WrdsFund("funda", "comp",
                 [("gvkey", "TEXT"), ("datadate", "DATE"), ("fyear", "INTEGER"), ("fyr", "INTEGER")],
                 ["revt", "cogs", "oiadp", "ni", "epspx", "epsfx", "at", "dltt", "dlc", "che", "ceq", "oancf", "capx"],
                 ["gvkey", "datadate"], "datadate", YEARS, revisions=True)
SEGMENTS = WrdsSegments()
EXRT = WrdsExrt()
AUDIT = WrdsAudit()
DATASETS = (FUNDQ, FUNDA, SEGMENTS, EXRT, AUDIT)
