"""The float: TradingView's ``float_shares_outstanding`` (``tradingview/float``) and Yahoo's ``floatShares``
(``yfinance/float``, the check).

**``yfinance/float``** asks Yahoo (the ``yfinance`` library, one ``Ticker.get_info`` per name) for every Tier A
name a run, with no pause and no window of ours (avo 23 Nov 2026, #1473): the names never asked first (by ticker),
then the longest ago, so a run cut short goes on where the last one stopped. A
401 or a 429 (Yahoo's refusal, or its rate limit) stops the run's lookups at once, and what was read before it is
kept: the next run goes on from there. ``yfinance`` (1.7.0, measured 28 Oct 2026) raises nothing for a refusal: it logs
the 401 or 429 on its ``yfinance`` logger and answers an empty info, so ``_lookup`` listens to that logger and raises
the refusal it logged when the answer is empty; an empty answer with no refusal logged is that name's error row
(``EMPTY_ANSWER``). Raw: ``raw/yfinance/float/<as_of>/batch-<n>.json.gz``, ``BATCH`` names a file;
a name a file of the day holds is not asked again that day. Parquet: ``parquet/yfinance/float/date=<as_of>/
part-0.parquet`` keyed on the ticker. ``_lookup`` is the one function that talks to Yahoo (the tests replace it).

**``tradingview/float``** asks TradingView's public stock scanner (``TV_URL``, no key) once a run for every US listing
and keeps the asked names (``asked``): the main float. It replaced Unusual Whales' ``total_float`` (#1473, avo 23 Nov
2026). A ticker on two venues keeps the row that is not OTC. Raw: ``raw/tradingview/float/<as_of>.json.gz``. Parquet:
``parquet/tradingview/float/date=<as_of>/part-0.parquet`` keyed on the ticker.
"""
from __future__ import annotations

import hashlib
import logging
import math
import re
from datetime import date
from pathlib import Path

import duckdb

from ....core import calendar
from .. import base
from . import KIND, scope, sec_ticker, stage

YAHOO = "yfinance/float"
TV = "tradingview/float"
TV_URL = "https://scanner.tradingview.com/america/scan"
TV_COLUMNS = ("name", "float_shares_outstanding", "total_shares_outstanding", "exchange", "type")
TV_RANGE = 25_000                 # every US listing in one answer (20,390 rows on 23 Nov 2026)
BATCH = 50
FIELDS = ("floatShares", "sharesOutstanding", "impliedSharesOutstanding", "quoteType", "currency", "exchange")
STOP = re.compile(r"\b(401|429)\b|rate.?limit|too many requests|unauthori[sz]ed|invalid crumb", re.I)
EMPTY_ANSWER = "empty answer: Yahoo returned none of the fields"
YAHOO_SCHEMA = [("ticker", "TEXT"), ("cik", "TEXT"), ("security_id", "TEXT"), ("float_shares", "DOUBLE"),
                ("shares_outstanding", "DOUBLE"), ("implied_shares", "DOUBLE"), ("quote_type", "TEXT"),
                ("currency", "TEXT"), ("error", "TEXT"), ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"),
                ("run_id", "TEXT")]
TV_SCHEMA = [("ticker", "TEXT"), ("cik", "TEXT"), ("security_id", "TEXT"), ("tv_symbol", "TEXT"),
             ("float_shares", "DOUBLE"), ("total_shares", "DOUBLE"), ("exchange", "TEXT"), ("type", "TEXT"),
             ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]


class _Logged(logging.Handler):
    """The ``yfinance`` logger's messages during one lookup."""

    def __init__(self):
        super().__init__(logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record):
        self.messages.append(record.getMessage())


class YahooRefused(RuntimeError):
    """Yahoo refused a lookup (a 401 or 429 the library only logged)."""


def _lookup(ticker: str) -> dict:
    """Yahoo's fields of ``FIELDS`` for one ticker (the SEC file's form, which is Yahoo's: ``BRK-B``). An empty
    answer after a logged 401 or 429 raises ``YahooRefused`` with the logged text (the run's stop rule reads it)."""
    import yfinance as yf
    log, seen = logging.getLogger("yfinance"), _Logged()
    log.addHandler(seen)
    try:
        info = yf.Ticker(ticker).get_info() or {}
    finally:
        log.removeHandler(seen)
    out = {k: info.get(k) for k in FIELDS}
    refused = [m for m in seen.messages if STOP.search(m) and "continuing without crumb" not in m]
    if refused and all(v is None for v in out.values()):
        raise YahooRefused(refused[-1][:300])
    return out


def _num(value) -> float | None:
    """``value`` as a finite float, else None: Yahoo answers NaN for a missing price (review N5)."""
    try:
        f = float(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None
    return f if f is not None and math.isfinite(f) else None


def _tier_a() -> list[dict]:
    return [n for n in scope() if n.get("tier") == "A"]


def _nothing_to_ask(ctx: base.RunContext) -> base.SourceError:
    """Why a float run has no name to ask: the request's scope, or a spine that was never built.

    A scope the Tier A rule answers nothing for is the request's own doing and a ``skipped`` row (review F4 of
    #294); no spine at all is a broken build and stays a failure.
    """
    if ctx.scope:
        return base.NothingInScope(f"no Tier A name in {ctx.scope.text()}: a fund has no float (#265)")
    return base.SourceError("nothing to ask: no Tier A name (spine.duckdb not built?)")


def asked(want=None) -> list[dict]:
    """The names one float run asks: the scope's Tier A names, because a fund (Tier B) has no float (#265). An
    explicit name list in the request is taken as it is: a person asking for one name means that name."""
    names = scope(want=want)
    if want is not None and want.names:
        return names
    return [n for n in names if n.get("tier") == "A"]


def _partitions(*parts: str) -> list[Path]:
    return [f for _, f in stage.partitions(base.parquet_root().joinpath(*parts), "date")]


class YahooFloat:
    name = YAHOO
    kind = KIND
    providers = ("yfinance",)
    tables = ("shares_class",)
    feeds = ("market_cap_daily",)                  # a class count times the close is the cap
    cadence = "daily"
    starts_by_hand = True
    honours_scope = True              # the request's names, else the scope's Tier A (``asked``)

    def default_as_of(self) -> date:
        return calendar.today_ny()

    def raw_dir(self, as_of: date) -> Path:
        return base.raw_root() / "yfinance" / "float" / as_of.isoformat()

    def _order(self, names: list[dict]) -> list[dict]:
        """Never asked first (by ticker), then the longest ago."""
        parts = _partitions("yfinance", "float")
        last: dict[str, float] = {}
        if parts:
            con = base.scratch_con()
            try:
                last = dict(con.execute("SELECT ticker, max(fetched_at) FROM read_parquet(["
                                        + ", ".join(base.sql_path(p) for p in parts) + "]) GROUP BY ticker").fetchall())
            finally:
                con.close()
        return sorted(names, key=lambda n: (n["ticker"] in last, last.get(n["ticker"], 0.0), n["ticker"]))

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        names = asked(ctx.scope)
        if not names:
            raise _nothing_to_ask(ctx)
        folder = self.raw_dir(as_of)
        have = sorted(folder.glob("batch-*.json.gz")) if folder.is_dir() else []
        done = {t for p in have for t in base.read_raw_json(p)["rows"]}
        todo = [n for n in self._order(names) if n["ticker"] not in done]
        out, batch, seq = list(have), {}, len(have)

        def flush():
            nonlocal batch, seq
            if batch:
                out.append(base.write_raw_json(folder / f"batch-{seq:04d}.json.gz", {
                    "as_of": as_of.isoformat(), "rows": batch, "fetched_at": calendar._now().timestamp(),
                    "run_id": ctx.run_id}))
                seq, batch = seq + 1, {}
        for n in todo:
            ctx.check_cap("yfinance")
            ctx.count("yfinance", calls=1)
            entry = {"cik": n.get("cik"), "security_id": n["security_id"]}
            try:
                entry.update(_lookup(n["ticker"]))
                if all(entry.get(k) is None for k in FIELDS):
                    ctx.count("yfinance", failures=1)
                    entry["error"] = EMPTY_ANSWER
            except Exception as e:  # noqa: BLE001 - one name's failure is that name's row, a refusal stops the run
                text = f"{type(e).__name__}: {e}"
                if STOP.search(text) or type(e).__name__ == "YFRateLimitError":
                    ctx.count("yfinance", failures=1, http_429=int("429" in text or "rate" in text.lower()))
                    ctx.notes.append(f"yfinance stopped at {n['ticker']}: {text[:120]}")
                    break
                ctx.count("yfinance", failures=1)
                entry["error"] = text[:200]
            batch[n["ticker"]] = entry
            if len(batch) >= BATCH:
                flush()
        flush()
        return out

    def backfill(self, ctx: base.RunContext, start, end: date) -> None:
        self.to_parquet_all(ctx, self.fetch(ctx, end))

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        return self.to_parquet_all(ctx, [raw])

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        days: dict[str, list[dict]] = {}
        for raw in raws:
            p = base.read_raw_json(raw)
            for ticker, e in p["rows"].items():
                days.setdefault(p["as_of"], []).append({
                    "ticker": ticker, "cik": e.get("cik"), "security_id": e.get("security_id"),
                    "float_shares": _num(e.get("floatShares")), "shares_outstanding": _num(e.get("sharesOutstanding")),
                    "implied_shares": _num(e.get("impliedSharesOutstanding")), "quote_type": e.get("quoteType"),
                    "currency": e.get("currency"), "error": e.get("error"), "source_as_of": date.fromisoformat(
                        p["as_of"]), "fetched_at": p["fetched_at"], "run_id": p["run_id"]})
        return [base.upsert_partition(rows, YAHOO_SCHEMA, ["ticker"], base.parquet_root() / "yfinance" / "float"
                                      / f"date={d}" / "part-0.parquet") for d, rows in sorted(days.items())]

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        stage.create(con, "stg_yahoo_float", YAHOO_SCHEMA, _partitions("yfinance", "float"))
        return {}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        return _float_check(ctx, con, YAHOO, "stg_yahoo_float", "float_shares", self.default_as_of())


class TradingViewFloat:
    name = TV
    kind = KIND
    providers = ("tradingview",)
    tables = ("shares_class",)
    feeds = ("market_cap_daily",)                  # a class count times the close is the cap
    cadence = "daily"
    starts_by_hand = True
    honours_scope = True              # the request's names, else the scope's Tier A (``asked``)

    def default_as_of(self) -> date:
        return calendar.today_ny()

    def raw_path(self, as_of: date, scope=None) -> Path:
        """The day's raw file, and a file of its own for a scoped ask.

        One file a day was the resume marker, and ``fetch`` returned it before looking at the scope: a
        ``names=["KO"]`` press wrote a one-row file and the day's later full run was handed that same file back, so
        the day ended with a float for one name (review F3 of #294). A scoped ask keys its own file, and both type
        into the same day's partition by upsert, so a narrow run and a later full run compose.
        """
        stem = as_of.isoformat()
        if scope:
            # Every part of the ask, groups included: without them ``include=["watchlist"]`` and
            # ``include=["cover_classes"]`` shared one file on the same day and the first one run was handed back
            # to the other (review D1 of #294).
            key = "\n".join([*scope.tiers, "|", *scope.names, "|", *scope.include])
            stem += "-" + hashlib.sha1(key.encode()).hexdigest()[:8]
        return base.raw_root() / "tradingview" / "float" / f"{stem}.json.gz"

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        path = self.raw_path(as_of, ctx.scope)
        if path.exists():
            return [path]
        names = {n["ticker"]: {"cik": n.get("cik"), "security_id": n["security_id"]} for n in asked(ctx.scope)}
        if not names:
            raise _nothing_to_ask(ctx)
        body = {"markets": ["america"], "symbols": {"query": {"types": []}, "tickers": []},
                "options": {"lang": "en"}, "columns": list(TV_COLUMNS), "range": [0, TV_RANGE]}
        answer = base.http_post(ctx, "tradingview", TV_URL, json=body).json()
        rows = {}
        for item in answer.get("data") or []:
            d = dict(zip(TV_COLUMNS, item.get("d") or []))
            t = sec_ticker(d.get("name") or "")
            if t not in names or (t in rows and d.get("exchange") == "OTC"):
                continue
            rows[t] = {**names[t], "tv_symbol": item.get("s"), "float_shares": d.get("float_shares_outstanding"),
                       "total_shares": d.get("total_shares_outstanding"), "exchange": d.get("exchange"),
                       "type": d.get("type")}
        if not rows:
            raise base.SourceError(f"tradingview scan answered none of the {len(names)} names asked")
        return [base.write_raw_json(path, {"as_of": as_of.isoformat(), "rows": rows, "status": "ok",
                                           "fetched_at": calendar._now().timestamp(), "run_id": ctx.run_id})]

    def backfill(self, ctx: base.RunContext, start, end: date) -> None:
        self.to_parquet_all(ctx, self.fetch(ctx, end))

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        return self.to_parquet_all(ctx, [raw])

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        out = []
        for raw in raws:
            p = base.read_raw_json(raw)
            rows = [{"ticker": t, "cik": e.get("cik"), "security_id": e.get("security_id"),
                     "tv_symbol": e.get("tv_symbol"),
                     "float_shares": _num(e.get("float_shares")), "total_shares": _num(e.get("total_shares")),
                     "exchange": e.get("exchange"), "type": e.get("type"),
                     "source_as_of": date.fromisoformat(p["as_of"]),
                     "fetched_at": p["fetched_at"], "run_id": p["run_id"]} for t, e in sorted(p["rows"].items())]
            out.append(base.upsert_partition(rows, TV_SCHEMA, ["ticker"], base.parquet_root() / "tradingview" / "float"
                                             / f"date={p['as_of']}" / "part-0.parquet"))
        return out

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        stage.create(con, "stg_tv_float", TV_SCHEMA, _partitions("tradingview", "float"))
        return {}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        return _float_check(ctx, con, TV, "stg_tv_float", "float_shares", self.default_as_of())


def _float_check(ctx, con, name: str, staging: str, column: str, default: date) -> dict:
    """The check row of a float source: its ``shares_class`` rows against the live file, and the share of Tier A
    with a value on any stored day (Yahoo asks a slice of the names a day)."""
    cols = ["security_id", "measure", "as_of", "value", "source"]
    added, removed = stage.compare_live(con, "shares_class", cols, f"source = '{name}'")
    tier_a = {n["ticker"] for n in _tier_a()}
    have = {r[0] for r in con.execute(f"SELECT DISTINCT ticker FROM {staging} WHERE {column} IS NOT NULL").fetchall()}
    as_of = ctx.as_of or default
    return {"dataset": name, "result": "changed" if added or removed else "unchanged",
            "source_as_of": as_of.isoformat(), "rows": stage.count(con, staging), "added": added, "removed": removed,
            "coverage": round(len(tier_a & have) / len(tier_a), 4) if tier_a else None}


YAHOO_FLOAT = YahooFloat()
TV_FLOAT = TradingViewFloat()
