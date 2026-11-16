"""#646 step 1 (decisions I and K, avo 16 Nov 2026): one shares-outstanding reader for the 13F board's % Out and
Asymmetric Growth, and the cell rules on it.

The reader (``core.ownership.shares_outstanding``) is driven at the ``rcdata.read`` boundary: a cover count is used
unless it is over a year old or differs over 3x from market cap ÷ price; without one, market cap ÷ price stands in
only for one-class common. The board marks an estimate ``≈``, a share over 100% ``*``, and shows a dash with the
reason over 150%. Offline.
"""
from __future__ import annotations

from datetime import date

import pytest

from RevenueChaser.core import ownership
from RevenueChaser.module_sec_13f import report

TODAY = date(2026, 11, 16)

# ticker: (cover shares, cover as_of, market cap, price, issuer cap, security_type)
STORE = {
    "OK": (1_000.0, date(2026, 10, 1), 10_000.0, 10.0, 10_000.0, "common"),     # cover, agrees with cap/price
    "OLD": (1_000.0, date(2025, 10, 1), 10_000.0, 10.0, 10_000.0, "common"),    # cover over a year old
    "HQ": (1.0, date(2026, 10, 1), 10_000.0, 10.0, 10_000.0, "common"),         # cover 1,000x off cap/price
    "EST": (None, None, 5_000.0, 10.0, 5_000.0, "common"),                      # no cover, one-class common
    "ADR": (None, None, 5_000.0, 10.0, 5_000.0, "adr"),                         # no cover, an ADR
    "CLS": (None, None, 5_000.0, 10.0, 9_000.0, "common"),                      # no cover, a second listed class
    "NONE": (None, None, None, None, None, None),                               # nothing at all
}


@pytest.fixture
def store(monkeypatch):
    from RevenueChaser.rcdata import read
    monkeypatch.setattr(read, "security_ids", lambda tickers: {t: f"sid:{t}" for t in tickers})
    monkeypatch.setattr(read, "latest_market", lambda tickers: {
        t: {"ticker": t, "market_cap": STORE[t][2], "price": STORE[t][3], "issuer_market_cap": STORE[t][4],
            "cap_session": "2026-11-13"} for t in tickers if STORE[t][3] is not None})
    monkeypatch.setattr(read, "shares", lambda ids, measure=None, start=None, end=None: [
        {"security_id": f"sid:{t}", "value": v[0], "as_of": v[1]} for t, v in STORE.items()
        if v[0] is not None and f"sid:{t}" in ids])
    monkeypatch.setattr(read, "identity", lambda tickers: [
        {"ticker": t, "security_type": STORE[t][5]} for t in tickers])


def test_the_reader_applies_the_cover_age_crosscheck_and_estimate_rules(store):
    got = ownership.shares_outstanding(STORE, today=TODAY)
    assert got["OK"] == {"shares": 1_000.0, "as_of": date(2026, 10, 1), "source": "cover", "note": None}
    assert got["OLD"]["shares"] is None and "over a year old" in got["OLD"]["note"]
    assert got["HQ"]["shares"] is None and "differ over 3x" in got["HQ"]["note"]
    assert got["EST"]["shares"] == pytest.approx(500.0) and got["EST"]["source"] == "estimate"
    for t in ("ADR", "CLS"):
        assert got[t]["shares"] is None and "not used" in got[t]["note"], t
    assert got["NONE"]["shares"] is None and got["NONE"]["note"]


def test_an_unreadable_store_gives_no_shares_not_a_failed_board(monkeypatch):
    from RevenueChaser.rcdata import read

    def boom(_):
        raise RuntimeError("no serving file")
    monkeypatch.setattr(read, "latest_market", boom)
    assert ownership.shares_outstanding(["AAA"])["AAA"]["shares"] is None


def _pct_cell(held, enrich):
    totals = {"AAA": {"2026-03-31": {"shares": held / 2, "value": 1.0, "holders": 2},
                      "2026-06-30": {"shares": held, "value": 1.0, "holders": 2}}}
    payload = report.board_payload(totals, {"AAA": {"name": "A", "sector": "Technology"}}, {"AAA": enrich})
    return dict(zip(payload["cols"], payload["rows"][0][3]))["pct_out"]


@pytest.mark.parametrize("held, enrich, text, val, note", [
    (300.0, {"shares_outstanding": 1000.0, "shares_source": "cover"}, "30.0%", 30.0, None),
    (300.0, {"shares_outstanding": 1000.0, "shares_source": "estimate"}, "≈30.0%", 30.0, "estimate"),
    (1200.0, {"shares_outstanding": 1000.0, "shares_source": "cover"}, "120.0%*", 120.0, "count one block twice"),
    (1600.0, {"shares_outstanding": 1000.0, "shares_source": "cover"}, "—", None, "check"),
    (300.0, {"shares_note": "shares count of 2025-01-01 is over a year old: check"}, "—", None, "over a year old"),
])
def test_the_pct_out_cell_marks_estimates_double_counts_and_wrong_counts(held, enrich, text, val, note):
    cell = _pct_cell(held, enrich)
    assert cell[0] == text and cell[1] == (pytest.approx(val) if val is not None else None)
    if note:
        assert note in cell[3]


def test_a_store_only_refresh_keeps_the_unmapped_cusip_note(monkeypatch):
    """#77: the note comes from the store on every render, not only from the Fetch that passed it in."""
    from RevenueChaser.app import runners
    from RevenueChaser.module_sec_13f import engine, enrich, store
    seen = {}
    monkeypatch.setattr(store, "sync", lambda: (None, None, False))
    monkeypatch.setattr(engine, "load_totals", lambda: {"AAA": {"2026-06-30": {"shares": 1.0}}})
    monkeypatch.setattr(engine, "load_sec13f_meta", lambda: {})
    monkeypatch.setattr(enrich, "load_inputs", lambda totals: {})
    monkeypatch.setattr(runners, "_13f_coverage_note", lambda: "13F 2026-06-30: 9 CUSIP(s) have no ticker.")
    monkeypatch.setattr(report, "export_sec13f_dashboard",
                        lambda *a, **kw: seen.setdefault("notice", kw.get("notice")))
    runners.run_sec_13f_latest(None, provider_health={"ok": True})
    assert seen["notice"] == "13F 2026-06-30: 9 CUSIP(s) have no ticker."
    seen.clear()
    runners.run_sec_13f_latest(None, notice="13F 2026-06-30: 9 CUSIP(s) have no ticker.", provider_health={"ok": True})
    assert seen["notice"] == "13F 2026-06-30: 9 CUSIP(s) have no ticker."      # the Fetch's own: said once
