"""RC's own X reader for the News board's X lane (plan step 5; avo, 18 Nov 2026 21:59-23:27 Amsterdam: "sen kendi
islemcini kur twitter icin", "Yarim saatte bir seans acikken, yoksa 4 saatte bir", and 23:27: a new X account whose
follows are the list).

Read-only on X: it pages the **Following** timeline (newest first) of RC's own X account with twifork (the
maintained fork of twikit; the module is still ``twikit``), logged in with the browser cookies ``auth_token`` and
``ct0``. They live in ``/etc/life/secrets.env`` as ``RC_X_AUTH_TOKEN`` and ``RC_X_CT0`` (avo, 18 Nov 2026 23:40:
"secret dosyasina gitmeliler") and reach the dashboard through its environment; never printed. Who is read is decided
on X: avo follows the accounts from that account, so no list is kept here.

It runs as the dashboard job ``news_x_follow`` (the dashboard is the one writer of ``boards/news.duckdb``), queued
every 30 minutes by a timer; ``due`` lets a pass through every 30 minutes while the US session is open and every
4 hours otherwise. A pass stops at the first page that reaches the newest post it already stored, at ``MAX_PAGES``,
or when X has no more, with a pause of ``PAUSE_S`` between pages. **Fails closed:** a refused login, an error from X
or a page without a posts list ends the pass with nothing written and the mark unmoved.

Each post is one ``news_headlines`` row, provider ``x-follow``, ``headline_id`` ``x:<status id>`` (the same id as a
Grok row of the same tweet, which is kept as it is: a stored id is never written again, so its UW check survives),
``published_at`` the id's own time, ``tickers`` its cashtags, ``kind`` ``option`` when it names a contract
(``x_check.contract``), else ``news``.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from datetime import datetime, time as dtime
from zoneinfo import ZoneInfo

from RevenueChaser.core import rawstore
from RevenueChaser.module_news import x_check, x_feed
from RevenueChaser.module_news.calendar import META

PROVIDER = x_feed.FOLLOW_PROVIDER
COOKIES = ("RC_X_AUTH_TOKEN", "RC_X_CT0")
TABLE = "news_headlines"
STATE_KEY = "x_follow_state"
PAGE_SIZE = 40             # a hint; X often serves more and twifork buffers the rest for next()
MAX_PAGES = 5              # a first pass (or one after a long gap) reads the newest ~200 posts, not the history
PAUSE_S = (2.0, 5.0)       # seconds between two pages, drawn at random
SESSION_EVERY_S = 30 * 60  # avo: every half hour while the session is open...
OFF_EVERY_S = 4 * 3600     # ...else every 4 hours
SLACK_S = 120              # a timer tick a little early still counts
NY = ZoneInfo("America/New_York")
_CASHTAG = re.compile(r"\$([A-Z][A-Z0-9.]{0,9})\b")
_ID = re.compile(r"\d{1,25}")


class ReadFailed(RuntimeError):
    """X could not be read, or answered something the board will not store; nothing was written."""


def in_session(now: float) -> bool:
    """The US regular session, Monday to Friday 09:30-16:00 New York.
    shortcut: market holidays count as open; use the exchange calendar if a holiday's extra passes ever matter."""
    t = datetime.fromtimestamp(now, NY)
    return t.weekday() < 5 and dtime(9, 30) <= t.time() < dtime(16, 0)


def due(now: float, last: float | None) -> bool:
    """Whether a pass reads X now: never read, or the session's or the off-hours' interval has passed."""
    if last is None:
        return True
    return now - float(last) >= (SESSION_EVERY_S if in_session(now) else OFF_EVERY_S) - SLACK_S


def _state() -> dict:
    got = rawstore.query(f"SELECT value FROM {META} WHERE key = ?", [STATE_KEY], db="news")
    try:
        return json.loads(got[0]["value"]) if got else {}
    except (TypeError, ValueError):
        return {}


def tweet(raw) -> dict | None:
    """``{id, account, text}`` of one timeline entry (X's tweet result); None for what is not a readable post."""
    t = raw if isinstance(raw, dict) else {}
    if isinstance(t.get("tweet"), dict):                  # TweetWithVisibilityResults
        t = t["tweet"]
    legacy = t.get("legacy") if isinstance(t.get("legacy"), dict) else None
    tid = str(t.get("rest_id") or "")
    if legacy is None or not _ID.fullmatch(tid):
        return None
    user = ((t.get("core") or {}).get("user_results") or {}).get("result") or {}
    account = (user.get("core") or {}).get("screen_name") or (user.get("legacy") or {}).get("screen_name") or ""
    note = (((t.get("note_tweet") or {}).get("note_tweet_results") or {}).get("result") or {}).get("text")
    text = " ".join(str(note or legacy.get("full_text") or "").split())
    return {"id": tid, "account": account, "text": text} if text else None


def row(post: dict, now: float, run_id: str) -> dict:
    """One post as a ``news_headlines`` row of the X lane."""
    at = x_feed.status_time(int(post["id"]))
    text = post["text"]
    found = x_check._CONTRACT.search(text)
    option = found.group(0) if found and x_check.contract(text, at) else ""
    tickers = list(dict.fromkeys(_CASHTAG.findall(text)))[:4]
    account = post["account"] or "i"
    return {"headline_id": f"x:{post['id']}", "provider": PROVIDER, "published_at": at,
            "headline": text[:x_feed.TEXT_MAX], "source": f"@{account}", "tickers": json.dumps(tickers),
            "url": f"https://x.com/{account}/status/{post['id']}", "kind": "option" if option else "news",
            "option": option, "fetched_at": now, "run_id": run_id, "run_at": now}


def read(fetch, newest: int, pause=None, max_pages: int = MAX_PAGES) -> list[dict]:
    """Posts newer than ``newest`` (a status id), newest first. ``fetch()`` returns the next page's raw tweet
    objects (``[]`` at the end). Any error from X raises ``ReadFailed``."""
    pause = pause or (lambda: time.sleep(random.uniform(*PAUSE_S)))
    out: dict[str, dict] = {}
    for n in range(max_pages):
        if n:
            pause()
        try:
            page = fetch()
        except Exception as exc:  # noqa: BLE001 - twikit raises many types; each one means nothing is written
            raise ReadFailed(f"X refused the page ({type(exc).__name__}: {str(exc)[:200]})") from exc
        if not isinstance(page, list):
            raise ReadFailed("X's answer has no posts list")
        posts = [p for p in map(tweet, page) if p]
        for p in posts:
            if int(p["id"]) > newest:
                out.setdefault(p["id"], p)
        if not page or any(int(p["id"]) <= newest for p in posts):
            break
    return list(out.values())


def login(auth_token: str, ct0: str):
    """A ``fetch()`` over the Following timeline, logged in with the two browser cookies."""
    try:
        from twikit import Client
    except ImportError as exc:
        raise ReadFailed("twifork is not installed in the dashboard's Python (pip install -r requirements.txt)") from exc
    client = Client("en-US")
    client.set_cookies({"auth_token": auth_token, "ct0": ct0})
    loop = asyncio.new_event_loop()
    state = {"page": None}

    def fetch():
        # Result.next() serves the posts X sent beyond PAGE_SIZE before it asks again (twifork's own advice).
        page = state["page"]
        page = loop.run_until_complete(client.get_latest_timeline(count=PAGE_SIZE) if page is None else page.next())
        state["page"] = page
        return [tw._data for tw in page]

    return fetch


def run(now: float | None = None, fetch=None, run_id: str | None = None, pause=None) -> dict:
    """One pass when ``due``. Returns ``skipped``, ``read`` (new posts on X) and ``stored`` (rows written)."""
    now = time.time() if now is None else now
    run_id = run_id or f"x-follow-{int(now)}"
    state = _state()
    if not due(now, state.get("last_run")):
        return {"skipped": True, "read": 0, "stored": 0}
    if fetch is None:
        auth_token, ct0 = (os.getenv(n) or "" for n in COOKIES)
        if not (auth_token and ct0):
            raise ReadFailed(f"{' and '.join(COOKIES)} are not set in the dashboard's environment")
        fetch = login(auth_token, ct0)
    newest = int(state.get("newest") or 0)
    posts = read(fetch, newest, pause)
    rows = [row(p, now, run_id) for p in posts]
    stored = {r["headline_id"] for r in rawstore.query(
        f"SELECT headline_id FROM {TABLE} WHERE headline_id IN ({', '.join('?' for _ in rows)})",
        [r["headline_id"] for r in rows], db="news")} if rows else set()
    fresh = [r for r in rows if r["headline_id"] not in stored]
    if fresh:
        rawstore.write_rows(TABLE, fresh)
    newest = max([newest, *(int(p["id"]) for p in posts)])
    rawstore.write_rows(META, [{"key": STATE_KEY, "value": json.dumps({"newest": newest, "last_run": now}),
                                "run_at": now}])
    return {"skipped": False, "read": len(posts), "stored": len(fresh)}
