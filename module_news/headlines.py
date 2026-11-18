"""Market headlines for the News board from the IBKR Gateway (avo, 9 Nov 2026 20:54 Amsterdam: "Ibkr kullanalim").

IBKR serves news per contract, not as one market feed (measured 9 Nov: Dow Jones live, 50+ headlines a name a week,
none for SPY). So the board asks for the Dow Jones headlines (``DJ-N`` news, ``DJ-RT`` real-time) of the names on two watch lists
(``LISTS``): avo's own lists, the stock picks, then the News list, every name. Two requests a name (its contract id,
then its headlines), headlines only: the article body is never fetched.

Paced: a pass asks ``PER_PASS`` names, the next ones after the ``news_meta`` cursor ``headlines_cursor``, so every
name is asked in turn, about once an hour, and IBKR's farm gets about 30 news requests a 5-minute pass, not one per
name of every list. Each name's newest headlines of the last ``WINDOW_S`` are kept, and only a story not stored yet,
or met under a new name, is written; a headline id is made from the story's words, so the same story under two names
or two providers is one row whose ``tickers`` lists every name. A gateway that is down writes nothing, moves no cursor
and says why; a name it does not know is skipped.

``load_tape`` (#673) loads the market-wide headlines the listener (``module_news/tape.py``) appended since the last
load: same ids, ``tickers`` empty (the page's "Piyasa" lane). A story also met under a name keeps that name.

``load_x`` loads the Grok "X saatlik özet" mails the fetcher (``module_news/x_feed.py``) saved since the last load:
one row per tweet, ``provider`` ``grok-x`` (the page's "X" lane), with the tweet's ``kind`` and ``option``.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from RevenueChaser.core import config, ibkr_login, rawstore
from RevenueChaser.core.providers import ibkr_tws as ibkr
from RevenueChaser.module_news import tape, x_feed
from RevenueChaser.module_news.calendar import META
from RevenueChaser.rcdata import read

TABLE = "news_headlines"
CURSOR_KEY = "headlines_cursor"
TAPE_MARK_KEY = "tape_mark"
X_MARK_KEY = "x_mark"
# A client id of its own: the IV history client is 73, and a second client with the same id is refused (326).
CLIENT_ID = 74
PROVIDERS = "DJ-N+DJ-RT"
SOURCE = "Dow Jones"
PER_TICKER = 20
WINDOW_S = 24 * 3600
#: Names asked a pass (W1's note, 18 Nov 2026: 391 names every 5 minutes is ~780 requests, more than IBKR paces).
#: Thirty a pass is ~60 news requests in 10 minutes, IBKR's historical-data pacing; 391 names go round in ~65 min.
PER_PASS = 30
#: The watch lists the per-ticker headlines read (avo, 18 Nov 2026 21:53 Amsterdam: "Hepsini watchliste.duckdb ye
#: bagla"; 22:31: "Artik watchlist.duckbd den secmeliler"), by ``wl_list.feeds``: ``""`` is every one of avo's own
#: lists, then the stock picks (together ``rcdata.read.PICKED``, the one definition of avo's picks), then the News
#: list (``jobs.news``, seeded with the large caps the code held until then). No cap: every name is asked each pass.
#: Read strictly, list by list (``read.job_list``), so an unreadable list is named on the board, not dropped.
LISTS = (*read.PICKED, "news")

_META_PREFIX = re.compile(r"^\{[^}]*\}!?")
_IB_TIME = "%Y-%m-%d %H:%M:%S.0"


def tickers(*lists) -> list[str]:
    """The names of ``lists`` in their order, each list sorted, no repeats."""
    out: list[str] = []
    for names in lists:
        for t in sorted(str(x).upper() for x in names or ()):
            if t and t not in out:
                out.append(t)
    return out


def clean(headline: str) -> str:
    """The headline without Dow Jones' ``{A:…:C:…}!`` metadata prefix."""
    return _META_PREFIX.sub("", str(headline or "")).strip()


def _epoch(text: str) -> float | None:
    try:
        return datetime.strptime(text.strip(), _IB_TIME).replace(tzinfo=timezone.utc).timestamp()
    except (ValueError, AttributeError):
        return None


def batch(names: list[str]) -> list[str]:
    """The next ``PER_PASS`` of ``names`` (alphabetical) after the cursor, wrapping round; every name once at most."""
    order = sorted(set(names))
    rows = rawstore.query(f"SELECT value FROM {META} WHERE key = ?", [CURSOR_KEY], db="news")
    after = str(rows[0]["value"]) if rows else ""
    start = next((i for i, t in enumerate(order) if t > after), 0)
    return (order[start:] + order[:start])[:PER_PASS]


def story_id(text: str) -> str:
    """By the story's words, not IBKR's article id: DJ-N and DJ-RT carry one story under two ids."""
    key = re.sub(r"\W+", " ", text.lower()).strip()
    return "ibkr:" + hashlib.sha1(key.encode()).hexdigest()[:16]


def _merge_tickers(rows: list[dict]) -> list[dict]:
    """Each row's ``tickers`` (a list) joined with what is stored under its id, as the JSON text the table keeps.
    Returns the rows that are new or gained a name: the others are already stored as they are."""
    stored = {r["headline_id"]: r for r in rawstore.query(
        f"SELECT headline_id, tickers FROM {TABLE} WHERE headline_id IN ({', '.join('?' for _ in rows)})",
        [r["headline_id"] for r in rows], db="news")} if rows else {}
    changed = []
    for r in rows:
        old = json.loads(stored[r["headline_id"]]["tickers"] or "[]") if r["headline_id"] in stored else []
        merged = sorted(set(old) | set(r["tickers"]))
        if r["headline_id"] not in stored or merged != sorted(old):
            changed.append(r)
        r["tickers"] = json.dumps(merged)
    return changed


def _new_lines(folder: Path, key: str, first: str) -> tuple[list[bytes], dict | None, dict | None]:
    """The whole lines appended to ``folder/*.jsonl`` since the ``news_meta`` mark ``key``, and the old and new mark.

    The mark is ``{"file", "offset"}`` of the first byte not loaded; a line still being written (no newline yet)
    waits for the next load. With no mark, files from ``first`` (a file name) on are read."""
    rows_m = rawstore.query(f"SELECT value FROM {META} WHERE key = ?", [key], db="news")
    try:
        mark = json.loads(rows_m[0]["value"]) if rows_m else None
    except (TypeError, ValueError):
        mark = None
    files = sorted(folder.glob("*.jsonl")) if folder.exists() else []
    first = mark["file"] if mark else first
    lines: list[bytes] = []
    new_mark = mark
    for path in (f for f in files if f.name >= first):
        start = int(mark["offset"]) if mark and path.name == mark["file"] else 0
        with open(path, "rb") as f:
            f.seek(start)
            data = f.read()
        done = data[:data.rfind(b"\n") + 1]
        lines.extend(done.splitlines())
        new_mark = {"file": path.name, "offset": start + len(done)}
    return lines, mark, new_mark


def _move_mark(key: str, mark: dict | None, new_mark: dict | None, now: float) -> None:
    if new_mark and new_mark != mark:
        rawstore.write_rows(META, [{"key": key, "value": json.dumps(new_mark), "run_at": now}])


def _tape_rows(lines: list[bytes], now: float, run_id: str) -> list[dict]:
    """The tape lines as ``news_headlines`` rows, one a story, ``tickers`` still a list."""
    found: dict[str, dict] = {}
    for line in lines:
        try:
            it = json.loads(line)
            at = float(it["time_ms"]) / 1000.0
        except (ValueError, TypeError, KeyError):
            continue
        text = clean(it.get("headline"))
        if not text:
            continue
        found.setdefault(story_id(text), {
            "headline_id": story_id(text), "provider": "ibkr", "published_at": at, "headline": text,
            "source": SOURCE if str(it.get("provider", "")).startswith("DJ") else str(it.get("provider") or ""),
            "tickers": [], "url": None, "fetched_at": now, "run_id": run_id, "run_at": now})
    return list(found.values())


def load_tape(now: float | None = None, run_id: str | None = None) -> dict:
    """Load the tape lines appended since the mark into ``news_headlines``. Returns ``read`` and ``stored``.
    With no mark, only the files of the last ``WINDOW_S`` are read."""
    now = time.time() if now is None else now
    run_id = run_id or f"news-{int(now)}"
    lines, mark, new_mark = _new_lines(tape.tape_dir(), TAPE_MARK_KEY, tape.day_file(now - WINDOW_S).name)
    rows = _tape_rows(lines, now, run_id)
    _merge_tickers(rows)
    if rows:
        rawstore.write_rows(TABLE, rows)
    _move_mark(TAPE_MARK_KEY, mark, new_mark, now)
    return {"read": len(lines), "stored": len(rows)}


def peek_tape(now: float | None = None) -> list[dict]:
    """The tape lines the next ``load_tape`` will store, as rows, without writing anything: the page's poll shows a
    market headline the moment the listener appends it, not at the next 5-minute pass (avo, 18 Nov 2026). Their
    ``run_at`` is ``None``: the poll's cursor must not move past rows a running pass has not written yet."""
    now = time.time() if now is None else now
    lines, _, _ = _new_lines(tape.tape_dir(), TAPE_MARK_KEY, tape.day_file(now - WINDOW_S).name)
    return [{**r, "tickers": "[]", "run_at": None} for r in _tape_rows(lines, now, "peek")]


def load_x(now: float | None = None, run_id: str | None = None) -> dict:
    """Load the Grok X mails saved since the mark into ``news_headlines``. Returns ``mails``, ``stored``,
    ``refused`` (rows ``x_feed.parse`` turned down) and ``cut`` (mails that declared more rows than they carried).
    With no mark, every saved mail is read (the first load is the backfill)."""
    now = time.time() if now is None else now
    run_id = run_id or f"news-{int(now)}"
    lines, mark, new_mark = _new_lines(x_feed.x_dir(config.MARKET_RAW_DIR), X_MARK_KEY, "")
    found: dict[str, dict] = {}
    mails = refused = cut = 0
    for line in lines:
        try:
            text = str(json.loads(line)["text"])
        except (ValueError, TypeError, KeyError):
            continue
        mails += 1
        rows, bad = x_feed.parse(text, now, run_id)
        refused += len(bad)
        declared = x_feed.declared(text)
        cut += declared is not None and declared > len(rows) + len(bad)
        for r in rows:
            found[r["headline_id"]] = {**r, "tickers": json.dumps(r["tickers"])}
    if found:
        rawstore.write_rows(TABLE, list(found.values()))
    _move_mark(X_MARK_KEY, mark, new_mark, now)
    return {"mails": mails, "stored": len(found), "refused": refused, "cut": int(cut)}


# Contract ids do not change; kept for the dashboard process's life so a 5-minute pass asks one request a name.
_CON_IDS: dict[str, int] = {}


def fetch(names: list[str], now: float | None = None, run_id: str | None = None,
          target: tuple[str, int] | None = None) -> dict:
    """One pass over the next ``batch`` of ``names``. Returns ``tickers`` (names asked), ``of`` (all names),
    ``stored``, ``skipped`` (names IBKR does not know), ``failed`` (names whose request IBKR refused for another
    reason, with the error) and ``error`` (or None)."""
    now = time.time() if now is None else now
    run_id = run_id or f"news-{int(now)}"
    of, names = len(set(names)), batch(names)
    since = now - WINDOW_S
    host, port = target or ibkr_login.target()
    found: dict[str, dict] = {}            # story key -> row
    skipped: list[str] = []
    failed: list[str] = []
    try:
        with ibkr.TWSClient(host, port, client_id=CLIENT_ID) as client:
            req = 0
            for name in names:
                req += 1
                try:
                    if name not in _CON_IDS:
                        _CON_IDS[name] = client.con_id(req, ibkr.contract_for(name))
                    con_id = _CON_IDS[name]
                    req += 1
                    items = client.news(req, con_id, PROVIDERS, "", "", PER_TICKER)   # the newest; see news()
                except ibkr.HistoryError as e:
                    # 200 "no security definition": a name IBKR does not know, the same every run, only a note.
                    # Any other code (a lapsed feed, pacing) is a failure the board shows.
                    (skipped if e.code == 200 else failed).append(name if e.code == 200 else f"{name} ({e})")
                    continue
                for it in items:
                    text, at = clean(it["headline"]), _epoch(it["time"])
                    if not text or at is None or at < since:
                        continue
                    row = found.setdefault(story_id(text), {
                        "headline_id": story_id(text), "provider": "ibkr", "published_at": at,
                        "headline": text, "source": SOURCE, "tickers": [], "url": None, "fetched_at": now,
                        "run_id": run_id, "run_at": now})
                    if name not in row["tickers"]:
                        row["tickers"].append(name)
    except ibkr.TWSError as e:                 # no session, or the gateway went away: nothing is written
        return {"tickers": len(names), "of": of, "stored": 0, "skipped": skipped, "failed": failed, "error": str(e)}
    rows = _merge_tickers(list(found.values()))
    if rows:
        rawstore.write_rows(TABLE, rows)
    # The gateway answered: the next pass asks the next names. A refused name waits its turn and the banner names it.
    if names:
        rawstore.write_rows(META, [{"key": CURSOR_KEY, "value": names[-1], "run_at": now}])
    return {"tickers": len(names), "of": of, "stored": len(rows), "skipped": skipped, "failed": failed, "error": None}


# ── One name on demand (plan step 3; avo, 18 Nov 2026 21:43 Amsterdam, card D1 "B"; 23:16 "sen yayina al") ──
#: Its own client id, so a click never meets the 5-minute pass's 74 (326 "client id already in use").
ON_DEMAND_CLIENT_ID = 75
#: Dow Jones (news, real time) and Briefing (general, upgrades/downgrades): the four of the eight IBKR lists for
#: this account that carry per-name stories (measured 18 Nov 2026 on homesrv, reqNewsProviders).
ON_DEMAND_PROVIDERS = "DJ-N+DJ-RT+BRFG+BRFUPDN"
#: IBKR's cap on one reqHistoricalNews; one request, so a click is far inside the pacing.
ON_DEMAND_TOTAL = 300
ON_DEMAND_DAYS = 7
ASK_KEY = "ticker_ask:"


def source_of(provider: str) -> str:
    """The newsroom behind an IBKR provider code: ``DJ-…`` Dow Jones, ``BRF…`` Briefing, else the code."""
    code = str(provider or "")
    return SOURCE if code.startswith("DJ") else "Briefing" if code.startswith("BRF") else code


def fetch_ticker(name: str, now: float | None = None, target: tuple[str, int] | None = None) -> dict:
    """Ask IBKR for one name's newest ``ON_DEMAND_TOTAL`` headlines of the last ``ON_DEMAND_DAYS`` and store them
    like a pass does (one row a story, ``tickers`` merged). The answer is kept in ``news_meta`` under
    ``ticker_ask:<NAME>`` (``at``, ``stored``, ``error``), which the page reads back with the rows. Returns it."""
    now = time.time() if now is None else now
    name = str(name).strip().upper()
    since = now - ON_DEMAND_DAYS * 86400
    host, port = target or ibkr_login.target()
    found: dict[str, dict] = {}
    error = None
    try:
        with ibkr.TWSClient(host, port, client_id=ON_DEMAND_CLIENT_ID) as client:
            if name not in _CON_IDS:
                _CON_IDS[name] = client.con_id(1, ibkr.contract_for(name))
            for it in client.news(2, _CON_IDS[name], ON_DEMAND_PROVIDERS, "", "", ON_DEMAND_TOTAL):
                text, at = clean(it["headline"]), _epoch(it["time"])
                if text and at is not None and at >= since:
                    found.setdefault(story_id(text), {
                        "headline_id": story_id(text), "provider": "ibkr", "published_at": at, "headline": text,
                        "source": source_of(it.get("provider")), "tickers": [name], "url": None,
                        "fetched_at": now, "run_id": f"news-ticker-{int(now)}", "run_at": now})
    except ibkr.HistoryError as e:
        error = f"IBKR does not know {name}" if e.code == 200 else str(e)
    except ibkr.TWSError as e:
        error = str(e)
    rows = _merge_tickers(list(found.values())) if not error else []
    if rows:
        rawstore.write_rows(TABLE, rows)
    ask = {"at": now, "stored": len(rows), "found": len(found), "error": error}
    rawstore.write_rows(META, [{"key": ASK_KEY + name, "value": json.dumps(ask), "run_at": now}])
    return ask


def ticker_rows(name: str, now: float | None = None) -> dict:
    """What the page shows for one name: its stored headlines of the last ``ON_DEMAND_DAYS``, newest first, and the
    last ask's answer (``None`` before the first ask)."""
    now = time.time() if now is None else now
    name = str(name).strip().upper()
    rows = rawstore.query(
        f"SELECT headline_id, published_at, headline, source, tickers, url FROM {TABLE} "
        f"WHERE provider = 'ibkr' AND tickers LIKE ? AND published_at >= ? "
        f"ORDER BY published_at DESC LIMIT {ON_DEMAND_TOTAL}",
        [f'%"{name}"%', now - ON_DEMAND_DAYS * 86400], db="news")
    got = rawstore.query(f"SELECT value FROM {META} WHERE key = ?", [ASK_KEY + name], db="news")
    try:
        ask = json.loads(got[0]["value"]) if got else None
    except (TypeError, ValueError):
        ask = None
    return {"ticker": name, "rows": rows, "ask": ask}
