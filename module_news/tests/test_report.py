"""The News board page (plan §6, mock News.dc.html): today, this week, the highlight and the headlines."""
from __future__ import annotations

import json
from datetime import datetime

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_news import calendar as cal, report

NOW = datetime(2026, 11, 9, 15, 0, tzinfo=cal.AMS).timestamp()        # Mon 9 Nov 15:00 Amsterdam
HOUR = 3600.0


def _at(day, hh, mm=0):
    return datetime(2026, 11, day, hh, mm, tzinfo=cal.AMS).timestamp()


def _event(ts, event, kind="report", fc=None, prev=None, retired=None):
    return {"event_ts": ts, "event": event, "type": kind, "importance": cal.econ_importance.importance(event, kind),
            "forecast": fc, "prev": prev, "reported_period": None, "first_seen": 1.0, "last_seen": 1.0,
            "retired_at": retired, "run_id": "t", "run_at": NOW - HOUR}


@pytest.fixture
def seeded():
    rawstore.write_rows("news_events", [
        _event(_at(9, 14, 40), "Fed Governor Bowman speaks", "fed-speaker"),
        _event(_at(9, 17, 0), "NY Fed consumer inflation expectations", prev="3.9%"),
        _event(_at(9, 18, 0), "Cancelled release", retired=NOW),
        _event(_at(10, 14, 30), "CPI, Y/Y%", fc="3.6%", prev="3.7%"),
        _event(_at(20, 14, 30), "Retail sales"),                               # past the week
    ])
    rawstore.write_rows("news_highlight", [{
        "session_date": "2026-11-09", "event_ts": _at(9, 17, 0), "event": "NY Fed consumer inflation expectations",
        "type": "report", "importance": 2, "forecast": None, "prev": "3.9%", "text": "Hanehalkı beklentisi.",
        "text_source": "template", "run_id": "t", "run_at": NOW}])
    rawstore.write_rows("news_headlines", [
        {"headline_id": "uw:1", "provider": "uw", "published_at": NOW - 2 * HOUR, "headline": "Stocks <b>rally</b>",
         "source": "Reuters", "tickers": json.dumps(["SPY"]), "url": None, "fetched_at": NOW, "run_id": "t",
         "run_at": NOW},
        {"headline_id": "uw:2", "provider": "uw", "published_at": NOW - 30 * HOUR, "headline": "Old news",
         "source": None, "tickers": "[]", "url": None, "fetched_at": NOW, "run_id": "t", "run_at": NOW},
    ])


def test_tr_value_writes_turkish_numbers():
    assert cal.tr_value("3.9%") == "%3,9" and cal.tr_value("-0.2%") == "-%0,2"
    assert cal.tr_value("215K") == "215K" and cal.tr_value("1.25M") == "1,25M"
    assert cal.tr_value(None) is None and cal.tr_value("n/a") == "n/a"


def test_the_page_shows_today_the_week_and_the_highlight(seeded):
    page = report.render_html(now=NOW)
    assert "9 Kasım 2026" in page and "Pazartesi" in page
    assert "Fed Governor Bowman speaks" in page and "CPI, Y/Y%" in page
    assert "Salı 10 Kasım" in page                       # the week groups by Amsterdam day
    assert "Retail sales" not in page                    # beyond seven days
    assert "Cancelled release" not in page               # retired events never show
    assert "Hanehalkı beklentisi." in page and "Öne çıkan veri" in page
    assert "%3,6" in page and "%3,7" in page              # forecast and previous in Turkish numbers
    assert 'data-past="1"' in page                       # 14:40 has passed at 15:00


def test_headlines_are_the_last_24_hours_and_escaped(seeded):
    page = report.render_html(now=NOW)
    assert "Stocks &lt;b&gt;rally&lt;/b&gt;" in page and "<b>rally" not in page
    assert "Old news" not in page and "SPY" in page


def test_an_empty_store_says_so_in_turkish():
    page = report.render_html(now=NOW)
    assert "Bu hafta takvimde veri yok" in page and "Henüz başlık yok" in page


def test_the_page_is_phone_friendly_and_themed(seeded):
    page = report.render_html(now=NOW)
    assert "max-width:900px" in page and "min-height:44px" in page
    assert 'data-theme="light"' in page or ":root[data-theme=\"light\"]" in page


def test_render_writes_the_board_file(seeded, tmp_path, monkeypatch):
    monkeypatch.setattr(report, "OUTPUT_DIR", tmp_path)
    path = report.render(now=NOW)
    assert path == tmp_path / "news_latest.html" and "CPI, Y/Y%" in path.read_text(encoding="utf-8")


def test_market_and_stock_headlines_get_their_own_lane_and_the_page_polls():
    rawstore.write_rows("news_headlines", [
        {"headline_id": "ibkr:m", "provider": "ibkr", "published_at": NOW - HOUR, "headline": "Fed holds rates",
         "source": "BRFG", "tickers": "[]", "url": None, "fetched_at": NOW, "run_id": "t", "run_at": NOW - 50},
        {"headline_id": "ibkr:s", "provider": "ibkr", "published_at": NOW - HOUR, "headline": "Apple beats",
         "source": "Dow Jones", "tickers": json.dumps(["AAPL"]), "url": None, "fetched_at": NOW, "run_id": "t",
         "run_at": NOW - 40}])
    page = report.render_html(now=NOW)
    market, stocks = page.index('id="heads-market"'), page.index('id="heads-stocks"')
    assert "Piyasa · son 24 saat" in page and "Hisseler · son 24 saat" in page
    assert market < page.index("Fed holds rates") < stocks < page.index("Apple beats")
    assert f"NEWS_SINCE = {NOW - 40!r}" in page and "/api/news/headlines?since=" in page and "}, 2000);" in page
    # Polled and asked-for text is never parsed as HTML: the board's own scripts build rows with textContent. The one
    # innerHTML there is the shared watch-list helper's escaped button (rcWatchButtons), as on every board.
    own = (report._JS + report._TQ_JS).replace("innerHTML = rcWatchButtons(t)", "")
    assert "textContent" in page and "innerHTML" not in own


# ── F2: one freshness a lane ─────────────────────────────────────────────────────────────────────────────────────

def test_each_lane_says_when_its_own_newest_row_was_fetched():
    """Review F2 (18 Nov 2026): the page's header time is the board's newest write of any lane, so the hourly X
    load hid a per-ticker fetch that had been dead for a day. Each lane now carries its own reading."""
    rawstore.write_rows("news_headlines", [
        {"headline_id": "ibkr:m", "provider": "ibkr", "published_at": NOW - HOUR, "headline": "Fed holds rates",
         "source": "BRFG", "tickers": "[]", "url": None, "fetched_at": NOW - 120, "run_id": "t", "run_at": NOW - 120},
        {"headline_id": "ibkr:s", "provider": "ibkr", "published_at": NOW - 2 * HOUR, "headline": "Apple beats",
         "source": "Dow Jones", "tickers": json.dumps(["AAPL"]), "url": None, "fetched_at": NOW - 26 * HOUR,
         "run_id": "t", "run_at": NOW - 26 * HOUR},
        {"headline_id": "x:1", "provider": "grok-x", "published_at": NOW - HOUR, "headline": "SPY bid",
         "source": "@a", "tickers": "[]", "url": "https://x.com/a/status/1", "fetched_at": NOW - 300,
         "run_id": "t", "run_at": NOW - 300, "kind": "news", "option": "", "x_check": None},
    ])
    page = report.render_html(now=NOW)
    market, stocks, x = (page.index(f'id="heads-{k}"') for k in ("market", "stocks", "x"))
    assert page.index("son veri 14:58 · 2 dk önce") < market                  # the tape lane: 2 minutes old
    assert market < page.index("son veri 13:00 · 1 gün önce") < stocks        # the dead per-ticker lane says so
    assert stocks < page.index("son veri 14:55 · 5 dk önce") < x              # the X lane


def test_a_lane_with_no_row_at_all_says_so(seeded):
    page = report.render_html(now=NOW)                 # `seeded` has a stocks and a market row, no tweet
    assert page.count("bu kulvarda hiç veri yok") == 1
    assert page.index('id="heads-x"') > page.index("bu kulvarda hiç veri yok")
