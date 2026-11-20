"""Financials' reader of the peer side of the comps ladder (#286): no provider call, one shape per peer.

``peer_multiples`` is the board's ``fundamentals.peer_multiples`` need: a thin mapping over the fundamentals
serving layer and the prices serving layer (through ``core/spine_reads``), with no SQL of its own, in the shape of
``module_spx_gamma/store_reads.py`` and ``module_earnings_radar/stored_inputs.py``. A peer the store holds no row
for comes back as a ``stored: False`` marker, never as a live read: there is no provider fallback here.

**The two derived figures, and why they are derived.** The comps ladder used to read Yahoo's ``.info`` once per
peer and take ``enterpriseValue`` and ``ebitda`` straight off it. The fundamentals store carries neither, so both
are built from what it does carry (avo's decision of 20 Nov 2026, "Store'dan türet"):

* **EBITDA** = ``ebit + depreciation`` of the peer's newest stored annual record. Yahoo's own ``ebitda`` is not
  that sum — it is its vendor's normalisation — so the EV/EBITDA multiples move.
* **Enterprise value** = ``market cap + total debt − cash``. The market cap is the prices store's issuer cap of
  the peer's newest session (``read.latest_market``, the same value the target's own card uses through
  ``market_inputs.overlay``); the debt and the cash are the same annual record's. No minority interest and no
  preferred stock are added, exactly as the target's own net-debt bridge does not subtract them (#92,
  ``NO_MINORITY_BRIDGE``).

**The basis changed with it, and the card says so.** Yahoo's figures were trailing twelve months; these are the
newest stored **fiscal year**, so a peer that reported three months ago is on an older window than Yahoo's was.
``P/E`` is the market cap over that year's net income, because the store has no ``trailingPE``.

A field the record does not carry leaves its multiple ``None``, which the engine already renders as a blank and
keeps out of the percentile. ``revenue`` is read by name only, so a bank peer carrying one of the two bank top
lines and no ``revenue`` gets no EV/Revenue multiple — the rule of #450, unchanged.
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: The keys the comps engine reads, kept as Yahoo's names so the engine's own arithmetic did not have to move
#: with this change. ``stored`` is this module's own addition.
FIELDS = ("enterpriseValue", "ebitda", "totalRevenue", "marketCap", "netIncomeToCommon", "trailingPE")


def _num(value):
    """``value`` as a float, or None when it is absent or not a number."""
    if value is None:
        return None
    try:
        out = float(value)
    except (TypeError, ValueError):
        return None
    return out if out == out else None       # a NaN is not a figure


def _ebitda(record) -> float | None:
    """``ebit + depreciation``, or None when either half is unknown: half an EBITDA is not an EBITDA."""
    ebit, da = _num(record.get("ebit")), _num(record.get("depreciation"))
    return None if ebit is None or da is None else ebit + da


def _enterprise_value(cap, record) -> float | None:
    """``market cap + total debt - cash``, or None when any of the three is unknown.

    No minority interest and no preferred stock are added, which is the same bridge the target's own net debt
    uses (#92): the card carries ``NO_MINORITY_BRIDGE`` for that already.
    """
    debt, cash = _num(record.get("total_debt")), _num(record.get("cash"))
    if cap is None or debt is None or cash is None:
        return None
    return cap + debt + cash  # MUTATION: #286 mutation check, reverted in the next commit


def peer_multiples(peers) -> dict[str, dict]:
    """``{ticker: answer}`` for the peers, from the store only (#286).

    An answer carries :data:`FIELDS` (any of them None when the record does not say) plus

    * ``stored``: False for a peer the fundamentals layer holds no company or no annual record for — the card
      shows it as not stored and it stays out of every percentile;
    * ``fiscal_year``: the record the figures are of, so the card can say how old the peer side is;
    * ``cap_session``: the session the market cap is of, None when the prices store had none in its window.

    Read only: a store error is "nothing stored" for every peer, never an exception into the Fetch and never a
    provider call.
    """
    wanted = [str(t).strip().upper() for t in (peers or ()) if str(t or "").strip()]
    if not wanted:
        return {}
    records = _records(wanted)
    market = _market(wanted)
    out: dict[str, dict] = {}
    for ticker in wanted:
        annual = [r for r in (records.get(ticker) or ()) if r.get("fiscal_year") is not None]
        if not annual:
            out[ticker] = {"stored": False, **{f: None for f in FIELDS}}
            continue
        latest = annual[-1]
        cap_row = market.get(ticker) or {}
        cap = _num(cap_row.get("issuer_market_cap"))
        if cap is None:
            cap = _num(cap_row.get("market_cap"))
        net_income = _num(latest.get("net_income"))
        out[ticker] = {
            "stored": True,
            "fiscal_year": latest.get("fiscal_year"),
            "cap_session": cap_row.get("cap_session"),
            "marketCap": cap,
            "ebitda": _ebitda(latest),
            "enterpriseValue": _enterprise_value(cap, latest),
            "totalRevenue": _num(latest.get("revenue")),
            "netIncomeToCommon": net_income,
            # The store has no trailing P/E; the engine's own fallback (cap over net income) is the figure, and
            # None here lets it run rather than hard-coding the division twice.
            "trailingPE": None,
        }
    return out


def _records(tickers) -> dict[str, list[dict]]:
    """``{ticker: annual records}`` from the fundamentals serving layer, the Financials board's own statement
    source since G6 (``core/fundamentals_layer``): two reads for the whole peer list, no request."""
    from RevenueChaser.core import fundamentals_layer
    try:
        found = fundamentals_layer.records_many(tickers)
    except Exception as exc:  # noqa: BLE001 - a Fetch must never fail on the store
        logger.warning("comps peers: the fundamentals layer could not be read (%s); no peer is stored", exc)
        return {}
    return {ticker: annual for ticker, (annual, _quarterly, _meta) in found.items()}


def _market(tickers) -> dict[str, dict]:
    """``{ticker: newest market row}`` through ``core/spine_reads.latest_market``: one read for the whole list.

    The wrapper, not ``rcdata.read.latest_market`` straight, for two reasons. It is the path the target's own
    card already takes (``market_inputs.from_store``), so a peer's cap and the target's come from the same
    memoised read of the same session — they have to be comparable, since one divides by the other. And it
    answers ``{}`` with no read at all before the first prices build, so a render on a fresh checkout opens
    nothing. Reading ``rcdata.read`` from a board package directly would also need a line in
    ``needs/boards.PLANNED_READS``, which the wrapper is there to avoid.

    An empty answer means no peer has a cap, so no peer has an enterprise value.
    """
    from RevenueChaser.core import spine_reads
    try:
        return spine_reads.latest_market(tickers)
    except Exception as exc:  # noqa: BLE001 - a Fetch must never fail on the store
        logger.warning("comps peers: the market caps could not be read (%s); no peer gets an enterprise value",
                       exc)
        return {}
