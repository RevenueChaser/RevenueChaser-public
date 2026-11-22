"""Sector Rotation's ETF holdings: the spine's whole lists (``funds/etf_holdings``), read through ``rcdata.read``.

The board fetches no holdings itself any more (#642 PR 5): the UW and yfinance fallback chain and the "holdings"
job that ran it are gone, and the spine's build is the one writer.
"""
from __future__ import annotations

import logging

from revenuechaser.core import datahealth
from revenuechaser.core.datahealth import Health

logger = logging.getLogger(__name__)


def synced_etfs() -> list[str]:
    """The ETFs the board shows holdings for: every sector and theme ETF of the Rotation universe."""
    from revenuechaser.core import rotation_reference
    return [t for t, info in rotation_reference.rotation_etfs().items() if info.get("group") in ("sector", "theme")]


def stored_holdings(ticker: str) -> list[dict]:
    """An ETF's holdings (``ticker``, ``name``, ``weight``, ``provider``, ``as_of``, ``truncated``), largest first,
    from the spine's whole lists (``rcdata.read.etf_holdings``, its newest day; #642 PR 4: the holdings job's
    ``raw.etf_holdings`` is no longer read). A line with no US ticker is left out.

    **A fund the daily issuer or UW list does not hold reads its newest Form N-PORT report instead**
    (``read.etf_holdings_nport``, ``provider`` ``nport``, quarterly; #354 C5, and the source every fund without an
    issuer file is read from since avo's D3 of 22 Nov 2026). Each row says which source served it, so a caller
    never has to guess whether a list is today's or last quarter's: ``provider`` and ``as_of`` of the day it came
    from, and ``truncated`` True for a UW list cut at UW's 250-line cap. ``[]`` only when neither source holds the
    fund (no network either way)."""
    from revenuechaser.rcdata import read
    rows = read.etf_holdings([ticker]) or read.etf_holdings_nport([ticker])
    return [{"ticker": r["ticker"], "name": r.get("name") or "", "weight": r.get("weight"),
             "provider": r.get("provider"), "as_of": r.get("as_of"), "truncated": bool(r.get("truncated"))}
            for r in rows if r.get("ticker")]


# The map funds whose holdings say where a company sits: a broad style, region, bond or yield fund holds
# everything, so it would outvote the sector and theme funds (plan v5 7e).
WEIGHT_GROUPS = ("sector", "theme", "industry")


def ticker_weights() -> dict[str, list[tuple[str, float]]]:
    """``{ticker: [(etf, share), ...]}``, largest share first: each company's share of every sector, theme and
    industry map fund that holds it, from the fund's newest holdings in the spine (``rcdata.read.etf_holdings``),
    or, for a fund the daily file does not hold, from its newest N-PORT report (``read.etf_holdings_nport``).
    The share is the line's weight over the sum of that fund's weights, so a fund published in percent and one in
    fractions compare. A line with no ticker or no weight is left out. A map fund with no weighted line is named in
    a warning and gives nothing: it is missing data, never weight 0."""
    from revenuechaser.rcdata import read
    from revenuechaser.core import rotation_reference
    funds = [t for t, info in rotation_reference.rotation_etfs().items() if info.get("group") in WEIGHT_GROUPS]
    by_fund: dict[str, dict[str, float]] = {}

    def take(rows):
        for r in rows:
            if r.get("ticker") and (r.get("weight") or 0) > 0:
                lines = by_fund.setdefault(r["etf"], {})
                lines[r["ticker"]] = lines.get(r["ticker"], 0.0) + float(r["weight"])
    take(read.etf_holdings(funds))
    # A map fund the daily file does not hold (avo adds funds on the Watch lists board; PEJ, VNQ, XTL, #1063)
    # reads its newest N-PORT report: quarterly, but sourced, and better than not counting the fund.
    take(read.etf_holdings_nport(sorted(set(funds) - set(by_fund))))
    missing = sorted(set(funds) - set(by_fund))
    if missing:
        logger.warning("rotation weights: %d map fund(s) have no weighted holdings: %s", len(missing), ", ".join(missing))
    out: dict[str, list[tuple[str, float]]] = {}
    for etf in sorted(by_fund):
        total = sum(by_fund[etf].values())
        for ticker, weight in by_fund[etf].items():
            out.setdefault(ticker, []).append((etf, weight / total))
    for pairs in out.values():
        pairs.sort(key=lambda p: (-p[1], p[0]))
    return out


@datahealth.scoped
def health_summary() -> dict:
    """What Data Health says about the board's holdings: the spine's lists, no network.

    ``lines`` counts the lines read; ``newest_session`` is the newest ``as_of`` among them, ``in_newest`` the ETFs
    on it; ``providers`` the provider of every ETF's list; ``missing`` the board's ETFs with no line in the spine;
    ``rs_stored`` the theme ETFs with stored RS rows (``rotation_holdings``, which the Rotation Fetch writes)."""
    from revenuechaser.rcdata import read
    from revenuechaser.core import rotation_reference

    from . import store_reads as sr
    expected = synced_etfs()
    lines = read.etf_holdings(expected)
    rows = {r["etf"]: r for r in lines}                 # one per ETF: all of an ETF's lines share as_of and provider
    sessions = {t: r["as_of"] for t, r in rows.items() if r.get("as_of") is not None}
    newest = max(sessions.values()) if sessions else None
    providers: dict[str, int] = {}
    for r in rows.values():
        if r.get("provider"):
            providers[r["provider"]] = providers.get(r["provider"], 0) + 1
    themes = [t for t, info in rotation_reference.rotation_etfs().items() if info.get("group") == "theme"]
    with_rs = sr.etfs_with_holdings()
    return {
        "expected": len(expected),
        "lines": len(lines),
        "stored": sum(1 for t in expected if t in rows),
        "newest_session": newest.isoformat() if newest else None,
        "in_newest": sum(1 for t in expected if newest is not None and sessions.get(t) == newest),
        "providers": providers,
        "missing": sorted(t for t in expected if t not in rows),
        "themes": len(themes),
        "rs_stored": sum(1 for t in themes if t in with_rs),
    }


def health() -> Health:
    """The numbers :func:`health_summary` reports, typed (#124 S4).

    ``covered`` is the ETFs with stored holdings against the ``expected`` sector and theme ETFs;
    ``source_share`` is the provider of each stored list as a share of the stored lists (a list stored without a
    provider is in no numerator, so the shares can sum below 1). ``newest`` is the newest spine day;
    the summary reads no calendar, so it has no ``expected_as_of``.
    """
    n = health_summary()
    stored = n["stored"]
    return Health(
        covered=stored,
        expected=n["expected"],
        newest=n["newest_session"],
        expected_as_of=None,
        source_share={p: c / stored for p, c in n["providers"].items()} if stored else None,
    )
