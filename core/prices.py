"""Daily price bars: the read API and the pure helpers (#156).

The reads read the builder's ``prices.duckdb`` (``rcdata/build/prices/serving.py``), whose ``price_bars_daily`` and
``price_actions`` views keep the old names and columns (the bridge D4). Splits and dividends are rows of
``price_actions`` and are applied on read by :func:`daily_bars` (R2). There is no fallback: no served file reads as no
rows, and ``source_state()["reason"]`` says why. The old writers (the nightly, the attended fill, the watermarks and
their Data Health row) went with the old ``.store/prices.duckdb`` (#860).
"""
from __future__ import annotations

import logging
import math
from datetime import date, datetime, timedelta

import duckdb
import numpy as np
import pandas as pd

from RevenueChaser.core import calendar

logger = logging.getLogger(__name__)

BENCHMARKS = ("SPY", "DIA", "QQQ")
CALENDAR_START = date(2025, 1, 1)

_BAR_COLUMNS = ["ticker", "session_date", "open", "high", "low", "close", "volume", "source"]
_YF_FIELDS = ("Open", "High", "Low", "Close", "Adj Close", "Volume",
              "Dividends", "Stock Splits", "Capital Gains")


# ── small helpers ────────────────────────────────────────────────────────────


def _f(v):
    """A finite float, else None (a string number, NaN and None all become None)."""
    if v is None:
        return None
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(x) or math.isinf(x) else x


def _threshold(ex_date: date) -> datetime:
    """``ex_date`` at 09:30 New York: the split's ex-date open (R6)."""
    return datetime.combine(ex_date, calendar.SESSION_OPEN, tzinfo=calendar.NY)


def _threshold_epoch(ex_date: date) -> float:
    return _threshold(ex_date).timestamp()


def _placeholders(n: int) -> str:
    return ", ".join("?" for _ in range(n))


# ── scope ────────────────────────────────────────────────────────────────────


def _norm(tickers) -> list[str]:
    """Upper-case, strip, de-duplicate, benchmarks first."""
    out: list[str] = []
    seen: set[str] = set()
    if isinstance(tickers, str):            # one ticker, not its characters
        tickers = [tickers]
    # An index level (^GSPC, ^VIX) is never a bar here (#293 stores index levels): only the
    # fill's reference download names one, and it never writes it.
    values = [v for v in (str(t).strip().upper() for t in (tickers or [])) if not v.startswith("^")]
    for b in BENCHMARKS:
        if b in values and b not in seen:
            seen.add(b)
            out.append(b)
    for t in values:
        if t and t not in seen:
            seen.add(t)
            out.append(t)
    return out


# ── pure helpers (no store, no network) ──────────────────────────────────────

def sessions_behind(last: date | None, latest: date) -> int | None:
    """Trading days in ``(last, latest]``; ``None`` when ``last`` predates the calendar."""
    if last is None or last < CALENDAR_START:
        return None
    n = 0
    d = last + timedelta(days=1)
    while d <= latest:
        if calendar.is_trading_day(d):
            n += 1
        d += timedelta(days=1)
    return n


class _EventRows(list):
    """A list of bar rows that also carries ``attrs`` (``skipped_events``)."""

    def __init__(self, *args, attrs: dict | None = None):
        super().__init__(*args)
        self.attrs = attrs or {}


# ── the event engine (K8a speed, #383): numpy over every bar of every ticker at once ────────────────────────
# Each factor is a left fold in the actions' list order, ``acc = op(acc, v)`` for every event whose condition holds,
# exactly as the per-row loop did it (k *= r, a' /= r, m *= f), so the floats are bit-identical, not merely close:
# the loop runs over the event position j (a ticker's 0th, 1st, ... event) and is vectorised over the items.

def _group_index(groups: np.ndarray, n_groups: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """``(order, first, count)``: a stable sort of the items by group (list order kept within a group), and each
    group's first position and size in that order."""
    order = np.argsort(groups, kind="stable")
    count = np.bincount(groups, minlength=n_groups)
    return order, np.cumsum(count) - count, count


def _fold(acc: np.ndarray, owner: np.ndarray, first: np.ndarray, count: np.ndarray, values: np.ndarray,
          cond, op) -> np.ndarray:
    """``acc[i] = op(acc[i], values[j])`` over the events ``j`` of item ``i``'s group, in list order, where
    ``cond(i, j)``. ``first``/``count`` index the events by group (from :func:`_group_index`)."""
    n_ev = count[owner]
    for j in range(int(n_ev.max(initial=0))):
        items = np.flatnonzero(n_ev > j)
        evs = first[owner[items]] + j
        hit = cond(items, evs)
        items, evs = items[hit], evs[hit]
        acc[items] = op(acc[items], values[evs])
    return acc


def _event_factors(g: np.ndarray, d: np.ndarray, fetched: np.ndarray, close: np.ndarray, close_null: np.ndarray,
                   n_groups: int, splits: tuple, amounts: tuple | None
                   ) -> tuple[np.ndarray, np.ndarray | None, int]:
    """``(k, m, skipped)`` per bar: the split divisor ``k`` and, when ``amounts`` is given, the amount multiplier.

    - ``g``/``d``: each bar's group and day number, sorted by ``(g, d)`` with ties in list order; ``fetched`` its
      fetched_at (None as 0); ``close``/``close_null`` the stored close and where it is None.
    - ``splits``: ``(group, ex_day, T(e) epoch, ratio)`` and ``amounts``: ``(group, ex_day, fetched_at, value)``,
      each in the actions' list order and already filtered to a usable value.
    """
    sg, s_ex, s_thr, s_val = splits
    s_ord, s_first, s_count = _group_index(sg, n_groups)
    s_ex, s_thr, s_val = s_ex[s_ord], s_thr[s_ord], s_val[s_ord]
    k = _fold(np.ones(len(g)), g, s_first, s_count, s_val,
              lambda i, j: (d[i] < s_ex[j]) & (fetched[i] < s_thr[j]), np.multiply)
    if amounts is None:
        return k, None, 0
    ag, a_ex, a_fetched, a_val = amounts
    if not len(ag):
        return k, np.ones(len(g)), 0
    if not len(g):
        return k, np.ones(0), len(ag)                      # no bar: every amount lacks C_prev
    base = int(d.min()) - 1                                # a bar's offset is in [1, width - 2]
    width = int(d.max()) - base + 2
    bar_key = g * width + (d - base)

    def key(groups, days):
        return groups * width + np.clip(days - base, 0, width - 1)

    # C_prev: the nominal close of the group's last bar before the ex-date (the last of equal dates, as the loop)
    pos = np.searchsorted(bar_key, key(ag, a_ex), side="left") - 1
    at = np.clip(pos, 0, None)
    has = (pos >= 0) & (g[at] == ag) & ~close_null[at]
    with np.errstate(all="ignore"):
        c_prev = close[at] / k[at]
        a_prime = _fold(a_val.copy(), ag, s_first, s_count, s_val,
                        lambda i, j: (a_ex[i] < s_ex[j]) & (a_fetched[i] < s_thr[j]), np.divide)
        m = 1.0 - a_prime / c_prev
        bad = ~has | (c_prev <= 0) | (m <= 0.0) | (m >= 1.0)
    keep = ~bad
    fg, fe, fm = ag[keep], a_ex[keep], m[keep]
    if not len(fg):
        return k, np.ones(len(g)), int(bad.sum())
    # A bar's multiplier depends only on how many of its group's distinct factor ex-dates are on or before it (its
    # segment), so the fold runs once per (group, segment), not once per bar.
    fkey = key(fg, fe)
    ukey = np.unique(fkey)
    u_count = np.bincount(ukey // width, minlength=n_groups)
    u_first = np.cumsum(u_count) - u_count
    rank = np.searchsorted(ukey, fkey) - u_first[fg]       # a factor applies to segment s while rank >= s
    p_count = u_count + 1
    p_first = np.cumsum(p_count) - p_count
    p_group = np.repeat(np.arange(n_groups), p_count)
    p_seg = np.arange(len(p_group)) - p_first[p_group]
    f_ord, f_first, f_count = _group_index(fg, n_groups)
    f_rank, f_m = rank[f_ord], fm[f_ord]
    per_seg = _fold(np.ones(len(p_group)), p_group, f_first, f_count, f_m,
                    lambda i, j: f_rank[j] >= p_seg[i], np.multiply)
    seg = np.searchsorted(ukey, bar_key, side="right") - u_first[g]
    return k, per_seg[p_first[g] + seg], int(bad.sum())


def _usable(actions, kinds: tuple[str, ...]) -> list[dict]:
    """The actions of ``kinds`` with a usable value, in list order."""
    return [a for a in actions if a.get("action") in kinds and _f(a.get("value"))]


def _split_arrays(splits: list[tuple[int, dict]]) -> tuple:
    return (np.array([gi for gi, _ in splits], dtype=np.int64),
            np.array([a["ex_date"].toordinal() for _, a in splits], dtype=np.int64),
            np.array([_threshold_epoch(a["ex_date"]) for _, a in splits], dtype=float),
            np.array([float(a["value"]) for _, a in splits], dtype=float))


def _amount_arrays(amounts: list[tuple[int, dict]]) -> tuple:
    return (np.array([gi for gi, _ in amounts], dtype=np.int64),
            np.array([a["ex_date"].toordinal() for _, a in amounts], dtype=np.int64),
            np.array([float(a.get("fetched_at") or 0.0) for _, a in amounts], dtype=float),
            np.array([float(a["value"]) for _, a in amounts], dtype=float))


def apply_events(bars: list[dict], actions: list[dict], basis: str) -> list[dict]:
    """The nominal or split/dividend-adjusted series of one ticker (R2/R6).

    - Nominal: OHLC ÷ ``k_i`` and volume × ``k_i``, ``k_i = Π r`` over splits with
      ``d_i < e`` and ``fetched_at_i < T(e)``.
    - Adjusted: nominal × ``Π m`` over dividends and capital gains with ``d_i < e``, where
      ``m = 1 − a'/C_prev``; ``a'`` divides the amount by each split that took effect after
      the amount was fetched. An event with no ``C_prev`` or ``m`` outside ``(0, 1)`` is
      skipped and counted in ``attrs['skipped_events']``. Volume is never dividend-adjusted.

    Computed by the vectorised engine (:func:`_event_factors`, #383 K8a speed): the same floats as the per-row
    formulas. The read path (:func:`daily_bars`) runs the engine over every ticker at once, not this per ticker.
    """
    if basis not in ("nominal", "adjusted"):
        raise ValueError(f"unknown basis {basis!r}")
    ordered = sorted(bars, key=lambda b: b["session_date"])
    fields = _FIELDS
    raw = {f: [b.get(f) for b in ordered] for f in fields}
    null = {f: [v is None for v in raw[f]] for f in fields}
    vals = {f: np.array([0.0 if v is None else v for v in raw[f]], dtype=float) for f in fields}
    d = np.array([b["session_date"].toordinal() for b in ordered], dtype=np.int64)
    fetched = np.array([float(b.get("fetched_at") or 0.0) for b in ordered], dtype=float)
    splits = _split_arrays([(0, a) for a in _usable(actions, ("split",))])
    amounts = (_amount_arrays([(0, a) for a in _usable(actions, _AMOUNTS)])
               if basis == "adjusted" else None)
    k, m, skipped = _event_factors(np.zeros(len(ordered), dtype=np.int64), d, fetched, vals["close"],
                                   np.array(null["close"], dtype=bool), 1, splits, amounts)
    nominal = {f: (vals[f] * k if f == "volume" else vals[f] / k) for f in fields}
    out = {f: (nominal[f] * m if m is not None and f != "volume" else nominal[f]).tolist() for f in fields}
    rows: list[dict] = []
    for i, b in enumerate(ordered):
        row = dict(b)
        for f in fields:
            row[f] = None if null[f][i] else out[f][i]
        row["split_ratio"] = None
        rows.append(row)
    return _EventRows(rows, attrs={"skipped_events": skipped})


# ── store reads ──────────────────────────────────────────────────────────────

LAYER = "layer"
SERVING_DATASET = "prices/serving"


def source_state() -> dict:
    """``{requested, effective, reason, variable}`` of the bars the boards read: always the builder's file since
    #642 PR 6 (the old-store switch is gone); ``reason`` says why that file gives no rows, if it does not
    (``rcdata.read.missing``)."""
    from ..rcdata import read
    return {"requested": LAYER, "effective": LAYER, "reason": read.missing("prices", SERVING_DATASET),
            "variable": None}


def _layer_read(sql: str, params: list | None, fetch):
    """``fetch(cursor)`` of ``sql`` on the served file. No file, or a missing view, reads as no rows
    (``fetch(None)``): a board says why with ``source_state()["reason"]``."""
    from ..rcdata import serving
    try:
        con = serving.open_read("prices")
    except serving.ServingFileMissing:
        return fetch(None)
    with con:
        try:
            return fetch(con.execute(sql, params or []))
        except duckdb.CatalogException:
            return fetch(None)


def _dicts(cur) -> list[dict]:
    if cur is None:
        return []
    cols = [d[0] for d in cur.description] if cur.description else []
    return [dict(zip(cols, row)) for row in cur.fetchall()]


def _read(sql: str, params: list | None = None, layer: bool = True) -> list[dict]:
    """A read of the served price views, with no fallback (#642 PR 6). ``layer`` is kept for the callers' keyword;
    the old store it once chose is gone (#860)."""
    return _layer_read(sql, params, _dicts)


_READ_COLUMNS = ("ticker", "session_date", "open", "high", "low", "close", "volume", "source", "fetched_at")
_AMOUNTS = ("dividend", "capital_gain")
_FIELDS = ("open", "high", "low", "close", "volume")
_EPOCH_ORDINAL = date(1970, 1, 1).toordinal()        # datetime64 day 0 as a date ordinal
# The session_date dtype a frame of stored dates gets (datetime64[s] on pandas 3), as the per-row read built it.
_DATE_DTYPE = pd.to_datetime(pd.Series([date(2000, 1, 3)], dtype=object)).dtype


def _read_columns(sql: str, params: list) -> dict[str, np.ndarray]:
    """A read of the price bars as numpy columns, NULLs masked (#383 K8a speed): the rows ``_read`` would return,
    without a Python dict per bar. The served file only (#642 PR 6): no file or no table reads as no rows."""
    return _layer_read(sql, params, lambda cur: {} if cur is None else cur.fetchnumpy())


def _plain(col) -> tuple[np.ndarray, np.ndarray]:
    """``(values, is_null)`` of a fetched column."""
    if isinstance(col, np.ma.MaskedArray):
        return np.ma.getdata(col), np.ma.getmaskarray(col)
    col = np.asarray(col)
    return col, np.zeros(len(col), dtype=bool)


def _columns_from_read(parts: list[dict]) -> dict[str, np.ndarray]:
    """The bar columns of one or more ``_read_columns`` results: ``ticker``, ``day`` (date ordinal), each field and
    ``<field>_null``, ``source`` (None where NULL) and ``fetched`` (``float(fetched_at or 0.0)``)."""
    parts = [p for p in parts if p and len(p["ticker"])]
    if not parts:
        return {}

    def joined(name):
        vals, nulls = zip(*(_plain(p[name]) for p in parts))
        return np.concatenate(vals), np.concatenate(nulls)

    out: dict[str, np.ndarray] = {"ticker": joined("ticker")[0].astype(object)}
    days, _ = joined("session_date")
    out["day"] = days.astype("datetime64[D]").astype(np.int64) + _EPOCH_ORDINAL
    for f in _FIELDS:
        vals, null = joined(f)
        out[f] = np.where(null, np.nan, vals.astype(float))
        out[f + "_null"] = null
    source, null = joined("source")
    out["source"] = np.where(null, None, source.astype(object))
    fetched, null = joined("fetched_at")
    out["fetched"] = np.where(null | (fetched == 0.0), 0.0, fetched.astype(float))
    return out


def _columns_from_rows(rows: list[dict]) -> dict[str, np.ndarray]:
    """The same columns from bar dicts (the ``_bars_frame`` and ``apply_events`` inputs)."""
    out: dict[str, np.ndarray] = {"ticker": np.array([r["ticker"] for r in rows], dtype=object),
                                  "day": np.array([r["session_date"].toordinal() for r in rows], dtype=np.int64)}
    for f in _FIELDS:
        raw = [r.get(f) for r in rows]
        out[f + "_null"] = np.array([v is None for v in raw], dtype=bool)
        out[f] = np.array(raw, dtype=float)
    out["source"] = np.array([r.get("source") for r in rows], dtype=object)
    out["fetched"] = np.array([float(r.get("fetched_at") or 0.0) for r in rows], dtype=float)
    return out


def _read_series(tickers: list[str], start: date | None = None, end: date | None = None, prev_closes: bool = True
                 ) -> tuple[dict[str, np.ndarray], dict[str, list[dict]]]:
    """Bar columns (:func:`_columns_from_read`) and actions of ``tickers``: every action, and the bars the read needs.

    - With ``start`` (K8a, #383 R3): the bars from ``start`` on plus each ticker's last bar before it, the previous
      close a dividend in the window needs.
    - With ``end`` (K8a speed, #383): no bar after ``end`` but each ticker's first one and, when ``prev_closes``, the
      one bar each dividend or capital gain ex after ``end`` takes its ``C_prev`` from. An event after ``end`` still
      adjusts every bar before it (both factors use ``d_i < e``), which is why the actions are never bounded: a
      split needs only its own row and the bar's fetched_at, an amount its ``C_prev`` bar.
    """
    actions: dict[str, list[dict]] = {}
    if not tickers:
        return {}, actions
    marks = _placeholders(len(tickers))
    # The served view keeps no row order; the factors' product is order-sensitive in its last bits, so fix one.
    for r in _read(f"SELECT * FROM price_actions WHERE ticker IN ({marks}) ORDER BY ticker, ex_date, action",
                   list(tickers), layer=True):
        actions.setdefault(r["ticker"], []).append(r)
    cols = ", ".join(f"b.{c}" for c in _READ_COLUMNS)
    where, params = [f"b.ticker IN ({marks})"], list(tickers)
    if start is not None:
        where.append("b.session_date >= COALESCE((SELECT MAX(p.session_date) FROM price_bars_daily p "
                     "WHERE p.ticker = b.ticker AND p.session_date < ?), ?)")
        params += [start, start]
    if end is not None:
        where.append("b.session_date <= ?")
        params.append(end)
    parts = [_read_columns(f"SELECT {cols} FROM price_bars_daily b WHERE {' AND '.join(where)}", params)]
    if end is not None:
        # Past end: each ticker's first bar (it has bars to adjust exactly when the unbounded read had: the skipped
        # count and an empty frame stay the same) and, for the adjusted basis, each C_prev bar.
        keys = [f"SELECT ticker, MIN(session_date) AS session_date FROM price_bars_daily WHERE ticker IN ({marks}) "
                f"AND session_date > ? GROUP BY ticker"]
        key_params = [*tickers, end]
        if prev_closes:
            keys.append(f"SELECT p.ticker, p.session_date FROM (SELECT DISTINCT ticker, ex_date FROM price_actions "
                        f"WHERE ticker IN ({marks}) AND action IN ('dividend', 'capital_gain') AND ex_date > ?) a "
                        f"ASOF JOIN price_bars_daily p ON a.ticker = p.ticker AND a.ex_date > p.session_date")
            key_params += [*tickers, end if start is None else max(start, end)]   # an amount ex <= start: unused
        parts.append(_read_columns(
            f"SELECT {cols} FROM price_bars_daily b JOIN (SELECT DISTINCT ticker, session_date FROM "
            f"({' UNION ALL '.join(keys)})) c ON b.ticker = c.ticker AND b.session_date = c.session_date "
            f"WHERE b.session_date > ?", [*key_params, end]))
    return _columns_from_read(parts), actions


# ── read API ─────────────────────────────────────────────────────────────────

def daily_bars(tickers, basis: str = "nominal", start: date | None = None,
               end: date | None = None) -> pd.DataFrame:
    """Stored bars for ``tickers``, sorted by ticker then date; never fetches.

    ``basis`` is ``nominal`` or ``adjusted`` (the R2 factor series). The factors are applied first and the rows
    only then filtered to ``[start, end]``. With ``start`` the read is a window (K8a, #383 R3): the bars from
    ``start`` on plus each ticker's last bar before it, and every action except one ex on or before ``start``
    (a split or an amount there divides or adjusts no bar in the window). With ``end`` no bar after ``end`` is
    read but the ``C_prev`` bars of the amounts after it (K8a speed, #383). The result equals the full read sliced;
    ``attrs['skipped_events']`` counts the events that touch the window.
    """
    if basis not in ("nominal", "adjusted"):
        raise ValueError(f"unknown basis {basis!r}")
    return daily_bars_bases(tickers, start, end, bases=(basis,))[basis]


def daily_bars_bases(tickers, start: date | None = None, end: date | None = None,
                     bases: tuple[str, ...] = ("nominal", "adjusted")) -> dict[str, pd.DataFrame]:
    """``{basis: daily_bars(tickers, basis, start, end)}`` from one read of the bars and one of the actions.

    The screeners need both bases of every scored name (levels nominal, returns adjusted; #383 R3 S3): one read
    serves both instead of one per basis.
    """
    for basis in bases:
        if basis not in ("nominal", "adjusted"):
            raise ValueError(f"unknown basis {basis!r}")
    names = _norm(tickers)
    if isinstance(start, datetime):
        start = start.date()
    last = None if end is None else pd.Timestamp(end).date()     # the bars are dates: <= end is <= its day
    cols, actions = (_read_series(names, start, last, prev_closes="adjusted" in bases) if names else ({}, {}))
    group = (pd.Index(names).get_indexer(cols["ticker"]) if cols else np.zeros(0, dtype=np.int64))
    return _frames(names, cols, group, actions, bases, start, end)


def _empty_bars(skipped: int = 0) -> pd.DataFrame:
    empty = pd.DataFrame(columns=_BAR_COLUMNS)
    empty.attrs["skipped_events"] = skipped
    return empty


def _bars_frame(names: list[str], bars: dict[str, list[dict]], actions: dict[str, list[dict]], basis: str,
                start: date | None, end: date | None) -> pd.DataFrame:
    """One basis of per-ticker bar dicts as ``daily_bars`` returns it."""
    present = [t for t in names if t in bars]
    rows = [r for t in present for r in bars[t]]
    group = np.repeat(np.arange(len(present), dtype=np.int64), [len(bars[t]) for t in present])
    cols = _columns_from_rows(rows) if rows else {}
    return _frames(present, cols, group, actions, (basis,), start, end)[basis]


def _frames(names: list[str], cols: dict[str, np.ndarray], group: np.ndarray, actions: dict[str, list[dict]],
            bases: tuple[str, ...], start: date | None, end: date | None) -> dict[str, pd.DataFrame]:
    """Each basis of the bar columns as ``daily_bars`` returns it: one engine pass over every ticker (#383).

    ``group`` is each bar's index in ``names``. The rows are laid out as the per-ticker code laid them out (``names``
    order, each ticker's bars by date, ties in read order), so the frame, its filters and its sort are the same.
    """
    if not len(group):
        return {basis: _empty_bars() for basis in bases}
    by_day = np.argsort(cols["day"], kind="stable")
    order = by_day[np.argsort(group[by_day], kind="stable")]
    g, d = group[order], cols["day"][order]
    vals = {f: cols[f][order] for f in _FIELDS}
    null = {f: cols[f + "_null"][order] for f in _FIELDS}
    splits: list[tuple[int, dict]] = []
    amounts: list[tuple[int, dict]] = []
    with_bars = np.bincount(group, minlength=len(names)) > 0
    for gi, t in enumerate(names):
        if not with_bars[gi]:
            continue                                               # a ticker with no bar: nothing to adjust
        acts = actions.get(t, [])
        if start is not None:
            acts = [a for a in acts if a["ex_date"] > start]      # one ex on or before start adjusts no bar here
        splits += [(gi, a) for a in _usable(acts, ("split",))]
        amounts += [(gi, a) for a in _usable(acts, _AMOUNTS)]
    k, m, skipped = _event_factors(g, d, cols["fetched"][order], vals["close"], null["close"], len(names),
                                   _split_arrays(splits),
                                   _amount_arrays(amounts) if "adjusted" in bases else None)
    nominal = {f: vals[f] * k if f == "volume" else vals[f] / k for f in _FIELDS}
    dates = (d - _EPOCH_ORDINAL).astype("datetime64[D]").astype(_DATE_DTYPE)
    ticker, source = cols["ticker"][order], cols["source"][order]
    out: dict[str, pd.DataFrame] = {}
    for basis in bases:
        values = nominal if basis == "nominal" else {f: nominal[f] * m if f != "volume" else nominal[f]
                                                     for f in _FIELDS}
        df = pd.DataFrame({"ticker": ticker, "session_date": dates,
                           **{f: _as_column(values[f], null[f]) for f in _FIELDS}, "source": source})
        if start is not None:
            df = df[df["session_date"] >= pd.Timestamp(start)]
        if end is not None:
            df = df[df["session_date"] <= pd.Timestamp(end)]
        df = df[_BAR_COLUMNS].sort_values(["ticker", "session_date"]).reset_index(drop=True)
        df.attrs["skipped_events"] = skipped if basis == "adjusted" else 0
        out[basis] = df
    return out


def _as_column(values: np.ndarray, null: np.ndarray):
    """A float column, or all None when every value is None (the dtype a frame of the per-row dicts had)."""
    return np.full(len(values), None, dtype=object) if null.all() else values


# ── Data Health ──────────────────────────────────────────────────────────────


# ── UW client access ─────────────────────────────────────────────────────────


# ── nightly ──────────────────────────────────────────────────────────────────


__all__ = ["BENCHMARKS", "daily_bars", "daily_bars_bases", "sessions_behind", "apply_events", "source_state"]
