"""The News board page (plan §6, mock ``News.dc.html``): today's US economic calendar, this week, the day's highlight
and the market headlines, in Turkish, times in Europe/Amsterdam.

Store-only: it reads ``boards/news.duckdb`` and never fetches. Event names stay as the provider serves them; the board's
own words are Turkish. Phone first: one column under 900 px, 44 px touch targets, light and dark from the shell's theme.
"""
from __future__ import annotations

import json
import time
from datetime import datetime, timedelta
from pathlib import Path

from RevenueChaser.core import econ_importance, rawstore
from RevenueChaser.core.config import OUTPUT_DIR
from RevenueChaser.core.html_safe import esc
from RevenueChaser.core.html_safe import script_json
from RevenueChaser.core.reporting_common import (FILTERS_CSS, FILTERS_JS, THEME_CSS, THEME_JS, combobox_html, help_html,
                                                 provider_health_html, watchlist_html, write_artifact)
from RevenueChaser.module_news.calendar import AMS, EVENTS, HIGHLIGHT, local_day, tr_value
from RevenueChaser.module_news import headlines, x_check
from RevenueChaser.module_news.x_feed import PROVIDER as X_PROVIDER

FILENAME = "news_latest.html"
HEADLINES = "news_headlines"
WEEK_DAYS = 7
HEADLINE_HOURS = 24
HEADLINE_LIMIT = 30

MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım",
           "Aralık")
WEEKDAYS = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")
_KIND = {"report": "Veri", "fed-speaker": "Fed", "fomc": "FOMC"}
_LEVEL = {3: "yüksek", 2: "orta", 1: "düşük"}


def hm(ts: float) -> str:
    return datetime.fromtimestamp(float(ts), AMS).strftime("%H:%M")


def long_date(d) -> str:
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def day_label(d) -> str:
    return f"{WEEKDAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]}"


def _load(now: float) -> tuple[list[dict], dict | None, list[dict], float | None]:
    today = local_day(now)
    start = datetime(today.year, today.month, today.day, tzinfo=AMS)
    end = start + timedelta(days=WEEK_DAYS)
    events = rawstore.query(
        f"SELECT * FROM {EVENTS} WHERE event_ts >= ? AND event_ts < ? AND retired_at IS NULL ORDER BY event_ts, event",
        [start.timestamp(), end.timestamp()], db="news")
    hl = rawstore.query(f"SELECT * FROM {HIGHLIGHT} WHERE session_date = ?", [today.isoformat()], db="news")
    x = f"coalesce(provider, '') = '{X_PROVIDER}'"
    lanes = (f"NOT {x} AND coalesce(tickers, '[]') = '[]'", f"NOT {x} AND coalesce(tickers, '[]') <> '[]'",
             f"{x} AND coalesce(kind, '') <> 'other'")        # the X lane leaves out what Grok filed as "other"
    heads = [r for cond in lanes for r in rawstore.query(      # each lane its own newest LIMIT
        f"SELECT * FROM {HEADLINES} WHERE published_at >= ? AND {cond} "
        f"ORDER BY published_at DESC LIMIT {HEADLINE_LIMIT}", [now - HEADLINE_HOURS * 3600], db="news")]
    # The page's "updated" time is its newest write: the calendar's, or the 5-minute headline pass's.
    got = rawstore.query(f"SELECT max(run_at) AS t FROM {EVENTS}", db="news")
    stamps = [float(t) for t in [got[0]["t"] if got else None] + [h.get("run_at") for h in heads] if t is not None]
    return events, (hl[0] if hl else None), heads, (max(stamps) if stamps else None)


def dots_html(level) -> str:
    n = int(level or 1)
    return (f'<span class="dots" title="{_LEVEL.get(n, "düşük")} önem" aria-label="{_LEVEL.get(n, "düşük")} önem">'
            f'{econ_importance.dots(n)}</span>')


def vals_html(e: dict) -> str:
    fc, prev = tr_value(e.get("forecast")), tr_value(e.get("prev"))
    return (f'<div class="vals"><span>Beklenti <b>{esc(fc or "–")}</b></span>'
            f'<span>Önceki <b>{esc(prev or "–")}</b></span></div>')


def _row(e: dict, now: float, hl_key) -> str:
    key = (e["event_ts"], e["event"], e["type"])
    cls = "ev hl" if key == hl_key else "ev"
    past = ' data-past="1"' if float(e["event_ts"]) < now else ""
    kind = _KIND.get(str(e.get("type") or "").lower(), "Veri")
    return (f'<li class="{cls}"{past}><span class="t">{hm(e["event_ts"])}</span>'
            f'<div class="nm"><span class="kind">{kind}</span> {dots_html(e.get("importance"))}'
            f'<div class="name">{esc(e["event"])}</div></div>{vals_html(e)}</li>')


def _calendar(events: list[dict], now: float, hl_key) -> tuple[str, str]:
    today = local_day(now)
    todays = [e for e in events if local_day(e["event_ts"]) == today]
    today_html = ("<ul class=\"list\">" + "".join(_row(e, now, hl_key) for e in todays) + "</ul>") if todays else (
        '<p class="empty">Bugün takvimde veri yok.</p>')
    if not events:
        return today_html, '<p class="empty">Bu hafta takvimde veri yok. Yenile, saklı takvimden yeniden kurar.</p>'
    by_day: dict = {}
    for e in events:
        by_day.setdefault(local_day(e["event_ts"]), []).append(e)
    week = "".join(f'<h3 class="day">{day_label(d)}</h3><ul class="list">'
                   + "".join(_row(e, now, hl_key) for e in rows) + "</ul>" for d, rows in by_day.items())
    return today_html, week


def _highlight(hl: dict | None) -> str:
    if not hl:
        return ('<section class="card feat"><h2 class="lbl">Öne çıkan veri</h2>'
                '<p class="empty">Bugün öne çıkan bir veri yok.</p></section>')
    return (f'<section class="card feat"><h2 class="lbl">Öne çıkan veri</h2>'
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
    """``x`` for a tweet from the Grok X mails, ``market`` for a broad-tape headline (no ticker, #673), else
    ``stocks``."""
    if row.get("provider") == X_PROVIDER:
        return "x"
    return "stocks" if _tickers(row.get("tickers")) else "market"


_LANES = {"market": ("Piyasa", "Piyasa akışından henüz başlık yok."),
          "stocks": ("Hisseler", "Henüz başlık yok."),
          "x": ("X", "X özetlerinden henüz kayıt yok.")}
#: The tweet kinds of the X lane, in the board's Turkish (the JS keeps the same map).
X_KINDS = {"news": "haber", "level": "seviye", "option": "opsiyon", "macro": "makro", "position": "pozisyon",
           "other": "diğer"}


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
        opt += _fold("İşlem grafiği", x_check.chart_svg(state, float(r["published_at"])))
    badge = _badge_html(state) if x else ""
    return (f'<li class="hd" data-hid="{esc(r["headline_id"])}" data-at="{float(r["published_at"])}">'
            f'<div class="muted meta">{hm(r["published_at"])}{src} {kind}{tk}{badge}</div>'
            f'<div class="htext">{text}</div>{opt}</li>')


def x_group(r: dict) -> str:
    """The X lane's group of a row: its contract's ticker, else its first ticker, else "" (Genel)."""
    state = _check(r)
    return state.get("ticker") or state.get("px_tk") or (_tickers(r.get("tickers")) or [""])[0].upper()


def _group_li(key: str, rows: list[dict]) -> str:
    """One ticker: its name, how many posts of which kinds, how many UW confirmed, the session's price line with every
    tweet on it, then the posts."""
    kinds = ", ".join(dict.fromkeys(X_KINDS.get(r.get("kind") or "", r.get("kind") or "") for r in rows if r.get("kind")))
    seen = sum(1 for r in rows if _check(r).get("status") == "seen")
    opts = sum(1 for r in rows if r.get("kind") == "option")
    conf = (f' · <span class="vb {"ok" if seen else "wait"}"><b aria-hidden="true">{"✓" if seen else "–"}</b>'
            f'{seen}/{opts} UW teyitli</span>') if opts else ""
    with_px = [r for r in rows if _check(r).get("px")]
    chart = ""
    if with_px:
        newest = with_px[0]
        session = x_check.session_day(float(newest["published_at"]))
        marks = [(float(r["published_at"]), f'{hm(r["published_at"])} {r.get("source") or ""}'.strip())
                 for r in rows if x_check.session_day(float(r["published_at"])) == session]
        chart = _fold("Fiyat grafiği", x_check.price_svg(_check(newest)["px"], marks))
    name = f'<span class="sym">{esc(key)}</span>' if key else '<span class="sym gen">Genel</span>'
    return (f'<li class="xg" data-grp="{esc(key)}" data-at="{float(rows[0]["published_at"])}">'
            f'<div class="xgh">{name}<span class="muted">{len(rows)} kayıt · {esc(kinds)}{conf}</span></div>'
            f'{chart}<ul class="list">{"".join(_head_li(r) for r in rows)}</ul></li>')


def _x_groups(rows: list[dict]) -> str:
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(x_group(r), []).append(r)
    order = sorted(groups.items(), key=lambda kv: (kv[0] == "", -float(kv[1][0]["published_at"])))
    return "".join(_group_li(k, v) for k, v in order)


def _headlines(rows: list[dict]) -> dict[str, str]:
    """One card a lane: Piyasa (the broad tape), Hisseler (per ticker) and X (the Grok X mails, one group a ticker),
    each with its row count; the page's poll adds to their lists."""
    out = {}
    for key, (title, empty) in _LANES.items():
        mine = [r for r in rows if lane(r) == key]
        mine = (_curated(mine) if key == "x" else mine)[:HEADLINE_LIMIT]
        body = _x_groups(mine) if key == "x" else "".join(_head_li(r) for r in mine)
        out[key] = (f'<section class="card"><h2 class="lbl">{title} · son {HEADLINE_HOURS} saat</h2>'
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
    return (f'<section class="card tbox" aria-labelledby="tq-l"><h2 class="lbl" id="tq-l">Bir hisse için haber</h2>'
            f'<div class="tq">{combobox_html("tq", "tq-l", "Ticker ya da şirket adı, ör. NVDA")}'
            f'<button type="button" class="go" id="tq-go" disabled onclick="tqAsk()">Haberleri getir</button></div>'
            f'<div id="tq-out" hidden><div class="th"><span id="tq-watch"></span><span class="sym" id="tq-sym"></span>'
            f'<span class="muted" id="tq-meta"></span></div>'
            f'<div class="chips" id="tq-chips" role="group" aria-label="Kaynak"></div>'
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
[hidden]{display:none!important}
@media (max-width:900px){.grid,.cols{grid-template-columns:minmax(0,1fr)}.feat{order:-1}}
@media (max-width:560px){.ev{grid-template-columns:60px 1fr}.vals{grid-column:2}.wrap{padding:12px}}
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
  if(r.option){ var o = document.createElement('div'); o.className = r.option.indexOf('UW teyidi:') === 0 ? 'xo ok' : 'xo';
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
    n.className = r.group ? 'sym' : 'sym gen'; n.textContent = r.group || 'Genel'; h.appendChild(n); g.appendChild(h);
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
"""


_TQ_JS = r"""
var TQ = {t: null, src: '', data: null};
var TQ_MONTHS = ['Ocak','Şubat','Mart','Nisan','Mayıs','Haziran','Temmuz','Ağustos','Eylül','Ekim','Kasım','Aralık'];
function tqParts(sec){
  var p = {}; new Intl.DateTimeFormat('en-GB', {timeZone: 'Europe/Amsterdam', year: 'numeric', month: '2-digit',
    day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23'}).formatToParts(new Date(sec * 1000))
    .forEach(function(x){ p[x.type] = x.value; });
  return {day: p.year + '-' + p.month + '-' + p.day, hm: p.hour + ':' + p.minute, d: +p.day, m: +p.month};
}
function tqDay(sec){
  var a = tqParts(sec), now = Date.now() / 1000;
  if(a.day === tqParts(now).day) return 'Bugün';
  if(a.day === tqParts(now - 86400).day) return 'Dün';
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
  if(/historical data farm is down/.test(err)) return "IBKR'ın geçmiş haber sunucusu şu an kapalı, başlık gelmedi.";
  if(/does not know/.test(err)) return 'IBKR bu sembolü tanımıyor.';
  if(/gateway|session|connect/i.test(err)) return "IBKR Gateway'e bağlanılamadı.";
  return 'IBKR yanıtı: ' + err;
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
    .catch(function(){ if(TQ.t === t) tqState('err', 'Saklı başlıklar okunamadı.'); });
}
function tqAsk(retry){
  var t = TQ.t; if(!t) return;
  document.getElementById('tq-go').disabled = true;
  tqState('wait', "IBKR'dan " + t + ' soruluyor, birkaç saniye sürer.');
  fetch('/run/news_ticker', {method: 'POST', headers: {'Content-Type': 'application/json', 'X-RC-Panel': 'news'},
    body: JSON.stringify({ticker: t})})
    .then(function(r){ return r.json().then(function(d){ return {s: r.status, d: d || {}}; }); })
    .then(function(x){
      if(!x.d.job_id){ document.getElementById('tq-go').disabled = false;
        tqState('err', x.d.error || 'İstek başlamadı.'); return; }
      // 409: another name's ask is running; follow it, then ask for this one once.
      tqWait(x.d.job_id, 0, function(){ if(x.s === 409 && !retry) tqAsk(true); else if(TQ.t === t) tqLoad('asked'); });
    })
    .catch(function(){ document.getElementById('tq-go').disabled = false; tqState('err', 'Panoya ulaşılamadı.'); });
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
  var meta = 'son 7 gün · ' + rows.length + ' başlık · ' +
    (ask ? tqParts(ask.at).hm + "'de soruldu" : 'henüz sorulmadı');
  document.getElementById('tq-meta').textContent = meta;
  var counts = {}; rows.forEach(function(r){ counts[r.source] = (counts[r.source] || 0) + 1; });
  var chips = document.getElementById('tq-chips'); chips.textContent = '';
  [['', 'Hepsi ' + rows.length]].concat(Object.keys(counts).sort().map(function(k){ return [k, k + ' ' + counts[k]]; }))
    .forEach(function(c){
      var b = tqEl('button', 'chip', c[1]); b.type = 'button';
      b.setAttribute('aria-pressed', TQ.src === c[0] ? 'true' : 'false');
      b.onclick = function(){ TQ.src = c[0]; tqDraw(null); }; chips.appendChild(b);
    });
  if(ask && ask.error) tqState('err', tqWhy(ask.error) + (rows.length ? ' Saklı son başlıklar aşağıda.' : ''));
  else if(!rows.length) tqState('', ask ? t + ' için son 7 günde Dow Jones ya da Briefing başlığı yok.'
                                        : "Henüz sorulmadı: 'Haberleri getir'e basın.");
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
    "<p>ABD ekonomik takvimi (bugün ve bu hafta, saatler Amsterdam) ve izleme listesindeki ve en büyük ABD "
    "şirketlerinin Dow Jones başlıkları (<b>Hisseler</b>), IBKR'nin piyasa geneli haber akışı (<b>Piyasa</b>) ve "
    "Grok'un saatlik X özet maillerindeki paylaşımlar (<b>X</b>; her kaydın X kimliği kendi zamanıyla doğrulanır, "
    "\"diğer\" türü ve aynı kontratın tekrarları düşer). Bir opsiyon paylaşımının kontratı Unusual Whales'ta "
    "aranır (rozet: ✓ UW teyitli, ✗ UW'de yok, ◷ bekliyor; opsiyon dışı kayıtlarda ✓ X kimliği) ve kayıtlar hisseye göre gruplanır, her grubun üstünde seansın 5 dakikalık fiyatı ve tweet anları çizilir: tweet saatinin 4 saat öncesinden 15 dakika sonrasına kadar o kontratın $25 bin üstü işlemleri (adet, "
    "kontrat, prim, ask/bid tarafı) ve ertesi gün açık pozisyon (OI) değişimi gösterilir. "
    "Gerçekleşen değer gösterilmez: beklenti ve önceki değer.</p>"
    "<p>Piyasa başlıkları geldiği anda, birkaç saniye içinde sayfaya düşer; hisse başlıkları 5 dakikada bir gelir.</p>"
    "<p><b>Bir hisse için haber</b>: My Universe'den bir hisse seçip <b>Haberleri getir</b>'e basınca IBKR'dan o hissenin "
    "son 7 günlük Dow Jones ve Briefing başlıkları sorulur (en çok 300) ve saklanır; IBKR yanıt vermezse saklı son "
    "başlıklar gösterilir.</p>"
    "<p><b>Fetch</b> saklı takvimi <code>boards/news.duckdb</code> içine artımlı yazar (yeni ve değişen "
    "olaylar; listeden düşen olay silinmez, emekliye ayrılır) ve IBKR Gateway'den son başlıkları sorar. "
    "<b>Refresh</b> yalnızca saklı veriden sayfayı yeniden çizer, hiçbir şey indirmez.</p>")


def render_html(now: float | None = None, provider_health: dict | None = None) -> str:
    """The page; ``provider_health`` (a Fetch whose gateway did not answer) adds the "Data incomplete" banner."""
    now = time.time() if now is None else now
    events, hl, heads, stamp = _load(now)
    since = max((float(h["run_at"]) for h in heads if h.get("run_at") is not None), default=now)
    today = local_day(now)
    hl_key = (hl["event_ts"], hl["event"], hl["type"]) if hl else None
    today_html, week_html = _calendar(events, now, hl_key)
    n_today = sum(1 for e in events if local_day(e["event_ts"]) == today)
    updated = f"Veri {hm(stamp)}'de güncellendi" if stamp else "Veri henüz kurulmadı"
    lanes = _headlines(heads)
    return f"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Haberler</title><script>{THEME_JS}</script><style>{THEME_CSS}{_CSS}</style>{FILTERS_CSS}</head>
<body><div class="wrap">
<header class="top"><div><div class="eyebrow">ABD · Ekonomik takvim</div><h1>{long_date(today)}</h1>
<div class="muted">{WEEKDAYS[today.weekday()]} · bugün {n_today} veri</div></div>
<div class="muted">{updated}</div></header>
{provider_health_html(provider_health)}
<nav class="ptabs" role="tablist" aria-label="Bölümler">
<button type="button" role="tab" aria-selected="true" aria-controls="pg-cal" onclick="pageTab(this)">Takvim</button>
<button type="button" role="tab" aria-selected="false" aria-controls="pg-heads" onclick="pageTab(this)">Başlıklar
<span class="n">{lanes["market_n"] + lanes["stocks_n"]}</span></button>
<button type="button" role="tab" aria-selected="false" aria-controls="pg-x" onclick="pageTab(this)">X
<span class="n">{lanes["x_n"]}</span></button>
</nav>
<div id="pg-cal" role="tabpanel"><div class="grid">
<section class="card"><div class="tabs" role="tablist">
<button type="button" role="tab" aria-selected="true" aria-controls="news-today" onclick="newsTab(this)">Bugün</button>
<button type="button" role="tab" aria-selected="false" aria-controls="news-week" onclick="newsTab(this)">Bu hafta</button>
</div><div id="news-today" role="tabpanel">{today_html}</div>
<div id="news-week" role="tabpanel" hidden>{week_html}</div></section>
<div class="side">{_highlight(hl)}</div>
</div></div>
<div id="pg-heads" role="tabpanel" hidden>{_ticker_box()}<div class="cols">{lanes["market"]}{lanes["stocks"]}</div></div>
<div id="pg-x" role="tabpanel" hidden>{lanes["x"]}</div>
<p class="foot">Kaynak: takvim Unusual Whales, başlıklar Dow Jones (IBKR), X kayıtları Grok özetleri · Saatler Europe/Amsterdam · Önem: ●●● yüksek ●●○ orta ●○○ düşük</p>
{HELP}
</div>{watchlist_html("news")}<script>{FILTERS_JS}</script>
<script>var NEWS_SINCE = {since!r}, HEAD_LIMIT = {HEADLINE_LIMIT}, TQ_PICK = {script_json(_picker())};{_JS}{_TQ_JS}</script>
</body></html>"""


def render(now: float | None = None, provider_health: dict | None = None) -> Path:
    """Write the board file ``.cache/news_latest.html`` and return its path."""
    return write_artifact(Path(OUTPUT_DIR) / FILENAME, render_html(now, provider_health))
