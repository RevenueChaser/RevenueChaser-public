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
load: same ids, ``tickers`` empty (the page's "Market" lane). A story also met under a name keeps that name.
"""
from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from revenuechaser.core import config, ibkr_login, rawstore
from revenuechaser.core.providers import ibkr_tws as ibkr
from revenuechaser.module_news import store_reads, tape, x_reader
from revenuechaser.rcdata import read

# The board's reader owns the table names (#217); the writes below still happen here.
TABLE = store_reads.HEADLINES
META = store_reads.META
CURSOR_KEY = "headlines_cursor"
TAPE_MARK_KEY = "tape_mark"
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
    stored = store_reads.meta_value(CURSOR_KEY)
    after = "" if stored is None else str(stored)
    start = next((i for i, t in enumerate(order) if t > after), 0)
    return (order[start:] + order[:start])[:PER_PASS]


def story_id(text: str) -> str:
    """By the story's words, not IBKR's article id: DJ-N and DJ-RT carry one story under two ids."""
    key = re.sub(r"\W+", " ", text.lower()).strip()
    return "ibkr:" + hashlib.sha1(key.encode()).hexdigest()[:16]


def _merge_tickers(rows: list[dict]) -> list[dict]:
    """Each row's ``tickers`` (a list) joined with what is stored under its id, as the JSON text the table keeps.
    Returns the rows that are new or gained a name: the others are already stored as they are."""
    stored = store_reads.stored_tickers(r["headline_id"] for r in rows)
    changed = []
    for r in rows:
        old = json.loads(stored[r["headline_id"]] or "[]") if r["headline_id"] in stored else []
        merged = sorted(set(old) | set(r["tickers"]))
        if r["headline_id"] not in stored or merged != sorted(old):
            changed.append(r)
        r["tickers"] = json.dumps(merged)
    return changed


def _stored_ids(ids: list[str]) -> set[str]:
    """The ids of ``ids`` already in the table."""
    return store_reads.stored_headline_ids(ids)


#: The lanes of the News page, in its order, as ``module_news.report.lane`` cuts them.
LANES = store_reads.LANES
#: ``news_meta`` key prefix for "this lane's own fetch last came back clean" (``mark_lane_ok``).
OK_PREFIX = "lane_ok"
#: The lanes that keep such a mark. The ``market`` lane does not: its source is the listener, whose own record is
#: already read (``module_news/tape_state.py``, ``rc_news_tape_written_timestamp_seconds``, #727).
OK_LANES = ("stocks", "x")


#: How long a lane may go without a clean pass before it is late, each from its own cadence and not retyped: the
#: per-ticker pass is queued every ``tape.TRIGGER_S``, so six missed passes; RC's X reader thins to
#: ``x_reader.OFF_EVERY_S`` outside the US session, so one missed pass plus half of it. Exported beside the mark
#: (``rc_news_lane_late_after_seconds``), so Grafana's rule carries no limit of its own either.
LATE_AFTER_S = {"stocks": 6 * tape.TRIGGER_S, "x": int(1.5 * x_reader.OFF_EVERY_S)}


def mark_lane_ok(lane: str, now: float | None = None) -> None:
    """Record that ``lane``'s own fetch has just come back with nothing refused.

    Freshness cannot carry the alarm on its own: ``fetched_at`` moves only when a row is written, so a lane with
    no news to bring looks exactly like a lane whose fetch is dead, and an alert on it would fire every quiet
    night. This mark moves on a clean pass whether or not it brought a row, so "the per-ticker fetch has not
    worked for an hour" is a question Grafana can ask (review F2, 18 Nov 2026; plan step 6)."""
    now = time.time() if now is None else now
    rawstore.write_rows(META, [{"key": f"{OK_PREFIX}:{lane}", "value": repr(float(now)), "run_at": now}])


def lane_late_after() -> dict[str, float]:
    """How long each lane of ``OK_LANES`` may go without a clean pass, seconds."""
    return {name: float(LATE_AFTER_S[name]) for name in OK_LANES}


def lane_ok() -> dict[str, float | None]:
    """When each lane of ``OK_LANES`` last came back clean; None for one that never has."""
    stored = store_reads.meta_values(f"{OK_PREFIX}:{name}" for name in OK_LANES)
    got = {}
    for key, value in stored.items():
        try:
            got[key.split(":", 1)[1]] = float(value)
        except (TypeError, ValueError, IndexError):
            continue
    return {name: got.get(name) for name in OK_LANES}


def lane_freshness() -> dict[str, float | None]:
    """The newest ``fetched_at`` of each lane of ``LANES``; None for a lane with no row at all.

    One freshness over the whole table cannot see a dead lane (review F2, 18 Nov 2026): the hourly X load keeps
    ``news_headlines.fetched_at`` moving, so the dataset stays "fresh" on Settings and in Grafana while the
    per-ticker IBKR fetch has been down for a day. One reading a lane, which the board shows and Grafana alerts on.
    """
    return store_reads.lane_freshness()


def _new_lines(folder: Path, key: str, first: str) -> tuple[list[bytes], dict | None, dict | None]:
    """The whole lines appended to ``folder/*.jsonl`` since the ``news_meta`` mark ``key``, and the old and new mark.

    The mark is ``{"file", "offset"}`` of the first byte not loaded; a line still being written (no newline yet)
    waits for the next load. With no mark, files from ``first`` (a file name) on are read."""
    stored = store_reads.meta_value(key)
    try:
        mark = json.loads(stored) if stored is not None else None
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
    rows = store_reads.headlines_for_ticker(name, now - ON_DEMAND_DAYS * 86400, ON_DEMAND_TOTAL)
    got = store_reads.meta_value(ASK_KEY + name)
    try:
        ask = json.loads(got) if got is not None else None
    except (TypeError, ValueError):
        ask = None
    return {"ticker": name, "rows": rows, "ask": ask}
