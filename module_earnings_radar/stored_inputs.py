"""The Earnings board's stored reads that are not in ``store_reads``: the calendar, the rate events and the bars.

``calendar_items`` reads the served UW earnings calendar (``option_screener_daily``, the options builder's G8 read),
``screener_rows`` the same table's screener fields for the watchlist augmentation (#1138), ``earnings_tape`` the
``/earnings/{ticker}`` tape the earnings set's evening fetch stores (#644), ``rate_events`` reads
``market.economic_event`` (R6) and ``ohlc_bars`` the prices store's daily bars. The old D26
calendar sweep lived in raw.duckdb and went with it (#860), so every calendar day was asked of UW live again until
``option_screener_daily`` began carrying the calendar's own expected move (#273's data half, 18 Nov 2026).

A missing file or a read error is "nothing stored": the caller falls back to the live provider, and the error is
logged once per table. Read only.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from revenuechaser.core import calendar
from revenuechaser.rcdata import read as market_read

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

CALENDAR_SOURCE = "rcdata:option_screener_daily"
# The need the freshness comes from: ``options.screener``, one session (``rcdata/needs/catalog.py``). avo, 29 Oct
# 2026: a calendar older than the last session is not read at all.
_CALENDAR_NEED = "options.screener"


def calendar_max_lag() -> int:
    """Sessions the served calendar may lag the board's day by, read from the need catalog on every call."""
    from revenuechaser.rcdata import needs
    need = needs.catalog.NEEDS[_CALENDAR_NEED]
    if need.max_lag_unit != "sessions":
        raise ValueError(f"{_CALENDAR_NEED}: this reader counts sessions, the catalog says {need.max_lag_unit}")
    return need.max_lag


def calendar_days_ahead() -> int:
    """The report days a built session covers — the builder's own window, never a second copy of 28."""
    from revenuechaser.rcdata.build.options.uw_screener import DAYS_AHEAD
    return int(DAYS_AHEAD)


def _calendar_session(value) -> str | None:
    """A stored ``report_session`` as the session name the Fetch asks UW for."""
    v = str(value or "").strip().lower().replace("-", "")
    if v in ("premarket", "bmo", "before"):
        return "premarket"
    if v in ("afterhours", "postmarket", "amc", "after"):
        return "afterhours"
    return None


def _calendar_item(row: dict) -> dict:
    """One served row as the UW calendar item ``app/runners._calendar_event`` reads.

    The field names are UW's, not the table's, so the event is built by the one function either way and a stored
    pair and a live pair cannot drift apart.
    """
    return {
        "symbol": row.get("ticker"),
        "sector": row.get("sector") or "",
        "full_name": row.get("full_name") or "",
        "marketcap": row.get("marketcap"),
        "expected_move_perc": _num(row.get("expected_move_perc")),
        "street_mean_est": _num(row.get("street_mean_est")),
        "pre_earnings_close": _num(row.get("pre_earnings_close")),
        "post_earnings_close": _num(row.get("post_earnings_close")),
        "report_time": row.get("report_time") or "",
    }


def calendar_items(days, today=None) -> tuple[dict, date | None]:
    """``({(report day, report session): [calendar item, ...]}, built session)`` from the served calendar.

    One entry per **pair** the newest built session covers, empty list included: a covered day with no report is
    answered, not asked of UW. A pair that is absent is the Fetch's to read live. Nothing is served when

    * the table is empty or unreadable;
    * the newest session lags ``calendar_max_lag()`` sessions behind ``today`` (default New York's today);
    * the day falls outside the session's window (``session < day <= session + calendar_days_ahead()``);
    * the day is today or the next trading day — UW moves the expected move, the estimate and the report time
      during the day for the names about to report, so those pairs are always live (the rule the old D26 reader
      had, kept).

    Read only: never a provider call, and a store error is "nothing stored".
    """
    wanted = [d for d in days or () if isinstance(d, date) and d.weekday() < 5]
    if not wanted:
        return {}, None
    try:
        today = _as_date(today) or calendar.today_ny()
    except ValueError:
        today = calendar.today_ny()
    live_always = {today}
    try:
        live_always.add(calendar.next_trading_day(today))
    except ValueError:
        pass
    wanted = [d for d in wanted if d not in live_always]
    if not wanted:
        return {}, None
    try:
        rows = market_read.option_screener()
    except Exception as exc:  # noqa: BLE001 - a Fetch must never fail on the store
        _note_once("option_screener_daily", exc)
        return {}, None
    sessions = [s for s in (_as_date(r.get("session_date")) for r in rows or ()) if s is not None]
    if not sessions:
        _note_once("option_screener_daily")
        return {}, None
    session = max(sessions)
    lag = _sessions_after(session, today)
    if lag is None or lag > calendar_max_lag():
        _note_once("option_screener_daily")
        return {}, None
    window_end = session + timedelta(days=calendar_days_ahead())
    covered = [d for d in wanted if session < d <= window_end]
    if not covered:
        return {}, None
    out = {(d, rs): [] for d in covered for rs in ("premarket", "afterhours")}
    for row in rows:
        # ``option_screener`` serves the newest session on its own; the check keeps an older row out should a
        # caller ever hand this reader more than one session.
        if _as_date(row.get("session_date")) != session:
            continue
        day, rs = _as_date(row.get("report_date")), _calendar_session(row.get("report_session"))
        if day is None or rs is None or (day, rs) not in out:
            continue
        out[(day, rs)].append(_calendar_item(row))
    return out, session


# ── #1138: the screener rows behind the watchlist augmentation ───────────────────────────────────────────────────

# The fields ``watchlist_augment._augment_watchlist`` reads off a screener row, under UW's own names, so a stored row
# and a live one cannot drift apart (the same discipline as ``_calendar_item``).
_SCREENER_TEXTS = ("er_time", "sector", "full_name")
_SCREENER_NUMS = ("marketcap", "implied_move_perc")


def _screener_item(row: dict) -> dict:
    """One served ``option_screener_daily`` row as the screener answer ``uw.screener_batch`` gives per ticker."""
    out = {"next_earnings_date": None}
    day = _as_date(row.get("next_earnings_date"))
    if day is not None:
        out["next_earnings_date"] = day.isoformat()
    for name in _SCREENER_TEXTS:
        out[name] = row.get(name) or ""
    for name in _SCREENER_NUMS:
        out[name] = _num(row.get(name))
    return out


def screener_rows(tickers, today=None) -> dict[str, dict]:
    """``{ticker: screener answer}`` from the served screener set, for the names the store covers (#1138).

    The set is ``uw/option_screener``: one row per name reporting in the 28 days after the built session, carrying its
    ``next_earnings_date``, ``er_time``, ``implied_move_perc``, sector, name and market cap — every field the watchlist
    augmentation reads. A name that is absent here is the caller's to ask UW for.

    A name is **not** covered when

    * the table is empty or unreadable, or its newest session lags ``calendar_max_lag()`` sessions behind ``today``
      (the same freshness gate :func:`calendar_items` applies);
    * its row carries no ``next_earnings_date`` — then the store cannot say when it reports;
    * that date is today or the next trading day — UW still moves the report time and the implied move of a name
      about to report, so those names stay live, exactly as the calendar pairs do.

    Read only: never a provider call, and a store error is "nothing stored".
    """
    wanted = {str(t).strip().upper() for t in (tickers or ()) if str(t or "").strip()}
    if not wanted:
        return {}
    try:
        today = _as_date(today) or calendar.today_ny()
    except ValueError:
        today = calendar.today_ny()
    live_always = {today}
    try:
        live_always.add(calendar.next_trading_day(today))
    except ValueError:
        pass
    try:
        rows = market_read.option_screener()
    except Exception as exc:  # noqa: BLE001 - a Fetch must never fail on the store
        _note_once("option_screener_daily", exc)
        return {}
    sessions = [s for s in (_as_date(r.get("session_date")) for r in rows or ()) if s is not None]
    if not sessions:
        _note_once("option_screener_daily")
        return {}
    session = max(sessions)
    lag = _sessions_after(session, today)
    if lag is None or lag > calendar_max_lag():
        _note_once("option_screener_daily")
        return {}
    out: dict[str, dict] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        if ticker not in wanted or _as_date(row.get("session_date")) != session:
            continue
        day = _as_date(row.get("next_earnings_date"))
        if day is None or day in live_always:
            continue
        out[ticker] = _screener_item(row)
    return out


def _sessions_after(obs: date, day: date) -> int | None:
    """NYSE sessions after ``obs`` up to and including ``day`` (0 when ``obs >= day``); None past the calendar.

    The same count ``store_reads._sessions_after`` makes, so the board measures one kind of lag.
    """
    n, d = 0, obs
    while n <= 40:
        try:
            d = calendar.next_trading_day(d)
        except ValueError:
            return None
        if d > day:
            return n
        n += 1
    return None



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
    return "cpi" in text or "consumer price" in text or "inflation rate" in text   # TradingView: "Inflation Rate YoY"


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
    from revenuechaser.core import prices
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


# ── #644: the /earnings/{ticker} tape the earnings set stores ────────────────────────────────────────────────────

#: The tape columns the scoring reads, under UW's own names (the build stores them under the same names, so a
#: stored row and a live one cannot drift apart — the discipline ``_calendar_item`` and ``_screener_item`` keep).
#: ``report_source`` is the build's name for UW's ``source``; the scoring does not read it.
_TAPE_DOUBLES = ("actual_eps", "street_mean_est", "price", "expected_move", "expected_move_perc",
                 "pre_earnings_move_1d", "pre_earnings_move_3d", "pre_earnings_move_1w", "pre_earnings_move_2w",
                 "post_earnings_move_1d", "post_earnings_move_3d", "post_earnings_move_1w", "post_earnings_move_2w",
                 "long_straddle_1d", "long_straddle_1w", "short_straddle_1d", "short_straddle_1w")


def _tape_item(row: dict) -> dict:
    """One served ``earnings_tape`` row as a row of UW's ``/earnings/{ticker}`` answer.

    The dates come back as ISO text, the shape the scoring reads (``str(h["report_date"])[:10]`` on a live row);
    a NULL double stays None, which every rule treats as "no signal", never as a zero.
    """
    out: dict = {"ticker": str(row.get("ticker") or "").strip().upper(),
                 "report_time": row.get("report_time") or None,
                 "source": row.get("report_source") or None}
    for name in ("report_date", "ending_fiscal_quarter"):
        day = _as_date(row.get(name))
        out[name] = day.isoformat() if day is not None else None
    for name in _TAPE_DOUBLES:
        out[name] = _num(row.get(name))
    return out


def earnings_tape(tickers, today=None) -> dict[str, list[dict]]:
    """``{ticker: tape rows, newest report first}`` from the stored earnings set's tape (#644).

    One row per report of the ``/earnings/{ticker}`` answer: the completed prints the reaction columns, the edge
    median and the straddle median read, and the upcoming event (``rows[0]``) the card's report time, expected
    move and estimate come from. The board made one request per scored name for this.

    A name's rows are the **newest session the tape holds for that name**, because a name is only in the earnings
    set on the two evenings before its report: one ``max(session_date)`` over the table would serve the names that
    report next and drop every other. A name is **not** covered when

    * the table is empty or unreadable;
    * its newest session lags ``calendar_max_lag()`` sessions behind ``today`` (default New York's today) — the
      same freshness gate :func:`calendar_items` and :func:`screener_rows` apply;
    * its upcoming event is today or the next trading day — UW moves the expected move, the estimate and the
      report time during the day for a name about to report, so those names stay live, exactly as the calendar
      pairs and the screener rows do.

    A name that is absent is the Fetch's to read live. Read only: never a provider call, and a store error is
    "nothing stored".
    """
    wanted = {str(t).strip().upper() for t in (tickers or ()) if str(t or "").strip()}
    if not wanted:
        return {}
    try:
        today = _as_date(today) or calendar.today_ny()
    except ValueError:
        today = calendar.today_ny()
    live_always = {today.isoformat()}
    try:
        live_always.add(calendar.next_trading_day(today).isoformat())
    except ValueError:
        pass
    try:
        rows = market_read.earnings_tape(sorted(wanted))
    except Exception as exc:  # noqa: BLE001 - a Fetch must never fail on the store
        _note_once("earnings_tape", exc)
        return {}
    if not rows:
        _note_once("earnings_tape")
        return {}
    newest: dict[str, date] = {}
    for row in rows:
        ticker = str(row.get("ticker") or "").strip().upper()
        session = _as_date(row.get("session_date"))
        if ticker in wanted and session is not None and session > newest.get(ticker, date.min):
            newest[ticker] = session
    out: dict[str, list[dict]] = {}
    for ticker, session in newest.items():
        lag = _sessions_after(session, today)
        if lag is None or lag > calendar_max_lag():
            continue
        tape = [_tape_item(r) for r in rows
                if str(r.get("ticker") or "").strip().upper() == ticker
                and _as_date(r.get("session_date")) == session]
        # ``read.earnings_tape`` orders by report date descending, the order UW's own answer has.
        if any(r["report_date"] in live_always for r in tape):
            continue
        if tape:
            out[ticker] = tape
    if not out:
        _note_once("earnings_tape")
    return out
