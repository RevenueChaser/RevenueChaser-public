"""``delisted/serving``: the delisted serving store, built from the CRSP Parquet already on disk (no fetch, no network).

**Tables** (``delisted.duckdb``, serving schema version 1), every one keyed on ``permno:<PERMNO>``:

- ``delisted_security``: one row per delisted PERMNO -- its newest CRSP delisting (date, price and return), its
  Compustat ``gvkey``/``iid`` and the CIK where the link exists, its header CUSIP, its last ticker, its first and
  last priced session and how many sessions it has here;
- ``delisted_security_symbol``: the tickers the security traded under, each with the session range it was in use
  (``valid_from``..``valid_to``, both inclusive; never open-ended, because the security is dead). A ticker a
  security held twice is two rows, so a reader that must resolve a ticker as of a day can;
- ``delisted_price_bar_daily``: **the columns of** ``price_bar_daily`` (``prices/serving.PRICE_BAR``), nominal, from
  ``crsp.dsf_v2``, so a reader unions the two deliberately and the live table never widens;
- ``delisted_corporate_action``: the columns of ``corporate_action``, from the two CRSP columns the fetch already
  stores -- the splits its cumulative price factor records (``dlycumfacpr``) and the ordinary cash dividends
  (``dlyorddivamt``) -- so a reader can put a dead name's bars on one basis.

**Who delisted.** CRSP's own delisting table, ``crsp_a_stock.stkdelists`` (staged by ``wrds/prices``): a PERMNO with a
delisting date. Its history is every ``dsf_v2`` session it has from :data:`HISTORY_FROM` on.

**What is not here, and why.** CRSP's delisting *code* (the reason: merger, dropped, moved) is not on disk -- the
fetch asks ``stkdelists`` without the type-code columns (``wrds_history.DELIST``), so this layer cannot carry it
without one more snapshot query, which is a change to the ``prices`` fetch and its own PR (#1219 follow-up). CRSP's
own day return (``dlyret``) is on disk but not served: ``delisted_price_bar_daily`` holds exactly
``price_bar_daily``'s columns. Share type is not fetched either, so this layer cannot yet tell a dead stock from a
dead fund (avo's default was "stocks first, funds later"); every delisted PERMNO is served and the reader can cut
on its own.

**Attended, built whole.** One backfill from the Parquet on disk, then with the other WRDS datasets' monthly run
(#1219): never due on its own, run from the CLI on the server
(``python -m revenuechaser.rcdata.build backfill delisted/serving``). There is no daily run and no scope to widen.

**Append-only**, so the ordinary shrink guard refuses a build that lost rows and no table of this kind belongs in
``SHRINKS_BY_CHOICE``. Its own serving version, its own ``prev`` file and its own backup step: a bad ``delisted``
build cannot touch live prices.
"""
from __future__ import annotations

import logging
from datetime import date

import duckdb

from ... import serving as _serving
from .. import base
from ..prices import stage as prices_stage, wrds_history
from ..prices import serving as prices_serving
from . import KIND

logger = logging.getLogger(__name__)

NAME = "delisted/serving"
SECURITY = "delisted_security"
SYMBOL = "delisted_security_symbol"
BAR = "delisted_price_bar_daily"
ACTION = "delisted_corporate_action"
TABLES = (SECURITY, SYMBOL, BAR, ACTION)

#: The first session this layer serves. avo's default of 20 Nov 2026 is the fetch's own start, Compustat's earliest
#: priced day, so the delisted history reaches as far back as the live one; CRSP itself holds 1925 on. One constant,
#: because the start is avo's to change.
HISTORY_FROM = wrds_history.COMPUSTAT_START
#: The DuckDB variable the queries read it through, set once at the top of the build (``prices/serving``'s own
#: ``rc_build_date`` pattern): the number stays one Python constant rather than being baked into every SQL string.
FROM_VAR = "rc_delisted_from"
_FROM = f"getvariable('{FROM_VAR}')"
#: The source name every row of this kind carries: CRSP, as ``prices`` names it.
SOURCE = wrds_history.CRSP
#: A ``dlycumfacpr`` ratio further from 1 than this is a split (``wrds_history._CRSP_SPLIT_ROWS``' own threshold).
SPLIT_EPS = 1e-6

#: The staging tables this build makes over the ``wrds/prices`` Parquet. Views, not copies: a TEMP copy of 40 years
#: of ``dsf_v2`` (66M rows) is what filled 92 GB of spill on the prices build (``prices/stage.view``).
STG_DSF, STG_DELIST, STG_SECD = "stg_del_dsf", "stg_del_delist", "stg_del_secd"

DELISTED_SECURITY = [("security_id", "TEXT"), ("permno", "TEXT"), ("gvkey", "TEXT"), ("iid", "TEXT"),
                     ("cik", "TEXT"), ("cusip", "TEXT"), ("last_symbol", "TEXT"), ("link", "TEXT"),
                     ("first_session", "DATE"), ("last_session", "DATE"), ("sessions", "BIGINT"),
                     ("delisting_date", "DATE"), ("delisting_price", "DOUBLE"), ("delisting_return", "DOUBLE"),
                     ("source", "TEXT"), ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]
DELISTED_SYMBOL = [("security_id", "TEXT"), ("permno", "TEXT"), ("symbol", "TEXT"), ("valid_from", "DATE"),
                   ("valid_to", "DATE"), ("sessions", "BIGINT"), ("source", "TEXT")]
#: Exactly ``price_bar_daily``'s and ``corporate_action``'s columns (#1219): the live tables are the shape, read from
#: them rather than restated, so a column added there is a build error here and not a silent difference.
DELISTED_BAR = list(prices_serving.PRICE_BAR)
DELISTED_ACTION = list(prices_serving.CORPORATE_ACTION)
SCHEMAS = {SECURITY: DELISTED_SECURITY, SYMBOL: DELISTED_SYMBOL, BAR: DELISTED_BAR, ACTION: DELISTED_ACTION}
#: The key of each table, checked after its insert (:func:`_refuse_duplicates`). No ``PRIMARY KEY`` is written: the
#: bars are a row per security **and** session and DuckDB holds a key's index in memory for the whole insert, which
#: is what ran the prices build out of its ``memory_limit`` (``prices/serving.MAY_DROP_PRIMARY_KEY``).
KEYS = {SECURITY: ("security_id",), SYMBOL: ("security_id", "symbol", "valid_from"),
        BAR: ("security_id", "session_date"), ACTION: ("security_id", "ex_date", "action", "source_id")}

#: The delisted securities: one row per PERMNO, its newest delisting (a PERMNO relisted and delisted again has two
#: ``stkdelists`` rows; the newest is the one that ended it).
DELISTED_PERMNO_SQL = f"""
    SELECT permno, delistingdt, deldtprc, delret, source_as_of, fetched_at, run_id
    FROM {STG_DELIST} WHERE permno IS NOT NULL AND delistingdt IS NOT NULL
    QUALIFY row_number() OVER (PARTITION BY permno ORDER BY delistingdt DESC) = 1"""

#: Every priced session of those PERMNOs from :data:`HISTORY_FROM` on, in ``price_bar_daily``'s shape. A negative
#: ``dlyprc`` is CRSP's bid/ask midpoint, read ``abs`` as the prices store reads it; ``shrout`` is thousands of
#: shares. ``cik`` is NULL: CRSP carries none, and the one ``delisted_security`` links is the issuer's, not the bar's.
BAR_SQL = f"""
    SELECT 'permno:' || d.permno AS security_id, d.dlycaldt AS session_date,
           nullif(upper(trim(d.ticker)), '') AS symbol, CAST(NULL AS TEXT) AS cik,
           d.dlyopen AS open, d.dlyhigh AS high, d.dlylow AS low, abs(d.dlyprc) AS close, d.dlyvol AS volume,
           CAST(NULL AS DOUBLE) AS vwap, CAST(NULL AS BIGINT) AS trade_count,
           d.shrout * {wrds_history.CRSP_SHARES_UNIT} AS shares_outstanding, '{SOURCE}' AS source,
           d.source_as_of, d.fetched_at, d.run_id
    FROM {STG_DSF} d JOIN _delisted_permno p USING (permno)
    WHERE d.dlyprc IS NOT NULL AND d.dlyprc <> 0 AND d.dlycaldt >= {_FROM}"""

#: Each ticker with the contiguous session range it was in use, read from the bars just built: two
#: ``row_number()``s whose difference is constant inside one run of the same symbol, so a ticker a security held,
#: lost and held again is two rows rather than one span covering the gap.
SYMBOL_SQL = f"""
    WITH s AS (SELECT security_id, session_date, symbol FROM {BAR} WHERE symbol IS NOT NULL),
         g AS (SELECT *, row_number() OVER (PARTITION BY security_id ORDER BY session_date)
                         - row_number() OVER (PARTITION BY security_id, symbol ORDER BY session_date) AS grp
               FROM s)
    SELECT security_id, replace(security_id, 'permno:', '') AS permno, symbol, min(session_date) AS valid_from,
           max(session_date) AS valid_to, count(*) AS sessions, '{SOURCE}' AS source
    FROM g GROUP BY security_id, permno, symbol, grp"""

#: The Compustat security of a delisted PERMNO: its newest header CUSIP (8 characters) against a ``comp.secd``
#: CUSIP. One ``gvkey:iid`` per CUSIP (the lowest, so two builds agree), and the link is named (``link``) so a
#: reader can tell a joined name from an unjoined one. A PERMNO with no Compustat CUSIP has no fundamentals of ours,
#: which is why the bars come first (#1219's risk).
LINK_SQL = f"""
    WITH h AS (SELECT d.permno, left(arg_max_null(d.hdrcusip, d.dlycaldt), 8) AS c8
               FROM {STG_DSF} d JOIN _delisted_permno p USING (permno)
               WHERE d.hdrcusip IS NOT NULL GROUP BY d.permno),
         comp AS (SELECT left(cusip, 8) AS c8, min(gvkey || ':' || iid) AS gid FROM {STG_SECD}
                  WHERE cusip IS NOT NULL GROUP BY 1)
    SELECT h.permno, h.c8 AS cusip, comp.gid, 'hdrcusip' AS how FROM h LEFT JOIN comp USING (c8)"""

#: One row per delisted PERMNO: its delisting, its link and what its bars span.
SECURITY_SQL = f"""
    WITH span AS (SELECT security_id, min(session_date) AS first_session, max(session_date) AS last_session,
                         count(*) AS sessions, arg_max_null(symbol, session_date) AS last_symbol
                  FROM {BAR} GROUP BY security_id)
    SELECT 'permno:' || p.permno AS security_id, p.permno,
           split_part(l.gid, ':', 1) AS gvkey, split_part(l.gid, ':', 2) AS iid, sp.cik, l.cusip,
           b.last_symbol, CASE WHEN l.gid IS NULL THEN NULL ELSE l.how END AS link,
           b.first_session, b.last_session, coalesce(b.sessions, 0) AS sessions,
           p.delistingdt AS delisting_date, p.deldtprc AS delisting_price, p.delret AS delisting_return,
           '{SOURCE}' AS source, p.source_as_of, p.fetched_at, p.run_id
    FROM _delisted_permno p
    LEFT JOIN _delisted_link l USING (permno)
    LEFT JOIN span b ON b.security_id = 'permno:' || p.permno
    LEFT JOIN _delisted_spine sp ON sp.gid = l.gid"""

#: The splits CRSP's cumulative price factor records, for the delisted names only. A session whose ``dlycumfacpr``
#: differs from the previous session's of the **same answer** is a split of ratio previous / today's (new over old
#: shares, the store's convention); two rows of different answers are not compared, because a year partition keeps
#: the factor basis of the day it was asked (``wrds_history.COMP_ADJ``'s own rule).
SPLIT_SQL = f"""
    SELECT 'permno:' || x.permno AS security_id, x.dlycaldt AS ex_date, 'split' AS action,
           CASE WHEN x.ratio < 1 THEN 'reverse_split' ELSE 'forward_split' END AS action_type,
           x.ratio AS ratio, CAST(NULL AS DOUBLE) AS amount, CAST(NULL AS TEXT) AS currency, false AS special,
           true AS applied, CAST(NULL AS TEXT) AS not_applied_why, CAST(NULL AS TEXT) AS symbol,
           CAST(NULL AS TEXT) AS new_symbol, CAST(NULL AS DATE) AS record_date, CAST(NULL AS DATE) AS payable_date,
           CAST(NULL AS DATE) AS process_date, '{SOURCE}' AS source,
           'crspsplit:' || x.permno || ':' || CAST(x.dlycaldt AS TEXT) AS source_id,
           x.source_as_of, x.fetched_at, x.run_id
    FROM (SELECT d.permno, d.dlycaldt, d.source_as_of, d.fetched_at, d.run_id,
                 lag(d.dlycumfacpr) OVER w / d.dlycumfacpr AS ratio, lag(d.run_id) OVER w AS prev_run
          FROM {STG_DSF} d JOIN _delisted_permno p USING (permno)
          WHERE d.dlycumfacpr > 0 AND d.dlycaldt >= {_FROM}
          WINDOW w AS (PARTITION BY d.permno ORDER BY d.dlycaldt)) x
    WHERE x.prev_run = x.run_id AND x.ratio IS NOT NULL AND abs(ln(x.ratio)) > {SPLIT_EPS}"""

#: The ordinary cash dividends the same rows carry (``dlyorddivamt``, the amount going ex that session).
DIVIDEND_SQL = f"""
    SELECT 'permno:' || d.permno AS security_id, d.dlycaldt AS ex_date, 'cash_dividend' AS action,
           'cash_dividend' AS action_type, CAST(NULL AS DOUBLE) AS ratio, d.dlyorddivamt AS amount,
           'USD' AS currency, false AS special, true AS applied, CAST(NULL AS TEXT) AS not_applied_why,
           CAST(NULL AS TEXT) AS symbol, CAST(NULL AS TEXT) AS new_symbol, CAST(NULL AS DATE) AS record_date,
           CAST(NULL AS DATE) AS payable_date, CAST(NULL AS DATE) AS process_date, '{SOURCE}' AS source,
           'crspdiv:' || d.permno || ':' || CAST(d.dlycaldt AS TEXT) AS source_id,
           d.source_as_of, d.fetched_at, d.run_id
    FROM {STG_DSF} d JOIN _delisted_permno p USING (permno)
    WHERE d.dlyorddivamt IS NOT NULL AND d.dlyorddivamt > 0
      AND d.dlycaldt >= {_FROM}"""


def _parquet_dir(table: str):
    return base.parquet_root() / "wrds" / "prices" / table


def _year_files(table: str) -> list:
    return [f for _, f in prices_stage.partitions(_parquet_dir(table), "year")]


def _newest_snapshot(table: str) -> list:
    snaps = prices_stage.partitions(_parquet_dir(table), "snapshot")
    return [snaps[-1][1]] if snaps else []


def stage_sources(con: duckdb.DuckDBPyConnection) -> None:
    """The three ``wrds/prices`` Parquet trees this build reads, as TEMP views (never copies): CRSP's daily file,
    CRSP's delisting snapshot and Compustat's daily file (the CUSIP link only). A tree with no partition yet is an
    empty typed view, so the build runs on a server that has never fetched (and in a test)."""
    schema = wrds_history.DSF + wrds_history.PROVENANCE
    prices_stage.view(con, STG_DSF, schema, _year_files("dsf"))
    # ``added_later``: the snapshot on disk is the four-column one the fetch asked before #1293, and a snapshot is
    # re-asked only when it is ``SNAPSHOT_DAYS`` old, so the type-code columns are read as NULL until then. Without
    # it every missing column resolves to its own alias and DuckDB refuses the view (Binder Error: column
    # ``deldtprcflg`` cannot be referenced before it is defined), which is what the first attended run on homesrv
    # hit, four seconds in, before any file was written (27 Nov 2026).
    prices_stage.view(con, STG_DELIST, wrds_history.DELIST + wrds_history.PROVENANCE, _newest_snapshot("stkdelists"),
                      added_later=wrds_history.DELIST_ADDED)
    prices_stage.view(con, STG_SECD, wrds_history.SECD + wrds_history.PROVENANCE, _year_files("secd"),
                      added_later=wrds_history.SECD_ADDED)


def _spine_link(con: duckdb.DuckDBPyConnection) -> int:
    """``_delisted_spine``: ``{gvkey:iid -> cik}`` from the **live** spine, read-only, so a delisted share class of a
    company that still files gets its CIK. Empty before a first spine build, and for every name the spine never
    held -- which is most of them, by definition."""
    con.execute("CREATE OR REPLACE TEMP TABLE _delisted_spine (gid TEXT, cik TEXT)")
    live = _serving.live_path("spine")
    if not live.exists():
        return 0
    con.execute(f"ATTACH {base.sql_path(live)} AS live_spine (READ_ONLY)")
    try:
        con.execute("INSERT INTO _delisted_spine SELECT gvkey || ':' || iid, min(cik) FROM live_spine.security "
                    "WHERE nullif(gvkey, '') IS NOT NULL AND nullif(iid, '') IS NOT NULL AND nullif(cik, '') "
                    "IS NOT NULL GROUP BY 1")
    finally:
        con.execute("DETACH live_spine")
    return prices_stage.count(con, "_delisted_spine")


def compare_live(con: duckdb.DuckDBPyConnection, table: str, columns: list[str]) -> tuple[int, int]:
    """``(added, removed)``: rows of the build's ``table`` against the live ``delisted.duckdb`` on ``columns``. No
    live file or no such table in it: every row is added. ``prices/stage.compare_live`` cannot stand in for this --
    it names the live **prices** file in its own code -- and a check of this kind must never read that one."""
    cols = ", ".join(f'"{c}"' for c in columns)
    new_rows = int(con.execute(f'SELECT count(*) FROM "{table}"').fetchone()[0])
    live = _serving.live_path(KIND)
    if not live.exists():
        return new_rows, 0
    con.execute(f"ATTACH {base.sql_path(live)} AS live_delisted (READ_ONLY)")
    try:
        known = {r[0] for r in con.execute(
            "SELECT table_name FROM duckdb_tables() WHERE database_name = 'live_delisted'").fetchall()}
        if table not in known:
            return new_rows, 0
        fresh, old = f'SELECT {cols} FROM "{table}"', f'SELECT {cols} FROM live_delisted."{table}"'
        added = con.execute(f"SELECT count(*) FROM ({fresh} EXCEPT ALL {old})").fetchone()[0]
        removed = con.execute(f"SELECT count(*) FROM ({old} EXCEPT ALL {fresh})").fetchone()[0]
        return int(added), int(removed)
    finally:
        con.execute("DETACH live_delisted")


def _create(con: duckdb.DuckDBPyConnection, table: str, select: str) -> int:
    """``table`` with its own schema, loaded from ``select`` by column name; its row count."""
    schema = SCHEMAS[table]
    cols = ", ".join(f'"{c}" {t}' for c, t in schema)
    names = ", ".join(f'"{c}"' for c, _ in schema)
    con.execute(f"CREATE TABLE {table} ({cols})")
    con.execute(f"INSERT INTO {table} ({names}) SELECT {names} FROM ({select})")
    return prices_stage.count(con, table)


def duplicate_keys(con: duckdb.DuckDBPyConnection, table: str, limit: int = 10) -> list[tuple]:
    """The keys of ``table`` that hold more than one row, at most ``limit`` of them: the check that stands in for the
    ``PRIMARY KEY`` this kind does not write."""
    key = ", ".join(f'"{c}"' for c in KEYS[table])
    return con.execute(f"SELECT {key}, count(*) AS n FROM {table} GROUP BY ALL HAVING count(*) > 1 "
                       f"ORDER BY n DESC LIMIT {int(limit)}").fetchall()


def _refuse_duplicates(con: duckdb.DuckDBPyConnection, table: str) -> None:
    """A repeated key is a source the build cannot read as one row per key (a year partition written twice), not a
    number to serve: the build fails and the live file is not touched."""
    found = duplicate_keys(con, table)
    if found:
        named = ", ".join(":".join(str(v) for v in row[:-1]) + f" x{row[-1]}" for row in found)
        raise base.SourceError(f"{table}: {len(found)} repeated key(s) in the CRSP Parquet, e.g. {named}")


class DelistedServing:
    name = NAME
    kind = KIND
    #: It fetches nothing: the Parquet is ``wrds/prices``' (declared, so ``dirty.read_dirs`` sees a change there).
    parquet_reads = ("wrds/prices",)
    providers: tuple[str, ...] = ()
    tables = TABLES
    feeds: tuple[str, ...] = ()        # it builds every served table of its kind itself
    #: With the other WRDS datasets' monthly run (#1219): attended, so it is never due on its own and the hourly
    #: pass never starts it. One backfill from the Parquet on disk first.
    attended = True
    cadence = "monthly"
    backfill_needs_from = False

    def default_as_of(self) -> date:
        from ....core import calendar
        return calendar.latest_complete_session()

    def fetch(self, ctx: base.RunContext, as_of: date) -> list:
        return []                                   # built from ``wrds/prices``' Parquet only

    def backfill(self, ctx: base.RunContext, start, end: date) -> None:
        return None

    def to_parquet(self, ctx, raw) -> list:
        return []

    def to_parquet_all(self, ctx, raws) -> list:
        return []

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        con.execute(f"SET VARIABLE {FROM_VAR} = DATE '{HISTORY_FROM.isoformat()}'")
        stage_sources(con)
        _spine_link(con)
        con.execute(f"CREATE OR REPLACE TEMP TABLE _delisted_permno AS {DELISTED_PERMNO_SQL}")
        names = prices_stage.count(con, "_delisted_permno")
        if not names:
            ctx.notes.append("no delisted security on disk: crsp_a_stock.stkdelists has not been fetched yet")
        con.execute(f"CREATE OR REPLACE TEMP TABLE _delisted_link AS {LINK_SQL}")
        counts = {BAR: _create(con, BAR, BAR_SQL)}
        _refuse_duplicates(con, BAR)
        counts[SYMBOL] = _create(con, SYMBOL, SYMBOL_SQL)
        counts[SECURITY] = _create(con, SECURITY, SECURITY_SQL)
        counts[ACTION] = _create(con, ACTION, f"{SPLIT_SQL} UNION ALL {DIVIDEND_SQL}")
        for table in (SECURITY, SYMBOL, ACTION):
            _refuse_duplicates(con, table)
        linked = con.execute(f"SELECT count(*) FROM {SECURITY} WHERE gvkey IS NOT NULL").fetchone()[0]
        no_bar = con.execute(f"SELECT count(*) FROM {SECURITY} WHERE sessions = 0").fetchone()[0]
        span = con.execute(f"SELECT min(session_date), max(session_date) FROM {BAR}").fetchone()
        ctx.notes.append(f"{names} delisted securities, {linked} with a Compustat gvkey, {no_bar} with no priced "
                         f"session from {HISTORY_FROM.isoformat()} on")
        if span[0]:
            ctx.notes.append(f"delisted bars {span[0]}..{span[1]}: {counts[BAR]} rows, {counts[ACTION]} actions")
        logger.info("delisted: %s securities (%s linked), %s bars, %s actions, %s symbol periods",
                    names, linked, counts[BAR], counts[ACTION], counts[SYMBOL])
        return counts

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        cols = ["security_id", "session_date", "open", "high", "low", "close", "volume"]
        added, removed = compare_live(con, BAR, cols)
        newest = con.execute(f"SELECT max(delisting_date) FROM {SECURITY}").fetchone()[0]
        return {"dataset": NAME, "result": "changed" if added or removed else "unchanged",
                "source_as_of": (newest or ctx.as_of or self.default_as_of()).isoformat(),
                "rows": prices_stage.count(con, BAR), "added": added, "removed": removed, "coverage": None}


DATASET = DelistedServing()
