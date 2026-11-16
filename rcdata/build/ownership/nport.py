"""``sec/nport``: the SEC's Form N-PORT data sets, every registered fund's holdings, newest quarter only (#354, C1).

``GET <RC_NPORT_INDEX_URL>`` (default ``<www.sec.gov>/data-research/sec-markets-data/form-n-port-data-sets``) links
one zip per quarter, ``<yyyy>q<n>_nport.zip`` (2019q4 on; about 440 MB each, measured 1 Nov 2026 on 2026q3). The
index read and the TSV load are the 13F sets' own (``sec13f_sets.listed``, ``sec13f_sets._load``). Only the newest
listed set is held (decision G, avo 16 Nov 2026: newest quarter only; history is C7, when a reader needs it). A set
held is never asked again; one held raw but not typed is typed on the next run.

The download is streamed to disk (``_download``): the zip never sits whole in the builder's memory, which a
``sec13f_sets.download`` of 440 MB would (twice, the answer and its zip check). Typing runs in a DuckDB file beside
the raw zip under :data:`MEMORY_LIMIT` and two threads, so the 5.6M holding rows spill to the HDD instead of the RAM.

Read members: ``SUBMISSION``, ``REGISTRANT``, ``FUND_REPORTED_INFO`` (the series, its assets) and
``FUND_REPORTED_HOLDING`` with ``IDENTIFIERS`` (the ISIN and ticker of a holding, the first of each when a holding
carries several). A CUSIP is kept only when it is nine letters or digits and not all zeros (the set writes ``N/A``
and ``000000000`` for none). Columns a set lacks are added empty (``sec13f_sets._load``'s ``add_missing``).

Raw: ``raw/sec/nport/<zip>`` with a ``.meta.json`` sidecar. Parquet: ``parquet/sec/nport/quarter=<set>/fund.parquet``
(one row per filing and series) and ``holdings.parquet`` (one row per reported holding). No served table yet: C2
(``etf_holdings_nport`` in ``ownership.duckdb``) rides the combined ownership bump, so ``build`` writes nothing and
``dirty`` is clean. ``heavy``: one run at a time per builder process (#812). Starts by hand.
"""
from __future__ import annotations

import os
import tempfile
import time
import zipfile
from datetime import date
from pathlib import Path

import duckdb
import httpx

from ....core import calendar
from .. import base, dirty
from . import KIND, sec, sec13f_sets

NAME = "sec/nport"
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


def index_url() -> str:
    return os.getenv(INDEX_ENV) or sec.www_base() + INDEX_PATH


def raw_dir() -> Path:
    return sec13f_sets.raw_dir(SUB)


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
    tables: tuple[str, ...] = ()
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
        # Newest quarter only (decision G): a backfill is the daily rule.
        self.to_parquet_all(ctx, self.fetch(ctx, end))

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        if base.raw_only():
            ctx.notes.append(f"{LABEL} data set {raw.name}: raw only, the zip is kept and not typed")
            return []
        quarter = quarter_of(raw.name)
        folder = parquet_dir() / f"quarter={quarter}"
        meta = sec13f_sets._meta(raw)
        info = base.read_raw_json(meta) if meta.exists() else {}
        with tempfile.TemporaryDirectory(dir=raw.parent, prefix=sec13f_sets.SCRATCH) as tmp:
            con = duckdb.connect(str(Path(tmp) / "set.duckdb"))
            try:
                con.execute(f"SET memory_limit = '{MEMORY_LIMIT}'; SET threads = 2; "
                            f"SET temp_directory = {base.sql_path(Path(tmp) / 'spill')}")
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
        return dirty.CLEAN            # no served table until C2

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        return {}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        return {"dataset": NAME, "result": "changed" if ctx.pending.get(NAME) else "unchanged",
                "source_as_of": (ctx.as_of or self.default_as_of()).isoformat(), "rows": 0, "added": 0,
                "removed": 0}


DATASET = Nport()
