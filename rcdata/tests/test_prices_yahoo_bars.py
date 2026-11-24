"""``yfinance/bars`` (avo, 24 Nov 2026, F28): Yahoo's daily bars of the names Compustat does not price, served only on
a session no Compustat row of the security has, as traded (Yahoo's split-adjusted prices made nominal again)."""
from __future__ import annotations

from datetime import date

import pytest

from revenuechaser.rcdata.build import base
from revenuechaser.rcdata.build.prices import yahoo_bars

from .test_prices_wrds import AAPL, _build, _q, _secd, _spine_etf_table, env, fake  # noqa: F401

FLG = "figi:BBG000BWBX65"          # the fixture's name with no Compustat series
OCT = ["2026-10-21", "2026-10-22", "2026-10-23", "2026-10-26", "2026-10-27"]


def _yahoo(close, split_on=None, ratio=2.0):
    return [{"date": d, "open": close, "high": close, "low": close, "close": close, "volume": 1000.0,
             "split": ratio if d == split_on else 0} for d in OCT]


def test_nominal_scales_the_days_before_a_split_back_to_their_traded_prices():
    rows = yahoo_bars.nominal([{**r, "dividend": 0.25} for r in _yahoo(10.0, split_on="2026-10-23")])
    assert [r["close"] for r in rows] == [20.0, 20.0, 10.0, 10.0, 10.0]
    assert [r["dividend"] for r in rows] == [0.5, 0.5, 0.25, 0.25, 0.25]
    assert [r["volume"] for r in rows] == [500.0, 500.0, 1000.0, 1000.0, 1000.0]


def test_only_the_names_compustat_has_not_priced_lately_are_asked(fake):
    _build()
    asked = {n["security_id"] for n in yahoo_bars.asked(base.Scope(), date(2026, 10, 27))}
    assert FLG in asked and AAPL not in asked


def test_a_fund_compustat_prices_by_its_ticker_and_a_cover_class_are_never_asked(fake, monkeypatch):
    """Review findings 2 and 3 of #1490: GLDX, a fund with no spine row, is served under the Compustat series that
    carries its ticker, so a Yahoo row under ``sym:GLDX`` would be the same fund under a second id; BRK-A's
    ``class:`` id beside Compustat's series of the class would count Berkshire's cap twice. Neither is asked. FLG, a
    stock, is asked even when a Compustat series carries its ticker: a stock's link is the spine's, never the
    ticker's."""
    fake[0].data["comp.secd"] += [_secd("077777", "01", d, "GLDX", 40.0, exchg=17, cusip="77777A100")
                                  for d in ("2026-10-26", "2026-10-27")]
    fake[0].data["comp.secd"] += [_secd("055555", "01", "2026-10-27", "FLG", 4.0, cusip="55555A100")]
    _build()
    names = [{"ticker": "GLDX", "cik": None, "tier": None, "security_id": "sym:GLDX"},
             {"ticker": "BRK-A", "cik": "1067983", "tier": None, "security_id": "class:1067983:a"},
             {"ticker": "FLG", "cik": "910073", "tier": "A", "security_type": "common", "security_id": FLG},
             {"ticker": "NEWF", "cik": None, "tier": None, "security_id": "sym:NEWF"}]
    monkeypatch.setattr(yahoo_bars, "scope", lambda want=None: names)
    asked = {n["ticker"] for n in yahoo_bars.asked(base.Scope(), date(2026, 10, 27))}
    assert asked == {"FLG", "NEWF"}


def test_recent_is_counted_from_compustats_newest_day_and_a_stale_compustat_stops_the_run(fake):
    """Review finding 5: a WRDS refresh a week late made every name look unpriced, so Yahoo was asked for the
    whole universe. Recent is counted back from Compustat's own newest day; one over ``STALE_SESSIONS`` sessions
    old stops the run instead."""
    _build()
    late = {n["security_id"] for n in yahoo_bars.asked(base.Scope(), date(2026, 11, 2))}
    assert FLG in late and AAPL not in late
    with pytest.raises(base.SourceError, match="Compustat's newest priced day is 2026-10-27"):
        yahoo_bars.asked(base.Scope(), date(2026, 11, 10))


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


def test_a_fund_only_yahoo_prices_is_served_and_a_fund_compustat_claims_keeps_its_series_id(fake, monkeypatch):
    """Review findings 4 and 2 of #1490: NEWF, a universe fund with no spine row, no Alpaca bar and no Compustat
    series, was fetched and never served (its ``sym:`` id reached no ``_universe`` branch). GLDX, a fund whose
    ticker a Compustat series carries, is served under that series: Yahoo fills only the sessions Compustat lacks,
    and no second ``sym:GLDX`` id appears."""
    fake[0].data["comp.secd"] += [_secd("077777", "01", d, "GLDX", 40.0, exchg=17, cusip="77777A100")
                                  for d in ("2026-10-26", "2026-10-27")]
    _spine_etf_table([("NEWF", 5e9), ("GLDX", 5e9)])
    _build()
    answers = {"NEWF": _yahoo(8.0), "GLDX": _yahoo(39.0)}
    monkeypatch.setattr(yahoo_bars, "_lookup", lambda t: answers[t])
    row = base.run_request({"dataset": yahoo_bars.NAME, "params": {"as_of": "2026-10-27", "names": ["NEWF", "GLDX"]}})
    assert row["result"] != "failed", row
    newf = _q("SELECT session_date FROM price_bar_daily WHERE security_id = 'sym:NEWF'")
    assert len(newf) == len(OCT)
    gldx = _q("SELECT CAST(session_date AS TEXT) AS d, close, source FROM price_bar_daily "
              "WHERE security_id = '077777:01' AND session_date >= '2026-10-21' ORDER BY 1")
    assert [(r["d"], r["source"]) for r in gldx] == [(d, yahoo_bars.NAME) for d in OCT[:3]] + [
        (d, "wrds/compustat") for d in OCT[3:]]
    assert not _q("SELECT 1 FROM price_bar_daily WHERE security_id = 'sym:GLDX'")


def test_yahoos_splits_and_dividends_are_served_only_on_a_day_whose_bar_is_yahoos(fake, monkeypatch):
    """avo's D2 (24 Nov 2026, "Evet, Yahoo'dan al") and review finding 1 of #1490: a Yahoo-only name had no split
    and no dividend, so its total return was its price return. FLG's split and dividend are served from Yahoo, the
    dividend as traded (Yahoo writes it split-adjusted like its prices); AAPL's Yahoo dividend on a day Compustat's bar
    is served is not."""
    _build()
    flg = _yahoo(10.0, split_on="2026-10-23")
    for r in flg:
        r["dividend"] = 0.25 if r["date"] in ("2026-10-22", "2026-10-26") else 0
    aapl = [{**r, "dividend": 0.3 if r["date"] == "2026-10-27" else 0} for r in _yahoo(999.0)]
    monkeypatch.setattr(yahoo_bars, "_lookup", lambda t: {"FLG": flg, "AAPL": aapl}[t])
    row = base.run_request({"dataset": yahoo_bars.NAME, "params": {"as_of": "2026-10-27", "names": ["FLG", "AAPL"]}})
    assert row["result"] != "failed", row
    acts = _q("SELECT CAST(ex_date AS TEXT) AS d, action_type, ratio, amount FROM corporate_action "
              "WHERE security_id = ? AND source = ? ORDER BY 1", [FLG, yahoo_bars.NAME])
    assert [(a["d"], a["action_type"]) for a in acts] == [
        ("2026-10-22", "cash_dividend"), ("2026-10-23", "forward_split"), ("2026-10-26", "cash_dividend")]
    assert [a["amount"] for a in acts if a["action_type"] == "cash_dividend"] == [0.5, 0.25]
    assert [a["ratio"] for a in acts if a["action_type"] == "forward_split"] == [2.0]
    assert not _q("SELECT 1 FROM corporate_action WHERE security_id = ? AND source = ?", [AAPL, yahoo_bars.NAME])


def test_no_bar_before_compustats_first_day_and_no_bar_of_a_session_still_open(fake, monkeypatch):
    """Review of #1490, finding 7 and the floor Low: Yahoo answers today's partial bar during the session, and a
    history from 1962; neither is stored. The fixture's clock is 27 Oct 2026 21:00 UTC, so 27 Oct is complete."""
    from datetime import datetime, timezone

    from revenuechaser.core import calendar
    _build()
    old = [{**_yahoo(3.0)[0], "date": d} for d in ("1983-12-29", "1983-12-30")]
    monkeypatch.setattr(yahoo_bars, "_lookup", lambda t: old + _yahoo(8.0))
    monkeypatch.setattr(calendar, "_now", lambda: datetime(2026, 10, 27, 15, 0, tzinfo=timezone.utc))
    row = base.run_request({"dataset": yahoo_bars.NAME, "params": {"as_of": "2026-10-27", "names": ["FLG"]}})
    assert row["result"] != "failed", row
    days = [str(r["session_date"]) for r in _q("SELECT session_date FROM price_bar_daily WHERE security_id = ? "
                                                "ORDER BY 1", [FLG])]
    assert days == ["1983-12-30"] + OCT[:-1]
    import duckdb
    stored = duckdb.sql(f"SELECT max(session_date) FROM read_parquet('{base.parquet_root()}/yfinance/bars/*/*.parquet')"
                        ).fetchone()[0]
    assert str(stored) == "2026-10-26", "the open session's bar is not even kept in the Parquet"


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
