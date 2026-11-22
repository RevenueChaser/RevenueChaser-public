"""Financials' price, market cap, shares and beta from the prices store (G6 follow-up) — the only source since
#645, so a value it does not give is absent rather than a vendor's. Offline: a served ``prices.duckdb`` written
from rows (``rcdata/tests/prices_store``)."""
from __future__ import annotations

from datetime import date, datetime, timezone

import duckdb
import pytest

from revenuechaser.core.tests.test_fundamentals_layer import TICKER, built, grw_facts  # noqa: F401
from revenuechaser.module_financials import market_inputs as mi
from revenuechaser.rcdata import serving
from revenuechaser.rcdata.tests import prices_store
from revenuechaser.rcdata.tests.conftest import http_mock, market_roots  # noqa: F401  (fixtures)

NEWEST = date(2026, 10, 27)
#: A payload that already carries market figures. Before #645 these were Yahoo's and the overlay kept them where
#: the store had none; now nothing supplies them, so this stands for a caller's own numbers in a unit test.
GIVEN = {"shares_outstanding": 50.0, "market_cap": 5000.0, "beta": 1.1, "current_price": 100.0}


@pytest.fixture(autouse=True)
def _today(monkeypatch):
    """Today is the day after the store's newest session, unless a test moves it."""
    _clock(monkeypatch)


def _clock(monkeypatch, now: datetime = datetime(2026, 10, 28, 15, 0, tzinfo=timezone.utc)):
    from revenuechaser.core import calendar
    monkeypatch.setattr(calendar, "_now", lambda: now)


def _month_end_series(n: int, beta: float, end: date = date(2026, 9, 30)):
    """``n`` month ends up to ``end`` (index level, stock close) where every stock return is 0.002 + beta x the
    index return."""
    import pandas as pd
    months = pd.period_range(end=pd.Period(end, "M"), periods=n, freq="M")
    index, stock = [3000.0], [50.0]
    for i in range(1, n):
        r = 0.03 * ((i * 7) % 5 - 2) / 2          # a deterministic, varied index return
        index.append(index[-1] * (1 + r))
        stock.append(stock[-1] * (1 + 0.002 + beta * r))
    days = [m.to_timestamp(how="end").date() for m in months]
    return list(zip(days, stock)), list(zip(days, index))


def test_the_beta_is_the_slope_of_monthly_returns_on_the_index():
    stock, index = _month_end_series(61, 1.5)
    assert mi.monthly_beta(stock, index, NEWEST) == pytest.approx(1.5)


def test_only_the_last_sixty_complete_months_count():
    stock, index = _month_end_series(90, 1.5)
    # The 29 oldest months move the other way: they fall outside the window and change nothing.
    early = [(d, c * (1 + (0.05 if i % 2 else -0.05))) for i, (d, c) in enumerate(stock[:29])]
    assert mi.monthly_beta(early + stock[29:], index, NEWEST) == pytest.approx(1.5)


def test_the_running_month_is_not_a_return():
    stock, index = _month_end_series(61, 1.5)
    assert mi.monthly_beta(stock + [(date(2026, 10, 20), 1.0)], index + [(date(2026, 10, 20), 3000.0)],
                           NEWEST) == pytest.approx(1.5)


def test_too_few_months_give_no_beta():
    stock, index = _month_end_series(mi.BETA_MIN_MONTHS, 1.5)        # one return short of the minimum
    assert mi.monthly_beta(stock, index, NEWEST) is None


def test_exactly_the_minimum_of_months_gives_a_beta():
    stock, index = _month_end_series(mi.BETA_MIN_MONTHS + 1, 1.5)    # BETA_MIN_MONTHS returns
    assert mi.monthly_beta(stock, index, NEWEST) == pytest.approx(1.5)


@pytest.mark.filterwarnings("ignore::RuntimeWarning")         # the overflow is the point
def test_a_beta_that_is_not_a_number_is_none():
    # A month-end index level of 1e-300 makes a return of ~1e303: the variance overflows and the slope is NaN.
    stock, index = _month_end_series(61, 1.5)
    index = [(d, 1e-300 if i == 30 else c) for i, (d, c) in enumerate(index)]
    stock = [(d, 1e-300 if i == 30 else c) for i, (d, c) in enumerate(stock)]
    assert mi.monthly_beta(stock, index, NEWEST) is None


def test_a_missing_month_makes_no_return_across_the_gap():
    stock, index = _month_end_series(61, 1.5)
    gap = stock[:30] + [(d, c * 3) for d, c in stock[31:]]      # month 31 missing, later closes on another level
    assert mi.monthly_beta(gap, index, NEWEST) == pytest.approx(1.5)


def _store(ticker: str = TICKER, *, months: int = 61, price: float = 120.0, own_cap: float | None = 5500.0,
           issuer_cap: float | None = 6000.0, beta: float = 1.5, cap_session: date = NEWEST) -> None:
    stock, index = _month_end_series(months, beta)
    prices_store.put_bars([{"ticker": ticker, "session_date": d, "close": c} for d, c in stock]
                          + [{"ticker": ticker, "session_date": NEWEST, "close": price}]
                          + [{"ticker": "SPX", "security_id": mi.INDEX_ID, "session_date": d, "close": c}
                             for d, c in index])
    if own_cap is not None:
        con = duckdb.connect(str(serving.live_path("prices")))
        try:
            con.execute("INSERT INTO market_cap_daily (security_id, session_date, close, market_cap, "
                        "issuer_market_cap) VALUES (?, ?, ?, ?, ?)",
                        [f"sym:{ticker}", cap_session, price, own_cap, issuer_cap])
            con.execute("CHECKPOINT")
        finally:
            con.close()


def test_the_store_gives_the_price_the_issuers_cap_the_shares_and_the_beta(market_roots):  # noqa: F811
    _store()
    got = mi.from_store(TICKER.lower())
    assert got["current_price"] == 120.0 and got["price_session"] == NEWEST
    assert got["market_cap"] == 6000.0                       # the issuer's, every listed class
    assert got["shares_outstanding"] == pytest.approx(50.0)  # 6000 / 120: the class-equivalent count
    assert got["beta"] == pytest.approx(1.5)


def test_without_an_issuer_sum_the_class_cap_counts(market_roots):  # noqa: F811
    _store(issuer_cap=None)
    assert mi.from_store(TICKER)["market_cap"] == 5500.0




def test_a_bar_without_a_cap_gives_the_price_alone(market_roots):  # noqa: F811
    _store(own_cap=None, months=12)
    got = mi.from_store(TICKER)
    assert set(got) == {"current_price", "price_session"}


@pytest.mark.parametrize("today, fresh", [(date(2026, 11, 10), True), (date(2026, 11, 11), False)])
def test_a_close_older_than_the_rates_limit_gives_nothing(market_roots, monkeypatch, today, fresh):  # noqa: F811
    # The same 14 days as the risk-free rate on that card, counted from today, not from the store's newest session.
    from revenuechaser.module_financials.config import RISK_FREE_MAX_AGE_DAYS
    assert (date(2026, 11, 10) - NEWEST).days == RISK_FREE_MAX_AGE_DAYS
    _store()
    _clock(monkeypatch, datetime(today.year, today.month, today.day, 20, 0, tzinfo=timezone.utc))
    got = mi.from_store(TICKER)
    assert (got.get("current_price") == 120.0) is fresh and (got == {}) is not fresh


def test_a_cap_from_another_session_than_the_price_is_not_divided_by_it(market_roots):  # noqa: F811
    # The cap of 2026-10-23 over the close of 2026-10-27 is no share count, so the card gets neither.
    _store(cap_session=date(2026, 10, 23))
    got = mi.from_store(TICKER)
    assert got["current_price"] == 120.0 and "market_cap" not in got and "shares_outstanding" not in got


def test_no_prices_file_gives_nothing(market_roots):  # noqa: F811
    assert mi.from_store(TICKER) == {}


def test_the_overlay_names_what_the_store_did_not_give(market_roots):  # noqa: F811
    """#645: a beta the store cannot compute is named as not stored, not as Yahoo's. The payload's own number is
    not overwritten (the engines read it), but the Source line no longer claims a vendor supplied it."""
    _store(months=12)                                        # too short for a beta
    out, part = mi.overlay(TICKER, {**GIVEN, "annual": []})
    assert out["current_price"] == 120.0 and out["market_cap"] == 6000.0
    assert part == "prices store, 2026-10-27 close (price, market cap, shares) · not stored (beta)"
    assert out["market_meta"]["price_session"] == "2026-10-27"
    assert "beta_source" not in out


def test_the_overlay_names_a_cap_the_store_did_not_give(market_roots):  # noqa: F811
    _store(own_cap=None, months=12)
    _out, part = mi.overlay(TICKER, dict(GIVEN))
    assert part == "prices store, 2026-10-27 close (price) · not stored (market cap, shares, beta)"


def test_the_overlay_with_nothing_in_the_store_names_no_source(market_roots):  # noqa: F811
    out, part = mi.overlay(TICKER, dict(GIVEN))
    assert part == "not stored (price, market cap, shares, beta)"
    # Nothing supplies a share count, so the comps basis says so rather than naming a vendor.
    assert out["market_meta"]["shares_source"] is None










def test_the_card_names_the_session_of_the_stores_price():
    from revenuechaser.module_financials.reporting.html_builder import build_report_html
    fin = {**GIVEN, "market_meta": {"from_store": ["price"], "price_session": "2026-10-27"}}
    html = build_report_html({"ticker": TICKER, "financials": fin, "modules": {}, "warnings": []})
    assert "Price: $100.00 (close 2026-10-27)<" in html
    no_session = build_report_html({"ticker": TICKER, "financials": dict(GIVEN), "modules": {}, "warnings": []})
    assert "Price: $100.00<" in no_session


def test_the_comps_basis_names_where_the_targets_shares_came_from(market_roots):  # noqa: F811
    # #286: the peer side is the store's newest annual record; the target's per-share values divide by the
    # store's shares. This test is about the second half, so the peers are injected.
    from revenuechaser.module_financials.engines import comps_engine
    from revenuechaser.module_financials.reporting.html_builder import build_report_html
    _store()
    fin, _part = mi.overlay(TICKER, {**GIVEN, "annual": [{"fiscal_year": "2025", "revenue": 100.0, "ebitda": 30.0,
                                                          "net_income": 10.0, "total_debt": 5.0, "cash": 5.0}]})
    peer = {"enterpriseValue": 900.0, "ebitda": 90.0, "totalRevenue": 300.0, "marketCap": 800.0,
            "netIncomeToCommon": 40.0}
    comps = comps_engine.run_comps(fin, ["PEER"], fetch_info=lambda p: peer)
    assert comps["basis"]["target_shares"] == "prices store, 2026-10-27 close"
    html = build_report_html({"ticker": TICKER, "financials": fin, "modules": {"comps": comps}, "warnings": []})
    assert "peer multiples are newest stored fiscal year" in html
    assert "per share divides by the target's shares from the prices store, 2026-10-27 close." in html
    unstored = comps_engine.run_comps({**GIVEN, "annual": fin["annual"]}, ["PEER"], fetch_info=lambda p: peer)
    assert unstored["basis"]["target_shares"] == "not stored"


def test_the_cards_ev_names_the_bridge_it_is_built_from():
    """#645: the EV is no longer Yahoo's own figure but the store's bridge (cap + total debt - cash of the newest
    stored fiscal year), the same one the peer side uses, so the header names the bridge instead of a vendor."""
    from revenuechaser.module_financials.reporting.html_builder import build_report_html
    fin = {**GIVEN, "enterprise_value": 5200.0,
           "market_meta": {"from_store": ["price", "market cap, shares"], "price_session": "2026-10-27",
                           "shares_source": "prices store, 2026-10-27 close"}}
    html = build_report_html({"ticker": TICKER, "financials": fin, "modules": {}, "warnings": []})
    assert "EV: $5.2K (cap + debt − cash, newest FY)<" in html
    # No EV at all (a year without a debt or cash line) renders the empty value and no bridge note.
    none = build_report_html({"ticker": TICKER, "financials": dict(GIVEN), "modules": {}, "warnings": []})
    assert "(cap + debt" not in none
