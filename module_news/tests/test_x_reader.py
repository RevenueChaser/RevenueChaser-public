"""RC's own X reader for the News board's X lane (plan step 5): the Following timeline of RC's X account."""
from __future__ import annotations

import json
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from RevenueChaser.core import rawstore
from RevenueChaser.module_news import x_check, x_feed, x_reader

NY = ZoneInfo("America/New_York")
ID = 2120251362529419593                                 # @kiantrades, 10 Nov 2026 15:24 New York
AT = x_feed.status_time(ID)


def _ny(*args) -> float:
    return datetime(*args, tzinfo=NY).timestamp()


def _raw(tid, text, user="kiantrades", note=None, wrap=False):
    t = {"rest_id": str(tid), "legacy": {"full_text": text},
         "core": {"user_results": {"result": {"core": {"screen_name": user}}}}}
    if note:
        t["note_tweet"] = {"note_tweet_results": {"result": {"text": note}}}
    return {"__typename": "TweetWithVisibilityResults", "tweet": t} if wrap else t


def _pages(*pages):
    left = list(pages)

    def fetch():
        page = left.pop(0) if left else []
        if isinstance(page, Exception):
            raise page
        return page
    return fetch


def test_a_pass_is_due_every_half_hour_in_the_session_and_every_four_hours_otherwise():
    wed = _ny(2026, 11, 18, 11, 0)
    assert x_reader.in_session(wed) and not x_reader.in_session(_ny(2026, 11, 18, 16, 0))
    assert not x_reader.in_session(_ny(2026, 11, 21, 11, 0))                           # Saturday
    assert x_reader.due(wed, None)
    assert x_reader.due(wed, wed - 29 * 60) and not x_reader.due(wed, wed - 20 * 60)  # a tick a little early counts
    sat = _ny(2026, 11, 21, 11, 0)
    assert not x_reader.due(sat, sat - 3600) and x_reader.due(sat, sat - 4 * 3600)


def test_a_timeline_entry_becomes_a_post_and_the_rest_is_dropped():
    assert x_reader.tweet(_raw(ID, "$SPY  759C\n11/20")) == {"id": str(ID), "account": "kiantrades",
                                                             "text": "$SPY 759C 11/20"}
    assert x_reader.tweet(_raw(ID, "short", wrap=True))["text"] == "short"           # TweetWithVisibilityResults
    assert x_reader.tweet(_raw(ID, "cut…", note="the whole long post"))["text"] == "the whole long post"
    assert x_reader.tweet({"entryId": "cursor-bottom-1"}) is None
    assert x_reader.tweet(_raw("abc", "no id")) is None and x_reader.tweet(_raw(ID, "  ")) is None


def test_a_post_is_a_row_of_the_x_lane():
    r = x_reader.row({"id": str(ID), "account": "kiantrades", "text": "$SPY 759C 11/20exp $1.8M premium $SPY $QQQ"},
                     AT + 60, "r1")
    assert r["headline_id"] == f"x:{ID}" and r["provider"] == "x-follow" and r["published_at"] == AT
    assert r["kind"] == "option" and r["option"] and json.loads(r["tickers"]) == ["SPY", "QQQ"]
    assert r["url"] == f"https://x.com/kiantrades/status/{ID}" and r["source"] == "@kiantrades"
    assert x_reader.row({"id": str(ID), "account": "", "text": "Fed speaks at 2"}, AT, "r1")["kind"] == "news"


def test_read_stops_at_the_page_that_reaches_the_newest_stored_post():
    fetch = _pages([_raw(ID + 30, "c"), _raw(ID + 20, "b")], [_raw(ID + 10, "a"), _raw(ID, "old")], [_raw(ID - 5, "x")])
    pauses = []
    got = x_reader.read(fetch, ID, pause=lambda: pauses.append(1))
    assert [p["text"] for p in got] == ["c", "b", "a"] and len(pauses) == 1           # the third page never asked
    capped = x_reader.read(_pages(*[[_raw(ID + n, str(n))] for n in range(9, 0, -1)]), 0, pause=lambda: None,
                           max_pages=3)
    assert len(capped) == 3


def test_read_fails_closed():
    with pytest.raises(x_reader.ReadFailed, match="RuntimeError"):
        x_reader.read(_pages([_raw(ID + 2, "a")], RuntimeError("401")), 0, pause=lambda: None)
    with pytest.raises(x_reader.ReadFailed, match="no posts list"):
        x_reader.read(_pages({"errors": []}), 0, pause=lambda: None)


def _grok_row():
    rawstore.write_rows("news_headlines", [{
        "headline_id": f"x:{ID}", "provider": "grok-x", "published_at": AT, "headline": "Grok's line",
        "source": "@kiantrades", "tickers": '["SPY"]', "url": "u", "kind": "option", "option": "SPY 759C 11/20",
        "x_check": json.dumps({"status": "seen"}), "fetched_at": AT, "run_id": "g", "run_at": AT}])


def _stored():
    return {r["headline_id"]: r for r in rawstore.query(
        "SELECT headline_id, provider, headline, x_check FROM news_headlines", db="news")}


def _mark():
    return json.loads(rawstore.query("SELECT value FROM news_meta WHERE key = ?", [x_reader.STATE_KEY],
                                     db="news")[0]["value"])


def test_run_stores_new_posts_keeps_a_grok_row_and_moves_the_mark():
    _grok_row()
    now = AT + 600
    out = x_reader.run(now=now, fetch=_pages([_raw(ID + 9, "$NVDA earnings beat"), _raw(ID, "same tweet")]),
                       pause=lambda: None)
    assert out == {"skipped": False, "read": 2, "stored": 1}
    rows = _stored()
    assert rows[f"x:{ID + 9}"]["provider"] == "x-follow"
    assert rows[f"x:{ID}"]["provider"] == "grok-x" and json.loads(rows[f"x:{ID}"]["x_check"]) == {"status": "seen"}
    assert _mark() == {"newest": ID + 9, "last_run": now}
    assert x_reader.run(now=now + 60, fetch=_pages())["skipped"]                      # not due yet


def test_a_refused_read_writes_nothing_and_leaves_the_mark():
    with pytest.raises(x_reader.ReadFailed):
        x_reader.run(now=AT, fetch=_pages([_raw(ID, "a")], RuntimeError("429")), pause=lambda: None)
    assert _stored() == {}
    assert not rawstore.query("SELECT 1 FROM news_meta WHERE key = ?", [x_reader.STATE_KEY], db="news")


def test_missing_cookies_are_named_not_read(monkeypatch):
    for name in x_reader.COOKIES:
        monkeypatch.delenv(name, raising=False)
    with pytest.raises(x_reader.ReadFailed, match="RC_X_AUTH_TOKEN and RC_X_CT0"):
        x_reader.run(now=AT)


def test_an_option_post_of_the_reader_waits_for_its_uw_check():
    rawstore.write_rows("news_headlines", [x_reader.row(
        {"id": str(ID), "account": "kiantrades", "text": "$SPY 759C 11/20exp $1.8M premium"}, AT, "r")])
    assert [r["headline_id"] for r in x_check._waiting(AT + 60)] == [f"x:{ID}"]
