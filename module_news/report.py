"""The News board page (plan §6, mock ``News.dc.html``): today's US economic calendar, this week, the day's highlight
and the market headlines, times in Europe/Amsterdam.

Store-only: it reads ``boards/news.duckdb`` and never fetches. Event names stay as the provider serves them; the board's
own words are English (avo, 19 Nov 2026: every word the boards show is English). Phone first: one column under 900 px,
44 px touch targets, light and dark from the shell's theme.
"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from pathlib import Path

from RevenueChaser.core import econ_importance, rawstore
from RevenueChaser.core.config import OUTPUT_DIR
from RevenueChaser.core.html_safe import esc
from RevenueChaser.core.html_safe import script_json
from RevenueChaser.core.reporting_common import (FILTERS_CSS, FILTERS_JS, THEME_CSS, THEME_JS, combobox_html, help_html,
                                                 provider_health_html, watchlist_html, write_artifact)
from RevenueChaser.module_news.calendar import AMS, EVENTS, FDA_TYPE, HIGHLIGHT, local_day, served_value
from RevenueChaser.module_news import headlines, x_check
from RevenueChaser.module_news.x_feed import X_PROVIDERS

FILENAME = "news_latest.html"
HEADLINES = "news_headlines"
WEEK_DAYS = 7
HEADLINE_HOURS = 24
HEADLINE_LIMIT = 30

#: ``target_precision`` of an FDA catalyst UW gives a real day for; anything else is a window (#807).
DAY_PRECISION = "day"
#: At most this many FDA catalysts with no day of their own stand in the "Later, no day yet" group (#808).
UNDATED_LIMIT = 40
#: How far back the undated group is read: a window that is still open can have begun up to a year ago (a
#: ``2026-Q4`` catalyst resolves to 1 October), so the rows are read wide and ``window_open`` cuts them.
UNDATED_LOOKBACK_DAYS = 370
#: How long an FDA window lasts from its first day, by precision: a quarter three months, a half year and "mid"
#: six, "late" the last quarter of the year.
_WINDOW_MONTHS = {"quarter": 3, "half": 6, "mid": 6, "late": 3}
#: How the tail of UW's target text reads on the board: ``2027-MID`` -> ``Mid 2027``, ``2027-Q2`` -> ``Q2 2027``.
_WINDOW_WORD = {"MID": "Mid", "LATE": "Late"}
#: An indication or a description is UW's free text; the row shows this much of it.
INDICATION_CHARS = 72

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August", "September", "October",
          "November", "December")
WEEKDAYS = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_KIND = {"report": "Data", "fed-speaker": "Fed", "fomc": "FOMC"}
_LEVEL = {3: "high", 2: "medium", 1: "low"}


def hm(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), AMS).strftime("%H:%M")


def long_date(d) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def day_label(d) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def week_days(now: float) -> list[date]:
    """The seven days of the Amsterdam week today falls in, Monday first (#808's week strip)."""
    today = local_day(now)
    monday = today - timedelta(days=today.weekday())
    return [monday + timedelta(days=i) for i in range(WEEK_DAYS)]


def dated(e: dict) -> bool:
    """True when UW gave this catalyst a real day; false for a quarter, a half year, "mid" or "late" (#807)."""
    return str(e.get("target_precision") or DAY_PRECISION).lower() == DAY_PRECISION


def window_open(e: dict, today: date) -> bool:
    """True while an undated catalyst's window has not ended: its first day plus the precision's length."""
    months = _WINDOW_MONTHS.get(str(e.get("target_precision") or "").lower(), 0)
    d = local_day(e["event_ts"])
    m = d.month - 1 + months
    return date(d.year + m // 12, m % 12 + 1, 1) > today


def window_label(text) -> str:
    """UW's own target text as the board writes it: ``2027-Q2`` -> ``Q2 2027``, ``2027-LATE`` -> ``Late 2027``."""
    raw = str(text or "").strip()
    year, _, part = raw.partition("-")
    if not part or not year.isdigit():
        return raw or "No date"
    part = part.upper()
    return f"{_WINDOW_WORD.get(part, part)} {year}"


def _load(now: float) -> tuple[list[dict], list[dict], dict | None, list[dict], float | None]:
    days = week_days(now)
    start = datetime(days[0].year, days[0].month, days[0].day, tzinfo=AMS)
    end = start + timedelta(days=WEEK_DAYS)
    today = local_day(now)
    events = rawstore.query(
        f"SELECT * FROM {EVENTS} WHERE event_ts >= ? AND event_ts < ? AND retired_at IS NULL "
        f"ORDER BY event_ts, event", [start.timestamp(), end.timestamp()], db="news")
    # The FDA catalysts UW gives no day for (a quarter, a half year, "late"): they belong to no day of the strip,
    # so they stand in their own group under the FDA tab and are read outside the week's window (#808).
    undated = [e for e in rawstore.query(
        f"SELECT * FROM {EVENTS} WHERE type = ? AND retired_at IS NULL AND coalesce(target_precision, ?) <> ? "
        f"AND event_ts >= ? ORDER BY event_ts, event LIMIT {UNDATED_LIMIT}",
        [FDA_TYPE, DAY_PRECISION, DAY_PRECISION,
         (start - timedelta(days=UNDATED_LOOKBACK_DAYS)).timestamp()], db="news")
        if window_open(e, today)]
    hl = rawstore.query(f"SELECT * FROM {HIGHLIGHT} WHERE session_date = ?", [today.isoformat()], db="news")
    x = f"coalesce(provider, '') IN ({', '.join(repr(p) for p in X_PROVIDERS)})"
    lanes = (f"NOT {x} AND coalesce(tickers, '[]') = '[]'", f"NOT {x} AND coalesce(tickers, '[]') <> '[]'",
             f"{x} AND coalesce(kind, '') <> 'other'")        # the X lane leaves out what Grok filed as "other"
    heads = [r for cond in lanes for r in rawstore.query(      # each lane its own newest LIMIT
        f"SELECT * FROM {HEADLINES} WHERE published_at >= ? AND {cond} "
        f"ORDER BY published_at DESC LIMIT {HEADLINE_LIMIT}", [now - HEADLINE_HOURS * 3600], db="news")]
    # The page's "updated" time is its newest write: the calendar's, or the 5-minute headline pass's.
    got = rawstore.query(f"SELECT max(run_at) AS t FROM {EVENTS}", db="news")
    stamps = [float(t) for t in [got[0]["t"] if got else None] + [h.get("run_at") for h in heads] if t is not None]
    return events, undated, (hl[0] if hl else None), heads, (max(stamps) if stamps else None)


def dots_html(level) -> str:
    n = int(level or 1)
    return (f'<span class="dots" title="{_LEVEL.get(n, "low")} importance" aria-label="{_LEVEL.get(n, "low")} '
            f'importance">'
            f'{econ_importance.dots(n)}</span>')


def vals_html(e: dict) -> str:
    fc, prev = served_value(e.get("forecast")), served_value(e.get("prev"))
    return (f'<div class="vals"><span>Forecast <b>{esc(fc or "–")}</b></span>'
            f'<span>Previous <b>{esc(prev or "–")}</b></span></div>')


def _day_attrs(e: dict, today: date) -> str:
    """What the week strip filters a row by: its own Amsterdam day, hidden unless that day is the pressed one."""
    d = local_day(e["event_ts"])
    return f' data-day="{d.isoformat()}"' + ("" if d == today else " hidden")


def _row(e: dict, now: float, hl_key) -> str:
    key = (e["event_ts"], e["event"], e["type"])
    cls = "ev hl" if key == hl_key else "ev"
    past = ' data-past="1"' if float(e["event_ts"]) < now else ""
    kind = _KIND.get(str(e.get("type") or "").lower(), "Data")
    return (f'<li class="{cls}"{past}{_day_attrs(e, local_day(now))}>'
            f'<span class="t">{hm(e["event_ts"])}</span>'
            f'<div class="nm"><span class="kind">{kind}</span> {dots_html(e.get("importance"))}'
            f'<div class="name">{esc(e["event"])}</div></div>{vals_html(e)}</li>')


def _clip(value, chars: int = INDICATION_CHARS) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= chars else text[:chars - 1].rstrip() + "…"


def fda_vals_html(e: dict) -> str:
    """An FDA row's two columns: what the drug is for, and where the application stands (#808's approved mock)."""
    return (f'<div class="vals"><span>Indication <b>{esc(_clip(e.get("indication")) or "–")}</b></span>'
            f'<span>Status <b>{esc(e.get("status") or "–")}</b></span></div>')


def _fda_sub(e: dict) -> str:
    """The small line under the name: UW's own target text when it is not a day, and the outcome once there is one."""
    parts = []
    if not dated(e) and e.get("target_text"):
        parts.append(f'Unusual Whales serves this one as {e["target_text"]}, not a day')
    if e.get("outcome"):
        parts.append(f'Outcome: {_clip(e["outcome"])}')
    return f'<div class="sub">{esc(" · ".join(parts))}</div>' if parts else ""


def _fda_row(e: dict, now: float, strip: bool = True) -> str:
    """One FDA catalyst. A day it really has stands as ``20 Nov``; a window stands as its own words with a
    "no day yet" chip, so a quarter is never read as a day (#807, #808)."""
    today, d = local_day(now), local_day(e["event_ts"])
    if dated(e):
        t = f'<span class="t">{d.day} {MONTHS[d.month - 1][:3]}</span>'
        chip = ""
    else:
        t = f'<span class="t na">{esc(window_label(e.get("target_text")))}</span>'
        chip = ' <span class="pchip">no day yet</span>'
    past = ' data-past="1"' if d < today else ""
    return (f'<li class="ev"{past}{_day_attrs(e, today) if strip else ""}>{t}'
            f'<div class="nm"><span class="kind">FDA</span> {dots_html(e.get("importance"))}{chip}'
            f'<div class="name">{esc(e["event"])}</div>{_fda_sub(e)}</div>{fda_vals_html(e)}</li>')


def _strip(events: list[dict], now: float) -> str:
    """The week's seven days, Monday first: each with its own count of releases and FDA catalysts, today marked.
    Pressing a day filters both lists to it; without JavaScript the page stands on today (#808)."""
    today, out = local_day(now), []
    counts = {d: [0, 0] for d in week_days(now)}
    for e in events:
        row = counts.get(local_day(e["event_ts"]))
        if row is not None:
            row[1 if str(e.get("type") or "") == FDA_TYPE else 0] += 1
    for d, (n_econ, n_fda) in counts.items():
        cls = "wkd" + (" today" if d == today else "") + ("" if n_econ or n_fda else " empty")
        body = ((f'<i class="e">{n_econ}</i>' if n_econ else "") + (f'<i class="f">{n_fda}</i>' if n_fda else "")
                ) or "<i>&middot;</i>"
        out.append(f'<button type="button" class="{cls}" data-day="{d.isoformat()}" onclick="newsDay(this)" '
                   f'aria-pressed="{"true" if d == today else "false"}" '
                   f'aria-label="{day_label(d)}: {n_econ} releases, {n_fda} FDA catalysts">'
                   f'<span class="wd">{WEEKDAYS[d.weekday()][:3]}</span><span class="dn">{d.day}</span>'
                   f'<span class="cnt">{body}</span></button>')
    return '<div class="wk" role="group" aria-label="This week">' + "".join(out) + "</div>"


def _cd(label: str, body: str) -> str:
    return f'<p class="cd" id="cd-{label}">{body}</p>'


def _econ_cd(events: list[dict], now: float) -> str:
    """The next release still to come this week, with a clock the page counts down (#808's approved mock)."""
    nxt = next((e for e in events if str(e.get("type") or "") != FDA_TYPE and float(e["event_ts"]) > now), None)
    if not nxt:
        return _cd("econ", "No release left this week.")
    left = float(nxt["event_ts"]) - now
    return _cd("econ", f'Coming in <b data-ts="{float(nxt["event_ts"]):.0f}">{_hms(left)}</b> · '
                       f'<span class="nm2">{esc(nxt["event"])}</span> {hm(nxt["event_ts"])}')


def _fda_cd(rows: list[dict], now: float) -> str:
    """The next FDA catalyst with a day of its own. A catalyst has a date and no time, so there is no clock: today
    says so, a later day says how many days away it is."""
    today = local_day(now)
    nxt = next((e for e in rows if dated(e) and local_day(e["event_ts"]) >= today), None)
    if not nxt:
        return _cd("fda", "No FDA catalyst with a day of its own left this week.")
    d = local_day(nxt["event_ts"])
    days = (d - today).days
    when = "today, no time published" if days == 0 else day_label(d)
    clock = "—" if days == 0 else f"{days} day{'s' if days != 1 else ''}"
    return _cd("fda", f'Coming in <b>{clock}</b> · <span class="nm2">{esc(nxt["event"])}</span> {when}')


def _hms(seconds: float) -> str:
    s = max(0, int(seconds))
    h, m, x = s // 3600, (s % 3600) // 60, s % 60
    return f"{h}:{m:02d}:{x:02d}" if h else f"{m}:{x:02d}"


def _list(rows: list[str], shown: int, empty: str) -> str:
    """One list and its own "nothing on this day" line. ``shown`` is how many of the rows the pressed day leaves
    visible: with none, the list goes and the line stands. The strip swaps the two as the day changes."""
    return (f'<ul class="list" data-day-list{"" if shown else " hidden"}>{"".join(rows)}</ul>'
            f'<p class="empty dayempty"{" hidden" if shown else ""}>{empty}</p>')


def _calendar(events: list[dict], undated: list[dict], now: float, hl_key) -> str:
    """The calendar card: the week strip, then the Economic and FDA lists of the pressed day (#808)."""
    today = local_day(now)
    econ = [e for e in events if str(e.get("type") or "") != FDA_TYPE]
    fda = [e for e in events if str(e.get("type") or "") == FDA_TYPE]
    n_econ = sum(1 for e in econ if local_day(e["event_ts"]) == today)
    n_fda = sum(1 for e in fda if local_day(e["event_ts"]) == today)
    later = ('<h3 class="day">Later, no day yet</h3><ul class="list">'
             + "".join(_fda_row(e, now, strip=False) for e in undated) + "</ul>") if undated else ""
    return (f'{_strip(events, now)}'
            f'<div class="tabs" role="tablist" aria-label="Calendar">'
            f'<button type="button" role="tab" aria-selected="true" aria-controls="cal-econ" '
            f'onclick="newsTab(this)">Economic <span class="n" data-n="econ">{n_econ}</span></button>'
            f'<button type="button" role="tab" aria-selected="false" aria-controls="cal-fda" '
            f'onclick="newsTab(this)">FDA <span class="n" data-n="fda">{n_fda}</span></button></div>'
            f'<div id="cal-econ" role="tabpanel">{_econ_cd(events, now)}'
            f'{_list([_row(e, now, hl_key) for e in econ], n_econ, "Nothing on this day’s economic calendar.")}</div>'
            f'<div id="cal-fda" role="tabpanel" hidden>{_fda_cd(fda, now)}'
            f'{_list([_fda_row(e, now) for e in fda], n_fda, "No FDA catalyst on this day.")}{later}</div>')


def _highlight(hl: dict | None) -> str:
    if not hl:
        return ('<section class="card feat"><h2 class="lbl">Highlight</h2>'
                '<p class="empty">No highlight today.</p></section>')
    return (f'<section class="card feat"><h2 class="lbl">Highlight</h2>'
            f'<div class="feat-name">{esc(hl["event"])}</div>'
            f'<div class="muted">{hm(hl["event_ts"])} Amsterdam · {dots_html(hl.get("importance"))}</div>'
            f'{vals_html(hl)}<p class="why">{esc(hl.get("text"))}</p></section>')


def _tickers(value) -> list[str]:
    try:
        got = json.loads(value) if isinstance(value, str) else (value or [])
    except ValueError:
        return []
    return [str(t) for t in got if t][:4] if isinstance(got, list) else []


def lane(row: dict) -> str:
    """``x`` for a tweet (the Grok X mails or RC's own X reader), ``market`` for a broad-tape headline (no ticker, #673), else
    ``stocks``."""
    if row.get("provider") in X_PROVIDERS:
        return "x"
    return "stocks" if _tickers(row.get("tickers")) else "market"


_LANES = {"market": ("Market", "No headline from the market tape yet."),
          "stocks": ("Stocks", "No headline yet."),
          "x": ("X", "No post from the X summaries yet.")}
#: The tweet kinds of the X lane, in the board's words (the JS keeps the same map).
X_KINDS = {"news": "news", "level": "level", "option": "option", "macro": "macro", "position": "position",
           "other": "other"}


def _check(r: dict) -> dict:
    try:
        return json.loads(r["x_check"]) if r.get("x_check") else {}
    except ValueError:
        return {}


def x_lines(r: dict) -> tuple[str, str]:
    """An X row's contract chip and its fact line: the UW check for an option tweet, else Grok's option field."""
    state = _check(r)
    return x_check.chip(state), (x_check.facts(state) or (r.get("option") or ""))


def _curated(rows: list[dict]) -> list[dict]:
    """The X lane: one card a contract and session (the same print tweeted by two accounts is one card, the
    accounts joined), newest first."""
    out, seen = [], {}
    for r in rows:
        state = _check(r)
        key = (state.get("occ"), state.get("session")) if state.get("occ") else None
        if key and key in seen:
            first = seen[key]
            if r.get("source") and r["source"] not in first["source"]:
                first["source"] = f'{first["source"]}, {r["source"]}'
            continue
        r = dict(r)
        out.append(r)
        if key:
            seen[key] = r
    return out


def _badge_html(state: dict) -> str:
    cls, icon, label, tip = x_check.badge(state)
    return f'<span class="vb {cls}" title="{esc(tip)}"><b aria-hidden="true">{icon}</b>{esc(label)}</span>'


def _fold(label: str, chart: str) -> str:
    """A chart closed until clicked (avo, 11 Nov 2026 08:34 Amsterdam: "Plotlar click to expand ile gosterilmeli")."""
    return f'<details class="xd"><summary>{label}</summary>{chart}</details>' if chart else ""


def _head_li(r: dict) -> str:
    tk = "".join(f'<span class="tk">{esc(t)}</span>' for t in _tickers(r.get("tickers")))
    kind = f'<span class="xk">{esc(X_KINDS.get(r.get("kind") or "", r.get("kind")))}</span>' if r.get("kind") else ""
    src = f' · {esc(r["source"])}' if r.get("source") else ""
    text = esc(r.get("headline"))
    if r.get("url") and str(r["url"]).startswith(("https://", "http://")):
        text = f'<a href="{esc(r["url"])}" target="_blank" rel="noopener noreferrer">{text}</a>'
    x = lane(r) == "x"
    state = _check(r) if x else {}
    chip, line = x_lines(r) if x else ("", "")
    if chip:
        tk = f'<span class="tk">{esc(chip)}</span>'
    elif x:
        tk = ""                                    # the group's header names the ticker
    opt = f'<div class="xo{" ok" if state.get("status") == "seen" else ""}">{esc(line)}</div>' if line else ""
    if x:
        move = x_check.price_move(state, float(r["published_at"]))
        opt += f'<div class="xm">{esc(move)}</div>' if move else ""
        opt += _fold("Trade chart", x_check.chart_svg(state, float(r["published_at"])))
    badge = _badge_html(state) if x else ""
    return (f'<li class="hd" data-hid="{esc(r["headline_id"])}" data-at="{float(r["published_at"])}">'
            f'<div class="muted meta">{hm(r["published_at"])}{src} {kind}{tk}{badge}</div>'
            f'<div class="htext">{text}</div>{opt}</li>')


def x_group(r: dict) -> str:
    """The X lane's group of a row: its contract's ticker, else its first ticker, else "" (General)."""
    state = _check(r)
    return state.get("ticker") or state.get("px_tk") or (_tickers(r.get("tickers")) or [""])[0].upper()


def _group_li(key: str, rows: list[dict]) -> str:
    """One ticker: its name, how many posts of which kinds, how many UW confirmed, the session's price line with every
    tweet on it, then the posts."""
    kinds = ", ".join(dict.fromkeys(X_KINDS.get(r.get("kind") or "", r.get("kind") or "") for r in rows if r.get("kind")))
    seen = sum(1 for r in rows if _check(r).get("status") == "seen")
    opts = sum(1 for r in rows if r.get("kind") == "option")
    conf = (f' · <span class="vb {"ok" if seen else "wait"}"><b aria-hidden="true">{"✓" if seen else "–"}</b>'
            f'{seen}/{opts} UW confirmed</span>') if opts else ""
    with_px = [r for r in rows if _check(r).get("px")]
    chart = ""
    if with_px:
        newest = with_px[0]
        session = x_check.session_day(float(newest["published_at"]))
        marks = [(float(r["published_at"]), f'{hm(r["published_at"])} {r.get("source") or ""}'.strip())
                 for r in rows if x_check.session_day(float(r["published_at"])) == session]
        chart = _fold("Price chart", x_check.price_svg(_check(newest)["px"], marks))
    name = f'<span class="sym">{esc(key)}</span>' if key else '<span class="sym gen">General</span>'
    return (f'<li class="xg" data-grp="{esc(key)}" data-at="{float(rows[0]["published_at"])}">'
            f'<div class="xgh">{name}<span class="muted">{len(rows)} posts · {esc(kinds)}{conf}</span></div>'
            f'{chart}<ul class="list">{"".join(_head_li(r) for r in rows)}</ul></li>')


def _x_groups(rows: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(x_group(r), []).append(r)
    order = sorted(groups.items(), key=lambda kv: (kv[0] == "", -float(kv[1][0]["published_at"])))
    return "".join(_group_li(k, v) for k, v in order)


def _ago(seconds: float) -> str:
    """How long ago, coarse: ``just now``, ``7 min ago``, ``3 h ago``, ``2 d ago`` (avo, 19 Nov 2026: every word
    the boards show is English)."""
    s = max(0.0, float(seconds))
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{int(s // 60)} min ago"
    if s < 86400:
        return f"{int(s // 3600)} h ago"
    return f"{int(s // 86400)} d ago"


def _fresh_html(key: str, fresh: dict, now: float) -> str:
    """The lane's own freshness line (review F2, 18 Nov 2026).

    The page's header time is the board's newest write of any lane, so a dead per-ticker fetch cannot be seen there
    while the X load keeps writing. Each lane says when its own newest row was fetched; the page states it and never
    judges it, because every lane has its own cadence (the tape writes in seconds, the per-ticker pass goes round in
    about an hour, X is hourly) and the alarm belongs in Grafana, where the threshold can be changed."""
    at = fresh.get(key)
    if at is None:
        return '<p class="fresh">no data in this lane yet</p>'
    return f'<p class="fresh">last data {hm(at)} · {_ago(now - at)}</p>'


def _headlines(rows: list[dict], fresh: dict, now: float) -> dict[str, str]:
    """One card a lane: Market (the broad tape), Stocks (per ticker) and X (the Grok X mails and RC's own reader,
    one group a ticker), each with its row count and its own freshness; the page's poll adds to their lists."""
    out = {}
    for key, (title, empty) in _LANES.items():
        mine = [r for r in rows if lane(r) == key]
        mine = (_curated(mine) if key == "x" else mine)[:HEADLINE_LIMIT]
        body = _x_groups(mine) if key == "x" else "".join(_head_li(r) for r in mine)
        out[key] = (f'<section class="card"><h2 class="lbl">{title} · last {HEADLINE_HOURS} h</h2>'
                    f'{_fresh_html(key, fresh, now)}'
                    f'<p class="empty"{" hidden" if mine else ""}>{empty}</p>'
                    f'<ul class="list" id="heads-{key}">{body}</ul></section>')
        out[key + "_n"] = len(mine)
    return out


def api_rows(since: float, limit: int = 2 * HEADLINE_LIMIT) -> list[dict]:
    """Headlines stored after ``since`` (their ``run_at``), plus the tape lines not stored yet (``peek_tape``), newest
    first, as the poll draws them."""
    rows = rawstore.query(
        f"SELECT headline_id, provider, published_at, headline, source, tickers, url, kind, option, x_check, run_at "
        f"FROM {HEADLINES} "
        f"WHERE run_at > ? AND published_at >= ? ORDER BY published_at DESC LIMIT {int(limit)}",
        [float(since), time.time() - HEADLINE_HOURS * 3600], db="news")
    rows = [r for r in rows if not (lane(r) == "x" and r.get("kind") == "other")]
    cutoff, seen = time.time() - HEADLINE_HOURS * 3600, {r["headline_id"] for r in rows}
    rows += [r for r in headlines.peek_tape() if r["headline_id"] not in seen and r["published_at"] >= cutoff]
    rows = sorted(rows, key=lambda r: -float(r["published_at"]))[:int(limit)]
    return [{"headline_id": r["headline_id"], "published_at": r["published_at"], "hm": hm(r["published_at"]),
             "headline": r["headline"], "source": r.get("source") or "",
             "tickers": [x_lines(r)[0]] if lane(r) == "x" and x_lines(r)[0] else (
                 [] if lane(r) == "x" else _tickers(r.get("tickers"))),
             "kind": X_KINDS.get(r.get("kind") or "", r.get("kind") or ""),
             "option": x_lines(r)[1] if lane(r) == "x" else "",
             "badge": list(x_check.badge(_check(r))[:3]) if lane(r) == "x" else None,
             "move": x_check.price_move(_check(r), float(r["published_at"])) if lane(r) == "x" else "",
             "group": x_group(r) if lane(r) == "x" else "",
             "url": r["url"] if str(r.get("url") or "").startswith(("https://", "http://")) else "",
             "lane": lane(r), "run_at": r["run_at"]} for r in rows]


def _picker() -> list[dict]:
    """The ticker box's names: My Universe (a watch list holds names picked inside it; avo, 18 Nov 2026), with the
    spine's company name. A spine that cannot be read leaves the box open to any symbol instead of empty."""
    from RevenueChaser.rcdata import read
    try:
        names = read.my_universe_tickers() or set()
        by = {r["ticker"]: r.get("name") or "" for r in read.identity(names)} if names else {}
    except Exception:  # noqa: BLE001 - a page must render; the box then takes any symbol
        return []
    return [{"ticker": t, "name": by.get(t, "")} for t in sorted(names)]


def _ticker_box() -> str:
    """One name's headlines on demand (plan step 3, mock approved by avo 18 Nov 2026 23:16): pick, ask IBKR, read back."""
    return (f'<section class="card tbox" aria-labelledby="tq-l"><h2 class="lbl" id="tq-l">News for one stock</h2>'
            f'<div class="tq">{combobox_html("tq", "tq-l", "Ticker or company name, e.g. NVDA")}'
            f'<button type="button" class="go" id="tq-go" disabled onclick="tqAsk()">Get headlines</button></div>'
            f'<div id="tq-out" hidden><div class="th"><span id="tq-watch"></span><span class="sym" id="tq-sym"></span>'
            f'<span class="muted" id="tq-meta"></span></div>'
            f'<div class="chips" id="tq-chips" role="group" aria-label="Source"></div>'
            f'<div class="state" id="tq-state" role="status" hidden></div>'
            f'<ul class="list" id="tq-rows"></ul></div></section>')


_CSS = """
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
.wrap{max-width:1200px;margin:0 auto;padding:16px}
.top{display:flex;flex-wrap:wrap;justify-content:space-between;gap:8px 16px;align-items:flex-end;margin-bottom:12px}
.eyebrow{color:var(--muted);font-size:12px;letter-spacing:.04em;text-transform:uppercase}
h1{margin:2px 0 0;color:var(--bright);font-size:22px}
.muted{color:var(--muted);font-size:12.5px}
.grid{display:grid;grid-template-columns:minmax(0,1.3fr) minmax(0,1fr);gap:16px}
.side{display:flex;flex-direction:column;gap:16px}
.card{background:var(--card);border:1px solid var(--border);border-radius:12px;padding:14px 16px}
.lbl{margin:0 0 10px;font-size:12px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted);font-weight:600}
.fresh{margin:-6px 0 10px;color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.tabs{display:flex;gap:8px;margin-bottom:12px}
.ptabs{display:flex;gap:4px;margin-bottom:16px;border-bottom:1px solid var(--border);overflow-x:auto}
.ptabs button{min-height:44px;padding:0 16px;border:0;border-bottom:2px solid transparent;background:transparent;
 color:var(--muted);font:inherit;font-weight:600;cursor:pointer;white-space:nowrap}
.ptabs button[aria-selected="true"]{color:var(--bright);border-bottom-color:var(--amber)}
.ptabs .n{margin-left:6px;padding:1px 7px;border-radius:999px;background:var(--input-bg);font-size:11.5px;
 font-variant-numeric:tabular-nums}
.cols{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px;align-items:start}
#pg-x{max-width:900px}
.tabs button{min-height:44px;padding:0 18px;border-radius:10px;border:1px solid var(--border);background:transparent;
 color:var(--fg);font:inherit;cursor:pointer}
.tabs button[aria-selected="true"]{background:var(--input-bg);color:var(--bright);border-color:var(--amber)}
.list{list-style:none;margin:0;padding:0}
.ev{display:grid;grid-template-columns:60px 1fr auto;gap:8px 12px;align-items:center;padding:10px 8px;
 border-bottom:1px solid var(--border);min-height:44px}
.ev.hl{border:1px solid var(--amber);border-radius:10px;background:var(--input-bg)}
.ev.hl .t{color:var(--amber)}
.ev[data-past="1"]{opacity:.55}
.t{font-variant-numeric:tabular-nums;color:var(--bright);font-weight:600}
.kind{font-size:11.5px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.dots{color:var(--amber);letter-spacing:1px;font-size:11px}
.name{color:var(--bright)}
.vals{display:flex;gap:12px;font-size:12.5px;color:var(--muted);flex-wrap:wrap}
.vals b{color:var(--fg);font-weight:600}
.day{margin:14px 0 4px;font-size:13px;color:var(--muted);font-weight:600}
.feat-name{font-size:18px;color:var(--bright);font-weight:600;margin-bottom:2px}
.feat .vals{margin:10px 0}
.why{margin:8px 0 0;line-height:1.6}
.hd{padding:10px 0;border-bottom:1px solid var(--border);overflow-wrap:anywhere}
.htext a{color:var(--bright);text-decoration:none}
.htext a:hover{text-decoration:underline}
.tk{display:inline-block;margin-left:4px;padding:0 6px;border-radius:6px;background:var(--input-bg);
 color:var(--sky);font-size:11.5px}
.xk{display:inline-block;margin-left:4px;padding:0 6px;border-radius:6px;border:1px solid var(--border);
 color:var(--amber);font-size:11.5px}
.xo{margin-top:4px;color:var(--muted);font-size:12.5px;font-variant-numeric:tabular-nums}
.xo.ok{color:var(--fg);border-left:3px solid var(--amber);padding-left:8px}
.xc{margin:8px 0 0}
.xc svg{display:block;width:100%;height:72px}
.xc .xb{stroke:var(--border);stroke-width:1;vector-effect:non-scaling-stroke}
.xc .xt{stroke:var(--amber);stroke-width:2;stroke-dasharray:4 3;vector-effect:non-scaling-stroke}
.xc .pa{fill:var(--pos)}.xc .pb{fill:var(--neg)}.xc .pm{fill:var(--badge-gray)}
.xc figcaption{display:flex;justify-content:space-between;gap:8px;color:var(--muted);font-size:11.5px;
 font-variant-numeric:tabular-nums}
.xc .lg i{display:inline-block;width:10px;height:10px;border-radius:2px;margin:0 3px 0 8px;vertical-align:-1px}
.xc .lg i.pa{background:var(--pos)}.xc .lg i.pb{background:var(--neg)}
.xc .lg i.xt{height:0;border-top:2px dashed var(--amber);border-radius:0}
.meta{display:flex;flex-wrap:wrap;align-items:center;gap:4px}
.vb{display:inline-flex;align-items:center;gap:4px;margin-left:4px;padding:0 7px;border-radius:999px;font-size:11.5px;
 border:1px solid currentColor;line-height:18px;white-space:nowrap}
.vb b{font-weight:700}
.vb.ok{color:var(--pos)}.vb.no{color:var(--neg)}.vb.warn{color:var(--amber)}.vb.wait{color:var(--muted)}
.vb.id{color:var(--sky)}
.xg{padding:12px 0 4px;border-bottom:2px solid var(--border)}
.xg:first-child{padding-top:0}
.xg>.list>.hd:last-child{border-bottom:0}
.xgh{display:flex;flex-wrap:wrap;align-items:baseline;gap:4px 10px}
.sym{font:600 16px/1.3 ui-monospace,"JetBrains Mono","SFMono-Regular",Menlo,monospace;color:var(--bright)}
.sym.gen{font-family:inherit}
.xm{margin-top:2px;color:var(--muted);font-size:12.5px;font-variant-numeric:tabular-nums}
.xp{position:relative;margin:8px 0 2px}
.xp svg{display:block;width:100%;height:96px}
.xp .ln{fill:none;stroke-width:2;stroke-linejoin:round;stroke-linecap:round;vector-effect:non-scaling-stroke}
.xp .ln.up{stroke:var(--pos)}.xp .ln.down{stroke:var(--neg)}
.xp .hit{fill:transparent}
.xd>summary{min-height:44px;display:flex;align-items:center;gap:6px;cursor:pointer;color:var(--sky);font-size:12.5px;
 list-style:none}
.xd>summary::-webkit-details-marker{display:none}
.xd>summary::before{content:"▸";width:12px}
.xd[open]>summary::before{content:"▾"}
.plot{position:relative;margin-right:64px}
.plot .ya{position:absolute;left:100%;padding-left:6px;transform:translateY(-50%);color:var(--muted);font-size:11px;
 line-height:1;font-variant-numeric:tabular-nums;white-space:nowrap}
.xp .gr,.xc .gr{stroke:var(--border);stroke-width:1;stroke-dasharray:2 3;vector-effect:non-scaling-stroke}
.plot>i.tw{position:absolute;width:12px;height:12px;margin:-6px 0 0 -6px;border-radius:50%;background:var(--amber);
 border:2px solid var(--card);cursor:default}
.xp figcaption{display:flex;flex-wrap:wrap;justify-content:space-between;gap:4px 8px;color:var(--muted);
 font-size:11.5px;font-variant-numeric:tabular-nums}
.xp .lg i.tw{display:inline-block;width:9px;height:9px;border-radius:50%;background:var(--amber);margin-right:4px;
 vertical-align:-1px}
.empty{color:var(--muted);margin:6px 0}
.tbox{margin-bottom:16px}
.tq{display:flex;gap:8px;align-items:stretch;flex-wrap:wrap}
.tq .rcf-combo{flex:1 1 220px;min-width:0}
.tq .rcf-combo input{min-height:44px;width:100%;background:var(--input-bg);color:var(--fg);border:1px solid var(--border);
 border-radius:10px}
.tq .go{min-height:44px;padding:0 18px;border-radius:10px;border:1px solid var(--amber);background:var(--input-bg);
 color:var(--bright);font:inherit;font-weight:600;cursor:pointer}
.tq .go:disabled{opacity:.5;cursor:default}
.th{display:flex;align-items:center;flex-wrap:wrap;gap:4px 10px;margin:14px 0 4px}
.th .sym{font-size:18px}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 4px}
.chip{min-height:44px;display:inline-flex;align-items:center;padding:0 12px;border-radius:999px;background:transparent;
 border:1px solid var(--border);color:var(--muted);font:inherit;font-size:12.5px;cursor:pointer}
.chip[aria-pressed="true"]{color:var(--bright);border-color:var(--amber)}
.tday{margin:12px 0 0;font-size:12.5px;color:var(--muted);font-weight:600}
.state{margin:10px 0;padding:12px 14px;border-radius:10px;border:1px dashed var(--border)}
.state.err{border:1px solid var(--neg)}
.spin{display:inline-block;width:12px;height:12px;border:2px solid var(--border);border-top-color:var(--amber);
 border-radius:50%;margin-right:8px;vertical-align:-1px;animation:tqspin 1s linear infinite}
@keyframes tqspin{to{transform:rotate(360deg)}}
@media (prefers-reduced-motion:reduce){.spin{animation:none}}
.foot{margin-top:16px;color:var(--muted);font-size:12px}
/* ── #808: the week strip, the category tabs' counts and the countdown (mock approved by avo 20 Nov 2026) ── */
.wk{display:grid;grid-template-columns:repeat(7,minmax(0,1fr));gap:6px;margin:0 0 14px}
.wkd{min-height:var(--touch);display:flex;flex-direction:column;align-items:center;justify-content:center;gap:2px;
 padding:8px 2px;border:1px solid var(--border);border-radius:10px;background:transparent;color:var(--fg);
 font:inherit;cursor:pointer;text-align:center}
.wkd .wd{font-size:11px;letter-spacing:.04em;text-transform:uppercase;color:var(--muted)}
.wkd .dn{font-size:16px;font-weight:600;color:var(--bright);font-variant-numeric:tabular-nums;line-height:1.1}
.wkd .cnt{display:flex;gap:6px;font-size:11px;font-variant-numeric:tabular-nums;color:var(--muted)}
.wkd .cnt i{font-style:normal}
.wkd .cnt .e::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;
 background:var(--accent);margin-right:3px;vertical-align:1px}
.wkd .cnt .f::before{content:"";display:inline-block;width:6px;height:6px;border-radius:50%;
 background:var(--amber);margin-right:3px;vertical-align:1px}
.wkd[aria-pressed="true"]{border-color:var(--accent);background:var(--input-bg)}
.wkd.today .dn{color:var(--accent)}
.wkd.today{box-shadow:inset 0 -2px 0 var(--accent)}
.wkd.empty .dn{color:var(--muted)}
.cd{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin:0 0 10px;padding:8px 12px;
 border:1px dashed var(--border);border-radius:10px;color:var(--muted);font-size:12.5px}
.cd b{color:var(--bright);font-variant-numeric:tabular-nums}
.cd .nm2{color:var(--fg)}
.pchip{display:inline-block;padding:0 6px;border-radius:6px;background:var(--input-bg);color:var(--muted);
 font-size:11px;white-space:nowrap}
.ev .t.na{color:var(--muted);font-weight:400;font-size:12px}
.sub{color:var(--muted);font-size:12px;margin-top:2px}
[hidden]{display:none!important}
@media (max-width:900px){.grid,.cols{grid-template-columns:minmax(0,1fr)}.feat{order:-1}}
@media (max-width:560px){.ev{grid-template-columns:60px 1fr}.vals{grid-column:2}.wrap{padding:12px}
 .wk{gap:4px}.wkd{padding:6px 0}.wkd .cnt{flex-direction:column;gap:0}}
"""

_JS = """
function _headLi(r){
  var li = document.createElement('li'); li.className = 'hd';
  li.setAttribute('data-hid', r.headline_id); li.setAttribute('data-at', r.published_at);
  var m = document.createElement('div'); m.className = 'muted';
  m.textContent = r.hm + (r.source ? ' · ' + r.source : '') + ' ';
  if(r.kind){ var k = document.createElement('span'); k.className = 'xk'; k.textContent = r.kind; m.appendChild(k); }
  r.tickers.forEach(function(t){ var s = document.createElement('span'); s.className = 'tk'; s.textContent = t; m.appendChild(s); });
  if(r.badge){ var b = document.createElement('span'); b.className = 'vb ' + r.badge[0];
    var bi = document.createElement('b'); bi.setAttribute('aria-hidden', 'true'); bi.textContent = r.badge[1];
    b.appendChild(bi); b.appendChild(document.createTextNode(r.badge[2])); m.appendChild(b); }
  m.className = 'muted meta';
  var h = document.createElement('div'); h.className = 'htext';
  if(r.url){ var a = document.createElement('a'); a.href = r.url; a.target = '_blank'; a.rel = 'noopener noreferrer';
    a.textContent = r.headline; h.appendChild(a); } else { h.textContent = r.headline; }
  li.appendChild(m); li.appendChild(h);
  if(r.option){ var o = document.createElement('div'); o.className = r.option.indexOf('UW confirmed:') === 0 ? 'xo ok' : 'xo';
    o.textContent = r.option; li.appendChild(o); }
  if(r.move){ var mv = document.createElement('div'); mv.className = 'xm'; mv.textContent = r.move; li.appendChild(mv); }
  return li;
}
function _addHead(r){
  if(document.querySelector('[data-hid="' + r.headline_id + '"]')) return;
  var ul = document.getElementById('heads-' + r.lane); if(!ul) return;
  if(r.lane === 'x'){ ul = _xGroup(ul, r); }
  var li = _headLi(r), kids = ul.children, i = 0;
  while(i < kids.length && parseFloat(kids[i].getAttribute('data-at')) > r.published_at) i++;
  ul.insertBefore(li, kids[i] || null);
  while(ul.children.length > HEAD_LIMIT) ul.removeChild(ul.lastChild);
  var empty = ul.parentNode.querySelector('.empty'); if(empty) empty.hidden = true;
}
function _xGroup(top, r){
  var g = null, gs = top.children;
  for(var i = 0; i < gs.length; i++){ if(gs[i].getAttribute('data-grp') === r.group){ g = gs[i]; break; } }
  if(!g){
    g = document.createElement('li'); g.className = 'xg'; g.setAttribute('data-grp', r.group);
    var h = document.createElement('div'); h.className = 'xgh'; var n = document.createElement('span');
    n.className = r.group ? 'sym' : 'sym gen'; n.textContent = r.group || 'General'; h.appendChild(n); g.appendChild(h);
    var l = document.createElement('ul'); l.className = 'list'; g.appendChild(l);
    top.insertBefore(g, top.firstChild);
  }
  g.setAttribute('data-at', Math.max(parseFloat(g.getAttribute('data-at') || 0), r.published_at));
  return g.querySelector('ul');
}
function newsPoll(){
  fetch('/api/news/headlines?since=' + NEWS_SINCE, {cache: 'no-store'}).then(function(r){ return r.json(); })
    .then(function(d){
      if(!d || !d.ok) return;
      d.rows.forEach(function(r){ NEWS_SINCE = Math.max(NEWS_SINCE, r.run_at); _addHead(r); });
    }).catch(function(){});
}
setInterval(function(){ if(!document.hidden) newsPoll(); }, 2000);   // the tape is read live (peek_tape)
function pageTab(btn, keep){
  newsTab(btn);
  if(!keep){ try { localStorage.setItem('rc-news-page', btn.getAttribute('aria-controls')); } catch(e) {} }
}
(function(){
  var want = null; try { want = localStorage.getItem('rc-news-page'); } catch(e) {}
  var b = want && document.querySelector('.ptabs [aria-controls="' + want + '"]'); if(b) pageTab(b, true);
})();
function newsTab(btn){
  var tabs = btn.parentNode.querySelectorAll('button');
  for(var i = 0; i < tabs.length; i++){
    var on = tabs[i] === btn;
    tabs[i].setAttribute('aria-selected', on ? 'true' : 'false');
    document.getElementById(tabs[i].getAttribute('aria-controls')).hidden = !on;
  }
}
function _hms(s){                                     // the countdown's clock: m:ss, h:mm:ss past the hour
  s = Math.max(0, Math.round(s));
  var h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
  var p = function(n){ return (n < 10 ? '0' : '') + n; };
  return h ? h + ':' + p(m) + ':' + p(x) : m + ':' + p(x);
}
function newsTick(){
  var b = document.querySelector('#cd-econ b[data-ts]'); if(!b) return;
  var left = parseFloat(b.getAttribute('data-ts')) - Date.now() / 1000;
  b.textContent = left > 30 ? _hms(left) : 'now';
}
setInterval(newsTick, 1000); newsTick();
function newsDay(btn){                                // the week strip: one day's releases and catalysts at a time
  var day = btn.getAttribute('data-day'), s = document.querySelectorAll('.wkd'), i = 0;
  for(i = 0; i < s.length; i++) s[i].setAttribute('aria-pressed', s[i] === btn ? 'true' : 'false');
  var lists = document.querySelectorAll('[data-day-list]');
  for(i = 0; i < lists.length; i++){
    var ul = lists[i], rows = ul.children, n = 0;
    for(var j = 0; j < rows.length; j++){
      var mine = rows[j].getAttribute('data-day') === day;
      rows[j].hidden = !mine; if(mine) n++;
    }
    ul.hidden = n === 0;
    var empty = ul.parentNode.querySelector('.empty.dayempty'); if(empty) empty.hidden = n > 0;
    var panel = ul.parentNode.getAttribute('id') || '';
    var cnt = document.querySelector('.tabs .n[data-n="' + panel.replace('cal-', '') + '"]');
    if(cnt) cnt.textContent = n;
  }
}
"""


_TQ_JS = r"""
var TQ = {t: null, src: '', data: null};
var TQ_MONTHS = ['January','February','March','April','May','June','July','August','September','October','November','December'];
function tqParts(sec){
  var p = {}; new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/Amsterdam', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}).formatToParts(new Date(sec * 1000))
    .forEach(function(x){ p[x.type] = x.value; });
  return {day: p.year + '-' + p.month + '-' + p.day, hm: p.hour + ':' + p.minute, d: +p.day, m: +p.month};
}
function tqDay(sec){
  var a = tqParts(sec), now = Date.now() / 1000;
  if(a.day === tqParts(now).day) return 'Today';
  if(a.day === tqParts(now - 86400).day) return 'Yesterday';
  return a.d + ' ' + TQ_MONTHS[a.m - 1];
}
function tqEl(tag, cls, text){ var e = document.createElement(tag); if(cls) e.className = cls;
  if(text != null) e.textContent = text; return e; }
function tqState(kind, text){
  var s = document.getElementById('tq-state'); s.hidden = !kind; s.className = 'state' + (kind === 'err' ? ' err' : '');
  s.textContent = '';
  if(kind === 'wait'){ var sp = tqEl('span', 'spin'); sp.setAttribute('aria-hidden', 'true'); s.appendChild(sp); }
  if(text) s.appendChild(document.createTextNode(text));
  document.getElementById('tq-out').hidden = false;
}
function tqWhy(err){
  if(/historical data farm is down/.test(err)) return "IBKR's historical news server is down, so no headline came back.";
  if(/does not know/.test(err)) return 'IBKR does not know this symbol.';
  if(/gateway|session|connect/i.test(err)) return 'Could not connect to the IBKR Gateway.';
  return 'IBKR answered: ' + err;
}
function tqPick(t){
  TQ.t = t; TQ.src = ''; TQ.data = null;
  document.getElementById('tq-go').disabled = !t;
  if(t) tqLoad(null);
}
function tqLoad(after){
  var t = TQ.t;
  fetch('/api/news/ticker/' + encodeURIComponent(t), {cache: 'no-store'}).then(function(r){ return r.json(); })
    .then(function(d){ if(d && d.ok && d.ticker === TQ.t){ TQ.data = d; tqDraw(after); } })
    .catch(function(){ if(TQ.t === t) tqState('err', 'Could not read the stored headlines.'); });
}
function tqAsk(retry){
  var t = TQ.t; if(!t) return;
  document.getElementById('tq-go').disabled = true;
  tqState('wait', 'Asking IBKR for ' + t + ', this takes a few seconds.');
  fetch('/run/news_ticker', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-RC-Panel': 'news'},
    body: JSON.stringify({ticker: t})})
    .then(function(r){ return r.json().then(function(d){ return {s: r.status, d: d || {}}; }); })
    .then(function(x){
      if(!x.d.job_id){ document.getElementById('tq-go').disabled = false;
        tqState('err', x.d.error || 'The request did not start.'); return; }
      // 409: another name's ask is running; follow it, then ask for this one once.
      tqWait(x.d.job_id, 0, function(){ if(x.s === 409 && !retry) tqAsk(true); else if(TQ.t === t) tqLoad('asked'); });
    })
    .catch(function(){ document.getElementById('tq-go').disabled = false; tqState('err', 'Could not reach the dashboard.'); });
}
function tqWait(id, n, then){
  fetch('/api/job/' + encodeURIComponent(id), {cache: 'no-store'}).then(function(r){ return r.json(); })
    .then(function(d){
      var s = d && d.job && d.job.status;
      if(s === 'done' || s === 'error' || s === 'cancelled' || n > 120){
        document.getElementById('tq-go').disabled = !TQ.t; then(); return; }
      setTimeout(function(){ tqWait(id, n + 1, then); }, 1000);
    }).catch(function(){ setTimeout(function(){ tqWait(id, n + 1, then); }, 2000); });
}
function tqDraw(after){
  var d = TQ.data, t = d.ticker, rows = d.rows || [], ask = d.ask;
  document.getElementById('tq-out').hidden = false;
  document.getElementById('tq-sym').textContent = t;
  document.getElementById('tq-watch').innerHTML = rcWatchButtons(t);
  var meta = 'last 7 days · ' + rows.length + ' headlines · ' +
    (ask ? 'asked at ' + tqParts(ask.at).hm : 'not asked yet');
  document.getElementById('tq-meta').textContent = meta;
  var counts = {}; rows.forEach(function(r){ counts[r.source] = (counts[r.source] || 0) + 1; });
  var chips = document.getElementById('tq-chips'); chips.textContent = '';
  [['', 'All ' + rows.length]].concat(Object.keys(counts).sort().map(function(k){ return [k, k + ' ' + counts[k]]; }))
    .forEach(function(c){
      var b = tqEl('button', 'chip', c[1]); b.type = 'button';
      b.setAttribute('aria-pressed', TQ.src === c[0] ? 'true' : 'false');
      b.onclick = function(){ TQ.src = c[0]; tqDraw(null); }; chips.appendChild(b);
    });
  if(ask && ask.error) tqState('err', tqWhy(ask.error) + (rows.length ? ' The last stored headlines are below.' : ''));
  else if(!rows.length) tqState('', ask ? 'No Dow Jones or Briefing headline for ' + t + ' in the last 7 days.'
                                        : "Not asked yet: press 'Get headlines'.");
  else tqState(null);
  if(!(ask && ask.error) && !rows.length) document.getElementById('tq-state').hidden = false;
  var ul = document.getElementById('tq-rows'); ul.textContent = '';
  var last = null;
  rows.filter(function(r){ return !TQ.src || r.source === TQ.src; }).forEach(function(r){
    var day = tqDay(r.published_at);
    if(day !== last){ ul.appendChild(tqEl('li', 'tday', day)); last = day; }
    var li = tqEl('li', 'hd'), m = tqEl('div', 'muted meta', tqParts(r.published_at).hm + ' · ' + (r.source || ''));
    var others = []; try { others = JSON.parse(r.tickers || '[]'); } catch(e) {}
    others.filter(function(x){ return x !== t; }).forEach(function(x){ m.appendChild(tqEl('span', 'tk', x)); });
    var h = tqEl('div', 'htext');
    if(/^https?:\/\//.test(r.url || '')){ var a = tqEl('a', null, r.headline); a.href = r.url; a.target = '_blank';
      a.rel = 'noopener noreferrer'; h.appendChild(a); } else { h.textContent = r.headline; }
    li.appendChild(m); li.appendChild(h); ul.appendChild(li);
  });
}
(function(){
  var input = document.getElementById('tq');
  if(input && window.RCCombobox) RCCombobox.mount({input: input, list: '#tq-list', rows: TQ_PICK,
    allowFree: !TQ_PICK.length, clear: true, onPick: function(r){ tqPick(r.ticker); }});
})();
"""


HELP = help_html(
    "<p>The US economic calendar (today and this week, times in Amsterdam), the Dow Jones headlines of the watch "
    "list and the largest US companies (<b>Stocks</b>), IBKR's market-wide news tape (<b>Market</b>) and the posts "
    "in Grok's hourly X summary mails and in RC's own X account feed (<b>X</b>; every post's X id is checked "
    "against its own time, the \"other\" kind and repeats of the same contract are dropped). An option post's "
    "contract is looked up in Unusual Whales (badge: \u2713 UW confirmed, \u2717 not in UW, \u25f7 waiting; a "
    "non-option post carries \u2713 X id) and the posts are grouped by stock, with the session's 5-minute price "
    "and the tweet moments drawn above each group: from 4 hours before the tweet to 15 minutes after it, that "
    "contract's trades over $25k (size, contract, premium, ask/bid side) and the next day's open-interest change. "
    "The actual value is not shown: forecast and previous value.</p>"
    "<p><b>The week strip</b> stands above the calendar: one button a day, Monday to Sunday, with that day's "
    "number of economic releases and of FDA catalysts, and today marked. Pressing a day shows that day under "
    "both the <b>Economic</b> and the <b>FDA</b> tab; the line above each list is the next one still to come.</p>"
    "<p><b>FDA</b> is Unusual Whales' FDA calendar: a PDUFA date, an advisory committee meeting or a decision, "
    "with what the drug is for and where its application stands. Unusual Whales does not give every catalyst a "
    "day — some are served as a quarter, a half year, \"mid\" or \"late\" in a year. Those carry a <b>no day "
    "yet</b> chip and stand together under <b>Later, no day yet</b>, never snapped onto a day they do not have. "
    "An FDA catalyst has a date and no time of day, so it shows no clock.</p>"
    "<p>Market headlines land on the page within seconds of arriving; stock headlines come every 5 minutes. "
    "Under each lane's heading stands that lane's <b>own</b> last data time: the clock at the top of the page is "
    "the newest write to any lane of the board, so on its own it cannot show a lane that has died.</p>"
    "<p><b>News for one stock</b>: pick a stock from My Universe and press <b>Get headlines</b> to ask IBKR for "
    "that name's Dow Jones and Briefing headlines of the last 7 days (at most 300) and store them; if IBKR does "
    "not answer, the last stored headlines are shown.</p>"
    "<p><b>Fetch</b> writes the stored calendar into <code>boards/news.duckdb</code> incrementally (new and "
    "changed events; an event that drops off the list is not deleted, it is retired) and asks the IBKR Gateway "
    "for the latest headlines. <b>Refresh</b> only redraws the page from stored data and downloads nothing.</p>")


def render_html(now: float | None = None, provider_health: dict | None = None) -> str:
    """The page; ``provider_health`` (a Fetch whose gateway did not answer) adds the "Data incomplete" banner."""
    now = time.time() if now is None else now
    events, undated, hl, heads, stamp = _load(now)
    since = max((float(h["run_at"]) for h in heads if h.get("run_at") is not None), default=now)
    today = local_day(now)
    hl_key = (hl["event_ts"], hl["event"], hl["type"]) if hl else None
    cal_html = _calendar(events, undated, now, hl_key)
    todays = [e for e in events if local_day(e["event_ts"]) == today]
    n_today = sum(1 for e in todays if str(e.get("type") or "") != FDA_TYPE)
    n_fda = len(todays) - n_today
    counted = (f"{n_today} release{'' if n_today == 1 else 's'} and {n_fda} FDA "
               f"catalyst{'' if n_fda == 1 else 's'} today")
    updated = f"Data updated at {hm(stamp)}" if stamp else "No data built yet"
    lanes = _headlines(heads, headlines.lane_freshness(), now)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>News</title><script>{THEME_JS}</script><style>{THEME_CSS}{_CSS}</style>{FILTERS_CSS}</head>
<body><div class="wrap">
<header class="top"><div><div class="eyebrow">US · Calendar</div><h1>{long_date(today)}</h1>
<div class="muted">{WEEKDAYS[today.weekday()]} · {counted}</div></div>
<div class="muted">{updated}</div></header>
{provider_health_html(provider_health)}
<nav class="ptabs" role="tablist" aria-label="Sections">
<button type="button" role="tab" aria-selected="true" aria-controls="pg-cal" onclick="pageTab(this)">Calendar</button>
<button type="button" role="tab" aria-selected="false" aria-controls="pg-heads" onclick="pageTab(this)">Headlines
<span class="n">{lanes["market_n"] + lanes["stocks_n"]}</span></button>
<button type="button" role="tab" aria-selected="false" aria-controls="pg-x" onclick="pageTab(this)">X
<span class="n">{lanes["x_n"]}</span></button>
</nav>
<div id="pg-cal" role="tabpanel"><div class="grid">
<section class="card">{cal_html}</section>
<div class="side">{_highlight(hl)}</div>
</div></div>
<div id="pg-heads" role="tabpanel" hidden>{_ticker_box()}<div class="cols">{lanes["market"]}{lanes["stocks"]}</div></div>
<div id="pg-x" role="tabpanel" hidden>{lanes["x"]}</div>
<p class="foot">Source: economic and FDA calendar Unusual Whales, headlines Dow Jones (IBKR), X posts Grok summaries and RC's own X reader · Times Europe/Amsterdam · Importance: ●●● high ●●○ medium ●○○ low</p>
{HELP}
</div>{watchlist_html("news")}<script>{FILTERS_JS}</script>
<script>var NEWS_SINCE = {since!r}, HEAD_LIMIT = {HEADLINE_LIMIT}, TQ_PICK = {script_json(_picker())};{_JS}{_TQ_JS}</script>
</body></html>"""


def render(now: float | None = None, provider_health: dict | None = None) -> Path:
    """Write the board file ``.cache/news_latest.html`` and return its path."""
    return write_artifact(Path(OUTPUT_DIR) / FILENAME, render_html(now, provider_health))
