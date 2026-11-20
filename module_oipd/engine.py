"""Implied Probability (OIPD) engine — option chain -> SVI surface -> risk-neutral PDF.

**The board's path is** :func:`build`: it reads one session's chain from the nightly options build
(``options.duckdb`` ``option_eod``, through ``rcdata.read``) for a name the build stores a quoted chain for (the option
watch list, the evening's earnings set) and makes no provider call (avo's decision B, 10 Nov 2026; F2, 18 Nov 2026).
Its spot is the session's close and its discount rate the stored FRED 10-year yield of that session
(``macro.dgs10``, ``session_risk_free``; avo's decision of 10 Nov 2026, #644), the 4% constant only as a fallback.

The older UW path below (``run``, ``fetch_result``, ``oipd_chain`` / ``oipd_meta``) is no longer called by the
dashboard; it goes with the board's own store in a later step:

- **Fetch** (``no_fetch=False``): pull the option chain from Unusual Whales,
  persist it to ``oipd_chain`` / ``oipd_meta``, then fit.
- **Refresh** (``no_fetch=True``): re-read the stored chain and re-fit with
  **zero network calls**.

The fit itself is pure numpy/scipy (``opd_math``) and deterministic, so a
Refresh reproduces the Fetch board exactly.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import numpy as np

from RevenueChaser.core import calendar, rawstore
from RevenueChaser.core.config import to_float
from RevenueChaser.core.providers.result import ProviderResult

from . import config, opd_math, uw_chain

logger = logging.getLogger(__name__)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _today() -> str:
    """The latest complete session: the ``as_of`` when no spot candle dates the run (#382)."""
    return calendar.latest_complete_session().isoformat()


def _candle_session(data: dict | None) -> str | None:
    """The session date of an ``ohlc_latest`` bar, when the bar carries one."""
    day = (data or {}).get("date")
    return day[:10] if isinstance(day, str) and day else None


# ── persistence ─────────────────────────────────────────────────────────────
def chain_rows(ticker: str, contracts: list[dict], meta: dict) -> list[dict]:
    """The ``oipd_chain`` rows of a pull (its result history, ``oipd_chain_history``, is their mirror)."""
    fetched = meta["fetched_at"]
    return [{
        "ticker": ticker,
        "option_symbol": c["option_symbol"],
        "expiry": c["expiry"], "option_type": c["option_type"],
        "strike": c["strike"], "bid": c["bid"], "ask": c["ask"],
        "last_price": c["last_price"], "volume": c["volume"],
        "open_interest": c["open_interest"], "iv": c["iv"],
        "delta": c["delta"], "tape_time": c.get("tape_time"),
        "fetched_at": fetched,
    } for c in contracts]


def _persist(ticker: str, contracts: list[dict], meta: dict) -> None:
    rows = chain_rows(ticker, contracts, meta)

    # One transaction (#592): a failure between the two writes must not leave a chain without its meta row.
    # write mode "replace" + group_by ticker: only this ticker's chain is swapped.
    def _write(tx):
        tx.write_rows("oipd_chain", rows)
        tx.write_rows("oipd_meta", [meta])

    rawstore.atomic(_write, db="oipd")


def _contracts_from_store(rows: list[dict]) -> list[dict]:
    out = []
    for r in rows:
        out.append({
            "option_symbol": r.get("option_symbol"),
            "expiry": r.get("expiry"), "option_type": r.get("option_type"),
            "strike": r.get("strike"), "bid": r.get("bid"), "ask": r.get("ask"),
            "last_price": r.get("last_price"),
            "mid": uw_chain.mid_price(r.get("bid"), r.get("ask"), r.get("last_price")),
            "iv": r.get("iv"), "open_interest": r.get("open_interest"),
            "volume": r.get("volume"), "delta": r.get("delta"),
            "tape_time": r.get("tape_time"),
        })
    return out


def last_ticker() -> str | None:
    rows = rawstore.query(
        "SELECT ticker FROM oipd_meta ORDER BY fetched_at DESC LIMIT 1", db="oipd")
    return rows[0]["ticker"] if rows else None


# ── fetch ───────────────────────────────────────────────────────────────────
@dataclass
class FetchResult:
    """One chain pull: the contracts, and whether every request behind them worked.

    ``status`` is ``ok``, ``partial`` (some expiry was truncated or missing: the contracts are the
    ones that arrived) or ``failed`` (requests failed and nothing arrived). An empty answer from
    a request that worked, or a 404 chain, is ``ok``: the provider simply has no chain.
    """

    contracts: list[dict]
    meta: dict
    warnings: list[str]
    status: str = "ok"
    errors: list[dict] = field(default_factory=list)
    # The spot candle's failure (its ``status`` and ``error``), or None. Not a chain error: the chain stays whole.
    candle_error: dict | None = None


def _ask(uw, method: str, *args, **kw) -> ProviderResult:
    """``uw.<method>_result(...)``: the answer with its outcome. A client without that ``*_result`` twin (a test
    fake) is taken at its word: what its plain method returns is an ``ok`` answer."""
    fn = getattr(uw, f"{method}_result", None)
    if fn is not None:
        res = fn(*args, **kw)
        if isinstance(res, ProviderResult):
            return res
    return ProviderResult("ok", getattr(uw, method)(*args, **kw), None, "")


def _meta(ticker: str, asof: str, spot: float | None, contracts: list[dict]) -> dict:
    return {
        "ticker": ticker, "as_of": asof, "spot": spot,
        "risk_free": config.RISK_FREE_RATE,
        "expiry_count": len({c["expiry"] for c in contracts}),
        "horizon_days": config.MAX_DTE,
        "fetched_at": _now(),
    }


def _pull(uw, ticker: str, **kw) -> ProviderResult:
    """One chain request with its outcome. A client without ``option_contracts_result`` (a test fake)
    is taken at its word: the list it returns is an ``ok`` answer."""
    fn = getattr(uw, "option_contracts_result", None)
    if fn is not None:
        res = fn(ticker, **kw)
        if isinstance(res, ProviderResult):
            return res
    return ProviderResult("ok", uw.option_contracts(ticker, **kw) or [], None, "")


def fetch_result(uw, ticker: str) -> FetchResult:
    """Pull the chain for ``ticker`` and say whether it is whole."""
    warnings: list[str] = []
    errors: list[dict] = []

    # The spot candle dates the run: its session drives every DTE/T, so it is read first. With no
    # candle the latest complete session is the as_of (#382).
    candle = _ask(uw, "ohlc_latest", ticker)
    spot = to_float((candle.data or {}).get("close"))
    asof = _candle_session(candle.data) or _today()
    candle_error = None
    if candle.status != "ok":
        # Only the spot-relative probabilities are lost: the chain is whole and is still saved.
        err = candle.error or {}
        candle_error = {"status": err.get("status"), "error": err.get("error")}
        code = err.get("status")
        warnings.append(f"The Unusual Whales spot price request failed{f' (HTTP {code})' if code else ''}; "
                        "the forward falls back to the chain.")
    elif spot is None:
        warnings.append("No spot price available; the forward falls back to the chain.")

    breakdown = _ask(uw, "expiry_breakdown", ticker)
    if breakdown.status != "ok":
        # The expiry list is unknown, not empty: no chain is pulled, not even the default one. A 404 is a
        # ticker UW has no options for (an empty chain, "check the ticker"); any other failure fails the run,
        # so nothing is saved and the stored chain is kept.
        err = breakdown.error or {}
        if err.get("status") == 404:
            return FetchResult([], _meta(ticker, asof, None, []), warnings)
        return FetchResult([], _meta(ticker, asof, None, []), warnings, "failed",
                           [{"expiry": "the expiry breakdown", **err}])
    picks = uw_chain.expiries_from_breakdown(
        breakdown.data or [], asof, config.MIN_DTE, config.MAX_DTE, config.MAX_EXPIRIES)
    if not picks:
        warnings.append("No expiries in the 1d-365d window; fetched the default chain.")
        pulls = [("the default chain", _pull(uw, ticker, limit=config.PAGE_LIMIT,
                                             max_pages=config.MAX_PAGES))]
    else:
        pulls = [(p["expiry"], _pull(uw, ticker, expiry=p["expiry"], limit=config.PAGE_LIMIT,
                                     max_pages=config.MAX_PAGES)) for p in picks]

    raw: list[dict] = []
    for label, res in pulls:
        raw.extend(res.data or [])
        err = res.error or {}
        if res.status == "ok" or (res.status == "failed" and err.get("status") == 404):
            continue
        errors.append({"expiry": label, **err})
        if res.status == "partial":
            page = err.get("page")      # 0-based, as UW pages (#255); shown counted from 1
            shown = page + 1 if isinstance(page, int) else "?"
            warnings.append(f"{label}: page {shown} of the Unusual Whales chain failed; "
                            "this expiry is truncated.")
        else:
            warnings.append(f"{label}: the Unusual Whales request failed; this expiry is missing.")

    contracts = uw_chain.map_rows(raw)
    if not contracts:
        warnings.append("Unusual Whales returned no usable contracts.")

    meta = _meta(ticker, asof, spot, contracts)
    status = "ok" if not errors else ("partial" if contracts else "failed")
    return FetchResult(contracts, meta, warnings, status, errors, candle_error)


def fetch(uw, ticker: str) -> tuple[list[dict], dict, list[str]]:
    """Pull the chain for ``ticker``; returns (contracts, meta, warnings)."""
    res = fetch_result(uw, ticker)
    return res.contracts, res.meta, res.warnings


# ── fit ─────────────────────────────────────────────────────────────────────
def _curve_view(curve: opd_math.ProbCurve, n: int = 121) -> dict:
    """Down-sample the density/CDF to a display window around the bulk of mass."""
    lo = curve.quantile(0.005)
    hi = curve.quantile(0.995)
    mask = (curve.S >= lo) & (curve.S <= hi)
    S, pdf, cdf = curve.S[mask], curve.price_pdf[mask], curve.cdf[mask]
    if S.size > n:
        idx = np.linspace(0, S.size - 1, n).round().astype(int)
        S, pdf, cdf = S[idx], pdf[idx], cdf[idx]
    return {
        "S": [round(float(v), 4) for v in S],
        "pdf": [round(float(v), 8) for v in pdf],
        "cdf": [round(float(v), 6) for v in cdf],
    }


def _smile_view(contracts: list[dict], params: dict, F: float, T: float, r: float,
                n: int = 121) -> dict:
    k_mkt, iv_mkt = [], []
    for c in contracts:
        if c["strike"] <= 0:
            continue
        # The marker is the fit's own solved IV (the price's, not the vendor's) so the dots and
        # the fitted curve answer the same question (#382).
        iv = uw_chain.contract_iv(c, F, T, r)
        if iv is None or not (0.0 < iv < 5.0):
            continue
        k_mkt.append(float(np.log(c["strike"] / F)))
        iv_mkt.append(float(iv))
    if k_mkt:
        lo, hi = min(k_mkt), max(k_mkt)
    else:
        lo, hi = -0.5, 0.5
    k_fit = np.linspace(lo, hi, n)
    svi = {kk: params[kk] for kk in ("a", "b", "rho", "m", "sigma")}
    w = opd_math.svi_w(k_fit, **svi)
    iv_fit = np.sqrt(np.clip(w, 0.0, None) / T) if T > 0 else np.zeros_like(k_fit)
    return {
        "k_mkt": [round(v, 5) for v in k_mkt],
        "iv_mkt": [round(v, 5) for v in iv_mkt],
        "k_fit": [round(float(v), 5) for v in k_fit],
        "iv_fit": [round(float(v), 5) for v in iv_fit],
    }


def _fit_expiry(expiry: str, contracts: list[dict], spot: float, r: float,
                asof: str, svi: dict | None = None) -> tuple[dict | None, str | None]:
    d = uw_chain.dte(asof, expiry)
    if d is None or d <= 0:
        return None, f"{expiry}: no valid DTE"
    T = d / 365.0
    F = uw_chain.infer_forward([c for c in contracts if uw_chain.two_sided(c)], T, r, spot)
    if not np.isfinite(F) or F <= 0:
        return None, f"{expiry}: no forward (no quoted put/call pairs)"

    inputs = uw_chain.fit_inputs(contracts, F, config.MAX_REL_SPREAD)
    ks, ws = [], []
    for c in inputs:
        iv = uw_chain.contract_iv(c, F, T, r)
        if iv is None:
            continue
        ks.append(float(np.log(c["strike"] / F)))
        ws.append(iv * iv * T)
    if len(ks) < config.MIN_CONTRACTS:
        return None, f"{expiry}: only {len(ks)} usable strikes (< {config.MIN_CONTRACTS})"

    params = opd_math.fit_svi(ks, ws, g_floor=config.G_FLOOR,
                              penalty_weight=config.PENALTY_WEIGHT)
    if params is None:
        return None, f"{expiry}: SVI fit failed"
    if svi is not None:                        # the fitted parameters, for the result history (#382)
        svi[expiry] = {k: float(params[k]) for k in ("a", "b", "rho", "m", "sigma")}
    # A negative g_min is not fatal — the board renders and flags it in the
    # skew KPI — so the expiry is kept rather than dropped.
    curve = opd_math.ProbCurve(expiry, T, F, params, r, **config.GRID)
    st = curve.stats()
    atm = opd_math.atm_iv(params, T)
    tail_ratio = (math.log(st["p95"] / st["p05"]) / (2 * 1.645 * atm * math.sqrt(T))
                  if atm and st["p05"] > 0 and st["p95"] > 0 else None)
    greeks = opd_math.atm_greeks(params, T, r, F)
    # With no spot (UW returned no regular-session bar) the fit stands on the
    # chain's forward; only the spot-relative probabilities are unknown.
    if spot is not None:
        up10, dn10 = spot * 1.10, spot * 0.90
        spot_probs = {
            "prob_below_spot": round(curve.prob_below(spot), 4),
            "prob_above_spot": round(curve.prob_above(spot), 4),
            "p_up10": round(curve.prob_above(up10), 4),
            "p_down10": round(curve.prob_below(dn10), 4),
        }
    else:
        spot_probs = dict.fromkeys(("prob_below_spot", "prob_above_spot", "p_up10", "p_down10"))
    entry = {
        "date": expiry, "dte": d, "T": round(T, 6),
        "forward": round(F, 4), "n": len(ks),
        "atm_iv": round(atm, 4) if atm else None,
        "g_min": round(params["g_min"], 5),
        "g_min_window": round(curve.g_min_window, 5),
        "clipped_pct": round(100.0 * curve.clipped_mass, 3),
        "min_var": round(curve.min_var, 6),
        **{f"density_{k}": v for k, v in opd_math.density_check(
            params["g_min"], curve.g_min_window, 100.0 * curve.clipped_mass, curve.min_var,
            config.CLIP_FLAG_PCT, tail_ratio, config.TAIL_FLAG_RATIO, config.G_FLAG_TOL).items()},
        "tail_ratio": round(tail_ratio, 3) if tail_ratio is not None else None,
        "rmse": round(params["rmse"], 6),
        "mean": round(st["mean"], 4),
        "quantiles": {kk: round(st[kk], 4) for kk in
                      ("p05", "p10", "p25", "median", "p75", "p90", "p95")},
        **spot_probs,
        "greeks": {kk: round(float(v), 6) for kk, v in greeks.items()},
        "curve": _curve_view(curve),
        "smile": _smile_view(inputs, params, F, T, r),
    }
    return entry, None


def _fit_payload(ticker: str, contracts: list[dict], meta: dict,
                 warnings: list[str], svi: dict | None = None) -> dict:
    spot = meta.get("spot")
    r = meta.get("risk_free") or config.RISK_FREE_RATE
    asof = meta.get("as_of") or _today()

    by_expiry: dict[str, list[dict]] = {}
    for c in contracts:
        by_expiry.setdefault(c["expiry"], []).append(c)

    entries, curves = [], []
    for expiry in sorted(by_expiry):
        chain, dropped = uw_chain.one_root(by_expiry[expiry])
        if dropped:
            warnings.append(f"{expiry}: fitted the {chain[0].get('root')} chain; left out {', '.join(dropped)} "
                            "(a separate contract with its own settlement, e.g. SPX AM)")
        entry, err = _fit_expiry(expiry, chain, spot, r, asof, svi)
        if err:
            warnings.append(err)
            continue
        entries.append(entry)

    payload = {
        "ticker": ticker,
        "asof": asof,
        "spot": spot,
        "risk_free": r,
        # Where that rate came from: "macro.dgs10" with the observation's date, or "default" (#644).
        "risk_free_source": meta.get("risk_free_source") or "default",
        "risk_free_as_of": meta.get("risk_free_as_of"),
        "source": "Unusual Whales",
        "generated_at": _now(),
        "fetched_at": meta.get("fetched_at"),
        "horizon_days": meta.get("horizon_days"),
        "n_contracts": len(contracts),
        "model_version": config.model_version(),
        "expiries": entries,
        "fan": None,
        "warnings": warnings,
        "error": None,
    }
    fanned = [e for e in entries if not e["density_flag"]]   # a flagged density is shown muted, never fanned
    if len(fanned) < len(entries):
        warnings.append(f"{len(entries) - len(fanned)} flagged expir{'y' if len(entries) - len(fanned) == 1 else 'ies'} "
                        "left out of the fan: " + "; ".join(f"{e['date']} {e['density_note']}"
                                                            for e in entries if e["density_flag"]))
    if fanned:
        # Fan chart from the trustworthy fitted curves (quantiles across expiries).
        fan = {"expiries": [e["date"] for e in fanned],
               "dte": [e["dte"] for e in fanned],
               "quantiles": {
                   q: [e["quantiles"][k] for e in fanned]
                   for q, k in (("0.05", "p05"), ("0.25", "p25"),
                                ("0.50", "median"), ("0.75", "p75"),
                                ("0.95", "p95"))},
               "spot_ref": [e["forward"] for e in fanned]}
        payload["fan"] = fan
    if contracts and not any(uw_chain.two_sided(c) for c in contracts):
        payload["error"] = (f"The stored {ticker} chain of {asof} carries no two-sided quote (no bid on any of "
                            f"{len(contracts):,} contracts), so nothing is fitted: the fit uses quotes, never last "
                            "trades or the vendor's IV.")
    if not entries and not payload["error"]:
        payload["error"] = (
            f"No expiry could be fitted for {ticker}."
            + ((" " + "; ".join(warnings)) if warnings else "")
        )
    return payload


def _empty_payload(ticker: str, message: str) -> dict:
    return {
        "ticker": ticker, "asof": _today(), "spot": None,
        "risk_free": config.RISK_FREE_RATE, "risk_free_source": "default", "risk_free_as_of": None,
        "source": "Unusual Whales",
        "generated_at": _now(), "fetched_at": None, "horizon_days": None,
        "n_contracts": 0, "expiries": [], "fan": None,
        "warnings": [], "error": message,
    }


# ── the nightly build (decision B) ──────────────────────────────────────────────────────────────────────────
def list_names() -> list[str]:
    """The names the build stores a quoted chain for: the option watch list (``read.watched``, the one list source;
    strict, so an unreadable list raises ``read.JobListUnreadable``) and the newest evening's earnings set."""
    from RevenueChaser.rcdata import read
    # Not SPX: UW stores its chain with a zero NBBO, so it cannot be fitted on quotes; SPY stands for the S&P 500
    # here (avo's G1, 18 Nov 2026; #1061).
    names = set(read.watched("option")) - {"SPX"}
    er = read.earnings_options(start=calendar.today_ny() - timedelta(days=14))   # bounded: er_options grows forever
    newest = max((str(r["session_date"])[:10] for r in er), default=None)
    names.update(r["ticker"] for r in er if str(r["session_date"])[:10] == newest)
    return sorted(names)


def _iso_time(epoch) -> str | None:
    try:
        return datetime.fromtimestamp(float(epoch), timezone.utc).isoformat(timespec="seconds")
    except (TypeError, ValueError):
        return None


def stored_chain(ticker: str, session: str | None = None) -> tuple[str | None, list[dict], float | None, str | None]:
    """``(session, contracts, spot, fetched_at)`` of one name's stored chain: the newest session when ``session`` is
    None. Spot is the session's close (``option_daily``), else the price UW served with the earnings set's spot
    exposures (``option_strike``), else None (the forward then stands on the chain alone)."""
    from RevenueChaser.rcdata import read
    rows = read.option_chain(ticker, session)
    if not rows:
        return None, [], None, None
    day = str(rows[0]["session_date"])[:10]
    spot = next((to_float(r.get("close")) for r in read.option_daily(ticker, day, day) if r.get("close")), None)
    if spot is None:
        spot = next((to_float(r.get("price")) for r in read.option_strikes(ticker, day, "earnings")
                     if r.get("price")), None)
    fetched = max((r["fetched_at"] for r in rows if r.get("fetched_at") is not None), default=None)
    return day, uw_chain.map_rows(rows), spot, _iso_time(fetched)


def pick_expiries(contracts: list[dict], asof: str) -> list[dict]:
    """The contracts of the expiries a fit uses: ``MIN_DTE``-``MAX_DTE`` days out, the ``MAX_EXPIRIES`` with the most
    open interest (the rule the UW fetch applied to the breakdown; the stored chain holds every expiry)."""
    oi: dict[str, float] = {}
    for c in contracts:
        d = uw_chain.dte(asof, c["expiry"])
        if d is not None and config.MIN_DTE <= d <= config.MAX_DTE:
            oi[c["expiry"]] = oi.get(c["expiry"], 0.0) + (c.get("open_interest") or 0.0)
    keep = set(sorted(oi, key=lambda e: (-oi[e], e))[:config.MAX_EXPIRIES])
    return [c for c in contracts if c["expiry"] in keep]


def session_risk_free(session: str | None) -> tuple[float, str, str | None, str | None]:
    """``(rate, source, as_of, warning)`` for a chain's session: the stored FRED 10-year yield of that session
    (``macro.dgs10``, avo's decision of 10 Nov 2026, #644), else the constant with a warning the board shows.

    The yield discounts every fitted expiry (``opd_math.black76_price``, the forward and the greeks), so the board
    says which day's yield it stood on rather than implying a rate it did not use.
    """
    from RevenueChaser.core import risk_free
    held = risk_free.stored_dgs10(session, config.RISK_FREE_MAX_AGE_DAYS)
    if held is None:
        return (config.RISK_FREE_RATE, "default", None,
                f"No stored 10-year Treasury yield within {config.RISK_FREE_MAX_AGE_DAYS} days of "
                f"{session or 'this session'}; the fit discounts at the {config.RISK_FREE_RATE:.0%} default.")
    return held["value"], "macro.dgs10", held["as_of"], None


def build(ticker: str | None = None, session: str | None = None) -> dict:
    """The board's payload for ``ticker`` from the stored chain: no provider call, no write."""
    from RevenueChaser.rcdata import read
    try:
        names = list_names()
    except read.JobListUnreadable as exc:
        return _empty_payload((ticker or config.DEFAULT_TICKER).upper(),
                              f"The option list could not be read ({exc}). Try again in a moment.")
    default = config.DEFAULT_TICKER if config.DEFAULT_TICKER in names else (names[0] if names else None)
    ticker = (ticker or default or config.DEFAULT_TICKER).upper()
    if ticker not in names:
        p = _empty_payload(ticker, f"{ticker} is not on the option list nor in the newest earnings set. Add it on the Watchlists board; "
                                   "its chain comes with the next session's build.")
        p["names"] = names
        return p
    asof, contracts, spot, fetched = stored_chain(ticker, session)
    if not contracts:
        p = _empty_payload(ticker, f"No stored chain for {ticker} yet: the nightly options build stores it after "
                                   "the close.")
        p["names"] = names
        return p
    rate, rate_source, rate_as_of, rate_warning = session_risk_free(asof)
    meta = {"as_of": asof, "spot": spot, "risk_free": rate, "risk_free_source": rate_source,
            "risk_free_as_of": rate_as_of, "horizon_days": config.MAX_DTE, "fetched_at": fetched}
    warnings = [] if spot is not None else ["No close stored for this session; the forward stands on the chain."]
    if rate_warning:
        warnings.append(rate_warning)
    payload = _fit_payload(ticker, pick_expiries(contracts, asof), meta, warnings)
    payload.update(source="Unusual Whales, nightly options build", names=names)
    return payload


def run(uw=None, ticker: str | None = None, no_fetch: bool = False, capture: dict | None = None) -> dict:
    """Fit the risk-neutral surface for ``ticker`` (Fetch or store-only Refresh).

    A Fetch that passes ``capture`` (the result history, #382) gets what the fit stood on: the pull's ``status``
    and ``errors``, the ``chain`` rows it pulled (kept even when a partial chain is not saved), the ``meta``, each
    fitted expiry's ``svi`` parameters and the spot candle's ``candle_error`` (None when it worked). A Refresh
    never fills it."""
    warnings: list[str] = []
    if no_fetch:
        ticker = (ticker or last_ticker() or config.DEFAULT_TICKER).upper()
        rows = rawstore.query(
            "SELECT option_symbol, expiry, option_type, strike, bid, ask, "
            "last_price, volume, open_interest, iv, delta, tape_time "
            "FROM oipd_chain WHERE ticker = ?", [ticker], db="oipd")
        meta = rawstore.get("oipd_meta", ticker)
        if not rows or not meta:
            return _empty_payload(
                ticker, f"No cached chain for {ticker}. Run a Fetch first.")
        contracts = _contracts_from_store(rows)
        return _fit_payload(ticker, contracts, meta, warnings)

    ticker = (ticker or config.DEFAULT_TICKER).upper()
    pulled = fetch_result(uw, ticker)
    contracts, meta = pulled.contracts, pulled.meta
    warnings.extend(pulled.warnings)
    svi: dict | None = None
    if capture is not None:
        svi = {}
        capture.update(status=pulled.status, errors=list(pulled.errors), meta=dict(meta), svi=svi,
                       chain=chain_rows(ticker, contracts, meta), candle_error=pulled.candle_error)
    if pulled.status == "failed":
        status = pulled.errors[0].get("status")
        return _empty_payload(
            ticker,
            f"Unusual Whales request failed for {ticker}"
            f"{f' (HTTP {status})' if status else ''} — the option chain was not fetched and "
            "nothing was saved. Try the Fetch again.")
    if not contracts:
        return _empty_payload(
            ticker,
            f"Unusual Whales returned no option chain for {ticker} — check the ticker.")
    if pulled.status == "partial":
        # A truncated chain would replace a whole one with a thinner one and make Refresh reproduce it.
        warnings.append("Partial chain: not saved, the stored chain was kept.")
    else:
        _persist(ticker, contracts, meta)
    return _fit_payload(ticker, contracts, meta, warnings, svi)
