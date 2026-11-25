"""``yfinance/bars``: Yahoo's daily bars of the universe names Compustat does not price (avo, 24 Nov 2026, decision
card "Yahoo'dan günlük bar çek"; DECISIONS F7's amendment F28).

The served history is Compustat's (``prices/serving``, priority 1). A name with no Compustat bar in the last
:data:`RECENT_DAYS` days before its own newest one -- a fund Compustat does not carry, or a new listing it has
not picked up yet -- had no served bar at all. (ILCB, ISCB and RFDI, the names that started this, turned out to be
renamed funds Compustat prices under their new tickers MLRG, MSML and AFDM: Joker's check of 24 Nov 2026.) This dataset asks Yahoo for those names only, and ``prices/serving`` serves a Yahoo bar (priority 3) only on
a session no Compustat row of the security has.

**One call per name, the whole history** (``Ticker.history(period="max", auto_adjust=False, actions=True)``): a few
names, so the whole history costs no more than a window and a split Yahoo learns later restates every older row in
the next run. Yahoo's OHLC is **split-adjusted** even with ``auto_adjust=False`` (its ``Adj Close`` is the only
dividend-adjusted column), so :func:`nominal` rebuilds the prices as traded: each day times the product of the split
ratios after it, the volume divided by it. The store's factors then come from the served actions, Yahoo's own
splits and dividends on the days its bar is served (:data:`ACTIONS_SQL`). A 401 or 429 stops the run, as in ``yfinance/float``; what was read before it is kept.

Raw: ``raw/yfinance/bars/<as_of>/<ticker>.json.gz``; a name a file of the day holds is not asked again that day.
Parquet: ``parquet/yfinance/bars/ticker=<ticker>/part-0.parquet``, the name's whole history from its newest answer,
rewritten only when the bars changed; staging reads every ticker's file.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import duckdb

from ....core import calendar
from .. import base, secd
from . import KIND, scope, stage, universe
from .floats import STOP, YahooRefused, _Logged, _num

NAME = "yfinance/bars"
STAGING = "stg_yahoo_bars"
#: A name with a Compustat bar this many days before Compustat's newest one is Compustat's: Yahoo is not asked.
RECENT_DAYS = 14
#: Compustat's newest priced day more than this many sessions old stops the run (review finding 5).
STALE_SESSIONS = 5
#: The id a Yahoo row is served under, over ``y`` joined as :data:`JOIN` joins it: the Compustat series that claims
#: the fund's ticker (``universe.ETF_TIC_SERIES_SQL``, ``pick = 1``), so a fund Compustat picks up later keeps one id
#: (review finding 2), else the spine's row of the ticker and CIK, else the id the fetch saw. A ``class:`` id is
#: never served from Yahoo (finding 3): :data:`SERVED` says so.
ID = "coalesce(e.gid, s.security_id, y.security_id)"
JOIN = ("LEFT JOIN stg_spine s ON s.ticker = y.ticker AND s.cik IS NOT DISTINCT FROM y.cik "
        "LEFT JOIN _etf_tic_series e ON e.pick = 1 AND e.tic = " + universe.norm("y.ticker"))
SERVED = f"{ID} NOT LIKE 'class:%'"
SCHEMA = [("ticker", "TEXT"), ("cik", "TEXT"), ("security_id", "TEXT"), ("session_date", "DATE"),
          ("open", "DOUBLE"), ("high", "DOUBLE"), ("low", "DOUBLE"), ("close", "DOUBLE"), ("volume", "DOUBLE"),
          ("split", "DOUBLE"), ("dividend", "DOUBLE"), ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]
#: Yahoo's splits and cash dividends as ``prices/serving`` actions (avo, 24 Nov 2026, D2 "Evet, Yahoo'dan al"),
#: in the columns of ``wrds_history``'s actions. ``PricesServing._wrds_actions`` takes one only on a day whose served
#: bar is Yahoo's and that no Alpaca or Compustat action of the kind already holds. One of a kind per id and day: two
#: tickers of one id (a rename's old file beside the new one) would apply a split or dividend twice (review N1).
ACTIONS_SQL = f"""
    SELECT {ID} AS security_id, 'yahoo:split:' || {ID} || ':' || CAST(y.session_date AS TEXT) AS action_id,
           CASE WHEN y.split < 1 THEN 'reverse_split' ELSE 'forward_split' END AS action_type,
           y.session_date AS ex_date, y.session_date AS eff, 1.0 AS old_rate, y.split AS new_rate,
           CAST(NULL AS DOUBLE) AS rate, false AS special, CAST(NULL AS TEXT) AS currency,
           CAST(NULL AS DATE) AS record_date, CAST(NULL AS DATE) AS payable_date, '{NAME}' AS source,
           y.source_as_of, y.fetched_at, y.run_id
    FROM {STAGING} y {JOIN} WHERE y.split > 0 AND y.split <> 1 AND {SERVED}
    QUALIFY row_number() OVER (PARTITION BY {ID}, y.session_date ORDER BY y.fetched_at DESC, y.ticker) = 1
    UNION ALL
    SELECT {ID}, 'yahoo:div:' || {ID} || ':' || CAST(y.session_date AS TEXT), 'cash_dividend', y.session_date,
           y.session_date, NULL, NULL, y.dividend, false, 'USD', NULL, NULL, '{NAME}', y.source_as_of, y.fetched_at,
           y.run_id
    FROM {STAGING} y {JOIN} WHERE y.dividend > 0 AND {SERVED}
    QUALIFY row_number() OVER (PARTITION BY {ID}, y.session_date ORDER BY y.fetched_at DESC, y.ticker) = 1"""


def _lookup(ticker: str) -> list[dict]:
    """Yahoo's daily rows of one ticker as ``{date, open, high, low, close, volume, split, dividend}``, oldest first,
    OHLC, volume and dividend as Yahoo gives them (split-adjusted). ``split`` is the day's ratio (new over old
    shares), 0 for none; ``dividend`` the cash per share going ex that day, a fund's capital-gains distribution
    included (review N7), 0 for none. An empty answer after a logged 401 or 429 raises ``YahooRefused``. The one
    function that talks to Yahoo."""
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
             "close": r.get("Close"), "volume": r.get("Volume"), "split": r.get("Stock Splits") or 0,
             "dividend": (_num(r.get("Dividends")) or 0) + (_num(r.get("Capital Gains")) or 0)}
            for ix, r in frame.iterrows()]


def nominal(rows: list[dict]) -> list[dict]:
    """``rows`` (Yahoo's, split-adjusted, any order) as traded: a day's prices and dividend times the product of the
    split ratios of the later days, its volume divided by it."""
    out, after = [], 1.0
    for r in sorted(rows, key=lambda r: r["date"], reverse=True):
        f = after
        out.append({**r, **{k: (_num(r.get(k)) * f if _num(r.get(k)) is not None else None)
                            for k in ("open", "high", "low", "close", "dividend")},
                    "volume": _num(r.get("volume")) / f if _num(r.get("volume")) is not None else None})
        split = _num(r.get("split")) or 0
        if split > 0:
            after *= split                      # this day is the first on the new basis: the days before it scale
    return sorted(out, key=lambda r: r["date"])


def _compustat_recent(as_of: date) -> tuple[date | None, set[str], set[str]]:
    """Compustat's newest priced day up to ``as_of`` (None with no ``wrds/prices`` Parquet), the ``gvkey:iid`` of
    every security it priced in the ``RECENT_DAYS`` before that day, and the tickers (in ``universe.norm``'s
    spelling) those securities carry on their own newest day there. Only a day on an exchange whose days are served
    (``wrds_history.SERVED_EXCHG``) counts: a name Compustat still files as over-the-counter has no served bar from
    it, so Yahoo is asked (review N4: CZZL, Nasdaq-listed, priced by Compustat only as OTC ``CZZLF``). Counted back
    from Compustat's day, not from ``as_of``: a WRDS refresh a week late must not make every name look unpriced
    (review finding 5)."""
    from . import wrds_history
    files = [p for y in range(as_of.year - 1, as_of.year + 1)
             if (p := wrds_history.partition_path("secd", y)).is_file()]
    if not files:
        return None, set(), set()
    con = base.scratch_con()
    try:
        rows = con.execute(f"""
            WITH d AS (SELECT gvkey || ':' || iid AS gid, {universe.norm('tic')} AS tic, CAST(datadate AS DATE) AS day
                       FROM read_parquet([{", ".join(base.sql_path(p) for p in files)}], union_by_name = true)
                       WHERE {secd.PRICED} AND exchg IN ({wrds_history._SERVED})
                         AND CAST(datadate AS DATE) <= ?),
                 n AS (SELECT max(day) AS newest FROM d)
            SELECT n.newest, d.gid, arg_max(d.tic, d.day) FROM d, n
            WHERE d.day > n.newest - INTERVAL {RECENT_DAYS} DAY GROUP BY ALL""", [as_of]).fetchall()
    finally:
        con.close()
    if not rows:
        return None, set(), set()
    return rows[0][0], {r[1] for r in rows}, {r[2] for r in rows if r[2]}


def asked(want, as_of: date) -> list[dict]:
    """The names one run asks: the scope's names Compustat has not priced in the ``RECENT_DAYS`` before its own
    newest day. An explicit name list in the request is taken as it is. Never asked (review of #1490):

    - a ``class:`` id, a share class the SEC covers name and the spine lacks: a Yahoo bar under it would count the
      issuer's cap twice beside Compustat's series of the same class (finding 3);
    - a fund Compustat prices by its ticker (``universe.ETF_TIC_SERIES_SQL``): it is served under that series, and a
      Yahoo row under its ``sym:`` id would be a second id of the same fund (finding 2). A stock's link to Compustat
      is the spine's, never the ticker's, so this applies only to a name the stock rule does not hold.

    Compustat's newest day more than ``STALE_SESSIONS`` sessions before ``as_of`` (or none) stops the run."""
    names = scope(want=want)
    if want is not None and want.names:
        return names
    newest, priced, tics = _compustat_recent(as_of)
    floor = calendar.previous_trading_day(as_of)
    for _ in range(STALE_SESSIONS):
        floor = calendar.previous_trading_day(floor - timedelta(days=1))
    if newest is None or newest < floor:
        raise base.SourceError(f"Compustat's newest priced day is {newest or 'missing'}, before {floor}: "
                               "Yahoo is not asked until the WRDS prices are refreshed")
    return [n for n in names
            if n["security_id"] not in priced and not str(n["security_id"]).startswith("class:")
            and (universe.in_stock(n) or _norm(n["ticker"]) not in tics)]


def _norm(ticker: str) -> str:
    """``universe.norm`` in Python."""
    return str(ticker).upper().replace(".", "-")


#: The columns that make two answers of a name the same bars (the fetch's own stamps left out).
_BARS = [c for c, _ in SCHEMA if c not in ("source_as_of", "fetched_at", "run_id")]


def _same(con: duckdb.DuckDBPyConnection, final: Path) -> bool:
    """``new_rows`` in ``con`` holds exactly the bars of the Parquet file ``final``."""
    cols = ", ".join(f'"{c}"' for c in _BARS)
    old = f"SELECT {cols} FROM read_parquet({base.sql_path(final)})"
    return not con.execute(f"SELECT count(*) FROM (({old} EXCEPT ALL SELECT {cols} FROM new_rows) UNION ALL "
                           f"(SELECT {cols} FROM new_rows EXCEPT ALL {old}))").fetchone()[0]


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
        """One file per ticker holding its whole Yahoo history, replaced whole, and **left untouched** when the new
        answer holds the same bars: the prices build on the live copy rebuilds a name only when its file changed
        (review of #1490, finding 6). An answer with no row (a failed name) keeps the file it had."""
        from .wrds_history import COMPUSTAT_START
        newest: dict[str, dict] = {}
        for raw in raws:
            p = base.read_raw_json(raw)
            if p.get("rows") and float(p["fetched_at"]) >= float(newest.get(p["ticker"], {}).get("fetched_at", 0)):
                newest[p["ticker"]] = p
        out = []
        for ticker, p in sorted(newest.items()):
            # Nothing before the served history's first day, and no bar of a session still open at the fetch (Yahoo
            # answers today's partial bar during the session): review of #1490, finding 7 and the floor Low.
            last = calendar.latest_complete_session(datetime.fromtimestamp(float(p["fetched_at"]), tz=timezone.utc))
            rows = [{"ticker": ticker, "cik": p.get("cik"), "security_id": p.get("security_id"),
                     "session_date": date.fromisoformat(r["date"]), "open": r["open"], "high": r["high"],
                     "low": r["low"], "close": r["close"], "volume": r["volume"],
                     "split": _num(r.get("split")) or None, "dividend": r.get("dividend") or None,
                     "source_as_of": date.fromisoformat(p["as_of"]), "fetched_at": p["fetched_at"],
                     "run_id": p["run_id"]}
                    for r in nominal(p["rows"])
                    if r["close"] is not None and COMPUSTAT_START.isoformat() <= r["date"] <= last.isoformat()]
            final = base.parquet_root() / "yfinance" / "bars" / f"ticker={ticker}" / "part-0.parquet"
            con = base.scratch_con()
            try:
                base.rows_table(con, "new_rows", SCHEMA, rows)
                if not (final.exists() and _same(con, final)):
                    base.write_parquet(con, "SELECT * FROM new_rows ORDER BY session_date", final)
            finally:
                con.close()
            out.append(final)
        return out

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        files = [f for _, f in stage.partitions(base.parquet_root() / "yfinance" / "bars", "ticker")]
        stage.create(con, STAGING, SCHEMA, files, select="SELECT * FROM {src} QUALIFY row_number() OVER ("
                     "PARTITION BY ticker, session_date ORDER BY fetched_at DESC) = 1")
        return {}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        as_of = ctx.as_of or self.default_as_of()
        names = con.execute(f"SELECT count(DISTINCT ticker) FROM {STAGING}").fetchone()[0]
        return {"dataset": NAME, "result": "changed", "source_as_of": as_of.isoformat(),
                "rows": stage.count(con, STAGING), "names": int(names)}


DATASET = YahooBars()
