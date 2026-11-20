"""The early-turn rule and its score against the stored history (#597, item 2).

The early turn is the bottom-fishing signature on the A1 axes: momentum above 100 for three weeks running while the
ratio is still below 100, i.e. the dot is climbing the left half of the map. The board marks it with a ``⚡`` chip.
This module holds

* the **rule** as one pure function (``is_early_turn``), which the board calls, so the chip and the score can never
  measure two different rules, and
* the **score**: how often a flag is followed by the predicted quadrant (LEADING) within ``HORIZON_WEEKS``, as a hit
  rate and as a Brier score against the base rate of the same pool (``brier``).

Everything here is pure: the caller passes the stored snapshot rows (``store.load_range``), nothing is read or
fetched. The measurement runs on **weekly** points: the A1 values only move when a week closes, so two stored
sessions of the same ISO week carry the same point and the last session of each week stands for it.

Known gap, not fixed here: the board reads the two prior *stored snapshots* (``report._previous_momentum``) while
the score reads the two prior *weeks*. When snapshots are stored daily those are the same week's point three times,
so the board's chip is easier to meet than the rule the score measures. The rule is #1021's; what the score says
about it belongs in #597's follow-up, not in a second rule here.
"""
from __future__ import annotations

from datetime import date

from . import engine

# Weeks of momentum above 100 the rule wants before the flagged week itself.
PRIOR_WEEKS = 2

# Weeks a flag is given to be followed by LEADING. 8 weeks ~ two months: long enough for a ratio to cross, short
# enough that the flag is saying something about now.
HORIZON_WEEKS = 8

# The quadrant an early turn predicts.
PREDICTED = "LEADING"


def is_early_turn(ratio_z, momentum_z, prior_momentum_z) -> bool:
    """``True`` for the early-turn signature: momentum above 100 now and on each of the ``PRIOR_WEEKS`` weeks before
    (``prior_momentum_z``, oldest first) while the ratio is still below 100.

    ``False`` when a value is missing or fewer than ``PRIOR_WEEKS`` prior weeks are known — the rule is never read as
    met by absence.
    """
    priors = list(prior_momentum_z or ())
    if ratio_z is None or momentum_z is None or len(priors) < PRIOR_WEEKS:
        return False
    return (momentum_z > 0 and ratio_z < 0
            and all(p is not None and p > 0 for p in priors[-PRIOR_WEEKS:]))


def completed_week(day: date) -> str:
    """The completed ISO week a stored session stands for, as the Sunday that ends it.

    A session is dated by the last week complete at it (``engine.week_cut``), so a Wednesday's snapshot carries the
    week before its own — exactly what ``cross_section`` computed it from. Two sessions that stand for one week
    (a Friday and the Wednesday after it) give the same Sunday, while a Wednesday and the Friday of its own week
    give different ones, because they are different completed weeks.
    """
    year, week = tuple(engine.week_cut(day).isocalendar())[:2]
    return date.fromisocalendar(year, week, 7).isoformat()


def weekly_points(by_day: dict) -> tuple[list[str], dict[str, list]]:
    """``(weeks, {ticker: points})`` from ``store.load_range`` rows.

    ``weeks`` are the completed weeks the stored sessions stand for (``completed_week``: the Sunday ending each),
    oldest first; ``points[ticker]`` has one entry per week: ``(ratio, momentum)`` around 100 (the stored axes plus
    100) or ``None`` for a week the ticker has no stored row of. The last stored session of a week wins — they carry
    the same completed-week point, and the later one is the one a re-Fetch rewrote.
    """
    weekly: dict[str, dict[str, dict]] = {}
    for day in sorted(by_day):
        wk = completed_week(date.fromisoformat(day))
        for row in by_day[day]:
            if row.get("ticker"):
                weekly.setdefault(wk, {})[row["ticker"]] = row
    weeks = sorted(weekly)
    tickers = sorted({t for rows in weekly.values() for t in rows})
    points: dict[str, list] = {}
    for t in tickers:
        series = []
        for wk in weeks:
            row = weekly[wk].get(t) or {}
            rz, mz = row.get("rs_ratio_z"), row.get("rs_momentum_z")
            series.append(None if rz is None or mz is None else (100 + rz, 100 + mz))
        points[t] = series
    return weeks, points


def points_from_prices(as_of: date, weeks: int = 156, benchmark: str = "SPY") -> tuple[list[str], dict[str, list]]:
    """``(weeks, {ticker: points})`` like ``weekly_points``, rebuilt from the **prices store** instead of the stored
    snapshots: every RRG ticker's A1 path over the completed weeks up to ``as_of``, through the same
    ``engine.jdk_series`` the board computes its dot with.

    Reads the prices store once (``engine.bar_points``) and writes nothing, so the band and the score can be
    measured over years of weeks without waiting for snapshots to accumulate and without a live write. A week is
    named by the Sunday that ends it, as ``completed_week`` names a stored session's. A ticker whose series starts
    later than the benchmark's is padded at the front with gaps, so every series lines up with the weeks returned;
    one with under ``engine.MIN_WEEKS`` weekly closes is left out, as it is left off the map.
    """
    from datetime import timedelta
    pts = engine.bar_points([benchmark, *engine.rrg_tickers()],
                            as_of - timedelta(weeks=weeks + engine.READ_WEEKS), as_of)
    bench = pts.get(benchmark) or []
    benchmark_weekly = engine.weekly_closes(bench, as_of)
    if len(benchmark_weekly) < engine.MIN_WEEKS:
        return [], {}
    labels = [date.fromisocalendar(y, w, 7).isoformat() for y, w in engine.weekly_week_keys(bench, as_of)]
    out: dict[str, list] = {}
    for ticker in engine.rrg_tickers():
        closes = engine.aligned_weekly_closes(pts.get(ticker) or [], bench, as_of)
        if len(closes) < engine.MIN_WEEKS:
            continue
        series = engine.jdk_series(closes, benchmark_weekly)
        series = [None] * (len(labels) - len(series)) + series       # line the start up with the benchmark's weeks
        out[ticker] = series[-weeks:]
    return labels[-weeks:], out


def flagged_weeks(series: list, band: float | None = None) -> list[bool]:
    """``is_early_turn`` for every week of one ticker's ``weekly_points`` series. ``band`` is unused by the rule and
    accepted so a caller can pass the one it scores with."""
    out = []
    for i, p in enumerate(series):
        if p is None:
            out.append(False)
            continue
        priors = [None if q is None else q[1] - 100 for q in series[max(0, i - PRIOR_WEEKS):i]]
        out.append(is_early_turn(p[0] - 100, p[1] - 100, priors))
    return out


def _outcome(path: list[str], i: int, horizon: int) -> bool:
    """Did the ticker reach ``PREDICTED`` in the ``horizon`` weeks after week ``i``?"""
    return any(q == PREDICTED for q in path[i + 1:i + 1 + horizon])


def _mean(values) -> float | None:
    values = list(values)
    return sum(values) / len(values) if values else None


def brier(by_day: dict | None = None, horizon_weeks: int = HORIZON_WEEKS, band: float | None = None,
          *, weekly: tuple | None = None) -> dict:
    """Score the early-turn flag on the stored snapshots: a hit rate and a Brier score.

    The pool is every (week, ticker) point whose ratio is below 100 (the half of the map the flag picks from), whose
    ``PRIOR_WEEKS`` prior weeks are stored (so the rule can be read either way), and which has ``horizon_weeks`` of
    weeks after it (so the outcome is known). The outcome is the ticker reaching ``PREDICTED`` within those weeks, on
    the same banded path the board shows (``engine.quadrant_path`` with ``band``, default ``engine.QUADRANT_BAND``).

    Returns counts and, when there is a flag to score, ``hit_rate``; ``brier`` = the Brier score of reading the flag
    as "it will happen" (= 1 - hit_rate); ``base_rate`` = the share of the whole pool that reached ``PREDICTED``;
    ``brier_base`` = the Brier score of forecasting that base rate on the same flagged weeks; and ``skill`` = how
    much better than the base rate the flag is (above 0 = better, 0 = no better, below 0 = worse). ``flags_pending``
    counts flags whose horizon has not run out yet — they are left out of the score, never counted as misses.

    ``weekly`` is a ``(weeks, points)`` pair from ``weekly_points`` or ``points_from_prices``, scored instead of
    ``by_day``: the stored snapshots are three weeks long (measured on homesrv, 20 Nov 2026), far too short for an
    8-week horizon, while the prices store holds years.
    """
    band = engine.QUADRANT_BAND if band is None else band
    weeks, points = weekly if weekly is not None else weekly_points(by_day or {})
    pool: list[tuple[str, str, bool, bool]] = []            # (week, ticker, flagged, outcome)
    pending = 0
    for ticker, series in points.items():
        path = engine.quadrant_path(series, band)
        flags = flagged_weeks(series, band)
        for i, p in enumerate(series):
            if p is None or p[0] - 100 >= 0:
                continue
            priors = series[max(0, i - PRIOR_WEEKS):i]
            if len(priors) < PRIOR_WEEKS or any(q is None for q in priors):
                continue
            if i + horizon_weeks >= len(series):            # the outcome window is not complete yet
                pending += 1 if flags[i] else 0
                continue
            pool.append((weeks[i], ticker, flags[i], _outcome(path, i, horizon_weeks)))

    hits = [o for _, _, f, o in pool if f]
    base_rate = _mean(1.0 if o else 0.0 for _, _, _, o in pool)
    hit_rate = _mean(1.0 if o else 0.0 for o in hits)
    score = None if hit_rate is None else round(1 - hit_rate, 4)
    base_score = (None if base_rate is None or not hits
                  else _mean((base_rate - (1.0 if o else 0.0)) ** 2 for o in hits))
    out = {
        "horizon_weeks": horizon_weeks,
        "band": band,
        "predicted": PREDICTED,
        "weeks": len(weeks),
        "first_week": weeks[0] if weeks else None,
        "last_week": weeks[-1] if weeks else None,
        "pool": len(pool),
        "flags": len(hits),
        "flags_pending": pending,
        "hits": sum(1 for o in hits if o),
        "hit_rate": None if hit_rate is None else round(hit_rate, 4),
        "brier": score,
        "base_rate": None if base_rate is None else round(base_rate, 4),
        "brier_base": None if base_score is None else round(base_score, 4),
        "skill": None if not base_score or score is None else round(1 - score / base_score, 4),
    }
    return out


def caption(result: dict) -> str:
    """One line for the board's Early Turn card, or ``""`` when nothing scores yet.

    Each number stands next to the one it is fair to read it against: the hit rate against the pool's base rate,
    and the flag's Brier against the Brier of forecasting that base rate. Printing the Brier (0.36 as measured)
    beside the base *rate* (0.48) read as though the flag beat it, which is backwards — a lower Brier is better and
    those two are not the same quantity (review on PR #1151, 20 Nov 2026).
    """
    if not result or not result.get("flags"):
        return ""
    bits = [f"{result['hits']}/{result['flags']} reached {result['predicted'].title()} "
            f"within {result['horizon_weeks']}w"]
    if result.get("hit_rate") is not None and result.get("base_rate") is not None:
        bits.append(f"hit {result['hit_rate']:.0%} vs base {result['base_rate']:.0%}")
    if result.get("brier") is not None:
        against = result.get("brier_base")
        bits.append(f"Brier {result['brier']:.2f}" + (f" vs {against:.2f}" if against is not None else ""))
    return " · ".join(bits)


# ── the band measurement (#597, item 1) ───────────────────────────────────────────────────────────────────────────
BAND_CANDIDATES = (0.0, 0.1, 0.15, 0.2, 0.25, 0.3, 0.5, 1.0)


def band_scan(by_day: dict | None = None, bands=BAND_CANDIDATES, *, weekly: tuple | None = None) -> list[dict]:
    """Per candidate band, read off the stored snapshots: how many weekly quadrant changes the map would have had,
    how many of those are **one-week round trips** (a quadrant left for a single week and taken again — the flip a
    band is there to remove), and the mean number of weeks a ticker stays in one quadrant.

    This is the table #597 asks the band to be re-measured on: the band to keep is the smallest one that takes the
    round trips away without stretching the mean stay much. Pure; the caller passes ``store.load_range`` rows, or a
    ``weekly`` ``(weeks, points)`` pair (``points_from_prices``) when the stored snapshots are too few to say.
    """
    weeks, points = weekly if weekly is not None else weekly_points(by_day or {})
    rows = []
    for band in bands:
        changes = round_trips = runs = run_weeks = 0
        for series in points.values():
            path = [q for q in engine.quadrant_path(series, band) if q]
            if not path:
                continue
            stays: list[list] = []                          # [[quadrant, weeks], ...] oldest first
            for q in path:
                if stays and stays[-1][0] == q:
                    stays[-1][1] += 1
                else:
                    stays.append([q, 1])
            changes += len(stays) - 1
            runs += len(stays)
            run_weeks += len(path)
            for i in range(1, len(stays) - 1):              # A -> B (one week) -> A: the dot came straight back
                if stays[i][1] == 1 and stays[i - 1][0] == stays[i + 1][0]:
                    round_trips += 1
        rows.append({"band": band, "changes": changes, "round_trips": round_trips,
                     "mean_weeks_in_quadrant": round(run_weeks / runs, 2) if runs else None,
                     "weeks": len(weeks), "tickers": len(points)})
    return rows
