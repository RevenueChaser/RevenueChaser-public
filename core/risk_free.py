"""The stored 10-year Treasury yield as a risk-free rate — one reader for every board that needs one.

The source is the market serving layer's ``market_series`` DGS10 from FRED (``rcdata``, G6), which stores the yield
**in percent** (4.25), so a rate is that value divided by 100. There is no fallback source: the old store's
``macro_series`` row went with it (#860), and a board without a stored yield takes its own labelled default.

FRED publishes DGS10 one business day late, so the observation of the session a board is pricing is often not held
yet. :func:`stored_dgs10` therefore reads the newest observation dated **on or before** that session, inside a window
the caller sets, and hands back the date with the rate so the board can say which day's yield it used.
"""
from __future__ import annotations

from datetime import date, timedelta

#: How many calendar days before a session an observation may be and still count. A ten-year yield moves a few basis
#: points in two weeks, and every caller's fallback is a flat constant, which is further off than a two-week-old
#: yield (Financials review S2, the Opus review's N1).
DEFAULT_MAX_AGE_DAYS = 14


def _day(value) -> date | None:
    if value is None:
        return None
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def stored_dgs10(session=None, max_age_days: int = DEFAULT_MAX_AGE_DAYS) -> dict | None:
    """``{"value": rate, "as_of": "YYYY-MM-DD"}`` — the newest stored FRED 10-year yield as a decimal rate, dated on
    or before ``session`` (default: today in New York) and at most ``max_age_days`` calendar days before it.

    ``None`` when no market file is served yet, or when the window holds no observation. Read-only and zero network,
    so a Refresh reads it too.
    """
    from ..rcdata import read, serving
    from . import calendar as market_calendar
    end = _day(session) or market_calendar.today_ny()
    if not serving.live_path("market").exists():
        return None            # no market file yet; the old store's macro_series row went with it (#860)
    rows = [r for r in read.market_series(["DGS10"], start=end - timedelta(days=max_age_days), end=end)
            if r.get("source") == "fred" and r.get("value") is not None]
    if not rows:
        return None
    newest = max(rows, key=lambda r: r["obs_date"])
    return {"value": float(newest["value"]) / 100, "as_of": _day(newest["obs_date"]).isoformat()}
