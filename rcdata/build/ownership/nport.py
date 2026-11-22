"""``sec/nport``: the SEC's Form N-PORT data sets, every registered fund's holdings, newest quarter only (#354, C1).

``GET <RC_NPORT_INDEX_URL>`` (default ``<www.sec.gov>/data-research/sec-markets-data/form-n-port-data-sets``) links
one zip per quarter, ``<yyyy>q<n>_nport.zip`` (2019q4 on; about 440 MB each, measured 1 Nov 2026 on 2026q3). The
index read and the TSV load are the 13F sets' own (``sec13f_sets.listed``, ``sec13f_sets._load``). A daily run holds
the newest listed set only (decision G, avo 16 Nov 2026). A set held is never asked again; one held raw but not
typed is typed on the next run.

**History (C7, avo 22 Nov 2026: "eski ceyrekleride indir").** A backfill with a first day takes every listed
quarter whose filing window reaches it, **oldest first**, at most :data:`MAX_SETS_PER_RUN` a run, each under the
``sec`` cap and ``Pacer`` like the first one. 2019q4 to 2026q2 is 27 further sets, about 12 GB of raw zip, so a run
stops before the disk does: each download is refused when the raw disk has less free space than
:data:`MIN_FREE_SETS` (the zip plus the room its typing spills), with a note and a ``no_space`` issue, and the sets
already held are kept. A stopped or killed run resumes where it left off, because a held and typed set is skipped
and each quarter reports its own counts as it lands. **The served table is unchanged by history:** it is still
built from the newest typed quarter only, so no further quarter means a version bump or a store write.

The download is streamed to disk (``_download``): the zip never sits whole in the builder's memory, which a
``sec13f_sets.download`` of 440 MB would (twice, the answer and its zip check). Typing runs in a DuckDB file beside
the raw zip (``serving.connect_scratch_file``) under :data:`MEMORY_LIMIT` and two threads, so the 5.6M holding rows
spill to the HDD instead of the RAM.

Read members: ``SUBMISSION``, ``REGISTRANT``, ``FUND_REPORTED_INFO`` (the series, its assets) and
``FUND_REPORTED_HOLDING`` with ``IDENTIFIERS`` (the ISIN and ticker of a holding, the first of each when a holding
carries several). A CUSIP is kept only when it is nine letters or digits and not all zeros (the set writes ``N/A``
and ``000000000`` for none). Columns a set lacks are added empty (``sec13f_sets._load``'s ``add_missing``).

Raw: ``raw/sec/nport/<zip>`` with a ``.meta.json`` sidecar. Parquet: ``parquet/sec/nport/quarter=<set>/fund.parquet``
(one row per filing and series) and ``holdings.parquet`` (one row per reported holding). ``heavy``: one run at a time
per builder process (#812). Starts by hand.

Served (C2, avo 16 Nov 2026, Q11 of the 13F plan): ``etf_holdings_nport``, the holdings of the spine's ETFs only
(``etf.series_id``, ETNs left out), from each series' newest report in the newest typed quarter (report date, then
filing date, then accession), and only the positions whose CUSIP is one spine ticker's current CUSIP
(``common.spine_cusips``): bonds, derivatives, cash and unmapped lines stay in Parquet. Built whole, from one quarter,
whenever this dataset's Parquet changed; kept as it is on the live copy otherwise. Long equity only (``asset_cat``
``EC``, ``payoff_profile`` ``Long``): a short, a bond, a derivative or cash with a spine CUSIP is not a holding of the
fund's stock list (#1441, measured 22 Nov 2026: ~3,950 such rows were served).

**History (#1441, avo 22 Nov 2026):** ``etf_holdings_nport_history`` holds every typed quarter (2019q4 on): per
quarter, each spine ETF's newest report in that quarter and its long equity, **one row per holding** (a fund reports a
security on several lines: VXUS lists Banco Santander twice in 2026q3, 212,710,002 and 4 shares), keyed by its CUSIP,
else its ISIN, else its name. A holding no spine ticker holds is kept with ``ticker`` NULL (a foreign share by its
ISIN and country: TSMC in VXUS, $26.5B; a private share by its name), so the board shows the fund's whole stock list.
``ticker`` here is the spine's current CUSIP owner; ``rcdata.read.etf_holdings_history`` overlays the 13F CUSIP map
of the report's quarter (``sec13f_cusip_map``, Compustat's dated history first), so N-PORT and 13F name a CUSIP alike.
"""
from __future__ import annotations

import os
import shutil
import tempfile
import time
import zipfile
from datetime import date
from pathlib import Path

import duckdb
import httpx

from ....core import calendar
from ... import serving
from .. import base, dirty
from . import KIND, common, sec, sec13f_sets

NAME = "sec/nport"
TABLE = "etf_holdings_nport"
SERVED = [("etf_ticker", "TEXT"), ("series_id", "TEXT"), ("report_date", "DATE"), ("filed", "DATE"),
          ("accession", "TEXT"), ("ticker", "TEXT"), ("cusip", "TEXT"), ("issuer_name", "TEXT"),
          ("balance", "DOUBLE"), ("unit", "TEXT"), ("currency_value", "DOUBLE"), ("pct_of_net_assets", "DOUBLE"),
          ("asset_cat", "TEXT"), ("quarter", "TEXT")]
HISTORY = "etf_holdings_nport_history"
HISTORY_SERVED = [("etf_ticker", "TEXT"), ("series_id", "TEXT"), ("quarter", "TEXT"), ("report_date", "DATE"),
                  ("filed", "DATE"), ("accession", "TEXT"), ("ticker", "TEXT"), ("cusip", "TEXT"), ("isin", "TEXT"),
                  ("issuer_name", "TEXT"), ("country", "TEXT"), ("balance", "DOUBLE"), ("currency_value", "DOUBLE"),
                  ("pct_of_net_assets", "DOUBLE"), ("lines", "INTEGER")]
SCHEMAS = {TABLE: SERVED, HISTORY: HISTORY_SERVED}
# A fund's stock list: long equity lines only (shorts, bonds, derivatives and cash stay in Parquet).
LONG_EQUITY = "h.asset_cat = 'EC' AND h.payoff_profile = 'Long'"
INDEX_ENV = "RC_NPORT_INDEX_URL"
INDEX_PATH = "/data-research/sec-markets-data/form-n-port-data-sets"
SUFFIX = "_nport"
SUB = "nport"
LABEL = "N-PORT"
MEMBERS = ("SUBMISSION", "REGISTRANT", "FUND_REPORTED_INFO", "FUND_REPORTED_HOLDING", "IDENTIFIERS")
# The non-key columns read; a set without one gets it empty rather than failing the quarter.
OPTIONAL = {
    "SUBMISSION": ("FILING_DATE", "SUB_TYPE", "REPORT_ENDING_PERIOD", "REPORT_DATE"),
    "REGISTRANT": ("CIK", "REGISTRANT_NAME"),
    "FUND_REPORTED_INFO": ("SERIES_ID", "SERIES_NAME", "TOTAL_ASSETS", "NET_ASSETS"),
    "FUND_REPORTED_HOLDING": ("ISSUER_NAME", "ISSUER_TITLE", "ISSUER_LEI", "ISSUER_CUSIP", "BALANCE", "UNIT",
                              "CURRENCY_CODE", "CURRENCY_VALUE", "PERCENTAGE", "PAYOFF_PROFILE", "ASSET_CAT",
                              "ISSUER_TYPE", "INVESTMENT_COUNTRY"),
    "IDENTIFIERS": ("IDENTIFIER_ISIN", "IDENTIFIER_TICKER"),
}
MEMORY_LIMIT = "1GB"
CHUNK = 1 << 20
# C7: at most this many quarters a run, so one run is bounded in time and disk even when 27 are wanted; the next
# run takes the next ones, since a held and typed set is skipped.
MAX_SETS_PER_RUN = 4
# Free space the raw disk must keep before a set is asked: a zip is about 440 MB (measured 1 Nov 2026 on 2026q3)
# and typing it spills the unpacked TSVs beside it, so a quarter wants several GB in hand, not one.
MIN_FREE_SETS = 8 * 2**30


def index_url() -> str:
    return os.getenv(INDEX_ENV) or sec.www_base() + INDEX_PATH


def raw_dir() -> Path:
    return sec13f_sets.raw_dir(SUB)


def raw_dir_for_free() -> Path:
    """The existing folder whose disk the raw zips land on: the raw dir itself once made, else its nearest made
    parent, because ``shutil.disk_usage`` needs a path that is there."""
    path = raw_dir()
    while not path.exists() and path != path.parent:
        path = path.parent
    return path


def parquet_dir() -> Path:
    return base.parquet_root() / "sec" / "nport"


def quarter_of(name: str) -> str:
    """The partition key of a set: its zip name without the suffix (``2026q3``)."""
    return name[: -len(SUFFIX + ".zip")].lower()


def typed(name: str) -> bool:
    folder = parquet_dir() / f"quarter={quarter_of(name)}"
    return all((folder / f).exists() for f in ("fund.parquet", "holdings.parquet"))


def _download(ctx: base.RunContext, pacer: sec.Pacer, name: str, url: str) -> Path:
    """Stream the set to ``raw/sec/nport/<name>`` through ``.tmp`` and a rename; an answer that is not a zip is
    refused and not kept. Counted and logged as ``base.http_get`` counts and logs.

    shortcut: one attempt, no retry ladder (``base.http_get`` holds the body in memory); a failed run is asked
    again by the next one, since nothing is kept."""
    path = sec13f_sets.raw_path(name, SUB)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    pacer.wait()
    ctx.check_cap(sec.PROVIDER)
    ctx.count(sec.PROVIDER, calls=1, logged=True)
    started = time.monotonic()
    try:
        with ctx.http.stream("GET", url) as r:
            base._log_http(ctx, sec.PROVIDER, "GET", url, f"HTTP {r.status_code}", started)
            if r.status_code >= 400:
                ctx.count(sec.PROVIDER, failures=1, logged=True)
                raise base.SourceError(f"{LABEL} data set {name}: HTTP {r.status_code}")
            with open(tmp, "wb") as f:
                for chunk in r.iter_bytes(CHUNK):
                    f.write(chunk)
            last_modified = r.headers.get("last-modified")
    except httpx.HTTPError as e:
        base._log_http(ctx, sec.PROVIDER, "GET", url, type(e).__name__, started)
        ctx.count(sec.PROVIDER, failures=1, logged=True)
        tmp.unlink(missing_ok=True)
        raise base.SourceError(f"{LABEL} data set {name}: {type(e).__name__}") from e
    if not zipfile.is_zipfile(tmp):
        size = tmp.stat().st_size
        tmp.unlink()
        raise base.SourceError(f"{LABEL} data set {name}: the answer is not a zip ({size} bytes)")
    base.write_raw_json(sec13f_sets._meta(path), {"url": url, "last_modified": last_modified,
                                                  "fetched_at": time.time(), "run_id": ctx.run_id,
                                                  "bytes": tmp.stat().st_size})
    os.replace(tmp, path)
    return path


def _spine_etfs() -> list[tuple[str, str]]:
    """``(ticker, series_id)`` of the live spine's ETFs that carry a series and are not notes; empty without a spine
    or its ``etf`` table."""
    try:
        con = serving.open_read(common.SPINE)
    except serving.ServingFileMissing:
        return []
    try:
        return con.execute("SELECT ticker, series_id FROM etf WHERE series_id IS NOT NULL "
                           "AND NOT coalesce(is_etn, false) ORDER BY ticker").fetchall()
    except duckdb.Error:
        return []
    finally:
        con.close()


def _num(col: str) -> str:
    return f"TRY_CAST(replace(trim({col}), ',', '') AS DOUBLE)"


def _text(col: str) -> str:
    return f"nullif(trim({col}), '')"


def _fund_sql(quarter: str, fetched_at: float, run_id: str | None) -> str:
    day = sec13f_sets._day
    return f"""
        WITH s AS (SELECT * FROM z_submission
                   QUALIFY row_number() OVER (PARTITION BY trim(ACCESSION_NUMBER) ORDER BY rowid) = 1),
             r AS (SELECT * FROM z_registrant
                   QUALIFY row_number() OVER (PARTITION BY trim(ACCESSION_NUMBER) ORDER BY rowid) = 1)
        SELECT '{quarter}' AS quarter, trim(f.ACCESSION_NUMBER) AS accession,
               CAST(TRY_CAST(trim(r.CIK) AS BIGINT) AS VARCHAR) AS cik, {_text('r.REGISTRANT_NAME')} AS registrant,
               {_text('f.SERIES_ID')} AS series_id, {_text('f.SERIES_NAME')} AS series_name,
               upper({_text('s.SUB_TYPE')}) AS form, {day('s.FILING_DATE')} AS filed,
               {day('s.REPORT_ENDING_PERIOD')} AS period_end, {day('s.REPORT_DATE')} AS report_date,
               {_num('f.TOTAL_ASSETS')} AS total_assets, {_num('f.NET_ASSETS')} AS net_assets,
               CAST({float(fetched_at)!r} AS DOUBLE) AS fetched_at, {f"'{run_id}'" if run_id else 'NULL'} AS run_id
        FROM z_fund_reported_info f
        LEFT JOIN s ON trim(s.ACCESSION_NUMBER) = trim(f.ACCESSION_NUMBER)
        LEFT JOIN r ON trim(r.ACCESSION_NUMBER) = trim(f.ACCESSION_NUMBER)
        ORDER BY accession"""


def _holdings_sql(quarter: str) -> str:
    cusip = "upper(trim(h.ISSUER_CUSIP))"
    return f"""
        WITH i AS (SELECT trim(HOLDING_ID) AS holding_id, min({_text('IDENTIFIER_ISIN')}) AS isin,
                          min(upper({_text('IDENTIFIER_TICKER')})) AS ticker
                   FROM z_identifiers GROUP BY 1)
        SELECT '{quarter}' AS quarter, trim(h.ACCESSION_NUMBER) AS accession, trim(h.HOLDING_ID) AS holding_id,
               {_text('h.ISSUER_NAME')} AS issuer_name, {_text('h.ISSUER_TITLE')} AS issuer_title,
               {_text('h.ISSUER_LEI')} AS issuer_lei,
               CASE WHEN regexp_full_match({cusip}, '[0-9A-Z]{{9}}') AND {cusip} <> '000000000' THEN {cusip} END
                   AS cusip,
               i.isin, i.ticker, {_num('h.BALANCE')} AS balance, {_text('h.UNIT')} AS unit,
               {_text('h.CURRENCY_CODE')} AS currency, {_num('h.CURRENCY_VALUE')} AS currency_value,
               {_num('h.PERCENTAGE')} AS pct_of_net_assets, {_text('h.PAYOFF_PROFILE')} AS payoff_profile,
               {_text('h.ASSET_CAT')} AS asset_cat, {_text('h.ISSUER_TYPE')} AS issuer_type,
               {_text('h.INVESTMENT_COUNTRY')} AS country
        FROM z_fund_reported_holding h LEFT JOIN i ON i.holding_id = trim(h.HOLDING_ID)
        ORDER BY accession"""


class Nport:
    name = NAME
    kind = KIND
    providers = (sec.PROVIDER,)
    tables = (TABLE, HISTORY)
    feeds: tuple[str, ...] = ()       # it serves its own table; no 13F table is built from its rows
    cadence = "monthly"
    backfill_needs_from = False
    starts_by_hand = True             # the first run is a 440 MB request: avo's written word first (#354 C3)
    heavy = True

    def default_as_of(self) -> date:
        return calendar.today_ny()

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        sec13f_sets._clear_scratch(ctx, SUB, LABEL)
        pacer = sec.Pacer(ctx)
        sets = sec13f_sets.listed(ctx, pacer, index_url(), SUFFIX, LABEL)
        name = max(sets, key=lambda n: (sets[n][1], n))
        path = sec13f_sets.raw_path(name, SUB)
        if path.exists():
            ctx.notes.append(f"{LABEL} data set {name}: held" + ("" if typed(name) else ", typed now"))
            return [] if typed(name) else [path]
        ctx.pending.setdefault(NAME, []).append(name)
        return [_download(ctx, pacer, name, sets[name][2])]

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        """Without a first day: the daily rule, the newest quarter only (decision G). With one (``--from``, C7):
        every listed quarter whose filing window reaches ``start``, oldest first, at most
        :data:`MAX_SETS_PER_RUN` a run and only while the raw disk keeps :data:`MIN_FREE_SETS` free. A set already
        held and typed is skipped, so a stopped run resumes; a set held raw is typed without being asked again."""
        if start is None:
            self.to_parquet_all(ctx, self.fetch(ctx, end))
            return
        sec13f_sets._clear_scratch(ctx, SUB, LABEL)
        pacer = sec.Pacer(ctx)
        sets = sec13f_sets.listed(ctx, pacer, index_url(), SUFFIX, LABEL)
        wanted = sorted((n for n, (first, last, _) in sets.items() if last >= start and first <= end),
                        key=lambda n: (sets[n][0], n))
        todo = [n for n in wanted if not typed(n)]
        ctx.notes.append(f"{LABEL} history: {len(wanted)} listed quarter(s) from {start} to {end}, "
                         f"{len(wanted) - len(todo)} already typed, {len(todo)} to go")
        for name in todo[:MAX_SETS_PER_RUN]:
            path = sec13f_sets.raw_path(name, SUB)
            if not path.exists():
                free = shutil.disk_usage(raw_dir_for_free()).free
                if free < MIN_FREE_SETS:
                    ctx.notes.append(f"{LABEL} history: stopped before {name}, "
                                     f"{free / 2**30:.1f} GiB free and a quarter needs "
                                     f"{MIN_FREE_SETS / 2**30:.0f} GiB")
                    ctx.issue("no_space", name, f"{free / 2**30:.1f} GiB free on the raw disk")
                    return
                ctx.pending.setdefault(NAME, []).append(name)
                path = _download(ctx, pacer, name, sets[name][2])
            self.to_parquet(ctx, path)
        left = len(todo) - min(len(todo), MAX_SETS_PER_RUN)
        if left:
            ctx.notes.append(f"{LABEL} history: {left} quarter(s) left, the next run takes them")

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        if base.raw_only():
            ctx.notes.append(f"{LABEL} data set {raw.name}: raw only, the zip is kept and not typed")
            return []
        quarter = quarter_of(raw.name)
        folder = parquet_dir() / f"quarter={quarter}"
        meta = sec13f_sets._meta(raw)
        info = base.read_raw_json(meta) if meta.exists() else {}
        with tempfile.TemporaryDirectory(dir=serving.scratch_dir(raw.parent.name, raw.parent),
                                         prefix=sec13f_sets.SCRATCH) as tmp:
            con = serving.connect_scratch_file(Path(tmp) / "set.duckdb", MEMORY_LIMIT)
            try:
                con.execute("SET threads = 2")
                sec13f_sets._load(con, raw, Path(tmp), raw.name, ctx.notes, MEMBERS, OPTIONAL, LABEL)
                # The fund file last: it is the "typed" mark (``typed``), so a run killed between the two types again.
                out = [base.write_parquet(con, _holdings_sql(quarter), folder / "holdings.parquet"),
                       base.write_parquet(con, _fund_sql(quarter, info.get("fetched_at") or raw.stat().st_mtime,
                                                         info.get("run_id") or ctx.run_id), folder / "fund.parquet")]
                n_fund, n_hold, no_cusip = con.execute(
                    f"SELECT (SELECT count(*) FROM read_parquet({base.sql_path(out[1])})), count(*), "
                    f"count(*) FILTER (WHERE cusip IS NULL) FROM read_parquet({base.sql_path(out[0])})").fetchone()
            finally:
                con.close()
        ctx.notes.append(f"{LABEL} data set {raw.name}: {n_fund} series filings, {n_hold} holdings "
                         f"({no_cusip} without a CUSIP)")
        return out

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        return [p for raw in raws for p in self.to_parquet(ctx, raw)]

    def dirty(self, ctx: base.RunContext):
        """Clean when none of its Parquet changed since the live file was built; else the table is built whole."""
        changed = getattr(ctx, "changed", None)
        root = parquet_dir().resolve()
        if changed is not None and not any(root in Path(p).resolve().parents for p in changed):
            return dirty.CLEAN
        return dirty.ALL

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        plan = getattr(ctx, "incremental", None)
        if (plan is not None and common.has_table(con, TABLE) and common.has_table(con, HISTORY)
                and plan.dirty.get(NAME, dirty.ALL).clean):
            return {TABLE: common.count(con, TABLE), HISTORY: common.count(con, HISTORY)}
        con.execute(f"DROP TABLE IF EXISTS {TABLE}")
        con.execute(f"DROP TABLE IF EXISTS {HISTORY}")
        held = sorted(f for f in parquet_dir().glob("quarter=*") if (f / "fund.parquet").exists()
                      and (f / "holdings.parquet").exists()) if parquet_dir().exists() else []
        etfs = _spine_etfs()
        cusips = common.spine_cusips() or {}
        if not held or not etfs or not cusips:
            ctx.notes.append(f"{TABLE}: " + ("no typed N-PORT quarter" if not held else "no live spine ETFs or CUSIPs"))
            return {TABLE: common.create_table(con, TABLE, SERVED), HISTORY: common.create_table(con, HISTORY,
                                                                                                  HISTORY_SERVED)}
        # The newest quarter by its set's window (``2026q3`` sorts as its name; a dated name by its first day).
        newest = max(held, key=lambda f: (sec13f_sets.window(f.name[8:] + SUFFIX + ".zip", SUFFIX) or (date.min,))[0])
        common.temp_rows(con, "_np_etf", [("etf_ticker", "TEXT"), ("series_id", "TEXT")],
                         [{"etf_ticker": t, "series_id": s} for t, s in etfs])
        common.temp_rows(con, "_np_cusip", [("cusip", "TEXT"), ("ticker", "TEXT")],
                         [{"cusip": c, "ticker": t} for c, t in cusips.items()])
        fund, hold = (base.sql_path(newest / n) for n in ("fund.parquet", "holdings.parquet"))
        n = common.create_table(con, TABLE, SERVED, f"""
            WITH f AS (SELECT * FROM read_parquet({fund})
                       QUALIFY row_number() OVER (PARTITION BY series_id
                                                  ORDER BY report_date DESC NULLS LAST, filed DESC, accession DESC) = 1)
            SELECT e.etf_ticker, f.series_id, f.report_date, f.filed, f.accession, c.ticker, h.cusip, h.issuer_name,
                   h.balance, h.unit, h.currency_value, h.pct_of_net_assets, h.asset_cat, f.quarter
            FROM f JOIN _np_etf e ON e.series_id = f.series_id
            JOIN read_parquet({hold}) h ON h.accession = f.accession
            JOIN _np_cusip c ON c.cusip = h.cusip
            WHERE {LONG_EQUITY}
            ORDER BY e.etf_ticker, h.currency_value DESC NULLS LAST, c.ticker""")
        funds = con.execute(f"SELECT count(DISTINCT etf_ticker) FROM {TABLE}").fetchone()[0]
        ctx.notes.append(f"{TABLE}: {n} holdings of {funds} spine ETFs, quarter {newest.name[8:]}")
        hist = self._history(con, held)
        con.execute("DROP TABLE _np_etf; DROP TABLE _np_cusip")
        quarters, mapped = con.execute(f"SELECT count(DISTINCT quarter), count(ticker) FROM {HISTORY}").fetchone()
        ctx.notes.append(f"{HISTORY}: {hist} holdings over {quarters} quarters ({hist - mapped} without a spine ticker)")
        return {TABLE: n, HISTORY: hist}

    @staticmethod
    def _history(con: duckdb.DuckDBPyConnection, held: list[Path]) -> int:
        """``etf_holdings_nport_history`` from every typed quarter: each spine ETF's newest report in each quarter
        (``_np_etf``), its long equity summed per holding, the spine ticker of its CUSIP (``_np_cusip``) or none.

        One quarter at a time: the whole history in one query (13.1M rows, 28 quarters) peaked at 3.83 GB against the
        4 GB scope on homesrv (measured 22 Nov 2026, PR #1445); a quarter alone is about 600K rows."""
        common.create_table(con, HISTORY, HISTORY_SERVED)
        names = ", ".join(f'"{c}"' for c, _ in HISTORY_SERVED)
        for q in held:
            con.execute(f"INSERT INTO {HISTORY} SELECT {names} FROM ({Nport._history_quarter(q)})")
        return common.count(con, HISTORY)

    @staticmethod
    def _history_quarter(q: Path) -> str:
        funds, holds = base.sql_path(q / "fund.parquet"), base.sql_path(q / "holdings.parquet")
        return f"""
            WITH f AS (SELECT * FROM read_parquet({funds}, union_by_name = true)
                       QUALIFY row_number() OVER (PARTITION BY quarter, series_id
                                                  ORDER BY report_date DESC NULLS LAST, filed DESC, accession DESC) = 1),
                 r AS (SELECT e.etf_ticker, f.series_id, f.quarter, f.report_date, f.filed, f.accession,
                              coalesce(h.cusip, h.isin, upper(trim(h.issuer_name))) AS holding,
                              h.cusip, h.isin, h.issuer_name, h.country, h.balance, h.currency_value,
                              h.pct_of_net_assets
                       FROM f JOIN _np_etf e ON e.series_id = f.series_id
                       JOIN read_parquet({holds}, union_by_name = true) h
                         ON h.accession = f.accession AND h.quarter = f.quarter
                       WHERE {LONG_EQUITY} AND coalesce(h.cusip, h.isin, h.issuer_name) IS NOT NULL)
            SELECT r.etf_ticker, r.series_id, r.quarter, r.report_date, r.filed, r.accession, c.ticker,
                   min(r.cusip) AS cusip, min(r.isin) AS isin, min(r.issuer_name) AS issuer_name,
                   min(r.country) AS country, sum(r.balance) AS balance, sum(r.currency_value) AS currency_value,
                   sum(r.pct_of_net_assets) AS pct_of_net_assets, CAST(count(*) AS INTEGER) AS lines
            FROM r LEFT JOIN _np_cusip c ON c.cusip = r.cusip
            GROUP BY r.etf_ticker, r.series_id, r.quarter, r.report_date, r.filed, r.accession, r.holding, c.ticker
            ORDER BY r.etf_ticker, r.quarter, currency_value DESC NULLS LAST, issuer_name"""

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        # both served tables: a build that changes only the history must not read as unchanged
        diffs = [base.compare_with_live(con, KIND, TABLE, ["etf_ticker", "accession", "cusip"]),
                 base.compare_with_live(con, KIND, HISTORY, ["etf_ticker", "quarter", "accession", "cusip", "isin",
                                                             "issuer_name", "balance"])]
        added, removed = sum(d[0] for d in diffs), sum(d[1] for d in diffs)
        return {"dataset": NAME, "result": "changed" if added or removed else "unchanged",
                "source_as_of": (ctx.as_of or self.default_as_of()).isoformat(),
                "rows": common.count(con, TABLE) + common.count(con, HISTORY), "added": added, "removed": removed}


DATASET = Nport()
