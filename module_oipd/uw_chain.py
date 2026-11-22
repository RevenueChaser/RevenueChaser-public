"""Map Unusual Whales option-contract rows into the OIPD chain inputs.

The UW ``/option-contracts`` row is one contract: ``option_symbol`` (OCC),
``nbbo_bid``/``nbbo_ask``, ``last_price``, ``implied_volatility``,
``open_interest``, ``volume``, ``delta`` and ``last_tape_time``. This module
turns those into typed dicts, picks a sensible set of expiries from the
``/expiry-breakdown`` payload, and infers each expiry's forward from put-call
parity (the same convention OIPD uses — no dividend/borrow model required).
"""
from __future__ import annotations

import math
from datetime import date as _date

import numpy as np

from revenuechaser.core.config import to_float
from revenuechaser.core.options import parse_option_symbol

from . import opd_math


def dte(asof: str, expiry: str) -> int | None:
    """Whole days from ``asof`` to ``expiry`` (ISO strings); None when unparsable."""
    try:
        return (_date.fromisoformat(expiry) - _date.fromisoformat(asof)).days
    except (ValueError, TypeError):
        return None


def expiries_from_breakdown(rows: list[dict], asof: str,
                            min_dte: int, max_dte: int,
                            max_expiries: int) -> list[dict]:
    """Choose expiries to fetch: DTE in range, no 0DTE, highest OI first, capped.

    Returns ``[{expiry, dte, open_interest, volume, chains}]`` sorted by DTE.
    """
    picked: list[dict] = []
    for r in rows or []:
        # UW sends ``expires`` (the spec says ``expiry``): rcdata/build/options/rows.py ``expiry_of``.
        exp = str(r.get("expiry") or r.get("expires") or "")[:10]
        d = dte(asof, exp)
        if d is None or d < min_dte or d > max_dte:
            continue
        picked.append({
            "expiry": exp, "dte": d,
            "open_interest": to_float(r.get("open_interest")) or 0.0,
            "volume": to_float(r.get("volume")) or 0.0,
            "chains": int(to_float(r.get("chains")) or 0),
        })
    # Highest open interest wins when there are more expiries than the cap.
    picked.sort(key=lambda x: (-x["open_interest"], x["dte"]))
    picked = picked[:max_expiries]
    picked.sort(key=lambda x: x["dte"])
    return picked


def mid_price(bid: float | None, ask: float | None,
              last: float | None) -> float | None:
    """NBBO mid when both sides are live, else the last traded price."""
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return (bid + ask) / 2.0
    if last is not None and last > 0:
        return last
    return None


def map_rows(rows: list[dict]) -> list[dict]:
    """Normalise UW contract rows; unparsable symbols and unpriced rows drop out."""
    out: list[dict] = []
    for r in rows or []:
        sym = parse_option_symbol(r.get("option_symbol") or "")
        if sym is None:
            continue
        bid = to_float(r.get("nbbo_bid"))
        ask = to_float(r.get("nbbo_ask"))
        last = to_float(r.get("last_price"))
        mid = mid_price(bid, ask, last)
        out.append({
            "option_symbol": r.get("option_symbol"),
            "root": sym["root"],
            "expiry": sym["expiry"],
            "option_type": sym["type"],
            "strike": sym["strike"],
            "bid": bid, "ask": ask, "last_price": last, "mid": mid,
            "iv": to_float(r.get("implied_volatility")),
            "open_interest": to_float(r.get("open_interest")),
            "volume": to_float(r.get("volume")),
            "delta": to_float(r.get("delta")),
            "tape_time": r.get("last_tape_time"),
        })
    return out


def infer_forward(contracts: list[dict], T: float, r: float, spot: float,
                  window: float = 0.20) -> float:
    """Forward from put-call parity: ``F = K + e^{rT}(C - P)``.

    Uses the median over near-the-money strikes (both legs quoted), falling back
    to ``spot * e^{rT}`` when too few pairs are available.
    """
    calls = {c["strike"]: c["mid"] for c in contracts
             if c["option_type"] == "C" and c.get("mid")}
    puts = {p["strike"]: p["mid"] for p in contracts
            if p["option_type"] == "P" and p.get("mid")}
    strikes = calls.keys() & puts.keys()
    disc_inv = math.exp(r * T)
    implied = [k + disc_inv * (calls[k] - puts[k]) for k in strikes]
    if spot and spot > 0:
        near = [k + disc_inv * (calls[k] - puts[k]) for k in strikes
                if abs(k / spot - 1.0) <= window]
        if len(near) >= 3:
            return float(np.median(near))
    if len(implied) >= 3:
        return float(np.median(implied))
    return float(spot * disc_inv) if spot and spot > 0 else float("nan")


def two_sided(c: dict) -> bool:
    """A live NBBO on both sides that is not crossed."""
    bid, ask = c.get("bid"), c.get("ask")
    return bid is not None and ask is not None and bid > 0 and ask >= bid


def rel_spread(c: dict) -> float:
    """``(ask - bid) / mid`` of a two-sided quote."""
    return (c["ask"] - c["bid"]) / ((c["ask"] + c["bid"]) / 2.0)


def fit_inputs(contracts: list[dict], F: float, max_rel_spread: float) -> list[dict]:
    """The contracts the smile is fitted on (review N3, N4; avo's D1, 18 Nov 2026): a two-sided quote within the
    relative-spread cap, and only the out-of-the-money leg of each strike (calls at ``K >= F``, puts below), so
    every strike counts once and the deep in-the-money leg, whose time value drowns in its spread, stays out."""
    return [c for c in contracts
            if c["strike"] > 0 and two_sided(c) and rel_spread(c) <= max_rel_spread
            and (c["option_type"] == "C") == (c["strike"] >= F)]


def one_root(contracts: list[dict]) -> tuple[list[dict], list[str]]:
    """One option root per expiry (review N10): SPX (AM-settled monthlies) and SPXW (PM-settled) share a date but are
    different contracts. The root with the most contracts stays; returns ``(kept, dropped roots)``."""
    roots: dict[str, int] = {}
    for c in contracts:
        roots[c.get("root") or ""] = roots.get(c.get("root") or "", 0) + 1
    if len(roots) < 2:
        return contracts, []
    keep = max(sorted(roots), key=lambda r: roots[r])
    return [c for c in contracts if (c.get("root") or "") == keep], sorted(r for r in roots if r != keep)


def contract_iv(c: dict, F: float, T: float, r: float) -> float | None:
    """IV for one contract, solved from its mid; None when it does not solve.

    No vendor-IV fallback (review N4): the surface is a function of *prices* (the OIPD convention), never of the
    vendor's own IV methodology.
    """
    if not c.get("mid"):
        return None
    solved = opd_math.implied_vol_black76(F, c["strike"], T, r, c["mid"], c["option_type"])
    return solved if solved is not None and 0.0 < solved < 5.0 else None
