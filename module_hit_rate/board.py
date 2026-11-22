"""The Hit Rate board (#25): did each screener's frozen picks work, against what the same day's universe did.

Read-only and rendered in memory on every load, like LEAPS: it reads ``forecast_ledger`` (the frozen picks),
``forecast_outcomes`` (each pick's MFE per horizon) and ``forecast_baselines`` (the whole universe on the same
freeze dates), all in the ``forecast`` store; it fetches nothing and writes nothing. The readability gate, the
dirty list and the 90-day dedupe are ``core/hit_rate.py`` (HR-2): below 30 closed records over 3 freeze dates a
board shows its counts and no rate.

The baseline is the universe's share at the same MFE level over the freeze dates the board's counted records
come from. shortcut: the matched-volatility decile is not shown yet (its rows exist, ``vol_decile_*``); add it
once a board's rate is readable.
"""
from __future__ import annotations

from revenuechaser.core import baselines, hit_rate, outcomes, rawstore
from revenuechaser.core.html_safe import esc
from revenuechaser.core.reporting_common import THEME_CSS, THEME_JS, help_html

TITLE = "Hit Rate"
DB = "forecast"
LEVELS = [name for name, _ in baselines.GE]

_PICKS_SQL = """
    SELECT l.source, l.subject, l.forecast_date, l.model_version, o.horizon_days, o.status, o.mfe
    FROM forecast_ledger l JOIN forecast_outcomes o
      ON o.source = l.source AND o.forecast_date = l.forecast_date AND o.subject = l.subject
     AND o.target_type = l.target_type AND o.target_date = l.target_date
    WHERE l.target_type = ?"""
_BASE_SQL = """SELECT forecast_date, horizon_days, n, ge20, ge10, ge5 FROM forecast_baselines
               WHERE basis = ? AND status = ?"""


def _baseline(base: list[dict], horizon: int, days: set) -> dict:
    rows = [b for b in base if b["horizon_days"] == horizon and b["forecast_date"] in days]
    n = sum(b["n"] or 0 for b in rows)
    return {name: (sum(b[name] or 0 for b in rows) / n if n else None) for name in LEVELS}


def build(picks: list[dict], base: list[dict]) -> dict:
    """The page's data from the joined pick rows and the universe baseline rows (pure; the tests drive it)."""
    out = []
    for horizon in outcomes.HORIZONS:
        rows = [r for r in picks if r["horizon_days"] == horizon]
        lines = hit_rate.summary(rows)
        for line in lines:
            days = {hit_rate._day(r["forecast_date"]) for r in hit_rate.dedupe(rows)
                    if (r["source"], r.get("model_version")) == (line["source"], line["model_version"])
                    and r.get("status") == outcomes.CLOSED}
            line["universe"] = _baseline(base, horizon, days) if line["readable"] else None
        out.append({"horizon": horizon, "lines": lines})
    return {"horizons": out, "picks": len({(r["source"], r["subject"], r["forecast_date"]) for r in picks})}


def payload() -> dict:
    picks = rawstore.query(_PICKS_SQL, ["pick"], db=DB)
    base = rawstore.query(_BASE_SQL, [baselines.UNIVERSE, outcomes.CLOSED], db=DB)
    for b in base:
        b["forecast_date"] = hit_rate._day(b["forecast_date"])
    return build(picks, base)


def _pct(v) -> str:
    return "–" if v is None else f"{v * 100:.0f}%"


def _card(line: dict) -> str:
    head = (f'<div class="hr-head"><b>{esc(line["source"])}</b>'
            f'<span class="hr-ver">model {esc(line["model_version"] or "–")}</span></div>')
    counts = (f'<div class="hr-counts">{line["records"]} closed records · {line["dates"]} freeze dates · '
              f'{line["open"]} still open</div>')
    if line["readable"]:
        uni = line["universe"] or {}
        cells = "".join(
            f'<div class="hr-cell"><span class="k">MFE ≥ {name[2:]}%</span><b>{_pct(line[name])}</b>'
            f'<span class="k">universe {_pct(uni.get(name))}</span></div>' for name in LEVELS)
        body = f'<div class="hr-cells">{cells}</div>'
    else:
        body = (f'<div class="hr-wait">Not readable yet: {hit_rate.MIN_RECORDS} closed records over '
                f'{hit_rate.MIN_DATES} freeze dates are needed.</div>')
    dirty = line["dirty"]
    listed = "".join(f'<li>{esc(d["subject"])} · {esc(d["forecast_date"])} · {esc(d["status"])}</li>'
                     for d in dirty[:50])
    more = f'<li>and {len(dirty) - 50} more</li>' if len(dirty) > 50 else ""
    dirty_html = (f'<details class="hr-dirty"><summary>{len(dirty)} record(s) left out (no bars or an '
                  f'unrecorded split)</summary><ul>{listed}{more}</ul></details>' if dirty else "")
    return f'<div class="hr-card">{head}{counts}{body}{dirty_html}</div>'


def render_html(data: dict) -> str:
    sections = []
    for h in data["horizons"]:
        cards = "".join(_card(line) for line in h["lines"]) or '<div class="hr-wait">No frozen picks yet.</div>'
        sections.append(f'<section><h2>{h["horizon"]} calendar days</h2>{cards}</section>')
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{TITLE}</title><script>{THEME_JS}</script><style>{THEME_CSS}{_CSS}</style></head>
<body><main class="hr">
<header><h1>{TITLE}</h1><span class="sub">Each screener's frozen picks, scored forward on the highest price
after the next open (MFE), against the whole universe on the same freeze dates. {data["picks"]} picks frozen.</span>
</header>
{_HELP}
{"".join(sections)}
</main></body></html>"""


_HELP = help_html(
    "Each screener (Swing, Asymmetric Growth, Fundamentals) freezes its picks when its <b>Fetch</b> runs. Every "
    "night the outcomes are scored: the highest price within 30 and 90 calendar days after the next open (MFE), "
    "and the same for the whole universe on the same freeze dates. A board's rate shows once it has "
    f"{hit_rate.MIN_RECORDS} closed records over {hit_rate.MIN_DATES} freeze dates; a name picked again within "
    f"{hit_rate.DEDUPE_DAYS} days counts once, and versions of a board's rules are never pooled. This tab has no "
    "Fetch of its own; <b>Refresh</b> re-reads the stored outcomes. Issue #25.")

_CSS = """
.hr{max-width:960px;margin:0 auto;padding:16px}
.hr h1{margin:0 0 4px}.hr .sub{color:var(--muted);font-size:13px;display:block;margin-bottom:16px}
.hr h2{font-size:15px;margin:20px 0 8px}
.hr-card{background:var(--card);border:1px solid var(--border);border-radius:8px;padding:12px;margin-bottom:10px}
.hr-head{display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap}
.hr-ver,.hr-counts,.k{color:var(--muted);font-size:12px}
.hr-cells{display:grid;grid-template-columns:repeat(auto-fit,minmax(120px,1fr));gap:8px;margin-top:8px}
.hr-cell{display:flex;flex-direction:column;gap:2px}.hr-cell b{font-size:20px}
.hr-wait{color:var(--amber);font-size:13px;margin-top:8px}
.hr-dirty{margin-top:8px;font-size:12px}.hr-dirty summary{min-height:44px;display:flex;align-items:center;cursor:pointer}
"""
