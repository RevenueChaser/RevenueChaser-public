"""Orkestrasyon: ticker -> Quick Remarks + Fin Model engine'leri -> rapor."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from revenuechaser.core.reporting_common import filters_meta, write_artifact

from .config import OUTPUT_DIR, PEER_CAP_RATIO_BAND, PEER_K, RISK_FREE_MAX_AGE_DAYS
from .engines import (
    comps_engine,
    credit_capacity_engine,
    dcf_engine,
    quick_remarks_engine,
    sensitivity_engine,
    three_statement_engine,
)
from . import market_inputs
from .peers import peer_set, target_row
from .reporting.html_builder import build_report_html


# An upper-cased symbol such as BRK.B. The ticker becomes a file name (CLI report), so a path piece
# must never get through (#173 D5, #175).
_TICKER_RE = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,9}")


logger = logging.getLogger(__name__)


def _stored_risk_free() -> dict | None:
    """The newest stored FRED 10-year Treasury yield as a rate with its date, or ``None`` when none is stored or the
    newest is more than ``RISK_FREE_MAX_AGE_DAYS`` old.

    The DCF's risk-free rate was the 4% constant although the store holds the real yield (Financials review S2).
    Read-only and zero network, so a Refresh reads it too; without it the DCF takes its default and says so. The
    yield is ``market_series`` DGS10 (``rcdata``, G6) alone, read through ``core/risk_free``, which the Implied
    Probability fit reads as well (#644).

    The window is looser than the Earnings Radar's on purpose (the Opus review's N1): that one pairs daily yields
    with returns for a beta, so a series three sessions behind is already wrong there. Here one level is read, a
    ten-year yield moves a few basis points in two weeks, and the fallback is a flat 4%, which is further off than a
    two-week-old yield; the date is shown.
    """
    from revenuechaser.core import risk_free
    return risk_free.stored_dgs10(max_age_days=RISK_FREE_MAX_AGE_DAYS)


# The statement fields the SEC facts carry (``sec_edgar.CONCEPTS``) that the engines read, by the engines' names. A
# field the facts do not carry (current assets and liabilities) is left out, so the engines' labelled defaults show
# (review S1).
# The last three are #645 G1 (avo 10 Nov 2026): the layer serves ``IncomeTaxExpenseBenefit``, pre-tax income and
# interest expense, which only Yahoo used to supply, so the effective tax rate and the interest cover are now the
# filer's own figures rather than a flat default on every name.
_SEC_FIELDS = ("revenue", "cost_of_revenue", "gross_profit", "ebit", "net_income", "diluted_shares", "basic_shares",
               "rd_expense", "operating_cash_flow", "capex", "depreciation", "total_assets", "total_equity", "cash",
               "short_term_investments", "receivables", "inventory", "payables", "total_debt",
               "tax_provision", "pretax_income", "interest_expense")
# The layer's name for a field the engines call something else. The SEC concept is ``IncomeTaxExpenseBenefit``, which
# the layer serves as ``income_tax_expense``; the engines were written against Yahoo's ``tax_provision`` and read
# that (``engines/_inputs.statement_tax_rate``).
_LAYER_NAMES = {"tax_provision": "income_tax_expense"}
# shortcut: the newest five fiscal years (Yahoo gave four); read more when a model projects from a longer history.
SEC_YEARS = 5


def _financials_record(rec: dict) -> dict:
    """One SEC annual record (``sec_edgar.extract_annual``'s shape) as the engines read a year: the fields above,
    ``capital_expenditure`` beside ``capex``, ``period_end`` (the revenue's) and EBITDA as operating income plus
    depreciation when the year has both."""
    from revenuechaser.core import fiscal_year
    from revenuechaser.core.config import to_float
    end = fiscal_year.period_end(rec)
    out: dict = {"fiscal_year": rec.get("fiscal_year"), "period_end": end.isoformat() if end else None}
    for f in _SEC_FIELDS:
        v = to_float(rec.get(_LAYER_NAMES.get(f, f)))
        if v is not None:
            out[f] = v
    if "capex" in out:
        out["capital_expenditure"] = out["capex"]
    if "ebit" in out and "depreciation" in out:
        out["ebitda"] = out["ebit"] + out["depreciation"]
    return out


def _tax_and_interest_gaps(annual: list[dict], bank: bool = False) -> list[str]:
    """What the SEC's statements leave the engines a labelled default for beside the statement lines: the effective
    tax rate and the interest expense (#645 G1).

    It used to be both, on every name, because the facts carried neither (the old ``NOT_IN_FACTS``). The layer
    serves all three concepts now, so this is measured per company: the tax rate is a gap only when no year's
    ``tax_provision / pretax_income`` is inside the believable band (``_inputs.median_tax_rate``, which is what the
    DCF actually falls back from), and the interest expense when the newest year with revenue has none. A bank's
    model reads neither, so it has no gap (the delta review's nit).
    """
    from revenuechaser.core import fiscal_year
    from revenuechaser.core.config import to_float
    from .engines._inputs import median_tax_rate
    if bank:
        return []
    i = fiscal_year.anchor(annual)
    latest = annual[i] if i is not None else {}
    gaps = []
    if median_tax_rate(annual)[0] is None:
        gaps.append("tax rate")
    if to_float(latest.get("interest_expense")) is None:
        gaps.append("interest expense")
    return gaps


def _statement_gaps(annual: list[dict], bank: bool = False) -> list[str]:
    """The base-year inputs the engines would run on a labelled default for (``dcf_engine``): revenue, EBITDA,
    depreciation and capex of the newest year with revenue (``fiscal_year.anchor``), and working capital in every
    year, except for a bank (``bank``), whose models never read it (P/E only, Opus review N4)."""
    from revenuechaser.core import fiscal_year
    from revenuechaser.core.config import to_float
    from .engines.dcf_engine import _nwc
    i = fiscal_year.anchor(annual)
    latest = annual[i] if i is not None else {}
    gaps = sorted(f for f in ("revenue", "ebitda", "depreciation") if to_float(latest.get(f)) is None)
    if to_float(latest.get("capex")) is None and to_float(latest.get("capital_expenditure")) is None:
        gaps = sorted(gaps + ["capex"])
    if not bank and not any(_nwc(r) is not None for r in annual):
        gaps.append("working capital")
    return gaps


#: What the Source line and the warning say for a name the fundamentals layer holds no annual year for
#: for. Yahoo used to supply those statements; since avo's decision of 10 Nov 2026 (option B) it is dropped, so
#: such a name is stated rather than modelled on a vendor's numbers.
NO_SEC_DATA = "No SEC data (the company facts hold no annual year at all), so no model was run"


def _sec_statements(ticker: str) -> tuple[list[dict] | None, dict]:
    """``(annual, meta)`` from the fundamentals layer (G6, build plan PR 15: "statement inputs from the store").

    ``annual`` is the newest ``SEC_YEARS`` fiscal years, ending on the newest year with revenue: a later year the
    layer serves with only balance-sheet fields is not a base year (Opus review S2). It is **None** when the layer
    holds no such year — the board's no-data state since Yahoo was dropped (#645, avo 10 Nov 2026), where it used
    to be the moment Yahoo's statements took over.

    ``meta`` comes back either way: it carries the SEC entity name the header shows and the layer's own stamps,
    which a name without a single annual year still has.
    """
    from revenuechaser.core import fiscal_year, fundamentals_layer
    annual, _quarterly, meta = fundamentals_layer.records(ticker)
    i = fiscal_year.anchor(annual)
    if i is None:
        return None, meta
    annual = annual[:i + 1]
    return [_financials_record(r) for r in annual[-SEC_YEARS:]], meta


def _company_name(ticker: str, meta: dict) -> str:
    """The name the report header shows: the SEC's own entity name, else the spine's, else the ticker.

    It was Yahoo's ``longName`` until #645. A store read only, and a failed one is no name rather than an error.
    """
    name = str(meta.get("entity_name") or "").strip()
    if name:
        return name
    try:
        from revenuechaser.core import universe as _spine
        row = _spine.filter_fields([ticker]).get(ticker) or {}
    except Exception as exc:  # noqa: BLE001 - a header name is never worth failing a run
        logger.debug("financials: no spine name for %s (%s)", ticker, exc)
        row = {}
    return str(row.get("name") or "").strip() or ticker


def _enterprise_value(market_cap, annual: list[dict]) -> float | None:
    """``market cap + total debt - cash`` of the newest annual year, the same bridge the peer side uses
    (``store_reads._enterprise_value``, avo 20 Nov 2026 "Store'dan türet").

    The EV was Yahoo's ``enterpriseValue`` — its own newest quarter's debt and cash — so the target's figure and
    the peers' were on two bases. Both are the newest stored fiscal year now, which is the basis the comps card
    already states. None when the cap or either balance-sheet line is unknown: half a bridge is not an EV.
    """
    from revenuechaser.core import fiscal_year
    from .store_reads import _enterprise_value as bridge
    i = fiscal_year.anchor(annual or [])
    return bridge(market_cap, annual[i]) if i is not None else None


class _NoCachedData(Exception):
    """No cached payload in .store for the ticker (store-only render)."""

    def __init__(self, ticker: str):
        super().__init__(f"no cached financials for {ticker}")
        self.ticker = ticker


def picker_payload(ticker: str) -> dict:
    """The rows the shared filter bar and the Ticker combobox read, and the bar's meta (#591).

    The pool is this board's own universe cut: the spine's operating names above the market-cap floor, the same
    set the comps peer ladder ranks over, carrying the universal-filter fields (index, market cap, GICS path,
    theme ids, earnings date). A store read only, so a Refresh stays network-free.

    The filters narrow only what the picker offers; the statements below are always the one company the board
    fetched. The ticker on the page stays in the pool even when the cut drops it, so the picker never opens on
    a name it cannot show.
    """
    from revenuechaser.core import universe as _spine

    names = _spine.classification_universe(operating_only=_spine.BOARD_OPERATING_ONLY["module_financials"])
    fields = _spine.filter_fields(names) if names else {}
    rows = [fields[t] for t in names if t in fields]
    ticker = (ticker or "").strip().upper()
    if ticker and not any(r.get("ticker") == ticker for r in rows):
        rows.insert(0, _spine.filter_fields([ticker]).get(ticker) or {"ticker": ticker, "name": ticker})
    return {"rows": rows,
            "meta": filters_meta("financials", earnings_mode="filter", themes=_spine.theme_catalog())}


def run(ticker: str, modules: list[str] | tuple[str, ...] = ("dcf",),
        output: str = "html", use_cache: bool = True, no_fetch: bool = False,
        assumptions: dict | None = None, peers: list[str] | None = None,
        report_path: Path | str | None = None, run_id: str | None = None) -> dict:
    """Uçtan uca Fin Research çalıştırır; rapor yolunu ve sonuçları döndürür.

    ``no_fetch=True`` — store-only render: its stored inputs lived in the old store, so it raises
    ``_NoCachedData`` and the caller shows an empty state (#860).

    The report goes to ``report_path`` when given (the dashboard's single ``financials_latest.html``).
    Without it, ``output="html"`` writes the per-ticker file ``<OUTPUT_DIR>/<TICKER>_report.html``:
    that is the CLI's behaviour and nothing else writes per-ticker files (#173 D5/M18).

    A Fetch makes no provider call at all since #645 (avo 10 Nov 2026, option B: Yahoo is dropped). Every figure
    is a store read: the statements from the fundamentals serving layer, the market inputs from the prices store,
    the peers' multiples from both. A name the layer holds no annual year for gets no model and the
    board says :data:`NO_SEC_DATA`.
    """
    ticker = ticker.upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError(f"bad ticker: {ticker!r}")
    if no_fetch:
        # A store-only render read the statements and the payload the last Fetch stored in the old store
        # (``vendor_financials``, ``ticker_payload_cache``); they went with it (#860), so there is nothing to render.
        raise _NoCachedData(ticker)
    return _run(ticker, modules, output, assumptions, peers, report_path)


def _run(ticker: str, modules, output: str, assumptions: dict | None, peers: list[str] | None,
         report_path: Path | str | None) -> dict:
    """``run``'s body."""
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")

    # R5 (#88): the sector is the spine's (DCF bands, comps peers and the report header all read it).
    # A name the spine lacks is Unclassified.
    from revenuechaser.core import universe as _spine
    from .engines._inputs import PE_ONLY_SECTOR
    sector = _spine.gics_of(ticker, _spine.spine_gics([ticker])).sector
    bank = sector == PE_ONLY_SECTOR

    # The statements the models read are the SEC's, and since #645 the only ones: Yahoo's payload is gone, so the
    # name is the SEC entity's (or the spine's) and the currency is USD, the unit the layer's facts are tagged in
    # (a filer that tagged another is listed in the layer's ``non_usd_units``).
    annual, meta = _sec_statements(ticker)
    financials: dict = {"ticker": ticker, "name": _company_name(ticker, meta), "currency": "USD",
                        "annual": annual or [], "_fetched_at_iso": now, "fetched_at_iso": now}

    # G6 follow-up: the price, the market cap, the shares and the beta are the prices store's (G2); ``market`` is
    # the Source line's part that names the ones it gave and the ones nothing did.
    financials, market = market_inputs.overlay(ticker, financials)
    financials["enterprise_value"] = _enterprise_value(financials.get("market_cap"), annual or [])

    warnings: list[str] = []
    if annual is None:
        # avo, 10 Nov 2026 (option B): Yahoo is dropped, so there is no second source of statements. A name the
        # company facts hold no annual year for is stated, not modelled.
        financials["statements_meta"] = {**meta, "used": "none", "sec_lacks": []}
        financials["source"] = NO_SEC_DATA + " · " + market
        warnings.append(f"{ticker}: " + NO_SEC_DATA[0].lower() + NO_SEC_DATA[1:])
    else:
        # #645 G1: the facts carry the tax and interest concepts, so what the Source line names is this filer's
        # own gap, not a constant. A bank's model (P/E only) reads neither (delta review nit).
        lacking = _statement_gaps(annual, bank) + _tax_and_interest_gaps(annual, bank=bank)
        filed = meta.get("newest_filed")
        financials["statements_meta"] = {**meta, "used": "sec", "sec_lacks": lacking}
        financials["source"] = ("SEC company facts (statements" + (f", newest filed {filed}" if filed else "")
                                + ("; not in this filer's facts, so defaults: " + ", ".join(lacking)
                                   if lacking else "")
                                + ") · " + market)

    results: dict = {"ticker": ticker, "financials": financials, "modules": {}, "warnings": warnings}

    # Quick Remarks — her zaman üstte, the shared ``ticker_scores`` card and nothing else: its Yahoo fallback went
    # with #645, and Asymmetric Growth scores that card from the same SEC statements.
    results["quick_remarks"] = quick_remarks_engine.run_quick_remarks(ticker)

    financials["sector"] = sector
    financials["risk_free_rate"] = _stored_risk_free()
    for m in (() if annual is None else modules):
        m = m.strip().lower()
        if m in ("dcf", "dcf_engine"):
            results["modules"]["dcf"] = dcf_engine.run_dcf(financials, assumptions)
        elif m in ("3stmt", "three_statement", "3statement"):
            results["modules"]["three_statement"] = three_statement_engine.run_three_statement(financials, assumptions)
        elif m in ("comps", "comps_engine"):
            rungs: dict[str, str] = {}
            if peers:
                used_peers = list(peers)
            else:
                # FIN-3: the peers are the spine's (industry at the nearest market cap, then sector), never
                # a static list. A short ladder is reported, not silently padded — and a target the spine
                # does not carry is not a short ladder: it is the reason there is no ladder at all.
                spine_rows = _spine.classification_universe_rows(
                    operating_only=_spine.BOARD_OPERATING_ONLY["module_financials"])
                picked = peer_set(ticker, spine_rows)
                used_peers = [p["ticker"] for p in picked]
                rungs = {p["ticker"]: p["rung"] for p in picked}
                if target_row(ticker, spine_rows) is None:
                    warnings.append(f"comps: {ticker} is not in the spine universe (below the market-cap "
                                    f"floor, or an excluded security type), so no peers were picked")
                elif len(used_peers) < PEER_K:
                    warnings.append(f"comps: {len(used_peers)} of {PEER_K} peers — the spine industry and "
                                    f"sector have no name inside the cap band "
                                    f"({PEER_CAP_RATIO_BAND[0]:g}x to {PEER_CAP_RATIO_BAND[1]:g}x "
                                    f"the target's market cap)")
                # #91: part of a full ladder may come from the sector rung, which is a weaker comp than the
                # target's own industry. No number moves; the board has to say it.
                from_sector = sum(1 for p in picked if p["rung"] == "sector")
                if from_sector:
                    warnings.append(f"comps: {from_sector} of {len(used_peers)} peers come from the sector, "
                                    f"not {ticker}'s own industry")
            # #286: the peer figures are the store's, read in one call; this used to be one live Yahoo
            # ``.info`` request per peer.
            results["modules"]["comps"] = comps_engine.run_comps(
                financials, used_peers, fetch_many=comps_engine._default_fetch_many, rungs=rungs)
        elif m in ("credit", "credit_capacity"):
            results["modules"]["credit"] = credit_capacity_engine.run_credit_capacity(financials, assumptions)
        elif m in ("sensitivity", "sensitivity_engine"):
            results["modules"]["sensitivity"] = sensitivity_engine.run_sensitivity(financials, assumptions)
        else:
            warnings.append(f"unknown module skipped: {m}")

    # Engine warnings/errors (deduplicated, order preserved)
    seen: set[str] = set()
    for name, res in results["modules"].items():
        if isinstance(res, dict):
            for w in res.get("warnings", []):
                if w not in seen:
                    seen.add(w)
                    warnings.append(w)
            err = res.get("error")
            if err:
                msg = f"{name}: {err}"
                if msg not in seen:
                    seen.add(msg)
                    warnings.append(msg)

    # No provider banner (#299): since #645 this board makes no provider call, so there is nothing to report.
    # ``provider_health_html`` renders nothing for an absent health, which is what a clean run looked like anyway.

    # The shared filter kit's pool (#591): the picker's names, read from the store, never a network call.
    results["picker"] = picker_payload(ticker)

    paths: dict = {}
    if output in ("html", "both"):
        html = build_report_html(results)
        path = Path(report_path) if report_path else OUTPUT_DIR / f"{ticker}_report.html"
        # OUTPUT_DIR is created at import time only; if the (regenerable)
        # .cache tree was cleared while the server runs, recreate it here like
        # every other writer in the repo does. A bare write_text made a store-only
        # refresh die with FileNotFoundError and silently fall back to the network.
        path.parent.mkdir(parents=True, exist_ok=True)
        write_artifact(path, html)
        paths["html"] = str(path)

    return {"paths": paths, "results": results}
