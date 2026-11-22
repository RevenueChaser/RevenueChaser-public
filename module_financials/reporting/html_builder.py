"""HTML rapor üretici — engine çıktılarını Jinja2 dark-theme template'e enjekte eder."""
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from markupsafe import Markup

from revenuechaser.core import calendar as market_calendar
from revenuechaser.module_financials.config import RISK_FREE_MAX_AGE_DAYS
from revenuechaser.core.html_safe import script_json
from revenuechaser.core.reporting_common import (FILTERS_CSS, FILTERS_JS, THEME_CSS, THEME_JS, combobox_html,
                                                 filters_bar_html, help_html, provider_health_html,
                                                 watch_buttons_html, watchlist_html)

_TEMPLATES = Path(__file__).resolve().parent / "templates"
# Autoescape on: ticker, company, sector, source and warnings come from the
# request or the provider (M8 / ADR-X1, #144). Pre-rendered fragments go in as Markup.
_ENV = Environment(loader=FileSystemLoader(str(_TEMPLATES)), autoescape=True)

# The shared "What am I looking at?" box (#383 C3); fixed text, so it goes in as Markup.
HELP = help_html(
    "One company at a time: <b>Quick Remarks</b> (the stored scores for the ticker) on top, then the "
    "<b>financial model</b>: DCF, three-statement view, comparables, credit and sensitivity. "
    "<b>Fetch</b> rebuilds the report from what is already stored and makes <b>no provider call at all</b> "
    "(#645). The price, market cap, shares and beta are the <b>prices store</b>'s (its newest close, "
    f"at most {RISK_FREE_MAX_AGE_DAYS} days old); nothing stands in for one it does not hold, and the "
    "<b>Source</b> line names it as not stored. The models read the annual statements the company filed with "
    "the <b>SEC</b> (the fundamentals layer, re-read on each filing day) and nothing else, so a name whose "
    "company facts hold no annual year gets no model and the Source line says so; a line the facts do not "
    "carry shows the engines' labelled default, which the Source line also names. <b>Refresh</b> rebuilds the report for the ticker in the "
    "picker from the stored data with no network call; a ticker with nothing stored needs a Fetch first. The "
    "<b>filters</b> only narrow which names the <b>Ticker</b> picker offers \u2014 they never slice the "
    "statements below, which are always the one company the board fetched.")


def _fmt_usd(v) -> str:
    # Not a number is N/A: None, and a Jinja ``Undefined`` from a payload that has no such key at all (the peer
    # rows of a hand-built comps result have no market cap, #91). ``abs(Undefined)`` would raise and lose the page.
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return "N/A"
    a = abs(v)
    sign = "-" if v < 0 else ""
    if a >= 1e12:
        return f"{sign}${a / 1e12:,.2f}T"
    if a >= 1e9:
        return f"{sign}${a / 1e9:,.2f}B"
    if a >= 1e6:
        return f"{sign}${a / 1e6:,.2f}M"
    if a >= 1e3:
        return f"{sign}${a / 1e3:,.1f}K"
    return f"{sign}${a:,.0f}"


def _fmt_num(v, nd=2) -> str:
    if isinstance(v, str):
        return v          # a word the engine chose ("NM": a non-positive denominator has no multiple)
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return "N/A"      # None, and a key the payload does not carry at all (Jinja ``Undefined``)
    return f"{v:,.{nd}f}"


def _fmt_pct(v, nd=1) -> str:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return "N/A"      # None, and a key the payload does not carry at all (Jinja ``Undefined``)
    return f"{v * 100:,.{nd}f}%"


def _fmt_price(v) -> str:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return "N/A"      # None, and a key the payload does not carry at all (Jinja ``Undefined``)
    return f"${v:,.2f}"


def _fmt_day(iso: str | None) -> str:
    if not iso:
        return "N/A"
    text = str(iso)
    return text[:10] if len(text) >= 10 else text


def _fmt_friendly_day(iso: str | None) -> str:
    """``Tuesday, September 01, 2026 EOD`` for the top bar's ``Last sync`` (AGENTS.md §6, FIN-10).

    The day is the New York session the stamp belongs to (``core/calendar.session_for``, rule B), the same day the
    comps' "as of" names (``history._as_of``); the stamp is written in UTC, and read as UTC a Tuesday-evening Fetch
    said Wednesday. A fetch inside the session reads ``intraday``, not ``EOD`` (Financials review S4). A naive stamp
    is New York time; one outside the holiday table shows its date as it reads.
    """
    if not iso:
        return "N/A"
    try:
        moment = datetime.fromisoformat(str(iso).replace("Z", "+00:00"))
        stamp = market_calendar.session_for(moment if moment.tzinfo else moment.replace(tzinfo=market_calendar.NY))
    except ValueError:
        return _fmt_day(iso)
    word = "intraday" if stamp.quality == market_calendar.QUALITY_INTRADAY else "EOD"
    return f"{stamp.session_date:%A, %B %d, %Y} {word}"


def _fmt_tax_rate(assumptions: dict | None) -> str:
    """The model's tax rate, with where it came from: ``21.0% (median of 3 years)`` for the statements' median
    (#89), ``default 21.0% (no sector rate)`` when neither a statement nor the user set one (FIN-9 B).

    The "no sector rate" parenthetical is true, not decoration: no sector band carries a ``tax_rate``
    (``module_financials/engines/_inputs.default_tax_rate``), so the fallback is the single
    ``DEFAULT_TAX_RATE`` for every sector and the row must not read as a sector-specific one.
    """
    a = assumptions or {}
    rate = _fmt_pct(a.get("tax_rate"))
    source = str(a.get("tax_rate_source") or "")
    if source == "default":
        return f"default {rate} (no sector rate)"
    if source.startswith("statements (median of "):
        return f"{rate} ({source[len('statements ('):-1]})"
    return rate


def _or_default(text: str, is_default=False) -> str:
    """``default 30.0%``: a shown value the model took from a built-in constant, because neither the user nor the
    data gave one (reviews S1 and S2, the tax row's wording)."""
    return f"default {text}" if is_default else text


_ENV.filters["usd"] = _fmt_usd
_ENV.filters["num"] = _fmt_num
_ENV.filters["pct"] = _fmt_pct
_ENV.filters["price"] = _fmt_price
_ENV.filters["day"] = _fmt_day
_ENV.filters["friendly_day"] = _fmt_friendly_day
_ENV.filters["tax_rate"] = _fmt_tax_rate
_ENV.filters["or_default"] = _or_default
# The watch-list pair (PR 4): ``watch_buttons_html`` escapes the ticker and gives nothing for one the dashboard
# refuses, so its output is markup the template takes as it is.
_ENV.globals["watch_pair"] = lambda ticker: Markup(watch_buttons_html(ticker))


def build_report_html(results: dict) -> str:
    """results -> tam HTML string."""
    financials = results.get("financials", {})
    modules = results.get("modules", {})
    ticker = results.get("ticker", financials.get("ticker", ""))

    picker = results.get("picker") or {}

    # Quick Remarks bölümü (ticker_scores'dan beslenir; her zaman üstte)
    quick_remarks = results.get("quick_remarks")
    if quick_remarks:
        from .quick_remarks_html import render_quick_remarks_section
        # The fragment escapes its own fields (FN-1).
        quick_remarks_section = Markup(render_quick_remarks_section(quick_remarks))
    else:
        quick_remarks_section = ""

    ctx = {
        "ticker": ticker,
        # The SEC entity name, else the spine's (``run._company_name``); Yahoo's ``longName`` went with #645.
        "company": financials.get("name") or ticker,
        "sector": financials.get("sector"),
        "price": financials.get("current_price"),
        # The prices store's session of that price (G6 follow-up); None when the store held none.
        "price_session": (financials.get("market_meta") or {}).get("price_session"),
        "currency": financials.get("currency", "USD"),
        "shares_outstanding": financials.get("shares_outstanding"),
        "market_cap": financials.get("market_cap"),
        # Since #645 the EV is the store's bridge (cap + total debt - cash of the newest stored fiscal year,
        # ``run._enterprise_value``), the same one the peer side uses, so the target and its comps are on one
        # basis. It was Yahoo's ``enterpriseValue`` — its own newest quarter — until Yahoo was dropped.
        "enterprise_value": financials.get("enterprise_value"),
        "source": financials.get("source", "SEC company facts"),
        "data_date": financials.get("_fetched_at_iso") or financials.get("fetched_at_iso"),
        "quick_remarks": quick_remarks,
        "quick_remarks_section": quick_remarks_section,
        "help_block": Markup(HELP),
        # Escapes every provider string itself (Common K3); empty for a clean run.
        "provider_banner": Markup(provider_health_html(results.get("provider_health"))),
        # Every Fetch of any ticker, newest first (#383 C7); escapes its own strings.
        "history_block": Markup(""),
        "watch_mount": Markup(watchlist_html("financials")),
        "dcf": modules.get("dcf"),
        "three_statement": modules.get("3stmt") or modules.get("three_statement"),
        "comps": modules.get("comps"),
        "credit": modules.get("credit"),
        "sensitivity": modules.get("sensitivity"),
        "warnings": results.get("warnings", []),
        # The shared filter kit (#591). The pool and its meta are built by the runner (a store read), so this
        # builder stays store-free; without them the bar mounts over no rows and the picker offers none.
        "theme_css": Markup(THEME_CSS),
        "theme_js": Markup(THEME_JS),
        "filters_css": Markup(FILTERS_CSS),
        "filters_js": Markup(FILTERS_JS),
        "filters_bar": Markup(filters_bar_html("rc-filters")),
        "ticker_combo": Markup(combobox_html("ticker-combo", "ticker-combo-label", "Search ticker or name")),
        "picker_rows_json": Markup(script_json(picker.get("rows") or [])),
        "picker_meta_json": Markup(script_json(picker.get("meta") or {"board": "financials"})),
        "ticker_json": Markup(script_json(ticker)),
    }
    return _ENV.get_template("report_base.html.j2").render(**ctx)
