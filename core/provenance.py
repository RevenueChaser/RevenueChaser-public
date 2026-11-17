"""What date is each board actually computed against?

"Last run" only says when a scan executed. It says nothing about how old the
downloaded data underneath is — and a re-render that reads the cache without
touching the network stamps "now" over data that may be days old. That is how
the Swing board came to read "Last run: today" on Aug 31 bars.

So every board backed by downloaded data reports the newest date present in the
data it actually reads. One resolver per board, all reading the store, so a new
board gets a data date by adding one entry rather than by patching the UI.

Returns an ISO ``YYYY-MM-DD`` string, or ``None`` for a board that holds no
downloaded data (a live-only view, or an empty store).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from RevenueChaser.core import rawstore
from RevenueChaser.core.calendar import to_session_date

logger = logging.getLogger(__name__)


def _day(value) -> str | None:
    """Normalise whatever a column holds into a YYYY-MM-DD day."""
    if value in (None, ""):
        return None
    if isinstance(value, (int, float)):  # epoch seconds (ticker_payload_cache.fetched_at)
        return datetime.fromtimestamp(value, tz=timezone.utc).strftime("%Y-%m-%d")
    text = str(value)
    return text[:10] if len(text) >= 10 else None


def session_of(value) -> str | None:
    """ISO New York session date of an old run-time value (epoch, ISO text or date), else ``None``.

    The read path for old tables until each migrates to ``session_date`` (#283, ADR-3). Unlike
    ``_day`` it does not take a text prefix or the UTC date, so a Saturday fetch reads as
    Friday. Never raises: a value outside the calendar or unparseable gives ``None``.
    """
    try:
        d = to_session_date(value)
    except Exception:  # noqa: BLE001 - a label is never worth an error
        return None
    return d.isoformat() if d else None


def _max(sql: str, db: str) -> str | None:
    rows = rawstore.query(sql, db=db)
    return _day(rows[0]["v"]) if rows else None


# ── per-board resolvers ─────────────────────────────────────────────────────

def _comovement_day() -> str | None:
    """Newest prices-store session over the names Co-movement clusters (the classification universe): it reads the
    prices store since PR 8 (G3), so its date is its own names' price date (DF101, as K7 does for Swing and
    Fundamentals)."""
    from RevenueChaser.module_comovement import ohlc
    return prices_day(ohlc.universe_tickers())


def prices_day(tickers) -> str | None:
    """Newest session of the prices store (``rcdata.read.last_sessions``) over ``tickers``; ``None`` when none has a
    bar or there is no store."""
    from RevenueChaser.rcdata import read
    days = list(read.last_sessions(list(tickers)).values())
    return max(days).isoformat() if days else None


def d01_day(tickers) -> str | None:
    """Newest D01 session (``price_bars_daily``) over ``tickers``; ``None`` when none has a bar."""
    from RevenueChaser.core import ledger
    days = [day for day, _ in ledger.d01_last_bars(tickers).values()]
    return max(days) if days else None


def _scored_d01_day(scores: str):
    """A resolver: the newest D01 session over the names in the board's score table ``scores`` (K7, #383 R3).

    Swing and Fundamentals score every name from D01 since C12, so their date is the price date of their own names
    (DF101), not the newest bar of any ticker in a shared cache. Asymmetric Growth reads its momentum from D01 since
    #380 S4, so its date is its scored names' too. No scored name: no date.
    """
    def resolve() -> str | None:
        return d01_day(r["ticker"] for r in rawstore.query(f"SELECT ticker FROM {scores}", db=rawstore._db_of(scores)))
    return resolve


def _scored_prices_day(scores: str):
    """``_scored_d01_day`` over the prices store: Asymmetric Growth reads its momentum there since PR 11 (G3)."""
    def resolve() -> str | None:
        return prices_day(r["ticker"] for r in rawstore.query(f"SELECT ticker FROM {scores}", db=rawstore._db_of(scores)))
    return resolve


def _rotation_day() -> str | None:
    return _max("SELECT max(as_of_date) AS v FROM rotation_snapshots", db="sector_rotation")


def _sec13f_day() -> str | None:
    """Newest 13F reporting period the builder serves (``ownership.sec13f_totals``) — what the board renders.
    Quarterly, so months behind by design."""
    from RevenueChaser.core import ownership
    periods = {p for per in ownership.sec13f_totals().values() for p in per}
    return max(periods) if periods else None


def _leaps_day() -> str | None:
    """The newest session of ``option_far_contract``, the one table the LEAPS board reads (#746)."""
    from RevenueChaser.rcdata import read
    sessions = read.far_contract_sessions()
    return str(sessions[0]["session_date"]) if sessions else None


def _spx_gamma_day() -> str | None:
    """SPX Gamma's newest shown day, from its board file's latest pointer (``spx_meta``)."""
    from RevenueChaser.app import runners
    payload = runners.spxgamma_latest()
    if not payload:
        return None
    return _day(payload.get("asof_date") or payload.get("api_snapshot_time"))


def _chain_day() -> str | None:
    """Newest filing date in the Value Chain corpus."""
    return _max("SELECT max(filed) AS v FROM chain_filings", db="value_chain")   # #860 stage 1


def _oipd_day() -> str | None:
    """As-of day of the cached chain of the ticker on the board (falls back to its fetch time).

    The shown ticker is the one in the last rendered payload (``.cache/oipd/oipd_latest.json``); with none
    rendered there is no shown ticker and no date. Not the newest ``as_of`` of any ticker (OIPD-7).
    """
    from RevenueChaser.core.config import OUTPUT_DIR as CACHE_ROOT
    p = CACHE_ROOT / "oipd" / "oipd_latest.json"
    if not p.exists():
        return None
    ticker = (json.loads(p.read_text(encoding="utf-8")).get("ticker") or "").strip().upper()
    if not ticker:
        return None
    rows = rawstore.query("SELECT as_of, fetched_at FROM oipd_meta WHERE ticker = ?", [ticker], db="oipd")
    if not rows:
        return None
    return _day(rows[0].get("as_of")) or _day(rows[0].get("fetched_at"))


def _news_day() -> str | None:
    """NY day of the newest economic-calendar fetch in ``boards/news.duckdb`` (the headlines carry their own times)."""
    rows = rawstore.query("SELECT max(fetched_at) AS v FROM news_calendar", db="news")
    return session_of(rows[0]["v"]) if rows and rows[0]["v"] is not None else None


# module key (as used by app/dashboard.py's tabs) -> resolver.
# A board absent from this map, or mapped to None, shows no data date — say so
# explicitly rather than leaving a stale value on screen.
RESOLVERS = {
    # Swing and Fundamentals: the D01 date of the names they last scored (K7, #383 R3); Asymmetric Growth: their
    # prices-store date (#380 S4, PR 11).
    "module_swing_potential": _scored_d01_day("swing_scores"),
    "module_fundamentals": _scored_d01_day("fundamentals_scores"),
    "module_asymmetric_growth": _scored_prices_day("ticker_scores"),
    # Co-movement clusters its names' prices-store closes (PR 8).
    "module_comovement": _comovement_day,
    # Earnings Radar: its run record lived in the old history file (#860), so it has no date stamp.
    "module_earnings_radar": None,
    "module_sector_rotation": _rotation_day,
    "module_sec_13f": _sec13f_day,
    "module_leaps": _leaps_day,
    # Hit Rate (#25): derived from the frozen picks, no downloaded data of its own.
    "module_hit_rate": None,
    # Watch lists (#786): the lists are avo's own and have no data date, so the stamp is the one the numbers beside
    # them carry — the prices store's newest close, the session the board's own header names.
    "module_watchlists": _comovement_day,
    "module_spx_gamma": _spx_gamma_day,
    # Financials: its payload cache lived in the old raw.duckdb (#860), so it has no date stamp.
    "module_financials": None,
    "module_value_chain": _chain_day,
    # Relatedness profiles are derived from the same 10-K/20-F corpus.
    "module_relatedness": _chain_day,
    # Implied Probability reads its own cached UW option chain.
    "module_oipd": _oipd_day,
    # News: the day of its newest calendar fetch.
    "module_news": _news_day,
    # Welcome summarises many datasets, each card stating its own session or time: no single date to stamp.
    "module_welcome": None,
    # Settings (avo, 10 Nov 2026: "su bolumlerde dogru gelmeli"): each dataset keeps its own date on its row; the
    # header carries the universe's newest prices-store close, the session the Health "prices behind" card names.
    "module_settings": _comovement_day,
    # interactive lab over the UW API: live state, no downloaded dataset
    "module_uw_interaction": None,
    # the dashboard's own log files: no downloaded dataset
    "logs": None,
    "runs": None,
}


def last_run(module: str) -> str | None:
    """When the board's own run last started, ISO UTC; ``None`` when the shell's per-board reader says it.

    Only Settings answers here: its run is the builder's (``ops.last_builder_run``). Never raises."""
    if module != "module_settings":
        return None
    try:
        from RevenueChaser.rcdata import ops
        run = ops.last_builder_run() or {}
        started = run.get("started_at")
        return datetime.fromtimestamp(float(started), tz=timezone.utc).isoformat() if started else None
    except Exception:  # noqa: BLE001 - a label is never worth an error
        logger.debug("last_run(%s) failed", module, exc_info=True)
        return None


def data_as_of(module: str) -> str | None:
    """Newest data date backing ``module``; ``None`` when it has none.

    Never raises: a provenance label must not be able to break a board.
    """
    resolver = RESOLVERS.get(module)
    if resolver is None:
        return None
    try:
        return resolver()
    except Exception:  # noqa: BLE001 - a label is never worth an error
        logger.debug("data_as_of(%s) failed", module, exc_info=True)
        return None
