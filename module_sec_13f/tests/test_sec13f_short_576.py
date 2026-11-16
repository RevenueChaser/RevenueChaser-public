"""#576 (decision A, avo 16 Nov 2026): the 13F board's Short% is FINRA's newest settlement short interest, read through
the one FINRA reader the Earnings board uses too (``core.ownership.finra_short``), over the shares outstanding % Out
divides by, and the cell names its settlement day. Offline, at the ``rcdata.read`` boundary.
"""
from __future__ import annotations

from datetime import date

import pytest

from RevenueChaser.core import ownership
from RevenueChaser.module_sec_13f import enrich, report


def _finra(rows):
    def reader(tickers, start=None, end=None):
        return [r for r in rows if r["ticker"] in set(tickers) and start <= r["settlement_date"] <= end]
    return reader


def test_the_newest_settlement_wins_and_a_tie_takes_the_tickers_own_symbol(monkeypatch):
    from RevenueChaser.rcdata import read
    monkeypatch.setattr(read, "finra_short_interest", _finra([
        {"ticker": "AAA", "symbol": "AAA", "settlement_date": date(2026, 10, 15), "current_short": 10.0},
        {"ticker": "AAA", "symbol": "AAA.X", "settlement_date": date(2026, 10, 31), "current_short": 20.0},
        {"ticker": "AAA", "symbol": "AAA", "settlement_date": date(2026, 10, 31), "current_short": 30.0},
        {"ticker": "BBB", "symbol": "BBB", "settlement_date": date(2025, 1, 15), "current_short": 5.0}]))
    got = ownership.finra_short(["AAA", "BBB"], date(2026, 10, 1), date(2026, 11, 16))
    assert set(got) == {"AAA"}                                       # BBB's only settlement is outside the window
    assert got["AAA"]["current_short"] == 30.0 and got["AAA"]["settlement_date"] == date(2026, 10, 31)


def test_load_inputs_puts_short_over_the_shares_outstanding(monkeypatch):
    monkeypatch.setattr(ownership, "shares_outstanding", lambda tickers, today=None: {
        "AAA": {"shares": 1000.0, "as_of": None, "source": "cover", "note": None},
        "BBB": {"shares": None, "as_of": None, "source": None, "note": "no shares count"}})
    monkeypatch.setattr(enrich, "_short_interest", lambda tickers: {
        "AAA": {"current_short": 50.0, "settlement_date": date(2026, 10, 31)},
        "BBB": {"current_short": 50.0, "settlement_date": date(2026, 10, 31)}})
    monkeypatch.setattr(enrich, "quarter_end_closes", lambda tickers, quarters: {})
    monkeypatch.setattr(ownership, "split_factors_13f", lambda wanted: {})
    from RevenueChaser.module_sec_13f import store
    monkeypatch.setattr(store, "read_breaks", lambda tickers: {})
    got = enrich.load_inputs({"AAA": {"2026-06-30": {}}, "BBB": {"2026-06-30": {}}})
    assert got["AAA"]["short_pct"] == pytest.approx(5.0) and got["AAA"]["short_pct_as_of"] == "2026-10-31"
    assert "short_pct" not in got["BBB"]                             # no shares: no Short%, never 0


@pytest.mark.parametrize("enr, text, note", [
    ({"short_pct": 5.0, "short_pct_as_of": "2026-10-31", "shares_outstanding": 1000.0, "shares_source": "cover"},
     "5.0%", "settlement 2026-10-31"),
    ({"short_pct": 5.0, "short_pct_as_of": "2026-10-31", "shares_outstanding": 1000.0, "shares_source": "estimate"},
     "≈5.0%", "estimate"),
    ({}, "—", None),
])
def test_the_short_cell_names_its_settlement(enr, text, note):
    totals = {"AAA": {"2026-06-30": {"shares": 100.0, "value": 1.0, "holders": 2}}}
    payload = report.board_payload(totals, {"AAA": {"name": "A"}}, {"AAA": enr})
    cell = dict(zip(payload["cols"], payload["rows"][0][3]))["short"]
    assert cell[0] == text
    if note:
        assert note in cell[3]
