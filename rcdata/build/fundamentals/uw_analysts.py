"""``uw/screener_analysts``: Unusual Whales' dated analyst ratings and price targets, read once before the plan ends.

**Why it exists, and why only once.** UW's ``GET /api/screener/analysts`` is the one analyst record measured on
27 Nov 2026 that answers for **delisted** names -- FRC (26 Apr 2023), ATVI (3 Aug 2023), SGEN (1 Nov 2023) all come
back with a firm and a target, while ``yfinance.upgrades_downgrades`` returns no row for them and
``api.nasdaq.com`` answers "Symbol not exists" (#1588, the G2 provider matrix). For **live** names yfinance is the
deeper and free source (ACN: 601 rows back to 9 Mar 2012), so this dataset is not the first source of ratings: it is
the survivorship-free archive, and avo's plan answers until **6 December 2026**. Hence
:data:`due.SOURCE_ENDS`, ``starts_by_hand`` and no cadence that could turn it into a weekly ask after that day.

**Two passes, because one cannot reach both ends.**

- *Pass 1, the market-wide feed.* ``?limit=500`` with no ticker is every ticker's ratings newest first, so paging
  back with ``older_than`` (the oldest row of the page, the paging of ``options/uw_screener.py``'s far prints; UW
  ignores ``page`` here) collects the delisted names too with no universe list at all. Its floor is the token's
  own: an explicit ``older_than`` before :data:`FLOOR` (2023-12-28) is refused, with UW's own text about two years
  of history.
- *Pass 2, one call per ticker, asked **below** the floor.* A **ticker-filtered** query answers rows older than
  that floor -- measured, not documented. Each call is sent with ``older_than`` = :data:`PASS2_FROM` (the day
  after the floor), so it returns the pre-floor tail itself rather than the newest 500 rows, which for a busy
  name would never reach 2023 and would only repeat what pass 1 holds. **Measured on 8 of 8 probe tickers,
  27 Nov 2026** (rows below the floor, oldest row): FRC 24 / 3 Jan 2023, SIVB 21 / 3 Jan 2023, ATVI 30 /
  5 Jan 2023, SGEN 36 / 4 Jan 2023, WBD 31 / 4 Jan 2023, AAPL 127 / 3 Jan 2023, ACN 52 / 30 Jan 2023, TSM 14 /
  9 Mar 2023 -- every one under the 500 limit, so **one call per ticker**; the code still pages on a full page.
  No probe reached December 2022, so :data:`ARCHIVE_START` is where this token's archive begins.
  The ticker set is the **delisted universe first** (avo's choice of 27 Nov 2026, option A), then every ticker
  pass 1 saw, then the live universe. A security delisted **before** :data:`ARCHIVE_START` cannot have a row in
  this archive, so it is not asked: that is what keeps pass 2 to a few thousand calls instead of one per
  delisted security ever (29,833 of them in the delisted store).

**Identity stays out of it.** A row carries UW's ticker string and nothing else; a dated ticker to security join is
its own slice (#1444). Joining inside the fetch is how a delisted name is lost twice: its ticker belongs to a live
company today.

**No served table, no reader.** The rows land in raw and Parquet and stage into ``stg_uw_analyst_rating``; nothing
reads them yet (measured: no board reads ratings or price targets, #1588 "Cross-board impact"). So the dataset
serves no table, needs no entry in the need catalog -- a need is a board's ask answered by a reader, and there is
neither -- and the fundamentals serving schema version does not move: a staging table is a TEMP table.

Raw: ``raw/uw/screener_analysts/<as-of>/feed/page-NNNN.json.gz`` and ``.../ticker/<TICKER>.json.gz`` (both the
resume marker: a page or a ticker already written is not asked again). Parquet:
``parquet/uw/screener_analysts/date=<as-of>/part-0.parquet``, rewritten from the day's raw files so a resumed day
loses none. Staging: ``stg_uw_analyst_rating``, one row per rating event.

A row with no ``timestamp`` or no ``ticker`` has no key and is skipped, counted. ``target`` is UW's string
(``"266.0000"``, ``"220"``, ``null``): it parses or stays NULL, and never becomes 0.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb

from ....core import calendar, credentials
from ....core.providers.unusual_whales import is_rejected
from .. import base
from .. import dirty as dirty_set
from . import KIND, common

NAME = "uw/screener_analysts"
PROVIDER = "uw"
KEY = "unusual_whales"
EP = "/screener/analysts"
#: UW's documented maximum for this endpoint ("Default: 500, Max: 500", ``docs/openapi.yaml``).
PAGE_LIMIT = 500
#: The token's own earliest day for an **explicit** ``older_than``: before it UW refuses the request. A
#: ticker-filtered query still answers older rows, which is what pass 2 is for.
FLOOR = date(2023, 12, 28)
#: The ``older_than`` every pass-2 call carries: the day after the floor, so the answer is the pre-floor tail.
PASS2_FROM = date(2023, 12, 29)
#: The first day any probe found a row under (measured 27 Nov 2026 on 8 tickers: the oldest was 3 Jan 2023). A
#: security delisted before it is not asked in pass 2, with a month's margin.
ARCHIVE_START = date(2022, 12, 1)
#: Pages before pass 1 stops asking: 2,000 pages are a million rows, well past two years of a few hundred ratings
#: a day, and only stop a feed that never ends.
MAX_FEED_PAGES = 2_000
#: Pages one ticker may take in pass 2. Every probe answered in one (the busiest, AAPL, 127 rows), so this only
#: bounds a name nobody measured.
MAX_TICKER_PAGES = 10
#: Provider-side failures in a row that stop the run (UW throttling or down), as every UW dataset here counts them.
FAIL_STREAK = 5
#: Requests UW rejects (a 4xx of the request's own: an unknown ticker) in a row with no answer between: one dead
#: ticker is its own, this many in a row is the path.
REJECT_STREAK = 25
STAGING = "stg_uw_analyst_rating"
#: One row per rating event, as UW serves it. ``published_at`` is UW's ``timestamp``.
SCHEMA = [("ticker", "TEXT"), ("published_at", "TIMESTAMP"), ("action", "TEXT"), ("recommendation", "TEXT"),
          ("target", "DOUBLE"), ("analyst_name", "TEXT"), ("firm", "TEXT"), ("sector", "TEXT"),
          ("source", "TEXT"), ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]


def day_dir(as_of: date | str) -> Path:
    return common.raw_dir(NAME) / str(as_of)


def feed_dir(as_of: date | str) -> Path:
    return day_dir(as_of) / "feed"


def ticker_dir(as_of: date | str) -> Path:
    return day_dir(as_of) / "ticker"


def feed_path(as_of: date | str, page: int) -> Path:
    return feed_dir(as_of) / f"page-{page:04d}.json.gz"


def ticker_path(as_of: date | str, ticker: str) -> Path:
    return ticker_dir(as_of) / f"{ticker.replace('/', '_')}.json.gz"


def _num(v) -> float | None:
    """UW's price target as a number, or None: never 0 for a missing one."""
    if v is None or isinstance(v, bool) or str(v).strip() in ("", "None", "-", "null"):
        return None
    try:
        return float(str(v).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _stamp(v) -> datetime | None:
    """UW's ``timestamp`` as a naive UTC datetime, or None."""
    text = str(v or "").strip()
    if not text:
        return None
    try:
        got = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return got.astimezone(timezone.utc).replace(tzinfo=None) if got.tzinfo else got


def rows_of(body) -> list:
    """The ``data`` list of a body (or a bare list); anything else is no rows."""
    items = body.get("data") if isinstance(body, dict) else body
    return items if isinstance(items, list) else []


def oldest_stamp(rows: list) -> str | None:
    """The oldest ``timestamp`` string of a page: pass 1's next ``older_than`` cursor."""
    stamps = sorted(str(r.get("timestamp")) for r in rows
                    if isinstance(r, dict) and _stamp(r.get("timestamp")) is not None)
    return stamps[0] if stamps else None


def below_floor(cursor: str | None) -> bool:
    """Whether the cursor has reached the token's floor, so no further page may be asked."""
    got = _stamp(cursor)
    return got is not None and got.date() <= FLOOR


def table_rows(body, stamps: dict) -> tuple[list[dict], dict[str, int]]:
    """The staging rows of one answer, and ``counts`` of the rows left out and why."""
    out, counts = [], {}
    for row in rows_of(body):
        if not isinstance(row, dict):
            counts["not_a_row"] = counts.get("not_a_row", 0) + 1
            continue
        when, ticker = _stamp(row.get("timestamp")), str(row.get("ticker") or "").strip()
        if when is None:
            counts["no_timestamp"] = counts.get("no_timestamp", 0) + 1
            continue
        if not ticker:
            pass            # MUTATION (#1588): a row with no ticker is kept, to see the identity test go red
        out.append({"ticker": ticker, "published_at": when, "action": row.get("action"),
                    "recommendation": row.get("recommendation"), "target": _num(row.get("target")),
                    "analyst_name": row.get("analyst_name"), "firm": row.get("firm"), "sector": row.get("sector"),
                    "source": NAME, **stamps})
    return out, counts


def delisted_tickers() -> list[str]:
    """Every ticker a security **delisted on or after** :data:`ARCHIVE_START` traded under, from the delisted
    serving layer; [] without that file. The window is the point: UW's archive starts in January 2023, so a name
    that stopped trading before it has no row to fetch and no call is spent on it."""
    from ... import read
    try:
        ids = [str(r["security_id"]) for r in read.delisted_securities(delisted_from=ARCHIVE_START)
               if r.get("security_id")]
        rows: list[dict] = []
        for n in range(0, len(ids), 500):               # one IN list per chunk, not 30,000 placeholders
            rows += read.delisted_symbols(security_ids=ids[n:n + 500])
    except Exception:                                   # noqa: BLE001 - no delisted file yet is no delisted names
        return []
    return sorted({str(r.get("symbol") or "").strip() for r in rows if str(r.get("symbol") or "").strip()})


def live_tickers() -> list[str]:
    """The kind's own universe, by ticker."""
    return sorted({str(r["ticker"]).strip() for r in common.universe() if str(r.get("ticker") or "").strip()})


def ticker_order(seen: list[str]) -> list[str]:
    """Pass 2's ticker set: **the delisted universe first** (avo, 27 Nov 2026), then the tickers pass 1 saw, then
    the live universe; each ticker once, in that order."""
    out: list[str] = []
    for group in (delisted_tickers(), sorted(set(seen)), live_tickers()):
        for t in group:
            if t not in out:
                out.append(t)
    return out


class UWScreenerAnalysts:
    name = NAME
    kind = KIND
    providers = (PROVIDER,)
    tables: tuple[str, ...] = ()
    feeds: tuple[str, ...] = ()                 # nothing is served from it yet (#1588): raw, Parquet and staging
    cadence = "quarterly"
    backfill_needs_from = False
    starts_by_hand = True

    def default_as_of(self) -> date:
        return calendar.today_ny()

    # ── fetch ──
    def _ask(self, ctx: base.RunContext, params: dict):
        """One UW GET; ``(body, error)``. 401/403 and an open breaker fail the run, as every UW call here does."""
        ctx.check_cap(PROVIDER)
        res = ctx.uw_client().get_result(EP, params)
        if res.status == "ok":
            return res.data, None
        err = res.error or {}
        what, status = err.get("error") or "failed", err.get("status")
        if what == "breaker_open":
            raise base.SourceError(f"UW {EP}: breaker_open: the client stopped after repeated provider failures")
        if status in (401, 403):
            raise base.SourceError(f"UW {EP}: HTTP {status}: the key was refused")
        return None, err

    def _ticker_rows(self, ctx: base.RunContext, ticker: str):
        """One ticker's rows **below the floor**: ``older_than`` = :data:`PASS2_FROM`, paged on while a page comes
        back full. ``(body, error)``; the body is ``{"data": rows}`` so the raw file keeps the shape UW answers."""
        cursor, rows = PASS2_FROM.isoformat(), []
        for _ in range(MAX_TICKER_PAGES):
            body, err = self._ask(ctx, {"limit": PAGE_LIMIT, "ticker": ticker, "older_than": cursor})
            if err is not None:
                return None, err
            page = rows_of(body)
            rows += page
            if len(page) < PAGE_LIMIT:
                break
            nxt = oldest_stamp(page)
            if nxt is None or nxt == cursor:
                break
            cursor = nxt
        return {"data": rows}, None

    def _feed(self, ctx: base.RunContext, as_of: date) -> tuple[list[Path], list[str]]:
        """Pass 1: the market-wide feed, newest first, paged back with ``older_than`` to :data:`FLOOR`. Returns the
        day's feed files and the tickers they hold. A page already on disk is read, not asked again."""
        out, seen, cursor = [], [], None
        for page in range(MAX_FEED_PAGES):
            path = feed_path(as_of, page)
            if path.exists():
                rows = rows_of(base.read_raw_json(path).get("body"))
            else:
                if below_floor(cursor):
                    break
                params = {"limit": PAGE_LIMIT} if cursor is None else {"limit": PAGE_LIMIT, "older_than": cursor}
                body, err = self._ask(ctx, params)
                if err is not None:
                    ctx.issue("fetch_failed", f"feed page {page}", f"UW {EP}: {err.get('error')} {err.get('status')}")
                    raise base.SourceError(f"UW {EP} feed page {page}: {err.get('error')} "
                                           f"HTTP {err.get('status')}; {len(out)} pages kept")
                rows = rows_of(body)
                path = base.write_raw_json(path, {"request": {"endpoint": EP, "params": params}, "pass": "feed",
                                                  "page": page, "as_of": as_of.isoformat(), "fetched_at": time.time(),
                                                  "run_id": ctx.run_id, "body": body})
            out.append(path)
            seen += [str(r.get("ticker")).strip() for r in rows if isinstance(r, dict) and r.get("ticker")]
            if len(rows) < PAGE_LIMIT:
                break                                   # a short page is the end of the feed
            cursor = oldest_stamp(rows)
            if cursor is None:
                break
        else:
            ctx.notes.append(f"pass 1 stopped at the {MAX_FEED_PAGES}-page ceiling")
        ctx.notes.append(f"pass 1: {len(out)} feed pages, {len(set(seen))} tickers")
        return out, seen

    def _tickers(self, ctx: base.RunContext, as_of: date, seen: list[str]) -> list[Path]:
        """Pass 2: one call per ticker, delisted first. ``FAIL_STREAK`` provider-side failures stop the run and fail
        it; ``REJECT_STREAK`` rejects in a row are the path, not the tickers."""
        every = ticker_order(seen)
        out, failed, rejected, streak, held, streak_first = [], [], 0, 0, [], ""
        for n, ticker in enumerate(every):
            path = ticker_path(as_of, ticker)
            if path.exists():
                out.append(path)
                continue
            body, err = self._ticker_rows(ctx, ticker)
            if err is not None:
                failed.append(ticker)
                ctx.issue("fetch_failed", ticker, f"UW {EP}: {err.get('error')} HTTP {err.get('status')}")
                if is_rejected(err.get("status")):
                    held.append((ticker, err))
                    if len(held) >= REJECT_STREAK:
                        raise base.SourceError(
                            f"UW {EP}: {REJECT_STREAK} requests in a row rejected (first {held[0][0]}: "
                            f"{held[0][1].get('status')}), {len(every) - n - 1} not asked; the path, not the tickers")
                    continue
                streak += 1
                streak_first = streak_first or ticker
                if streak >= FAIL_STREAK:
                    raise base.SourceError(f"UW {EP}: {FAIL_STREAK} provider-side failures in a row (first "
                                           f"{streak_first}), {len(every) - n - 1} not asked; "
                                           f"{len(out)} tickers answered this run and kept")
                continue
            for t, e in held:
                out.append(base.write_raw_json(ticker_path(as_of, t), {
                    "request": {"endpoint": EP, "params": {"ticker": t, "older_than": PASS2_FROM.isoformat()}},
                "pass": "ticker", "ticker": t,
                    "as_of": as_of.isoformat(), "fetched_at": time.time(), "run_id": ctx.run_id,
                    "rejected": e, "body": None}))
            rejected += len(held)
            held, streak, streak_first = [], 0, ""
            out.append(base.write_raw_json(path, {
                "request": {"endpoint": EP, "params": {"ticker": ticker,
                                                       "older_than": PASS2_FROM.isoformat()}},
                "pass": "ticker", "ticker": ticker,
                "as_of": as_of.isoformat(), "fetched_at": time.time(), "run_id": ctx.run_id, "body": body}))
        ctx.notes.append(f"pass 2: {len(every)} tickers asked, {len(failed)} failed"
                         + (f" ({rejected} rejected by UW, kept as an empty answer)" if rejected else ""))
        return out

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        if not credentials.key_for(KEY):
            ctx.issue("missing_key", KEY, credentials.missing_message(KEY))
            ctx.notes.append("no UNUSUAL_WHALES_API_KEY: nothing asked")
            return []
        feed, seen = self._feed(ctx, as_of)
        try:
            return sorted(set(feed) | set(self._tickers(ctx, as_of, seen)))
        except base.SourceError:
            # What was answered stays: the raw files are the resume marker, and a failed fetch is not converted by
            # the runner, so the day's Parquet is written here before the run fails.
            self.to_parquet_all(ctx, self._raws(as_of))
            raise

    def _raws(self, as_of: date | str) -> list[Path]:
        return sorted(feed_dir(as_of).glob("*.json.gz")) + sorted(ticker_dir(as_of).glob("*.json.gz"))

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        # One read holds the whole archive this token can reach: a backfill is the same pass at its end day.
        self.to_parquet_all(ctx, self.fetch(ctx, end))

    # ── type ──
    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        return self.to_parquet_all(ctx, [raw])

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        """One Parquet file per as-of day, rewritten from every raw file of that day: the feed pages and the tickers
        overlap on purpose, so a rating event is kept once."""
        out, left = [], {}
        days = sorted({p.parent.parent.name for p in raws if p.parent.name in ("feed", "ticker")})
        for day in days:
            rows: dict[tuple, dict] = {}
            for raw in self._raws(day):
                doc = base.read_raw_json(raw)
                stamps = {"source_as_of": date.fromisoformat(doc["as_of"]), "fetched_at": float(doc["fetched_at"]),
                          "run_id": doc["run_id"]}
                got, counts = table_rows(doc.get("body"), stamps)
                for k, n in counts.items():
                    left[k] = left.get(k, 0) + n
                for r in got:
                    rows[(r["ticker"], r["published_at"], r["analyst_name"], r["firm"], r["action"],
                          r["recommendation"], r["target"])] = r
            con = base.scratch_con()
            try:
                base.rows_table(con, "rows", SCHEMA, [rows[k] for k in sorted(rows, key=lambda k: (k[0], k[1]))])
                out.append(base.write_parquet(con, "SELECT * FROM rows ORDER BY ticker, published_at",
                                              common.parquet_dir(NAME) / f"date={day}" / "part-0.parquet"))
            finally:
                con.close()
        if left:
            ctx.notes.append("rows left out: " + ", ".join(f"{k} {n}" for k, n in sorted(left.items())))
        return out

    # ── build ──
    def dirty(self, ctx: base.RunContext):
        """Not partitioned by company: staged whole by every build."""
        return dirty_set.ALL

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        common.stage_glob(con, STAGING, SCHEMA, common.parquet_dir(NAME), "date=*/part-0.parquet",
                          select="SELECT * FROM {src} QUALIFY row_number() OVER (PARTITION BY ticker, published_at, "
                                 "analyst_name, firm, action ORDER BY source_as_of DESC, fetched_at DESC) = 1")
        return {}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        rows = common.count(con, STAGING)
        tickers, oldest, newest, as_of = con.execute(
            f"SELECT count(DISTINCT ticker), min(published_at), max(published_at), max(source_as_of) "
            f"FROM {STAGING}").fetchone()
        ctx.notes.append(f"{rows} rating events for {tickers} tickers"
                         + (f", {oldest:%Y-%m-%d} to {newest:%Y-%m-%d}" if oldest and newest else ""))
        on = ctx.as_of or self.default_as_of()
        return {"dataset": NAME, "result": "changed" if rows else "unchanged",
                "source_as_of": (as_of or on).isoformat(), "rows": rows, "added": rows, "removed": 0,
                "coverage": None}


DATASET = UWScreenerAnalysts()
