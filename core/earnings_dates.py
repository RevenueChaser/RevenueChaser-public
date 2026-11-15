"""The next earnings date a screener card shows: UW's calendar on the options layer, Yahoo's own value otherwise
(#304, G6).

The cards (Asymmetric Growth, Swing, Fundamentals) and their week filter read ``quote["earningsTimestampStart"]``
(epoch seconds). The source is ``options.duckdb``'s ``option_screener_daily`` (``uw/option_screener``, G8), asked
through ``needs.ask("earnings.next")``; a name the layer does not hold keeps Yahoo's value. The stored D26 calendar
(``earnings_calendar`` in the old ``raw.duckdb``) was the second source until #860 removed the old store.

Freshness is the catalog's and only the catalog's (avo, 29 Oct 2026): ``earnings.next``'s ``max_lag``, with the unit
it is counted in (one session). A session older than that, or later than ``today``, is not read.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from RevenueChaser.core import calendar

logger = logging.getLogger(__name__)

#: The need the layer's calendar is asked for; its ``max_lag`` is the one freshness constant.
NEED = "earnings.next"


def next_dates_answer(today: date | None = None):
    """The ``earnings.next`` answer. ``rows`` are the layer's screener rows as the store holds them; the
    ``{ticker: date}`` map a card wants is ``stored_next_dates``. This keeps the envelope, for the cards that show how
    fresh the calendar is.
    """
    from RevenueChaser.rcdata import needs

    today = today or calendar.today_ny()
    need = needs.catalog.NEEDS[NEED]
    try:
        ans = needs.ask(NEED)
    except Exception as exc:  # noqa: BLE001 - an unreadable layer reads as missing
        logger.warning("the options layer's earnings calendar could not be read (%s)", exc)
        ans = needs.Answer(need=NEED, rows=[], state="missing", status="unreadable",
                         freshness={"as_of_session": None, "lag_sessions": None,
                                    "max_lag": need.max_lag, "unit": need.max_lag_unit},
                         coverage={"asked": 0, "served": 0, "missing": [], "from_fallback": 0}, provenance=[])
    return ans


def stored_next_dates(today: date | None = None) -> dict[str, date]:
    """``{ticker: next earnings date on or after today}``: the layer's calendar. ``{}`` when it does not answer;
    never an error."""
    today = today or calendar.today_ny()      # the New York date: after midnight in Amsterdam it is still yesterday there
    from RevenueChaser.rcdata import needs

    need = needs.catalog.NEEDS[NEED]
    try:
        return _layer_dates(needs.ask(NEED), today, need)
    except Exception as exc:  # noqa: BLE001 - a card keeps Yahoo's date
        logger.warning("the options layer's earnings calendar could not be read (%s)", exc)
        return {}


def _layer_dates(ans, today: date, need) -> dict[str, date]:
    """``{ticker: coming report date}`` from the layer's answer, or ``{}`` when its session is too old or not yet
    reached. A session later than ``today`` is a calendar from a run that has not happened for this day yet."""
    session = ans.freshness["as_of_session"]
    if session is None or session > today:
        return {}
    from RevenueChaser.rcdata import needs

    # The lag is counted against the day the API counts it against, not against ``today``: on a trading day whose
    # session is not over yet those differ by one, and the card and the filter would disagree (review I1).
    if needs.lag_in(need.max_lag_unit, session, max(needs.reference_session(), session)) > need.max_lag:
        return {}
    # One row per session and ticker (the table's key), so a name has one report date in the session.
    return {str(r["ticker"]).strip().upper(): r["report_date"] for r in ans.rows
            if r.get("session_date") == session and r.get("ticker") and r.get("report_date")
            and r["report_date"] >= today}


def epoch(day: date) -> float:
    """Noon UTC of ``day``: the same calendar date in every timezone the week filter can run in."""
    return datetime(day.year, day.month, day.day, 12, tzinfo=timezone.utc).timestamp()


def with_stored_date(row: dict, stored: dict[str, date]) -> dict:
    """``row`` with the stored date in its quote, or ``row`` itself when the store has none for the ticker."""
    day = stored.get(str(row.get("ticker") or "").strip().upper())
    if day is None:
        return row
    return {**row, "quote": {**(row.get("quote") or {}), "earningsTimestampStart": epoch(day)}}
