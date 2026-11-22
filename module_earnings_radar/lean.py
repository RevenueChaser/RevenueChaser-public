"""The prints R5's institutional lean reads: a window of sessions and a slice of strikes and expiries (#256).

``docs/module_earnings-radar/redesign.md`` R5 asks for two local filters the ``flow-recent`` endpoint cannot do itself
("Window: last 1-3 sessions", "Strike filter = R4 EM-band + earnings-expiry proximity. ``flow-recent`` does not
slice strikes - slice locally"). Until this module the lean read whatever the endpoint returned: every strike, every
expiry, and as many sessions back as the newest prints happened to span. A LEAP bought a week before the report, or
a far out-of-the-money strike that is no earnings bet at all, counted the same as the night's at-the-money sweep.

``select`` is pure: it takes the prints the pipeline already fetched (no request of its own) and returns the subset
the lean is computed over. The tape's own newest print sets the window, not the clock, so a Fetch of a past day and
a Fetch of tonight slice the same way.

Three filters, each of which keeps a print when the figure it needs is missing - the tape is evidence and an absent
field is not a reason to drop a print:

- **Window.** The NY dates the prints carry, newest first: keep the newest ``sessions`` of them. "Session" is a day
  the tape actually served, so a holiday or a quiet name costs no window.
- **Strike band.** ``spot x (1 +/- move x slack)``, where ``move`` is R4's expected move for the report and
  ``slack`` widens it so a bet one strike outside the implied move still counts. No spot or no expected move keeps
  every strike.
- **Expiry.** From the report day out to ``expiry_days`` after it. An expiry before the report cannot express the
  event; one far beyond it is a position, not an earnings bet. No earnings date, or a print with no expiry, keeps it.

``R8``'s retail share and the tape buckets on the card keep reading the whole answer: the slice is R5's alone.
"""
from __future__ import annotations

from datetime import date, datetime, timezone

from RevenueChaser.core import calendar as rc_calendar
from RevenueChaser.core.config import R5_LEAN_BAND_SLACK, R5_LEAN_EXPIRY_DAYS, R5_LEAN_SESSIONS


def _day(value) -> date | None:
    """The NY date of a print's ``executed_at`` (UW serves UTC), or a plain date/datetime as given."""
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, date):
        return value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(rc_calendar.NY).date()


def _expiry(item: dict) -> date | None:
    raw = item.get("expiry")
    if raw in (None, ""):
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _strike(item: dict) -> float | None:
    raw = item.get("strike")
    try:
        return None if raw in (None, "") else float(raw)
    except (TypeError, ValueError):
        return None


def select(prints: list | None, *, spot: float | None = None, expected_move_pct: float | None = None,
           earnings_date: date | None = None, sessions: int = R5_LEAN_SESSIONS,
           expiry_days: int = R5_LEAN_EXPIRY_DAYS, band_slack: float = R5_LEAN_BAND_SLACK) -> list:
    """The prints R5's lean reads. ``expected_move_pct`` is R4's figure as a fraction (0.08 = 8%)."""
    rows = [p for p in (prints or []) if isinstance(p, dict)]
    if not rows:
        return []

    days = sorted({d for d in (_day(p.get("executed_at")) for p in rows) if d is not None}, reverse=True)
    keep_days = set(days[:max(1, int(sessions))]) if days else set()
    if keep_days:
        rows = [p for p in rows if (_day(p.get("executed_at")) or min(keep_days)) in keep_days]

    low = high = None
    if spot and spot > 0 and expected_move_pct:
        band = abs(float(expected_move_pct)) * float(band_slack)
        low, high = float(spot) * (1 - band), float(spot) * (1 + band)
    if low is not None:
        rows = [p for p in rows if (k := _strike(p)) is None or low <= k <= high]

    if earnings_date is not None:
        last = earnings_date.toordinal() + int(expiry_days)
        rows = [p for p in rows
                if (x := _expiry(p)) is None or earnings_date.toordinal() <= x.toordinal() <= last]
    return rows
