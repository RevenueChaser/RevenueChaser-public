"""yfinance client — finansal tabloları (income/balance/cashflow/info) normalize eder.

yfinance DataFrames'i (satır=kalem, kolon=fiskal yıl) standart bir dict yapısına
dönüştürür: ``financials["annual"]`` kronolojik (eskiden yeniye) kayıt listesi.
"""
from __future__ import annotations

import contextlib
import logging
import threading
from typing import Any

import pandas as pd

from ..config import to_float
from . import spend, yf_session
from .result import ProviderHealth, ProviderResult

logger = logging.getLogger(__name__)

# Every ``.info`` and statement read, and the ones that raised (Common K3): a failed read is counted for the
# board banner, not only logged. A run reads it with ``health()`` after ``reset_health()``.
_HEALTH = ProviderHealth("yfinance")

# The runs counting on this thread (#299). This module's counter is one global, and the dashboard runs two job
# workers, so a board that reset it would zero another board's run in flight; a run opens its own
# ``health_scope`` instead and reads only its own calls. Thread-local, because a job holds one thread.
_SCOPES = threading.local()

# The threads whose caller keeps its own book on the day's ledger (#1277). The builder counts each Yahoo read it
# asks for with ``ctx.count`` (``rcdata/build/fundamentals/fx_rates.py``, ``estimates.py``) and writes the same
# ``provider_calls_daily`` row this module's spend count writes, so counting here as well doubled the day and
# ``rcdata.caps`` stopped a build at half the reads it should allow. This is ``UWClient``'s door in the shape a
# module-level client can have it (``unusual_whales.py``: installing the observers takes the counting over).
# Thread-local, like ``_SCOPES`` and for the same reason: a job holds one thread, and the dashboard runs two job
# workers, so a process-wide flag would silence the other worker's reads too.
_OWNED = threading.local()

# The annual window a Fetch serves. A store-only Refresh reads the same window back through
# ``vendor_data.read_financials``: the store keeps every period it ever saw, so once a seventh fiscal year is
# stored an uncapped reader would average NWC/revenue over more years than the Fetch did and disagree with it.
MAX_YEARS = 6


def health() -> dict:
    """The Yahoo reads since the last ``reset_health()``, in the shared provider-health shape."""
    return _HEALTH.health()


def reset_health() -> None:
    _HEALTH.reset()


def _count(error: str | None = None, endpoint: str = "") -> None:
    """Count one Yahoo read for the shared global, for every scope open on this thread, and for the day's spend.

    The day's counter (``providers/spend.py``, #166) is the one ``rcdata.caps`` reads and the Spend card renders,
    and its unit for Yahoo is one **read**, not one HTTP request -- the same unit the builder's Yahoo source
    counts in (``rcdata/build/sources/yahoo.py``), because the library fetches its own cookie and crumb and a
    read may be several requests. Both halves of the app and the builder therefore add up in one row.

    A caller inside :func:`spend_owned_by_caller` counts that row itself, so the day's counter is left alone here
    (#1277). The banner's counters are not: a read is a read, whoever books its spend.
    """
    _HEALTH.call(error=error, endpoint=endpoint)
    for health in getattr(_SCOPES, "stack", ()):
        health.call(error=error, endpoint=endpoint)
    if not getattr(_OWNED, "depth", 0):
        spend.count("yfinance", calls=1, failures=1 if error is not None else 0)


def attempt(call, endpoint: str = "", empty=None, count: bool = True) -> tuple[Any, str | None]:
    """One Yahoo read, as ``(value, error text or None)``: counted for the banner and retried once after a 401.

    **Every** yfinance read in the tree belongs here, for two reasons.

    * It is counted through :func:`_count`, so the read lands in the module global **and** in every
      ``health_scope`` open on this thread (#299). A caller that counts on ``_HEALTH`` itself is invisible to
      the scope its own board opened.
    * Yahoo's HTTP 401 "Invalid Crumb" is cured by one session reset, and until it is, every later read of the
      process fails the same way (#402). ``yf_session.recover`` decides and resets; this is what calls it.
      #402 built that cure for ``load_ohlc``, which went with the old bar path, so ``recover`` was left with no
      caller at all and the cure was inert (measured on ``main`` c2b2c88, 20 Nov 2026).

    yfinance does not always raise a refusal: a refused ``history`` comes back as an empty frame with the 401 on
    the ``yfinance`` logger. Pass ``empty`` — a predicate over the value — to have such an answer consult
    ``recover`` too, so an empty-because-refused read is retried and an empty-because-no-data read is not (only
    a pending 401 makes ``recover`` say yes).

    The error text is the caller's to render; a failed read is counted with it either way.

    ``count=False`` buys the session reset and the retry **without** the counting, for the one caller that
    decides for itself what the read was worth: Swing's ``.info`` refetch keeps an expired payload and counts
    that as a failed read (#80, #259), which this cannot see, because the answer came back fine.
    """
    started = yf_session.clock()
    try:
        value = call()
    except Exception as exc:  # noqa: BLE001 - every yfinance read is network
        if not yf_session.recover(started, exc):
            return _failed(exc, endpoint, count)
        try:
            value = call()
        except Exception as exc:  # noqa: BLE001 - the retry after the reset is the last one
            return _failed(exc, endpoint, count)
    else:
        if empty is not None and _is_empty(empty, value) and yf_session.recover(started):
            try:
                value = call()
            except Exception as exc:  # noqa: BLE001
                return _failed(exc, endpoint, count)
    if count:
        _count(endpoint=endpoint)
    return value, None


def read(call, endpoint: str = "", default=None, empty=None, count: bool = True):
    """:func:`attempt` without the error text: the value, or ``default`` when the read failed."""
    value, error = attempt(call, endpoint=endpoint, empty=empty, count=count)
    return default if error is not None else value


def _failed(exc: BaseException, endpoint: str, count: bool = True) -> tuple[None, str]:
    """Count one failed Yahoo read and give its text back to the caller."""
    text = str(exc)[:200] or type(exc).__name__
    logger.debug("yfinance %s: %s", endpoint or "read", text)
    if count:
        _count(error=text, endpoint=endpoint)
    return None, text


def _is_empty(empty, value) -> bool:
    """``empty(value)``; a predicate that itself raises means "not empty", never a crash in a read path."""
    try:
        return bool(empty(value))
    except Exception:  # noqa: BLE001 - a broken predicate must not fail the read
        return False


@contextlib.contextmanager
def spend_owned_by_caller():
    """The reads this thread makes inside the block are **not** counted on the day's spend ledger (#1277).

    For the one caller that keeps its own book in the same ``provider_calls_daily`` row: a builder dataset, which
    counts every read it asks for with ``ctx.count`` before it asks. Without this the read was counted twice --
    once by the dataset, once here -- and the counter ``rcdata.caps`` reads for the day caps ran at double, so a
    build stopped at half the reads its cap allowed and the Spend card overstated the day.

    This is ``UWClient``'s contract (``unusual_whales.py``: a caller that installs the observers owns the
    counting) for a module-level client: a block instead of an instance. It changes nothing else -- the module
    global, every open ``health_scope`` and the retry behaviour are exactly what they are outside the block, so a
    board banner still shows the reads. The blocks nest, and the block ends with its body, an exception included.
    """
    depth = getattr(_OWNED, "depth", 0)
    _OWNED.depth = depth + 1
    try:
        yield
    finally:
        _OWNED.depth = depth


@contextlib.contextmanager
def health_scope(provider: str = "yfinance"):
    """One run's own Yahoo call accounting, isolated from every other board's (#299).

    Yields a :class:`~revenuechaser.core.providers.result.ProviderHealth` that counts the reads this thread makes
    inside the block, and nothing else: the shared global keeps counting everything. The board hands
    ``health.health()`` to its payload, which ``provider_health_html`` turns into the amber banner.
    """
    health = ProviderHealth(provider)
    stack = getattr(_SCOPES, "stack", None)
    if stack is None:
        stack = _SCOPES.stack = []
    stack.append(health)
    try:
        yield health
    finally:
        stack.remove(health)

# Kanonik alan -> olası yfinance satır etiketleri (öncelik sırasıyla)
_INCOME_FIELDS = {
    "revenue": ["Total Revenue", "Operating Revenue", "Total Operating Revenues"],
    "cost_of_revenue": ["Cost Of Revenue", "Cost of Goods Sold", "Total Expenses"],
    "gross_profit": ["Gross Profit"],
    "ebit": ["EBIT", "Operating Income", "Operating Income Or Loss"],
    "ebitda": ["EBITDA", "Normalized EBITDA"],
    "pretax_income": ["Pretax Income", "Income Before Tax"],
    "tax_provision": ["Tax Provision", "Income Tax Expense"],
    "net_income": ["Net Income", "Net Income Common Stockholders"],
    # "Net Interest Income" is deliberately absent: it is income minus expense, not an expense (#169a).
    "interest_expense": ["Interest Expense", "Interest Expense Non Operating"],
    "diluted_shares": ["Diluted Average Shares", "Diluted Weighted Average Shares"],
    "basic_shares": ["Basic Average Shares", "Basic Weighted Average Shares"],
    "rd_expense": ["Research And Development", "Research & Development"],
}

_CASHFLOW_FIELDS = {
    "operating_cash_flow": [
        "Operating Cash Flow", "Cash Flow From Continuing Operating Activities",
        "Total Cash From Operating Activities",
    ],
    "capital_expenditure": [
        "Capital Expenditure", "Capital Expenditures", "Purchase Of Property Plant And Equipment",
    ],
    "depreciation": [
        "Depreciation & Amortization", "Depreciation And Amortization",
        "Depreciation Amortization Depletion",
    ],
}

_BALANCE_FIELDS = {
    "total_assets": ["Total Assets"],
    "total_equity": ["Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"],
    "cash": ["Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments", "Cash"],
    "short_term_debt": ["Current Debt", "Current Debt And Capital Lease Obligation", "Short Term Debt"],
    "long_term_debt": ["Long Term Debt", "Long Term Debt And Capital Lease Obligation"],
    "total_debt": ["Total Debt"],
    "receivables": ["Accounts Receivable", "Net Receivables", "Accounts Receivables Net"],
    "inventory": ["Inventory", "Inventories"],
    "payables": ["Accounts Payable", "Payables"],
    "current_assets": ["Current Assets"],
    "current_liabilities": ["Current Liabilities"],
}


def _label_map(df: pd.DataFrame) -> dict[str, pd.Series]:
    """{küçük-harfli etiket: seri} haritası (boşluk/altçizgi normalize)."""
    out: dict[str, pd.Series] = {}
    for idx, row in df.iterrows():
        label = str(idx).strip().lower().replace("_", " ")
        if label and label != "nan":
            out[label] = row
    return out


def _pick(series_map: dict[str, pd.Series], candidates: list[str]) -> pd.Series | None:
    for cand in candidates:
        key = cand.strip().lower().replace("_", " ")
        if key in series_map:
            return series_map[key]
    return None


def _years(df: pd.DataFrame, max_years: int = MAX_YEARS) -> list[Any]:
    """Kronolojik (eskiden yeniye) geçerli yıl kolonları."""
    cols = []
    for c in df.columns:
        s = df[c]
        if s.notna().any():
            cols.append(c)
    cols.sort()  # datetime kolonları sıralanabilir
    return cols[-max_years:]


def _col_values(series: pd.Series | None, cols: list[Any]) -> list[float | None]:
    if series is None:
        return [None] * len(cols)
    return [to_float(series.get(c)) for c in cols]


def _sum_series(maps: dict[str, pd.Series], groups: list[list[str]], cols: list[Any]) -> list[float | None]:
    """Sums one value per group and year (e.g. short-term + long-term debt).

    The labels of a group are alternatives for the same item, in priority order: per year the first label with
    a value counts and the others are never added (#169b: "Current Debt" plus its capital-lease variant counted the
    same debt twice). A year where no group has a value is None, not 0.0 (DF38).
    """
    group_rows = []
    for labels in groups:
        rows = [maps.get(c.strip().lower().replace("_", " ")) for c in labels]
        group_rows.append([r for r in rows if r is not None])
    total: list[float | None] = []
    for c in cols:
        year_total: float | None = None
        for rows in group_rows:
            v = next((x for x in (to_float(r.get(c)) for r in rows) if x is not None), None)
            if v is not None:
                year_total = v if year_total is None else year_total + v
        total.append(year_total)
    return total


def get_financials(ticker: str, max_years: int = MAX_YEARS) -> dict:
    """yfinance'tan normalize finansal tabloları çeker.

    Returns:
        {"ticker", "info", "sector", "annual": [ {fiscal_year, revenue, ...} ], ...}
    """
    import yfinance as yf

    t = yf.Ticker(ticker)
    info = _read_info(t, ticker)

    def _stmt(attrs: tuple[str, ...]) -> pd.DataFrame:
        for attr in attrs:
            # ``attempt`` counts the read and gives a refused session one reset and one retry (#402, #100);
            # a statement this version does not carry is the next label's turn, as before.
            df = read(lambda attr=attr: getattr(t, attr), endpoint=f"{ticker}.{attr}")
            if isinstance(df, pd.DataFrame) and not df.empty:
                return df
        return pd.DataFrame()

    income = _stmt(("income_stmt", "financials"))
    cashflow = _stmt(("cashflow", "cash_flow"))
    balance = _stmt(("balance_sheet",))

    annual: list[dict] = []

    # Ortak yıl ekseni: üç tablodan en geniş kapsamı kullan
    year_sets = [set(_years(df, max_years)) for df in (income, cashflow, balance) if not df.empty]
    if not year_sets:
        return {"ticker": ticker, "info": info, "sector": _sector(info), "annual": annual}

    common = sorted(set.union(*year_sets))

    inc_map = _label_map(income) if not income.empty else {}
    cf_map = _label_map(cashflow) if not cashflow.empty else {}
    bal_map = _label_map(balance) if not balance.empty else {}

    revenue = _col_values(_pick(inc_map, _INCOME_FIELDS["revenue"]), common)
    ebit = _col_values(_pick(inc_map, _INCOME_FIELDS["ebit"]), common)
    ebitda = _col_values(_pick(inc_map, _INCOME_FIELDS["ebitda"]), common)
    net_income = _col_values(_pick(inc_map, _INCOME_FIELDS["net_income"]), common)
    tax_provision = _col_values(_pick(inc_map, _INCOME_FIELDS["tax_provision"]), common)
    pretax_income = _col_values(_pick(inc_map, _INCOME_FIELDS["pretax_income"]), common)
    gross_profit = _col_values(_pick(inc_map, _INCOME_FIELDS["gross_profit"]), common)
    cost_of_revenue = _col_values(_pick(inc_map, _INCOME_FIELDS["cost_of_revenue"]), common)
    interest_expense = _col_values(_pick(inc_map, _INCOME_FIELDS["interest_expense"]), common)
    diluted_shares = _col_values(_pick(inc_map, _INCOME_FIELDS["diluted_shares"]), common)
    basic_shares = _col_values(_pick(inc_map, _INCOME_FIELDS["basic_shares"]), common)
    rd_expense = _col_values(_pick(inc_map, _INCOME_FIELDS["rd_expense"]), common)

    ocf = _col_values(_pick(cf_map, _CASHFLOW_FIELDS["operating_cash_flow"]), common)
    capex_raw = _col_values(_pick(cf_map, _CASHFLOW_FIELDS["capital_expenditure"]), common)
    # yfinance capex'i negatif (nakit çıkışı) raporlar -> çıkış büyüklüğü olarak pozitife çevir
    capex = [abs(v) if v is not None else None for v in capex_raw]
    depreciation = _col_values(_pick(cf_map, _CASHFLOW_FIELDS["depreciation"]), common)

    total_assets = _col_values(_pick(bal_map, _BALANCE_FIELDS["total_assets"]), common)
    total_equity = _col_values(_pick(bal_map, _BALANCE_FIELDS["total_equity"]), common)
    cash = _col_values(_pick(bal_map, _BALANCE_FIELDS["cash"]), common)
    receivables = _col_values(_pick(bal_map, _BALANCE_FIELDS["receivables"]), common)
    inventory = _col_values(_pick(bal_map, _BALANCE_FIELDS["inventory"]), common)
    payables = _col_values(_pick(bal_map, _BALANCE_FIELDS["payables"]), common)
    current_assets = _col_values(_pick(bal_map, _BALANCE_FIELDS["current_assets"]), common)
    current_liabilities = _col_values(_pick(bal_map, _BALANCE_FIELDS["current_liabilities"]), common)

    # Toplam borç: "Total Debt" yoksa kısa+uzun vadeli borç toplamı
    total_debt = _col_values(_pick(bal_map, _BALANCE_FIELDS["total_debt"]), common)
    if all(v is None for v in total_debt):
        total_debt = _sum_series(
            bal_map,
            [_BALANCE_FIELDS["short_term_debt"], _BALANCE_FIELDS["long_term_debt"]],
            common,
        )

    for i, year in enumerate(common):
        annual.append({
            "fiscal_year": _year_label(year),
            "period_end": _period_end(year),
            "revenue": revenue[i],
            "cost_of_revenue": cost_of_revenue[i],
            "gross_profit": gross_profit[i],
            "ebit": ebit[i],
            "ebitda": ebitda[i],
            "pretax_income": pretax_income[i],
            "tax_provision": tax_provision[i],
            "net_income": net_income[i],
            "interest_expense": interest_expense[i],
            "diluted_shares": diluted_shares[i],
            "basic_shares": basic_shares[i],
            "rd_expense": rd_expense[i],
            "operating_cash_flow": ocf[i],
            "capital_expenditure": capex[i],
            "depreciation": depreciation[i],
            "total_assets": total_assets[i],
            "total_equity": total_equity[i],
            "cash": cash[i],
            "receivables": receivables[i],
            "inventory": inventory[i],
            "payables": payables[i],
            "current_assets": current_assets[i],
            "current_liabilities": current_liabilities[i],
            "total_debt": total_debt[i],
        })

    return _payload(ticker, info, annual)


def _payload(ticker: str, info: dict, annual: list[dict]) -> dict:
    return {
        "ticker": ticker.upper(),
        "info": info,
        "sector": _sector(info),
        "annual": annual,
        "shares_outstanding": to_float(info.get("sharesOutstanding")),
        "market_cap": to_float(info.get("marketCap")),
        "enterprise_value": to_float(info.get("enterpriseValue")),
        "beta": to_float(info.get("beta")),
        "current_price": to_float(info.get("currentPrice")),
        "currency": info.get("currency", "USD"),
        "source": "yfinance",
    }


def _read_info(t, ticker: str) -> dict:
    """One ticker's ``.info``, counted for the banner and retried once after a 401 session reset (#402, #100)."""
    return read(lambda: t.info or {}, endpoint=f"{ticker}.info", default={})


def get_info(ticker: str) -> dict:
    """The ``get_financials`` payload from ONE Yahoo request (``.info``), with no statements (#150 U13).

    ``annual`` is empty and the payload carries ``info_only``: ``cache`` hands such a row only to a
    reader that asks for it (Asymmetric Growth, whose annual figures come from EDGAR), so no other
    board reads it as a full payload.
    """
    import yfinance as yf

    out = _payload(ticker, _read_info(yf.Ticker(ticker), ticker), [])
    out["info_only"] = True
    return out


# The four ``earningsTrend`` blocks D14 stores (#323), as yfinance's ``Ticker.get_<block>`` methods name them.
TREND_BLOCKS = ("earnings_estimate", "revenue_estimate", "eps_trend", "eps_revisions")


def get_earnings_trend(ticker: str) -> ProviderResult:
    """A ticker's analyst estimates (E0 D14, #323): ``{block: {field: {period: value}}}`` for ``TREND_BLOCKS``,
    each block as ``get_<block>(as_dict=True)`` gives it (periods ``0q``, ``+1q``, ``0y``, ``+1y``; a missing value
    is NaN).

    yfinance 1.7.0 reads all four blocks from ONE quoteSummary ``earningsTrend`` request, cached on the ticker's
    ``Analysis`` (``scrapers/analysis.py``); the PC's installed version is checked by the M1 probe
    (``module_earnings_radar/inputs/estimates.probe``). ``ok`` with empty blocks when Yahoo has none, ``failed``
    when the read raised. Counted as one call in ``health()``.
    """
    import yfinance as yf

    endpoint = f"{ticker}.earningsTrend"
    try:
        t = yf.Ticker(ticker)
        blocks = {name: getattr(t, f"get_{name}")(as_dict=True) for name in TREND_BLOCKS}
    except Exception as exc:  # noqa: BLE001 - network or a changed library; counted for the banner
        logger.debug("yfinance earningsTrend %s: %s", ticker, exc)
        _count(error=str(exc)[:200] or type(exc).__name__, endpoint=endpoint)
        return ProviderResult("failed", {}, {"error": type(exc).__name__, "attempts": 1}, endpoint)
    _count()
    return ProviderResult("ok", {k: v if isinstance(v, dict) else {} for k, v in blocks.items()}, None, endpoint)


def get_fx_history(currency: str, start: str | None = None) -> ProviderResult:
    """Yahoo's daily close of ``<currency>USD=X`` (#535): ``{day: usd_per_unit}``, the whole history when ``start`` is
    None, else from ``start`` (ISO day). A NaN close is left out. ``ok`` with an empty dict when Yahoo has no rows,
    ``failed`` when the read raised. Counted as one call in ``health()``."""
    import math

    import yfinance as yf

    endpoint = f"{currency}USD=X.history"
    try:
        t = yf.Ticker(f"{currency}USD=X")
        frame = t.history(start=start, auto_adjust=False) if start else t.history(period="max", auto_adjust=False)
    except Exception as exc:  # noqa: BLE001 - network or a changed library; counted for the banner
        logger.debug("yfinance fx %s: %s", currency, exc)
        _count(error=str(exc)[:200] or type(exc).__name__, endpoint=endpoint)
        return ProviderResult("failed", {}, {"error": type(exc).__name__, "attempts": 1}, endpoint)
    _count()
    closes = {} if frame is None or frame.empty else {
        ts.date().isoformat(): float(v) for ts, v in frame["Close"].items()
        if v is not None and not math.isnan(float(v))}
    return ProviderResult("ok", closes, None, endpoint)


def _sector(info: dict) -> str | None:
    return info.get("sector") or None


def _period_end(year: Any) -> str | None:
    """The fiscal period's end date as ISO text (the ``vendor_financials`` key, #297); None without a date."""
    if hasattr(year, "date") and callable(year.date):
        try:
            return year.date().isoformat()
        except (TypeError, ValueError):
            return None
    return None


def _year_label(year: Any) -> str:
    """Fiskal yıl kolonunu '2021' gibi etikete çevirir."""
    if hasattr(year, "year"):
        return str(year.year)
    return str(year)[:4]
