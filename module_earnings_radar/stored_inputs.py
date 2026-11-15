"""The Earnings board's stored reads that are not in ``store_reads``: the rate events and the reaction bars.

``rate_events`` reads ``market.economic_event`` (R6) and ``ohlc_bars`` the prices store's daily bars. The stored
earnings calendar (D26) this module also read lived in the old raw.duckdb and went with it (#860): the Fetch asks
UW for every calendar day now.

A missing file or a read error is "nothing stored": the caller falls back to the live provider, and the error is
logged once per table. Read only.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from RevenueChaser.core import calendar
from RevenueChaser.rcdata import read as market_read

logger = logging.getLogger(__name__)

NY = ZoneInfo("America/New_York")


_OHLC_MAX_BARS = 270              # ``pipeline.REACTION_OHLC_SESSIONS``
_OHLC_LOOKBACK_DAYS = 400         # calendar days back from the latest complete session

_LOGGED: set[str] = set()         # one note per table per process


def _note_once(table: str, exc: BaseException | None = None) -> None:
    if table in _LOGGED:
        return
    _LOGGED.add(table)
    logger.info("stored inputs: %s is not read (%s); the run asks the provider",
                table, f"{type(exc).__name__}: {exc}" if exc is not None else "no table")


def _as_date(value) -> date | None:
    """A stored DATE cell as a ``date`` (DuckDB serves ``date``, a legacy cell may be ISO text)."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and len(value) >= 10:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return None
    return None


def _num(value) -> float | None:
    """A stored ``DOUBLE`` cell as a float (None for a NULL or an unreadable cell)."""
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


# ── D26: the earnings calendar ───────────────────────────────────────────────────────────────────────────────────


# ── D37: the economic calendar (rate events) ─────────────────────────────────────────────────────────────────────

def _event_day(ts) -> date | None:
    """The New York date of a UW economic event (``event_ts`` is UTC epoch seconds)."""
    try:
        return datetime.fromtimestamp(float(ts), NY).date()
    except (TypeError, ValueError, OSError, OverflowError):
        return None


def _is_rate_event(row: dict) -> bool:
    """FOMC, or a report whose text names CPI — the two releases that move the whole yield curve.

    Payrolls, GDP and the fed-speaker slots are not rate events (a bad print there is a growth story). The match is
    on the served text, so 'CPI', 'CPI, Y/Y%' and 'Core CPI, M/M%' all count while 'PPI' and
    'Ex-Food & Energy PPI' do not.
    """
    kind = str(row.get("type") or "").strip().lower()
    if kind == "fomc":
        return True
    if kind != "report":
        return False
    text = str(row.get("event") or "").lower()
    return "cpi" in text or "consumer price" in text


def rate_events() -> list[dict]:
    """Every served ``market.economic_event`` row (``session_date``, ``event_ts``, ``event``, ``type``): one read per
    run, handed to :func:`rate_event_overlap` for each card. ``session_date`` is the row's snapshot day, the sweep a
    row came from. A missing file or a read error is an empty list."""
    try:
        rows = market_read.economic_events()
    except Exception as exc:  # noqa: BLE001 - a Fetch must never fail on the store
        _note_once("economic_event", exc)
        return []
    return [{"session_date": r["snapshot_date"], "event_ts": r["event_ts"], "event": r["event"], "type": r["type"]}
            for r in rows]


def rate_event_window(report_date) -> tuple[date, date] | None:
    """``(start, end)``: the trading day before ``report_date`` and the trading day after it (±1 trading day).

    ``next_trading_day(d)`` is already the first trading day after ``d``, so a Monday report ends on Tuesday and a
    Friday one on Monday. None for a date outside the holiday table.
    """
    d = _as_date(report_date)
    if d is None:
        return None
    try:
        return calendar.previous_trading_day(d - timedelta(days=1)), calendar.next_trading_day(d)
    except ValueError:
        return None


def rate_event_overlap(report_date, events: list[dict] | None = None) -> bool | None:
    """Is an FOMC/CPI event inside ``report_date`` ± 1 trading day (:func:`rate_event_window`)?

    ``True``/``False`` when the stored ``economic_calendar`` spans the window, ``None`` when it does not — the
    store holds the current and next week, so a report three months out has no answer and R6 must not turn a
    missing calendar into a veto. The event's day is its New York date, never its UTC one (a 23:30 ET release is
    the same session in New York, the next day in UTC).

    The writer keeps every session's sweep, so a release that was moved keeps its old date in the older sweeps
    (review D-1). The answer comes from one sweep only: the newest ``session_date`` whose own rows span the window.

    ``events`` is the run's one :func:`rate_events` read; without it the table is read here.
    """
    window = rate_event_window(report_date)
    if window is None:
        return None
    start, end = window
    rows = rate_events() if events is None else events
    sweeps: dict[date | None, list[tuple[date, dict]]] = {}
    for r in rows:
        day = _event_day(r.get("event_ts"))
        if day is not None:
            sweeps.setdefault(_as_date(r.get("session_date")), []).append((day, r))
    for session in sorted(sweeps, key=lambda s: s or date.min, reverse=True):
        dated = sweeps[session]
        if min(d for d, _ in dated) > start or max(d for d, _ in dated) < end:
            continue
        return any(start <= d <= end and _is_rate_event(r) for d, r in dated)
    return None


# ── D01: the daily price bars (the reaction window) ──────────────────────────────────────────────────────────────

# The keys the pipeline and ``history.packet_ohlc`` read from an ``ohlc_year`` bar — nothing else is mapped.
_OHLC_KEYS = ("open", "high", "low", "close", "volume")


def _bar(values: dict) -> dict:
    """One stored bar in the shape the provider serves (``date`` first, then the five numbers)."""
    out = {"date": values["date"]}
    for k in _OHLC_KEYS:
        v = values.get(k)
        try:
            out[k] = None if v is None else float(v)
        except (TypeError, ValueError):
            out[k] = None
    return out


def ohlc_bars(tickers) -> dict[str, list[dict]]:
    """``{ticker: live-shaped bars}`` from the stored D01 daily bars, oldest first, the last 270 per ticker.

    One ``prices.daily_bars`` read for the lot (K8a window: from ``latest_complete_session() - 400d`` on), nominal
    basis — the bars as served, with the splits and dividends in ``price_actions`` applied on read. A ticker with no
    bar is absent from the map: the caller must ask UW for it (and the pipeline only uses a series whose last bar is
    the latest complete session, which is what the reaction columns anchor on).
    """
    names = sorted({str(t).upper() for t in (tickers or []) if t})
    if not names:
        return {}
    from RevenueChaser.core import prices
    start = calendar.latest_complete_session() - timedelta(days=_OHLC_LOOKBACK_DAYS)
    try:
        frame = prices.daily_bars(names, basis="nominal", start=start)
    except Exception as exc:  # noqa: BLE001 - a Fetch must never fail on the store
        _note_once("price_bars_daily", exc)
        return {}
    out: dict[str, list[dict]] = {}
    for rec in frame.to_dict("records"):
        ticker = str(rec.get("ticker") or "").upper()
        d = _as_date(rec.get("session_date"))
        if not ticker or d is None:
            continue
        out.setdefault(ticker, []).append(_bar({**rec, "date": d.isoformat()}))
    for ticker, bars in out.items():
        bars.sort(key=lambda b: b["date"])
        out[ticker] = bars[-_OHLC_MAX_BARS:]
    return out
