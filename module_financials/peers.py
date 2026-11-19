"""Comps peers from the spine universe (#385 FIN-3) — no static list.

The ladder, one rung at a time, inside ``core.universe.classification_universe_rows`` (the same floor and the
same excluded-security-type rule every other board reads):

1. the spine's ``industry``, nearest market cap first;
2. widening to the spine's ``sector`` until there are ``k`` peers.

Both rungs keep only names inside ``PEER_CAP_RATIO_BAND`` of the target's market cap (#90), so a short ladder is
reported rather than filled with names of a different size; ``peer_set`` says which rung each peer came from (#91).

``sub_industry`` is not a rung: the identity master writes it (and ``industry_group``) NULL, so a name has
nothing to match on there. A target the universe does not carry (no market cap to measure "nearest" from), or
one whose industry and sector are exhausted, gets fewer peers than ``k`` or none — the caller says so in a
warning rather than substituting a list of its own.
"""
from __future__ import annotations

from .config import PEER_CAP_RATIO_BAND, PEER_K
from RevenueChaser.core.gics_map import UNCLASSIFIED, canonical_sector, is_unclassified


def _industry_key(row: dict) -> str:
    """The rung a name joins, ``""`` when it has no usable industry (never "all the blanks match")."""
    industry = (row.get("industry") or "").strip()
    return "" if not industry or is_unclassified(industry) else industry


def in_cap_band(target_cap: float, cap) -> bool:
    """Whether ``cap`` is inside ``PEER_CAP_RATIO_BAND`` of ``target_cap`` (#90).

    A name with no market cap is not in the band: there is nothing to compare, and "unknown" must not read as
    "close enough". A non-positive target cap has no ratio either, so nothing is in its band — ``target_row``
    already refuses a target without a cap, so that case does not reach a run.
    """
    c = cap if isinstance(cap, (int, float)) and not isinstance(cap, bool) else None
    if c is None or c <= 0 or target_cap <= 0:
        return False
    low, high = PEER_CAP_RATIO_BAND
    return low * target_cap <= c <= high * target_cap


def _nearest(target_cap: float, rows: list[dict], limit: int) -> list[dict]:
    """``limit`` rows at the closest market cap to ``target_cap``, inside the cap band only (#90).

    Ties keep the universe's own order (cap-descending), so a run is reproducible.
    """
    banded = [r for r in rows if in_cap_band(target_cap, r.get("market_cap"))]
    ranked = sorted(banded, key=lambda r: abs(r["market_cap"] - target_cap))
    return ranked[:limit]


def target_row(ticker: str, rows: list[dict]) -> dict | None:
    """The universe row the ladder starts from: ``ticker`` with a market cap, else None.

    The precondition of the whole ladder: a name the spine does not carry (below the market-cap floor, or an
    excluded security type) or one with no cap has no "nearest market cap" to rank peers from, so it gets no
    peer at all — and the caller says that, rather than reporting an exhausted industry.
    """
    wanted = (ticker or "").strip().upper()
    row = next((r for r in rows if r["ticker"] == wanted), None)
    return row if row is not None and row.get("market_cap") is not None else None


def peer_set(ticker: str, rows: list[dict], k: int = PEER_K) -> list[dict]:
    """The ``k`` peers of ``ticker`` as ``{"ticker", "market_cap", "rung"}``; the target is never one of them.

    ``rung`` is ``"industry"`` or ``"sector"``: the board says how many peers came from the sector instead of the
    target's own industry, because a sector peer is a weaker comp and no number on the page said so (#91).
    """
    wanted = (ticker or "").strip().upper()
    target = target_row(ticker, rows)
    if target is None:
        return []
    candidates = [r for r in rows if r["ticker"] != wanted]

    picked: list[dict] = []
    industry = _industry_key(target)
    if industry:
        picked = [{"ticker": r["ticker"], "market_cap": r.get("market_cap"), "rung": "industry"}
                  for r in _nearest(target["market_cap"],
                                    [r for r in candidates if _industry_key(r) == industry], k)]

    sector = canonical_sector(target.get("sector"))
    if len(picked) < k and sector != UNCLASSIFIED:
        taken = {r["ticker"] for r in picked}
        picked += [{"ticker": r["ticker"], "market_cap": r.get("market_cap"), "rung": "sector"}
                   for r in _nearest(target["market_cap"],
                                     [r for r in candidates
                                      if r["ticker"] not in taken and canonical_sector(r.get("sector")) == sector],
                                     k - len(picked))]
    return picked


def select_peers(ticker: str, rows: list[dict], k: int = PEER_K) -> list[str]:
    """The ``k`` peer tickers of ``ticker`` from the universe ``rows``; the target is never one of them."""
    return [p["ticker"] for p in peer_set(ticker, rows, k)]
