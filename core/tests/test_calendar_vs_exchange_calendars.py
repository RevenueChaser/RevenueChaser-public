"""Cross-check ``core.calendar``'s hand-typed NYSE closure table against ``exchange_calendars``.

``_MARKET_HOLIDAYS`` is typed by hand (1993-2024 from each year's observance rules plus the special
closures, 2025-2028 transcribed from nyse.com), and its 1993-2024 half was checked once against CRSP's
trading dates. Nothing checked it again afterwards, and nothing checks the transcribed years at all, so a
mistyped day would reach a ``session_date`` in a build before anyone noticed.

This test is that second opinion: ``exchange_calendars``' ``XNYS`` sessions over the same span. It is a
cross-check and never a source of truth -- the package says plainly that "all of the exchange calendars are
maintained by user contributions", so a difference means *look*, not *copy*. A difference we have decided on
goes in ``ACCEPTED`` with its reason; measured with exchange_calendars 4.13.3 on 2026-11-20, there are none
over all 36 years.

Offline by construction: the package carries its holiday rules in code, so nothing here opens a socket.
"""

from __future__ import annotations

from datetime import date, timedelta

import exchange_calendars as xcals

from revenuechaser.core import calendar as rc_calendar

# (year, ISO date) -> why we keep our own answer. Empty today; a row here is a decision, not a TODO.
ACCEPTED: dict[tuple[int, str], str] = {}


def _xnys_weekday_closures() -> dict[int, set[date]]:
    """Per year, the weekdays in our table's span that XNYS does not trade."""
    years = sorted(rc_calendar.MARKET_HOLIDAYS)
    cal = xcals.get_calendar("XNYS", start=f"{years[0]}-01-01", end=f"{years[-1]}-12-31")
    sessions = {d.date() for d in cal.sessions}
    out: dict[int, set[date]] = {y: set() for y in years}
    day = date(years[0], 1, 1)
    end = date(years[-1], 12, 31)
    while day <= end:
        if day.weekday() < 5 and day not in sessions:
            out[day.year].add(day)
        day += timedelta(days=1)
    return out


def test_every_year_agrees_with_xnys() -> None:
    theirs = _xnys_weekday_closures()
    differences: list[str] = []
    for year, ours in sorted(rc_calendar.MARKET_HOLIDAYS.items()):
        for day in sorted(ours - theirs[year]):
            if (year, day.isoformat()) not in ACCEPTED:
                differences.append(f"{day}: closed in core.calendar, a session in XNYS")
        for day in sorted(theirs[year] - ours):
            if (year, day.isoformat()) not in ACCEPTED:
                differences.append(f"{day}: a session in core.calendar, closed in XNYS")
    assert not differences, (
        "core.calendar._MARKET_HOLIDAYS and exchange_calendars' XNYS disagree:\n  "
        + "\n  ".join(differences)
        + "\nCheck https://www.nyse.com/markets/hours-calendars, fix whichever is wrong, and only then add"
          " the day to ACCEPTED with its reason."
    )


def test_the_cross_check_covers_our_whole_span() -> None:
    """A silent empty comparison would pass; this is what makes the test above mean something."""
    theirs = _xnys_weekday_closures()
    assert set(theirs) == set(rc_calendar.MARKET_HOLIDAYS)
    assert all(theirs[y] for y in theirs), "XNYS reports no closure at all for " + str(
        sorted(y for y in theirs if not theirs[y]))
