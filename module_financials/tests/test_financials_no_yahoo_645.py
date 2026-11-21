"""The Financials board makes no provider call (#645, avo 10 Nov 2026, option B: "Yahoo is dropped").

The last Yahoo read on this board was ``get_financials`` — one ``.info`` request plus three statement requests on
every Fetch — with a second pair (``.info`` and a one-year history) behind Quick Remarks' fallback. The decision
was that only the SEC's statements are used and **a name without them says so and gets no model**.

What that costs and where each figure comes from instead:

* the statements: the fundamentals serving layer alone (``run._sec_statements``), with no whole-source choice left;
* the company name: the SEC entity name, else the spine's row, else the ticker (``run._company_name``);
* the price, market cap, shares and beta: the prices store alone, and the Source line names what it did not give;
* the enterprise value: the store's bridge (cap + total debt − cash of the newest stored fiscal year), the same
  one the peer side has used since #286, so the target and its comps are on one basis;
* Quick Remarks: the shared ``ticker_scores`` card, and an empty section when the scan holds none.

Offline by construction: these tests patch no provider away, they assert the module never reaches one. A fake
``yfinance`` whose ``Ticker`` raises stands in for the library, so a read that came back would fail the test
rather than pass quietly.
"""
from __future__ import annotations

import sys

import pytest

import RevenueChaser.module_financials.run as fm


class _Boom:
    """A ``yfinance.Ticker`` that refuses every attribute: a read of any kind is an error, not an empty answer."""

    def __init__(self, ticker: str):
        raise AssertionError(f"the Financials board read Yahoo for {ticker}")


@pytest.fixture
def no_yahoo(monkeypatch):
    """The library replaced by one that raises on use, so any surviving read fails loudly."""
    fake = type(sys)("yfinance")
    fake.Ticker = lambda ticker: _Boom(ticker)
    monkeypatch.setitem(sys.modules, "yfinance", fake)
    return fake


def _year(fy: str, **over) -> dict:
    rec = {"fiscal_year": fy, "revenue": 1_000.0, "ebit": 200.0, "depreciation": 20.0, "capex": 30.0,
           "net_income": 120.0, "total_debt": 400.0, "cash": 150.0, "total_assets": 2_000.0,
           "total_equity": 900.0, "receivables": 90.0, "inventory": 40.0, "payables": 60.0,
           "income_tax_expense": 50.0, "pretax_income": 200.0, "interest_expense": 15.0,
           "period_ends": {"revenue": f"{fy}-12-31"}}
    rec.update(over)
    return rec


def _layer(monkeypatch, years: list[dict], meta: dict | None = None) -> None:
    """The fundamentals layer serving ``years`` for every ticker, with ``meta``'s keys on its answer."""
    from RevenueChaser.core import fundamentals_layer
    answer = (years, [], {"entity_name": "Test Corporation", "newest_filed": "2026-08-01",
                          "available": bool(years), **(meta or {})})
    monkeypatch.setattr(fundamentals_layer, "reads_layer", lambda: True)
    monkeypatch.setattr(fundamentals_layer, "records", lambda t: answer)


def _offline(monkeypatch, tmp_path) -> None:
    """Everything the run reads besides the layer, stubbed to a store answer: no spine file, no prices file."""
    from RevenueChaser.core import universe as spine
    monkeypatch.setattr(fm, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(spine, "spine_gics", lambda tickers=None: {})
    monkeypatch.setattr(spine, "filter_fields", lambda tickers=None: {})
    monkeypatch.setattr(fm, "picker_payload", lambda ticker: {})
    monkeypatch.setattr(fm, "_stored_risk_free", lambda: None)
    monkeypatch.setattr(fm.market_inputs, "from_store", lambda ticker: {})


# ── the run makes no provider call ────────────────────────────────────────────────────────────────────────────

def test_a_fetch_reads_no_provider_at_all(no_yahoo, monkeypatch, tmp_path):
    """The whole Fetch, every module: the figures are store reads and the library is never touched."""
    _offline(monkeypatch, tmp_path)
    _layer(monkeypatch, [_year("2024"), _year("2025")])
    out = fm.run("TEST", modules=["dcf", "3stmt", "comps", "credit", "sensitivity"], output="html")
    assert set(out["results"]["modules"]) == {"dcf", "three_statement", "comps", "credit", "sensitivity"}
    assert out["results"]["financials"]["source"].startswith("SEC company facts")


def test_the_module_imports_no_provider_client():
    """``run.py`` holds no ``core.providers`` import and names no provider library: the read cannot come back by
    a path the board's provider ceiling does not see (the companion guard is ``rcdata/tests/test_needs_old_links``).
    """
    import inspect
    src = inspect.getsource(fm)
    assert "providers import yfinance" not in src and "import yfinance" not in src
    assert "yfinance_client" not in src


# ── a name the layer holds no year for ────────────────────────────────────────────────────────────────────────

def test_a_name_without_sec_statements_gets_no_model_and_says_so(no_yahoo, monkeypatch, tmp_path):
    """avo's option B: Yahoo used to supply those statements, so this was a silent fall-back to a vendor's
    numbers. Now the board runs no model and names the reason."""
    _offline(monkeypatch, tmp_path)
    _layer(monkeypatch, [])
    out = fm.run("TEST", modules=["dcf", "comps"], output="html")
    results = out["results"]
    assert results["modules"] == {}, "a name with no SEC annual year must get no model"
    assert results["financials"]["source"].startswith(fm.NO_SEC_DATA)
    assert any(w.startswith("TEST: ") and "no sec data" in w.lower() for w in results["warnings"])
    assert results["financials"]["statements_meta"]["used"] == "none"
    html = (tmp_path / "TEST_report.html").read_text(encoding="utf-8")
    assert fm.NO_SEC_DATA in html


def test_a_year_without_revenue_is_the_filers_own_year_not_a_vendors(no_yahoo, monkeypatch, tmp_path):
    """A newest year the layer serves with only balance-sheet fields was the one case where Yahoo's statements
    took over (``_statements_choice``). The year is the filer's own now: it is SEC data, so the board keeps it
    and the model says what the year itself lacks, rather than a vendor filling the gap or the board claiming
    there is no SEC data at all (``fiscal_year.anchor`` stands the newest record in when no year carries
    revenue, so the cash and balance-sheet rules still see a year)."""
    _offline(monkeypatch, tmp_path)
    _layer(monkeypatch, [{"fiscal_year": "2025", "cash": 5.0}])
    out = fm.run("TEST", modules=["dcf"], output="none")
    results = out["results"]
    assert not results["financials"]["source"].startswith(fm.NO_SEC_DATA), "a stored year is SEC data"
    assert results["financials"]["source"].startswith("SEC company facts")
    assert "no revenue" in (results["modules"]["dcf"].get("error") or ""), results["modules"]["dcf"]


# ── the company name ──────────────────────────────────────────────────────────────────────────────────────────

def test_the_header_name_is_the_sec_entity_name():
    assert fm._company_name("TEST", {"entity_name": "Test Corporation"}) == "Test Corporation"


def test_without_an_entity_name_the_spines_row_names_the_company(monkeypatch):
    from RevenueChaser.core import universe as spine
    monkeypatch.setattr(spine, "filter_fields", lambda tickers=None: {"TEST": {"name": "Test Inc."}})
    assert fm._company_name("TEST", {}) == "Test Inc."


def test_with_neither_the_name_is_the_ticker(monkeypatch):
    from RevenueChaser.core import universe as spine
    monkeypatch.setattr(spine, "filter_fields", lambda tickers=None: {})
    assert fm._company_name("TEST", {"entity_name": "  "}) == "TEST"


def test_a_spine_read_that_fails_is_no_name_not_an_error(monkeypatch):
    from RevenueChaser.core import universe as spine

    def _boom(_tickers=None):
        raise RuntimeError("no spine file")

    monkeypatch.setattr(spine, "filter_fields", _boom)
    assert fm._company_name("TEST", {}) == "TEST"


def test_the_card_shows_that_name_where_yahoos_longname_used_to_stand(no_yahoo, monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path)
    _layer(monkeypatch, [_year("2025")])
    fm.run("TEST", modules=["dcf"], output="html")
    html = (tmp_path / "TEST_report.html").read_text(encoding="utf-8")
    assert "Test Corporation" in html


# ── the enterprise value ──────────────────────────────────────────────────────────────────────────────────────

def test_the_ev_is_the_stores_bridge_on_the_newest_year():
    years = [fm._financials_record(_year("2024")), fm._financials_record(_year("2025", total_debt=500.0))]
    assert fm._enterprise_value(10_000.0, years) == 10_000.0 + 500.0 - 150.0


def test_the_ev_is_the_same_bridge_the_peer_side_uses():
    """One basis for the target and its comps (#286's bridge, reused rather than written twice)."""
    from RevenueChaser.module_financials import store_reads
    year = fm._financials_record(_year("2025"))
    assert fm._enterprise_value(10_000.0, [year]) == store_reads._enterprise_value(10_000.0, year)


@pytest.mark.parametrize("cap, over", [(None, {}), (10_000.0, {"total_debt": None}), (10_000.0, {"cash": None})])
def test_half_a_bridge_is_no_ev(cap, over):
    year = fm._financials_record(_year("2025", **over))
    assert fm._enterprise_value(cap, [year]) is None


def test_without_a_year_there_is_no_ev():
    assert fm._enterprise_value(10_000.0, []) is None


# ── the Source line ───────────────────────────────────────────────────────────────────────────────────────────

def test_the_source_line_names_the_filers_own_gaps_and_nothing_elses(no_yahoo, monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path)
    _layer(monkeypatch, [_year("2025", depreciation=None, interest_expense=None)])
    out = fm.run("TEST", modules=["dcf"], output="none")
    source = out["results"]["financials"]["source"]
    assert "Yahoo" not in source
    assert "newest filed 2026-08-01" in source
    for gap in ("depreciation", "interest expense"):
        assert gap in source


def test_a_whole_filer_names_no_gap(no_yahoo, monkeypatch, tmp_path):
    _offline(monkeypatch, tmp_path)
    _layer(monkeypatch, [_year("2024"), _year("2025")])
    source = fm.run("TEST", modules=["dcf"], output="none")["results"]["financials"]["source"]
    assert "so defaults" not in source
