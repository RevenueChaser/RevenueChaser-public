"""The shared reader of the served 13F numbers (#16): the builder writes them (``rcdata/build/ownership``); this
reads them, so a screener whose score includes institutional ownership reads rows instead of importing the 13F board's
engine.

The old ``ownership_snapshot`` table (shares outstanding and insider % per session, in ``raw.duckdb``) and its two
writers went with the old store (#860).
"""
from __future__ import annotations

import logging
from datetime import date

logger = logging.getLogger(__name__)

# The metrics a 13F cell carries, in the shape the retired derive wrote: ``rcdata/build/ownership/serve.py``
# ``METRICS``, pinned by ``module_sec_13f/tests/test_sec13f_board_store_g9.py``.
SEC13F_METRICS = ("shares", "value", "holders", "top10_pct", "hhi", "new_holders", "exited_holders", "buy_flow",
                  "sell_flow", "breadth", "breadth_chg")


def sec13f_totals() -> dict[str, dict]:
    """The served 13F per-ticker totals, ``{ticker: {"YYYY-MM-DD": metrics + ``complete``}}`` — nothing recomputed,
    no network. ``complete`` says the period's filing deadline has passed; before it the quarter is still arriving
    and its numbers are a part of themselves (#514).

    The builder owns these numbers (``rcdata/build/ownership``, PR 16: ``sec13f_ticker_period`` in
    ``ownership.duckdb``), and since G9 nothing else writes them: the dashboard's own derive and the
    ``sec13f_totals`` rows it kept in ``raw.duckdb`` are gone.

    Read by the 13F board (``module_sec_13f.engine.load_totals``) and by the Asymmetric Growth scan, whose
    institutional block is part of the score (owner, 5 Nov 2026). It lives here so the screener reads rows
    rather than importing the 13F engine for them (#16): a store both sides read is the contract, while an
    engine call makes one board's run depend on the other board's module being present.
    """
    from RevenueChaser.rcdata import read as rcread

    out: dict[str, dict] = {}
    for r in rcread.holders_13f():
        # ``complete`` is not one of the store's metrics, and it is not optional either: a period whose filing
        # deadline has not passed holds a part of itself, so a reader that cannot tell shows a quarter still
        # arriving as a collapse (#514). ``rcdata.read`` computes it from the deadline; this used to drop it.
        # ``closed`` (#732): the SEC data set covering the period's deadline is published, so the quarter takes no
        # more change. Left out when the store cannot say (nothing listed yet, or a store built before the column).
        cell = {**{m: r[m] for m in SEC13F_METRICS}, "complete": r["complete"]}
        if r.get("closed") is not None:
            cell["closed"] = bool(r["closed"])
        out.setdefault(r["ticker"], {})[r["period"].isoformat()] = cell
    return out


def sec13f_filer_breaks(tickers) -> dict[str, list[dict]]:
    """``{ticker: [{"period", "kind", "shares", "cik", "filer_name"}]}``: where each ticker's 13F flow breaks, the
    filers that started (``started``) or stopped (``stopped``) reporting it in a settled quarter (#732). The flows
    leave these filers out, so the board marks the ticker and lists them. A store that cannot be read gives ``{}``
    and a warning, never a failed board."""
    from RevenueChaser.rcdata import read as rcread

    wanted = sorted({str(t).strip().upper() for t in tickers if t})
    if not wanted:
        return {}
    out: dict[str, list[dict]] = {}
    try:
        rows = rcread.filer_breaks_13f(wanted)
    except Exception as exc:                      # noqa: BLE001 - a missing mark, never a failed board
        logger.warning("13F filer breaks unreadable, no break marks: %s", exc)
        return {}
    for r in rows:
        out.setdefault(r["ticker"], []).append({"period": r["period"].isoformat(), "kind": r["kind"],
                                                "shares": r["shares"], "cik": r["cik"],
                                                "filer_name": r.get("filer_name")})
    return out


#: The investor types the 13F board offers, in the order of the owner's screenshot (12 Nov 2026), as Unusual Whales'
#: institution tags (``docs/openapi.yaml`` ``Institution Tag``) with the board's label; ``all`` is every filer (#760).
SEC13F_TYPES = (("all", "All"), ("activist", "Activist"), ("13d_activist", "13D Activist"), ("biotech", "Biotech"),
                ("credit", "Credit"), ("energy", "Energy"), ("esg", "ESG"), ("event", "Event-driven"),
                ("real_estate", "Real Estate"), ("small_cap", "Small Cap"), ("tiger_club", "Tiger Cub"),
                ("value_investor", "Value"), ("public_companies", "Public Non-Finance"))


def sec13f_type_holdings(tag: str) -> list[dict]:
    """One investor type's ``sec13f_type_holdings`` rows (#760): per quarter its largest tickers with their ``share``
    (%) of the type's portfolio and the rest as one row whose ``ticker`` is None, periods as ISO dates. A store that
    cannot be read gives ``[]`` and a warning, never a failed board."""
    from RevenueChaser.rcdata import read as rcread

    try:
        rows = rcread.type_holdings_13f([tag])
    except Exception as exc:                      # noqa: BLE001 - an empty chart, never a failed board
        logger.warning("13F investor-type holdings unreadable: %s", exc)
        return []
    return [{**r, "period": r["period"].isoformat(),
             "snapshot_date": r["snapshot_date"].isoformat() if r.get("snapshot_date") else None} for r in rows]


def sec13f_type_filers() -> dict[str, int]:
    """``{tag: filers}``: each investor type's 13F filers in its newest stored quarter (#760), for the board's picker
    to show how thin a type is (13 Nov 2026: 4 energy investors, no ESG one). ``{}`` when the store cannot be read."""
    from RevenueChaser.rcdata import read as rcread

    try:
        rows = rcread.type_holdings_13f()
    except Exception as exc:                      # noqa: BLE001 - no counts, never a failed board
        logger.warning("13F investor-type counts unreadable: %s", exc)
        return {}
    newest: dict[str, tuple] = {}
    for r in rows:
        if r["tag"] not in newest or r["period"] > newest[r["tag"]][0]:
            newest[r["tag"]] = (r["period"], int(r.get("type_filers") or 0))
    return {tag: filers for tag, (_, filers) in newest.items()}


def sec13f_open_periods() -> set[str]:
    """The 13F report periods still arriving (their filing deadline not passed, nor their data set published), as
    ISO dates; ``set()`` when the store cannot be read."""
    from RevenueChaser.rcdata import read as rcread

    try:
        return {r["period"].isoformat() for r in rcread.periods_13f() if not r.get("complete")}
    except Exception as exc:                      # noqa: BLE001 - no mark, never a failed board
        logger.warning("13F periods unreadable, no still-arriving mark: %s", exc)
        return set()


SPLIT_LOOKBACK_DAYS = 10    # a quarter end on a weekend or a holiday still finds the session before it


def split_factors_13f(periods: dict) -> dict[str, dict[str, float]]:
    """``{ticker: {period: split_factor}}`` for ``periods`` (``{ticker: [ISO period, ...]}``): the prices store's
    factor that turns a share count of that quarter end into today's share basis (shares ÷ factor; a 1-for-25 reverse
    split after it serves 25, a 2-for-1 split serves 0.5). The factor of the last bar on or before the quarter end,
    at most ``SPLIT_LOOKBACK_DAYS`` earlier: Compustat's and Alpaca's splits, applied the way every board's split
    basis is (``rcdata.read.bars``). One bar read per quarter, not one per ticker.

    The one split rule for 13F share counts: the 13F board puts every quarter on today's basis with it (#732) and
    Asymmetric Growth its institutional share. A ticker or a quarter the store cannot place has no entry, so its
    shares stay as filed; a store it cannot read gives ``{}`` and a warning, never a failed board.
    """
    from datetime import timedelta

    from RevenueChaser.rcdata import read
    out: dict[str, dict[str, float]] = {}
    try:
        ids = read.security_ids(periods)
        by_period: dict[str, list[str]] = {}
        for t, ps in periods.items():
            if t in ids:
                for p in ps:
                    by_period.setdefault(str(p)[:10], []).append(t)
        for period, tickers in sorted(by_period.items()):
            end = date.fromisoformat(period)
            sid_to = {ids[t]: t for t in tickers}
            # Rows come by security and session, so the last one on or before the quarter end wins.
            for b in read.bars(sid_to, start=end - timedelta(days=SPLIT_LOOKBACK_DAYS), end=end, basis="split"):
                if b.get("split_factor"):
                    out.setdefault(sid_to[b["security_id"]], {})[period] = float(b["split_factor"])
    except Exception as exc:  # noqa: BLE001 - no prices store is "no factor", never a failed board
        logger.warning("13F split factors unread, shares stay as filed: %s: %s", type(exc).__name__, exc)
        return {}
    return out
