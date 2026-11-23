"""``yfinance/fx``: daily exchange rates for the companies that report in no USD (#535; avo, 6 Nov 2026).

The fundamentals layer serves a statement value in USD (``facts.py``): one tagged in another currency is converted
at these rates, and dropped only where they do not reach its period. Measured on the companyfacts raw of 6 Nov 2026,
222 IFRS filers in the universe report in no USD; the gap scan of 21 Nov 2026 added the 20-F/40-F filers whose
US-GAAP statements are in CAD or JPY (#105). One request per currency in
``CURRENCIES`` (``core/providers/yfinance.get_fx_history``: Yahoo's daily close of ``<CUR>USD=X``, USD per unit): the
whole history the first time, else from ``OVERLAP_DAYS`` before the newest stored day, so a late correction by
Yahoo is read again. Counted under ``yfinance``, not paced (avo 23 Nov 2026, #1473). A failed currency is an issue and is asked
again by the next run; a run where every request failed is a failed run.

Raw: ``raw/yfinance/fx/<as-of>/<CUR>.json.gz`` (``{day: rate}``, the resume marker). Parquet:
``parquet/yfinance/fx/part-0.parquet``, every raw day typed into one file, the newest answer per (currency, day).
Staging: ``stg_yf_fx``. The companyfacts typing reads the held rates (``held_rates``) to convert a filer's
statement values to USD where they are tagged in another currency (#105, IFRS filers and 20-F/40-F US-GAAP ones);
a company typed before its currency's rates were held is converted at its next re-type.

**Compustat's rate first, Yahoo's where Compustat has none** (#1181 step H; DECISIONS F3; avo, 20 Nov 2026: "WRDS'e
gecelim tamamen"). ``held_rates`` reads the newest ``wrds/exrt`` snapshot (``comp.exrt_dly``, quoted from GBP, so a
rate is the cross of ``cross_sql``) and this dataset's file: a (currency, day) Compustat holds is Compustat's, every
other day is Yahoo's. Compustat's snapshot is monthly, so the newest days are Yahoo's until the next one. Measured
on homesrv, 20 Nov 2026: the two agree within 1% on 91.4% of 9,947 pairs of a year. A company's values move to
the new rates when its facts are typed again, like any other change of the rates.
"""
from __future__ import annotations

import itertools
import statistics
import time
from datetime import date, timedelta
from pathlib import Path

import duckdb

from ....core import calendar
from .. import base
from .. import dirty as dirty_set
from . import KIND, common

NAME = "yfinance/fx"
PROVIDER = "yfinance"
OVERLAP_DAYS = 7
STAGING = "stg_yf_fx"
# shortcut: the currencies measured on the companyfacts raw of 6 Nov 2026 (the newest annual of the IFRS filers);
# derive them from the facts once the IFRS reader keeps a non-USD value's unit.
# 16 Nov 2026 (Fundamentals plan step 4, decision I): ten more, the currencies of the 13 unscored non-USD names.
CURRENCIES = ("AED", "ARS", "AUD", "BRL", "CAD", "CHF", "CLP", "CNY", "COP", "CZK", "DKK", "EGP", "EUR", "GBP",
              "HKD", "HUF", "IDR", "ILS", "INR", "JPY", "KRW", "KZT", "MXN", "MYR", "NGN", "NOK", "NZD", "PEN", "PHP",
              "PLN", "RUB", "SAR", "SEK", "SGD", "THB", "TRY", "TWD", "ZAR")
#: A day whose rate is this far from the median of the days before it and of the days after it (``SPIKE_WINDOW``
#: each) is a bad print, not a move, and is left out of the index (Yahoo's ARS/TRY/IDR/KRW history carries such
#: days). A real devaluation agrees with the days after it, so it stays.
SPIKE_RATIO = 1.5
SPIKE_WINDOW = 3
SCHEMA = [("currency", "TEXT"), ("day", "DATE"), ("usd_per_unit", "DOUBLE"), ("source_as_of", "DATE"),
          ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]
#: Compustat's daily rates (``wrds_fund.WrdsExrt``): the dataset, its table, and the currency every row is quoted
#: from (measured 20 Nov 2026, #1181). Named here, not there, because that module imports this one.
EXRT_NAME = "wrds/exrt"
EXRT_TABLE = "exrt_dly"
EXRT_BASE = "GBP"
USD = "USD"


def cross_sql(src: str, stamps: bool = False) -> str:
    """A SELECT of ``currency, day, usd_per_unit`` (and the three provenance columns when ``stamps``) from ``src``,
    a relation of ``comp.exrt_dly`` rows (``fromcurd``, ``tocurd``, ``datadate``, ``exratd``): USD per unit is
    ``exratd(base->USD) / exratd(base->currency)``, and the base currency's own rate is the USD row's. A day with no
    USD row, and a rate that is not above zero, give no rate."""
    c_more, u_more = (", c.source_as_of, c.fetched_at, c.run_id", ", source_as_of, fetched_at, run_id") \
        if stamps else ("", "")
    return f"""
        WITH rates AS (SELECT * FROM {src} WHERE fromcurd = '{EXRT_BASE}' AND exratd > 0),
             usd AS (SELECT * FROM rates WHERE tocurd = '{USD}')
        SELECT c.tocurd AS currency, c.datadate AS day, u.exratd / c.exratd AS usd_per_unit{c_more}
        FROM rates c JOIN usd u ON u.datadate = c.datadate
        WHERE c.tocurd NOT IN ('{USD}', '{EXRT_BASE}')
        UNION ALL
        SELECT '{EXRT_BASE}', datadate, exratd{u_more} FROM usd"""


def exrt_snapshot() -> Path | None:
    """The newest typed snapshot of ``wrds/exrt``, or None before its first run."""
    folder = common.parquet_dir(EXRT_NAME)
    found = sorted(p for p in folder.glob(f"snapshot=*/{EXRT_TABLE}.parquet")) if folder.is_dir() else []
    return found[-1] if found else None


def index_rates(rows) -> dict[str, tuple[list[str], list[float], list[float]]]:
    """``{currency: (days, rates, prefix sums)}`` of ``(currency, ISO day, usd_per_unit)`` rows sorted by currency
    and day: the shape ``facts.as_gaap`` reads."""
    out = {}
    for cur, group in itertools.groupby(rows, key=lambda r: r[0]):
        group = [r for r in group if r[2] is not None and float(r[2]) > 0]
        raw = [float(r[2]) for r in group]
        keep = [i for i in range(len(raw)) if not _spike(raw, i)]
        rates = [raw[i] for i in keep]
        out[cur] = ([str(group[i][1])[:10] for i in keep], rates, [0.0, *itertools.accumulate(rates)])
    return out


def _spike(rates: list[float], i: int) -> bool:
    """True when ``rates[i]`` is ``SPIKE_RATIO`` or more off the median of the ``SPIKE_WINDOW`` days before it AND
    of those after it. A devaluation agrees with one side, so it stays; the first and last days are kept."""
    before, after = rates[max(0, i - SPIKE_WINDOW):i], rates[i + 1:i + 1 + SPIKE_WINDOW]
    if not before or not after:
        return False

    def off(side: list[float]) -> bool:
        mid = statistics.median(side)
        return max(rates[i], mid) / min(rates[i], mid) >= SPIKE_RATIO
    return off(before) and off(after)


def held_rates() -> dict:
    """The held rates, indexed (``index_rates``): Compustat's for every (currency, day) its newest snapshot holds,
    Yahoo's for every other day; empty before the first fetch of either."""
    yahoo, compustat = common.parquet_dir(NAME) / "part-0.parquet", exrt_snapshot()
    parts = []
    if compustat is not None:
        src = f"read_parquet({base.sql_path(compustat)})"
        parts.append(f"SELECT currency, day, usd_per_unit, 0 AS pick FROM ({cross_sql(src)})")
    if yahoo.exists():
        parts.append(f"SELECT currency, day, usd_per_unit, 1 AS pick FROM read_parquet({base.sql_path(yahoo)})")
    if not parts:
        return {}
    con = base.scratch_con()
    try:
        return index_rates(con.execute(f"""
            SELECT currency, strftime(day, '%Y-%m-%d'), usd_per_unit FROM ({' UNION ALL '.join(parts)})
            WHERE usd_per_unit IS NOT NULL AND day IS NOT NULL
            QUALIFY row_number() OVER (PARTITION BY currency, day ORDER BY pick) = 1
            ORDER BY currency, day""").fetchall())
    finally:
        con.close()


def day_dir(as_of: date | str) -> Path:
    return common.raw_dir(NAME) / str(as_of)


def _newest_days() -> dict[str, date]:
    """The newest day held per currency, over every raw file (one walk)."""
    newest: dict[str, date] = {}
    root = common.raw_dir(NAME)
    for raw in (root.glob("*/*.json.gz") if root.is_dir() else []):
        days = base.read_raw_json(raw).get("rates") or {}
        if days:
            cur, last = raw.name.split(".")[0], date.fromisoformat(max(days))
            newest[cur] = max(newest.get(cur, last), last)
    return newest


class FxRates:
    name = NAME
    kind = KIND
    providers = (PROVIDER,)
    tables: tuple[str, ...] = ()
    # The rates an IFRS filer's facts are put in USD with (#105), so the facts and what is built over them.
    feeds = ("fundamental_fact", "peer_group", "customer_share")
    cadence = "daily"
    backfill_needs_from = False
    starts_by_hand = True

    def default_as_of(self) -> date:
        return calendar.today_ny()

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        from ....core.providers import yfinance as yf_provider
        newest = _newest_days()
        out, failed, empty = [], [], []
        for cur in CURRENCIES:
            start = (newest[cur] - timedelta(days=OVERLAP_DAYS)).isoformat() if cur in newest else None
            ctx.check_cap(PROVIDER)
            ctx.count(PROVIDER, calls=1)
            # This dataset's own book is the one that reaches the day's ledger: the provider module would count
            # the same read a second time into the same row (#1277).
            with yf_provider.spend_owned_by_caller():
                res = yf_provider.get_fx_history(cur, start)
            if res.status != "ok":
                ctx.count(PROVIDER, failures=1)
                failed.append(cur)
                ctx.issue("fetch_failed", cur, f"yfinance {cur}USD=X: {(res.error or {}).get('error')}")
                continue
            if not res.data:
                empty.append(cur)
                ctx.issue("no_rows", cur, f"yfinance {cur}USD=X: no rows from {start or 'the start'}")
                continue
            path = day_dir(as_of) / f"{cur}.json.gz"
            # A second run on the same day asks only the last week; it adds to that day's file, never replaces it,
            # or the whole history the first run read would be gone from raw and from Parquet.
            rates = {**(base.read_raw_json(path).get("rates") or {}), **res.data} if path.exists() else res.data
            out.append(base.write_raw_json(path, {"currency": cur, "as_of": as_of.isoformat(), "start": start,
                                                  "fetched_at": time.time(), "run_id": ctx.run_id, "rates": rates}))
        if not out and (failed or empty):
            raise base.SourceError(f"yfinance fx: no currency answered ({len(failed)} failed, {len(empty)} empty)")
        ctx.notes.append(f"{len(out)} of {len(CURRENCIES)} currencies read, {len(failed)} failed, {len(empty)} empty")
        return out

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        # The first run asks each currency's whole history: a backfill is one fetch.
        self.to_parquet_all(ctx, self.fetch(ctx, end))

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        return self.to_parquet_all(ctx, [raw])

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        rows = []
        for raw in sorted(common.raw_dir(NAME).glob("*/*.json.gz")):
            doc = base.read_raw_json(raw)
            stamps = {"source_as_of": date.fromisoformat(doc["as_of"]), "fetched_at": float(doc["fetched_at"]),
                      "run_id": doc["run_id"]}
            rows += [{"currency": doc["currency"], "day": date.fromisoformat(d), "usd_per_unit": float(v), **stamps}
                     for d, v in doc["rates"].items()]
        con = base.scratch_con()
        try:
            base.rows_table(con, "rows", SCHEMA, rows)
            return [base.write_parquet(con, """
                SELECT * FROM rows QUALIFY row_number() OVER (PARTITION BY currency, day ORDER BY fetched_at DESC) = 1
                ORDER BY currency, day""", common.parquet_dir(NAME) / "part-0.parquet")]
        finally:
            con.close()

    def dirty(self, ctx: base.RunContext):
        """Small and not partitioned by company: reloaded whole by every build, on the live copy too (#446)."""
        return dirty_set.ALL

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        common.stage_glob(con, STAGING, SCHEMA, common.parquet_dir(NAME), "part-0.parquet")
        return {}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        on = ctx.as_of or self.default_as_of()
        have, newest = con.execute(f"SELECT count(DISTINCT currency), max(source_as_of) FROM {STAGING}").fetchone()
        ctx.notes.append(f"{have} of {len(CURRENCIES)} currencies held")
        return {"dataset": NAME, "result": "changed" if newest == on else "unchanged",
                "source_as_of": (newest or on).isoformat(), "rows": common.count(con, STAGING), "added": 0,
                "removed": 0}


DATASET = FxRates()
