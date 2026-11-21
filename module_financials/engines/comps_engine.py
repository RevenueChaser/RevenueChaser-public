"""Comps Engine — rakip çarpanları (EV/EBITDA, EV/Revenue, P/E) + persentil + implied valuation."""
from __future__ import annotations

import logging
from typing import Callable

from ..config import to_float
from ._inputs import NO_MINORITY_BRIDGE, PE_ONLY_SECTOR, net_debt as _net_debt
from RevenueChaser.core.providers.validator import validate_annual

logger = logging.getLogger(__name__)


def _pct(vals: list[float]) -> dict[str, float]:
    if not vals:
        return {"p25": None, "p50": None, "p75": None, "count": 0}
    s = sorted(vals)
    n = len(s)
    def q(p: float) -> float:
        rank = (n - 1) * p
        lo = int(rank)
        hi = min(lo + 1, n - 1)
        w = rank - lo
        return s[lo] * (1 - w) + s[hi] * w
    return {"p25": q(0.25), "p50": q(0.50), "p75": q(0.75), "count": n}


def _default_fetch_many(peers: list[str]) -> dict[str, dict]:
    """Every peer's figures from the store, in one call (#286): ``store_reads.peer_multiples``.

    Until 20 Nov 2026 this was one Yahoo ``.info`` request **per peer**, taking ``enterpriseValue`` and
    ``ebitda`` straight off the payload. The store carries neither, so both are derived there (EBITDA =
    EBIT + D&A, EV = market cap + total debt − cash) and the multiples moved with it — avo's decision,
    "Store'dan türet". ``basis`` says which window the peer side is on, and a peer with nothing stored is
    marked rather than guessed at.
    """
    from .. import store_reads
    return store_reads.peer_multiples(peers)


# A multiple whose denominator was reported and is not positive is not meaningful: the cell reads NM and the
# value stays out of the percentile. 0 would read as a real multiple, and None as "not reported".
NM = "NM"

#: What the peer side's figures are, for the card's Basis line (#286). It names the two derived figures, because
#: neither is a number any provider published: a reader comparing this card with a vendor screen must see why
#: the multiples differ.
PEERS_SOURCE = "fundamentals store; EBITDA = EBIT + D&A, EV = market cap + total debt − cash"


def _multiple(numerator, denominator) -> float | str | None:
    """``numerator / denominator``, or ``NM`` for a non-positive denominator (missing inputs stay ``None``)."""
    if numerator is None or denominator is None:
        return None
    return NM if denominator <= 0 else numerator / denominator


def _measured(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def run_comps(financials: dict, peers: list[str],
              fetch_info: Callable[[str], dict] | None = None,
              rungs: dict[str, str] | None = None,
              fetch_many: Callable[[list[str]], dict] | None = None) -> dict:
    """Rakip çarpan analizi; fetch_info test için enjekte edilebilir.

    ``rungs`` maps a peer to the ladder rung it came from (``"industry"`` / ``"sector"``, ``peers.peer_set``), so
    the table can say which peers are not in the target's industry (#91); unknown for a peer list the caller typed.

    The peer figures come from the store in one call (#286, :func:`_default_fetch_many`). ``fetch_many`` replaces
    that call; ``fetch_info`` is the older per-peer seam and still answers one peer at a time where a test injects
    it.
    """
    infos = ({p: fetch_info(p) for p in peers} if fetch_info is not None
             else (fetch_many or _default_fetch_many)(peers))
    annual, warnings = validate_annual(financials.get("annual", []))
    if not annual:
        return {"error": "target financial data missing", "warnings": warnings}

    pe_only = financials.get("sector") == PE_ONLY_SECTOR

    latest = annual[-1]
    target_ebitda = to_float(latest.get("ebitda"))
    target_revenue = to_float(latest.get("revenue"))
    target_ni = to_float(latest.get("net_income"))
    target_debt = to_float(latest.get("total_debt"))
    target_cash = to_float(latest.get("cash"))
    target_shares = to_float(financials.get("shares_outstanding"))

    rows = []
    ev_ebitda, ev_rev, pe = [], [], []
    for p in peers:
        info = infos.get(p) or {"stored": False}
        ev = to_float(info.get("enterpriseValue"))
        ebitda = to_float(info.get("ebitda"))
        revenue = to_float(info.get("totalRevenue"))
        mc = to_float(info.get("marketCap"))
        ni = to_float(info.get("netIncomeToCommon"))
        pe_val = to_float(info.get("trailingPE"))
        if pe_val is None and mc is not None:
            pe_val = _multiple(mc, ni)
        if _measured(pe_val) and pe_val <= 0:
            pe_val = NM

        ev_eb = None if pe_only else _multiple(ev, ebitda)
        ev_r = None if pe_only else _multiple(ev, revenue)
        for bucket, value in ((ev_ebitda, ev_eb), (ev_rev, ev_r), (pe, pe_val)):
            if _measured(value):
                bucket.append(value)

        rows.append({
            "ticker": p,
            # Which rung of the ladder picked this peer (#91); None for a typed peer list.
            "rung": (rungs or {}).get(p),
            # #286: a peer the store holds no annual record for is marked, not blank — a blank row reads as
            # "the figures are missing", and this one is "we have never stored this company". Every multiple of
            # such a peer is None already, so it is out of each percentile by the same rule as any unknown.
            "stored": info.get("stored", True),
            "fiscal_year": info.get("fiscal_year"),
            "market_cap": mc,
            "enterprise_value": ev,
            "ev_ebitda": ev_eb,
            "ev_revenue": ev_r,
            "pe": pe_val,
        })

    def _implied(median_mult, target_metric, multiple: str, metric: str):
        """``median_mult * target_metric``, or None when the target's own metric is not positive.

        A peer multiple is a positive price per unit of EBITDA, revenue or earnings; the same multiple of a
        LOSS is a negative EV (or a negative per-share value — "Per Share $-1.04"), which is not a valuation.
        The run says which metric was not positive, once per implied value, so the board's N/A is explained.
        """
        if median_mult is None or target_metric is None:
            return None
        if target_metric <= 0:
            warnings.append(f"comps: implied {multiple} not computed — the target's {metric} is not positive")
            return None
        return median_mult * target_metric

    med_ev_ebitda = _pct(ev_ebitda)["p50"]
    med_ev_rev = _pct(ev_rev)["p50"]
    med_pe = _pct(pe)["p50"]

    implied_ev_ebitda = _implied(med_ev_ebitda, target_ebitda, "EV/EBITDA", "EBITDA")
    implied_ev_rev = _implied(med_ev_rev, target_revenue, "EV/Revenue", "revenue")
    implied_equity_pe = _implied(med_pe, target_ni, "P/E", "net income")

    net_debt = _net_debt(target_debt, target_cash)     # None when either is unknown
    if net_debt is not None and target_shares is not None:
        warnings.append(NO_MINORITY_BRIDGE)             # #92: the bridge subtracts net debt and nothing else

    def _per_share_ev(ev):
        if ev is None or net_debt is None or target_shares is None:
            return None
        return (ev - net_debt) / target_shares

    def _per_share_eq(eq):
        if eq is None or target_shares is None:
            return None
        return eq / target_shares

    return {
        "ticker": financials.get("ticker"),
        "warnings": warnings,
        # A Financial Services target is P/E only: the EV multiples are absent by design, not missing data.
        "pe_only": pe_only,
        # DF45: the two sides are on different bases, and the board says so (a label, no number moves).
        # #286: the peer side is the store's newest annual record, not Yahoo's trailing twelve months, and its
        # EBITDA and enterprise value are derived (``store_reads.peer_multiples``). ``peers_source`` lets a
        # stored result from before this change still render with its own label.
        "basis": {"peers": "newest stored fiscal year", "peers_source": PEERS_SOURCE,
                  "target_fiscal_year": latest.get("fiscal_year"),
                  "target_shares": (financials.get("market_meta") or {}).get("shares_source") or "Yahoo"},
        "peers": rows,
        "multiples": {
            "ev_ebitda": _pct(ev_ebitda),
            "ev_revenue": _pct(ev_rev),
            "pe": _pct(pe),
        },
        "implied": {
            "ev_ebitda": implied_ev_ebitda,
            "ev_revenue": implied_ev_rev,
            "equity_pe": implied_equity_pe,
            "per_share_ev_ebitda": _per_share_ev(implied_ev_ebitda),
            "per_share_ev_revenue": _per_share_ev(implied_ev_rev),
            "per_share_pe": _per_share_eq(implied_equity_pe),
            "net_debt": net_debt,
            # The fiscal year the net debt is as of (#92); the shares are the fetch's, see ``basis``.
            "net_debt_fy": latest.get("fiscal_year"),
        },
    }
