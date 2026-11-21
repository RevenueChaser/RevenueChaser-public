"""Runners — thin wrappers that run modules and write stable ``latest.html`` files.

These are the glue between the dashboard server and the existing engines/exporters.
Each runner returns the Path to the generated file (or None if nothing was produced).
"""
import json
import logging
import time
from datetime import date, timedelta
from pathlib import Path

from RevenueChaser.core.providers.unusual_whales import UWClient
from RevenueChaser.core.config import OUTPUT_DIR
from RevenueChaser.module_earnings_radar.pipeline import EarningsPipeline
from RevenueChaser.core import job_lock, ledger
from .jobs import GAPS, JobMessage, run_id

logger = logging.getLogger(__name__)


def _freeze_run_id() -> str:
    """``run_id`` for a forecast-ledger freeze: the running job's id, else a fresh one (#128)."""
    return run_id()


def _write_output(module: str, content: str, suffix: str, ext: str = "html") -> Path:
    """Write a stable ``{module}_latest.{ext}`` regenerable file under ``.cache/``.

    - HTML dashboards live under ``.cache/{module}_latest.{ext}``.
    - JSON lives under ``.cache/{module}/{module}_latest.json``.
    """
    if ext == "json":
        stable = OUTPUT_DIR / module / f"{module}_latest.json"
    else:
        stable = OUTPUT_DIR / f"{module}_latest.{ext}"
    stable.parent.mkdir(parents=True, exist_ok=True)
    from RevenueChaser.core.reporting_common import write_artifact
    return write_artifact(stable, content)

def _write_to(path: Path, content: str) -> Path:
    """Write one regenerable artifact at ``path``: the board's own constant, so the writer and every reader of it
    name one file (#111: a second spelling built from OUTPUT_DIR drifted from the constant a test redirected)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    from RevenueChaser.core.reporting_common import write_artifact
    return write_artifact(path, content)


def _run_asof(payload) -> str | None:
    """The board's own as-of word for its v2 envelope (#1241), read from the run payload.

    The K10 payload file carries the rows alone (``{"rows": ...}``, ``{"companies": ...}``), so the date the data
    speaks for is here, in the payload the renderer was given: ``v2_envelope.ASOF_KEYS`` in order.
    """
    from RevenueChaser.core import v2_envelope
    return v2_envelope.data_asof(payload)


def _write_board(path: Path, html: str, data, asof=None) -> Path:
    """Write a board's HTML, its K10 payload file and its v2 envelope (``reporting_common.write_board``).

    ``data=None`` drops both files. ``asof`` is the board's own as-of word for the envelope (#1241): the K10
    payload holds the rows only, so the date lives in the run payload the caller still has in hand.
    """
    from RevenueChaser.core.reporting_common import write_board
    return write_board(path, html, data, asof=asof)


def _write_empty_board(path: Path, title: str, message: str, hint: str = "") -> Path:
    """Write an explicit "nothing to show, and here is why" board.

    A run that produces no rows must still overwrite its artifact. Returning
    early instead left the previous (or missing) file in place, so the job
    reported success and the tab visibly did nothing — indistinguishable from a
    broken refresh.

    Markup lives in ``templates/empty_board.html.j2``. A plain Jinja environment
    rather than ``flask.render_template``: runners execute on the job-queue
    worker thread, which has no Flask app context.
    """
    from datetime import datetime, timezone
    from RevenueChaser.core import templating
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    from RevenueChaser.core.reporting_common import write_artifact
    return write_artifact(path, templating.render(
        "empty_board.html.j2", title=title, message=message, hint=hint, stamp=stamp))


def _uw_health(uw) -> dict | None:
    """``uw.health()`` for the board banner (MB3), or None without a real client
    (store-only renders and test doubles pass ``uw=None``)."""
    fn = getattr(uw, "health", None)
    if not callable(fn):
        return None
    try:
        return fn()
    except Exception:  # noqa: BLE001 - a banner must never break a render
        return None


def _provider_gap_text(uw) -> str | None:
    """Why an empty result is a provider failure, not "no data" (ER-1), or None."""
    auth = getattr(uw, "auth_error", None)
    if isinstance(auth, dict) and auth:
        return (f"Unusual Whales rejected the API key (HTTP {auth.get('status', '?')}). "
                "Check UNUSUAL_WHALES_API_KEY in .env.")
    health = _uw_health(uw) or {}
    if int(health.get("failed") or 0) > 0:
        return (f"{health['failed']} of {health.get('calls') or health['failed']} "
                "Unusual Whales calls failed.")
    return None


def _no_events_text(start: date, end: date) -> tuple[str, str]:
    """(message, hint) for an earnings range that returned no events."""
    same_day = start == end
    when = f"{start.isoformat()}" if same_day else f"{start.isoformat()} → {end.isoformat()}"
    weekend = same_day and start.weekday() >= 5
    message = f"No earnings events scheduled for {when}."
    if weekend:
        hint = ("That date is a weekend — US issuers do not report. Pick a "
                "weekday, or use the range picker to load the week ahead.")
    else:
        hint = ("The provider returned an empty calendar for this range. Try a "
                "wider range, or check the Unusual Whales key if every board is empty.")
    return message, hint


def _coerce_earnings_days(start=None, end=None, dates=None) -> list[date]:
    """Resolve a discrete day list from ``dates=`` or a contiguous ``start``/``end``."""
    if dates:
        if isinstance(dates, str):
            parts = [p.strip() for p in dates.split(",") if p.strip()]
            return sorted({date.fromisoformat(p) for p in parts})
        out: list[date] = []
        for d in dates:
            out.append(d if isinstance(d, date) else date.fromisoformat(str(d)))
        return sorted(set(out))
    if start is None:
        return []
    if end is None:
        end = start
    days = []
    d = start
    while d <= end:
        days.append(d)
        d += timedelta(days=1)
    return days


def _no_events_text_days(days: list[date]) -> tuple[str, str]:
    if not days:
        return "No earnings events scheduled.", "Pick at least one weekday."
    if len(days) == 1 or days[-1] - days[0] == timedelta(days=len(days) - 1):
        return _no_events_text(days[0], days[-1])
    when = ", ".join(d.isoformat() for d in days)
    message = f"No earnings events scheduled for {when}."
    hint = ("The provider returned an empty calendar for these days. Try other "
            "weekdays, or check the Unusual Whales key if every board is empty.")
    return message, hint


EARNINGS_LATEST = OUTPUT_DIR / "earnings_radar_latest.html"
NEWS_LATEST = OUTPUT_DIR / "news_latest.html"
WELCOME_LATEST = OUTPUT_DIR / "welcome_latest.html"
ROTATION_LATEST = OUTPUT_DIR / "sector_rotation_latest.html"
MONEY_FLOW_LATEST = OUTPUT_DIR / "sector_rotation" / "sector_rotation_latest.json"
ETF_HOLDINGS_CACHE = OUTPUT_DIR / "sector_rotation" / "etf_holdings.json"  # legacy path; store is raw.duckdb
SEC_13F_LATEST = OUTPUT_DIR / "sec_13f_latest.html"
QUICK_LATEST = OUTPUT_DIR / "financials_latest.html"
QUICK_STATE = OUTPUT_DIR / "financials" / "financials_latest.json"
ASYMMETRIC_GROWTH_LATEST = OUTPUT_DIR / "asymmetric_growth_latest.html"
ASYMMETRIC_GROWTH_JSON = OUTPUT_DIR / "asymmetric_growth" / "asymmetric_growth_latest.json"
SWING_LATEST = OUTPUT_DIR / "swing_potential_latest.html"
SWING_JSON = OUTPUT_DIR / "swing_potential" / "swing_potential_latest.json"
FUNDAMENTALS_LATEST = OUTPUT_DIR / "fundamentals_latest.html"
FUNDAMENTALS_JSON = OUTPUT_DIR / "fundamentals" / "fundamentals_latest.json"
COMOVEMENT_LATEST = OUTPUT_DIR / "comovement_latest.html"
COMOVEMENT_JSON = OUTPUT_DIR / "comovement" / "comovement_latest.json"
VALUE_CHAIN_LATEST = OUTPUT_DIR / "value_chain_latest.html"
VALUE_CHAIN_JSON = OUTPUT_DIR / "value_chain" / "value_chain_latest.json"
RELATEDNESS_LATEST = OUTPUT_DIR / "relatedness_latest.html"
RELATEDNESS_JSON = OUTPUT_DIR / "relatedness" / "relatedness_latest.json"
RELATEDNESS_PEERS_DIR = OUTPUT_DIR / "relatedness" / "peers"   # <TICKER>.json, served by /api/relatedness/peers/
OIPD_LATEST = OUTPUT_DIR / "oipd_latest.html"
OIPD_JSON = OUTPUT_DIR / "oipd" / "oipd_latest.json"
SETTINGS_LATEST = OUTPUT_DIR / "settings_latest.html"

def _load_watchlist() -> set:
    """avo's picks (``rcdata.read.picked``: his own watch lists and the stock list): Earnings' and Welcome's watched
    names. An unreadable list is left out, as on a page."""
    from RevenueChaser.rcdata import read
    return read.picked()


def _compute_nrc_results(cards) -> dict:
    from RevenueChaser.module_earnings_radar.pipeline import nrc_from_card
    wl = _load_watchlist()
    return {card.ticker: nrc_from_card(card, wl) for card in cards}


def _calendar_event(item: dict, d: date, session: str) -> dict | None:
    """One UW calendar row as the run's event dict, or None when the row names no ticker.

    ``source`` stays "UW" for a stored row too: ``history._input_problems`` counts these against
    ``UW_CALENDAR_ROW_LIMIT``, the most rows the client reads per session, whichever path served them.
    """
    t = item.get("symbol") or item.get("ticker", "")
    if not t:
        return None
    return {
        "ticker": t, "earnings_date": d,
        "earnings_time": "BMO" if session == "premarket" else "AMC",
        "sector": item.get("sector", ""),
        "full_name": item.get("full_name", ""),
        "marketcap": item.get("marketcap", ""),
        "expected_move_perc": item.get("expected_move_perc"),
        "street_mean_est": item.get("street_mean_est"),
        "pre_earnings_close": item.get("pre_earnings_close"),
        "post_earnings_close": item.get("post_earnings_close"),
        "report_time": item.get("report_time", ""),
        "source": "UW",
    }


# The coverage of the run's last ``_fetch_calendar_days`` (E5a, #372), for the history's ``input_sources``. A
# module-level slot rather than a third return value: every caller and test fake unpacks two.
_CALENDAR_SOURCES: dict = {}


def _fetch_calendar_days(uw: UWClient, days: list[date]) -> tuple[list, dict]:
    """Calendar events for the given days (weekends skipped), premarket first so ``raw_cal``'s "premarket wins"
    rule holds.

    The served calendar answers first, pair by pair (``stored_inputs.calendar_items``: the newest built session's
    ``option_screener_daily`` rows, which carry the UW calendar's own expected move since #273's data half). UW is
    asked only for the pairs the store does not cover — a day outside the built session's window, a session too
    old to read, and always today and the next trading day, whose numbers UW still moves. Either way the event is
    built by ``_calendar_event``, so a stored pair and a live pair cannot drift apart, and ``source`` stays "UW".
    """
    from RevenueChaser.module_earnings_radar.stored_inputs import calendar_items
    try:
        stored, session = calendar_items(days)
    except Exception as e:  # noqa: BLE001 - a store error is "nothing stored", never a failed Fetch
        logger.warning(f"Stored calendar read failed, asking UW for every day: {e}")
        stored, session = {}, None

    events = []
    raw_cal = {}
    n_live = n_stored = 0
    for d in days:
        if d.weekday() >= 5:
            continue
        for sess in ("premarket", "afterhours"):
            items = stored.get((d, sess))
            if items is None:
                n_live += 1
                items = uw.calendar_day_raw(d, sess)
            else:
                n_stored += 1
            for item in items:
                ev = _calendar_event(item, d, sess)
                if ev is None:
                    continue
                events.append(ev)
                t = ev["ticker"]
                if t not in raw_cal or sess == "premarket":
                    raw_cal[t] = ev
    _CALENDAR_SOURCES.clear()
    _CALENDAR_SOURCES.update({"stored": n_stored, "live": n_live,
                              "session": session.isoformat() if session and n_stored else None})
    return events, raw_cal


def _fetch_calendar_range(uw: UWClient, start: date, end: date) -> tuple[list, dict]:
    """Fetch UW calendar events for [start, end], returning (events, raw_cal)."""
    return _fetch_calendar_days(uw, _coerce_earnings_days(start, end))


def _no_cards_text(n_tickers: int, stats: dict | None, gap: str | None) -> str:
    """Why a run with calendar events scored nothing (E23)."""
    stats = stats or {}
    if stats.get("filtered") and not stats.get("passed") and not stats.get("bypassed"):
        by_reason = stats.get("by_reason") or {}
        if set(by_reason) == {"no screener row"}:      # E2, #372: unknown liquidity, not a failed gate
            return (f"No UW screener row for any of the {n_tickers} calendar tickers; nothing was scored."
                    + (f" {gap}" if gap else ""))
        reasons = ", ".join(f"{k} {v}" for k, v in sorted(by_reason.items(), key=lambda kv: -kv[1]))
        return (f"All {n_tickers} calendar tickers failed the filter gates ({reasons}); nothing was scored."
                + (f" {gap}" if gap else ""))
    return (f"{n_tickers} calendar tickers could not be scored; see the dashboard log."
            + (f" {gap}" if gap else ""))


def run_earnings_range(uw: UWClient, start: date | None = None, end: date | None = None,
                       dates=None) -> Path:
    """Run the earnings pipeline for a date range or a discrete day list."""
    days = _coerce_earnings_days(start, end, dates)
    run_at = time.time()   # one clock for the board stamp and the history header (ER-9, #372)
    _CALENDAR_SOURCES.clear()          # a patched calendar read leaves the slot empty, not the last run's
    if dates:
        events, raw_cal = _fetch_calendar_days(uw, days)
        empty_msg = _no_events_text_days(days)
        span = (min(days), max(days)) if days else None
    else:
        events, raw_cal = _fetch_calendar_range(uw, start, end if end is not None else start)
        empty_msg = _no_events_text(start, end if end is not None else start)
        span = (start, end if end is not None else start)
    watchlist_sources = None
    if span:
        # The CLI adds the watchlist names the session calendar omits (unknown time, estimated
        # date); the dashboard Fetch did not, so they dropped off the board (#198 E15).
        from RevenueChaser.module_earnings_radar.watchlist_augment import augment_calendar
        # Served first, UW only for the names the store does not cover (#1138).
        watchlist_sources = augment_calendar(uw, events, raw_cal, _load_watchlist(), span[0], span[1],
                                             days=days if dates else None)
    calendar_sources = dict(_CALENDAR_SOURCES) or {"stored": 0, "live": 0, "session": None}
    if not events:
        gap = _provider_gap_text(uw)
        if gap:
            # ER-1: an empty calendar after a rejected key or an outage is not
            # "no earnings scheduled" — say what actually happened.
            message = f"Could not load the earnings calendar: {gap}"
            _write_empty_board(EARNINGS_LATEST, "Earnings Radar", message,
                               "Run Fetch again later; the previous calendar is not shown.")
            raise JobMessage(message)
        message, hint = empty_msg
        _write_empty_board(EARNINGS_LATEST, "Earnings Radar", message, hint)
        raise JobMessage(message)

    tickers = list(dict.fromkeys(e["ticker"] for e in events))

    try:
        from RevenueChaser.module_sector_rotation.engine import rotation_quadrant_map
        etf_quadrant_map = rotation_quadrant_map(uw)
    except Exception as e:
        logger.warning(f"Rotation engine failed: {e}")
        etf_quadrant_map = {}

    pipeline = EarningsPipeline(tickers, uw, raw_cal, etf_quadrant_map=etf_quadrant_map)
    # What the calendar read came from (E5a, #372): pairs covered by the store vs pairs asked of UW live.
    sources = getattr(pipeline, "input_sources", None)
    if isinstance(sources, dict):
        sources["calendar"] = calendar_sources
        if isinstance(watchlist_sources, dict):
            # The watchlist augmentation's own coverage (#1138): names answered by the served screener set vs asked
            # of UW. ``None`` (a run with no span) leaves the slot out rather than claiming a zero.
            sources["watchlist"] = watchlist_sources
    cards = pipeline.run(use_preselect=True)

    from RevenueChaser.module_earnings_radar.report import export_html, screener_problem

    nrc = _compute_nrc_results(cards)
    # A partial/failed screener answer is told on the board (E2, #372).
    screener = getattr(pipeline, "screener_result", None)
    export_html(cards, events, nrc, filename=str(EARNINGS_LATEST.relative_to(OUTPUT_DIR)),
                filter_stats=pipeline._filter_stats, provider_health=_uw_health(uw),
                notice=screener_problem(screener), run_at=run_at)
    # Last step of the Fetch, after the board file is written (#580). The Earnings Radar has no Refresh, so every
    # run is a Fetch. A refused freeze is a note, never a JobMessage; a freeze *error* propagates, so the job shows it.
    from RevenueChaser.module_earnings_radar import freeze as earnings_freeze
    earnings_freeze.freeze_cards(cards, run_id=_freeze_run_id())
    if not cards:
        # E23: an empty table with a "done" job reads as a broken Fetch. Say why.
        raise JobMessage(_no_cards_text(len(tickers), pipeline._filter_stats, _provider_gap_text(uw)))
    return EARNINGS_LATEST


def run_rotation_latest(uw: UWClient, benchmark: str = "SPY", start: str = None,
                        end: str = None) -> Path:
    from RevenueChaser.module_sector_rotation.engine import (
        RotationEngine, fetch_all_holdings, sector_etf_trees,
    )
    from RevenueChaser.module_sector_rotation.report import export_rotation_dashboard
    from RevenueChaser.module_sector_rotation import engine as rotation_engine, store as rotation_store

    kept, notes = None, []
    short, stale = [], None
    if start or end:
        # Range fetch: reconstruct snapshots for every week in [start, end].
        from datetime import date as _date
        e = _date.fromisoformat(end) if end else _date.today()
        if start:
            s = _date.fromisoformat(start)
            if e < s:  # picker sent the ends the other way round
                s, e = e, s
        else:
            # Open start: run from the earliest stored date. With an empty store
            # the fallback must not overshoot ``end`` (defaulting to today would
            # silently widen an end-bounded request past what was asked for).
            dates = rotation_store.list_snapshot_dates()
            s = _date.fromisoformat(dates[0]) if dates else e
            s = min(s, e)
        backfill = rotation_store.backfill_weekly(uw, s, e)
        # Days the backfill refused to write (D01 short of SPY for them) go in the
        # job message, so a gap in the trail is explained instead of looking like a quiet week.
        backfill_note = getattr(backfill, "message", lambda: "")()
        if backfill_note:
            notes.append(backfill_note)
        # Load only the requested window (loading every stored date made the range picker a no-op),
        # then keep each ticker's newest row in it: one map row per ETF, and the header shows the
        # newest date (DF66). The trail page shows the weeks.
        snapshots = _latest_per_ticker(_load_rotation_snapshots(s, e))
    else:
        backfill_note = ""
        # M-ROT-2: D01 weekly closes (no UW candle), dated by the session they end on (#283).
        engine = RotationEngine(uw, benchmark=benchmark)
        snapshots = engine.process_all()
        if not snapshots:
            return _rotation_empty_fetch(uw, benchmark)
        short = list(getattr(engine, "too_short", None) or [])
        stale = getattr(engine, "stale", None)
        early = stale or ("an intraday run (the US session is open)" if getattr(engine, "intraday", False) else None)
        # ROT-5: a symbol with no series is missing. A thinner pull must not replace a session snapshot that covers
        # more ETFs (since A1 the other points would not move, but the missing ETF's row would be lost). #283: a run that is not a
        # complete session (intraday, or D01 short of the session) never replaces a stored one at least as wide.
        # The stored rows are shown and kept; the job says why. Too-short symbols are a warning, never missing.
        missing = _rotation_missing(snapshots, short)
        stored = _stored_session_snapshot(snapshots, same_width=bool(early)) if (missing or early) else []
        if stored:
            why = "; ".join(filter(None, [
                f"{len(missing)} of {len(missing) + len(snapshots)} rotation ETFs are missing from the live RRG "
                f"pull (no stored series up to the session): {', '.join(missing)}" if missing else "",
                f"this run is not a complete session ({early})" if early else ""]))
            kept = (f"{why}; kept the stored snapshot of the {stored[0].as_of_date.isoformat()} session "
                    f"({len(stored)} ETFs)")
            notes.append(f"{kept}.")
            snapshots, stale = stored, None
        else:
            day = getattr(snapshots[0], "as_of_date", None)
            rotation_store.save_snapshot(snapshots, as_of=day, benchmark=benchmark)
            if missing:
                notes.append(f"{len(missing)} of {len(missing) + len(snapshots)} rotation ETFs are missing from the "
                             f"live RRG pull (no stored series up to the session): {', '.join(missing)}. Saved without "
                             "them.")
            if stale:
                notes.append(f"{stale}.")
        if short:
            notes.append(f"{len(short)} rotation symbol(s) have under {rotation_engine.MIN_WEEKS} weeks of stored "
                         f"daily bars and are left off the map until their history grows: {', '.join(short)}.")
    # Embed holdings so the served map is self-contained (expandable rows work
    # even if the holdings route is unavailable / server is stale). Theme rows
    # only (ROT-4): sector rows expand to the sector -> industry tree
    # (cap-weighted, from the shared universe) rather than a 10-name ETF snapshot.
    holdings = fetch_all_holdings(uw, snapshots) if snapshots else {}
    # The holdings view reads these RS rows (#642 PR 5: the Fetch stores them now that the holdings job is gone).
    # An ETF the Fetch priced none for keeps what it stored.
    for etf, rows in holdings.items():
        rotation_store.save_holdings_cache(etf, rows)
    sector_holdings = sector_etf_trees() if snapshots else {}
    health = _uw_health(uw)
    html_path = export_rotation_dashboard(snapshots, filename=str(ROTATION_LATEST.relative_to(OUTPUT_DIR)),
                                          uw=uw, benchmark=benchmark, holdings=holdings,
                                          sector_holdings=sector_holdings,
                                          provider_health=health)
    if notes:
        raise JobMessage(" ".join(notes))
    return html_path


def _rotation_missing(snapshots, short=()) -> list[str]:
    """Map ETFs the live pull did not return, in universe order; the too-short ones (a warning) are not, and neither are
    the macro series, which are never on the map (B1)."""
    from RevenueChaser.module_sector_rotation.engine import rrg_tickers
    got = {s.ticker for s in snapshots}
    return [t for t in rrg_tickers() if t not in got and t not in short]


def _stored_session_snapshot(snapshots, same_width: bool = False) -> list:
    """The stored snapshot of the live pull's session when it holds every ETF the pull returned and more, else ``[]``.
    With ``same_width`` (a run that is not a complete session) one holding exactly the same ETFs qualifies too.

    A complete stored snapshot always qualifies. So does one that lacks only ETFs this pull lacks too: an ETF whose
    series is short on every run must not make every stored session replaceable by a thinner pull."""
    from RevenueChaser.module_sector_rotation import store as rotation_store
    from RevenueChaser.module_sector_rotation.report import _rows_to_snapshots
    day = getattr(snapshots[0], "as_of_date", None)
    if day is None:
        return []
    from RevenueChaser.module_sector_rotation.universe import MACRO_SERIES
    # a row stored before B1 may hold a macro series, which a pull never returns any more: not an ETF the pull lacks
    rows = [r for r in (rotation_store.load_snapshot(day) or {}).get("etfs") or [] if r.get("ticker") not in MACRO_SERIES]
    stored, live = {r.get("ticker") for r in rows}, {s.ticker for s in snapshots}
    return _rows_to_snapshots(rows) if rows and (stored > live or (same_width and stored >= live)) else []


def _rotation_empty_fetch(uw, benchmark) -> Path:
    """A live Fetch whose RRG pull returned no ETF (ROT-5): the board is not blanked.

    The board file stays as it is; only a first run, with no board yet, writes the empty map. The job says so."""
    from RevenueChaser.module_sector_rotation.report import export_rotation_dashboard
    health = _uw_health(uw)
    if ROTATION_LATEST.exists():
        what = "the board was not rewritten (it keeps its last render)"
    else:
        export_rotation_dashboard([], filename=str(ROTATION_LATEST.relative_to(OUTPUT_DIR)), uw=uw,
                                  benchmark=benchmark, provider_health=health)
        what = "the board shows its empty state"
    raise JobMessage(" ".join(filter(None, [
        _provider_gap_text(uw), f"The live RRG pull returned no ETF; {what}."])))


def _latest_per_ticker(snapshots) -> list:
    """Each ticker's newest snapshot, in first-seen order (DF66)."""
    newest: dict = {}
    for snap in snapshots:
        cur = newest.get(snap.ticker)
        if cur is None or snap.as_of_date >= cur.as_of_date:
            newest[snap.ticker] = snap
    return list(newest.values())


def _load_rotation_snapshots(start: date = None, end: date = None):
    """Stored rotation snapshots as ETFRotationSnapshot objects.

    With ``start``/``end`` only that window is loaded (one query), which is what
    the range picker asks for. Without them every stored date is returned.
    """
    from RevenueChaser.module_sector_rotation import store as rotation_store
    from RevenueChaser.module_sector_rotation.report import _rows_to_snapshots
    out = []
    if start is not None or end is not None:
        dates = rotation_store.list_snapshot_dates()
        lo = start.isoformat() if start else (dates[0] if dates else "")
        hi = end.isoformat() if end else (dates[-1] if dates else "")
        for _, rows in sorted(rotation_store.load_range(
                date.fromisoformat(lo), date.fromisoformat(hi)).items()):
            out.extend(_rows_to_snapshots(rows))
        return out
    for d in rotation_store.list_snapshot_dates():
        snap = rotation_store.load_snapshot(date.fromisoformat(d))
        if snap:
            out.extend(_rows_to_snapshots(snap.get("etfs", [])))
    return out


_MF_WINDOW, _MF_TOP_N = 21, 10           # the Money Flow leaderboard: 21-day window, top 10 per side


def run_money_flow_latest(uw: UWClient, days: int = 30) -> Path:
    """Compute the 21-day money-flow leaderboard (top 10) and cache to JSON."""
    import json
    from datetime import datetime
    from RevenueChaser.module_sector_rotation.money_flow import compute_money_flow

    result = compute_money_flow(days=days, window=_MF_WINDOW, top_n=_MF_TOP_N)
    partial = bool(result.get("partial"))
    empty = not (result.get("inflows") or result.get("outflows"))
    try:
        prev = json.loads(MONEY_FLOW_LATEST.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        prev = {}
    shown = bool(prev.get("inflows") or prev.get("outflows"))
    prev_when = prev.get("as_of") or prev.get("generated_at") or "the last run"
    missing = result.get("missing") or []
    why = ("Money flow came back empty (no stored daily bars to rank)" if empty else
           f"Money flow is partial ({len(missing)} ETF(s) with no stored daily bars up to the session: "
           f"{', '.join(missing)})")
    # An empty pull never replaces a board file with rows, and a partial one never replaces a whole one (PL2, #166).
    if (empty or partial) and shown and (empty or not prev.get("partial")):
        raise JobMessage(f"{why}; kept the stored leaderboard from {prev_when}.")
    result["generated_at"] = datetime.now().isoformat()
    _write_output("sector_rotation", json.dumps(result, indent=2), "latest", ext="json")
    if partial:
        raise JobMessage(f"{why}; saved flagged on the board.")
    return MONEY_FLOW_LATEST


def run_sec_13f_latest(uw: UWClient | None = None, notice: str | None = None,
                       provider_health: dict | None = None, capture: dict | None = None) -> Path:
    """Render the SEC 13F total-ownership dashboard from cached totals.

    No API calls — reads the board file's totals, the meta and the snapshot inputs from the stores: shares
    outstanding (the shared reader, #646), FINRA short interest (#576), quarter-end prices from D01, split factors
    and filer breaks (``enrich.load_inputs``). The Fetch renders through here too, so a Refresh shows the numbers
    the Fetch showed. The board banner comes from ``provider_health`` (or ``uw.health()`` when a client is
    passed), and ``notice`` adds a one-line note (e.g. "names were not refreshed"). ``capture`` (the Fetch only)
    receives the totals, meta and inputs (under ``enrichment``) the board was rendered from, for the result
    history (#375).
    """
    from RevenueChaser.module_sec_13f import engine as sec_13f
    from RevenueChaser.module_sec_13f.enrich import load_inputs
    from RevenueChaser.module_sec_13f.report import export_sec13f_dashboard
    from RevenueChaser.module_sec_13f import store as board_store

    try:
        # The board's own file (#732): brought up to the live ownership build once a build or a day, then read.
        _t, _b, written = board_store.sync()
        if written:
            logger.info("13F board file updated from the ownership build")
    except Exception as exc:                      # noqa: BLE001 - the board still renders from the builder
        logger.exception("13F board file was not updated")
        notice = "; ".join(n for n in (notice, f"13F board file not updated: {type(exc).__name__}") if n)
    # The unmapped-CUSIP note is the store's (``_13f_coverage_note``), so a store-only Refresh says it too (#77).
    coverage = _13f_coverage_note()
    if coverage and coverage not in (notice or ""):
        notice = "; ".join(n for n in (notice, coverage) if n)
    totals = sec_13f.load_totals()
    if capture is not None:
        capture["totals"] = totals
    if not totals:
        # Say so on the board instead of leaving the old (or no) file behind.
        _write_empty_board(
            SEC_13F_LATEST, "SEC 13F", "No 13F ownership totals are stored yet.",
            "Press Fetch to download and ingest the newest SEC Form 13F data set.")
        from RevenueChaser.core.reporting_common import drop_board_data
        # K10 + the v2 envelope: the rows go with the rows' file (#429), and so does the door's copy of them.
        drop_board_data(SEC_13F_LATEST)
        raise JobMessage("No 13F totals stored yet — press Fetch to ingest the SEC data set.")
    meta, enrichment = sec_13f.load_sec13f_meta(), load_inputs(totals)
    if capture is not None:
        capture.update(meta=meta, enrichment=enrichment)
    export_sec13f_dashboard(totals, meta, enrichment,
                            filename="sec_13f_latest.html",
                            provider_health=provider_health or _uw_health(uw) or _sec13f_health(),
                            notice=notice)
    return SEC_13F_LATEST


def _sec13f_busy_message() -> str:
    """The message a refused 13F job ends with: another Fetch, rebuild or map holds the family's lock (#26)."""
    pid = dict(job_lock.holders()).get("sec_13f", 0)
    who = f" (pid {pid})" if pid else ""
    return f"A 13F job is already running{who}; nothing was written."


def build_sec13f(uw: UWClient | None = None) -> Path:
    """The 13F Fetch: render from the stores.

    The numbers themselves are the builder's since G9 (``rcdata/build/ownership``, read through
    ``engine.load_totals``), and the names and sectors the spine's (``engine.load_sec13f_meta``), so the Fetch asks
    no provider for anything.

    One 13F job at a time (#26): a second one refuses with a ``JobMessage`` and writes nothing.
    """
    with job_lock.acquire("sec_13f", wait=0) as got:
        if not got:
            raise JobMessage(_sec13f_busy_message())
        return _build_sec13f(uw)


def _build_sec13f(uw: UWClient | None = None) -> Path:
    """The Fetch's work, once ``build_sec13f`` holds the ``"sec_13f"`` lock."""
    coverage = _13f_coverage_note()

    note = coverage
    path = _render_13f(None, note)

    if note:
        raise JobMessage(note)
    return path


def _13f_coverage_note() -> str | None:
    """One line on the CUSIPs the newest stored quarter could not name, or None; store read only.

    The builder records this per period (``sec13f_periods``: ``coverage``, the share of long-equity value it named
    a ticker, and ``unmapped_cusips``), so the board says the same thing it said when the retired derive counted
    them itself (DF89). None when the read fails: a coverage note must never fail the job.
    """
    from RevenueChaser.rcdata import read as rcread
    try:
        periods = rcread.periods_13f()
    except Exception as exc:  # noqa: BLE001 - a coverage note must never fail the job
        logger.warning("13F coverage note failed: %s", exc)
        return None
    if not periods:
        return None
    last = periods[-1]
    unmapped, coverage = last.get("unmapped_cusips"), last.get("coverage")
    if not unmapped:
        return None
    note = (f"13F {last['period']}: {unmapped:,} CUSIP(s) have no ticker, "
            f"{(1 - coverage) * 100:.1f}% of the quarter's value is not on the board."
            if coverage is not None else
            f"13F {last['period']}: {unmapped:,} CUSIP(s) have no ticker.")
    logger.warning("13F coverage: %s", note)
    return note


#: The builder datasets that still call SEC EDGAR for the 13F board (since G9 the board itself calls nothing).
SEC13F_SOURCES = ("sec/13f", "sec/13f_sets_listed")


def _sec13f_health() -> dict | None:
    """The 13F board's SEC EDGAR banner (#299): the newest builder check of each source, one count each.

    A source whose newest check ``failed`` counts as a failed call, with its date and note as the example, so a
    failed SEC fetch shows on the board until a later run of that dataset succeeds. None when the ops state
    cannot be read: a banner must never break a render.
    """
    from RevenueChaser.core.providers.result import ProviderHealth
    from RevenueChaser.rcdata import ops
    health = ProviderHealth("SEC EDGAR")
    try:
        checks = [(ds, ops.read_latest_check(ds)) for ds in SEC13F_SOURCES]
    except Exception as exc:  # noqa: BLE001 - a banner must never break a render
        logger.warning("13F builder health not read: %s", exc)
        return None
    for ds, check in checks:
        if check:
            failed = check.get("result") == "failed"
            why = f"{check.get('checked_on')}: {(check.get('note') or 'build failed')[:200]}"
            health.call(why if failed else None, endpoint=ds)
    return health.health()


def _render_13f(health: dict | None, note: str | None, capture: dict | None = None) -> Path:
    """Render the board with the best-effort UW banner (``health``) and ``note``."""
    try:
        return run_sec_13f_latest(None, notice=note, provider_health=health, capture=capture)
    except JobMessage:
        return SEC_13F_LATEST  # no totals at all: the empty board was written


def spxgamma_latest() -> dict | None:
    """The SPX board's latest pointer: the manifest of the newest day it shows (``spx_meta``)."""
    from RevenueChaser.module_spx_gamma import store as spx_store
    return spx_store.latest()


# The SPX report the last Fetch or calendar click built, so the board shows the clicked day. Kept in
# this process only: a restart, or a Refresh, puts the board back on the newest day (the latest pointer).
_SPX_VIEW: Path | None = None


def spxgamma_view_report() -> Path | None:
    """The report the board shows instead of ``latest.json``'s, or None for the newest day."""
    return _SPX_VIEW


# The builder datasets the SPX Gamma board reads (PR 3): its Fetch asks the builder for both and renders at once with
# what is stored (decision A4), never waiting on them.
SPX_BUILDER_DATASETS = ("uw/spot_expiry_strike", "market_series")
SPX_REQUESTED_BY = "spx_gamma"


def spx_builder_request() -> dict:
    """Queue one build of each dataset the board reads (``ops.enqueue_once``: one already queued or running adds
    nothing); the first step of an accepted SPX Gamma Fetch's job, so a refused Fetch queues nothing and no route
    lock is held while ``ops.sqlite`` is written. What each got goes on the board. A locked or broken ``ops.sqlite``
    is a note, never a failed Fetch (D1: the board only puts requests into the queue)."""
    from RevenueChaser.core.calendar import now_ny
    from RevenueChaser.rcdata import ops

    datasets: dict[str, str] = {}
    for name in SPX_BUILDER_DATASETS:
        try:
            rid = ops.enqueue_once(name, None, by=SPX_REQUESTED_BY)
            datasets[name] = "queued" if rid is not None else "already queued"
        except Exception as exc:  # noqa: BLE001 - the board renders what is stored either way
            logger.warning("spx gamma: builder request for %s not queued: %s", name, exc)
            datasets[name] = f"not queued ({type(exc).__name__}: {exc})"[:200]
    return {"requested_at": f"{now_ny():%Y-%m-%d %H:%M} New York", "datasets": datasets}


def run_spxgamma(uw, asof_date: str, force: bool = False) -> Path | None:
    """Run the SPX Option Position Map (Unusual Whales) for one as-of date.

    The module uses the job's own ``uw`` client, so its calls count in the job's provider health.
    A stored past day is rebuilt from disk with no network; ``force`` refetches it (#179 D5).
    It first asks the builder for the board's two datasets (PR 3, :func:`spx_builder_request`); the board says so.
    """
    global _SPX_VIEW
    from RevenueChaser.module_spx_gamma.run import run as spx_run

    out = spx_run(asof_date, uw=uw, force=force, builder_request=spx_builder_request())
    _SPX_VIEW = (out or {}).get("paths", {}).get("report_html")
    return _SPX_VIEW


def run_spxgamma_stored(uw, asof_date: str) -> Path:
    """Rebuild a stored past SPX day from disk (#179 D5): no UW client, so no auth probe either.

    Registered with ``requires_uw=False``; the route sends a date here only when
    ``serves_from_disk`` holds. ``refresh`` reads the stored day and never writes it.
    """
    global _SPX_VIEW
    from RevenueChaser.module_spx_gamma.run import refresh

    out = refresh(asof_date, builder_request=spx_builder_request())
    _SPX_VIEW = out["paths"]["report_html"]
    return _SPX_VIEW


def run_spxgamma_history(uw, start: str, end: str, max_calls: int | None = None,
                         sleep_s: float | None = None) -> dict:
    """Pull past SPX Gamma sessions in ``[start, end]`` into the raw day folders (D1, the 2-year history pull).

    Only raw days are written (``origin: history_pull``); the board, the latest pointer, the GEX record and the Brier
    record are untouched. The returned ``counts`` (without the answer shapes, a few failures) go into the run's
    ``job_runs`` row; the run's file under ``history_pull/`` has them all.
    """
    from RevenueChaser.module_spx_gamma import history_pull

    options = {k: v for k, v in (("max_calls", max_calls), ("sleep_s", sleep_s)) if v is not None}
    result = history_pull.pull_history(uw, start, end, **options)
    return {"counts": history_pull.row_counts(result["counts"])}


def run_spxgamma_cached() -> Path | None:
    """Refresh for SPX Gamma: rebuild the newest stored day from disk, zero network.

    Returns the rebuilt report, or None when no raw day is stored (a Fetch is needed first).
    """
    global _SPX_VIEW
    from RevenueChaser.module_spx_gamma.run import refresh

    out = refresh()
    _SPX_VIEW = None
    return out["paths"]["report_html"] if out else None


def _remember_quick_ticker(ticker: str, generated_at: str | None = None) -> None:
    """Cache the ticker + render date for the Financials tab in .cache/.

    State is a per-module JSON file (clearable, regenerable) — the view
    recomputes from .store on Refresh (no network) whenever the raw payload
    for the ticker is there. ``generated_at`` is the UTC stamp of the render
    that produced the current artifact and is always surfaced in the UI.
    """
    from datetime import datetime, timezone
    if generated_at is None:
        generated_at = datetime.now(timezone.utc).isoformat()
    from RevenueChaser.core.reporting_common import write_artifact
    write_artifact(QUICK_STATE, json.dumps({
        "ticker": ticker.upper(),
        "generated_at": generated_at,
    }))


def _last_quick_ticker() -> str:
    try:
        state = json.loads(QUICK_STATE.read_text(encoding="utf-8"))
        return state.get("ticker") or "AAPL"
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return "AAPL"


def _quick_state() -> dict:
    """Last rendered ticker + generated_at (UTC) — or empty dict when absent."""
    try:
        state = json.loads(QUICK_STATE.read_text(encoding="utf-8"))
        return state if isinstance(state, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _copy_quick_artifact(html: str) -> bool:
    """Copy a freshly rendered report to the stable .cache artifact."""
    import shutil
    p = Path(html)
    if not p.exists():
        return False
    QUICK_LATEST.parent.mkdir(parents=True, exist_ok=True)
    if p.resolve() != QUICK_LATEST.resolve():
        shutil.copy(p, QUICK_LATEST)
    return True


def run_quick(uw, ticker: str) -> Path:
    """Run Fin Research for one ticker — Quick Remarks (ticker_scores) + Fin Model (DCF/3-stmt/comps/credit/sensitivity).

    No provider call at all since #645 (``uw`` ignored, no key of any kind required): the statements come from the
    fundamentals serving layer, the market figures from the prices store, the peers' multiples from both, and a
    name the layer holds no annual year with revenue for gets no model. Recomputes the report into .cache.
    """
    from RevenueChaser.module_financials.run import run as fm_run

    # The dashboard keeps one report (financials_latest.html); per-ticker files are the CLI's (#173 D5).
    modules = ["dcf", "3stmt", "comps", "credit", "sensitivity"]
    res = fm_run(ticker, modules=modules, output="html", report_path=QUICK_LATEST)
    if _copy_quick_artifact(res["paths"].get("html") or ""):
        _remember_quick_ticker(ticker)
    return QUICK_LATEST


def run_quick_cached(uw=None, ticker: str | None = None) -> Path | None:
    """Store-only Financials render: the last report file, never a re-derive and never the network.

    The statements and the payload a re-derive read lived in the old store (``vendor_financials``,
    ``ticker_payload_cache``) and went with it (#860), so a Refresh serves the report the last Fetch wrote, or None
    (an empty state) when there is none or another ticker is asked for.
    """
    if ticker is not None and ticker.upper() != _last_quick_ticker():
        QUICK_LATEST.unlink(missing_ok=True)
        return None
    return QUICK_LATEST if QUICK_LATEST.exists() else None


def _ag_header_path() -> Path:
    """The last AG Fetch's header (``engine.fetch_header``), beside the page; written only by a Fetch."""
    return Path(ASYMMETRIC_GROWTH_LATEST).with_name("asymmetric_growth_fetch_header.json")


def run_asymmetric_growth(uw, refresh_universe: bool = False, no_fetch: bool = False) -> Path:
    """Run the Asymmetric Growth Hunter scan (US-listed, all caps, stored SEC EDGAR figures and prices-store bars).

    ``refresh_universe=True`` re-fetches the shared ticker universe first;
    ``no_fetch=True`` (a Refresh) renders the last Fetch's stored cards (``engine.stored_result``), no scoring.
    """
    import json
    from RevenueChaser.module_asymmetric_growth.engine import run_asymmetric_growth_hunter
    from RevenueChaser.module_asymmetric_growth.report import board_payload, render_asymmetric_growth_hunter_html
    from RevenueChaser.core import ticker_store
    from RevenueChaser.core.reporting_common import write_board

    from RevenueChaser.module_asymmetric_growth.engine import stored_result

    # One id per Fetch (jobs.py:97): its freeze.
    run = None if no_fetch else _freeze_run_id()
    # A Refresh shows the last Fetch read back from the store and never re-scores (S5, Common K4 #383 R1).
    # The Fetch's header (date, prices session, funnel) rides beside the stored rows, so a Refresh keeps it (F3).
    if no_fetch:
        try:
            header = json.loads(_ag_header_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            header = None
        result = stored_result(header)
    else:
        result = run_asymmetric_growth_hunter(uw, refresh_universe=refresh_universe, no_fetch=False, run_id=run)
    _write_output("asymmetric_growth", json.dumps(result, ensure_ascii=False, default=str), "latest", ext="json")
    # The page and its cards (S7, K10 #383 C6a): the cards go to the gzip payload file next to the page.
    write_board(ASYMMETRIC_GROWTH_LATEST, render_asymmetric_growth_hunter_html(result),
                board_payload(result), asof=_run_asof(result))
    if not no_fetch:
        # Only a Fetch rewrites the durable per-ticker table; a Refresh renders and leaves it alone (#145 D5).
        ticker_store.write_from_cards(result["cards"], result.get("asof"))
        from RevenueChaser.core.reporting_common import write_artifact
        from RevenueChaser.module_asymmetric_growth.engine import fetch_header
        write_artifact(_ag_header_path(), json.dumps(fetch_header(result), ensure_ascii=False, default=str))
        # Last step of a Fetch, after the board files are written. A Refresh (no_fetch) never freezes.
        # The outcome is a job note (core.ledger), not a JobMessage: ``run_universe_refresh`` still has
        # two boards to run. A freeze *error* propagates, so the job shows it.
        from RevenueChaser.module_asymmetric_growth import freeze as ag_freeze
        ag_freeze.freeze_result(result, run_id=run)
    return ASYMMETRIC_GROWTH_LATEST


def _end_empty_fetch(payload: dict, no_fetch: bool) -> None:
    """A Fetch that scored nothing says why (AGENTS.md §2) instead of ending "done" without a word (#145).

    Only a Fetch is a job. A Refresh is a GET with no job to carry a message; its board already shows the reason.
    The board is written before this raises, so the empty state is on disk either way.
    """
    if payload.get("no_data") and not no_fetch:
        raise JobMessage(str(payload.get("no_data_message") or "No data."))


def run_swing(uw, refresh_universe: bool = False, no_fetch: bool = False) -> Path:
    """Run the Swing Screener (broad US scan, Minervini/Weinstein/Qullamaggie).

    Reads the prices store's daily bars and the spine's names; no yfinance call at all (#645, Swing review F1), and
    ``uw`` is unused here (options flow is manual-review). Writes the
    structured JSON payload, the HTML board and its rows file (K10, #383 R3).
    ``refresh_universe=True`` re-fetches the shared ticker universe first;
    ``no_fetch=True`` (model-only) runs purely from cached per-ticker data.
    """
    from RevenueChaser.module_swing_potential.pipeline import run_scan, save_payload
    from RevenueChaser.module_swing_potential.report import render_swing_board

    payload = run_scan(uw, refresh_universe=refresh_universe, no_fetch=no_fetch)
    save_payload(payload)
    _write_board(SWING_LATEST, *render_swing_board(payload), asof=_run_asof(payload))
    if not no_fetch:                      # last step of a Fetch; a Refresh never freezes (see AG above)
        from RevenueChaser.module_swing_potential import freeze as swing_freeze
        swing_freeze.freeze_payload(payload, run_id=_freeze_run_id())
    _end_empty_fetch(payload, no_fetch)
    return SWING_LATEST


def run_fundamentals(uw, refresh_universe: bool = False, no_fetch: bool = False) -> Path:
    """Run the Fundamental Analysis scan (Rule of 40 / Quality / Momentum).

    SEC EDGAR + yfinance only (``uw`` unused; options flow is manual-review).
    Writes the JSON payload, the HTML board and its rows file (K10, #383 R3).
    ``refresh_universe=True`` re-fetches the shared ticker universe first;
    ``no_fetch=True`` (model-only) runs purely from cached per-ticker data.
    """
    from RevenueChaser.module_fundamentals.pipeline import run_scan, save_payload
    from RevenueChaser.module_fundamentals.report import render_fundamental_board

    payload = run_scan(uw, refresh_universe=refresh_universe, no_fetch=no_fetch)
    save_payload(payload)
    _write_board(FUNDAMENTALS_LATEST, *render_fundamental_board(payload), asof=_run_asof(payload))
    if not no_fetch:                      # last step of a Fetch; a Refresh never freezes (see AG above)
        from RevenueChaser.module_fundamentals import freeze as fundamentals_freeze
        fundamentals_freeze.freeze_payload(payload, run_id=_freeze_run_id())
    _end_empty_fetch(payload, no_fetch)
    return FUNDAMENTALS_LATEST


def run_comovement(uw=None, no_fetch: bool = False,
                   horizon: int | None = None,
                   benchmark: str | None = None,
                   window: int | None = None) -> Path:
    """Run the Co-movement board (return-correlation clusters).

    Fetch fills daily OHLC for the liquid universe then clusters; the
    ``no_fetch`` (model-only) path reads the cached store and re-renders with
    zero network. ``horizon`` (1/3/5/10) and ``benchmark`` (off/spy/dia/qqq)
    come from the board's Remove-market / Horizon controls and drive the
    residual clustering; ``window`` (sessions) is the board's window control,
    ``None`` meaning the Settings default. Writes the JSON payload, the
    HTML board and its K10 payload file (#584).

    After a Fetch's board is written, the popular windows
    (``config.PRECOMPUTE_WINDOWS``) are computed and stored so switching to them
    serves a stored run (#95). A precompute failure is logged; it never fails
    the Fetch or touches the board just written.

    A Fetch's runs share its ``run_id``.
    """
    from RevenueChaser.module_comovement import engine, report

    run = None if no_fetch else _freeze_run_id()       # a store-only run stores nothing, so it has no id
    payload = engine.run(no_fetch=no_fetch, horizon=horizon, benchmark=benchmark,
                         window=window, **({} if no_fetch else {"run_id": run}))
    _write_to(COMOVEMENT_JSON, json.dumps(payload, ensure_ascii=False, default=str))
    _write_board(COMOVEMENT_LATEST, *report.render_comovement_board(payload), asof=_run_asof(payload))
    if no_fetch:
        return COMOVEMENT_LATEST
    if not payload.get("clusters"):
        # #392 (3): a Fetch that clustered nothing says why instead of ending "done" without a word. The empty board
        # is already written; there is nothing to precompute.
        raise JobMessage(f"No groups: {int(payload.get('eligible') or 0)} names had enough daily prices in the "
                         f"window to cluster (3 needed). The prices build fills them after each close.")
    as_ofs: dict[int, str] = {}
    done: dict[int, str] = {}
    warnings: list[str] = []
    if payload.get("config_hash"):
        try:
            done = engine.precompute(horizon=horizon, benchmark=benchmark, run_id=run,
                                     as_ofs=as_ofs)
            logger.info("comovement precompute: %s", done)
        except Exception as exc:  # noqa: BLE001 - optional speed-up, never fatal
            logger.warning("comovement precompute failed: %s", exc, exc_info=True)
            warnings.append(f"precompute failed: {type(exc).__name__}: {exc}")
    if warnings:
        ledger.add_note(" ".join(warnings))
    return COMOVEMENT_LATEST


def run_comovement_recompute(uw=None) -> None:
    """Store-only recompute of Co-movement after a Settings save or reset (#40).

    ``requires_uw=False``, short lane, zero network: re-clusters the stored prices
    at the new effective settings (``run_comovement(no_fetch=True)``), then
    re-renders the Settings board so its card funnel follows. Always ends with a
    ``JobMessage`` so the UI reports the run.
    """
    run_comovement(None, no_fetch=True)
    try:
        payload = json.loads(COMOVEMENT_JSON.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        payload = {}
    run_settings(uw)
    st = payload.get("settings") or {}
    message = (f"Co-movement recomputed: {payload.get('eligible', 0):,} clustered, "
               f"{payload.get('window') or st.get('window')}-session window")
    if st.get("custom"):
        message += " (custom settings)"
    raise JobMessage(message)


def run_value_chain(uw=None, no_fetch: bool = False) -> Path:
    """Run the Value Chain board (supplier/customer links from each company's latest annual report).

    On the SEC layer a Fetch downloads nothing: it reads the filings the SEC service stores, rebuilds the links and
    says what it read. Off the layer it pulls the latest 10-K/20-F and slices Item 1/4. The ``no_fetch`` path
    re-renders the stored links with zero network.
    """
    from RevenueChaser.module_value_chain import engine, report

    payload = engine.run(no_fetch=no_fetch, run_id=None if no_fetch else _freeze_run_id())
    _write_to(VALUE_CHAIN_JSON, json.dumps(payload, ensure_ascii=False, default=str))
    _write_to(VALUE_CHAIN_LATEST, report.render_value_chain_dashboard(payload))
    fetch = payload.get("fetch") or {}
    if not no_fetch and fetch.get("corpus") == "layer":
        raise JobMessage(_value_chain_layer_message(payload))
    if not no_fetch and not fetch.get("fetched"):
        # A Fetch that wrote nothing says why instead of looking like a silent no-op.
        message = f"No new filings fetched ({fetch.get('cached', 0)} already cached"
        for key, label in (("kept", "kept"), ("form_40f", "40-F, read from the SEC layer only"),
                           ("no_filing", "no 10-K/20-F"), ("known_miss", "recorded misses"),
                           ("no_cik", "no CIK"), ("failed", "failed")):
            if fetch.get(key):
                message += f", {fetch[key]} {label}"
        raise JobMessage(message + ")")
    return VALUE_CHAIN_LATEST


def _value_chain_layer_message(payload: dict) -> str:
    """What a layer Fetch did, in counts (V2): it reads and rebuilds, so "no new filings fetched" was always true and
    never the news."""
    fetch = payload.get("fetch") or {}
    edges = payload.get("edges") or []
    msg = (f"Read {fetch.get('cached', 0):,} filings from the SEC layer; "
           f"{len(edges):,} supplier / customer links on the board")
    if payload.get("profile_hidden"):
        msg += f", {payload['profile_hidden']:,} profile links held back"
    if payload.get("kept"):
        msg += " (this run found none, so the stored links stay)"
    pending = payload.get("pending")
    if pending:
        msg += f"; {pending:,} companies not in the SEC layer yet"
    return msg + "."


def run_relatedness_compare(uw=None, provider: str = "", model: str = "", tickers: list | None = None) -> None:
    """The writer comparison (#370): ``tickers`` (at most 100) with one provider + model; no board table is written.
    The counts are the job's message; the scores file is under ``.cache/research/360/``."""
    from RevenueChaser.core import job_lock
    from RevenueChaser.module_relatedness import compare

    # The Relatedness Fetch's lock (PR 371 review S3): a comparison never spends beside a scheduled run.
    with job_lock.acquire("relatedness", wait=0) as got:
        if not got:
            raise JobMessage("Another Relatedness run is already in progress; the comparison did not start.")
        out = compare.run(list(tickers or []), provider=provider, model=model)
    raise JobMessage(json.dumps(out, ensure_ascii=False))


def _write_relatedness_peers(peers: dict) -> None:
    """One ``{"peers": [...]}`` file per focal ticker: the board fetches only the one it shows (a whole-board
    list inlined was 32 of the page's 35 MB). Built in a sibling folder and swapped in, so no stale ticker stays."""
    import shutil
    new, old = RELATEDNESS_PEERS_DIR.with_name("peers.new"), RELATEDNESS_PEERS_DIR.with_name("peers.old")
    shutil.rmtree(new, ignore_errors=True)
    new.mkdir(parents=True)
    for ticker, rows in peers.items():
        (new / f"{ticker}.json").write_text(
            json.dumps({"ticker": ticker, "peers": rows}, ensure_ascii=False, default=str, separators=(",", ":")),
            encoding="utf-8")
    shutil.rmtree(old, ignore_errors=True)
    if RELATEDNESS_PEERS_DIR.exists():
        RELATEDNESS_PEERS_DIR.rename(old)
    new.rename(RELATEDNESS_PEERS_DIR)
    shutil.rmtree(old, ignore_errors=True)


def run_relatedness(uw=None, no_fetch: bool = False, usd_cap: float | None = None) -> Path:
    """Run the Relatedness board (LLM business-profile similarity).

    Fetch builds profiles for the pilot universe with the board's writer (Settings, #360: EVREN by default, DeepSeek
    off-peak gated); the ``no_fetch`` (model-only) path re-renders from that writer's stored profiles with zero
    network.

    ``usd_cap`` is the run's spend ceiling in USD and counts only when that writer is DeepSeek; ``None`` leaves the
    module's own default (``module_relatedness.config.USD_CAP``). The weekly task passes it, because its cap is
    avo's 10 USD (2 Nov 2026) and not that default: since #1255 the task runs here rather than in a second writer
    process of its own.
    """
    from RevenueChaser.module_relatedness import engine, report
    from RevenueChaser.module_relatedness import settings as rel_settings

    # The model is a parameter (PR 362 review S1): a Refresh and a Save beside a Fetch never change a module default.
    provider, model = rel_settings.writer()[0], rel_settings.chosen_model()
    try:
        # One id per Fetch (jobs.py:97): its result history header (#388). A Refresh records nothing.
        payload = engine.run(no_fetch=no_fetch, run_id=None if no_fetch else _freeze_run_id(),
                             provider=provider, model=model, usd_cap=usd_cap)
    except engine.AlreadyRunning as exc:
        raise JobMessage(str(exc)) from exc
    _write_to(RELATEDNESS_JSON, json.dumps(payload, ensure_ascii=False, default=str))
    # Peers first, so a page loaded from the new HTML never asks for a list that is not written yet.
    _write_relatedness_peers(payload.get("peers") or {})
    _write_board(RELATEDNESS_LATEST, *report.render_relatedness_board(payload), asof=_run_asof(payload))
    # A Fetch that stopped early (peak, missing key, auth, the worker-pool stop)
    # or left work pending is not a silent success: say what is done and what waits.
    # A Refresh is a GET that writes nothing and must never raise (C-F6), so the
    # job message is Fetch-only.
    pending = payload.get("pending") or 0
    if not no_fetch and (payload.get("stopped_reason") or pending > 0):
        parts = [f"{payload.get('n') or 0} profiled, {pending} pending"]
        if payload.get("stopped_reason"):
            parts.append(f"stopped: {payload['stopped_reason']}")
        if payload.get("stopped_reason") in ("spine", "forms") and payload.get("error"):
            parts.append(str(payload["error"]))        # a stop no later run fixes by itself: say why (#841)
        if payload.get("next_off_peak"):
            parts.append(f"next off-peak {payload['next_off_peak']} UTC")
        raise JobMessage("; ".join(parts))
    return RELATEDNESS_LATEST


def run_oipd(uw=None, ticker: str | None = None, no_fetch: bool = False) -> Path:
    """Render the Implied Probability (OIPD) board for one ticker from the nightly options build.

    Store-only (decision B, avo 10 Nov 2026): ``engine.build`` reads the stored chain and fits it; no provider call,
    no write but the payload and the board. A Fetch and a Refresh do the same thing. A run that fits no expiry still
    writes the board (with its error state) and raises ``JobMessage`` so the UI explains itself.
    """
    from RevenueChaser.module_oipd import engine

    payload = engine.build(ticker=ticker)
    path = _render_oipd(payload)
    if not payload.get("expiries"):
        msg = payload.get("error")
        if not msg:
            warns = [w for w in (payload.get("warnings") or []) if w]
            msg = (" ".join(warns) if warns else
                   f"No expiry could be fitted for {payload.get('ticker')}.")
        raise JobMessage(msg)
    return path


def run_news(uw=None) -> Path:
    """The News board's Fetch: the incremental calendar build into ``boards/news.duckdb``, the Dow Jones headlines from
    the IBKR Gateway (every name of avo's own, the stock and the News watch lists), then the page.

    The calendar reads ``market.economic_event`` and ``market.fda_event`` (the builder's hourly
    ``uw/economic_calendar`` and ``uw/fda_calendar``, #807). The headlines are two gateway
    requests a name and no UW call; a gateway that is down is a job note, never a failed Fetch.
    """
    from RevenueChaser.module_news import calendar, earnings, report
    rid = run_id()
    out = calendar.build(run_id=rid)
    weeks = earnings.build(run_id=rid)       # next week's watch-list earnings too, so a Fetch is never a week late
    ledger.add_note(f"News earnings: {weeks['names']} watch-list names report in the week of {weeks['week_start']}")
    ledger.add_note(f"News calendar: {out['read']} raw rows read, {out['upserted']} events upserted, "
                    f"{out['retired']} retired, {out['highlights']} day highlights")
    if out.get("fda_read"):
        ledger.add_note(f"News FDA calendar: {out['fda_read']} raw rows read, {out['fda_upserted']} catalysts "
                        f"upserted, {out['fda_retired']} retired")
    health = _news_headlines_pass(rid)
    path = report.render(provider_health=health)
    if health:
        # The job too, so the Welcome freshness card does not show a ✓ for a Fetch that got no headlines.
        raise JobMessage(health["message"])
    return path


def _news_headlines_pass(rid: str) -> dict | None:
    """The tape lines the listener appended (#673), the Grok X mails the fetcher saved, then the per-ticker Dow Jones
    headlines. ``None``, or the provider health of a gateway that did not answer (with the job message in
    ``message``)."""
    from RevenueChaser.module_news import headlines
    tape = headlines.load_tape(run_id=rid)
    if tape["read"]:
        ledger.add_note(f"News tape: {tape['stored']} market headlines from {tape['read']} new lines")
    x = headlines.load_x(run_id=rid)
    if x["mails"]:
        ledger.add_note(f"News X: {x['stored']} posts from {x['mails']} Grok mails ({x['known']} already stored, "
                        f"{x['refused']} rows refused, {x['cut']} mails cut short)")
    from RevenueChaser.module_news import x_check
    checked = x_check.run(UWClient)
    if checked["calls"]:
        ledger.add_note(f"News X: {checked['checked']} option posts checked against UW ({checked['calls']} calls)")
    from RevenueChaser.rcdata import read
    lists, unread = [], []
    for kind in headlines.LISTS:                      # strict: an unreadable list is not an empty one (F6)
        try:
            lists.append(read.job_list(kind))
        except read.JobListUnreadable as e:
            unread.append(f"{kind or 'own'} watch lists ({e})")
            ledger.add_note(f"News headlines: the {kind or 'own'} watch lists could not be read ({e})")
    names = headlines.tickers(*lists)
    got = headlines.fetch(names, run_id=rid)
    health = None
    if got["error"]:
        ledger.add_note(f"News headlines not fetched: {got['error']}")
        # The board says so too, or a down gateway would pass for a quiet news day. A name IBKR does not know is
        # only a note: it is the same names every run, and a banner on every Fetch would be noise.
        asked = max(1, got["tickers"])
        health = {"provider": "ibkr", "calls": asked, "failed": asked,
                  "auth_error": None,
                  "failures": [{"endpoint": "headlines", "error": got["error"]}],
                  "message": f"{GAPS}: {asked} of {asked} Interactive Brokers calls failed "
                             f"(headlines: {got['error']}). The board may be incomplete — run Fetch again later."}
    else:
        skipped = f"; not known to IBKR: {', '.join(got['skipped'])}" if got["skipped"] else ""
        of = got.get("of", got["tickers"])
        ledger.add_note(f"News headlines: {got['stored']} new from {got['tickers']} of {of} names "
                        f"(IBKR, Dow Jones; the rest in later passes){skipped}")
        failed = got.get("failed", [])
        problems = failed + unread
        if not problems:
            # A clean pass, with or without a new headline: the mark Grafana alerts on (review F2, plan step 6).
            headlines.mark_lane_ok("stocks")
        if problems:
            # A refused request other than "unknown name" (a lapsed feed, pacing) or an unread list: the board shows
            # it, or the lane would only look quieter (review F1/F6, avo's D5 18 Nov 2026: "Panoda bant").
            # An unread list counts as one failed read, so the banner shows even when every name answered.
            health = {"provider": "ibkr", "calls": got["tickers"] + len(unread), "failed": len(problems),
                      "auth_error": None,
                      "failures": [{"endpoint": "headlines", "error": p} for p in problems],
                      "message": f"{GAPS}: {len(problems)} of {got['tickers'] + len(unread)} Interactive Brokers reads "
                                 f"failed ({'; '.join(problems[:3])}). The board may be incomplete."}
    return health


def run_news_headlines(uw=None) -> Path:
    """The live listener's 5-minute job (#673): new tape lines and the per-ticker headlines into
    ``boards/news.duckdb``, then the page. No calendar build, no UW call. A down gateway is the page's banner and a job
    note, not a job message: the shell alerts every message, and this job runs 288 times a day."""
    from RevenueChaser.module_news import report
    return report.render(provider_health=_news_headlines_pass(run_id()))


def run_news_ticker(uw=None, ticker: str = "") -> None:
    """One name's headlines on demand (the News page's ticker box): one IBKR request, stored like a pass. The answer,
    an error included, is kept for the page (``headlines.ticker_rows``); a job message would alert the shell."""
    from RevenueChaser.module_news import headlines
    ask = headlines.fetch_ticker(ticker)
    ledger.add_note(f"News {ticker}: {ask['found']} headlines from IBKR, {ask['stored']} new"
                    + (f" ({ask['error']})" if ask["error"] else ""))
    return None


def run_news_x_follow(uw=None) -> Path | None:
    """The X lane's own reader (plan step 5): the Following timeline of RC's X account into ``boards/news.duckdb``,
    then the page. The timer queues it every 30 minutes; ``x_reader.due`` thins that to every 4 hours outside the US
    session. A refused read is a job note and the page's banner, not a job message (the shell alerts every message)."""
    from RevenueChaser.module_news import headlines, report, x_reader
    try:
        got = x_reader.run(run_id=run_id())
    except x_reader.ReadFailed as e:
        ledger.add_note(f"News X reader: nothing read ({e})")
        return report.render(provider_health={
            "provider": "X", "calls": 1, "failed": 1, "auth_error": None,
            "failures": [{"endpoint": "following", "error": str(e)}],
            "message": f"{GAPS}: RC's X reader could not read the Following timeline ({e})."})
    if got["skipped"]:
        return None
    ledger.add_note(f"News X reader: {got['stored']} new posts stored of {got['read']} read")
    headlines.mark_lane_ok("x")
    return report.render()


def run_news_earnings(uw=None) -> Path:
    """The News board's weekly earnings pass (#886): next week's report day of every watch-list name, from the
    stored Alpha Vantage calendar (``fundamentals.earnings_event``), into ``boards/news.duckdb``, then the page.

    Store-only, no provider call. Queued by ``RC-News-Earnings-Weekly`` every Sunday 09:00 Amsterdam, and by the
    board's own Fetch, so a Fetch never shows last week's days.
    """
    from RevenueChaser.module_news import earnings, report
    out = earnings.build(run_id=run_id())
    ledger.add_note(f"News earnings: {out['names']} watch-list names report in the week of {out['week_start']}")
    return report.render()


def run_news_cached(uw=None) -> Path:
    """Store-only News render (Refresh, first load): reads ``boards/news.duckdb``, writes nothing to the store."""
    from RevenueChaser.module_news import report
    return report.render()


# ``welcome_job_labels`` went with #643 PR 6: the freshness card is one row per **builder file** now (avo's D2 of
# 10 Nov 2026), named by ``module_welcome.build.FILE_LABELS``, so the page needs no map of dashboard job labels.


def run_welcome(uw=None) -> Path:
    """The Welcome board's Fetch: the incremental build into ``boards/welcome.duckdb``, then the page. No network."""
    from RevenueChaser.module_welcome import build
    out = build.build(run_id=run_id())
    ledger.add_note(f"Welcome: {out['snapshot']} closes, {out['earnings']} earnings rows, "
                    f"{out['freshness']} builder files")
    return run_welcome_cached()


def run_welcome_cached(uw=None) -> Path:
    """Store-only Welcome render (Refresh, first load): reads the board files, writes nothing to the store."""
    from RevenueChaser.module_welcome import report
    return report.render(watchlist=_load_watchlist())


def run_oipd_cached(uw=None, ticker: str | None = None) -> Path:
    """Store-only Implied Probability render — no network, no credentials.

    Runs in the ``/view`` path, not the job queue, so it never raises: an empty
    store still writes an error board and returns it.
    """
    from RevenueChaser.module_oipd import engine
    return _render_oipd(engine.build(ticker=ticker))


def _render_oipd(payload: dict) -> Path:
    from RevenueChaser.module_oipd import report

    _write_to(OIPD_JSON, json.dumps(payload, ensure_ascii=False, default=str))
    _write_to(OIPD_LATEST, report.render_oipd_dashboard(payload))
    return OIPD_LATEST


def run_settings(uw=None) -> Path:
    """Render the Settings / Data health board from the store — no network.

    Store-only (``requires_uw=False``): the inventory reads ``raw.duckdb`` /
    ``edgar.duckdb`` and needs no credentials. An empty store still writes the
    artifact with its explicit empty state.

    It runs in the ``/view`` path (Refresh or first load), as the
    ``settings_refresh`` job, and from the runners that re-render the board
    after their own work (``run_comovement_recompute``,
    ``run_universe_caps_backfill``, ``run_storage_picture``). ``collect`` and
    the control view carry their own errors, but the render itself does not, so
    a caller that must not lose its own work does it before calling this.
    """
    from RevenueChaser.module_settings import inventory, report

    payload = inventory.collect()
    return _write_output(
        "settings", report.render_settings_dashboard(payload), "latest")


def run_storage_picture(uw=None) -> Path:
    """Walk the HDD raw and Parquet trees and store what is there, for the Settings board's journey table.

    Store-only and disk-only (``requires_uw=False``): no network, no store write, nothing but ``readdir`` and
    ``stat`` over regenerable trees. It runs on the long-jobs worker because that is off the request thread: the
    walk was in the page render until #434, where the first ``readdir`` of the folders that exist measured 26 s on
    the HDD and the whole walk ran past rc-warmup's 600 s ceiling, holding the single-threaded dashboard for all
    of it. The board reads the file this writes and shows when it was walked.
    """
    from RevenueChaser.module_settings import newdata

    picture = newdata.walk_storage()
    _write_to(newdata.STORAGE_PICTURE, json.dumps(picture, indent=1, sort_keys=True))
    # Re-render the board, or the new picture would wait for the next Refresh: the shell reloads this job's
    # ``produces`` tab with a cache-buster, which serves the stored artifact rather than recomputing it. Written
    # first, so a render that fails still leaves the picture on disk.
    run_settings()
    folders = [side for roots in picture["datasets"].values() for side in roots.values()]
    walked = [f for f in folders if f.get("files") is not None]
    capped = [f for f in walked if f.get("capped")]
    # A run that finds nothing, or finds it only in part, says so (AGENTS.md): a capped folder's count is a floor,
    # and that is the one failure that quietly falsifies the journey table.
    raise JobMessage(
        f"{len(walked)} folders walked, {sum(f['files'] for f in walked):,} files"
        + (f" \u2014 {len(capped)} folders ran out of time, so their counts are a floor" if capped else ""))


def run_uw_interaction(uw: UWClient, **params) -> Path:
    """Run one UW Interaction (lab) tool and persist its payload under .cache/.

    ``params`` carries the catalog tool key plus its validated query params.
    The board (``/view/module_uw_interaction``) is rendered from the stored
    payload, so this runner only writes the regenerable JSON — never ``.store``.

    A tool that yields nothing must say so: the payload is still written with an
    explicit empty/error state and a ``JobMessage`` explains the run so the UI
    does not look like a silent success.
    """
    from RevenueChaser.module_uw_interaction import engine as uw_engine
    from RevenueChaser.module_uw_interaction.config import save_state, utc_now

    tool = str(params.get("tool") or "").strip()
    try:
        result = uw_engine.run_tool(uw, tool, {k: v for k, v in params.items() if k != "tool"})
    except uw_engine.ToolError as exc:
        raise JobMessage(str(exc))

    payload = {
        "tool_key": result.tool_key,
        "label": result.label,
        "family": result.family,
        "path": result.path,
        "help": result.help,
        "params_used": result.params_used,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "error": result.error,
        "http_status": result.http_status,
        "generated_at": utc_now(),
        "provider_health": _uw_health(uw),
    }
    save_state(payload)

    if result.http_status in (401, 403):
        raise JobMessage(
            f"UW rejected the credentials for '{result.label}' (HTTP {result.http_status}). "
            "Check the Unusual Whales key in .env."
        )
    if result.error:
        raise JobMessage(f"'{result.label}' returned nothing to show: {result.error}")
    if not result.rows and _provider_gap_text(uw):
        # UW-1: a timeout or 5xx is not "no rows for those parameters".
        raise JobMessage(f"'{result.label}' request failed: {_provider_gap_text(uw)}")
    if not result.rows:
        raise JobMessage(f"'{result.label}' returned no rows for those parameters.")
    from RevenueChaser.module_uw_interaction.config import UW_STATE_JSON as _st
    return _st

