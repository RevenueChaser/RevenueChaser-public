"""Next week's earnings days of the names on avo's watch lists (#886).

The board's third calendar tab. avo's answers of 20 Nov 2026 ("Olur", yes to all four): the names come from the
**News watch lists** (``module_news/headlines.LISTS``: avo's own lists, the stock picks, the News list), the days
come from the **Alpha Vantage earnings calendar** the builder already serves (``fundamentals.earnings_event``),
and the pass runs **every Sunday at 09:00 Amsterdam**, once a week, because a calendar of next week does not
change by the hour.

Store-only: no provider call. One ``news_earnings`` row a name, kept for one week at a time — Sunday's pass
writes next week's rows and drops every other week, so the table is the week the board shows and nothing else.
The refresh time itself travels in ``news_meta`` under ``earnings_refresh``, which is the "last refresh" line on
the page: without it a stale tab cannot be told from a quiet week.
"""
from __future__ import annotations

import time
from datetime import date, datetime, timedelta

from RevenueChaser.core import rawstore
from RevenueChaser.module_news.calendar import META, local_day
from RevenueChaser.rcdata import read

TABLE = "news_earnings"
#: ``news_meta`` key holding the epoch second of the last pass (the page's "last refresh" line).
MARK_KEY = "earnings_refresh"
#: The days the tab shows: Monday to Friday. US companies do not report at the weekend, and avo's mock has five
#: headings; a Saturday row would still be stored, it simply has no day to stand under.
TRADING_DAYS = 5


def week(now: float | None = None) -> tuple[date, date]:
    """Next week's Monday and Friday, Amsterdam. On Sunday that is the week starting tomorrow, so the pass's own
    day belongs to the week it is leaving, not to the one it writes."""
    today = local_day(time.time() if now is None else now)
    monday = today - timedelta(days=today.weekday()) + timedelta(days=7)
    return monday, monday + timedelta(days=TRADING_DAYS - 1)


def _names() -> set[str]:
    """The watch-list names, the same lists the per-ticker headlines read. A list that cannot be read is logged
    and left out (``read.picked``), so one bad list never empties the tab."""
    from RevenueChaser.module_news import headlines
    return read.picked(headlines.LISTS)


def _better(new: dict, old: dict) -> bool:
    """Which of two rows for one name stands: a confirmed report beats a calendar guess, then the one the source
    saw most recently, then the earlier day."""
    return (bool(new.get("confirmed")), str(new.get("source_as_of") or ""), str(old.get("report_date") or "")) > (
        bool(old.get("confirmed")), str(old.get("source_as_of") or ""), str(new.get("report_date") or ""))


def rows(now: float | None = None) -> list[dict]:
    """The watch-list names reporting next week, one row a name, by day then name. Reads the market store only."""
    monday, friday = week(now)
    names = _names()
    if not names:
        return []
    company = {c["cik"]: c for c in read.fundamental_companies(names) if c.get("cik")}
    if not company:
        return []
    best: dict[str, dict] = {}
    for e in read.earnings_events(start=monday, end=friday):
        c = company.get(e.get("cik"))
        if c is None:
            continue
        ticker = str(c.get("ticker") or e.get("ticker") or "").upper()
        if not ticker or (ticker in best and not _better(e, best[ticker])):
            continue
        best[ticker] = {**e, "ticker": ticker, "company": c.get("name")}
    return sorted(best.values(), key=lambda r: (str(r["report_date"]), r["ticker"]))


def build(now: float | None = None, run_id: str | None = None) -> dict:
    """One weekly pass: next week's rows replace the table, and the mark moves. Returns ``week_start`` and the
    number of names written."""
    now = time.time() if now is None else now
    run_id = run_id or f"news-earnings-{int(now)}"
    monday, _friday = week(now)
    found = rows(now)
    rawstore.execute(f"DELETE FROM {TABLE}", db="news")       # one week at a time, never a second week's leftovers
    rawstore.write_rows(TABLE, [{
        "week_start": monday.isoformat(), "ticker": r["ticker"], "company": r.get("company"),
        "report_date": str(r["report_date"])[:10], "report_time": r.get("report_time"),
        "confirmed": bool(r.get("confirmed")), "source": r.get("source"), "run_id": run_id, "run_at": now,
    } for r in found])
    rawstore.write_rows(META, [{"key": MARK_KEY, "value": repr(float(now)), "run_at": now}])
    return {"week_start": monday.isoformat(), "names": len(found)}


def stored(now: float | None = None) -> tuple[list[dict], float | None]:
    """What the board shows: the stored rows of next week, and when the pass last ran. A table holding another
    week (the pass has not run since the week turned) answers no rows, so the tab says the week is not built
    rather than showing last week's days."""
    monday, _friday = week(now)
    got = rawstore.query(f"SELECT * FROM {TABLE} WHERE week_start = ? ORDER BY report_date, ticker",
                         [monday.isoformat()], db="news")
    mark = rawstore.query(f"SELECT value FROM {META} WHERE key = ?", [MARK_KEY], db="news")
    try:
        at = float(mark[0]["value"]) if mark else None
    except (TypeError, ValueError):
        at = None
    return got, at


def day_of(row: dict) -> date:
    """The row's report day as a date, whatever the store hands back (a ``date`` or its ISO text)."""
    value = row["report_date"]
    return value if isinstance(value, date) and not isinstance(value, datetime) else date.fromisoformat(
        str(value)[:10])
