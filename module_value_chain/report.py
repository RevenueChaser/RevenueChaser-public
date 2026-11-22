"""Value Chain board — Explorer: pick a ticker, see upstream / downstream / 2-hop.

The 2-hop graph is computed server-side per ticker (``engine.focal_graph``) and
fetched for the picked company only (``/api/value_chain/graph/<ticker>``), so the client only draws it. Evidence (a plain-language sentence + the
filing snippet + form + date) sits next to every edge — without it the sankey is
just a word cloud.

Readability is deliberate: a legend with direction arrows (not colour alone), a
"what am I looking at?" panel, and an explicit note that a link is what the filing
states, not a confirmed relationship.
"""
from __future__ import annotations

from datetime import datetime

from revenuechaser.core.config import PLOTLY_CDN_URL
from revenuechaser.core.gics_map import sector_or_unclassified, sector_path
from revenuechaser.core.html_safe import esc, fill, script_json
from revenuechaser.core.reporting_common import (
    FILTERS_CSS,
    FILTERS_JS,
    combobox_html,
    filters_bar_html,
    filters_meta,
    help_html,
    provider_health_html,
    watchlist_html,
)

from . import config, precision

CSS = """
:root{--bg:#05111F;--panel:#12161e;--panel2:#1a1f2b;--border:#232a38;
--text:#d7dce5;--muted:#8a93a6;--accent:#0EA5E9;--green:#2ecc71;--red:#e74c3c;--amber:#f1c40f;--neon:#00e6a8;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--text);font-family:-apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;font-size:14px;line-height:1.5}
.wrap{max-width:100%;margin:0 auto;padding:20px 24px 60px}
.topbar{display:flex;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;gap:10px;border-bottom:1px solid var(--border);padding-bottom:12px;margin-bottom:14px}
.topbar h1{margin:0;font-size:22px;letter-spacing:-.4px}
.topbar .sub{color:var(--muted);margin-top:2px;font-size:13px}
.sync{color:var(--muted);font-size:12.5px;white-space:nowrap}
.legend{display:flex;flex-wrap:wrap;gap:16px;align-items:center;margin-bottom:14px;font-size:12.5px;color:var(--muted)}
.legend b{color:var(--text)}
.arrow{font-weight:700}
.a-sup{color:var(--accent)} .a-foc{color:var(--neon)} .a-cus{color:var(--green)}
.banner{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:16px}
.stat{background:var(--panel);border:1px solid var(--border);border-radius:10px;padding:12px 14px}
.stat .v{font-size:22px;font-weight:800}
.stat .l{color:var(--text);font-size:12px;font-weight:600;margin-top:2px}
.stat .d{color:var(--muted);font-size:11px}
.stat.warn{border-color:rgba(241,196,15,.45)} .stat.warn .v{color:var(--amber)}
.controls{display:flex;flex-direction:column;gap:8px;margin-bottom:16px}
.frow{display:flex;flex-wrap:wrap;gap:10px;align-items:center}
.flbl{color:var(--muted);font-size:12px;font-weight:600}
.pick .rcf-combo{width:300px}
select,input[type=text],input[type=number]{background:#10151f;border:1px solid #2a3345;color:var(--text);border-radius:6px;height:34px;padding:0 10px;font:500 13px/1 inherit}
input[type=text]{flex:1;min-width:200px}
.count{color:var(--muted);font-size:12px;margin-left:auto;white-space:nowrap}
.chip{display:inline-block;background:var(--panel2);border:1px solid var(--border);border-radius:20px;padding:1px 9px;font-size:11px;color:var(--muted)}
.chip.warn{background:rgba(241,196,15,.12);border-color:rgba(241,196,15,.4);color:var(--amber)}
.chip.share{background:rgba(14,165,233,.12);border-color:rgba(14,165,233,.4);color:var(--accent);font-weight:700}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:1000px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:14px}
.panel h2{margin:0 0 10px;font-size:14px;color:var(--muted);text-transform:uppercase;letter-spacing:.4px}
.edge{border-top:1px solid var(--panel2);padding:9px 0}
.edge:first-child{border-top:none}
.rel{display:inline-block;padding:1px 8px;border-radius:20px;font-size:11px;font-weight:700;margin-right:6px}
.r-supplier{background:rgba(79,157,255,.16);color:var(--accent)}
.r-customer{background:rgba(46,204,113,.16);color:var(--green)}
.sentence{font-weight:600}
.snip{color:var(--muted);font-size:12.5px;margin-top:3px}
.meta{color:var(--muted);font-size:11px;margin-top:3px}
.empty{background:var(--panel);border:1px solid var(--border);border-radius:12px;padding:24px;color:var(--muted);text-align:center}
.note{color:var(--muted);font-size:12px;margin-top:12px;line-height:1.6}
/* "Show the other N links" (#1159): a full-width 44 px target, so it works on a phone. */
.more{display:block;width:100%;min-height:44px;margin-top:12px;background:var(--panel2);border:1px solid var(--border);
border-radius:8px;color:var(--text);font:600 13px/1 inherit;cursor:pointer}
.more:hover{border-color:var(--accent);color:var(--accent)}
.more:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
"""


def _friendly(as_of: str) -> str:
    try:
        dt = datetime.fromisoformat(str(as_of).replace("Z", "+00:00"))
        # A sync time, not a market close: no "EOD".
        return dt.strftime("%A, %B %d, %Y")
    except (ValueError, TypeError):
        return str(as_of or "")


def _precision_tile(rep: dict | None) -> str:
    """Measured precision of supplier/customer links on the census labels (plan v31 section 6): the share labelled
    right, and the Wilson 95% lower bound the gate reads."""
    rep = rep or {}
    p = rep.get("precision")
    cover = ""
    if rep.get("links") is not None:
        # "Links drawn" counts the served rows; this counts the distinct (filer, counterparty, relation) pairs
        # they make, which is what a label can speak for. The words differ so the two tiles cannot be read as
        # one number (#1159).
        cover = f' · labels cover {rep.get("covered") or 0} of {rep["links"]:,} distinct pairs'
    if p is None:
        return ('<div class="stat"><div class="v">—</div><div class="l">Precision</div>'
                f'<div class="d">not measured{cover}</div></div>')
    n = rep.get("n") or 0
    cls = "stat" if rep.get("passes") else "stat warn"
    lower = rep.get("lower_bound")
    bound = f"lower bound {round(lower * 100)}%" if lower is not None else "no lower bound"
    detail = esc(f"hand-checked n={n} · {bound} · gate 70%{cover}")
    return (f'<div class="{cls}"><div class="v">{round(p * 100)}%</div>'
            f'<div class="l">Precision</div>'
            f'<div class="d">{detail}</div></div>')


def _status_notes(payload: dict) -> str:
    """What the board holds back or carries over (plan v31 G-F and step 1(f)), one note each."""
    notes = []
    if payload.get("kept"):
        notes.append("Edges from an earlier run: the last sync found none, so the board shows the stored ones.")
    hidden = int(payload.get("profile_hidden") or 0)
    if hidden:
        notes.append(f"Profile relationships not yet verified: {hidden} links read from company profiles are "
                     "hidden until a hand-checked sample clears them. The board shows the customers each filing "
                     "tags in its XBRL.")
    notes.append("A link is what the filing states, not a confirmed relationship: read its source line before "
                 "relying on one.")
    return "".join(f'<div class="note">⚠ {esc(n)}</div>' for n in notes)


def _summary_html(payload: dict, n_filings: int, n_drawn: int) -> str:
    fetch = payload.get("fetch") or {}
    pending = payload.get("pending")
    if pending is None:
        pending = fetch.get("pending") or 0
    # Tickers left out of Pending (#116 C26): a recorded miss or no CIK.
    pending_d = "not in the SEC layer yet" if payload.get("corpus") == "layer" else "not yet fetched"
    # One filer can state the same counterparty in several filings or fields, so the served rows are more than
    # the pairs they make. The tile says both, because the Precision tile counts the pairs (#1159).
    n_pairs = (payload.get("precision") or {}).get("links")
    pairs_d = f' · {n_pairs:,} distinct pairs' if n_pairs else ""
    misses, no_cik = int(payload.get("misses") or 0), int(payload.get("no_cik") or 0)
    if misses:
        pending_d += f" · {misses} with no 10-K / 20-F"
    if no_cik:
        pending_d += f" · {no_cik} with no CIK"
    return "".join([
        f'<div class="stat"><div class="v">{n_filings}</div>'
        f'<div class="l">Filings</div><div class="d">latest annual report</div></div>',
        f'<div class="stat"><div class="v">{n_drawn:,}</div>'
        f'<div class="l">Links drawn</div><div class="d">supplier / customer links served'
        f'{pairs_d}</div></div>',
        f'<div class="stat"><div class="v">{payload.get("universe_total") or 0}</div>'
        f'<div class="l">Universe</div><div class="d">operating companies, no market-cap floor</div></div>',
        f'<div class="stat"><div class="v">{pending}</div>'
        f'<div class="l">Pending</div><div class="d">{esc(pending_d)}</div></div>',
        _precision_tile(payload.get("precision")),
    ])


def _picker_rows(filings: list[dict], extra: set[str]) -> list[dict]:
    """Every filing plus mention-src tickers, with filter fields for the picker."""
    by = {f["ticker"]: f for f in filings}
    rows = []
    for t in sorted(set(by) | extra):
        f = by.get(t) or {}
        rows.append({
            "ticker": t,
            "name": f.get("name") or t,
            "sector": sector_or_unclassified(f.get("sector")),
            "industry": f.get("industry") or "",
            "market_cap": f.get("market_cap"),
            "earnings_date": f.get("earnings_date"),
            "index": f.get("index") or [],
            # The shared filter row (#383 C1b): the sector path and the pinned theme run's ids.
            "gics": f.get("gics") or sector_path(sector_or_unclassified(f.get("sector")), f.get("industry") or ""),
            "theme_ids": f.get("theme_ids") or [],
            "form": f.get("form"),
            "filed": f.get("filed"),
            "quality": f.get("quality"),
            "unnamed_customers": f.get("unnamed_customers") or 0,
        })
    return rows


def _default_focal(tickers: list[str], edges: list[dict]) -> str | None:
    """The visible ticker with the most edges (deterministic tie-break: name)."""
    degree = {t: 0 for t in tickers}
    for e in edges:
        s, d = e.get("src"), e.get("dst_ticker")
        if s in degree:
            degree[s] += 1
        if d in degree:
            degree[d] += 1
    if not degree:
        return None
    return sorted(degree, key=lambda t: (-degree[t], t))[0]


def render_value_chain_dashboard(payload: dict) -> str:
    payload = payload or {}
    filings = payload.get("filings") or []
    edges = payload.get("edges") or []
    # An empty store has no sync date; printing today read as "synced today" (#392).
    sync = _friendly(payload.get("as_of")) or "no sync yet"
    informed = set()
    for e in edges:
        if e.get("relation") in ("supplier", "customer"):
            informed.update(t for t in (e.get("src"), e.get("dst_ticker")) if t)
    extra = informed
    picker = [r for r in _picker_rows(filings, extra) if r["ticker"] in informed]
    tickers = [r["ticker"] for r in picker]
    # The focal company's graph is fetched when it is picked (GRAPH_URL), not embedded for every ticker: the page
    # carried every ticker's two-hop graph and measured 14.6 MB on homesrv (claude-coordinator PR #919, section 8).
    default_focal = _default_focal(tickers, edges)
    n_drawn = sum(1 for e in edges if e.get("relation") in ("supplier", "customer"))
    summary = _summary_html(payload, len(filings), n_drawn)

    body = f"""
  <div class="banner">{summary}</div>
  <div class="legend">
    <span><span class="arrow a-sup">▲</span> <b>Supplier</b> — sells to the focal company</span>
    <span><span class="arrow a-foc">●</span> <b>Focal</b> — the company you picked</span>
    <span><span class="arrow a-cus">▼</span> <b>Customer</b> — buys from the focal company</span>
  </div>
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
    <div class="frow"><span class="chip" id="fmeta"></span></div>
  </div>
  <div class="grid">
    <div class="panel"><h2>Supply chain</h2><div id="sankey" style="height:520px"></div>
      <div class="note" id="sankey-note" hidden></div></div>
    <div class="panel"><h2>Evidence</h2><div id="edges"></div></div>
  </div>"""

    JS = r"""
var DATA = __DATA__;
var GRAPH_URL = "/api/value_chain/graph/";
var GRAPHS = {};          // ticker -> its graph, filled from GRAPH_URL as companies are picked
var FILINGS = {};         // the picker rows carry each filing's form, date and quality
DATA.forEach(function(r){ FILINGS[r.ticker] = r; });
var DEFAULT_FOCAL = __DEFAULT_FOCAL__;
var META = __META__;
var FOCAL = null;
var QUERY = "";
var RCF = null;
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
  if(ticker) FOCAL = ticker;
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
function options(){
  FOCAL = (DEFAULT_FOCAL && FILINGS[DEFAULT_FOCAL]) ? DEFAULT_FOCAL : ((DATA[0]||{}).ticker || null);
  rebuildOptions();
}
// The relationship seen from the focal company, which is what the legend defines (#405). An edge stored
// before the field falls back to the filing's own relation.
function focalRelation(l){ return l.focal_relation || l.relation; }
function sentence(l){
  var s = l.src, d = l.dst;
  if(l.relation === "supplier") return s + "'s filing names " + d + " as a possible supplier";
  if(l.relation === "customer") return s + "'s filing names " + d + " as a possible customer";
  return s + " mentions " + d;
}
function suspicious(l){
  // The chip names the list the snippet reads like, so it never says "customer list" on a customer edge (DF60).
  var s = (l.snippet || "").toLowerCase();
  if(l.relation === "supplier" && s.indexOf("customer") >= 0) return "may be a customer list";
  if(l.relation === "customer" && (s.indexOf("supplier") >= 0 || s.indexOf("purchase") >= 0)) return "may be a supplier list";
  return "";
}
// #387 D7: the share of the filer's (src's) sales (a customer) or purchases (a supplier) its filing states.
function hasShare(l){ return typeof l.share_pct === "number" && isFinite(l.share_pct); }
function shareText(l){
  if(!hasShare(l)) return "";
  return l.share_pct + "% of " + l.src + "'s " + (l.relation === "supplier" ? "purchases" : "sales");
}
function render(){
  rebuildOptions();
  if(!FOCAL){
    var none = '<div class="empty">' + (DATA.length
      ? "No companies match the current filters."
      : "No companies with supplier / customer links yet. <b>Fetch</b> reads them from the stored SEC filings.") + "</div>";
    document.getElementById("sankey").innerHTML = none;
    document.getElementById("edges").innerHTML = none;
    document.getElementById("fmeta").innerHTML = "";
    return;
  }
  var g = GRAPHS[FOCAL];
  if(!g){ loadGraph(FOCAL); return; }
  var links = g.links || [];
  if(g.failed){
    var err = '<div class="empty">Could not load ' + rcEsc(FOCAL) + "'s links. Reload the page to try again.</div>";
    document.getElementById("sankey").innerHTML = err;
    document.getElementById("edges").innerHTML = err;
    delete GRAPHS[FOCAL];      // a later pick asks again
    return;
  }
  var fm = FILINGS[FOCAL] || {};
  var q = fm.quality || "";
  document.getElementById("fmeta").innerHTML = rcWatchRow(FOCAL) +     // the focal company's pair (PR 4)
    (fm.form ? rcEsc(fm.form) + " · filed " + rcEsc(fm.filed) + " · " : "") +
    (q.split(";")[0] === "ok" ? "text: ok" : (q ? '<span class="chip warn">text: ' + rcEsc(q) + ' — item not fully extracted</span>' : ""));
  links = rankLinks(links);
  drawSankey(FOCAL, links);
  drawEdges(links);
  // D: customers the filing does not name are no nodes; the row says how many there are.
  var nu = fm.unnamed_customers || 0;
  if(nu) document.getElementById("edges").insertAdjacentHTML("beforeend", '<div class="note">Also ' + nu +
    (nu === 1 ? " unnamed customer: the filing does not name it." : " unnamed customers: the filing does not name them.") + "</div>");
}
// A hub such as AMZN is named by hundreds of filers, and the chart drew every one: the labels overlapped into a
// solid block at every width and the evidence list made the page 40,000 px tall on a phone (#1159, measured on
// real data 20 Nov 2026). Both halves now show the strongest links first and keep the rest one tap away.
var SANKEY_MAX = 40;        // links the chart draws: past this it is a wall of labels, not a graph
var EVIDENCE_PAGE = 25;     // evidence rows rendered before "show the rest"

// The order both halves read: hop 1 first, then the edges whose filing states a share, largest share first
// (#387 D7), then supplier before customer. Returns a new array; the caller's is left alone.
function rankLinks(links){
  var order = { supplier: 0, customer: 1 };
  return (links || []).slice().sort(function(a,b){
    return (a.hop - b.hop) || (hasShare(b) - hasShare(a)) ||
      (hasShare(a) && hasShare(b) ? b.share_pct - a.share_pct : 0) ||
      (order[focalRelation(a)]-order[focalRelation(b)]);
  });
}
// A hub's links are nearly all one direction -- AMZN's 261 are suppliers almost to the last -- so taking the
// strongest 40 flat would draw one colour and could hide the other side of a mixed company altogether. Each
// direction gets half the budget and whatever the other does not use, so a company with 200 suppliers and 5
// customers still draws all 5. The ranked order is kept, so the chart and the evidence list agree.
function capForChart(links){
  if(links.length <= SANKEY_MAX) return links;
  var sup = [], cus = [];
  links.forEach(function(l){ (focalRelation(l) === "supplier" ? sup : cus).push(l); });
  var half = Math.floor(SANKEY_MAX / 2);
  var nSup = Math.min(sup.length, SANKEY_MAX - Math.min(cus.length, half));
  var nCus = Math.min(cus.length, SANKEY_MAX - nSup);
  var kept = sup.slice(0, nSup).concat(cus.slice(0, nCus));
  return links.filter(function(l){ return kept.indexOf(l) >= 0; });
}
// At 411 px an unresolved counterparty's full legal name ("Hon Hai Precision Industry Co., Ltd.") is wider than
// the gap between two columns, and Plotly right-aligns the last column's labels across the node to their left,
// which covered the focal "NVDA" in the real render (#1159). The chart draws a short label with the full name on
// hover; the evidence row below always carries the name in full.
var NODE_LABEL_MAX = 18;
function nodeLabel(name){
  name = String(name == null ? "" : name);
  if(name.length <= NODE_LABEL_MAX) return name;
  return name.slice(0, NODE_LABEL_MAX - 1).replace(/[\s,.]+$/, "") + "…";
}
// A pair both companies state ("NVDA's filing names FN", "FN's filing names NVDA at 16.3% of sales") puts one
// node on both sides of the focal company, and Plotly draws that as a circular link: it leaves the node, runs
// under the chart and comes back as a rounded box (#1159, NVDA at 411 px). The chart draws such a pair once,
// keeping whichever the ranking puts first; both statements stay in the evidence list.
function dropReverseDuplicates(links){
  var seen = {}, kept = [];
  (links || []).forEach(function(l){
    var a = String(l.src), b = String(l.dst);
    if(seen[b + ">" + a]) return;
    seen[a + ">" + b] = true;
    kept.push(l);
  });
  return kept;
}
function drawSankey(focal, links){
  var note = document.getElementById("sankey-note");
  var total = links.length;
  links = dropReverseDuplicates(links);
  var capped = links.length > SANKEY_MAX;
  if(capped) links = capForChart(links);
  if(links.length < total){
    note.textContent = (capped
      ? "Showing the " + links.length + " strongest of " + total +
        " links: the ones whose filing states a share, largest first, both directions kept. "
      : "Showing " + links.length + " of " + total +
        " links: a pair both companies' filings state is drawn once. ") +
      "Every one is in the evidence below.";
    note.hidden = false;
  } else {
    note.textContent = ""; note.hidden = true;
  }
  var nodes = [focal], idx = {}; idx[focal] = 0;
  links.forEach(function(l){
    [l.src, l.dst].forEach(function(n){ if(!(n in idx)){ idx[n] = nodes.length; nodes.push(n); } });
  });
  var src = links.map(function(l){ return idx[l.src]; });
  var dst = links.map(function(l){ return idx[l.dst]; });
  var val = links.map(function(){ return 1; });
  var colors = links.map(function(l){
    return focalRelation(l) === "supplier" ? "rgba(79,157,255,.5)" : "rgba(46,204,113,.5)";
  });
  var nodeColors = nodes.map(function(n){
    if(n === focal) return "#00e6a8";
    return "#1a1f2b";
  });
  var data = [{ type: "sankey", orientation: "h", arrangement: "snap",
    node: { label: nodes.map(nodeLabel), customdata: nodes,
            hovertemplate: "%{customdata}<extra></extra>",
            pad: 12, thickness: 14, color: nodeColors,
            font: { color: "#d7dce5", size: 11 } },
    link: { source: src, target: dst, value: val, color: colors } }];
  var layout = { paper_bgcolor: "#12161e", plot_bgcolor: "#12161e",
                 font: { color: "#d7dce5" }, margin: { l: 8, r: 8, t: 8, b: 8 } };
  if(window.Plotly) Plotly.newPlot("sankey", data, layout, { displayModeBar: false, responsive: true });
}
function drawEdges(links){
  var el = document.getElementById("edges");
  if(!links.length){ el.innerHTML = '<div class="empty">No supplier / customer edges found for this company.</div>'; return; }
  // ``links`` is already ranked by ``rankLinks``. Only the first page is put in the DOM: a hub with hundreds of
  // links made the page unscrollable on a phone (#1159).
  el.innerHTML = edgeRows(links.slice(0, EVIDENCE_PAGE));
  if(links.length > EVIDENCE_PAGE){
    var rest = links.slice(EVIDENCE_PAGE);
    var btn = document.createElement("button");
    btn.type = "button"; btn.className = "more"; btn.id = "edges-more";
    btn.textContent = "Show the other " + rest.length + " links";
    btn.addEventListener("click", function(){
      btn.insertAdjacentHTML("beforebegin", edgeRows(rest));
      btn.remove();
    });
    el.appendChild(btn);
  }
}
function edgeRows(links){
  return links.map(function(l){
    var why = suspicious(l);
    var flag = why ? ' <span class="chip warn">⚠ ' + why + '</span>' : '';
    var share = hasShare(l) ? ' <span class="chip share">' + rcEsc(shareText(l)) + '</span>' : '';
    var rel = focalRelation(l);
    return '<div class="edge"><div><span class="rel r-'+rcEsc(rel)+'">'+rcEsc(rel)+'</span>' +
      '<span class="sentence">'+rcEsc(sentence(l))+'</span>' + share +
      (l.hop === 2 ? ' <span class="chip">2-hop</span>' : '') + flag + '</div>' +
      '<div class="snip">“'+rcEsc(l.snippet)+'”</div>' +
      '<div class="meta">'+(l.source === "profile" ? "from the company profile (LLM reading)"
        : l.source === "xbrl" ? "from the filing's XBRL" : "auto-extracted, unverified") +
      ' · source: '+rcEsc((FILINGS[l.src] || {}).form || "annual report")+', '+rcEsc((FILINGS[l.src] || {}).filed || "")+'</div></div>';
  }).join("");
}
function loadGraph(ticker){
  var msg = '<div class="empty">Loading ' + rcEsc(ticker) + '…</div>';
  document.getElementById("edges").innerHTML = msg;
  document.getElementById("sankey").innerHTML = msg;
  fetch(GRAPH_URL + encodeURIComponent(ticker))
    .then(function(r){ return r.ok ? r.json() : null; })
    .catch(function(){ return null; })
    .then(function(j){
      GRAPHS[ticker] = (j && j.graph) || {links: [], failed: !j};
      if(FOCAL === ticker) render();
    });
}
function init(){
  RCF = RCFilters.mount({root: "#rc-filters", rows: DATA, meta: META, onChange: function(){ render(); }});
  RCInfo.wire();
  var input = document.getElementById("ticker-combo");
  if(input) RCCombobox.mount({input: input, list: "#ticker-combo-list", rows: DATA, filter: pass, clear: true,
    onPick: function(r){ onFocal(r.ticker); }});
  options(); render();
}
"""

    JS = fill(JS, {"__DATA__": script_json(picker),
                   "__DEFAULT_FOCAL__": script_json(default_focal or ""),
                   "__META__": script_json(filters_meta(
                       "value_chain", earnings_mode="filter",
                       themes=payload.get("theme_catalog") or {}))})

    fetch_help = ("<b>Fetch</b> reads the filings the SEC service has stored (it downloads nothing itself) and "
                  "rebuilds the links" if payload.get("corpus") == "layer" else
                  "<b>Fetch (EDGAR)</b> downloads a filing from SEC only for a name with none stored and rebuilds "
                  "the links")
    help_block = help_html(
        "A link is a customer or supplier that a company's latest annual report (10-K, 20-F or 40-F) names. "
        "Customers come from the filing's XBRL tags; links read from the company profile (an LLM reading of the "
        "same report) "
        + ("are shown too. " if config.SERVE_PROFILE_EDGES else "are hidden until a hand-checked sample clears them. ")
        + "The arrow shows the direction: "
        "a <b>supplier</b> sells to the focal company, a <b>customer</b> buys from it. "
        "A <b>2-hop</b> edge is one step further out: a supplier or a customer of a first-hop company. "
        "A <b>percentage</b> on an edge is the share of the filer's sales (a customer) or purchases (a supplier) "
        "that the filing itself states; those edges are listed first, largest share first. "
        "A customer is linked only when its name resolves to a listed company; an unnamed one "
        "(\"Customer A\") gives no link, and the company's row says how many it has. "
        + fetch_help + "; <b>Refresh</b> redraws the board from the stored links with no network call.")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>Value Chain</title>
<script src="{PLOTLY_CDN_URL}"></script>
<style>{CSS}</style>
{FILTERS_CSS}
</head>
<body>
<div class="wrap">
  <div class="topbar">
    <div>
      <h1>Value Chain</h1>
      <div class="sub">Supplier / customer edges stated in the latest 10-K / 20-F</div>
    </div>
    <div class="sync">Last sync: {esc(sync)}</div>
  </div>
  {provider_health_html(payload.get("provider_health"))}
  {help_block}
  {_status_notes(payload)}
  {body}
</div>
<script>{FILTERS_JS}</script>
{watchlist_html("value_chain")}
<script>{JS}
init();
</script>
</body>
</html>
"""
