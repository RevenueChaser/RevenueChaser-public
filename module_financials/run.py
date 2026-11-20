"""Orkestrasyon: ticker -> Quick Remarks + Fin Model engine'leri -> rapor."""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

from RevenueChaser.core.reporting_common import filters_meta, write_artifact

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
from RevenueChaser.core.providers import yfinance as yfinance_client


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
    from RevenueChaser.core import risk_free
    return risk_free.stored_dgs10(max_age_days=RISK_FREE_MAX_AGE_DAYS)


# The statement fields the SEC facts carry (``sec_edgar.CONCEPTS``) that the engines read, by the engines' names. A
# field the facts do not carry (pre-tax income, tax provision, interest expense, current assets and liabilities) is
# left out, so the engines' labelled defaults show (review S1).
_SEC_FIELDS = ("revenue", "cost_of_revenue", "gross_profit", "ebit", "net_income", "diluted_shares", "basic_shares",
               "rd_expense", "operating_cash_flow", "capex", "depreciation", "total_assets", "total_equity", "cash",
               "short_term_investments", "receivables", "inventory", "payables", "total_debt")
# shortcut: the newest five fiscal years (Yahoo gave four); read more when a model projects from a longer history.
SEC_YEARS = 5
# What a run on the SEC's statements always takes a default for, because the facts never carry it (no pre-tax
# income, tax provision or interest expense): the Source line names it (Opus review M1; avo, 29 Oct 2026: stay on the
# SEC's statements and say so, rather than letting these send every run to Yahoo's).
# shortcut: named, not filled; upgrade when the layer serves the tax and interest concepts (#271).
NOT_IN_FACTS = ("tax rate", "interest expense")


def _financials_record(rec: dict) -> dict:
    """One SEC annual record (``sec_edgar.extract_annual``'s shape) as the engines read a year: the fields above,
    ``capital_expenditure`` beside ``capex``, ``period_end`` (the revenue's) and EBITDA as operating income plus
    depreciation when the year has both."""
    from RevenueChaser.core import fiscal_year
    from RevenueChaser.core.config import to_float
    end = fiscal_year.period_end(rec)
    out: dict = {"fiscal_year": rec.get("fiscal_year"), "period_end": end.isoformat() if end else None}
    for f in _SEC_FIELDS:
        v = to_float(rec.get(f))
        if v is not None:
            out[f] = v
    if "capex" in out:
        out["capital_expenditure"] = out["capex"]
    if "ebit" in out and "depreciation" in out:
        out["ebitda"] = out["ebit"] + out["depreciation"]
    return out


def _statement_gaps(annual: list[dict], bank: bool = False) -> list[str]:
    """The base-year inputs the engines would run on a labelled default for (``dcf_engine``): revenue, EBITDA,
    depreciation and capex of the newest year with revenue (``fiscal_year.anchor``), and working capital in every
    year, except for a bank (``bank``), whose models never read it (P/E only, Opus review N4)."""
    from RevenueChaser.core import fiscal_year
    from RevenueChaser.core.config import to_float
    from .engines.dcf_engine import _nwc
    i = fiscal_year.anchor(annual)
    latest = annual[i] if i is not None else {}
    gaps = sorted(f for f in ("revenue", "ebitda", "depreciation") if to_float(latest.get(f)) is None)
    if to_float(latest.get("capex")) is None and to_float(latest.get("capital_expenditure")) is None:
        gaps = sorted(gaps + ["capex"])
    if not bank and not any(_nwc(r) is not None for r in annual):
        gaps.append("working capital")
    return gaps


def _statements_choice(sec: list[dict], yahoo: list[dict], bank: bool = False) -> tuple[str, list[str]]:
    """``(used, what the SEC's statements lack)``: which annual statements a run models, ``"sec"`` or ``"yahoo"``.

    The SEC's, unless Yahoo's newest year is newer, or is the same year and gives an input the SEC's lacks (the
    real-data check of 29 Oct 2026: the SEC facts carry no depreciation for MSFT, ORCL, AMD and AVGO, no working
    capital for a filer without an inventory line, and no year after 2020 for an IFRS filer such as TM, so their DCF
    ran on defaults Yahoo did not need). Default chosen, change if avo prefers the SEC's statements always.

    A year is the newest one with revenue (``fiscal_year.anchor``), so a newer year with only a balance sheet is no
    newer year (Opus review S2). With ``"sec"`` the list is every input the SEC's year lacks, which then runs on a
    default and is named on the Source line (Opus review S1); with ``"yahoo"`` it is what Yahoo's gives that the
    SEC's lacks.

    shortcut: a whole-source choice per run, never a field-by-field mix; upgrade when the layer serves depreciation's
    other tags and current assets and liabilities (#271; then the SEC's statements stand alone)."""
    from RevenueChaser.core import fiscal_year
    sec_gaps = _statement_gaps(sec, bank)
    if not yahoo:
        return "sec", sec_gaps

    def year(rows):
        i = fiscal_year.anchor(rows)
        text = str(rows[i].get("fiscal_year") or "")[:4] if i is not None else ""
        return int(text) if text.isdigit() else None

    s, y = year(sec), year(yahoo)
    if s is not None and y is not None and s != y:
        return ("sec", sec_gaps) if s > y else ("yahoo", [f"the fiscal year {y}"])
    lacking = [g for g in sec_gaps if g not in _statement_gaps(yahoo, bank)]
    return ("yahoo", lacking) if lacking else ("sec", sec_gaps)


def _sec_statements(ticker: str) -> tuple[list[dict], dict] | None:
    """``(annual, meta)``: the newest ``SEC_YEARS`` fiscal years from the fundamentals layer (G6, build plan PR 15:
    "statement inputs from the store"), or None when it holds no year for ``ticker``. They end on
    the newest year with revenue: a later year the layer serves with only balance-sheet fields is not a base year
    (Opus review S2)."""
    from RevenueChaser.core import fiscal_year, fundamentals_layer
    annual, _quarterly, meta = fundamentals_layer.records(ticker)
    i = fiscal_year.anchor(annual)
    if i is None:
        return None
    annual = annual[:i + 1]
    return [_financials_record(r) for r in annual[-SEC_YEARS:]], meta


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
    from RevenueChaser.core import universe as _spine

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

    A Fetch asks Yahoo afresh each time and stores nothing (the payload cache went with the old store, #860).
    """
    ticker = ticker.upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise ValueError(f"bad ticker: {ticker!r}")
    if no_fetch:
        # A store-only render read the statements and the payload the last Fetch stored in the old store
        # (``vendor_financials``, ``ticker_payload_cache``); they went with it (#860), so there is nothing to render.
        raise _NoCachedData(ticker)
    # The board renders ``provider_health_html`` (reporting/html_builder), so this run counts its own Yahoo
    # reads (#299): a failed statement or peer read raises the amber banner instead of passing for a complete
    # board. Its own scope, not ``reset_health()``, because the client's counter is shared with every other
    # board and the dashboard runs two job workers. SEC EDGAR is not in the banner: since G6 the statements
    # come from the fundamentals serving layer (``_sec_statements``), which makes no request.
    with yfinance_client.health_scope() as provider_health:
        return _run(ticker, modules, output, assumptions, peers, report_path, provider_health)


def _run(ticker: str, modules, output: str, assumptions: dict | None, peers: list[str] | None,
         report_path: Path | str | None, provider_health) -> dict:
    """``run``'s body, inside its provider-health scope."""
    financials = yfinance_client.get_financials(ticker)
    financials.setdefault("_fetched_at_iso", datetime.now(timezone.utc).isoformat(timespec="seconds"))
    financials.setdefault("fetched_at_iso", financials["_fetched_at_iso"])

    # R5 (#88): the sector is the spine's (DCF bands, comps peers and the report header all read it);
    # the yfinance sector no longer feeds GICS. A name the spine lacks is Unclassified.
    from RevenueChaser.core import universe as _spine
    from .engines._inputs import PE_ONLY_SECTOR
    sector = _spine.gics_of(ticker, _spine.spine_gics([ticker])).sector

    # G6 follow-up: the price, the market cap, the shares and the beta are the prices store's (G2), each Yahoo's only
    # where the store has none; ``market`` is the Source line's part that says which.
    financials, market = market_inputs.overlay(ticker, financials)

    # G6 (build plan PR 15): on the fundamentals layer the statements the models read are the SEC's; Yahoo's
    # payload keeps the name (and whatever market input the prices store does not give).
    sec = _sec_statements(ticker)
    if sec is not None:
        annual, meta = sec
        used, lacking = _statements_choice(annual, financials.get("annual") or [], bank=sector == PE_ONLY_SECTOR)
        if used == "sec":
            # Delta review nit: a bank's model (P/E only) reads neither a tax rate nor an interest expense.
            if sector != PE_ONLY_SECTOR:
                lacking = lacking + list(NOT_IN_FACTS)
            filed = meta.get("newest_filed")
            financials = {**financials, "annual": annual,
                          "statements_meta": {**meta, "used": "sec", "sec_lacks": lacking},
                          "source": "SEC company facts (statements" + (f", newest filed {filed}" if filed else "")
                                    + ("; not in the facts, so defaults: " + ", ".join(lacking) if lacking else "")
                                    + ") · " + market}
        else:
            financials = {**financials, "statements_meta": {**meta, "used": "yahoo", "sec_lacks": lacking},
                          "source": "Yahoo (statements: the SEC company facts lack " + ", ".join(lacking)
                                    + ") · " + market}
    else:
        financials = {**financials, "source": "Yahoo (statements) · " + market}

    warnings: list[str] = []
    results: dict = {"ticker": ticker, "financials": financials, "modules": {}, "warnings": warnings}

    # Quick Remarks — her zaman üstte (ticker_scores'dan beslenir, yfinance fallback). FIN-5: it is handed the
    # payload this run already has, so it scores from it instead of fetching the same financials a second time.
    # ``no_fetch=False``: a store-only render never reaches here (it raised ``_NoCachedData`` above).
    results["quick_remarks"] = quick_remarks_engine.run_quick_remarks(ticker, no_fetch=False,
                                                                     financials=financials)

    financials["sector"] = sector
    financials["risk_free_rate"] = _stored_risk_free()
    for m in modules:
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
            results["modules"]["comps"] = comps_engine.run_comps(financials, used_peers,
                                                                fetch_info=comps_engine._default_fetch,
                                                                rungs=rungs)
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

    # The banner the board already renders (#299); zeros render nothing, so a clean run looks unchanged.
    results["provider_health"] = provider_health.health()

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
