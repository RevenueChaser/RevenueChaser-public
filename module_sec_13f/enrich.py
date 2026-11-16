"""The 13F board's snapshot inputs (#375 F2, 13F-B): read from the shared stores, never from a provider.

Per 13F ticker (``load_inputs``), in the shape ``report.board_entries`` reads:

- ``shares_outstanding``, ``shares_source``, ``shares_as_of``, ``shares_note``: the shared reader
  (``core.ownership.shares_outstanding``, #646): the newest SEC cover count, else market cap ÷ price for one-class
  common (``estimate``), else none with the reason in ``shares_note``. The board's ``% Out`` divides by it.

- ``price``: ``{quarter_end: close}`` from D01 (``price_bars_daily``), nominal (splits applied by
  ``prices.apply_events``, as ``prices.daily_bars`` applies them): the last close on or before each quarter end, at
  most ``PRICE_LOOKBACK_DAYS`` calendar days earlier, read in short bounded windows (``quarter_end_closes`` says
  why not the open-ended K8a window). The board's Price Δ is the change between the first and the last of these
  closes.

- ``split_factor``: ``{quarter_end: factor}`` from the prices store (``core.ownership.split_factors_13f``, #732):
  the factor that puts a share count of that quarter end on today's basis. The board divides every quarter's shares
  and flows by it and multiplies the close by it, so a split is not read as buying or selling. A quarter with no
  factor stays as filed.

- ``breaks``: ``[{period, kind, shares, cik, filer_name}]`` from the board's own file (``store.read_breaks``, #732): the
  filers that started or stopped reporting the ticker in a settled quarter, which the flows leave out. The board
  marks the ticker and lists them, newest first.

- ``short_pct``, ``short_pct_as_of``: FINRA's newest settlement short interest (``core.ownership.finra_short``, the
  Earnings board's reader too; #576, decision A) over ``shares_outstanding``, in %, and its settlement day. A
  settlement older than the ``ownership.short_interest`` need allows is not read.

Insider % is not shown (owner, 12 Nov 2026, #732; it comes back with its new reader, #646). A ticker with no
value for a field has no key for it, so the board shows "—", never 0.

The Fetch (after its shares step), the store-only Refresh and the ``/api/sec_13f/<t>`` chart all read these inputs
here, so every number comes out of the same path.

"""
from __future__ import annotations

import logging
from datetime import date, timedelta

from RevenueChaser.core import ownership

logger = logging.getLogger(__name__)

PRICE_LOOKBACK_DAYS = 10     # a quarter end on a weekend or a holiday still finds the session before it


def quarter_end_closes(tickers, quarters) -> dict[str, dict[str, float]]:
    """``{ticker: {quarter_end: close}}``: the last D01 nominal close on or before each quarter end, within
    ``PRICE_LOOKBACK_DAYS``.

    The K8a window (``prices.daily_bars(start=)``) has no upper bound (an adjusted bar needs the closes after it),
    so one window per quarter end would read every bar from 2025 to today for the whole 13F universe: about 53 s on
    a 2,222-ticker store, against a 3 s Refresh. This read is bounded on both sides instead: only the bars inside
    the quarter-end windows, plus the splits after the first window. The nominal series is ``prices.apply_events``
    (the rule ``daily_bars`` applies: a split divides the bars fetched before it), so a close is the one
    ``daily_bars(basis="nominal")`` returns for that session. Dividends do not change a nominal close.
    """
    from RevenueChaser.core import prices
    names = sorted({str(t).strip().upper() for t in tickers if t})
    qs = sorted(set(quarters))
    out: dict[str, dict[str, float]] = {}
    if not names or not qs:
        return out
    windows = [(date.fromisoformat(q) - timedelta(days=PRICE_LOOKBACK_DAYS), date.fromisoformat(q)) for q in qs]
    marks = ", ".join("?" * len(names))
    ranges = " OR ".join("session_date BETWEEN ? AND ?" for _ in windows)
    bars: dict[str, list[dict]] = {}
    for r in prices._read(f"SELECT * FROM price_bars_daily WHERE ticker IN ({marks}) AND ({ranges})",
                          [*names, *(d for w in windows for d in w)], layer=True):
        bars.setdefault(r["ticker"], []).append(r)
    splits: dict[str, list[dict]] = {}
    for r in prices._read(f"SELECT * FROM price_actions WHERE action = 'split' AND ticker IN ({marks}) "
                          f"AND ex_date > ?", [*names, windows[0][0]], layer=True):
        splits.setdefault(r["ticker"], []).append(r)
    for ticker, rows in bars.items():
        series = [b for b in prices.apply_events(rows, splits.get(ticker, []), "nominal") if b.get("close") is not None]
        for (start, end), q in zip(windows, qs):
            inside = [b for b in series if start <= b["session_date"] <= end]
            if inside:
                out.setdefault(ticker, {})[q] = float(inside[-1]["close"])
    return out


def _short_interest(tickers) -> dict[str, dict]:
    """FINRA's newest settlement of each ticker inside the ``ownership.short_interest`` age; ``{}`` and a warning
    when the store cannot be read, never a failed board."""
    try:
        return ownership.finra_short_recent(tickers)
    except Exception as exc:  # noqa: BLE001 - no FINRA rows is "no Short%", never a failed board
        logger.warning("13F short interest unread, Short%% stays empty: %s: %s", type(exc).__name__, exc)
        return {}


def load_inputs(totals: dict) -> dict[str, dict]:
    """The board's snapshot inputs of every ticker in ``totals`` (``{ticker: {period: cell}}``): see the module
    docstring. Store reads only, zero network."""
    from RevenueChaser.module_sec_13f import engine
    tickers = [t for t in totals if t]
    quarters = sorted({q for periods in totals.values() for q in periods if q >= engine.START_QUARTER})
    out: dict[str, dict] = {}
    for ticker, so in ownership.shares_outstanding(tickers).items():
        out[ticker] = {"shares_outstanding": so["shares"], "shares_source": so["source"],
                       "shares_as_of": so["as_of"], "shares_note": so["note"]}
    for ticker, row in _short_interest(tickers).items():
        so = out.get(ticker, {}).get("shares_outstanding")
        if row.get("current_short") is not None and so:
            out[ticker].update(short_pct=100.0 * float(row["current_short"]) / so,
                               short_pct_as_of=row["settlement_date"].isoformat())
    for ticker, px in quarter_end_closes(tickers, quarters).items():
        out.setdefault(ticker, {})["price"] = px
    wanted = {t: [q for q in periods if q >= engine.START_QUARTER] for t, periods in totals.items() if t}
    for ticker, factors in ownership.split_factors_13f(wanted).items():
        out.setdefault(ticker, {})["split_factor"] = factors
    from RevenueChaser.module_sec_13f import store
    for ticker, breaks in store.read_breaks(tickers).items():
        out.setdefault(ticker, {})["breaks"] = breaks
    return out
