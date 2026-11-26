"""Relatedness board — one focal combobox + top peers from LLM business profiles.

Chrome follows docs/dashboard_ui.md §6: search + count, the shared filter bar
(``rc_filters``; no Theme facet and no cluster chips until the SEC service owns
the profiles, #894 — avo, 16 Nov 2026, decision E option 2), then **one** ticker
combobox. One "Most related to" panel — no Company A / Company B selects. Each
peer row carries the cosine score + percentile and the 1/3/5/10-day move and
residual-vs-SPY correlation.
"""
from __future__ import annotations

import html as _html
from datetime import datetime, timezone

from revenuechaser.core.html_safe import fill, script_json
from revenuechaser.module_comovement import config as comov_config

from . import config
from revenuechaser.core.reporting_common import (
    FILTERS_CSS,
    FILTERS_JS,
    PAYLOAD_JS,
    combobox_html,
    filters_bar_html,
    filters_meta,
    help_html,
    provider_health_html,
    watchlist_html,
)

CSS = """
:root{--bg:#05111F;--panel:#12161e;--panel2:#1a1f2b;--border:#232a38;
--text:#d7dce5;--muted:#8a93a6;--accent:#0EA5E9;--green:#2ecc71;--amber:#f1c40f;--neon:#00e6a8;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.5}
.wrap{max-width:100%;margin:0 auto;padding:20px 24px 60px}
.topbar{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:10px;border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:14px}
.topbar h1{margin:0;font-size:22px;letter-spacing:-.4px}
.topbar .sub{color:var(--muted);margin-top:2px;font-size:13px}
.sync{color:var(--muted);font-size:12.5px;white-space:nowrap}
.banner{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px}
.stat{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.stat .v{font-size:22px;font-weight:800}
.stat .l{color:var(--text);font-size:12px;font-weight:600;margin-top:2px}
.stat .d{color:var(--muted);font-size:11px}
.controls{display:flex;flex-direction:column;gap:8px;margin-bottom:16px}
.frow{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.flbl{color:var(--muted);font-size:12px;font-weight:600}
select,input[type=text],input[type=number]{background:#10151f;border:1px solid #2a3345;color:var(--text);border-radius:6px;height:34px;padding:0 10px;font:500 13px/1 inherit}
input[type=text]{flex:1;min-width:200px}
.count{color:var(--muted);font-size:12px;margin-left:auto;white-space:nowrap}
.pick .rcf-combo{width:300px}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px}
.panel h2{margin:0 0 4px;font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
.panel h2 .nm{text-transform:none;color:var(--text);font-size:15px;letter-spacing:0}
.peer{border-top:1px solid var(--panel2);padding:9px 0}
.peer:first-child{border-top:none}
.peer-head{font-size:14.5px}
.tk{font-weight:750;min-width:64px;letter-spacing:-.2px}
.peer-name{color:var(--text)}
.pct{color:var(--muted);font-size:12.5px;font-variant-numeric:tabular-nums}
.prow-move{color:var(--muted);font-size:12px;font-variant-numeric:tabular-nums;margin-top:3px}
.prow-move .v{color:var(--text);font-weight:600}
.tags{display:flex;flex-wrap:wrap;gap:5px;margin-top:6px}
.tag{background:var(--panel2);border:1px solid var(--border);border-radius:6px;padding:1px 7px;font-size:11.5px;color:var(--muted)}
.more{display:block;width:100%;min-height:44px;margin-top:10px;background:var(--panel2);border:1px solid var(--border);border-radius:8px;color:var(--text);font:600 13px/1.4 inherit;cursor:pointer}
.more:hover{border-color:var(--accent)}
.empty{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:24px;color:var(--muted);text-align:center}
.badge-stale{display:inline-block;margin-left:6px;padding:0 6px;border:1px solid var(--amber);border-radius:6px;color:var(--amber);font-size:11px;font-weight:600}
.badge-writer{display:inline-block;margin-left:6px;padding:0 6px;border:1px solid var(--border);border-radius:6px;color:var(--muted);font-size:11px}
.note{color:var(--muted);font-size:12px;margin-top:12px}
"""


def _friendly(as_of: str) -> str:
    try:
        dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        # A run's time, not a market close (#391 R4): the weekly run lands on a Sunday night.
        return (dt.astimezone(timezone.utc) if dt.tzinfo else dt).strftime("%A, %B %d, %Y %H:%M UTC")
    except (ValueError, TypeError):
        return str(as_of or "")


def _summary_html(payload: dict) -> str:
    n = payload.get("n") or 0
    pending = payload.get("pending") or 0
    no_text = payload.get("no_text") or 0
    short_text = payload.get("short_text") or 0
    # The pairs the board stores and shows (each company's top peers), not every pair compared (#391 R4).
    shown = sum(len(v) for v in (payload.get("peers") or {}).values())
    compared = payload.get("n_pairs") or len(payload.get("scores") or [])
    # Which scorer the peers came from (#669): the board looked the same either way, so it says so (WP0, 11 Nov 2026).
    method = ("description embeddings + customers/suppliers" if payload.get("similarity") == "embedding"
              else "shared tags (fallback)")
    # The names without filing text are not pending (#388 D4): they wait for a 10-K text, not for the next run.
    # Nor are the ones whose Item 1 came out under the splitter's own floor (#313): too short to profile from.
    no_text_line = f'<div class="d">{no_text:,} without filing text</div>' if no_text else ""
    short_text_line = (f'<div class="d">{short_text:,} with too short a filing text</div>'
                       if short_text else "")
    no_parties = len(payload.get("no_parties") or [])
    no_parties_line = (f'<div class="d">{no_parties:,} name no customer, supplier or competitor</div>'
                       if no_parties else "")
    return "".join([
        f'<div class="stat"><div class="v">{n}</div>'
        f'<div class="l">Profiled</div><div class="d">business profiles</div>{no_parties_line}</div>',
        f'<div class="stat"><div class="v">{pending}</div>'
        f'<div class="l">Pending</div><div class="d">no SEC service read yet</div>{no_text_line}{short_text_line}</div>',
        f'<div class="stat"><div class="v">{payload.get("universe_total") or 0}</div>'
        f'<div class="l">Universe</div><div class="d">operating companies, no market-cap floor</div></div>',
        f'<div class="stat"><div class="v">{shown:,}</div>'
        f'<div class="l">Peer pairs</div><div class="d">top {config.TOP_PEERS} per company of {compared:,} '
        f'compared · {method}</div></div>',
    ])


# Company keys the page script never reads (REL-4, #388): the term weights and the raw profile were about a third of
# the page. The engine payload, relatedness_latest.json and the result history keep them.
_EMBED_SKIP = frozenset({"weights", "profile"})


def _embed_companies(companies: list[dict]) -> list[dict]:
    """The companies as the page embeds them: every key but ``_EMBED_SKIP`` (the caller's payload is not touched)."""
    return [{k: v for k, v in c.items() if k not in _EMBED_SKIP} for c in companies]


MODULE = "module_relatedness"
# The per-ticker peer list the board fetches (#383 K10 + the 35 MB page, coordinator PR #919 §8): the served page
# holds no peer row, so it stays small; app/dashboard.py serves the files ``runners`` writes.
PEERS_URL = "/api/relatedness/peers/"


def render_relatedness_dashboard(payload: dict) -> str:
    """The one-file page: every company and every peer list inlined, so it boots with no fetch (tests, guards)."""
    return _render(payload, inline=True)[0]


def render_relatedness_board(payload: dict) -> tuple[str, dict | None]:
    """The served page and its K10 payload (``{"companies": [...]}``), or ``None`` when no company was profiled.

    The HTML holds no company and no peer: it fetches the companies from ``/view/module_relatedness/payload.json``
    and each focal ticker's peers from ``PEERS_URL`` on pick. With no company the empty message needs no fetch.
    """
    return _render(payload, inline=False)


def _render(payload: dict, inline: bool) -> tuple[str, dict | None]:
    payload = payload or {}
    companies = payload.get("companies") or []
    peers = payload.get("peers") or {}
    # #392: no run that scored a name means no data date, never "now".
    sync = _friendly(payload.get("as_of")) if payload.get("as_of") and payload.get("n") else "no run yet"
    model = _html.escape(str(payload.get("model") or ""))
    n = payload.get("n") or 0
    body = f"""
  <div class="banner">{_summary_html(payload)}</div>
  <div class="controls">
    <div class="frow">
      <label class="flbl" for="q">Search</label>
      <input type="text" id="q" placeholder="Search ticker or name…" oninput="onQuery()" aria-label="Search ticker or name" spellcheck="false" autocomplete="off">
      <span class="count" id="count" aria-live="polite"></span>
    </div>
  </div>
  {filters_bar_html("rc-filters")}
  <div class="controls">
    <div class="frow pick">
      <span class="flbl" id="ticker-combo-label">Ticker</span>
      {combobox_html("ticker-combo", "ticker-combo-label", "Search ticker or name")}
    </div>
  </div>
  <div class="panel">
    <h2 id="panel-title">Most related to</h2>
    <div class="pct" id="meta"></div>
    <div id="peers" aria-live="polite"></div>
  </div>"""

    JS = PAYLOAD_JS + r"""
var MOD = __MOD__;
var BOOT = __BOOT__;
var PEERS_URL = __PEERS_URL__;
var DATA = [];
var PEERS = {};
var LOADING = {};
var INLINE = false;
var META = __META__;
var WRITER = __WRITER__;
var QUERY = "";
var FOCAL = null;
var VISIBLE = __VISIBLE__;
var EXPANDED = false;
var RCF = null;
var BY = {};
// The shared filter bar (rc_filters, #383 C1b) plus the board's own search box narrow the focal picker.
function pass(c){
  if(RCF && !RCF.pass(c)) return false;
  if(QUERY){
    var q = QUERY.toLowerCase();
    if((c.ticker||"").toLowerCase().indexOf(q) < 0 && (c.name||"").toLowerCase().indexOf(q) < 0) return false;
  }
  return true;
}
function onQuery(){
  QUERY = (document.getElementById("q").value || "").trim();
  render();
}
function onFocal(ticker){
  // A new company opens short again (#1568).
  if(ticker && ticker !== FOCAL) EXPANDED = false;
  if(ticker) FOCAL = ticker;
  render();
}
function showAllPeers(){
  EXPANDED = true;
  render();
}
function rebuildOptions(){
  var vis = DATA.filter(pass);
  if(!vis.some(function(c){ return c.ticker === FOCAL; })){
    FOCAL = vis.length ? vis[0].ticker : null;
  }
  var input = document.getElementById("ticker-combo");
  if(input){
    var item = vis.filter(function(c){ return c.ticker === FOCAL; })[0] || null;
    input.value = item ? item.ticker + " — " + (item.name || item.ticker) : "";
  }
  document.getElementById("count").textContent = vis.length + " names";
}
function tags(list){ return (list||[]).map(function(t){ return '<span class="tag">'+rcEsc(t)+'</span>'; }).join(""); }
function fmtMove(p){
  if(!p.move) return "";
  var parts = [];
  [1,3,5,10].forEach(function(n){
    var v = p.move[String(n)];
    if(v == null) return;
    parts.push(n + 'd ' + Number(v).toFixed(2));
  });
  if(!parts.length) return "";
  var line = 'move  ' + parts.join('   ');
  if(p.beyond_spy != null){
    line += '     beyond SPY ' + Number(p.beyond_spy).toFixed(2) + ' (__BEYOND_H__d)';
  }
  return '<div class="prow-move">' + line + '</div>';
}
function staleBadge(t){
  return ((BY[t] && BY[t].stale) ? '<span class="badge-stale" title="Profiled under an older model/prompt; refreshes on the next run">stale</span>' : "") + writerBadge(t);
}
// Mixed writers (11 Nov 2026): a profile another writer made stays current; name that writer's model on it.
function writerBadge(t){
  var w = BY[t] && BY[t].writer;
  if(!w || w === WRITER) return "";
  return '<span class="badge-writer" title="Profile written by ' + rcEsc(w) + '">' + rcEsc(w.split("/").pop()) + '</span>';
}
function peerRow(p){
  var name = p.name || "";
  return '<div class="peer">' +
    '<div class="peer-head"><span class="tk">' + rcEsc(p.peer) + '</span>' +
    (name ? '<span class="peer-name"> — ' + rcEsc(name) + '</span>' : '') + staleBadge(p.peer) + '</div>' +
    rcWatchRow(p.peer) +
    '<div class="pct">' + Number(p.score||0).toFixed(2) + ' · p' + p.percentile +
      (p.n_shared != null ? ' · ' + p.n_shared + ' shared' : '') + '</div>' +
    fmtMove(p) +
    '<div class="tags">' + tags(p.shared) + '</div>' +
    '</div>';
}
function render(){
  rebuildOptions();
  var meta = document.getElementById("meta");
  var panel = document.getElementById("panel-title");
  var body = document.getElementById("peers");
  if(!FOCAL){
    meta.textContent = "";
    panel.textContent = "Most related to";
    body.innerHTML = '<div class="empty">' + (DATA.length
      ? "No companies match the current filters."
      : "No profiles yet. The weekly Sunday run (RC-Relatedness-OffPeak) copies them from the SEC service.") + '</div>';
    return;
  }
  var c = BY[FOCAL] || {};
  panel.innerHTML = "Most related to " + rcEsc(FOCAL) +
    (c.name ? ' <span class="nm">— ' + rcEsc(c.name) + '</span>' : "") + staleBadge(FOCAL) + rcWatchButtons(FOCAL);
  meta.textContent =
    (c.sector || "") + (c.industry ? " · " + c.industry : "") +
    ((c.also || []).length ? " · also " + c.also.join(", ") : "");
  var list = INLINE ? (PEERS[FOCAL] || []) : PEERS[FOCAL];
  if(list === undefined){ loadPeers(FOCAL); body.innerHTML = '<div class="empty">Loading…</div>'; return; }
  if(list === null){ body.innerHTML = '<div class="empty">The peers did not load. Press Refresh.</div>'; return; }
  if(!list.length){ body.innerHTML = '<div class="empty">No peers.</div>'; return; }
  // Display fold (#1568): the first VISIBLE rows, the rest behind one button.
  var shown = (EXPANDED || list.length <= VISIBLE) ? list : list.slice(0, VISIBLE);
  var html = shown.map(peerRow).join("");
  if(shown.length < list.length){
    html += '<button type="button" class="more" onclick="showAllPeers()">Show all ' + list.length +
      ' related companies (' + (list.length - shown.length) + ' more)</button>';
  }
  body.innerHTML = html;
}
// One small request per focal ticker; the answer is kept, so going back to a ticker costs nothing.
function loadPeers(t){
  if(LOADING[t]) return;
  LOADING[t] = true;
  fetch(PEERS_URL + encodeURIComponent(t), {cache: "no-cache", credentials: "same-origin"})
    .then(function(r){
      if(r.status === 404) return {peers: []};
      if(!r.ok) throw new Error("peers " + r.status);
      return r.json();
    })
    .then(function(d){ PEERS[t] = d.peers || []; }, function(){ PEERS[t] = null; })
    .then(function(){ LOADING[t] = false; if(FOCAL === t) render(); });
}
function boot(data){
  DATA = data.companies || [];
  if(data.peers){ PEERS = data.peers; INLINE = true; }
  BY = {}; DATA.forEach(function(c){ BY[c.ticker] = c; });
  init();
}
function start(){
  if(BOOT){ boot(BOOT); return; }
  document.getElementById("count").textContent = "Loading…";
  rcPayload(MOD).then(boot, function(e){
    document.getElementById("count").textContent = "The board did not load (" + e.message + "). Press Refresh.";
  });
}
function init(){
  RCF = RCFilters.mount({root: "#rc-filters", rows: DATA, meta: META, onChange: function(){ render(); }});
  RCInfo.wire();
  var input = document.getElementById("ticker-combo");
  if(input) RCCombobox.mount({input: input, list: "#ticker-combo-list", rows: DATA, filter: pass, clear: true,
    onPick: function(r){ onFocal(r.ticker); }});
  FOCAL = (DATA[0] || {}).ticker || null;
  render();
}
"""

    embedded = {"companies": _embed_companies(companies)}
    # Inline: the whole board in the page. Served: no row in the page, unless there is none to fetch.
    boot = {**embedded, "peers": peers} if inline else (None if companies else embedded)
    JS = fill(JS, {"__BEYOND_H__": str(int(comov_config.DEFAULT_HORIZON)),
                   "__VISIBLE__": str(int(config.VISIBLE_PEERS)),
                   "__MOD__": script_json(MODULE),
                   "__BOOT__": script_json(boot),
                   "__PEERS_URL__": script_json(PEERS_URL),
                   "__WRITER__": script_json("/".join((payload.get("writer") or {}).get(k) or "" for k in
                                                       ("provider", "model")) or None),
                   "__META__": script_json(filters_meta(
                       "relatedness", earnings_mode="filter",
                       facets=["index", "mc", "gics", "earnings"]))})

    help_block = help_html(
        "Each company's profile is the SEC reading service's answer for its latest 10-K, 20-F or 40-F: what it "
        "sells, to whom, its customers and suppliers, its value-chain role. Relatedness measures "
        "<b>similar business</b>, not co-movement (see Co-movement) or trading links "
        f"(see Value Chain). {n} companies · model <b>{model}</b>. This board's <b>Fetch</b> has no button "
        "(the writer may be the paid one): it is the <b>weekly Sunday run</b>, which "
        "copies new profiles from the service and rescores every pair; <b>Refresh</b> rebuilds the board from "
        f"the stored profiles and scores with no network call. A pair's score is {config.W_DO:g} × how alike the "
        f"two business descriptions read (local embeddings) + {config.W_CHAIN:g} × the customer and supplier "
        f"types and names they share + {config.W_STRUCT:g} × matching structure (business model, role). Each "
        f"company shows its top {config.TOP_PEERS} peers — the first {config.VISIBLE_PEERS} open with the board and "
        "the rest on the button under them; the percentile ranks a peer among every pair compared.")
    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Relatedness</title>
<style>{CSS}</style>
{FILTERS_CSS}
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div>
      <h1>Relatedness</h1>
      <div class="sub">Business similarity from 10-K Item 1 / 20-F Item 4 — not price, not supply chain</div>
    </div>
    <div class="sync">Last sync: {_html.escape(sync)}</div>
  </div>
  {provider_health_html(payload.get("provider_health"))}
  {help_block}
  
  {body}
</div>
<script>{FILTERS_JS}</script>
{watchlist_html("relatedness")}
<script>{JS}
start();
</script>
</body>
</html>
"""
    return page, (None if inline or not companies else embedded)
