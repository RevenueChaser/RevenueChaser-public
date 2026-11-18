"""The stock heatmap of the Sector Rotation board (#782): a treemap whose tile area is market cap and whose colour is
the price change over a period.

avo's decisions on the mock, 18 Nov 2026 (in #782): the universe is the S&P 500 by default, and each of his own
watch lists (``watchlists.duckdb``, the lists a board treats as his picks, ``rcdata.read.PICKED``) can be chosen
instead. The periods are 1D, 1W, 1M, 3M, 6M and 1Y. Both colour scales (fixed per period, or set by the spread of
the names shown) are drawn in the page, which also lays out the treemap.

Read-only and local. Names, sectors, industries and caps come from the shared universe
(``core.universe.load_cached_universe``, the same rows every board reads); the closes come from the prices
store (``rcdata.read.ticker_bars``, splits applied, dividends not: a heatmap shows the price move). Any read that
fails gives no payload, and the board then shows no panel; it never stops the board from rendering.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

logger = logging.getLogger(__name__)

#: Label and trading sessions back, by period. A 1Y change needs 252 sessions before the newest one.
PERIODS: tuple[tuple[str, int], ...] = (("1D", 1), ("1W", 5), ("1M", 21), ("3M", 63), ("6M", 126), ("1Y", 252))
#: Calendar days of bars read: 252 sessions plus holidays, with room to spare.
READ_DAYS = 380
#: Tickers per bar read, so one read never holds the bars of every name at once.
CHUNK = 400
#: The fixed colour stop of each period, in percent (the "Fixed" scale of the page; "By spread" computes its own).
FIXED_STOPS = (3, 6, 12, 20, 30, 40)
#: Kept for tiles: the operating companies (common, ADR, REIT, ...), not funds or SPACs.
STOCK_TYPES = frozenset({"common", "adr", "reit", "bank_nonsec", "bdc", "mlp", "royalty_trust"})


def changes(closes: list[float]) -> list[float | None]:
    """Percent change of the last close against the close ``n`` sessions before it, for each period; ``None`` where
    the series is too short or the old close is not positive. ``closes`` is oldest first."""
    out: list[float | None] = []
    last = closes[-1] if closes else None
    for _, n in PERIODS:
        if last is None or len(closes) <= n or not closes[-1 - n] or closes[-1 - n] <= 0:
            out.append(None)
        else:
            out.append(round((last / closes[-1 - n] - 1) * 100, 2))
    return out


def _closes(tickers: list[str], start: date) -> tuple[dict[str, list[float]], dict[str, date]]:
    """``ticker -> closes`` (oldest first) and ``ticker -> newest session``, read in chunks."""
    from RevenueChaser.rcdata import read
    closes: dict[str, list[float]] = {}
    newest: dict[str, date] = {}
    for i in range(0, len(tickers), CHUNK):
        df = read.ticker_bars(tickers[i:i + CHUNK], start=start, basis="split")
        if df is None or df.empty:
            continue
        df = df.sort_values(["ticker", "session_date"])
        for t, g in df.groupby("ticker", sort=False):
            closes[t] = [float(c) for c in g["close"]]
            newest[t] = g["session_date"].iloc[-1].date()
    return closes, newest


def _universes(stocks: set[str]) -> list[tuple[str, str, list[str]]]:
    """``(id, label, tickers)``: the S&P 500, then each of avo's watch lists with at least one stock on it."""
    from RevenueChaser.rcdata import read
    out = [("sp500", "S&P 500", sorted({r["ticker"] for r in read.membership("sp500")} & stocks))]
    try:
        from RevenueChaser.module_watchlists import store
        for lst in store.lists():
            if (lst.get("feeds") or "") not in read.PICKED:
                continue
            names = sorted({(r.get("ticker") or "").upper() for r in store.items(lst["list_id"])} & stocks)
            if names:
                out.append((f"wl:{lst['list_id']}", lst.get("name") or lst["list_id"], names))
    except Exception as e:                                # noqa: BLE001 - no lists: the S&P 500 alone
        logger.warning("heatmap: watch lists not read: %s", e)
    return out


def payload(today: date | None = None) -> dict | None:
    """What the page draws: ``{"as_of", "periods", "stops", "stocks", "universes"}``, or ``None`` when there is
    nothing to draw (no universe, no bars) or a read failed.

    ``stocks`` rows are ``[ticker, name, sector, industry, cap_usd_bn, ch_1d, ..., ch_1y]``; ``universes`` are
    ``{"id", "name", "idx"}`` with ``idx`` the row numbers of its names. A name whose newest bar is older than the
    newest session read keeps no change (a halted or delisted name is not shown as flat)."""
    try:
        from RevenueChaser.core import universe
        rows = {r["ticker"]: r for r in universe.load_cached_universe()
                if r.get("security_type") in STOCK_TYPES and (r.get("market_cap") or 0) > 0}
        if not rows:
            return None
        unis = [u for u in _universes(set(rows)) if u[2]]
        wanted = sorted({t for _, _, names in unis for t in names})
        if not wanted:
            return None
        closes, newest = _closes(wanted, (today or date.today()) - timedelta(days=READ_DAYS))
    except Exception as e:                                # noqa: BLE001 - a board renders without its heatmap
        logger.warning("heatmap: not drawn: %s", e)
        return None
    if not newest:
        return None
    as_of = max(newest.values())
    stocks, index = [], {}
    from RevenueChaser.core.gics_map import canonical_sector
    for t in wanted:
        r = rows[t]
        ch = changes(closes[t]) if newest.get(t) == as_of else [None] * len(PERIODS)
        index[t] = len(stocks)
        stocks.append([t, r.get("name") or t, canonical_sector(r.get("sector")), r.get("industry") or "Unclassified",
                       round(float(r["market_cap"]) / 1e9, 3), *ch])
    return {"as_of": as_of.isoformat(), "periods": [p for p, _ in PERIODS], "stops": list(FIXED_STOPS),
            "stocks": stocks,
            "universes": [{"id": uid, "name": name, "idx": [index[t] for t in names]} for uid, name, names in unis]}


# ── The panel: markup, style and script (one block, so the board only places it) ───────────────────────────────────
# The page draws everything from the payload: a squarified treemap (Bruls, Huizing and van Wijk) of the sectors, then
# of each sector's names; a click on a sector opens it alone, grouped by industry; on a phone the map first shows one
# tile per sector and a tap opens it (avo, 18 Nov 2026: "Telefonda harita", "Click to expand"). Colours are the
# shared theme tokens (``--pos``, ``--neg`` mixed into ``--card-2``), so the panel follows the shell's light or dark.
PANEL_CSS = """<style>
.hm{margin:16px 0;padding:16px;border:1px solid var(--border);border-radius:var(--r-md);background:var(--card);
  color:var(--fg);font-family:var(--font-sans);font-size:var(--fs-base)}
.hm h2{margin:0 0 4px;font-size:var(--fs-md);color:var(--bright)}
.hm .hm-sub{margin:0 0 12px;color:var(--muted);font-size:var(--fs-sm)}
.hm-knobs{display:flex;flex-wrap:wrap;gap:8px 16px;align-items:center;margin-bottom:12px}
.hm-knob{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:var(--fs-sm)}
.hm select{min-height:var(--touch);padding:0 12px;border:1px solid var(--input-border);border-radius:var(--r-sm);
  background:var(--input-bg);color:var(--fg);font:inherit}
.hm-seg{display:inline-flex;border:1px solid var(--input-border);border-radius:var(--r-sm);overflow:hidden}
.hm-seg button{min-width:var(--touch);min-height:var(--touch);padding:0 12px;border:0;background:var(--input-bg);
  color:var(--muted);font:600 var(--fs-sm) var(--font-sans);cursor:pointer}
.hm-seg button+button{border-left:1px solid var(--input-border)}
.hm-seg button[aria-pressed="true"]{background:var(--accent-soft);color:var(--accent)}
.hm-crumb{display:flex;align-items:center;gap:8px;min-height:28px;margin-bottom:8px;color:var(--muted);font-size:var(--fs-sm)}
.hm-crumb button{min-height:var(--touch);padding:0 8px;border:0;background:none;color:var(--accent);font:600 var(--fs-sm) var(--font-sans);cursor:pointer}
.hm-crumb b{color:var(--bright)}
.hm-pick{display:flex;align-items:center;gap:12px;flex-wrap:wrap;min-height:52px;margin-bottom:12px;padding:8px 12px;
  border:1px solid var(--border);border-radius:var(--r-md);background:var(--card-2)}
.hm-pick[hidden]{display:none}
.hm-pick .tk{font-weight:700;color:var(--bright);font-size:var(--fs-md)}
.hm-pick .meta{color:var(--muted);font-size:var(--fs-sm)}
.hm-pick .ch{font-weight:700;font-variant-numeric:tabular-nums}
.hm .pos{color:var(--pos)}.hm .neg{color:var(--neg)}
.hm-map{position:relative;width:100%;height:640px;border-radius:var(--r-md);overflow:hidden;background:var(--bg)}
.hm-sec{position:absolute;overflow:hidden}
.hm-sech{position:absolute;left:0;right:0;top:0;height:24px;display:flex;align-items:center;gap:4px;padding:0 6px;border:0;
  background:none;color:var(--fg);font:600 var(--fs-sm)/1 var(--font-sans);cursor:pointer;text-align:left;white-space:nowrap;
  overflow:hidden;text-overflow:ellipsis}
.hm-sech:hover,.hm-sech:focus-visible{color:var(--bright);outline:none;text-decoration:underline}
.hm-sech .avg{font-weight:400;color:var(--muted);font-variant-numeric:tabular-nums}
.hm-tile{position:absolute;display:flex;flex-direction:column;align-items:center;justify-content:center;border:0;padding:2px;
  margin:0;cursor:pointer;color:var(--bright);font-family:var(--font-sans);overflow:hidden;box-shadow:inset 0 0 0 1px var(--bg);
  text-align:center;line-height:1.15}
.hm-tile:focus-visible{outline:2px solid var(--focus);outline-offset:-2px;z-index:2}
.hm-tile[aria-current="true"]{box-shadow:inset 0 0 0 2px var(--bright);z-index:2}
.hm-tile .t{font-weight:700}
.hm-tile .c{font-variant-numeric:tabular-nums;opacity:.92}
.hm-legend{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin-top:12px;font-size:var(--fs-xs);color:var(--muted)}
.hm-ramp{display:flex;border-radius:var(--r-sm);overflow:hidden}
.hm-ramp span{width:44px;height:20px;display:flex;align-items:center;justify-content:center;color:var(--bright);
  font-variant-numeric:tabular-nums}
.hm-tip{position:fixed;z-index:20;pointer-events:none;padding:8px 12px;border:1px solid var(--border);border-radius:var(--r-sm);
  background:var(--card);color:var(--fg);box-shadow:var(--elev-2);font-size:var(--fs-sm);max-width:260px}
.hm-tip[hidden]{display:none}
.hm-list{display:none}
.hm[data-view="list"] .hm-map{display:none}
.hm[data-view="list"] .hm-list{display:block}
.hm-card{margin-bottom:12px;border:1px solid var(--border);border-radius:var(--r-md);background:var(--card-2);overflow:hidden}
.hm-cardh{display:flex;align-items:center;justify-content:space-between;width:100%;min-height:var(--touch);padding:0 12px;border:0;
  border-bottom:1px solid var(--border);background:none;color:var(--bright);font:600 var(--fs-base) var(--font-sans);cursor:pointer}
.hm-row{display:flex;align-items:center;gap:8px;min-height:var(--touch);padding:4px 12px;border-bottom:1px solid var(--border)}
.hm-row:last-child{border-bottom:0}
.hm-row .tk{width:56px;font-weight:700;color:var(--bright)}
.hm-row .nm{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-size:var(--fs-sm)}
.hm-row .sw{flex:none;width:64px;height:22px;border-radius:4px;display:flex;align-items:center;justify-content:center;
  color:var(--bright);font-size:var(--fs-sm);font-weight:600;font-variant-numeric:tabular-nums}
.hm-more{width:100%;min-height:var(--touch);border:0;background:none;color:var(--accent);font:600 var(--fs-sm) var(--font-sans);cursor:pointer}
@media (max-width:600px){.hm{padding:12px}.hm-map{height:auto;aspect-ratio:3/4}}
</style>"""

PANEL_HTML = """<section class="hm" id="hm" data-view="map" aria-labelledby="hm-title">
<h2 id="hm-title">Stock heatmap</h2>
<p class="hm-sub">Area is market cap, colour is the price change over the period (closes of <span id="hm-asof"></span>). Click a sector to open it alone, a tile to pick the stock.</p>
<div class="hm-knobs">
  <label class="hm-knob">Universe <select id="hm-uni" aria-label="Universe"></select></label>
  <span class="hm-knob">Period <span class="hm-seg" id="hm-per" role="group" aria-label="Period"></span></span>
  <span class="hm-knob">Colour <span class="hm-seg" id="hm-scl" role="group" aria-label="Colour scale"><button type="button" aria-pressed="true" data-s="fixed">Fixed</button><button type="button" aria-pressed="false" data-s="spread">By spread</button></span></span>
  <span class="hm-knob">View <span class="hm-seg" id="hm-view" role="group" aria-label="View"><button type="button" aria-pressed="true" data-v="map">Map</button><button type="button" aria-pressed="false" data-v="list">List</button></span></span>
</div>
<div class="hm-crumb" id="hm-crumb"></div>
<div class="hm-pick" id="hm-pick" hidden></div>
<div class="hm-map" id="hm-map" role="group" aria-label="Treemap: area is market cap, colour is the change"></div>
<div class="hm-list" id="hm-list"></div>
<div class="hm-legend"><span class="hm-ramp" id="hm-ramp"></span><span id="hm-scale"></span></div>
<div class="hm-tip" id="hm-tip" hidden></div>
</section>"""

PANEL_JS = r"""<script>
(function(){
var HM = __HEATMAP_JSON__;
var P = 0, SCALE = 'fixed', OPEN = null, PICK = null, UNI = 0;
function $(id){ return document.getElementById(id); }
function esc(s){ return String(s == null ? '' : s).replace(/[&<>"']/g, function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
function pct(v){ return v == null ? '—' : (v > 0 ? '+' : v < 0 ? '−' : '') + Math.abs(v).toFixed(2) + '%'; }
function cap(b){ return b >= 1000 ? '$' + (b / 1000).toFixed(2) + 'T' : b >= 1 ? '$' + Math.round(b) + 'B' : '$' + Math.round(b * 1000) + 'M'; }
function ch(s){ return s[5 + P]; }
function names(){
  var u = HM.universes[UNI] || {idx: []};
  return u.idx.map(function(i){ return HM.stocks[i]; }).filter(function(s){ return !OPEN || s[2] === OPEN; });
}
// The colour stop: fixed per period, or the 90th percentile of |change| of the names shown ("By spread").
function stop(){
  if(SCALE === 'fixed') return HM.stops[P];
  var a = names().map(function(s){ return Math.abs(ch(s)); }).filter(function(v){ return !isNaN(v) && v != null; })
    .sort(function(x, y){ return x - y; });
  return a.length ? Math.max(0.5, a[Math.floor((a.length - 1) * .9)]) : HM.stops[P];
}
function colour(v, st){
  if(v == null) return 'var(--card-2)';
  var t = Math.max(-1, Math.min(1, v / st)), a = Math.round(Math.pow(Math.abs(t), .75) * 78) + 6;
  return 'color-mix(in oklab, var(' + (t >= 0 ? '--pos' : '--neg') + ') ' + a + '%, var(--card-2))';
}
function watch(t){ return typeof rcWatchButtons === 'function' ? rcWatchButtons(t) : ''; }
function squarify(items, r){
  items = items.filter(function(i){ return i.v > 0; }).sort(function(a, b){ return b.v - a.v; });
  var total = items.reduce(function(s, i){ return s + i.v; }, 0), out = [];
  if(!total || r.w <= 0 || r.h <= 0) return out;
  var k = r.w * r.h / total, x = r.x, y = r.y, w = r.w, h = r.h, row = [];
  items.forEach(function(i){ i.a = i.v * k; });
  function worst(row, side){
    var s = 0, mx = 0, mn = Infinity;
    row.forEach(function(i){ s += i.a; mx = Math.max(mx, i.a); mn = Math.min(mn, i.a); });
    return Math.max(side * side * mx / (s * s), s * s / (side * side * mn));
  }
  function lay(row){
    var s = row.reduce(function(a, i){ return a + i.a; }, 0);
    if(w >= h){ var cw = s / h, cy = y; row.forEach(function(i){ i.x = x; i.y = cy; i.w = cw; i.h = i.a / cw; cy += i.h; out.push(i); }); x += cw; w -= cw; }
    else { var chh = s / w, cx = x; row.forEach(function(i){ i.x = cx; i.y = y; i.h = chh; i.w = i.a / chh; cx += i.w; out.push(i); }); y += chh; h -= chh; }
  }
  items.forEach(function(i){
    var side = Math.min(w, h);
    if(!row.length || worst(row.concat([i]), side) <= worst(row, side)) row.push(i);
    else { lay(row); row = [i]; }
  });
  if(row.length) lay(row);
  return out;
}
function groups(){
  var by = {}, order = [];
  names().forEach(function(s){
    var g = OPEN ? s[3] : s[2];
    if(!by[g]){ by[g] = []; order.push(g); }
    by[g].push(s);
  });
  return order.map(function(g){
    var m = by[g], v = 0, w = 0, wsum = 0;
    m.forEach(function(s){ v += s[4]; if(ch(s) != null){ w += s[4] * ch(s); wsum += s[4]; } });
    return {g: g, m: m, v: v, avg: wsum ? w / wsum : null};
  });
}
function tile(x, y, w, h, bg, attrs, inner){
  return '<button class="hm-tile" type="button" ' + attrs + ' style="left:' + x + 'px;top:' + y + 'px;width:' + w + 'px;height:' + h +
    'px;background:' + bg + '">' + inner + '</button>';
}
function drawMap(){
  var el = $('hm-map'), W = el.clientWidth || 0, H = el.clientHeight || 0, st = stop(), html = '';
  if(!OPEN && W <= 600){
    // A phone opens on one tile per sector; a tap expands it.
    squarify(groups(), {x: 0, y: 0, w: W, h: H}).forEach(function(g){
      var fs = Math.max(11, Math.min(18, Math.min(g.w, g.h) / 6)), inner = g.w < 90 || g.h < 70 ?
        '<span class="c" style="font-size:11px">' + pct(g.avg) + '</span>' :
        '<span class="t" style="font-size:' + fs + 'px">' + esc(g.g) + ' ›</span><span class="c" style="font-size:' + Math.max(11, fs * .8) +
        'px">' + pct(g.avg) + '</span><span class="c" style="font-size:11px;opacity:.75">' + g.m.length + ' names</span>';
      html += tile(g.x, g.y, g.w, g.h, colour(g.avg, st), 'data-sec="' + esc(g.g) + '" aria-label="' + esc(g.g) + ', ' + pct(g.avg) + ', open"', inner);
    });
    el.innerHTML = html;
    return;
  }
  squarify(groups(), {x: 0, y: 0, w: W, h: H}).forEach(function(g){
    var head = g.h > 40 && g.w > 60 ? 24 : 0;
    html += '<div class="hm-sec" style="left:' + g.x + 'px;top:' + g.y + 'px;width:' + g.w + 'px;height:' + g.h + 'px">';
    if(head) html += '<button class="hm-sech" type="button"' + (OPEN ? '' : ' data-sec="' + esc(g.g) + '"') + ' title="' + esc(g.g) + '">' +
      esc(g.g) + (OPEN ? '' : ' ›') + ' <span class="avg">' + pct(g.avg) + '</span></button>';
    squarify(g.m.map(function(s){ return {v: s[4], s: s}; }), {x: 1, y: head, w: g.w - 2, h: g.h - head - 1}).forEach(function(t){
      var s = t.s, m = Math.min(t.w, t.h), fs = Math.max(10, Math.min(30, m / 4.2)), inner = '';
      if(t.w >= 34 && t.h >= 22) inner = '<span class="t" style="font-size:' + fs + 'px">' + esc(s[0]) + '</span>';
      if(t.w >= 44 && t.h >= 38) inner += '<span class="c" style="font-size:' + Math.max(10, fs * .62) + 'px">' + pct(ch(s)) + '</span>';
      html += tile(t.x, t.y, t.w, t.h, colour(ch(s), st), 'data-t="' + esc(s[0]) + '"' + (s[0] === PICK ? ' aria-current="true"' : '') +
        ' aria-label="' + esc(s[0]) + ' ' + esc(s[1]) + ', ' + pct(ch(s)) + '"', inner);
    });
    html += '</div>';
  });
  el.innerHTML = html;
}
function drawList(){
  var st = stop(), html = '';
  groups().sort(function(a, b){ return b.v - a.v; }).forEach(function(g){
    var rows = g.m.slice().sort(function(a, b){ return b[4] - a[4]; });
    html += '<div class="hm-card"><button class="hm-cardh" type="button"' + (OPEN ? '' : ' data-sec="' + esc(g.g) + '"') + '><span>' + esc(g.g) +
      (OPEN ? '' : ' ›') + '</span><span class="' + (g.avg >= 0 ? 'pos' : 'neg') + '">' + pct(g.avg) + '</span></button>';
    rows.slice(0, OPEN ? rows.length : 6).forEach(function(s){
      html += '<div class="hm-row">' + watch(s[0]) + '<span class="tk">' + esc(s[0]) + '</span><span class="nm">' + esc(s[1]) + ' · ' + cap(s[4]) +
        '</span><span class="hm-sw sw" style="background:' + colour(ch(s), st) + '">' + pct(ch(s)) + '</span></div>';
    });
    if(!OPEN && rows.length > 6) html += '<button class="hm-more" type="button" data-sec="' + esc(g.g) + '">Show all ' + rows.length + '</button>';
    html += '</div>';
  });
  $('hm-list').innerHTML = html;
}
function drawPick(){
  var el = $('hm-pick'), s = null;
  HM.stocks.forEach(function(x){ if(x[0] === PICK) s = x; });
  if(!s){ el.hidden = true; el.innerHTML = ''; return; }
  el.hidden = false;
  el.innerHTML = watch(s[0]) + '<span class="tk">' + esc(s[0]) + '</span><span>' + esc(s[1]) + '</span><span class="ch ' +
    ((ch(s) || 0) >= 0 ? 'pos' : 'neg') + '">' + pct(ch(s)) + ' ' + HM.periods[P] + '</span><span class="meta">' + esc(s[2]) + ' › ' +
    esc(s[3]) + ' · ' + cap(s[4]) + '</span>';
}
function drawCrumb(){
  $('hm-crumb').innerHTML = OPEN ? '<button type="button" data-all="1">‹ All sectors</button><b>' + esc(OPEN) + '</b><span>· grouped by industry</span>' :
    '<span>All sectors · ' + names().length + ' names</span>';
}
function drawRamp(){
  var s = stop();
  $('hm-ramp').innerHTML = [-1, -2/3, -1/3, 0, 1/3, 2/3, 1].map(function(f){ var v = f * s;
    return '<span style="background:' + colour(v, s) + '">' + (v === 0 ? '0' : (v > 0 ? '+' : '−') + Math.abs(v).toFixed(s < 4 ? 1 : 0)) + '</span>'; }).join('');
  $('hm-scale').textContent = (SCALE === 'fixed' ? 'Colour scale fixed at ±' + s + '% for ' + HM.periods[P] :
    'Colour scale ±' + s.toFixed(1) + '%: 90 % of the names shown moved less over ' + HM.periods[P]) + ' (a move past it is full colour).';
}
function draw(){ drawCrumb(); drawPick(); drawRamp(); drawMap(); drawList(); }
function press(groupId, btn){ [].forEach.call(document.querySelectorAll('#' + groupId + ' button'), function(x){ x.setAttribute('aria-pressed', String(x === btn)); }); }
function init(){
  if(!HM || !HM.stocks || !HM.stocks.length || !$('hm')) return;
  $('hm-asof').textContent = HM.as_of;
  $('hm-uni').innerHTML = HM.universes.map(function(u, i){ return '<option value="' + i + '">' + esc(u.name) + ' · ' + u.idx.length + '</option>'; }).join('');
  $('hm-per').innerHTML = HM.periods.map(function(p, i){ return '<button type="button" aria-pressed="' + (i === 0) + '" data-p="' + i + '">' + esc(p) + '</button>'; }).join('');
  $('hm-uni').addEventListener('change', function(){ UNI = +this.value; OPEN = null; draw(); });
  $('hm').addEventListener('click', function(e){
    var b = e.target.closest('button'); if(!b || b.closest('.rc-watch')) return;
    if(b.dataset.p != null){ P = +b.dataset.p; press('hm-per', b); draw(); }
    else if(b.dataset.s){ SCALE = b.dataset.s; press('hm-scl', b); draw(); }
    else if(b.dataset.v){ $('hm').dataset.view = b.dataset.v; press('hm-view', b); draw(); }
    else if(b.dataset.sec){ OPEN = b.dataset.sec; draw(); }
    else if(b.dataset.all){ OPEN = null; draw(); }
    else if(b.dataset.t){ PICK = b.dataset.t; draw(); }
  });
  var tip = $('hm-tip'), map = $('hm-map');
  map.addEventListener('mousemove', function(e){
    var b = e.target.closest('.hm-tile'), s = null; if(!b || !b.dataset.t){ tip.hidden = true; return; }
    HM.stocks.forEach(function(x){ if(x[0] === b.dataset.t) s = x; });
    if(!s){ tip.hidden = true; return; }
    tip.innerHTML = '<b>' + esc(s[0]) + '</b> ' + esc(s[1]) + '<br><span class="' + ((ch(s) || 0) >= 0 ? 'pos' : 'neg') + '">' + pct(ch(s)) + '</span> ' +
      HM.periods[P] + ' · ' + cap(s[4]) + '<br>' + esc(s[3]);
    tip.style.left = Math.min(e.clientX + 14, innerWidth - 270) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; tip.hidden = false;
  });
  map.addEventListener('mouseleave', function(){ tip.hidden = true; });
  addEventListener('resize', drawMap);
  draw();
}
window.hmInit = init;
if(document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init); else init();
})();
</script>"""


def panel_html(data: dict | None) -> str:
    """The heatmap section for ``data`` (:func:`payload`), or ``""`` when there is none."""
    if not data or not data.get("stocks"):
        return ""
    from RevenueChaser.core.html_safe import fill, script_json
    from RevenueChaser.core.reporting_common import THEME_CSS, THEME_JS
    return (f"<style>{THEME_CSS}</style><script>{THEME_JS}</script>{PANEL_CSS}{PANEL_HTML}"
            + fill(PANEL_JS, {"__HEATMAP_JSON__": script_json(data)}))
