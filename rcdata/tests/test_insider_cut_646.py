"""#646 decision D (avo 16 Nov 2026, D2 of 10 Nov): ``insider_reported`` sums only the officers' and directors'
positions filed inside two years; the older ones are left out and ``stale_share`` says how much of the reported
shares that was. Offline, at the reader's own boundaries."""
from __future__ import annotations

from datetime import date

import pytest

from RevenueChaser.rcdata import read

TODAY = date(2026, 11, 16)


def _tx(owner, day, shares):
    return {"ticker": "AAA", "tx_table": "non_derivative", "shares_after": shares, "is_officer": True,
            "is_director": False, "transaction_date": day, "filed": day, "security_title": "Common Stock",
            "owner_cik": owner, "direct_indirect": "D", "accession": owner, "line": 1}


@pytest.fixture
def store(monkeypatch):
    rows = []
    monkeypatch.setattr(read, "insider_transactions", lambda tickers: rows)
    monkeypatch.setattr(read, "security_ids", lambda tickers: {"AAA": "sid:AAA"})
    monkeypatch.setattr(read, "_split_factors", lambda ids: {})
    monkeypatch.setattr(read, "_class_divisors", lambda ids: {"sid:AAA": {"": 1000.0}})
    return rows


def test_a_position_older_than_two_years_is_left_out_and_counted(store):
    store += [_tx("1", date(2026, 3, 1), 50.0), _tx("2", date(2023, 1, 1), 150.0)]
    cell = read.insider_reported(["AAA"], as_of=TODAY)["AAA"]
    assert cell["pct"] == pytest.approx(5.0)                       # 50 of 1,000; the 2023 block is not summed
    assert cell["stale_share"] == pytest.approx(0.75) and cell["state"] == "partial"
    assert (cell["owners"], cell["owners_recent"]) == (2, 1)


def test_only_stale_positions_give_no_number_and_say_why(store):
    store += [_tx("2", date(2023, 1, 1), 150.0)]
    cell = read.insider_reported(["AAA"], as_of=TODAY)["AAA"]
    assert cell["pct"] is None and cell["state"] == "only stale positions" and cell["stale_share"] == 1.0
