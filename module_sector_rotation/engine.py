"""Sector & Theme Rotation Engine — RRG-style relative strength vs SPY."""
import logging
import math
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Optional
import numpy as np

from RevenueChaser.core import rotation_reference
from .universe import MACRO_SERIES
from RevenueChaser.core.gics_map import UNCLASSIFIED, canonical_sector, is_unclassified
from RevenueChaser.core.providers.unusual_whales import UWClient
from RevenueChaser.module_sector_rotation.models import ETFRotationSnapshot

logger = logging.getLogger(__name__)

LOOKBACKS = {"rs_1w": 1, "rs_1m": 4, "rs_3m": 12}

# Daily trading-day lookbacks for ETF holdings RS (≈ 1W / 1M / 3M).
HOLDING_LOOKBACKS = {"rs_1w": 5, "rs_1m": 21, "rs_3m": 63}


def _finite(v):
    """True for numbers that are not None and not NaN."""
    return v is not None and not (isinstance(v, float) and math.isnan(v))


# SPY closes the holdings RS needs: the longest lookback plus today's close. Fewer means the prices store does not
# hold enough of the benchmark, and every RS would read 0.0.
SPY_MIN_CLOSES = HOLDING_LOOKBACKS["rs_3m"] + 1


def relative_strength_pct(etf_closes: list[float], spy_closes: list[float], lookback: int) -> float:
    if len(etf_closes) <= lookback or len(spy_closes) <= lookback:
        return 0.0
    etf_ret = etf_closes[-1] / etf_closes[-1 - lookback] - 1
    spy_ret = spy_closes[-1] / spy_closes[-1 - lookback] - 1
    return round((etf_ret - spy_ret) * 100, 2)


def _industry_label(value) -> str:
    """A stored industry for the tree: blank, ``Other`` and ``Unclassified`` are one bucket, ``Unclassified``."""
    return UNCLASSIFIED if not value or is_unclassified(value) else str(value).strip() or UNCLASSIFIED


def _unknown_last(label: str) -> tuple[bool, str]:
    """Sort key: real labels alphabetically, the ``Unclassified`` bucket after them."""
    return (label == UNCLASSIFIED, label)


def industry_buckets(rows: list[dict]) -> dict[tuple, list[dict]]:
    """``{(sector, industry): members}`` from universe rows (pure; no store access).

    The sector is read through ``canonical_sector`` (a stored GICS spelling lands under its Morningstar name; a
    blank, ``Other`` or unknown one is ``Unclassified``). Members without a positive market cap are dropped. A
    blank, ``Other`` or ``Unclassified`` industry is the one ``Unclassified`` bucket (the identity master writes
    ``Unclassified``; ``Other`` is the pre-R3 spelling).
    """
    buckets: dict[tuple, list[dict]] = defaultdict(list)
    for r in rows:
        try:
            mc = float(r.get("market_cap"))
        except (TypeError, ValueError):
            continue
        if mc <= 0:
            continue
        buckets[(canonical_sector(r.get("sector")),
                 _industry_label(r.get("industry")))].append({
            "ticker": r.get("ticker") or "",
            "name": r.get("name") or "",
            "market_cap": mc,
        })
    return buckets


def sector_industry_tree(max_per_industry: int = 12) -> dict[str, list[dict]]:
    """Morningstar sector -> industry -> cap-weighted members.

    Built from the shared universe (``core.universe.load_cached_universe``: the spine's names, sectors and
    industries, the prices store's caps; #642 PR 4), so it needs no network and stays consistent with every other
    board's sector and industry labels. ``weight`` is each member's share of its own industry's
    market cap, so an industry's weights sum to ~100% (before the
    ``max_per_industry`` cut). Members without a market cap are dropped; an
    industry with none is omitted.
    """
    from RevenueChaser.core import universe
    return build_industry_tree(universe.load_cached_universe(), max_per_industry)


def build_industry_tree(rows: list[dict], max_per_industry: int = 12) -> dict[str, list[dict]]:
    """``sector_industry_tree`` from universe rows (pure).

    Within a sector the ``Unclassified`` industry is sorted last.
    """
    buckets = industry_buckets(rows)

    grouped: dict[str, dict[str, list[dict]]] = defaultdict(dict)
    for (sec, ind), members in buckets.items():
        total = sum(m["market_cap"] for m in members)
        if total <= 0:
            continue
        members.sort(key=lambda m: m["market_cap"], reverse=True)
        for m in members:
            m["weight"] = round(m["market_cap"] / total * 100, 2)
        grouped[sec][ind] = members[:max_per_industry]

    return {sec: [{"industry": ind, "holdings": industries[ind]}
                  for ind in sorted(industries, key=_unknown_last)]
            for sec, industries in grouped.items()}


def sector_etf_trees(max_per_industry: int = 12) -> dict[str, list[dict]]:
    """``{sector ETF ticker: industry tree}`` for the rotation map's sector rows.

    ``XLK`` -> Technology's tree, etc. Theme/region/bond rows are not sectors
    and are excluded (they keep their ETF holdings).
    """
    return etf_trees(sector_industry_tree(max_per_industry=max_per_industry))


def etf_trees(tree: dict[str, list[dict]]) -> dict[str, list[dict]]:
    """``{sector ETF ticker: that sector's tree}`` from a ``sector_industry_tree`` result (pure).

    A sector ETF is matched on its ``ROTATION_ETFS`` name, which is the Morningstar sector name of the universe's
    ``sector``.
    """
    out: dict[str, list[dict]] = {}
    for ticker, info in rotation_reference.rotation_etfs().items():
        if info.get("group") != "sector":
            continue
        if info.get("name") in tree:
            out[ticker] = tree[info["name"]]
    return out


# Calendar days of the prices store the holdings RS reads before the rotation session: 63 sessions back plus holidays and margin.
HOLDINGS_READ_DAYS = 120


def holdings_rs_rows(holdings: list[dict], points: dict[str, list[tuple[date, float]]],
                     spy: list[tuple[date, float]], as_of: date, max_holdings: int = 10) -> list[dict]:
    """Top holdings with SPY-relative strength from the stored daily closes (M-ROT-3, ROT-8); pure, no read, no fetch.

    The lookbacks (``HOLDING_LOOKBACKS``) are counted in SPY's sessions up to ``as_of``: a holding's RS over L sessions
    compares its close on SPY's last session with its close L sessions before, both on the same dates as SPY's. A
    holding the store holds no bar of on either date gets ``None`` for that RS (shown "n/a", a dash, DF67), and one with no
    bar at all keeps its row with ``close`` ``None`` too: it is never dropped silently. ``[]`` when SPY has fewer than
    ``SPY_MIN_CLOSES`` sessions (every RS would be missing), so the caller keeps what it stored.
    """
    spy = sorted((d, c) for d, c in spy if d <= as_of and _finite(c))
    if len(spy) < SPY_MIN_CLOSES:
        logger.warning("holdings RS: the prices store holds %d SPY sessions up to %s, need %d; no RS computed",
                       len(spy), as_of, SPY_MIN_CLOSES)
        return []
    dates = [d for d, _ in spy]
    spy_at = dict(spy)
    end = dates[-1]
    rows = []
    for h in holdings:
        t = h.get("ticker")
        if not t:
            continue
        series = {d: c for d, c in points.get(t, []) if d <= as_of and _finite(c)}
        row = {"ticker": t, "name": h.get("name") or "", "weight": _safe_float(h.get("weight")),
               "close": series[max(series)] if series else None}
        for key, lookback in HOLDING_LOOKBACKS.items():
            start = dates[-1 - lookback]
            a, b = series.get(start), series.get(end)
            row[key] = (None if a is None or b is None or not a or not spy_at[start]
                        else round(((b / a - 1) - (spy_at[end] / spy_at[start] - 1)) * 100, 2))
        rows.append(row)
    rows.sort(key=lambda r: r["weight"], reverse=True)
    return rows[:max_holdings]


def _session_of(snapshots) -> date | None:
    """The rotation session the snapshots are of (their newest ``as_of_date``), or ``None``."""
    days = []
    for s in snapshots:
        d = getattr(s, "as_of_date", None)
        if isinstance(d, str):
            try:
                d = date.fromisoformat(d[:10])
            except ValueError:
                continue
        if isinstance(d, datetime):
            d = d.date()
        if isinstance(d, date):
            days.append(d)
    return max(days) if days else None


def fetch_all_holdings(uw, snapshots, max_holdings: int = 10, max_workers: int = 8) -> dict[str, list[dict]]:
    """Top holdings (with SPY-relative RS) for every theme ticker.

    Used to embed holdings into the exported rotation map so it is self-contained
    (no live server round-trip needed to expand a row). The holdings come from the spine's lists
    (``etf_holdings.stored_holdings``, #642); an ETF with none gets none. Sector rows expand to the
    sector -> industry tree (``sector_etf_trees``) instead, so their ETF holdings are not priced (ROT-4).

    The RS reads the prices store (M-ROT-3, PR 9): one ``rcdata.read.ticker_bars`` read of SPY and every holding up
    to the rotation session; ``uw`` (and ``max_workers``) are kept for the callers' signature and not used. A holding
    with no stored bars shows "n/a" (``holdings_rs_rows``). ``{}`` when SPY is short in the store.
    """
    from RevenueChaser.core import calendar
    from .etf_holdings import stored_holdings

    tickers = [s.ticker for s in snapshots if getattr(s, "group_name", "") == "theme"]
    held = {t: h for t in tickers if (h := stored_holdings(t))}
    if not held:
        return {}
    as_of = _session_of(snapshots)
    if as_of is None:
        try:
            as_of = calendar.latest_complete_session()
        except ValueError:
            return {}
    wanted = sorted({h.get("ticker") for rows in held.values() for h in rows if h.get("ticker")} - {"SPY"})
    points = bar_points(["SPY", *wanted], as_of - timedelta(days=HOLDINGS_READ_DAYS), as_of)
    spy = points.get("SPY", [])
    if len(spy) < SPY_MIN_CLOSES:                       # no RS this run: the caller keeps what it stored
        logger.warning("holdings RS: the prices store holds %d SPY sessions up to %s, need %d", len(spy), as_of,
                       SPY_MIN_CLOSES)
        return {}
    out: dict[str, list[dict]] = {}
    for t, rows in held.items():
        if got := holdings_rs_rows(rows, points, spy, as_of, max_holdings):
            out[t] = got
    return out


def _safe_float(v) -> float:
    try:
        return float(v)
    except (ValueError, TypeError):
        return 0.0


def classify_rrg(ratio_z: float, momentum_z: float) -> str:
    if ratio_z >= 0 and momentum_z >= 0:
        return "LEADING"
    if ratio_z >= 0 and momentum_z < 0:
        return "WEAKENING"
    if ratio_z < 0 and momentum_z >= 0:
        return "IMPROVING"
    return "LAGGING"


def classify_quadrant(rs_ratio: float, rs_momentum: float) -> str:
    """Strict RRG quadrant classification on Z-scores (Ratio Z, Momentum Z)."""
    return classify_rrg(rs_ratio, rs_momentum)


# ── the hysteresis band (#597, item 1) ────────────────────────────────────────────────────────────────────────────
# A dot sitting on an axis flipped quadrant every week: |z| of 0.02 one week and -0.02 the next is noise, not a
# rotation. With the band an axis KEEPS the side it is on until the value crosses 100 by more than ``QUADRANT_BAND``,
# so a flip needs a real move. The band is in A1 units: ``z`` is a deviation over its own 52-week standard deviation
# (``_scaled``), so 1.0 is a whole standard deviation — the 1.0 of the old proposal was on the retired pooled-z
# axis and is not this scale.
#
# 0.5 is measured, not guessed: ``early_turn.band_scan`` over 156 weeks (2023-11-26 to 2026-11-15) and 97 tickers
# rebuilt from the prices store (homesrv, 20 Nov 2026, read-only) gives, per band, the one-week round trips a dot
# makes and the mean weeks it stays in a quadrant:
#
#     band   round trips   mean weeks in quadrant
#     0.0        1,135            3.03
#     0.25         318            4.31
#     0.5           77            5.37
#     1.0           10            7.69
#
# No band takes the round trips to zero, so "the smallest band that zeroes them" has no answer. 0.5 removes 93% of
# them and leaves the mean stay at about a calendar month, which is the scale an RRG is read on; 0.25 leaves a round
# trip per ticker per year, which is the flip this issue is about, and 1.0 more than doubles the stay and starts
# hiding real rotations (#597).
QUADRANT_BAND = 0.5

_RATIO_HIGH = ("LEADING", "WEAKENING")          # quadrants whose ratio side is "right of 100"
_MOMENTUM_HIGH = ("LEADING", "IMPROVING")       # quadrants whose momentum side is "above 100"


def classify_sticky(ratio_z: float, momentum_z: float, previous: str = "", band: float = QUADRANT_BAND) -> str:
    """The quadrant of ``(ratio_z, momentum_z)`` given the ``previous`` quadrant, with the hysteresis band (#597).

    Each axis is judged on its own: an axis the ``previous`` quadrant had on the high side stays high until the value
    falls to ``-band`` or below; one it had on the low side stays low until the value reaches ``+band``. Without a
    ``previous`` quadrant (the first week of a series) or with ``band <= 0`` this is exactly ``classify_rrg``.
    """
    if not previous or band <= 0:
        return classify_rrg(ratio_z, momentum_z)
    ratio_high = ratio_z > -band if previous in _RATIO_HIGH else ratio_z >= band
    momentum_high = momentum_z > -band if previous in _MOMENTUM_HIGH else momentum_z >= band
    if ratio_high:
        return "LEADING" if momentum_high else "WEAKENING"
    return "IMPROVING" if momentum_high else "LAGGING"


def quadrant_path(points, band: float = QUADRANT_BAND) -> list[str]:
    """The quadrant of every week of ``points`` (``jdk_series`` output: ``(ratio, momentum)`` around 100, ``None``
    where the history is too short), walked oldest to newest through the band.

    Pure, and a function of the closes alone: the live Fetch and the backfill of the same session walk the same path
    from the same weekly closes and agree on the quadrant (D-M3), which reading the last stored snapshot would not.
    A gap (``None``) gets ``""`` and keeps the quadrant memory, so one missing week does not reset the band.
    """
    out: list[str] = []
    previous = ""
    for p in points:
        if p is None:
            out.append("")
            continue
        previous = classify_sticky(p[0] - 100, p[1] - 100, previous, band)
        out.append(previous)
    return out


# ── the RRG cross-section from the stored bars (M-ROT-2, #374; model A1, avo 17 Nov 2026) ──────────────────────────
# A1: every ETF is scored against its OWN history (JdK-style), not against the other ETFs, on completed ISO weeks:
#   rel   = ln(ETF / SPY)                       dev   = rel - mean(rel over the last TREND_WEEKS)
#   ratio = 100 + dev / std(dev, last SCALE_WEEKS)        roc = ratio - ratio ROC_WEEKS before
#   mom   = 100 + roc / std(roc, last SCALE_WEEKS)        quadrant by the 100/100 cross
# so adding or removing an ETF never moves another ETF's dot (the old pooled z did).
TREND_WEEKS = 14
ROC_WEEKS = 4
SCALE_WEEKS = 52
MIN_SCALE = 26                    # a std over fewer points is too noisy to scale by
# weekly closes an ETF (and SPY) needs for a first point: trend, MIN_SCALE devs, the roc, MIN_SCALE rocs
MIN_WEEKS = (TREND_WEEKS - 1) + (MIN_SCALE - 1) + ROC_WEEKS + (MIN_SCALE - 1) + 1
# read enough that both 52-week scales are full, so a live Fetch and a backfill of the same session agree
READ_WEEKS = (TREND_WEEKS - 1) + (SCALE_WEEKS - 1) + ROC_WEEKS + (SCALE_WEEKS - 1) + 1 + 8


def week_cut(as_of: date) -> date:
    """The last day whose ISO week is complete at ``as_of``: ``as_of`` itself when it is the last session of its week,
    else the Sunday before its week (A1: completed weeks only, so a Tuesday never moves the map half a week)."""
    from RevenueChaser.core import calendar
    try:
        nxt = calendar.next_trading_day(as_of)
    except ValueError:                          # outside the holiday table: weekdays
        nxt = as_of + timedelta(days=3 if as_of.weekday() == 4 else 1)
    if tuple(nxt.isocalendar())[:2] != tuple(as_of.isocalendar())[:2]:
        return as_of
    return as_of - timedelta(days=as_of.weekday() + 1)


def _weekly(points, as_of: date) -> dict[tuple, float]:
    """``{(ISO year, ISO week): close}``, oldest first, from ``(session, close)`` daily points up to ``as_of``."""
    weeks: dict[tuple, float] = {}
    for d, close in sorted(points, key=lambda p: p[0]):
        if d > as_of or not _finite(close):
            continue
        weeks[tuple(d.isocalendar())[:2]] = float(close)      # dict order = week order; the last session wins
    return weeks


def weekly_closes(points, as_of: date) -> list[float]:
    """Completed ISO-week closes, oldest first, from ``(session, close)`` daily points: each week's last session up
    to ``week_cut(as_of)``."""
    return list(_weekly(points, week_cut(as_of)).values())


def weekly_week_keys(points, as_of: date) -> list[tuple]:
    """The ISO ``(year, week)`` of each close ``weekly_closes`` returns, in the same order, so a caller can name the
    weeks a series is on."""
    return list(_weekly(points, week_cut(as_of)))


def aligned_weekly_closes(points, benchmark_points, as_of: date, carry_weeks: int = 0) -> list[float]:
    """``weekly_closes`` of one symbol lined up with the benchmark's completed ISO weeks, so the lookbacks (counted
    from the end of both lists) compare the same weeks.

    ``[]`` when the symbol has no close in the benchmark's last ``carry_weeks + 1`` weeks: a series that stopped early
    is not plotted as of the session (it is missing). A benchmark week the symbol lacks in between, or one of its last
    ``carry_weeks``, carries its previous week's close (a 0% week) instead of shifting every older week by one
    (review 2026-10-16)."""
    cut = week_cut(as_of)
    own = _weekly(points, cut)
    weeks = list(_weekly(benchmark_points, cut))
    if not own or not weeks or not any(w in own for w in weeks[-(carry_weeks + 1):]):
        return []
    out, last = [], None
    for w in weeks:
        last = own.get(w, last)
        if last is not None:
            out.append(last)
    return out


def bar_points(tickers, start: date, end: date) -> dict[str, list[tuple[date, float]]]:
    """``{ticker: [(session, close), ...]}`` from one prices-store read (``rcdata.read.ticker_bars``, total-return
    basis, C1: a high-dividend ETF is not read as lagging for paying out); never fetches. A ticker the store holds no
    bar of in the window is absent."""
    from RevenueChaser.rcdata import read
    frame = read.ticker_bars(list(tickers), start=start, end=end, basis="total_return")
    out: dict[str, list[tuple[date, float]]] = {}
    if frame is None or frame.empty:
        return out
    for t, d, c in zip(frame["ticker"], frame["session_date"], frame["close"]):
        if _finite(c):
            out.setdefault(str(t), []).append((d.date() if hasattr(d, "date") else d, float(c)))
    return out


def macro_points(start: date, end: date, tickers=None) -> dict[str, list[tuple[date, float]]]:
    """``{macro symbol: [(day, value), ...]}`` from one ``market_series`` read (PR 9): each symbol's own row
    (``MACRO_SERIES[...]["series"]``: FRED's yields and oil, Cboe's VVIX, Yahoo's MOVE and wheat). A symbol with no
    row in the window is absent; nothing is fetched (the market build stores the series)."""
    from RevenueChaser.rcdata import read
    wanted = {t: tuple(MACRO_SERIES[t]["series"]) for t in (tickers if tickers is not None else MACRO_SERIES)
              if (MACRO_SERIES.get(t) or {}).get("series")}
    if not wanted:
        return {}
    of = {v: t for t, v in wanted.items()}
    out: dict[str, list[tuple[date, float]]] = {}
    for r in read.market_series(sorted({sid for sid, _ in wanted.values()}), start=start, end=end):
        t = of.get((r["series_id"], r["source"]))
        if t is not None and _finite(r.get("value")):
            out.setdefault(t, []).append((r["obs_date"], float(r["value"])))
    return out


def rrg_tickers() -> list[str]:
    """The RRG symbols: every rotation ETF but the benchmark and the macro series (B1: macro is a strip, not a dot)."""
    return [t for t in rotation_reference.rotation_etfs() if t != "SPY" and t not in MACRO_SERIES]


def too_short(closes: dict[str, list[float]]) -> list[str]:
    """Symbols with some weekly closes but fewer than ``MIN_WEEKS``, in universe order: a warning, not a failure."""
    return [t for t in rotation_reference.rotation_etfs() if 0 < len(closes.get(t) or []) < MIN_WEEKS]


def _scaled(values: list, i: int):
    """``values[i]`` over the std of the last ``SCALE_WEEKS`` values up to ``i``; ``None`` under ``MIN_SCALE`` of them."""
    win = [v for v in values[max(0, i - SCALE_WEEKS + 1):i + 1] if v is not None]
    if values[i] is None or len(win) < MIN_SCALE:
        return None
    sd = float(np.std(win))
    return values[i] / sd if sd > 0 else None


def jdk_series(closes: list[float], spy_closes: list[float]) -> list[tuple[float, float] | None]:
    """The A1 ``(ratio, momentum)`` of every week of ``closes`` against ``spy_closes`` (both oldest first, lined up
    from the end), ``None`` where the history is too short. Pure."""
    n = min(len(closes), len(spy_closes))
    a, b = closes[len(closes) - n:], spy_closes[len(spy_closes) - n:]
    rel = [math.log(x / y) if x and y and x > 0 and y > 0 else None for x, y in zip(a, b)]
    dev: list = [None] * n
    for i in range(TREND_WEEKS - 1, n):
        win = rel[i - TREND_WEEKS + 1:i + 1]
        if None not in win:
            dev[i] = rel[i] - sum(win) / TREND_WEEKS
    ratio = [None if (z := _scaled(dev, i)) is None else 100 + z for i in range(n)]
    roc = [ratio[i] - ratio[i - ROC_WEEKS] if i >= ROC_WEEKS and ratio[i] is not None
           and ratio[i - ROC_WEEKS] is not None else None for i in range(n)]
    mom = [None if (z := _scaled(roc, i)) is None else 100 + z for i in range(n)]
    return [None if r is None or m is None else (r, m) for r, m in zip(ratio, mom)]


def cross_section(closes: dict[str, list[float]], spy_closes: list[float], as_of: date) -> list[ETFRotationSnapshot]:
    """The RRG of ``as_of``: one snapshot per RRG symbol of ``closes`` with at least ``MIN_WEEKS`` completed weekly
    closes. ``rs_ratio`` / ``rs_momentum`` are the A1 values around 100 (``jdk_series``); ``rs_ratio_z`` /
    ``rs_momentum_z`` are the same values less 100, the map's axes, and the quadrant is their signs read through the
    hysteresis band (``quadrant_path``, #597): a dot on an axis keeps its quadrant until it crosses by more than
    ``QUADRANT_BAND``. ``rs_1w`` /
    ``rs_1m`` / ``rs_3m`` are the plain excess returns over SPY across ``LOOKBACKS`` weeks.

    The one function the live Fetch and the backfill share (D-M3): the same closes give the same rows.
    """
    snaps = []
    for ticker, info in rotation_reference.rotation_etfs().items():
        series = closes.get(ticker) or []
        if ticker == "SPY" or ticker in MACRO_SERIES or len(series) < MIN_WEEKS:
            continue
        path = jdk_series(series, spy_closes)
        point = path[-1]
        if point is None:
            continue
        ratio, mom = round(point[0], 3), round(point[1], 3)
        rz, mz = round(ratio - 100, 3), round(mom - 100, 3)
        quadrant = quadrant_path(path)[-1]
        snaps.append(ETFRotationSnapshot(
            as_of_date=as_of, ticker=ticker, group_name=info.get("group", ""), close_price=series[-1],
            rs_1w=relative_strength_pct(series, spy_closes, LOOKBACKS["rs_1w"]),
            rs_1m=relative_strength_pct(series, spy_closes, LOOKBACKS["rs_1m"]),
            rs_3m=relative_strength_pct(series, spy_closes, LOOKBACKS["rs_3m"]),
            rs_ratio=ratio, rs_momentum=mom, rs_ratio_z=rz, rs_momentum_z=mz, rrg_quadrant=quadrant))
    return snaps


# ── B1: the macro table under the map (avo 17 Nov 2026) ───────────────────────────────────────────────────────────
# Only series that compare with each other share a block: the rates in basis points, the rest in percent. MOVE and
# VVIX are volatility, read by their 1-year percentile, in a block of their own.
MACRO_BLOCKS = (
    ("Rates", ("US02Y", "US05Y", "US10Y", "US20Y", "US30Y", "US10Y-US02Y", "USIRYY", "HY_OAS", "IG_OAS")),
    ("Commodities", ("CL1!", "WHEATF")),
    ("Volatility", ("MOVE", "VVIX")),
)
_BP = {"Rates"}
_CHG_DAYS = (("1w", 5), ("4w", 21), ("13w", 63))


def macro_table(as_of: date) -> list[dict]:
    """One row per macro series with a stored value up to ``as_of``, in ``MACRO_BLOCKS`` order: the last value and
    its day, the change over ~1/4/13 weeks of observations (basis points for a rate, percent otherwise), the 1-year
    percentile of the last value, and up to 65 values for a sparkline. Read-only (``market_series``); never fetches."""
    tickers = [t for _, ts in MACRO_BLOCKS for t in ts]
    pts = macro_points(as_of - timedelta(days=400), as_of, tickers)
    out = []
    for block, ts in MACRO_BLOCKS:
        for t in ts:
            obs = sorted(pts.get(t) or [])
            if not obs:
                continue
            vals = [v for _, v in obs]
            last = vals[-1]
            row = {"ticker": t, "block": block, "name": (rotation_reference.rotation_etfs().get(t) or MACRO_SERIES[t]).get("name", t),
                   "last": round(last, 3), "last_date": str(obs[-1][0]), "unit": "bp" if block in _BP else "%"}
            for key, n in _CHG_DAYS:
                b = vals[-1 - n] if len(vals) > n else None
                row[f"chg_{key}"] = (None if b is None else round(100 * (last - b), 1) if block in _BP
                                     else None if not b else round(100 * (last / b - 1), 1))
            yr = vals[-252:]
            row["pct_1y"] = round(100 * sum(v <= last for v in yr) / len(yr))
            row["spark"] = [round(v, 3) for v in vals[-65:]]
            out.append(row)
    return out


class RotationEngine:
    """The RRG pull (PR 9; A1): completed weekly total-return closes of the ETFs from the prices store, lined up with
    SPY's weeks, one ``cross_section`` dated by the session its closes end on. The macro series are not on the map (B1,
    ``macro_table``). Nothing is fetched: a Fetch and a Refresh of the same stores give the same map.

    After ``process_all``:
    - ``as_of`` is that session: the latest complete session, or SPY's last stored session before it when the prices
      build has not stored it yet (``stale`` then says so);
    - ``intraday`` is true when the run happened while the US session was open (rule B, ``calendar.session_for``);
    - ``too_short`` lists the symbols left off the map for having under ``MIN_WEEKS`` weekly closes (a warning).
    ``uw`` is not called for closes any more; it is kept for the callers that pass one.
    """

    def __init__(self, uw: UWClient = None, benchmark: str = "SPY", now: datetime | None = None):
        self.uw = uw
        self.benchmark = benchmark
        self.now = now
        self.spy_closes: list[float] = []
        self.snapshots: list[ETFRotationSnapshot] = []
        self.as_of: date | None = None
        self.stale: str | None = None
        self.intraday = False
        self.too_short: list[str] = []

    def process_all(self) -> list[ETFRotationSnapshot]:
        from RevenueChaser.core import calendar
        self.snapshots, self.too_short, self.stale = [], [], None
        try:
            session = calendar.latest_complete_session(self.now)
            self.intraday = calendar.session_for(
                self.now or calendar._now()).quality == calendar.QUALITY_INTRADAY
        except ValueError as exc:                       # outside the holiday table: no session to date it by
            logger.warning("Rotation: no session for this run: %s", exc)
            return []
        start = session - timedelta(weeks=READ_WEEKS)
        points = bar_points([self.benchmark, *rrg_tickers()], start, session)
        spy = points.get(self.benchmark) or []
        if not spy:
            logger.warning("Rotation: the prices store holds no %s bar up to %s", self.benchmark, session)
            return []
        self.as_of = spy[-1][0]
        if self.as_of < session:
            self.stale = (f"the prices store has no {self.benchmark} bar of the {session.isoformat()} session yet "
                          f"(the prices build has not stored it); the RRG is as of {self.as_of.isoformat()}")
        self.spy_closes = weekly_closes(spy, self.as_of)
        if len(self.spy_closes) < MIN_WEEKS:
            logger.warning("Rotation: %s has %d weekly closes in the prices store, need %d",
                           self.benchmark, len(self.spy_closes), MIN_WEEKS)
            return []
        closes = {t: aligned_weekly_closes(points.get(t) or [], spy, self.as_of) for t in rrg_tickers()}
        self.too_short = too_short(closes)
        self.snapshots = cross_section(closes, self.spy_closes, self.as_of)
        return self.snapshots


def ticker_rotation_adjustment(
    quadrant: str,
    rotation_score: float = 50,
    flow_score: float = 50,
) -> tuple[int, float]:
    if quadrant == "LEADING" and flow_score >= 60:
        return 10, 1.00
    if quadrant == "IMPROVING" and flow_score >= 60:
        return 5, 0.75
    if quadrant == "WEAKENING":
        return -5, 0.60
    if quadrant == "LAGGING" and flow_score < 40:
        return -10, 0.50
    return 0, 0.75


QUADRANT_ORDER = {"LEADING": 0, "IMPROVING": 1, "WEAKENING": 2, "LAGGING": 3}


def get_quadrant_for_ticker(ticker: str, weights: dict[str, list[tuple[str, float]]],
                            snapshots_map: dict[str, str], sector: str = "") -> tuple[str, str]:
    """``(quadrant, basis)`` of a company. The quadrant most of its map-fund weight sits in, basis ``"funds"``:
    ``weights`` is ``etf_holdings.ticker_weights()``, its share of each map fund that holds it; no typed pairs (plan
    v5 7e, avo's D); a tie goes to the better quadrant (``QUADRANT_ORDER``). When no map fund with a quadrant holds
    it, the quadrant of its own sector's fund (``sector`` is the spine's sector name), basis ``"sector XLY"``, so the
    board can mark it (avo, 18 Nov 2026: 347 of 455 calendar names were empty without it). ``("", "")`` when
    neither gives one."""
    votes: dict[str, float] = {}
    for etf, weight in weights.get(ticker, ()):
        q = snapshots_map.get(etf, "")
        if q:
            votes[q] = votes.get(q, 0.0) + weight
    if votes:
        return min(votes, key=lambda q: (-votes[q], QUADRANT_ORDER.get(q, 9))), "funds"
    etf = rotation_reference.sector_etf().get(sector, "")
    q = snapshots_map.get(etf, "")
    return (q, f"sector {etf}") if q else ("", "")


def rotation_quadrant_map(uw: UWClient = None, compute: bool = True,
                          as_of: date = None, benchmark: str = "SPY") -> dict[str, str]:
    """Earnings Radar's Sector Rotation dependency — same-session freshness policy.

    Returns ``{ETF ticker: quadrant}`` for ``as_of`` (default: the latest complete session, #283). A stored
    snapshot for that session is reused — the Sector Rotation board or an earlier run already refreshed it. When none
    exists and ``compute=True`` the engine runs once (stored closes, no call) and persists its snapshot under the
    session its closes end on, so Earnings Radar and the Sector Rotation board agree on the same read; a run that is
    not a complete session (intraday, or the store short of the session) never replaces a snapshot stored for that
    day.
    With ``compute=False`` only the store is read (zero network).
    """
    from RevenueChaser.core import calendar
    from . import store as rotation_store
    d = as_of or calendar.latest_complete_session()
    rows = (rotation_store.load_snapshot(d) or {}).get("etfs") or []
    if rows:
        return _quadrants(rows)
    if not compute:
        return {}
    engine = RotationEngine(uw, benchmark=benchmark)
    snapshots = engine.process_all()
    if not snapshots:
        return {}
    day = getattr(snapshots[0], "as_of_date", None) or d
    stored = (rotation_store.load_snapshot(day) or {}).get("etfs") or [] if day != d else []
    if stored and (getattr(engine, "stale", None) or getattr(engine, "intraday", False)):
        return _quadrants(stored)
    rotation_store.save_snapshot(snapshots, as_of=day, benchmark=benchmark)
    logger.info("Rotation: computed + persisted the %s snapshot (%d ETFs)", day.isoformat(), len(snapshots))
    return {s.ticker: s.rrg_quadrant for s in snapshots if s.rrg_quadrant}


def _quadrants(rows: list[dict]) -> dict[str, str]:
    return {r.get("ticker"): r.get("quadrant") for r in rows if r.get("ticker") and r.get("quadrant")}
