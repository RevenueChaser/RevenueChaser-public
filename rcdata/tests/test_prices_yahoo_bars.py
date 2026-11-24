"""``yfinance/bars`` (avo, 24 Nov 2026, F28): Yahoo's daily bars of the names Compustat does not price, served only on
a session no Compustat row of the security has, as traded (Yahoo's split-adjusted prices made nominal again)."""
from __future__ import annotations

from datetime import date

import pytest

from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.prices import yahoo_bars

from .test_prices_wrds import AAPL, _build, _q, env, fake  # noqa: F401

FLG = "figi:BBG000BWBX65"          # the fixture's name with no Compustat series
OCT = ["2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27"]


def _yahoo(close, split_on=None, ratio=2.0):
    return [{"date": d, "open": close, "high": close, "low": close, "close": close, "volume": 1000.0,
             "split": ratio if d == split_on else 0} for d in OCT]


def test_nominal_scales_the_days_before_a_split_back_to_their_traded_prices():
    rows = yahoo_bars.nominal(_yahoo(10.0, split_on="2026-10-23"))
    assert [r["close"] for r in rows] == [20.0, 20.0, 10.0, 10.0, 10.0]
    assert [r["volume"] for r in rows] == [500.0, 500.0, 1000.0, 1000.0, 1000.0]


def test_only_the_names_compustat_has_not_priced_lately_are_asked(fake):
    _build()
    asked = {n["security_id"] for n in yahoo_bars.asked(base.Scope(), date(2026, 10, 27))}
    assert FLG in asked and AAPL not in asked


def test_a_yahoo_bar_is_served_only_where_compustat_has_none(fake, monkeypatch):
    _build()
    answers = {"FLG": _yahoo(10.0, split_on="2026-10-23"), "AAPL": _yahoo(999.0)}
    monkeypatch.setattr(yahoo_bars, "_lookup", lambda t: answers[t])
    row = base.run_request({"dataset": yahoo_bars.NAME, "params": {"as_of": "2026-10-27", "names": ["FLG", "AAPL"]}})
    assert row["result"] != "failed", row
    flg = _q("SELECT session_date, close, source FROM price_bar_daily WHERE security_id = ? ORDER BY session_date",
             [FLG])
    assert [(str(r["session_date"]), r["close"]) for r in flg] == list(zip(OCT, [20.0, 20.0, 10.0, 10.0, 10.0]))
    assert {r["source"] for r in flg} == {yahoo_bars.NAME}
    aapl = _q("SELECT close, source FROM price_bar_daily WHERE security_id = ? AND session_date = '2026-10-27'",
              [AAPL])
    assert [(r["close"], r["source"]) for r in aapl] == [(202.5, "wrds/compustat")]


def test_a_refusal_stops_the_run_and_keeps_what_was_read(fake, monkeypatch):
    _build()

    def lookup(t):
        if t == "FLG":
            raise yahoo_bars.YahooRefused("429 Too Many Requests")
        return _yahoo(5.0)
    monkeypatch.setattr(yahoo_bars, "_lookup", lookup)
    row = base.run_request({"dataset": yahoo_bars.NAME, "params": {"as_of": "2026-10-27", "names": ["BRK-B", "FLG"]}})
    assert "yfinance stopped at FLG" in (row.get("note") or ""), row
    assert not (yahoo_bars.DATASET.raw_dir(date(2026, 10, 27)) / "FLG.json.gz").exists()
    assert (yahoo_bars.DATASET.raw_dir(date(2026, 10, 27)) / "BRK-B.json.gz").exists()


@pytest.mark.parametrize("split", [0, 0.0, None])
def test_a_day_with_no_split_leaves_the_prices_as_they_are(split):
    rows = yahoo_bars.nominal([{**r, "split": split} for r in _yahoo(7.0)])
    assert {r["close"] for r in rows} == {7.0}
