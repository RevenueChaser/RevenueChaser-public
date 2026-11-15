"""Hit-rate readability (#25 HR-2): which frozen picks count, and whether a family's hit rate can be read yet.

The ledger (``forecast_ledger``), the outcomes (``forecast_outcomes``) and the baselines (``forecast_baselines``)
exist (HR-1). This module decides what a hit rate may be computed from, with the numbers decided in #25:

- **Dedupe:** a ticker picked again by the same family (``source``) within ``DEDUPE_DAYS`` of a pick that counts is
  the same bet, not a new one; the earliest pick is kept.
- **Dirty:** an outcome whose ``status`` is ``no_bars`` or ``split_check`` cannot be scored; it is listed, not counted.
- **Readable:** a family's hit rate is shown only with at least ``MIN_RECORDS`` closed records over at least
  ``MIN_DATES`` freeze dates, and never pooled across ``model_version`` (the pick's, from the ledger): a changed
  selection rule starts a new count.

Pure functions over rows, plus one read of the forecast board file (``load``). No write, no provider call.
"""
from __future__ import annotations

from datetime import date

from RevenueChaser.core import rawstore

MIN_RECORDS = 30
MIN_DATES = 3
DEDUPE_DAYS = 90
GE = (("ge20", 0.20), ("ge10", 0.10), ("ge5", 0.05))      # the buckets of ``core/baselines.py``, cumulative
CLOSED = "closed"
DIRTY = ("no_bars", "split_check")


def _day(value) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def dedupe(rows: list[dict]) -> list[dict]:
    """``rows`` without the repeats: per (source, model_version, horizon_days, subject), a pick within
    ``DEDUPE_DAYS`` after the last kept one is dropped. Order of the result: as kept, by forecast date."""
    kept, last = [], {}
    for r in sorted(rows, key=lambda r: _day(r["forecast_date"])):
        key = (r["source"], r.get("model_version"), r.get("horizon_days"), r["subject"])
        day = _day(r["forecast_date"])
        if key in last and (day - last[key]).days < DEDUPE_DAYS:
            continue
        last[key] = day
        kept.append(r)
    return kept


def summary(rows: list[dict]) -> list[dict]:
    """One row per (source, model_version, horizon_days): the closed, deduped records' count, freeze dates,
    ``readable``, the hit rates (``ge20``/``ge10``/``ge5`` as shares of ``n``, None while not readable), the mean
    MFE and MAE, and the dirty outcomes (``dirty``: count, ``dirty_subjects``: the first ten)."""
    groups: dict[tuple, dict] = {}
    for r in dedupe(rows):
        g = groups.setdefault((r["source"], r.get("model_version"), r.get("horizon_days")),
                              {"closed": [], "dirty": [], "open": 0})
        if r.get("status") == CLOSED and r.get("mfe") is not None:
            g["closed"].append(r)
        elif r.get("status") in DIRTY:
            g["dirty"].append(r)
        else:
            g["open"] += 1
    out = []
    for (source, version, horizon), g in sorted(groups.items(), key=lambda kv: tuple(str(k) for k in kv[0])):
        closed = g["closed"]
        n, dates = len(closed), len({_day(r["forecast_date"]) for r in closed})
        readable = n >= MIN_RECORDS and dates >= MIN_DATES
        row = {"source": source, "model_version": version, "horizon_days": horizon, "n": n, "dates": dates,
               "open": g["open"], "readable": readable, "dirty": len(g["dirty"]),
               "dirty_subjects": [r["subject"] for r in g["dirty"]][:10]}
        for name, cut in GE:
            row[name] = sum(1 for r in closed if r["mfe"] >= cut) / n if readable else None
        maes = [r["mae"] for r in closed if r.get("mae") is not None]
        row["mfe_mean"] = sum(r["mfe"] for r in closed) / n if readable else None
        row["mae_mean"] = sum(maes) / len(maes) if readable and maes else None
        out.append(row)
    return out


def load() -> list[dict]:
    """Every pick's outcome rows with the pick's own ``model_version`` (the ledger's, not the outcome rule's)."""
    return rawstore.query(
        "SELECT o.source, o.subject, o.forecast_date, o.horizon_days, o.mfe, o.mae, o.status, l.model_version "
        "FROM forecast_outcomes o JOIN forecast_ledger l USING (source, forecast_date, subject, target_type, "
        "target_date) WHERE o.target_type = 'pick'", [], db="forecast")
