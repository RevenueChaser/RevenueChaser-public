"""HR-2 of #25: when a board's hit rate may be read, which records are dirty, and the 90-day dedupe.

Pure functions over the joined rows of ``forecast_ledger`` (picks) and ``forecast_outcomes`` (one row per pick and
horizon): ``source``, ``subject``, ``forecast_date``, ``model_version``, ``status``, ``mfe``. No store read here; the
Hit Rate board reads the rows and hands them in.

The decided numbers (#25, HR-2): a hit rate is readable from ``MIN_RECORDS`` closed records over at least
``MIN_DATES`` freeze dates; the same ticker picked again by the same board within ``DEDUPE_DAYS`` of a kept pick is
one record (the earliest is kept); records of different ``model_version`` are never pooled.
"""
from __future__ import annotations

from datetime import date

from revenuechaser.core import baselines, outcomes

MIN_RECORDS = 30
MIN_DATES = 3
DEDUPE_DAYS = 90
#: A record that is not final and cannot become final on its own: no bars in its window, or a split the store has
#: no action for. Listed, never counted.
DIRTY = (outcomes.NO_BARS, outcomes.SPLIT_CHECK)


def _day(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v)[:10])


def dedupe(rows: list[dict]) -> list[dict]:
    """The rows left after the 90-day rule: per (source, model_version, subject), a pick within ``DEDUPE_DAYS`` of
    the last *kept* pick is dropped, so a name held on a board for months counts once per 90 days, from its first."""
    kept: list[dict] = []
    last: dict[tuple, date] = {}
    for r in sorted(rows, key=lambda r: (_day(r["forecast_date"]), str(r["subject"]))):
        key = (r["source"], r.get("model_version"), r["subject"])
        day = _day(r["forecast_date"])
        if key in last and (day - last[key]).days < DEDUPE_DAYS:
            continue
        last[key] = day
        kept.append(r)
    return kept


def summary(rows: list[dict]) -> list[dict]:
    """One line per (source, model_version): the closed records after the dedupe, their freeze dates, whether the
    rate is readable, the share of closed records at each ``baselines.GE`` level of MFE (None when unreadable), and
    the dirty records, listed. Open records are counted apart: they are not final yet."""
    groups: dict[tuple, list[dict]] = {}
    for r in dedupe(rows):
        groups.setdefault((r["source"], r.get("model_version")), []).append(r)
    out = []
    for (source, version), rs in sorted(groups.items(), key=lambda kv: (str(kv[0][0]), str(kv[0][1]))):
        closed = [r for r in rs if r.get("status") == outcomes.CLOSED and r.get("mfe") is not None]
        dates = {_day(r["forecast_date"]) for r in closed}
        readable = len(closed) >= MIN_RECORDS and len(dates) >= MIN_DATES
        rates = {name: (sum(1 for r in closed if r["mfe"] >= level) / len(closed) if readable else None)
                 for name, level in baselines.GE}
        out.append({"source": source, "model_version": version, "records": len(closed), "dates": len(dates),
                    "readable": readable, **rates,
                    "open": sum(1 for r in rs if r.get("status") == outcomes.OPEN),
                    "dirty": [{"subject": r["subject"], "forecast_date": _day(r["forecast_date"]),
                               "status": r["status"]} for r in rs if r.get("status") in DIRTY]})
    return out
