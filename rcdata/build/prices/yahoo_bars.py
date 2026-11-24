"""``yfinance/bars``: Yahoo's daily bars of the universe names Compustat does not price (avo, 24 Nov 2026, decision
card "Yahoo'dan günlük bar çek"; DECISIONS F7's amendment F28).

The served history is Compustat's (``prices/serving``, priority 1). A name with no Compustat bar in the last
:data:`RECENT_DAYS` days -- a fund Compustat never carried (ILCB, ISCB, RFDI on 24 Nov 2026: Yahoo bars to 11-23,
none on Alpaca, no ``comp.secd`` row since 2025) or a new listing Compustat has not picked up yet -- had no served bar
at all. This dataset asks Yahoo for those names only, and ``prices/serving`` serves a Yahoo bar (priority 3) only on
a session no Compustat row of the security has.

**One call per name, the whole history** (``Ticker.history(period="max", auto_adjust=False, actions=True)``): a few
names, so the whole history costs no more than a window and a split Yahoo learns later restates every older row in
the next run. Yahoo's OHLC is **split-adjusted** even with ``auto_adjust=False`` (its ``Adj Close`` is the only
dividend-adjusted column), so :func:`nominal` rebuilds the prices as traded: each day times the product of the split
ratios after it, the volume divided by it. The store's own factors then come from Alpaca's actions, as for every
security. A 401 or 429 stops the run, as in ``yfinance/float``; what was read before it is kept.

Raw: ``raw/yfinance/bars/<as_of>/<ticker>.json.gz``; a name a file of the day holds is not asked again that day.
Parquet: ``parquet/yfinance/bars/date=<as_of>/part-0.parquet`` keyed on ``(ticker, session_date)``; staging reads
every day's partition and keeps the newest fetch of each bar.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import duckdb

from ....core import calendar
from .. import base
from . import KIND, scope, stage
from .floats import STOP, YahooRefused, _Logged, _num

NAME = "yfinance/bars"
STAGING = "stg_yahoo_bars"
#: A name with a Compustat bar this many days back is Compustat's: Yahoo is not asked for it.
RECENT_DAYS = 14
SCHEMA = [("ticker", "TEXT"), ("cik", "TEXT"), ("security_id", "TEXT"), ("session_date", "DATE"),
          ("open", "DOUBLE"), ("high", "DOUBLE"), ("low", "DOUBLE"), ("close", "DOUBLE"), ("volume", "DOUBLE"),
          ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]


def _lookup(ticker: str) -> list[dict]:
    """Yahoo's daily rows of one ticker as ``{date, open, high, low, close, volume, split}``, oldest first, OHLC and
    volume as Yahoo gives them (split-adjusted). ``split`` is the day's ratio (new over old shares), 0 for none. An
    empty answer after a logged 401 or 429 raises ``YahooRefused``. The one function that talks to Yahoo."""
    import logging

    import yfinance as yf
    log, seen = logging.getLogger("yfinance"), _Logged()
    log.addHandler(seen)
    try:
        frame = yf.Ticker(ticker).history(period="max", interval="1d", auto_adjust=False, actions=True)
    finally:
        log.removeHandler(seen)
    refused = [m for m in seen.messages if STOP.search(m) and "continuing without crumb" not in m]
    if refused and (frame is None or frame.empty):
        raise YahooRefused(refused[-1][:300])
    if frame is None or frame.empty:
        return []
    return [{"date": ix.date().isoformat(), "open": r.get("Open"), "high": r.get("High"), "low": r.get("Low"),
             "close": r.get("Close"), "volume": r.get("Volume"), "split": r.get("Stock Splits") or 0}
            for ix, r in frame.iterrows()]


def nominal(rows: list[dict]) -> list[dict]:
    """``rows`` (Yahoo's, split-adjusted, any order) as traded: a day's prices times the product of the split ratios
    of the later days, its volume divided by it."""
    out, after = [], 1.0
    for r in sorted(rows, key=lambda r: r["date"], reverse=True):
        f = after
        out.append({**r, **{k: (_num(r.get(k)) * f if _num(r.get(k)) is not None else None)
                            for k in ("open", "high", "low", "close")},
                    "volume": _num(r.get("volume")) / f if _num(r.get("volume")) is not None else None})
        split = _num(r.get("split")) or 0
        if split > 0:
            after *= split                      # this day is the first on the new basis: the days before it scale
    return sorted(out, key=lambda r: r["date"])


def _priced_recently(as_of: date) -> set[str]:
    """The ``gvkey:iid`` of every security with a Compustat ``secd`` row since ``as_of - RECENT_DAYS``, read from
    the ``wrds/prices`` Parquet of those years."""
    from . import wrds_history
    since = as_of - timedelta(days=RECENT_DAYS)
    files = [p for y in range(since.year, as_of.year + 1)
             if (p := wrds_history.partition_path("secd", y)).is_file()]
    if not files:
        return set()
    con = base.scratch_con()
    try:
        return {r[0] for r in con.execute(
            "SELECT DISTINCT gvkey || ':' || iid FROM read_parquet(["
            + ", ".join(base.sql_path(p) for p in files) + "], union_by_name = true) "
            "WHERE CAST(datadate AS DATE) >= ? AND prccd IS NOT NULL", [since]).fetchall()}
    finally:
        con.close()


def asked(want, as_of: date) -> list[dict]:
    """The names one run asks: the scope's names Compustat has not priced in the last ``RECENT_DAYS`` days. An
    explicit name list in the request is taken as it is."""
    names = scope(want=want)
    if want is not None and want.names:
        return names
    priced = _priced_recently(as_of)
    return [n for n in names if n["security_id"] not in priced]


class YahooBars:
    name = NAME
    kind = KIND
    providers = ("yfinance",)
    tables = ("price_bar_daily",)
    feeds = ("market_cap_daily",)                  # a served close is a cap's close
    cadence = "daily"
    starts_by_hand = True
    honours_scope = True              # the request's names, else the scope's names Compustat does not price

    def default_as_of(self) -> date:
        return calendar.today_ny()

    def raw_dir(self, as_of: date) -> Path:
        return base.raw_root() / "yfinance" / "bars" / as_of.isoformat()

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        names = asked(ctx.scope, as_of)
        if not names:
            raise base.NothingInScope("every name in scope has a Compustat bar in the last "
                                      f"{RECENT_DAYS} days: nothing for Yahoo")
        folder = self.raw_dir(as_of)
        out = sorted(folder.glob("*.json.gz")) if folder.is_dir() else []
        done = {p.name.removesuffix(".json.gz") for p in out}
        for n in sorted(names, key=lambda n: n["ticker"]):
            if n["ticker"] in done:
                continue
            ctx.check_cap("yfinance")
            ctx.count("yfinance", calls=1)
            entry = {"ticker": n["ticker"], "cik": n.get("cik"), "security_id": n["security_id"],
                     "as_of": as_of.isoformat(), "fetched_at": calendar._now().timestamp(), "run_id": ctx.run_id}
            try:
                entry["rows"] = _lookup(n["ticker"])
            except Exception as e:  # noqa: BLE001 - one name's failure is that name's file, a refusal stops the run
                text = f"{type(e).__name__}: {e}"
                ctx.count("yfinance", failures=1)
                if STOP.search(text) or type(e).__name__ == "YFRateLimitError":
                    ctx.notes.append(f"yfinance stopped at {n['ticker']}: {text[:120]}")
                    break
                entry["rows"], entry["error"] = [], text[:200]
            out.append(base.write_raw_json(folder / f"{n['ticker']}.json.gz", entry))
        return out

    def backfill(self, ctx: base.RunContext, start, end: date) -> None:
        self.to_parquet_all(ctx, self.fetch(ctx, end))

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        return self.to_parquet_all(ctx, [raw])

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        days: dict[str, list[dict]] = {}
        for raw in raws:
            p = base.read_raw_json(raw)
            for r in nominal(p.get("rows") or []):
                if r["close"] is None:
                    continue
                days.setdefault(p["as_of"], []).append({
                    "ticker": p["ticker"], "cik": p.get("cik"), "security_id": p.get("security_id"),
                    "session_date": date.fromisoformat(r["date"]), "open": r["open"], "high": r["high"],
                    "low": r["low"], "close": r["close"], "volume": r["volume"],
                    "source_as_of": date.fromisoformat(p["as_of"]), "fetched_at": p["fetched_at"],
                    "run_id": p["run_id"]})
        return [base.upsert_partition(rows, SCHEMA, ["ticker", "session_date"], base.parquet_root() / "yfinance"
                                      / "bars" / f"date={d}" / "part-0.parquet") for d, rows in sorted(days.items())]

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        files = [f for _, f in stage.partitions(base.parquet_root() / "yfinance" / "bars", "date")]
        stage.create(con, STAGING, SCHEMA, files, select="SELECT * FROM {src} QUALIFY row_number() OVER ("
                     "PARTITION BY ticker, session_date ORDER BY fetched_at DESC) = 1")
        return {}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        as_of = ctx.as_of or self.default_as_of()
        names = con.execute(f"SELECT count(DISTINCT ticker) FROM {STAGING}").fetchone()[0]
        return {"dataset": NAME, "result": "changed", "source_as_of": as_of.isoformat(),
                "rows": stage.count(con, STAGING), "names": int(names)}


DATASET = YahooBars()
