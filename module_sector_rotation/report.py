"""Rotation Map Dashboard — RRG-style quadrant HTML with ETF data table."""
from RevenueChaser.core.reporting_common import (help_html, provider_health_html, watch_buttons_html, watchlist_html,
                                                 write_artifact)
from RevenueChaser.core.html_safe import ESC_JS, esc, fill, script_json
import html as _html
from datetime import datetime, date
from pathlib import Path
from typing import Optional
from RevenueChaser.core.config import OUTPUT_DIR
from RevenueChaser.core.gics_map import UNCLASSIFIED
from RevenueChaser.module_sector_rotation.models import ETFRotationSnapshot
from RevenueChaser.core import rotation_reference
from .universe import MACRO_SERIES, GROUP_COLORS, QUADRANT_COLORS
from .theme_focus import coarse_theme_catalog


CSS = """<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d1117;color:#c9d1d9;font-family:'Segoe UI',Consolas,monospace;padding:24px}
.header{margin-bottom:16px;padding-bottom:16px;border-bottom:1px solid #21262d}
.header h1{color:#d2991d;font-size:22px;letter-spacing:1px}
.header .meta{color:#8b949e;font-size:13px;margin-top:4px}
.summary-cards{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:16px}
.sum-card{flex:1;min-width:180px;background:#161b22;border:1px solid #21262d;border-radius:8px;padding:12px}
.sum-card .sc-title{font-size:11px;font-weight:700;letter-spacing:1px;text-transform:uppercase;margin-bottom:8px}
.sum-card .sc-body{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.chip{display:inline-block;padding:2px 8px;border-radius:10px;font-size:9px;font-weight:700;white-space:nowrap}
.chip.et{background:rgba(139,92,246,.15);color:#8B5CF6;border:1px solid #8B5CF6}
.chip.bd{background:rgba(248,113,113,.15);color:#f87171;border:1px solid #f87171}
.chip.more{background:transparent;color:#8b949e;border:1px solid #30363d;cursor:pointer}
.chip.more:hover{color:#c9d1d9;border-color:#58a6ff}
.sum-card .sc-note{margin-top:8px;font-size:11px;color:#8b949e;line-height:1.5}
.sum-card .sc-drawer{display:none;margin-top:6px}
.sum-card .sc-drawer.open{display:flex;flex-wrap:wrap;gap:6px}
.grid{display:flex;gap:24px;flex-wrap:wrap}
.quadrant-panel{flex:1 1 0;min-width:0;max-width:900px;background:#161b22;border:1px solid #21262d;border-radius:8px;padding:16px}
.quadrant-panel h2{color:#c9d1d9;font-size:16px;margin-bottom:14px}
.table-panel{flex:1.25 1 0;min-width:0;overflow-x:auto;background:#161b22;border:1px solid #21262d;border-radius:8px;padding:16px}
.grid>.quadrant-panel,.grid>.table-panel{align-self:flex-start}
@media (max-width:1000px){.grid>.quadrant-panel,.grid>.table-panel{flex-basis:100%;max-width:none}}
.topbar{display:flex;gap:10px;margin-bottom:16px;flex-wrap:wrap;align-items:center}
.topbar .filters{display:flex;gap:10px;flex-wrap:wrap}
.filters button{background:#161b22;color:#8b949e;border:1px solid #21262d;padding:5px 14px;border-radius:12px;cursor:pointer;font-size:12px;transition:all .2s}
.filters button:hover{color:#c9d1d9;border-color:#30363d}
.filters button.active{color:#58a6ff;border-color:#1f6feb;background:#1a1a2e}
table{width:100%;border-collapse:collapse;font-size:12px}
th{text-align:left;padding:9px 6px;color:#c9d1d9;font-size:11px;font-weight:600;letter-spacing:0.3px;border-bottom:2px solid #21262d;position:sticky;top:0;z-index:2}
th.group{font-size:11px;text-transform:uppercase;letter-spacing:1px;text-align:center;border-bottom:1px solid #30363d;padding:7px 4px;position:sticky;top:0;z-index:3}
th.num,td.num{text-align:right;font-family:ui-monospace,'Cascadia Mono',Consolas,'Segoe UI',monospace;font-variant-numeric:tabular-nums}
th.center,td.center{text-align:center}
td{padding:8px 6px;border-bottom:1px solid #161b22;white-space:nowrap;font-size:12px}
tr:hover{background:#161b22}
.ticker{color:#F1F5F9;font-weight:700;white-space:nowrap}
.group{font-size:10px;border-radius:4px;padding:1px 6px;color:#94A3B8}
.by-data{font-size:10px;padding:1px 6px;color:#8b949e}
.pos{color:#34D399}.neg{color:#F87171}.zero{color:#8b949e}
.badge{display:inline-block;padding:2px 8px;border-radius:10px;font-size:9px;font-weight:700}
.bd-L{background:#1a3a1a;color:#3fb950;border:1px solid #238636}
.bd-W{background:#2a2410;color:#d2991d;border:1px solid #9e6a03}
.bd-G{background:#1a1a1a;color:#f85149;border:1px solid #da3633}
.bd-I{background:#1a1a2e;color:#58a6ff;border:1px solid #1f6feb}
/* Group header tones */
.th-g1{background:rgba(88,166,255,0.10)}
.th-g2{background:rgba(210,153,29,0.08)}
.th-g3{background:rgba(139,148,158,0.08)}
.th-g4{background:rgba(163,113,247,0.10)}
.td-g1{background:rgba(88,166,255,0.03)}
.td-g2{background:rgba(210,153,29,0.03)}
.td-g3{background:rgba(139,148,158,0.03)}
.td-g4{background:rgba(163,113,247,0.03)}
.rs-bar{display:inline-block;height:6px;min-width:2px;border-radius:3px}
footer{margin-top:32px;padding-top:12px;border-top:1px solid #21262d;color:#484f58;font-size:11px;text-align:center}
.crosshair-line{stroke:#30363d;stroke-width:1;stroke-dasharray:4,4}
.axis-label{fill:#8b949e;font-size:10px}
.tooltip{position:absolute;background:#21262d;color:#c9d1d9;padding:6px 10px;border-radius:6px;font-size:11px;border:1px solid #30363d;pointer-events:none;display:none;z-index:10}
/* ticker multi-select dropdown and the zoomable svg (the trail page) */
.quadrant-svg{width:100%;height:650px}
.dd{position:relative;display:inline-block}
.dd-btn{background:#161b22;color:#c9d1d9;border:1px solid #30363d;padding:5px 12px;border-radius:12px;cursor:pointer;font-size:12px}
.dd-btn:hover{border-color:#58a6ff}
.dd-menu{position:absolute;top:100%;left:0;margin-top:4px;background:#161b22;border:1px solid #30363d;border-radius:8px;padding:6px;min-width:180px;max-height:320px;overflow-y:auto;z-index:50;display:none}
.dd-menu.open{display:block}
.dd-item{display:flex;align-items:center;gap:6px;padding:3px 6px;font-size:12px;cursor:pointer;border-radius:4px;white-space:nowrap}
.dd-item:hover{background:#21262d}
.dd-item input{margin:0}
.dd-actions{display:flex;gap:6px;padding:4px 6px;border-bottom:1px solid #21262d;margin-bottom:4px}
.dd-actions button{background:transparent;color:#58a6ff;border:0;cursor:pointer;font-size:11px;padding:0}
.theme-wrap{display:inline-flex;align-items:center;gap:6px;margin-left:4px;font-size:12px;color:#8b949e}
.theme-wrap select{background:#161b22;color:#c9d1d9;border:1px solid #30363d;border-radius:12px;padding:5px 10px;font-size:12px;cursor:pointer}
.theme-wrap select:hover{border-color:#58a6ff}
.hold-caret{color:#8b949e;cursor:pointer;font-size:11px;margin-right:2px;user-select:none}
tr.holdings-row td{background:#0b1828;border-bottom:1px solid #30363d}
.holdings-row table th.num,.holdings-row table td.num{text-align:right}
.holdings-row .num{font-variant-numeric:tabular-nums}
.moneyflow-panel{flex:1;min-width:550px;max-width:900px;background:#161b22;border:1px solid #21262d;border-radius:8px;padding:18px}
.moneyflow-panel h2{color:#c9d1d9;font-size:16px;margin:0;cursor:pointer;user-select:none;display:flex;align-items:center;gap:8px}
.moneyflow-panel .mf-toggle{font-size:12px;color:#8b949e;transition:transform .2s}
.moneyflow-panel.collapsed .mf-grid{display:none}
.moneyflow-panel.collapsed .mf-toggle{transform:rotate(-90deg)}
.mf-grid{display:flex;gap:16px;flex-wrap:wrap;margin-top:14px}
.mf-card{flex:1;min-width:240px;background:#0d1117;border:1px solid #21262d;border-radius:8px;padding:12px}
.mf-head{font-size:12px;font-weight:700;letter-spacing:1px;margin-bottom:8px}
.mf-row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid #161b22;font-size:12px}
.mf-row:last-child{border-bottom:0}
.mf-row .mf-name{color:#8b949e;font-size:11px}
.mf-row .mf-score{font-weight:700;font-variant-numeric:tabular-nums}
.mf-pos{color:#34D399}.mf-neg{color:#F87171}
/* the rotation chart (A1, 17 Nov 2026): drawn by RRG_JS; labels scale with --k so a phone keeps them legible */
svg.rrg{width:100%;height:auto;display:block;touch-action:manipulation;user-select:none;-webkit-user-select:none}
.map-controls{display:flex;align-items:center;gap:6px;margin-bottom:10px;flex-wrap:wrap}
.map-controls .lbl{font-size:11px;color:#8b949e;margin:0 4px}
.map-controls .filter-btn{background:#161b22;color:#8b949e;border:1px solid #21262d;min-height:44px;padding:0 14px;border-radius:12px;cursor:pointer;font-size:12px}
.map-controls .zoom-btn{min-width:44px;padding:0 10px;font-size:16px}
.map-controls .filter-btn.active{color:#58a6ff;border-color:#1f6feb;background:#1a1a2e}
.qlabel{font-size:calc(12px*var(--k,1));font-weight:600;letter-spacing:.04em}
.axis{font-size:calc(11px*var(--k,1));fill:#8b949e}
.tick{font-size:calc(10px*var(--k,1));fill:#8b949e}
.dlabel{font-size:calc(11.5px*var(--k,1));font-weight:600;fill:#f0f6fc;paint-order:stroke;stroke:#161b22;stroke-width:3px}
.wlabel{font-size:calc(10px*var(--k,1));fill:#8b949e;paint-order:stroke;stroke:#161b22;stroke-width:3px}
.note{font-size:11px;color:#8b949e;margin-top:10px;line-height:1.6}
.tooltip{position:fixed}
tbody tr.on{background:#1a1a2e;outline:1px solid #1f6feb}
.macro-panel{background:#161b22;border:1px solid #21262d;border-radius:8px;padding:16px;margin-top:24px}
.macro-panel h2{color:#c9d1d9;font-size:16px;margin-bottom:10px}
.macro-table tr.mblock td{color:#8b949e;font-size:10px;font-weight:700;letter-spacing:1px;text-transform:uppercase;padding-top:14px;border-bottom:1px solid #30363d}
.macro-table .msub{display:block;color:#8b949e;font-size:10px}
.macro-table .mspark-cell{width:140px}
.mspark{width:130px;height:24px;display:block}
@media (max-width:760px){
 body{padding:12px}
 .quadrant-panel,.table-panel,.moneyflow-panel{min-width:0;max-width:none;flex-basis:100%}
 .c-1w,.c-rot,.c-price{display:none}
 td{white-space:normal}
 /* The fund table on a phone (avo, 18 Nov 2026): no sideways scroll. Each row is a grid of ticker, quadrant, RS 1M
    and RS 3M, with the name and its data label on a second line under them. */
 .table-panel{padding:8px}
 .table-panel>table>thead>tr:first-child,.table-panel>table>thead>tr>th:nth-child(2){display:none}
 .table-panel>table>thead>tr,.table-panel tr[data-group]{display:grid;grid-template-columns:minmax(0,1fr) 86px 58px 58px}
 .table-panel tr[data-group]{border-bottom:1px solid #21262d}
 .table-panel tr[data-group]>td{border-bottom:0;display:flex;align-items:center;gap:3px}
 .table-panel tr[data-group]>td.center{justify-content:center}
 .table-panel tr[data-group]>td.num{justify-content:flex-end}
 .table-panel tr[data-group]>td.c-1w,.table-panel tr[data-group]>td.c-rot,.table-panel tr[data-group]>td.c-price{display:none}
 .table-panel tr[data-group]>td:nth-child(2){grid-row:2;grid-column:1/-1;padding-top:0}
 .table-panel tr[data-group]>td:nth-child(2) .by-data{display:inline}
 .table-panel tr[data-group]>td:nth-child(2){display:block}
 /* The table and its sections are blocks here, so an expanded row's cell has the panel's width and its own
    overflow-x works. As table boxes the cell took its content's width and widened the panel (seen live: 397 px in
    a 386 px panel, #1077). */
 .table-panel>table,.table-panel>table>thead,.table-panel>table>tbody{display:block}
 .table-panel tr.holdings-row,.table-panel tr.holdings-row>td{display:block;overflow-x:auto}
 .macro-table thead{display:none}
 .macro-table tr.mrow{display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:4px 8px;padding:8px 0;border-bottom:1px solid #21262d}
 .macro-table tr.mrow td{display:block;border:0;padding:0;text-align:left}
 .macro-table tr.mrow td::before{content:attr(data-l);display:block;color:#8b949e;font-size:10px}
 .macro-table tr.mrow td.mname,.macro-table tr.mrow td.mspark-cell{grid-column:1/-1}
 .macro-table tr.mrow td.mname::before{content:none}
 .mspark{width:100%}
 .macro-table tr.mblock{display:block}
 .macro-table tr.mblock td{display:block}
}
</style>"""

JS = """<script>
__ESC_JS__
var ACTIVE_GROUP = 'sector';
var THEME = 'all';
var THEME_ETFS = __THEME_ETFS_JSON__;
var INDUSTRY_ETFS = __INDUSTRY_ETFS_JSON__;  // the industry layer: one ETF per GICS industry group, whatever its own group
function inGroup(t, g) {
    return ACTIVE_GROUP === 'industry' ? INDUSTRY_ETFS.indexOf(t) >= 0 : String(g).trim().toLowerCase() === ACTIVE_GROUP;
}
var HIDDEN = {};  // ticker -> true means hidden (unchecked in picker)
var ROTATION_HOLDINGS = __HOLDINGS_JSON__;  // ticker -> pre-rendered holdings <td> fragment
function filterGroup(g) {
    ACTIVE_GROUP = String(g).trim().toLowerCase();
    document.querySelectorAll('.filter-btn').forEach(function(btn) {
        btn.classList.toggle('active', String(btn.dataset.group).trim().toLowerCase() === ACTIVE_GROUP);
    });
    renderChart();
}
function setTheme(v) {
    THEME = (v == null || v === '') ? 'all' : String(v);
    renderChart();
}
function rowVisible(row) {
    var t = row.dataset.ticker;
    if (HIDDEN[t]) return false;
    // Theme=All: group filter only. Theme set: THEME_ETFS membership (mapped ETF
    // in another group still shown so banks can surface KRE on sector view).
    if (THEME !== 'all') {
        var allowed = THEME_ETFS[THEME] || [];
        return allowed.indexOf(t) >= 0;
    }
    return inGroup(t, row.dataset.group);
}
function renderChart() {
    // map rows only: a nested holdings row has no group and would be hidden by the filter
    document.querySelectorAll('tbody tr[data-group]').forEach(function(row){
        row.style.display = rowVisible(row) ? '' : 'none';
    });
    if (typeof drawRRG === 'function') drawRRG();
}
function toggleHoldings(ticker) {
    var caret = document.getElementById('caret-' + ticker);
    var row = document.querySelector('tbody tr[data-ticker="' + ticker + '"]');
    if (!row) return;
    var next = row.nextElementSibling;
    if (next && next.classList.contains('holdings-row')) {
        // toggle collapse
        var open = next.style.display !== 'none';
        next.style.display = open ? 'none' : '';
        if (caret) caret.textContent = open ? '▸' : '▾';
        return;
    }
    var det = document.createElement('tr');
    det.className = 'holdings-row';
    det.innerHTML = '<td colspan="9" style="color:#8b949e;padding:10px 14px">Loading holdings…</td>';
    row.parentNode.insertBefore(det, row.nextSibling);
    if (caret) caret.textContent = '▾';
    if (ROTATION_HOLDINGS && ROTATION_HOLDINGS[ticker]) {
        det.innerHTML = ROTATION_HOLDINGS[ticker];
        rcWatchSync(det);                       // the fragment's watch-list pairs show the live lists (PR 4)
        return;
    }
    // Try the current route first, then the legacy route (covers servers that
    // predate the /view/module_sector_rotation slug rename).
    var urls = [
        '/view/module_sector_rotation/holdings?ticker=' + encodeURIComponent(ticker),
        '/view/rotation/holdings?ticker=' + encodeURIComponent(ticker)
    ];
    var ui = 0;
    (function tryNext() {
        if (ui >= urls.length) {
            det.innerHTML = '<td colspan="9" style="color:#f85149;padding:10px 14px">Failed to load holdings.</td>';
            return;
        }
        fetch(urls[ui++])
            .then(function(r){ if(!r.ok) throw new Error('HTTP ' + r.status); return r.text(); })
            .then(function(html){ det.innerHTML = html; rcWatchSync(det); })
            .catch(tryNext);
    })();
}
function sortTable(col, el) {
    const tbody = el.closest('table').querySelector('tbody');
    const rows = Array.from(tbody.querySelectorAll('tr'));
    const asc = el.dataset.sort === 'asc';
    rows.sort((a, b) => {
        let av = a.querySelector('td[data-col="' + col + '"]')?.dataset.val;
        let bv = b.querySelector('td[data-col="' + col + '"]')?.dataset.val;
        let am = av == null || av === '', bm = bv == null || bv === '';
        if (am || bm) return am === bm ? 0 : (am ? 1 : -1);   // a missing value sorts last either way
        return asc ? av - bv : bv - av;
    });
    el.dataset.sort = asc ? 'desc' : 'asc';
    rows.forEach(r => tbody.appendChild(r));
}
document.addEventListener('DOMContentLoaded', function(){
    renderChart();
    document.querySelectorAll('tbody tr[data-ticker]').forEach(function(row){
        row.addEventListener('click', function(e){
            if (e.target.closest('.holdings-row') || e.target.closest('a')) return;
            if (!row.querySelector('.hold-caret')) return;  // non-expandable group
            toggleHoldings(row.getAttribute('data-ticker'));
        });
    });
});
function toggleDrawer(el) {
    var card = el.closest('.sum-card');
    var drawer = card ? card.querySelector('.sc-drawer') : null;
    if (!drawer) return;
    drawer.classList.toggle('open');
    el.textContent = drawer.classList.contains('open') ? '− less' : '+' + (drawer.querySelectorAll('.chip').length) + ' more';
}
function toggleMoneyFlow() {
    var p = document.getElementById('mf-panel');
    if (p) p.classList.toggle('collapsed');
}
function renderMoneyFlow() {
    fetch('/api/moneyflow').then(function(r){ return r.json(); }).then(function(d){
        // DF70 / #181 R20: an inflow is a positive score and an outflow a negative one, so a list can hold fewer
        // than 10 rows. The sign test also cleans a leaderboard saved before that rule.
        var ranked = (d.inflows || []).length + (d.outflows || []).length;
        function card(el, rows, sign, none) {
            var html = '';
            (rows || []).forEach(function(x){
                var s = x.flow_score;
                if (s == null || !(s * sign > 0)) return;
                var sc = s > 0 ? 'mf-pos' : 'mf-neg';
                html += '<div class="mf-row"><div><b>' + rcEsc(x.ticker) + '</b> <span class="mf-name">' + rcEsc(x.name) + '</span></div><span class="mf-score ' + sc + '">' + (s>0?'+':'') + s.toFixed(1) + '</span></div>';
            });
            if (!html) html = '<div class="mf-row" style="color:#8b949e">' + (ranked ? none : 'No data yet.') + '</div>';
            el.innerHTML = html;
        }
        var inf = document.getElementById('mf-inflows');
        var outf = document.getElementById('mf-outflows');
        if (inf) card(inf.querySelector('.mf-body'), d.inflows, 1, 'No ETF with a positive score.');
        if (outf) card(outf.querySelector('.mf-body'), d.outflows, -1, 'No ETF with a negative score.');
        var asof = document.getElementById('mf-asof');
        if (asof) asof.textContent = d.generated_at
            ? 'as of ' + String(d.generated_at).replace('T', ' ').slice(0, 16)
            : 'not fetched yet — refreshed after each Rotation Fetch';
        // mf-note begin
        var mfGrid = document.querySelector('#mf-panel .mf-grid');
        if (d.partial && mfGrid) {
            var miss = d.missing || [];
            var note = document.createElement('div');
            note.id = 'mf-note';
            note.style.cssText = 'color:#F59E0B;font-size:12px;margin-top:10px';
            note.textContent = 'Partial leaderboard: ' + miss.length + ' ETF(s) have too few stored daily bars for the window'
                + (miss.length ? ' (' + miss.join(', ') + ')' : '') + ', so the ranking may be incomplete.';
            mfGrid.parentNode.insertBefore(note, mfGrid);
        }
        // mf-note end
    }).catch(function(){});
}
document.addEventListener('DOMContentLoaded', function(){ renderMoneyFlow(); });
</script>"""

def _format_rs(val: Optional[float]) -> str:
    """Signed percent-point RS; a missing value is a dash, never a fake +0.0% (DF67)."""
    if val is None:
        return "—"
    return f"{val:+.1f}%"


def _z_cell(col: str, val: Optional[float]) -> str:
    """An RS-Ratio / RS-Momentum cell (A1): the stored value less 100, shown around 100 as the chart's axes are; a
    missing value is a dash with an empty sort value, never a fake 100."""
    if val is None:
        return f'<td class="num zero td-g3 c-rot" data-col="{col}" data-val="">—</td>'
    return f'<td class="num {_rs_color(val)} td-g3 c-rot" data-col="{col}" data-val="{val:.4f}">{100 + val:.1f}</td>'


def _format_close(ticker: str, close: Optional[float]) -> str:
    """The last close: ``$`` for an exchange-traded fund only. A macro series (``MACRO_SERIES``: a yield, an index
    level, a futures quote) is a plain number (DF68). A missing close is a dash."""
    if close is None:
        return "—"
    return f"{close:.2f}" if ticker in MACRO_SERIES else f"${close:.2f}"


def _ticker_label(t: str) -> str:
    """Return 'TICKER — Name' (or just ticker when no name is known)."""
    name = rotation_reference.rotation_etfs().get(t, {}).get("name", "")
    return f"{t} — {name}" if name else t


def _theme_control_html(catalog: dict[str, list[str]]) -> tuple[str, str]:
    """Theme dropdown markup + THEME_ETFS JSON. Empty catalog → omit control."""
    theme_etfs_json = script_json(catalog)
    if not catalog:
        return "", theme_etfs_json
    opts = ['<option value="all" selected>All themes</option>']
    for label in catalog:
        opts.append(f'<option value="{esc(label)}">{esc(label)}</option>')
    html = (
        '<span class="theme-wrap">Theme '
        f'<select id="theme" onchange="setTheme(this.value)">{"".join(opts)}</select>'
        '</span>'
    )
    return html, theme_etfs_json


def _rows_to_snapshots(rows: list[dict]) -> list[ETFRotationSnapshot]:
    """Convert stored snapshot dict rows into ETFRotationSnapshot objects."""
    snaps = []
    for r in rows:
        s = ETFRotationSnapshot(
            as_of_date=date.fromisoformat(r["as_of_date"]),
            ticker=r["ticker"],
            group_name=r.get("group", ""),
            close_price=r.get("close_price", 0.0),
            rs_1w=r.get("rs_1w"), rs_1m=r.get("rs_1m"), rs_3m=r.get("rs_3m"),
            rs_ratio=r.get("rs_ratio"), rs_momentum=r.get("rs_momentum"),
            rs_ratio_z=r.get("rs_ratio_z"), rs_momentum_z=r.get("rs_momentum_z"),
            rrg_quadrant=r.get("quadrant", ""),
        )
        snaps.append(s)
    return snaps


def _snapshot_fetched_at(as_of: date):
    """Return the snapshot's `generated_at` timestamp (or None)."""
    from .store import load_snapshot
    snap = load_snapshot(as_of)
    if snap and snap.get("generated_at"):
        return snap["generated_at"]
    return None


def _previous_quadrants(as_of: date) -> dict[str, str]:
    """Quadrant per ticker from the most recent snapshot before as_of (for arrows/early-turn)."""
    from .store import load_snapshot, list_snapshot_dates
    dates = list_snapshot_dates()
    if not dates:
        return {}
    prev = None
    for d in dates:
        if d < as_of.isoformat():
            prev = d
        else:
            break
    if not prev:
        return {}
    snap = load_snapshot(date.fromisoformat(prev))
    if not snap:
        return {}
    return {e["ticker"]: e.get("quadrant", "") for e in snap.get("etfs", [])}


def _transition(prev_q: str, curr_q: str) -> bool:
    return bool(prev_q) and bool(curr_q) and prev_q != curr_q


def _previous_momentum(as_of: date, n: int = 2) -> list[dict[str, tuple]]:
    """Prior N snapshots' (rs_ratio_z, rs_momentum_z) per ticker, oldest->newest.

    Used for the early-turn rule: momentum_z > 0 on 2 consecutive snapshots
    while ratio_z < 0 (bottom-fishing signature).
    """
    from .store import load_snapshot, list_snapshot_dates
    dates = list_snapshot_dates()
    if not dates:
        return []
    prior = [d for d in dates if d < as_of.isoformat()][-n:]
    out = []
    for d in prior:
        snap = load_snapshot(date.fromisoformat(d))
        if not snap:
            continue
        row = {}
        for e in snap.get("etfs", []):
            row[e["ticker"]] = (e.get("rs_ratio_z"), e.get("rs_momentum_z"))
        out.append(row)
    return out


def _early_turn_tickers(as_of: date, snapshots: list[ETFRotationSnapshot]) -> set:
    """Tickers the early-turn rule flags: momentum above 100 on the two prior stored snapshots and now, while the
    ratio is still below 100.

    The rule itself is ``early_turn.is_early_turn`` — the one copy, which the score (#597) reads too, so the ``⚡``
    chip and the Brier line can never be two different rules.
    """
    from .early_turn import PRIOR_WEEKS, is_early_turn
    priors = _previous_momentum(as_of, n=PRIOR_WEEKS)
    if len(priors) < PRIOR_WEEKS:
        return set()
    return {s.ticker for s in snapshots
            if is_early_turn(s.rs_ratio_z, s.rs_momentum_z,
                             [p.get(s.ticker, (None, None))[1] for p in priors])}


# Weeks the Early Turn card scores itself on (#597). Read from the PRICES store, not from the stored snapshots:
# the live board file held 3 snapshots when this was measured (homesrv, 20 Nov 2026), so an 8-week horizon could
# judge nothing and the card showed no line at all — the measured score would not have reached the board until
# late December. 104 weeks is one read of bars the map already reads most of, and enough weeks that the horizon
# has run out on a useful number of flags.
SCORE_WEEKS = 104


def _early_turn_score(as_of: date) -> dict:
    """The early-turn flag's score (``early_turn.brier``) on the weeks rebuilt from the prices store, or ``{}``
    when the store cannot answer. Read-only, writes nothing, and never raises into the page."""
    from . import early_turn as et
    try:
        return et.brier(weekly=et.points_from_prices(as_of, weeks=SCORE_WEEKS))
    except Exception:                                   # noqa: BLE001 - no prices store yet: no line on the card
        return {}


def _rs_heat_style(val: float) -> str:
    """Subtle 0.12-opacity background tint for positive/negative values."""
    if val is None:
        return ""
    if val > 0:
        return "background:rgba(52,211,153,0.12);"
    if val < 0:
        return "background:rgba(248,113,113,0.12);"
    return ""


def _rs_color(val: float) -> str:
    if val > 0: return "pos"
    if val < 0: return "neg"
    return "zero"


def _quadrant_badge(q: str) -> str:
    if not q:
        return '<span class="badge" style="color:#8b949e">—</span>'
    abbr = {"LEADING": ("LEADING", "bd-L"), "WEAKENING": ("WEAKENING", "bd-W"),
            "LAGGING": ("LAGGING", "bd-G"), "IMPROVING": ("IMPROVING", "bd-I")}
    label, cls = abbr.get(q, ("?", "bd-I"))
    return f'<span class="badge {cls}">{label}</span>'


# Base axis range (-2..+2 z) shared by the map and trail views; ``_axis_limit`` widens it to the largest |z|.
QUADRANT_BASE_LIMIT = 2.0


def _clamp(v, limit: float) -> float:
    return max(-limit, min(limit, v))


def _axis_limit(values: list[float]) -> float:
    """Dynamic symmetric axis range from data: max(1.0, round(max_abs * 1.15, 1))."""
    if not values:
        return QUADRANT_BASE_LIMIT
    mx = max(abs(v) for v in values)
    return max(1.0, round(mx * 1.15, 1))


def _nice_step(limit: float) -> float:
    """Gridline spacing so the axis has ~4 ticks per side."""
    raw = limit / 4.0
    for s in (0.5, 1.0, 2.0, 5.0, 10.0):
        if s >= raw:
            return s
    return 10.0


def _grid_ticks(limit: float) -> list[float]:
    step = _nice_step(limit)
    n = int(limit / step)
    return [i * step for i in range(-n, n + 1)]


def _label_anchor(ox: float) -> str:
    """SVG text-anchor matching the horizontal side of the offset."""
    if ox < 0:
        return "end"
    if ox > 0:
        return "start"
    return "middle"


def _label_baseline(oy: float) -> str:
    """SVG dominant-baseline so the text extends toward the corner it points to.

    oy < 0 -> label above the dot (text extends up); oy > 0 -> below (down).
    """
    if oy < 0:
        return "text-after-edge"
    if oy > 0:
        return "text-before-edge"
    return "central"


def _quadrant_bias_offset(cx_p: float, cy_p: float, chart_cx: float, chart_cy: float,
                          pad: float) -> tuple[float, float]:
    """Outward diagonal starting offset toward the point's own quadrant corner.

    LEADING (x>=0,y>=0) -> (+pad,+pad); IMPROVING (x<0,y>=0) -> (-pad,+pad);
    LAGGING (x<0,y<0) -> (-pad,-pad); WEAKENING (x>=0,y<0) -> (+pad,-pad).
    """
    dx = pad if cx_p >= chart_cx else -pad
    dy = pad if cy_p >= chart_cy else -pad
    return dx, dy


def _label_box(cx_p: float, cy_p: float, ox: float, oy: float, lw: float, lh: float):
    """Bounding box of a label at (cx_p+ox, cy_p+oy), matching its anchor/baseline."""
    if oy < 0:
        top, bot = cy_p + oy - lh, cy_p + oy
    elif oy > 0:
        top, bot = cy_p + oy, cy_p + oy + lh
    else:
        top, bot = cy_p + oy - lh / 2, cy_p + oy + lh / 2
    if ox < 0:
        return (cx_p + ox - lw, top, cx_p + ox, bot)
    if ox > 0:
        return (cx_p + ox, top, cx_p + ox + lw, bot)
    return (cx_p + ox - lw / 2, top, cx_p + ox + lw / 2, bot)


def _place_label(cx_p: float, cy_p: float, lw: float, lh: float, r: float,
                 placed: list, chart_cx: float, chart_cy: float):
    """Pick a non-overlapping label offset via a quadrant-bias + outward spiral.

    The label first tries its natural quadrant-corner offset (radial bias), then
    spirals outward from the chart center until a collision-free slot is found.
    Returns (ox, oy, anchor, baseline, box).
    """
    import math

    def _collides(box):
        bx1, by1, bx2, by2 = box
        score = 0
        for (ax1, ay1, ax2, ay2) in placed:
            if bx1 < ax2 and ax1 < bx2 and by1 < ay2 and ay1 < by2:
                score += 1
        return score

    # 1) quadrant-bias start (natural outward anchor)
    bx, by = _quadrant_bias_offset(cx_p, cy_p, chart_cx, chart_cy, r + 6)
    bias_box = _label_box(cx_p, cy_p, bx, by, lw, lh)
    if _collides(bias_box) == 0:
        return bx, by, _label_anchor(bx), _label_baseline(by), bias_box

    # 2) outward spiral search (anti-overlap fallback)
    ang_out = math.atan2(cy_p - chart_cy, cx_p - chart_cx)
    best = None
    best_score = -1
    for ring in range(1, 13):
        base = r + 4 + (ring - 1) * 10
        for d in range(8):
            a = ang_out + (d - 3.5) * (math.pi / 8)
            ox = base * math.cos(a)
            oy = base * math.sin(a)
            box = _label_box(cx_p, cy_p, ox, oy, lw, lh)
            score = _collides(box)
            if score == 0:
                return ox, oy, _label_anchor(ox), _label_baseline(oy), box
            if score < best_score or best_score == -1:
                best_score = score
                best = (ox, oy, _label_anchor(ox), _label_baseline(oy), box)
    return best


def _leader_line(r: float, ox: float, oy: float, anchor: str, lw: float, color: str) -> str:
    """Faint line from the dot edge to the label's near edge (when displaced)."""
    import math
    ang = math.atan2(oy, ox)
    dx0, dy0 = r * math.cos(ang), r * math.sin(ang)
    if anchor == "end":
        lx, ly = ox - lw, oy
    elif anchor == "start":
        lx, ly = ox, oy
    else:
        lx, ly = ox - lw / 2, oy
    return f'<line x1="{dx0:.1f}" y1="{dy0:.1f}" x2="{lx:.1f}" y2="{ly:.1f}" stroke="{color}" stroke-width="0.7" opacity="0.3" stroke-dasharray="3,2"/>'


def _velocity_vector(hx: float, hy: float, dx: float, dy: float, color: str) -> str:
    """Arrowhead at the head node pointing in the direction of travel (dx, dy)."""
    import math
    length = math.hypot(dx, dy)
    if length < 1e-6:
        return ""
    # line from just outside the head dot outward a short, fixed visual distance
    ux, uy = dx / length, dy / length
    r0 = TRAIL_MAX_R + 2.0
    r1 = r0 + 10.0
    x1, y1 = hx + r0 * ux, hy + r0 * uy
    x2, y2 = hx + r1 * ux, hy + r1 * uy
    # arrowhead barbs
    barb = 3.0
    bx = -uy * barb
    by = ux * barb
    return (
        f'<g class="velocity-arrow">'
        f'<line x1="{x1:.1f}" y1="{y1:.1f}" x2="{x2:.1f}" y2="{y2:.1f}" stroke="{color}" stroke-width="1.2" opacity="0.9"/>'
        f'<line x1="{x2:.1f}" y1="{y2:.1f}" x2="{x2 - ux * barb + bx:.1f}" y2="{y2 - uy * barb + by:.1f}" stroke="{color}" stroke-width="1.2" opacity="0.9"/>'
        f'<line x1="{x2:.1f}" y1="{y2:.1f}" x2="{x2 - ux * barb - bx:.1f}" y2="{y2 - uy * barb - by:.1f}" stroke="{color}" stroke-width="1.2" opacity="0.9"/>'
        f'</g>'
    )


def _quadrant_backdrop(limit: float, W: int, H: int, margin: int, cx: float, cy: float) -> list[str]:
    """Shared quadrant backdrop: rects, watermark labels, gridlines+tick values, axes."""
    def tx(v): return cx + (v / limit) * (cx - margin)
    def ty(v): return cy - (v / limit) * (cy - margin)
    rows = [
        f'<rect x="{margin}" y="{margin}" width="{cx-margin}" height="{cy-margin}" fill="#0a0a1f" opacity="0.12"/>',
        f'<rect x="{cx}" y="{margin}" width="{cx-margin}" height="{cy-margin}" fill="#0a1a0a" opacity="0.12"/>',
        f'<rect x="{margin}" y="{cy}" width="{cx-margin}" height="{cy-margin}" fill="#1a0a0a" opacity="0.12"/>',
        f'<rect x="{cx}" y="{cy}" width="{cx-margin}" height="{cy-margin}" fill="#1f1a0a" opacity="0.12"/>',
        f'<text x="{tx(limit * 0.55):.1f}" y="{ty(limit * 0.55):.1f}" fill="#3fb950" font-size="18" font-weight="700" text-anchor="middle" opacity="0.4" class="qlabel" data-rx="0.55" data-ry="0.55">LEADING</text>',
        f'<text x="{tx(-limit * 0.55):.1f}" y="{ty(limit * 0.55):.1f}" fill="#58a6ff" font-size="18" font-weight="700" text-anchor="middle" opacity="0.4" class="qlabel" data-rx="-0.55" data-ry="0.55">IMPROVING</text>',
        f'<text x="{tx(-limit * 0.55):.1f}" y="{ty(-limit * 0.55):.1f}" fill="#f85149" font-size="18" font-weight="700" text-anchor="middle" opacity="0.4" class="qlabel" data-rx="-0.55" data-ry="-0.55">LAGGING</text>',
        f'<text x="{tx(limit * 0.55):.1f}" y="{ty(-limit * 0.55):.1f}" fill="#d2991d" font-size="18" font-weight="700" text-anchor="middle" opacity="0.4" class="qlabel" data-rx="0.55" data-ry="-0.55">WEAKENING</text>',
    ]
    for v in _grid_ticks(limit):
        gx = tx(v)
        gy = ty(v)
        rows.append(f'<line x1="{gx:.1f}" y1="{margin}" x2="{gx:.1f}" y2="{H-margin}" class="crosshair-line"/>')
        rows.append(f'<line x1="{margin}" y1="{gy:.1f}" x2="{W-margin}" y2="{gy:.1f}" class="crosshair-line"/>')
        if v != 0:
            lab = f"{v:g}"
            rows.append(f'<text x="{gx:.1f}" y="{cy+14}" fill="#6e7681" font-size="9" text-anchor="middle">{lab}</text>')
            rows.append(f'<text x="{cx+8}" y="{gy:.1f}" fill="#6e7681" font-size="9">{lab}</text>')
    rows.append(f'<line x1="{margin}" y1="{cy}" x2="{W-margin}" y2="{cy}" stroke="#484f58" stroke-width="1.5"/>')
    rows.append(f'<line x1="{cx}" y1="{margin}" x2="{cx}" y2="{H-margin}" stroke="#484f58" stroke-width="1.5"/>')
    rows.append(f'<text x="{W-margin+4}" y="{cy+5}" fill="#8b949e" font-size="12" font-weight="600">RS Ratio (z)</text>')
    rows.append(f'<text x="{cx+5}" y="{margin-4}" fill="#8b949e" font-size="12" font-weight="600">RS Momentum (z)</text>')
    return rows


def _quadrant_watermark_boxes(limit: float, W: int, H: int, margin: int, cx: float, cy: float) -> list:
    """Bounding boxes of the four quadrant watermark labels (obstacles for dot labels)."""
    def tx(v): return cx + (v / limit) * (cx - margin)
    def ty(v): return cy - (v / limit) * (cy - margin)
    labels = {"LEADING": (0.55, 0.55), "IMPROVING": (-0.55, 0.55),
              "LAGGING": (-0.55, -0.55), "WEAKENING": (0.55, -0.55)}
    boxes = []
    for name, (rx, ry) in labels.items():
        x = tx(rx * limit)
        y = ty(ry * limit)
        w = len(name) * 11.0
        boxes.append((x - w / 2, y - 18, x + w / 2, y + 4))
    return boxes


TRAIL_WEEKS = 13        # the longest trail the chips offer; the chart's default is 8


def _rrg_payload(snapshots: list[ETFRotationSnapshot], as_of: date) -> dict:
    """The data the chart draws (A1): per map ETF its point of every completed week in the last ``TRAIL_WEEKS``, from
    the stored snapshots (one per week: the last stored session of each completed week) and ``snapshots`` as the
    newest. A point is ``[ratio, momentum, week-ending day]`` around 100 (``100 + z``: a row stored before A1 carries a
    pooled z there, so a trail through an old week stays on the same axes until the backfill rewrites it).
    ``weeks_in_quadrant`` counts the newest points in the same quadrant."""
    from datetime import timedelta
    from .engine import quadrant_path, week_cut
    from .store import load_range
    try:
        stored = load_range(as_of - timedelta(weeks=TRAIL_WEEKS + 2), as_of)
    except Exception:                                   # noqa: BLE001 - no board file yet: the newest point only
        stored = {}
    by_week: dict[str, dict] = {}
    for day in sorted(stored):
        wk = week_cut(date.fromisoformat(day)).isoformat()
        by_week[wk] = {r["ticker"]: r for r in stored[day]}
    now_wk = week_cut(as_of).isoformat()
    by_week[now_wk] = {s.ticker: {"rs_ratio_z": s.rs_ratio_z, "rs_momentum_z": s.rs_momentum_z} for s in snapshots}
    weeks = sorted(by_week)[-TRAIL_WEEKS:]
    etfs = []
    for s in snapshots:
        if s.ticker in MACRO_SERIES or s.rs_ratio_z is None or s.rs_momentum_z is None:
            continue
        pts = []
        for wk in weeks:
            r = by_week[wk].get(s.ticker) or {}
            rz, mz = r.get("rs_ratio_z"), r.get("rs_momentum_z")
            pts.append(None if rz is None or mz is None else [round(100 + rz, 3), round(100 + mz, 3), wk])
        # the hysteresis band (#597), walked oldest to newest, so the trail's count agrees with the table's quadrant
        quads = [q or None for q in quadrant_path([None if p is None else (p[0], p[1]) for p in pts])]
        held = 0
        for q in reversed(quads):
            if q != quads[-1]:
                break
            held += 1
        etfs.append({"ticker": s.ticker, "name": rotation_reference.rotation_etfs().get(s.ticker, {}).get("name", s.ticker),
                     "group": s.group_name, "quadrant": s.rrg_quadrant, "weeks_in_quadrant": held, "points": pts,
                     "rs_1m": s.rs_1m, "rs_3m": s.rs_3m})
    return {"weeks": weeks, "etfs": etfs}


def _heatmap_html() -> str:
    """#782: the stock heatmap (S&P 500 by default, or one of avo's watch lists), drawn in the page; no data, no
    section."""
    from . import heatmap
    return heatmap.panel_html(heatmap.payload())


def _macro_table_html(as_of: date) -> str:
    """B1: the macro series as their own table under the map, one block per kind (``engine.MACRO_BLOCKS``); each row
    stacks into a card on a phone. Read-only; an empty store gives no section."""
    from .engine import macro_table
    try:
        rows = macro_table(as_of)
    except Exception:                                   # noqa: BLE001 - no market store: no section
        rows = []
    if not rows:
        return ""

    def chg(v, unit):
        if v is None:
            return '<span class="zero">—</span>'
        cls = "pos" if v > 0 else "neg" if v < 0 else "zero"
        return f'<span class="{cls}">{v:+.0f} bp</span>' if unit == "bp" else f'<span class="{cls}">{v:+.1f}%</span>'

    def spark(vals):
        if len(vals) < 2:
            return ""
        lo, hi = min(vals), max(vals)
        pts = " ".join(f"{i / (len(vals) - 1) * 100:.1f},{22 - (v - lo) / ((hi - lo) or 1) * 20:.1f}"
                       for i, v in enumerate(vals))
        return (f'<svg class="mspark" viewBox="0 0 100 24" preserveAspectRatio="none" aria-hidden="true">'
                f'<polyline points="{pts}" fill="none" stroke="#58a6ff" stroke-width="1.5" '
                f'vector-effect="non-scaling-stroke"/></svg>')

    body, block = "", None
    for r in rows:
        if r["block"] != block:
            block = r["block"]
            body += f'<tr class="mblock"><td colspan="7">{esc(block)}</td></tr>'
        last = f'{r["last"]:.2f}%' if r["unit"] == "bp" else f'{r["last"]:.2f}'
        body += (f'<tr class="mrow" data-macro="{esc(r["ticker"])}">'
                 f'<td class="mname" data-l="Series"><b>{esc(r["ticker"])}</b> <span class="mf-name">{esc(r["name"])}</span></td>'
                 f'<td class="num" data-l="Last">{last}<span class="msub">{esc(r["last_date"])}</span></td>'
                 f'<td class="num" data-l="1w">{chg(r["chg_1w"], r["unit"])}</td>'
                 f'<td class="num" data-l="4w">{chg(r["chg_4w"], r["unit"])}</td>'
                 f'<td class="num" data-l="13w">{chg(r["chg_13w"], r["unit"])}</td>'
                 f'<td class="num" data-l="1y pct">{"—" if r["pct_1y"] is None else r["pct_1y"]}</td>'
                 f'<td class="mspark-cell" data-l="65 days">{spark(r["spark"])}</td></tr>')
    return f"""<div class="macro-panel" id="macro-panel">
<h2>Macro backdrop</h2>
<table class="macro-table"><thead><tr><th>Series</th><th class="num">Last</th><th class="num">1w</th><th class="num">4w</th><th class="num">13w</th><th class="num">1y pct</th><th>Last 65 days</th></tr></thead>
<tbody>{body}</tbody></table>
<div class="note">Not on the map: a rate or an index level has no "beating SPY". Rates and credit spreads change in basis points, the rest in percent; 1y pct = where the last value sits in its own last year (100 = the year's high).</div>
</div>"""


RRG_JS = r"""<script>
var RRG = __RRG_JSON__;
var TRAIL = 8, FOCUS = null, HOVER = null;
var VIEW = {z: 1, cx: 100, cy: 100}, GEOM = null;   // zoom factor and centre, in RS units; GEOM = the last draw's scale
function zoomBy(f, cx, cy) {
    var z = Math.min(12, Math.max(1, VIEW.z * f));
    if (cx != null) { VIEW.cx = cx + (VIEW.cx - cx) * VIEW.z / z; VIEW.cy = cy + (VIEW.cy - cy) * VIEW.z / z; }
    VIEW.z = z;
    if (z === 1) { VIEW.cx = 100; VIEW.cy = 100; }
    drawRRG();
}
function zoomReset() { VIEW = {z: 1, cx: 100, cy: 100}; drawRRG(); }
var QCOL = {LEADING:'#3fb950', WEAKENING:'#d2991d', LAGGING:'#f85149', IMPROVING:'#58a6ff'};
function rrgVisible(e) {
    if (HIDDEN[e.ticker]) return false;
    if (THEME !== 'all') return (THEME_ETFS[THEME] || []).indexOf(e.ticker) >= 0;
    return inGroup(e.ticker, e.group);
}
function setTrail(n) {
    TRAIL = n;
    document.querySelectorAll('.trail-btn').forEach(function(b){ b.classList.toggle('active', +b.dataset.n === n); });
    drawRRG();
}
function setFocus(t) { FOCUS = (FOCUS === t) ? null : t; drawRRG(); }
function drawRRG() {
    var svg = document.getElementById('rrg');
    if (!svg) return;
    var rows = RRG.etfs.filter(function(e){ return rrgVisible(e) && e.points.length && e.points[e.points.length-1]; });
    var m = 1.5;
    rows.forEach(function(e){ e.points.slice(-TRAIL).forEach(function(p){ if (p) m = Math.max(m, Math.abs(p[0]-100), Math.abs(p[1]-100)); }); });
    m = Math.ceil(m*2)/2 + 0.25;
    var M = m / VIEW.z;
    var K = Math.max(1, 600 / (svg.clientWidth || 600));
    svg.style.setProperty('--k', K);
    var W = 600, P = Math.round(34*Math.min(K, 1.7)), S = (W-2*P)/(2*M);
    function X(v){ return P + (v-VIEW.cx+M)*S; } function Y(v){ return W-P-(v-VIEW.cy+M)*S; }
    GEOM = {S: S, P: P, M: M};
    function cl(v){ return Math.min(W-P, Math.max(P, v)); }
    var X0 = cl(X(100)), Y0 = cl(Y(100));
    svg.style.touchAction = VIEW.z > 1 ? 'none' : 'manipulation';
    var rs = document.getElementById('zoom-reset'); if (rs) rs.classList.toggle('active', VIEW.z > 1);
    var s = '';
    s += '<defs><clipPath id="rrg-clip"><rect x="'+P+'" y="'+P+'" width="'+(W-2*P)+'" height="'+(W-2*P)+'"/></clipPath></defs>';
    [['LEADING',X0,P,W-P-X0,Y0-P,'Leading','end',W-P-8,P+18],
     ['WEAKENING',X0,Y0,W-P-X0,W-P-Y0,'Weakening','end',W-P-8,W-P-8],
     ['LAGGING',P,Y0,X0-P,W-P-Y0,'Lagging','start',P+8,W-P-8],
     ['IMPROVING',P,P,X0-P,Y0-P,'Improving','start',P+8,P+18]].forEach(function(q){
        if (q[3] <= 0 || q[4] <= 0) return;
        s += '<rect x="'+q[1]+'" y="'+q[2]+'" width="'+q[3]+'" height="'+q[4]+'" fill="'+QCOL[q[0]]+'" opacity=".06"/>'
           + '<text class="qlabel" x="'+q[7]+'" y="'+q[8]+'" text-anchor="'+q[6]+'" fill="'+QCOL[q[0]]+'">'+q[5]+'</text>';
    });
    var st = M > 4 ? 2 : M > 1.6 ? 1 : M > 0.7 ? 0.5 : 0.25;
    for (var v = Math.ceil((VIEW.cx-M)/st)*st; v <= VIEW.cx+M + 1e-9; v += st) {
        s += '<line x1="'+X(v)+'" y1="'+P+'" x2="'+X(v)+'" y2="'+(W-P)+'" stroke="#21262d"/>'
           + '<text class="tick" x="'+X(v)+'" y="'+(W-P+14)+'" text-anchor="middle">'+(+v.toFixed(2))+'</text>';
    }
    for (var u = Math.ceil((VIEW.cy-M)/st)*st; u <= VIEW.cy+M + 1e-9; u += st) {
        s += '<line x1="'+P+'" y1="'+Y(u)+'" x2="'+(W-P)+'" y2="'+Y(u)+'" stroke="#21262d"/>'
           + '<text class="tick" x="'+(P-6)+'" y="'+(Y(u)+3)+'" text-anchor="end">'+(+u.toFixed(2))+'</text>';
    }
    if (X(100) >= P && X(100) <= W-P) s += '<line x1="'+X(100)+'" y1="'+P+'" x2="'+X(100)+'" y2="'+(W-P)+'" stroke="#8b949e"/>';
    if (Y(100) >= P && Y(100) <= W-P) s += '<line x1="'+P+'" y1="'+Y(100)+'" x2="'+(W-P)+'" y2="'+Y(100)+'" stroke="#8b949e"/>';
    s += '<text class="axis" x="'+(W-P)+'" y="'+(W-6)+'" text-anchor="end">RS-Ratio →</text>'
       + '<text class="axis" x="10" y="'+(P-12)+'">↑ RS-Momentum</text>';
    var lit = FOCUS || HOVER;
    s += '<g clip-path="url(#rrg-clip)">';
    rows.sort(function(a,b){ return (a.ticker === lit) - (b.ticker === lit); }).forEach(function(e){
        var pts = e.points.slice(-TRAIL).filter(Boolean).map(function(p){ return [X(p[0]), Y(p[1]), p[2]]; });
        var on = lit === e.ticker, op = (lit && !on) ? 0.15 : 1, c = QCOL[e.quadrant] || '#8b949e';
        for (var i = 1; i < pts.length; i++) {
            var f = 0.25 + 0.75*(i/(pts.length-1));
            s += '<line x1="'+pts[i-1][0]+'" y1="'+pts[i-1][1]+'" x2="'+pts[i][0]+'" y2="'+pts[i][1]+'" stroke="'+(on?'#f0f6fc':c)
               + '" stroke-width="'+(on?2.5:1.6)+'" stroke-linecap="round" opacity="'+((on?1:f*0.8)*op)+'"/>';
        }
        pts.slice(0,-1).forEach(function(p){
            s += '<circle cx="'+p[0]+'" cy="'+p[1]+'" r="'+(on?3.5:2.2)+'" fill="'+(on?'#f0f6fc':c)+'" opacity="'+((on?0.9:0.5)*op)+'"/>';
            if (on) s += '<text class="wlabel" x="'+(p[0]+6)+'" y="'+(p[1]-5)+'">'+rcEsc(String(p[2]).slice(5))+'</text>';
        });
        var h = pts[pts.length-1];
        s += '<g class="rrg-dot" data-ticker="'+rcEsc(e.ticker)+'" style="cursor:pointer" opacity="'+op+'">'
           + '<circle cx="'+h[0]+'" cy="'+h[1]+'" r="22" fill="transparent"/>'
           + '<circle cx="'+h[0]+'" cy="'+h[1]+'" r="'+((on?8:6.5)*Math.sqrt(K))+'" fill="'+c+'" stroke="#161b22" stroke-width="2"/>'
           + '<text class="dlabel" x="'+(h[0]+10*K)+'" y="'+(h[1]+4)+'">'+rcEsc(e.ticker)+'</text></g>';
    });
    s += '</g>';
    svg.innerHTML = s;
    svg.querySelectorAll('g.rrg-dot').forEach(function(g){
        var e = RRG.etfs.filter(function(x){ return x.ticker === g.dataset.ticker; })[0];
        g.addEventListener('click', function(){ setFocus(g.dataset.ticker); });
        g.addEventListener('mousemove', function(ev){ rrgTip(ev, e); });
        g.addEventListener('mouseleave', function(){ document.getElementById('rrg-tip').style.display = 'none'; });
    });
    document.querySelectorAll('tbody tr[data-ticker]').forEach(function(r){ r.classList.toggle('on', r.dataset.ticker === FOCUS); });
    var cnt = document.getElementById('chart-count');
    if (cnt) cnt.textContent = rows.length + ' ETFs';
}
function rrgTip(ev, e) {
    var p = e.points[e.points.length-1], t = document.getElementById('rrg-tip');
    function f(v){ return v == null ? '—' : (v > 0 ? '+' : '') + v.toFixed(1) + '%'; }
    t.innerHTML = '<b>' + rcEsc(e.ticker) + '</b> ' + rcEsc(e.name) + '<br>Ratio ' + p[0].toFixed(1) + ' · Momentum ' + p[1].toFixed(1)
        + '<br>' + rcEsc(e.quadrant.toLowerCase()) + ' for ' + e.weeks_in_quadrant + ' wk · vs SPY 4w ' + f(e.rs_1m) + ' · 12w ' + f(e.rs_3m);
    t.style.display = 'block'; t.style.left = (ev.clientX + 12) + 'px'; t.style.top = (ev.clientY + 12) + 'px';
}
window.addEventListener('resize', function(){ drawRRG(); });
// zoom with the wheel around the cursor; drag to pan (a finger pans only when zoomed in, so the page still scrolls)
function rrgAt(svg, ev) {
    var r = svg.getBoundingClientRect(), k = 600 / (r.width || 600);
    return [VIEW.cx - GEOM.M + ((ev.clientX - r.left)*k - GEOM.P) / GEOM.S, VIEW.cy + GEOM.M - ((ev.clientY - r.top)*k - GEOM.P) / GEOM.S];
}
document.addEventListener('DOMContentLoaded', function(){
    var svg = document.getElementById('rrg'), drag = null;
    if (!svg || !svg.addEventListener) return;
    svg.addEventListener('wheel', function(ev){
        if (!GEOM) return;
        ev.preventDefault();
        var at = rrgAt(svg, ev);
        zoomBy(ev.deltaY < 0 ? 1.25 : 0.8, at[0], at[1]);
    }, {passive: false});
    svg.addEventListener('pointerdown', function(ev){
        if (!GEOM || (ev.pointerType !== 'mouse' && VIEW.z <= 1) || ev.target.closest('g.rrg-dot')) return;
        drag = {x: ev.clientX, y: ev.clientY, cx: VIEW.cx, cy: VIEW.cy, k: 600 / (svg.getBoundingClientRect().width || 600)};
        ev.preventDefault(); svg.setPointerCapture(ev.pointerId);
    });
    svg.addEventListener('pointermove', function(ev){
        if (!drag) return;
        VIEW.cx = drag.cx - (ev.clientX - drag.x) * drag.k / GEOM.S;
        VIEW.cy = drag.cy + (ev.clientY - drag.y) * drag.k / GEOM.S;
        drawRRG();
    });
    svg.addEventListener('pointerup', function(){ drag = null; });
    svg.addEventListener('pointercancel', function(){ drag = null; });
    svg.addEventListener('dblclick', function(){ zoomReset(); });
});
document.addEventListener('DOMContentLoaded', function(){
    document.querySelectorAll('tbody tr[data-ticker]').forEach(function(row){
        row.addEventListener('mouseenter', function(){ HOVER = row.dataset.ticker; drawRRG(); });
        row.addEventListener('mouseleave', function(){ HOVER = null; drawRRG(); });
        row.addEventListener('click', function(e){
            if (e.target.closest('.holdings-row') || e.target.closest('a') || e.target.closest('button')) return;
            setFocus(row.dataset.ticker);
        });
    });
});
</script>"""


def export_rotation_dashboard(snapshots: list[ETFRotationSnapshot], filename: str = None,
                              uw=None, benchmark: str = "SPY",
                              holdings: dict[str, list[dict]] | None = None,
                              sector_holdings: dict[str, list[dict]] | None = None,
                              provider_health: dict | None = None) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = OUTPUT_DIR / (filename or f"rotation/rotation_map_{ts}.html")

    # Stats — the sectors' quadrant counts (Card 1 in the metric strip)
    quad_counts = {"LEADING": 0, "WEAKENING": 0, "LAGGING": 0, "IMPROVING": 0}
    for s in snapshots:
        if s.group_name == "sector" and s.rrg_quadrant in quad_counts:
            quad_counts[s.rrg_quadrant] += 1

    # previous-day quadrant map (for arrows / early-turn). The newest date shown (DF66): a range Fetch renders each
    # ticker's newest stored row, so the rows can carry different dates.
    as_of = max(s.as_of_date for s in snapshots) if snapshots else date.today()
    fetched_at = _snapshot_fetched_at(as_of) or (snapshots[0].retrieved_at if snapshots else None)
    prev_quadrants = _previous_quadrants(as_of)
    group_of = {s.ticker: s.group_name for s in snapshots}
    core_groups = ("sector",)
    transitions = [s.ticker for s in snapshots
                   if _transition(prev_quadrants.get(s.ticker, ""), s.rrg_quadrant)]
    breakdowns = [s.ticker for s in snapshots
                  if s.group_name in core_groups
                  and s.rrg_quadrant in ("LAGGING", "WEAKENING")
                  and prev_quadrants.get(s.ticker, "") not in (s.rrg_quadrant, "")
                  and s.ticker in transitions]
    early_turn = {t for t in _early_turn_tickers(as_of, snapshots)
                  if group_of.get(t, "") in core_groups}
    # How the rule has actually done on the stored weeks (#597): shown on the card, so the chip is never read as a
    # claim nobody checked.
    from .early_turn import caption as _et_caption
    early_turn_caption = _et_caption(_early_turn_score(as_of))

    # Filters (no "All" — default to sector; groups only)
    filters = ''
    groups_seen = set()
    for s in snapshots:
        if s.group_name not in groups_seen:
            groups_seen.add(s.group_name)
            color = GROUP_COLORS.get(s.group_name, "#8b949e")
            active = ' active' if s.group_name == 'sector' else ''
            filters += f'<button class="filter-btn{active}" data-group="{esc(s.group_name)}" onclick="filterGroup(this.dataset.group)" style="border-left:3px solid {color}">{esc(s.group_name)}</button>'
    if "industry" not in groups_seen and any(s.ticker in rotation_reference.industry_map_etfs() for s in snapshots):
        # the layer is drawn from rows of other groups too (SMH, XLE), so it has a button whenever one of them is here
        filters += f'<button class="filter-btn" data-group="industry" onclick="filterGroup(this.dataset.group)" style="border-left:3px solid {GROUP_COLORS["industry"]}">industry</button>'

    theme_catalog = coarse_theme_catalog()
    theme_html, theme_etfs_json = _theme_control_html(theme_catalog)

    # Sort: Leading first, then Improving, Weakening, Lagging
    order = {"LEADING": 0, "IMPROVING": 1, "WEAKENING": 2, "LAGGING": 3}
    # A missing momentum z sorts last within its quadrant, never as 0.
    snapshots_sorted = sorted(snapshots, key=lambda s: (order.get(s.rrg_quadrant, 9), s.rs_momentum_z is None,
                                                        -(s.rs_momentum_z or 0)))

    # Table. Under avo's hand-written name, what the fund is by its holdings (``etf_class``), so the two are never
    # taken for each other (avo's B, 18 Nov 2026); a fund with no label (a macro series, no spine yet) shows none.
    from RevenueChaser.module_watchlists.board import class_labels
    data_labels = class_labels([s.ticker for s in snapshots_sorted if s.ticker not in MACRO_SERIES])
    rows = ""
    for s in snapshots_sorted:
        info = rotation_reference.rotation_etfs().get(s.ticker, {})
        color = GROUP_COLORS.get(s.group_name, "#8b949e")
        r1c = _rs_color(s.rs_1w or 0); r2c = _rs_color(s.rs_1m or 0); r3c = _rs_color(s.rs_3m or 0)
        et_badge = '<span class="badge" style="background:rgba(139,92,246,.15);color:#8B5CF6;border:1px solid #8B5CF6">⚡</span> ' if s.ticker in early_turn else ''

        rows += f'<tr data-group="{esc(s.group_name)}" data-ticker="{esc(s.ticker)}">'
        caret = f'<span class="hold-caret" id="caret-{esc(s.ticker)}">▸</span> ' if s.group_name in ("sector", "theme") else ''
        # The watch-list pair (PR 4) for a fund; a macro series (a yield, an index level) is no name to watch.
        pair = "" if s.ticker in MACRO_SERIES else watch_buttons_html(s.ticker)
        rows += f'<td class="ticker td-g1">{pair}{caret}{et_badge}{esc(s.ticker)}</td>'
        data_label = data_labels.get(s.ticker)
        by_data = f'<div class="by-data" title="From the fund\'s holdings">{esc(data_label)}</div>' if data_label else ''
        rows += f'<td class="td-g1"><span class="group" style="color:{color}">{esc(info.get("name", s.ticker))}</span>{by_data}</td>'
        rows += f'<td class="td-g1 center">{_quadrant_badge(s.rrg_quadrant)}</td>'
        rows += f'<td class="num {r1c} td-g2 c-1w" style="{_rs_heat_style(s.rs_1w)}" data-col="rs_1w" data-val="{"" if s.rs_1w is None else s.rs_1w}">{_format_rs(s.rs_1w)}</td>'
        rows += f'<td class="num {r2c} td-g2" style="{_rs_heat_style(s.rs_1m)}" data-col="rs_1m" data-val="{"" if s.rs_1m is None else s.rs_1m}">{_format_rs(s.rs_1m)}</td>'
        rows += f'<td class="num {r3c} td-g2" style="{_rs_heat_style(s.rs_3m)}" data-col="rs_3m" data-val="{"" if s.rs_3m is None else s.rs_3m}">{_format_rs(s.rs_3m)}</td>'
        rows += _z_cell("rs_ratio_z", s.rs_ratio_z)
        rows += _z_cell("rs_momentum_z", s.rs_momentum_z)
        rows += f'<td class="num td-g1 c-price" data-col="close">{_format_close(s.ticker, s.close_price)}</td>'
        rows += f'</tr>'

    # ── 3-card metric strip ──
    # Card 1: global quadrant counts
    counts_chips = "".join(
        f'<span class="badge" style="background:{QUADRANT_COLORS.get(k,"#8b949e")}22;color:{QUADRANT_COLORS.get(k,"#8b949e")};border:1px solid {QUADRANT_COLORS.get(k,"#8b949e")}44">{k}: {v}</span>'
        for k, v in quad_counts.items()
    )

    def _chips_card(title, items, cls, note: str = ""):
        items = list(items)
        top = items[:3]
        rest = items[3:]
        chips = "".join(f'<span class="chip {cls}">{esc(_ticker_label(t))}</span>' for t in top)
        drawer = ""
        more = ""
        if rest:
            more = f'<span class="chip more" onclick="toggleDrawer(this)">+{len(rest)} more</span>'
            drawer_chips = "".join(f'<span class="chip {cls}">{esc(_ticker_label(t))}</span>' for t in rest)
            drawer = f'<div class="sc-drawer">{drawer_chips}</div>'
        body = f'<div class="sc-body">{chips}{more}</div>{drawer}'
        if not top:
            body = '<div class="sc-body" style="color:#8b949e">None</div>'
        if note:
            body += f'<div class="sc-note">{esc(note)}</div>'
        return f'<div class="sum-card"><div class="sc-title">{title}</div>{body}</div>'

    summary_cards = (
        f'<div class="summary-cards">'
        f'<div class="sum-card"><div class="sc-title">Sector Counts</div><div class="sc-body">{counts_chips}</div></div>'
        f'{_chips_card("⚡ Early Turn", sorted(early_turn), "et", note=early_turn_caption)}'
        f'{_chips_card("⚠️ Breakdown", breakdowns, "bd")}'
        f'</div>'
    )

    fetched_html = ""
    if fetched_at:
        try:
            fetched_s = fetched_at[:16].replace("T", " ")
        except TypeError:
            fetched_s = fetched_at.isoformat(timespec="minutes").replace("T", " ")
        fetched_html = f' | fetched {fetched_s}'

    # Self-contained holdings: pre-render each row's fragment so clicking it
    # shows holdings without a live server round-trip. Sector rows get the
    # sector -> industry tree; theme rows keep their ETF top-10. The trees go
    # last, so an ETF top-10 can never overwrite a sector's tree (ROT-4).
    fragments: dict[str, str] = {}
    if holdings:
        fragments.update({t: render_holdings_fragment(rows)
                          for t, rows in holdings.items()})
    if sector_holdings:
        fragments.update({t: render_industry_fragment(tree)
                          for t, tree in sector_holdings.items()})
    js = fill(JS, {"__HOLDINGS_JSON__": script_json(fragments),
                   "__THEME_ETFS_JSON__": theme_etfs_json,
                   "__INDUSTRY_ETFS_JSON__": script_json(list(rotation_reference.industry_map_etfs())),
                   "__ESC_JS__": ESC_JS})
    help_block = help_html(
        "A relative rotation map of sector and theme ETFs against the benchmark. Each dot's position "
        "combines <b>relative strength</b> (is it beating the benchmark?) with its <b>momentum</b> (is "
        "that getting better?), which places it in one of four quadrants: Leading, Weakening, Lagging, "
        "Improving. ETFs usually move around the map clockwise. <b>Fetch</b> computes the map from the stored daily "
        "prices and fund holdings (no provider call) and stores a snapshot. <b>Refresh</b> redraws the map from the newest stored snapshot with no network call.")
    html = f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1.0"><title>RevenueChaser — Rotation Map</title>{CSS}</head><body>
<div class="header"><h1>ROTATION MAP — Sector &amp; Theme</h1><div class="meta">{as_of.isoformat()}{fetched_html} | {len(snapshots)} ETFs | vs {benchmark}, total return, completed weeks</div></div>
{provider_health_html(provider_health)}
<div class="tooltip" id="rrg-tip"></div>
{help_block}

{summary_cards}

<div class="topbar"><span class="filters">{filters}</span>{theme_html}</div>

<div class="grid">
<div class="quadrant-panel">
<div class="map-controls"><span class="lbl">Trail</span><button class="filter-btn trail-btn" data-n="4" onclick="setTrail(4)">4w</button><button class="filter-btn trail-btn active" data-n="8" onclick="setTrail(8)">8w</button><button class="filter-btn trail-btn" data-n="13" onclick="setTrail(13)">13w</button><span class="lbl">Zoom</span><button class="filter-btn zoom-btn" onclick="zoomBy(1.5)" aria-label="Zoom in">+</button><button class="filter-btn zoom-btn" onclick="zoomBy(1/1.5)" aria-label="Zoom out">−</button><button class="filter-btn" id="zoom-reset" onclick="zoomReset()">Reset</button><span class="lbl" id="chart-count"></span></div>
<svg class="rrg" id="rrg" viewBox="0 0 600 600" role="img" aria-label="Relative rotation graph: each ETF against its own history vs {benchmark}"></svg>
<div class="note">Each dot is the last completed week; the line is its path over the weeks before (faint = older). Right of 100 = stronger than {benchmark} against its own 14-week trend, above 100 = that strength is rising. ETFs usually turn clockwise. Tap a dot or a row to follow one path.</div>
<div class="note"><b style="color:#c9d1d9">How it is computed:</b> total-return weekly closes vs {benchmark}, completed weeks only. RS-Ratio = 100 + how far the ETF/{benchmark} line sits above its own 14-week average, in units of its last year's spread; RS-Momentum = 100 + the 4-week change of RS-Ratio, in the same units. Each ETF is measured against its own history, so adding or removing an ETF never moves another's dot.<br>
<b>RS 1W / 1M / 3M</b> = the ETF's return over 1 / 4 / 12 weeks minus {benchmark}'s (percentage points). <span style="color:#8B5CF6">⚡ Early turn</span> = momentum above 100 on the two prior stored snapshots while ratio is below 100; the card says how often that was followed by Leading over the last two years of weeks, against how often any ETF left of 100 got there.<br>
<b>Quadrant</b> = the 100/100 cross with a hysteresis band: a dot keeps its quadrant until it crosses 100 by more than the band, so one sitting on an axis does not flip every week.</div>
</div>

<div class="table-panel">
<table><thead>
<tr>
<th class="group th-g1" colspan="3">Identity</th>
<th class="group th-g2" colspan="3">Return vs {benchmark}</th>
<th class="group th-g3 c-rot" colspan="2">Rotation</th>
<th class="group th-g1 c-price" colspan="1">Price</th>
</tr><tr>
<th class="th-g1">Ticker</th><th class="th-g1">Name</th><th class="th-g1 center">Quadrant</th>
<th class="th-g2 num c-1w">RS 1W</th><th class="th-g2 num">RS 1M</th><th class="th-g2 num">RS 3M</th>
<th class="th-g3 num c-rot">RS-Ratio</th><th class="th-g3 num c-rot">RS-Mom</th>
<th class="th-g1 num c-price">Price</th>
</tr></thead><tbody>{rows}</tbody></table>
</div></div>

{_heatmap_html()}

{_macro_table_html(as_of)}

<div class="grid">
<div class="moneyflow-panel" id="mf-panel">
<h2 onclick="toggleMoneyFlow()">Money Flow — Top Inflows / Outflows (21d) <span class="mf-toggle">▾</span> <span id="mf-asof" style="font-size:11px;font-weight:400;color:#8b949e"></span></h2>
<div class="mf-grid">
  <div class="mf-card" id="mf-inflows"><div class="mf-head" style="color:#34D399">Top Inflows</div><div class="mf-body">Loading…</div></div>
  <div class="mf-card" id="mf-outflows"><div class="mf-head" style="color:#F87171">Top Outflows</div><div class="mf-body">Loading…</div></div>
</div>
<div style="font-size:11px;color:#8b949e;margin-top:10px;line-height:1.6">
<b style="color:#c9d1d9">What the score means</b> — a 21-day rolling "Net Directional Dollar Flow" score in the range ≈ −100 to +100.<br>
On each day: <b>up-day</b> dollar volume (Close × Volume) counts positive, <b>down-day</b> counts negative.<br>
<b>Score = (Σ up-day $Vol − Σ down-day $Vol) ÷ Σ total $Vol × 100</b> — i.e. the net share of traded dollars that pushed price in the winning direction.<br>
<b>+52.6</b> ≈ 76.3% of traded dollars were up-day flow (net of down-day selling) over the last 21 trading days; <b>−52.6</b> would mean the opposite.<br>
A high positive score = persistent net buying pressure relative to the fund's own turnover (not an absolute dollar amount).
</div>

</div>
</div>

<footer>RevenueChaser v1 — Rotation Engine — stored prices &mdash; {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}</footer>
{RRG_JS.replace('__RRG_JSON__', script_json(_rrg_payload(snapshots, as_of)))}
{watchlist_html("sector_rotation")}
{js}</body></html>"""

    path.parent.mkdir(parents=True, exist_ok=True)
    write_artifact(path, html)
    return path


def export_rotation_from_store(as_of: date, filename: str = None) -> Path:
    """Render a stored daily snapshot (no API calls)."""
    from .store import load_snapshot
    snap = load_snapshot(as_of)
    if snap is None:
        return None
    snapshots = _rows_to_snapshots(snap.get("etfs", []))
    if not snapshots:
        return None
    return export_rotation_dashboard(snapshots, filename=filename)


def export_rotation_trail(start: date, end: date, filename: str = None) -> Path:
    """Render an RRG time-trail: every ETF, one dot per (sampled) week in range.

    Weekly sampling: keep the last snapshot of each ISO week (Wednesdays once
    backfilled). Newest week = full-size dot, older weeks decay in size/opacity.
    """
    from .store import load_range
    series = load_range(start, end)
    days = sorted(series)
    if not days:
        path = OUTPUT_DIR / (filename or "sector_rotation_trail.html")
        path.parent.mkdir(parents=True, exist_ok=True)
        write_artifact(path, _trail_html(start, end, [], {}))
        return path
    sampled = _weekly_sample(days)
    path = OUTPUT_DIR / (filename or "sector_rotation_trail.html")
    path.parent.mkdir(parents=True, exist_ok=True)
    write_artifact(path, _trail_html(start, end, sampled, series))
    return path


def _weekly_sample(days: list[str]) -> list[str]:
    """Keep the last snapshot of each ISO week (and always the newest overall)."""
    if not days:
        return []
    from datetime import date as _date
    last_of_week = {}
    order = []
    for d in days:
        dt = _date.fromisoformat(d)
        key = dt.isocalendar()[:2]  # (year, week)
        last_of_week[key] = d
        if key not in order:
            order.append(key)
    sampled = [last_of_week[k] for k in order]
    if sampled[-1] != days[-1]:
        sampled.append(days[-1])
    return sampled


def _week_label(d: str) -> str:
    """ISO week number label, e.g. 'W07 2026'."""
    try:
        dt = date.fromisoformat(d)
        iso = dt.isocalendar()
        return f"W{iso[1]:02d} {iso[0]}"
    except (ValueError, TypeError):
        return d


# trail dot decay (exponential): newest week full size, older weeks shrink
TRAIL_MAX_R = 6.0
TRAIL_DECAY = 0.55
TRAIL_FLOOR_R = 1.2


def _trail_html(start: date, end: date, sampled: list[str], series: dict[str, list[dict]]) -> str:
    W, H = 700, 580
    margin = 40
    cx, cy = W // 2, H // 2 + 10

    # collect tickers + their group (for the filter)
    tickers = set()
    all_z = []
    for d in sampled:
        for e in series.get(d, []):
            tickers.add(e["ticker"])
            if e.get("rs_ratio_z") is not None and e.get("rs_momentum_z") is not None:
                all_z.extend([e["rs_ratio_z"], e["rs_momentum_z"]])
    group_of = {t: rotation_reference.rotation_etfs().get(t, {}).get("group", "") for t in tickers}
    limit = _axis_limit(all_z)

    def tx(v): return cx + (v / limit) * (cx - margin)
    def ty(v): return cy - (v / limit) * (cy - margin)

    # filter buttons (no All — sector default, groups only)
    filters = ''
    for g in sorted(set(group_of.values())):
        color = GROUP_COLORS.get(g, "#8b949e")
        active = ' active' if g == 'sector' else ''
        filters += f'<button class="filter-btn{active}" data-group="{esc(g)}" onclick="filterTrail(this.dataset.group)" style="border-left:3px solid {color}">{esc(g)}</button>'

    theme_catalog = coarse_theme_catalog()
    theme_html, theme_etfs_json = _theme_control_html(theme_catalog)

    svg_rows = [f'<svg viewBox="0 0 {W} {H}" class="quadrant-svg" data-base-limit="{limit}" xmlns="http://www.w3.org/2000/svg" style="background:#0d1117">',
                '<g id="trail-layer">']
    svg_rows += _quadrant_backdrop(limit, W, H, margin, cx, cy)

    if not sampled:
        svg_rows.append(f'<text x="{cx}" y="{cy}" fill="#8b949e" text-anchor="middle" font-size="13">No stored snapshots in range</text>')
    else:
        # age index: 0 = newest (last sampled day), increasing into the past
        age = {d: len(sampled) - 1 - i for i, d in enumerate(sampled)}
        # precompute per-ticker trail geometry
        trails = []
        for ticker in sorted(tickers):
            pts = []
            for d in sampled:
                for e in series.get(d, []):
                    if e["ticker"] == ticker and e.get("rs_ratio_z") is not None and e.get("rs_momentum_z") is not None:
                        rz = _clamp(e["rs_ratio_z"], limit)
                        mz = _clamp(e["rs_momentum_z"], limit)
                        pts.append((tx(rz), ty(mz), d, e))
            if not pts:
                continue
            grp = group_of.get(ticker, "")
            final_q = pts[-1][3].get("quadrant", "")
            color = QUADRANT_COLORS.get(final_q, "#8b949e")
            name = rotation_reference.rotation_etfs().get(ticker, {}).get("name", "")
            trails.append((ticker, grp, color, name, pts, pts[-1][0], pts[-1][1]))

        # place labels with anti-overlap (newest-dot radius = TRAIL_MAX_R)
        placed = _quadrant_watermark_boxes(limit, W, H, margin, cx, cy)
        label_placements = {}
        for ticker, grp, color, name, pts, nx, ny in trails:
            label = name or ticker
            lw = min(len(label) * 4.2, 120)
            ox, oy, anchor, baseline, box = _place_label(nx, ny, lw, 12, TRAIL_MAX_R, placed, cx, cy)
            placed.append(box)
            label_placements[ticker] = (ox, oy, anchor, baseline, lw)

        for ticker, grp, color, name, pts, nx, ny in trails:
            svg_rows.append(f'<g class="trail-etf" data-group="{esc(grp)}" data-ticker="{esc(ticker)}" data-name="{esc(name)}">')
            if len(pts) >= 2:
                d_path = _catmull_rom_path([(x, y) for x, y, _, _ in pts])
                svg_rows.append(f'<path d="{d_path}" fill="none" stroke="{color}" stroke-width="1" opacity="0.2"/>')
            for x, y, d, e in pts:
                n = age[d]
                r = max(TRAIL_FLOOR_R, TRAIL_MAX_R * (TRAIL_DECAY ** n))
                op = max(0.15, 0.9 * (TRAIL_DECAY ** n))
                is_newest = n == 0
                wk = _week_label(d)
                ratio = e.get("rs_ratio")
                momentum = e.get("rs_momentum")
                rs1w = e.get("rs_1w"); rs1m = e.get("rs_1m"); rs3m = e.get("rs_3m")
                tip = (f"{esc(ticker)} — {esc(d)} ({esc(wk)}) — {esc(e.get('quadrant',''))}"
                       f"\nRS Ratio: {ratio:+.2f} | RS Momentum: {momentum:+.2f}"
                       f"\nRatio Z: {e['rs_ratio_z']:+.2f} | Momentum Z: {e['rs_momentum_z']:+.2f}"
                       f"\nRS 1W: {_format_rs(rs1w)} | 1M: {_format_rs(rs1m)} | 3M: {_format_rs(rs3m)}")
                svg_rows.append(
                    f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{r:.2f}" fill="{color}" opacity="{op:.2f}">'
                    f'<title>{tip}</title></circle>')
            # newest-dot label (relative to the newest dot, via its own translate group)
            ox, oy, anchor, baseline, lw = label_placements[ticker]
            trail_label = name or ticker
            svg_rows.append(f'<g transform="translate({nx:.1f},{ny:.1f})">')
            if (ox, oy) != (0, -(TRAIL_MAX_R + 4)):
                svg_rows.append(_leader_line(TRAIL_MAX_R, ox, oy, anchor, lw, color))
            svg_rows.append(
                f'<text x="{ox:.0f}" y="{oy:.0f}" text-anchor="{anchor}" dominant-baseline="{baseline}" fill="{color}" font-size="8" font-weight="600" '
                f'stroke="#0d1117" stroke-width="2" style="paint-order:stroke">{esc(trail_label)}</text>')
            svg_rows.append('</g>')
            # velocity vector: arrowhead from T-1 -> T0 direction at the head node
            if len(pts) >= 2:
                px0, py0 = pts[-2][0], pts[-2][1]  # previous point (T-1)
                dx, dy = nx - px0, ny - py0
                svg_rows.append(_velocity_vector(nx, ny, dx, dy, color))
            svg_rows.append('</g>')
    svg_rows.append('</g>')
    svg_rows.append('</svg>')

    svg = "\n".join(svg_rows)
    w0 = _week_label(sampled[0]) if sampled else ""
    w1 = _week_label(sampled[-1]) if sampled else ""
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><title>Rotation Trail</title>{CSS}</head><body>
<div class="header"><h1>ROTATION TRAIL — All ETFs</h1><div class="meta">{w0} → {w1} | {len(sampled)} weeks (weekly) | newest = big dot, older dots decay exponentially</div></div>
<div class="quadrant-panel" style="max-width:760px">
<div class="filters" style="margin-bottom:10px">{filters}{theme_html} <span style="margin-left:auto;display:inline-flex;gap:6px;align-items:center"><div class="dd" id="dd"><button class="dd-btn" onclick="toggleDd()">Show tickers ▾</button><div class="dd-menu" id="dd-menu"></div></div><button class="filter-btn" onclick="setZoom(ZOOM*1.25)">+</button><button class="filter-btn" onclick="setZoom(ZOOM/1.25)">−</button><button class="filter-btn" onclick="resetView()">Reset</button><span style="font-size:11px;color:#8b949e" id="zoom-label">1.0x</span></span></div>
{svg}
</div>
<footer>Rotation trail — each ETF against its own history (A1), stored weekly snapshots</footer>
<div style="font-size:11px;color:#8b949e;max-width:760px;margin:0 auto 20px;line-height:1.6">
<b style="color:#c9d1d9">Trail legend:</b> each line traces one symbol's (RS Ratio Z, RS Momentum Z) path across the selected weeks — the trail direction is your rotational momentum over time.<br>
Newest week = largest dot (head node); older dots shrink exponentially. The <b>arrowhead at the head node</b> points in the direction of travel from the previous week (clockwise = improving rotation, counter-clockwise = deteriorating).<br>
Hover a trail to isolate it (others dim to 15%); hover a dot for its full RS breakdown. Yield symbols: the inversion is not applied, so a rising yield reads as positive RS.
</div>
<script>
{ESC_JS}
var ACTIVE_GROUP = 'sector';
var THEME = 'all';
var THEME_ETFS = {theme_etfs_json};
var HIDDEN = {{}};
var ZOOM = 1.0;
var PAN_X = 0, PAN_Y = 0;
function filterTrail(g){{
  ACTIVE_GROUP = String(g).trim().toLowerCase();
  document.querySelectorAll('.filter-btn').forEach(function(b){{
    b.classList.toggle('active', String(b.dataset.group).trim().toLowerCase() === ACTIVE_GROUP);
  }});
  buildPicker(); renderTrail();
}}
function setTheme(v){{ THEME = (v == null || v === '') ? 'all' : String(v); renderTrail(); }}
function setZoom(z){{ ZOOM = Math.max(0.5, Math.min(4.0, z)); document.getElementById('zoom-label').textContent = ZOOM.toFixed(1)+'x'; renderTrail(); }}
function resetView(){{ ZOOM = 1.0; PAN_X = 0; PAN_Y = 0; document.getElementById('zoom-label').textContent = '1.0x'; renderTrail(); }}
function trailVisible(grp){{
  var t = grp.dataset.ticker;
  if (HIDDEN[t]) return false;
  if (THEME !== 'all') {{
    var allowed = THEME_ETFS[THEME] || [];
    return allowed.indexOf(t) >= 0;
  }}
  return String(grp.dataset.group).trim().toLowerCase() === ACTIVE_GROUP;
}}
function renderTrail(){{
  var layer = document.getElementById('trail-layer');
  if(layer) layer.setAttribute('transform', 'translate(' + PAN_X + ',' + PAN_Y + ') scale(' + ZOOM + ')');
  document.querySelectorAll('.trail-etf').forEach(function(grp){{
    grp.style.display = trailVisible(grp) ? '' : 'none';
  }});
}}
function svgPoint(svg, clientX, clientY){{
  var pt = svg.createSVGPoint(); pt.x = clientX; pt.y = clientY;
  return pt.matrixTransform(svg.getScreenCTM().inverse());
}}
function wheelZoom(e){{
  e.preventDefault();
  var svg = document.querySelector('.quadrant-svg');
  var p = svgPoint(svg, e.clientX, e.clientY);
  var factor = e.deltaY < 0 ? 1.1 : 1/1.1;
  var nz = Math.max(0.5, Math.min(4.0, ZOOM * factor));
  // keep the point under the cursor fixed: P' = p - (p - PAN) * (nz/ZOOM)
  PAN_X = p.x - (p.x - PAN_X) * (nz / ZOOM);
  PAN_Y = p.y - (p.y - PAN_Y) * (nz / ZOOM);
  ZOOM = nz;
  document.getElementById('zoom-label').textContent = ZOOM.toFixed(1)+'x';
  renderTrail();
}}
var DRAG = null;
function startDrag(e){{ DRAG = {{x: e.clientX, y: e.clientY, px: PAN_X, py: PAN_Y}}; }}
function moveDrag(e){{
  if(!DRAG) return;
  var svg = document.querySelector('.quadrant-svg');
  var p = svgPoint(svg, e.clientX, e.clientY);
  var s = svgPoint(svg, DRAG.x, DRAG.y);
  PAN_X = DRAG.px + (p.x - s.x);
  PAN_Y = DRAG.py + (p.y - s.y);
  renderTrail();
}}
function endDrag(){{ DRAG = null; }}
function buildPicker(){{
  var menu = document.getElementById('dd-menu'); if(!menu) return;
  var items = []; var seen = {{}};
  document.querySelectorAll('.trail-etf').forEach(function(g){{
    if(String(g.dataset.group).trim().toLowerCase() === ACTIVE_GROUP && !seen[g.dataset.ticker]){{
      seen[g.dataset.ticker]=1; items.push({{t:g.dataset.ticker, name:g.dataset.name||''}});
    }}
  }});
  items.sort(function(a,b){{ return a.t < b.t ? -1 : 1; }});
  var html = '<div class="dd-actions"><button onclick="selAll()">All</button><button onclick="selNone()">None</button></div>';
  items.forEach(function(it){{
    var label = it.t + (it.name ? ' — ' + it.name : '');
    var chk = HIDDEN[it.t] ? '' : ' checked';
    html += '<label class="dd-item"><input type="checkbox" data-t="'+rcEsc(it.t)+'"'+chk+' onchange="toggleTicker(this)">'+rcEsc(label)+'</label>';
  }});
  menu.innerHTML = html;
}}
function toggleTicker(cb){{ var t=cb.getAttribute('data-t'); if(cb.checked) delete HIDDEN[t]; else HIDDEN[t]=1; renderTrail(); }}
function selAll(){{ document.querySelectorAll('.trail-etf').forEach(function(g){{ if(String(g.dataset.group).trim().toLowerCase()===ACTIVE_GROUP) delete HIDDEN[g.dataset.ticker]; }}); buildPicker(); renderTrail(); }}
function selNone(){{ document.querySelectorAll('.trail-etf').forEach(function(g){{ if(String(g.dataset.group).trim().toLowerCase()===ACTIVE_GROUP) HIDDEN[g.dataset.ticker]=1; }}); buildPicker(); renderTrail(); }}
function toggleDd(){{ var m=document.getElementById('dd-menu'); if(m) m.classList.toggle('open'); }}
document.addEventListener('click', function(e){{ var dd=document.getElementById('dd'); if(dd && !dd.contains(e.target)){{ var m=document.getElementById('dd-menu'); if(m) m.classList.remove('open'); }} }});
function focusTrail(ticker, on){{
  document.querySelectorAll('.trail-etf').forEach(function(g){{
    if(g.dataset.ticker !== ticker) g.style.opacity = on ? '0.15' : '';
    else g.style.opacity = '1';
  }});
}}
document.addEventListener('DOMContentLoaded', function(){{
  buildPicker(); renderTrail();
  var svg = document.querySelector('.quadrant-svg');
  svg.addEventListener('wheel', wheelZoom, {{ passive: false }});
  svg.addEventListener('mousedown', startDrag);
  window.addEventListener('mousemove', moveDrag);
  window.addEventListener('mouseup', endDrag);
  document.querySelectorAll('.trail-etf').forEach(function(g){{
    g.addEventListener('mouseenter', function(){{ focusTrail(g.dataset.ticker, true); }});
    g.addEventListener('mouseleave', function(){{ focusTrail(g.dataset.ticker, false); }});
  }});
}});
</script>
</body></html>"""


def _catmull_rom_path(coords: list[tuple[float, float]]) -> str:
    """Catmull-Rom -> cubic bezier smooth path."""
    if len(coords) < 2:
        return ""
    pts = [coords[0]] + coords + [coords[-1]]
    d = f"M {coords[0][0]:.1f},{coords[0][1]:.1f}"
    for i in range(len(coords) - 1):
        p0, p1, p2, p3 = pts[i], pts[i + 1], pts[i + 2], pts[i + 3]
        c1x = p1[0] + (p2[0] - p0[0]) / 6
        c1y = p1[1] + (p2[1] - p0[1]) / 6
        c2x = p2[0] - (p3[0] - p1[0]) / 6
        c2y = p2[1] - (p3[1] - p1[1]) / 6
        d += f" C {c1x:.1f},{c1y:.1f} {c2x:.1f},{c2y:.1f} {p2[0]:.1f},{p2[1]:.1f}"
    return d


def _rs_color2(val):
    if val is None:
        return "zero"
    if val > 0:
        return "pos"
    if val < 0:
        return "neg"
    return "zero"


def render_holdings_fragment(rows: list[dict]) -> str:
    """HTML fragment for an expandable ETF-holdings detail row (inject via JS)."""
    if not rows:
        return '<td colspan="11" style="color:#8b949e;padding:10px 14px">No holdings data available for this ETF.</td>'
    def _pct(v):
        return "—" if v is None else f"{v:+.1f}%"

    def _rs_cell(v):
        if v is None:
            return '<td class="num" style="color:#8b949e">—</td>'
        return f'<td class="num {_rs_color2(v)}" style="{_rs_heat_style(v)}">{_pct(v)}</td>'

    body = ""
    total_w = 0.0
    for r in rows:
        w = r.get("weight") or 0
        total_w += w
        close = r.get("close")
        tick = _html.escape(str(r.get("ticker") or ""), quote=True)
        name = _html.escape(str(r.get("name") or ""))
        body += (
            f'<tr data-ticker="{tick}">'
            f'<td><span style="white-space:nowrap">{watch_buttons_html(r.get("ticker"))}<b>{tick}</b></span> '
            f'<span style="color:#8b949e;font-size:10px">{name}</span></td>'
            f'<td class="num">{w:.2f}%</td>'
            f'{_rs_cell(r.get("rs_1w"))}{_rs_cell(r.get("rs_1m"))}{_rs_cell(r.get("rs_3m"))}'
            f'<td class="num">{"—" if close is None else f"${close:.2f}"}</td>'
            f'</tr>'
        )
    inner = (
        f'<div style="padding:10px 14px"><div style="color:#c9d1d9;font-size:12px;font-weight:600;margin-bottom:6px">Top holdings — RS vs SPY</div>'
        f'<table style="font-size:11px"><thead><tr>'
        f'<th>Ticker</th><th class="num">Weight ({total_w:.1f}%)</th>'
        f'<th class="num">RS 5D</th><th class="num">RS 21D</th><th class="num">RS 63D</th><th class="num">Price</th>'
        f'</tr></thead><tbody>{body}</tbody></table></div>'
    )
    return f'<td colspan="11">{inner}</td>'


def render_industry_fragment(tree: list[dict]) -> str:
    """Detail row for a sector: industry → members.

    ``tree`` is ``sector_industry_tree()[sector]`` — a list of industries, each
    with its cap-weighted members. Sector rows use this instead of the ETF
    top-10 so the map reflects the real composition of the sector in the
    shared universe.
    """
    if not tree:
        return ('<td colspan="11" style="color:#8b949e;padding:10px 14px">'
                'No industry holdings yet — refresh the shared universe first.</td>')
    body = ""
    for ind in tree:
        name = _html.escape(ind.get("industry") or UNCLASSIFIED)
        for i, h in enumerate(ind.get("holdings") or []):
            label = f'<b style="color:#c9d1d9">{name}</b>' if i == 0 else ""
            body += (
                f'<tr><td>{label}</td>'
                f'<td style="white-space:nowrap">{watch_buttons_html(h.get("ticker"))}<b>{_html.escape(h.get("ticker") or "")}</b></td>'
                f'<td><span style="color:#8b949e;font-size:10px">{_html.escape(h.get("name") or "")}</span></td>'
                f'<td class="num">{h.get("weight", 0):.2f}%</td></tr>'
            )
    inner = (
        '<div style="padding:10px 14px">'
        '<div style="color:#c9d1d9;font-size:12px;font-weight:600;margin-bottom:4px">'
        'Industry holdings — cap-weighted</div>'
        '<table style="font-size:11px"><thead><tr>'
        '<th>Industry</th><th>Ticker</th><th>Name</th><th class="num">Weight</th>'
        f'</tr></thead><tbody>{body}</tbody></table></div>'
    )
    return f'<td colspan="11">{inner}</td>'
