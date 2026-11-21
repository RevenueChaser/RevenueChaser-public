"""The Welcome board's incremental build: stored inputs -> ``boards/welcome.duckdb`` (welcome plan §4, S16).

Three parts, each upserted from what changed since the **rows it already holds**; nothing is deleted.

There is no incremental mark, and the ``welcome_meta`` table the plan designed for one has **no writer** (#643,
found while building PR 5b/PR 6 in #1200). Comparing the stored rows is not a shortcut around a mark, it is the
stronger rule: a mark that drifts from the rows — a failed write after the mark moved, a row edited by hand, a
store restored from a backup — re-reads nothing and the drift is permanent, while a comparison converges on the
next pass. The table is left in place rather than dropped here, because dropping a board table is a store change
that carries its own backup and rollback.

- **Snapshot**: the last stored close of SPX, VIX, MOVE and the US 10-year yield, with the change on the session
  before and a 20-session line. A row is written only for a session newer than the series' stored one, or when the
  stored session's close changed. All four come from the builder's ``market.duckdb`` through their needs
  (#643 PR 5): the old ``prices.index_levels_daily``, ``raw.vol_index_daily`` and ``raw.macro_series`` reads are
  gone. A need that answers nothing writes no row, exactly as an empty old table did.
- **Earnings**: the names reporting today and on the next trading day, from the options builder's
  ``option_screener_daily`` through its needs (#643 PR 5b: ``earnings.next`` for the calendar row, and the spine's
  ``identity.security`` for a name the row does not carry). The old ``raw.earnings_calendar`` went with #860, which
  left this part writing nothing and the card showing the rows it last had. A name the newest built session no
  longer lists for one of the two days is **retired** (``retired_at``), never deleted.
- **Freshness**: one row per **builder file** (avo's D2 of 10 Nov 2026), rolled up from the builder's own run
  ledger ``job_runs2`` in ops (``rcdata.ops.builder_runs_since``), not from the dashboard's job rows: the old
  ``raw.job_runs`` went with #860 too. A file's row carries its last finished run, the last that ended well and the
  last that failed, so a file that has stopped building is on the card instead of missing from it.

No network, no provider call. The calendar card reads ``boards/news.duckdb`` at render time and copies nothing.
"""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from RevenueChaser.core import calendar as mcal
from RevenueChaser.core import rawstore
from RevenueChaser.core import reaction_anchor
from RevenueChaser.rcdata import needs, ops

logger = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")
SNAPSHOT, EARNINGS, FRESHNESS = "welcome_snapshot", "welcome_earnings", "welcome_freshness"
#: The table the plan designed for the incremental marks. Nothing writes it; see this module's docstring. It is
#: named here so a reader of the manifest finds the explanation, and so a test can hold that no build writes it.
META = "welcome_meta"
SPARK_DAYS = 20

#: series -> (need, its id in ``market_series``). The four share one table in ``market.duckdb``, so each is asked
#: for its own id: SPX and VIX are Cboe's, MOVE is Yahoo's ``^MOVE``, the 10-year yield FRED's ``DGS10``. MOVE has
#: no need of its own and goes through ``market.series``, which is why that need requires a named id.
SERIES = {
    "SPX": ("market.spx_close", "SPX"),
    "VIX": ("market.vix", "VIX"),
    "MOVE": ("market.series", "MOVE"),
    "US10Y": ("macro.dgs10", "DGS10"),
}
#: The stored ``report_session`` of a screener row, from the one timing vocabulary the repository keeps
#: (``core.reaction_anchor.timing_kind``): a provider spelling we do not know is ``unknown``, never guessed.
SESSION_OF_KIND = {"bmo": "premarket", "amc": "afterhours"}
UNKNOWN_SESSION = "unknown"
#: What each builder file is called on the freshness card, in the build order the Data flow draws. Every serving
#: kind has an entry, and a test holds that, so a new file cannot reach the card unnamed.
FILE_LABELS = {
    "spine": "Identity and the universe",
    "prices": "Prices and shares",
    "fundamentals": "Statements, filings and earnings",
    "ownership": "Who owns it, who is short",
    "options": "Options",
    "market": "Market-wide series",
    "sec_forms": "SEC forms",
    "sec_reads": "SEC reading service",
}
#: How far back the freshness roll-up reads the run ledger. Wider than the card's own window (7 days), so a file
#: that has not built for a week is a row that says so rather than a row that is not there.
FRESHNESS_LOOKBACK_DAYS = 30

#: Calendar days read back to hold ``SPARK_DAYS`` sessions: 20 sessions are 4 weeks, and a holiday or a provider's
#: gap makes them longer. The reader has no row limit, so the window is the bound.
SPARK_LOOKBACK_DAYS = 60


def ny_day(ts: float):
    return datetime.fromtimestamp(float(ts), NY).date()


def _value(row: dict) -> float | None:
    """The close of an OHLC row, else the one value column (Cboe's SPX and VIX, FRED's yields)."""
    v = row.get("close")
    return float(v) if v is not None else (float(row["value"]) if row.get("value") is not None else None)


def _observations(need: str, series_id: str, day: date) -> list[dict]:
    """The newest ``SPARK_DAYS`` observations of one series, newest first.

    An unreadable need is no rows, the way an empty old table was: the series keeps the row it already has and the
    next run tries again. ``needs.ask`` is the read, so a missing ``market.duckdb`` is a state and not an error.
    """
    try:
        ans = needs.ask(need, as_of=day, series_ids=[series_id], start=day - timedelta(days=SPARK_LOOKBACK_DAYS),
                        end=day)
    except Exception as exc:  # noqa: BLE001 - a need that cannot answer must not stop the other three
        logger.warning("welcome snapshot: %s (%s) could not be read: %s", need, series_id, exc)
        return []
    # One row per session: the table is keyed on the source as well, so a series served by two sources (or a
    # revision filed under a new one) would otherwise put two rows in the line and in the previous close.
    newest: dict[date, dict] = {}
    for r in ans.rows:
        if r.get("series_id") != series_id or _value(r) is None:
            continue
        held = newest.get(r["obs_date"])
        if held is None or (float(r.get("fetched_at") or 0.0), str(r.get("source") or "")) >= (
                float(held.get("fetched_at") or 0.0), str(held.get("source") or "")):
            newest[r["obs_date"]] = r
    days = sorted(newest)[-SPARK_DAYS:]
    return [{"session_date": d, "close": _value(newest[d])} for d in reversed(days)]


def earnings_days(now: float) -> tuple:
    """Today's New York trading day (or the next one on a closed day) and the trading day after it."""
    d = ny_day(now)
    first = d if mcal.is_trading_day(d) else mcal.next_trading_day(d)
    return first, mcal.next_trading_day(first)


def _snapshot(now: float, run_id: str) -> int:
    stored = {r["series"]: (r["session_date"], r["close"]) for r in rawstore.query(
        f"SELECT series, session_date, close FROM {SNAPSHOT} "
        "QUALIFY row_number() OVER (PARTITION BY series ORDER BY session_date DESC) = 1", db="welcome")}
    day = ny_day(now)
    rows = []
    for series, (need, series_id) in SERIES.items():
        got = _observations(need, series_id, day)
        old = stored.get(series)
        # A newer session, or a corrected close for the session already held (a revision, a later fetch).
        if not got or (old is not None and (got[0]["session_date"] < old[0] or
                                            (got[0]["session_date"] == old[0] and float(got[0]["close"]) == old[1]))):
            continue
        close = float(got[0]["close"])
        prev = float(got[1]["close"]) if len(got) > 1 else None
        rows.append({"series": series, "session_date": got[0]["session_date"], "close": close, "prev_close": prev,
                     "change": None if prev is None else close - prev,
                     "change_pct": None if not prev else (close - prev) / prev,
                     "spark": json.dumps([float(r["close"]) for r in reversed(got)]),
                     "run_id": run_id, "run_at": now})
    rawstore.write_rows(SNAPSHOT, rows)
    return len(rows)


def _report_session(value) -> str:
    """The stored row's session name, from the one timing vocabulary (``core.reaction_anchor``)."""
    return SESSION_OF_KIND.get(reaction_anchor.timing_kind(value) or "", UNKNOWN_SESSION)


def _as_day(value) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "")[:10]
    try:
        return date.fromisoformat(text) if text else None
    except ValueError:
        return None


def _screener(day: date) -> tuple[list[dict], date | None]:
    """The newest built session of the options screener, and the session it is.

    ``earnings.next`` answers the newest session only (``read.option_screener``), which is the one session UW's
    calendar was swept on. An unreadable need is no rows the way an empty old table was: the card keeps what it
    has and the next run tries again.
    """
    try:
        ans = needs.ask("earnings.next", as_of=day)
    except Exception as exc:  # noqa: BLE001 - a need that cannot answer must not stop the other parts
        logger.warning("welcome earnings: earnings.next could not be read: %s", exc)
        return [], None
    rows = list(ans.rows)
    session = max((d for d in (_as_day(r.get("session_date")) for r in rows) if d is not None), default=None)
    return rows, session


def _names(tickers: set[str]) -> dict[str, str]:
    """The spine's company names of ``tickers`` (``identity.security``); an unreadable need is no names."""
    if not tickers:
        return {}
    try:
        ans = needs.ask("identity.security", tickers=sorted(tickers))
    except Exception as exc:  # noqa: BLE001 - a missing name is a ticker on its own, not a failed build
        logger.warning("welcome earnings: identity.security could not be read: %s", exc)
        return {}
    return {str(r["ticker"]): str(r["name"]) for r in ans.rows if r.get("ticker") and r.get("name")}


def _earnings(now: float, run_id: str) -> int:
    """The two days' names from the screener's newest session; a name it no longer lists is retired.

    The ± the card prints is the calendar's ``expected_move_perc``, the field the old table carried, and the
    screener's own ``implied_move_perc`` where the calendar has none: one number, with the same meaning as before.
    """
    days = earnings_days(now)
    rows, session = _screener(ny_day(now))
    if session is None:
        return 0
    held = {(r["earnings_date"], r["ticker"], r["report_session"]): r for r in rawstore.query(
        f"SELECT * FROM {EARNINGS} WHERE earnings_date IN (?, ?)", [days[0], days[1]], db="welcome")}
    out, seen = [], set()
    listed = [r for r in rows if _as_day(r.get("report_date")) in days and r.get("ticker")]
    missing_name = {str(r["ticker"]) for r in listed if not str(r.get("full_name") or "").strip()}
    names = _names(missing_name)
    for r in listed:
        ticker = str(r["ticker"])
        key = (_as_day(r.get("report_date")), ticker, _report_session(r.get("report_session")))
        if key in seen:
            continue
        seen.add(key)
        move = r.get("expected_move_perc")
        if move is None:
            move = r.get("implied_move_perc")
        before = held.get(key)
        out.append({"earnings_date": key[0], "ticker": ticker, "report_session": key[2],
                    "full_name": (str(r.get("full_name") or "").strip() or names.get(ticker) or None),
                    "expected_move_perc": None if move is None else float(move),
                    "report_time": r.get("report_time") or None, "source_session": session,
                    "first_seen": (before or {}).get("first_seen") or now, "last_seen": now,
                    "retired_at": None, "run_id": run_id, "run_at": now})
    for key, before in held.items():
        if key in seen or before.get("retired_at") is not None:
            continue
        out.append({**before, "retired_at": now, "run_id": run_id, "run_at": now})
    rawstore.write_rows(EARNINGS, out)
    return len(out)


def _file_of_dataset(name: str) -> str | None:
    """The serving file dataset ``name`` builds, from the builder's own registry (never a list kept here)."""
    try:
        from RevenueChaser.rcdata.build import DATASETS
    except Exception:  # noqa: BLE001 - without the registry there is no roll-up, and no broken build
        return None
    ds = DATASETS.get(str(name))
    return getattr(ds, "kind", None) if ds is not None else None


def _freshness(now: float, run_id: str) -> int:
    """One row per builder file from the builder's run ledger in ops (avo's D2 of 10 Nov 2026).

    ``ok`` and ``skipped`` are a file that built (a skip is "nothing was due"); anything else is an error, with the
    run's own message. A file with no finished run inside the window gets no row, and the card says so in its own
    words rather than claiming a state nothing recorded.
    """
    try:
        runs = ops.builder_runs_since(now - FRESHNESS_LOOKBACK_DAYS * 86400)
    except Exception as exc:  # noqa: BLE001 - the ops store not answering is not a failed board build
        logger.warning("welcome freshness: the run ledger could not be read: %s", exc)
        return 0
    per_file: dict[str, dict] = {}
    for run in runs:
        kind = _file_of_dataset(run.get("dataset"))
        if kind is None or kind not in FILE_LABELS:
            continue
        finished = float(run.get("finished_at") or 0.0)
        if not finished:
            continue
        good = str(run.get("status") or "") in ("ok", "skipped")
        row = per_file.setdefault(kind, {"job": kind, "last_status": None, "last_finished_at": 0.0,
                                         "last_ok_at": None, "last_failed_at": None, "last_error": None,
                                         "run_id": run_id, "run_at": now})
        if finished >= row["last_finished_at"]:
            row["last_finished_at"] = finished
            row["last_status"] = "ok" if good else "error"
            row["last_error"] = None if good else (str(run.get("error") or "")[:500] or None)
        if good:
            row["last_ok_at"] = max(row["last_ok_at"] or 0.0, finished)
        else:
            row["last_failed_at"] = max(row["last_failed_at"] or 0.0, finished)
    rows = [per_file[k] for k in FILE_LABELS if k in per_file]
    rawstore.write_rows(FRESHNESS, rows)
    return len(rows)


def build(now: float | None = None, run_id: str | None = None) -> dict:
    """One incremental pass. Returns counts: ``snapshot``, ``earnings``, ``freshness``."""
    now = time.time() if now is None else now
    run_id = run_id or f"welcome-{int(now)}"
    snap = _snapshot(now, run_id)
    earn = _earnings(now, run_id)
    fresh = _freshness(now, run_id)
    return {"snapshot": snap, "earnings": earn, "freshness": fresh}
