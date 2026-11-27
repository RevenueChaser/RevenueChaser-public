"""Gamma exposure from a chain we own (lane A of #1431): the profile without a vendor exposure payload.

``core/gex_profile.py`` reads UW's ready-made per-strike exposures. This module computes the same numbers
from a plain chain — strike, right, open interest, contract gamma and a spot — which is what IBKR gives us
after Unusual Whales ends on 6 December 2026.

**Measured, session 2026-11-20** (read-only, no new UW call; 65 names, 9,010 strike rows of the serving
store): UW's own ``call_gamma_oi`` / ``put_gamma_oi`` equal ``gamma * open_interest * spot ** 2`` exactly,
the put side carried negative — the dollar-gamma-per-1 %-move convention
``module_spx_gamma/dealer_book.py`` already uses (``oi * 100 * gamma * spot ** 2 * 0.01``). So the exposure
side of this module is parity with UW, not an approximation.

The three levels are **ours**. Fed UW's own per-strike exposures, UW's written wall and flip rules do not
reproduce UW's own ``gex-levels`` answer for the same session: call wall 3/65 exact, put wall 12/65, flip
0/65 (median error 31 % of spot). Side-only concentration comes closest — put wall 28/65 exact, median
error 0.62 % of spot; call wall 10/65, 5.74 % — so that is the rule here.
shortcut: UW's `gex-levels` numbers are not reproducible from any basis we hold, so these levels are our
own rule and not a reproduction; revisit only if a vendor level source replaces UW.

Every row given is summed, so an expiry window is the caller's filter, not an argument here.
"""
from __future__ import annotations

from .config import to_float
from .gex_profile import cumulative_crossings, nearest_crossing

CALL, PUT = "call", "put"


def strike_exposure(rows: list[dict], spot: float | None) -> list[dict]:
    """Per-strike dollar gamma exposure per 1 % move, in UW's signs: calls positive, puts negative.

    ``rows`` carry ``strike``, ``option_type`` (``call``/``put``), ``gamma`` and ``open_interest``
    (``option_eod``'s own column names). A row missing any of them is skipped, never counted as 0.
    """
    spot = to_float(spot)
    if not rows or not spot:
        return []
    agg: dict[float, dict] = {}
    for r in rows:
        strike = to_float(r.get("strike"))
        gamma = to_float(r.get("gamma"))
        oi = to_float(r.get("open_interest"))
        side = (r.get("option_type") or "").lower()
        if strike is None or gamma is None or oi is None or side not in (CALL, PUT):
            continue
        row = agg.setdefault(strike, {"strike": strike, "call": 0.0, "put": 0.0})
        row[side] += gamma * oi * spot * spot * (1.0 if side == CALL else -1.0)
    out = sorted(agg.values(), key=lambda r: r["strike"])
    for row in out:
        row["net"] = row["call"] + row["put"]
    return out


def chain_profile(rows: list[dict], spot: float | None) -> dict:
    """The exposure profile and its three levels; ``{}`` without usable rows or a spot.

    ``call_wall`` is the strike above spot with the largest call exposure, ``put_wall`` the strike below
    with the largest put exposure, and ``flip`` the zero crossing of cumulative net exposure nearest spot
    (``gex_profile``'s one crossing walk). A level with no strike on its side of spot stays ``None``.
    """
    strikes = strike_exposure(rows, spot)
    if not strikes:
        return {}
    spot = to_float(spot)
    above = [r for r in strikes if r["strike"] > spot]
    below = [r for r in strikes if r["strike"] < spot]
    crossings = cumulative_crossings([(r["strike"], r["net"]) for r in strikes])
    return {
        "strikes": strikes,
        "spot": spot,
        "call_wall": max(above, key=lambda r: r["call"])["strike"] if above else None,
        "put_wall": min(below, key=lambda r: r["put"])["strike"] if below else None,
        "flip": nearest_crossing(crossings, spot),
    }
