"""The Welcome page (welcome plan §2): calendar summary, earnings, market snapshot, data freshness; English."""
from __future__ import annotations

import json
from datetime import date, datetime

from revenuechaser.core import rawstore
from revenuechaser.module_news import calendar as cal
from revenuechaser.module_welcome import report

NOW = datetime(2026, 11, 10, 9, 0, tzinfo=cal.AMS).timestamp()        # Tue 10 Nov 09:00 Amsterdam
HOUR = 3600.0


def _at(hh, mm=0, day=10):
    return datetime(2026, 11, day, hh, mm, tzinfo=cal.AMS).timestamp()


def _news():
    rows = [(_at(14, 30), "CPI, Y/Y%", 3, "3.6%", "3.7%"), (_at(16, 0), "Fed President Musalem speaks", 2, None, None),
            (_at(19, 0), "Wholesale inventories", 1, None, None), (_at(20, 0), "Treasury budget", 1, None, None),
            (_at(8, 0), "Early release", 1, None, None)]
    rawstore.write_rows("news_events", [
        {"event_ts": t, "event": e, "type": "report", "importance": i, "forecast": f, "prev": p,
         "reported_period": None, "first_seen": 1.0, "last_seen": 1.0, "retired_at": None, "run_id": "t",
         "run_at": NOW} for t, e, i, f, p in rows])
    rawstore.write_rows("news_highlight", [{
        "session_date": "2026-11-10", "event_ts": _at(14, 30), "event": "CPI, Y/Y%", "type": "report",
        "importance": 3, "forecast": "3.6%", "prev": "3.7%", "text": "Consumer prices.", "text_source": "template",
        "run_id": "t", "run_at": NOW}])




def test_the_calendar_card_reads_the_news_board_file():
    _news()
    page = report.render_html(now=NOW, watchlist={"CRWV"})
    assert "5 releases today" in page and "CPI, Y/Y%" in page and "3.6%" in page
    assert "Fed President Musalem speaks" in page and "Wholesale inventories" in page
    assert "Treasury budget" not in page and "Early release" not in page       # next two after now only
    assert "rc-open-tab" in page and "module_news" in page


def test_without_the_news_board_file_the_card_says_so():
    page = report.render_html(now=NOW, watchlist=set())
    assert "The News board is not built yet" in page








def _fresh_row(job, **over):
    row = {"job": job, "last_status": "ok", "last_finished_at": NOW - 60, "last_ok_at": NOW - 60,
           "last_failed_at": None, "last_error": None, "run_id": "t", "run_at": NOW}
    row.update(over)
    return row


def test_a_builder_file_that_ended_with_gaps_is_flagged_not_ticked():
    """#643 PR 6: the card's rows are the builder's files, named by ``build.FILE_LABELS``."""
    rawstore.write_rows("welcome_freshness", [_fresh_row(
        "market", last_status="gaps",
        last_error="Finished with gaps: 12 of 12 Interactive Brokers calls failed.")])
    page = report.render_html(now=NOW, watchlist=set())
    assert "All good" not in page and "1 file with a problem" in page
    assert "Market-wide series" in page and "module_news" not in page
    assert "! missing data" in page and "✓ ok" not in page and "12 of 12 Interactive Brokers" in page


def test_the_files_are_listed_problems_first_and_in_build_order():
    rawstore.write_rows("welcome_freshness", [_fresh_row("spine"), _fresh_row("prices"),
                                              _fresh_row("options", last_status="error", last_error="HTTP 503")])
    page = report.render_html(now=NOW, watchlist=set())
    order = [page.index(t) for t in ("Options", "Identity and the universe", "Prices and shares")]
    assert order == sorted(order) and "1 file with a problem" in page
    assert "the builder&#x27;s files" in page or "the builder's files" in page


def test_a_file_that_has_not_built_for_a_week_says_so_instead_of_leaving_the_card():
    rawstore.write_rows("welcome_freshness", [
        _fresh_row("ownership", last_finished_at=NOW - 9 * 24 * 3600, last_ok_at=NOW - 9 * 24 * 3600)])
    page = report.render_html(now=NOW, watchlist=set())
    assert "Who owns it, who is short" in page and f"! no run in {report.FRESH_DAYS} days" in page
    assert "1 file with a problem" in page


def test_with_no_builder_run_recorded_the_card_says_that():
    page = report.render_html(now=NOW, watchlist=set())
    assert "No builder run is recorded yet." in page


def test_the_session_clock_gets_the_next_sessions():
    page = report.render_html(now=NOW, watchlist=set())
    sessions = json.loads(page.split("var SESSIONS = ", 1)[1].split(";", 1)[0])
    first = sessions[0]
    assert datetime.fromtimestamp(first[0], cal.AMS).strftime("%H:%M") == "15:30"
    assert datetime.fromtimestamp(first[1], cal.AMS).strftime("%H:%M") == "22:00"
    assert len(sessions) >= 5


def test_phone_friendly_and_themed():
    page = report.render_html(now=NOW, watchlist=set())
    assert "max-width:900px" in page and "min-height:44px" in page and 'data-theme="light"' in page


def test_render_writes_the_board_file(tmp_path, monkeypatch):
    monkeypatch.setattr(report, "OUTPUT_DIR", tmp_path)
    assert report.render(now=NOW, watchlist=set()) == tmp_path / "welcome_latest.html"


def test_a_change_that_rounds_to_zero_reads_flat():
    rawstore.write_rows("welcome_snapshot", [
        {"series": "US10Y", "session_date": date(2026, 11, 9), "close": 4.05, "prev_close": 4.052, "change": -0.002,
         "change_pct": -0.0005, "spark": "[4.052, 4.05]", "run_id": "t", "run_at": NOW}])
    page = report.render_html(now=NOW, watchlist=set())
    assert "-0.00" not in page and "• 0.00" in page


def test_the_headlines_card_shows_the_three_newest_and_polls():
    rawstore.write_rows("news_headlines", [
        {"headline_id": f"ibkr:{i}", "provider": "ibkr", "published_at": NOW - i * 60, "headline": f"Story {i}",
         "source": "Dow Jones", "tickers": json.dumps(["AAPL"] if i % 2 else []), "url": None, "fetched_at": NOW,
         "run_id": "t", "run_at": NOW - i} for i in range(1, 6)])
    page = report.render_html(now=NOW, watchlist=set())
    assert "Latest headlines" in page and "Story 1" in page and "Story 3" in page and "Story 4" not in page
    assert "HEADS_SINCE = " in page and "/api/news/headlines?since=" in page


def test_without_headlines_the_card_says_so():
    _news()
    page = report.render_html(now=NOW, watchlist=set())
    assert "No headline in the last 24 hours." in page and '<p class="empty">No headline in the last 24' in page


# ── #643 PR 5b: the earnings card ──────────────────────────────────────────────────────────────────────────────

def _earnings_row(ticker, day, **over):
    row = {"earnings_date": day, "ticker": ticker, "report_session": "premarket", "full_name": f"{ticker} Inc",
           "expected_move_perc": 0.052, "report_time": "premarket", "source_session": date(2026, 11, 9),
           "first_seen": NOW - HOUR, "last_seen": NOW, "retired_at": None, "run_id": "t", "run_at": NOW}
    row.update(over)
    return row


def test_the_earnings_card_names_the_company_and_the_session_it_was_stored_on():
    rawstore.write_rows("welcome_earnings", [_earnings_row("AAA", date(2026, 11, 10)),
                                             _earnings_row("BBB", date(2026, 11, 11),
                                                           report_session="afterhours")])
    page = report.render_html(now=NOW, watchlist={"AAA"})
    assert "AAA" in page and "AAA Inc" in page and "on my list" in page
    assert "Pre-market" in page and "After hours" in page and "±5.2%" in page
    assert "as stored on 2026-11-09" in page


def test_a_retired_name_is_not_on_the_card():
    rawstore.write_rows("welcome_earnings", [_earnings_row("AAA", date(2026, 11, 10)),
                                             _earnings_row("GONE", date(2026, 11, 10), retired_at=NOW)])
    page = report.render_html(now=NOW, watchlist=set())
    assert "AAA" in page and "GONE" not in page


def test_a_name_with_no_confirmed_report_time_says_so():
    rawstore.write_rows("welcome_earnings", [
        _earnings_row("AAA", date(2026, 11, 10), report_session="unknown", report_time=None)])
    page = report.render_html(now=NOW, watchlist=set())
    assert "Time not confirmed" in page
