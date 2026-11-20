"""The Settings / Database part "Serving builds" (#446 step 8B): how each serving kind's last build was made.

``rcdata.build.state`` reads it from the live files; this module only draws it, inside the ``#needs`` frame and
palette (``static/needs.css``) like :mod:`freshness_tab`, so the part carries no palette of its own. One row per
serving kind, the kinds that were built whole first, because that is the row worth a look.

Three things the wording has to keep honest:

- The mode is the **last** build's, not the next one's (``rcdata.build.state``'s own docstring says why), so the
  part says "last build" in every place a reader could take it for a setting.
- A file that does not carry a table yet (an audit that has never run, a build from before the manifest) leaves
  its cell **empty**. It never reads as zero, because zero audited keys and no audit at all are different answers.
- ``prices`` holds its whole build for a person (#446 step 8): the row says so with a ``by hand`` chip, since
  otherwise a reader who sees ``whole`` as its last build would wait for an hourly pass that will not come.

Every string is English (avo, 19 Nov 2026: a board shows no Turkish), every value goes through ``esc``, and the
table turns into stacked cards under 760 px rather than scrolling sideways.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from RevenueChaser.core.html_safe import esc

#: avo's clock (CLAUDE.md: Europe/Amsterdam).
LOCAL = ZoneInfo("Europe/Amsterdam")

#: mode -> (chip text, chip class of needs.css, sort order: what to look at first)
MODES = {
    "fresh": ("whole", "st-stale", 0),
    "live": ("live copy", "st-fresh", 2),
    None: ("not recorded", "st-missing", 3),
}
#: The part's own styles; the frame, the chips and the colours come from ``needs.css``.
BUILD_CSS = """
/* #446 step 8B: the Serving builds part. One grid on the table, so a row never sizes its own cells. */
#needs #build-state table{width:100%;border-collapse:collapse;table-layout:fixed;font-size:13.5px}
#needs #build-state th,#needs #build-state td{padding:8px 10px;border-top:1px solid var(--line);
  vertical-align:top;font-variant-numeric:tabular-nums}
#needs #build-state th{text-align:center;color:var(--mut);font-size:12px;font-weight:700;border-top:0;
  white-space:nowrap}
/* The leftmost cell is left-aligned, the middle ones centred, the rightmost right-aligned (avo 13 Nov 2026). */
#needs #build-state th:first-child,#needs #build-state td:first-child{text-align:left}
#needs #build-state th:last-child,#needs #build-state td:last-child{text-align:right}
#needs #build-state td:not(:first-child):not(:last-child){text-align:center}
#needs #build-state .bs-kind{font-weight:700}
#needs #build-state .bs-det{display:block;color:var(--mut);font-size:12px;margin-top:2px;overflow-wrap:anywhere}
#needs #build-state .bs-none{color:var(--mut)}
#needs #build-state .bs-chips{display:block;margin-top:4px}
#needs #build-state .bs-chips .st{margin-right:4px}
@media (max-width:760px){
  /* Phone: one column, full-width cards, every cell on its own line with its header beside it. */
  #needs #build-state thead{display:none}
  #needs #build-state table,#needs #build-state tbody,#needs #build-state tr,#needs #build-state td{display:block}
  #needs #build-state tr{background:var(--card-2);border:1px solid var(--line);border-radius:10px;
    padding:8px 10px;margin:0 0 10px}
  #needs #build-state td{border-top:0;padding:4px 0;text-align:left!important}
  #needs #build-state td:not(.bs-first)::before{content:attr(data-label) " ";color:var(--mut);font-size:12px}
}
"""

#: The columns, in order: (header, whether it is the row's name cell).
COLUMNS = ("Kind", "Last build", "Parquet files", "Last audit round", "Keys waiting")


def collect() -> dict:
    """``{"kinds": [...]}``: one row per serving kind, read from the live files (read-only)."""
    from RevenueChaser.rcdata.build import state
    return {"kinds": state.all_kinds()}


def _at(ts) -> str:
    """``20 Nov 01:12`` in Amsterdam from epoch seconds; ``—`` when there is none."""
    if ts is None:
        return "—"
    try:
        d = datetime.fromtimestamp(float(ts), timezone.utc).astimezone(LOCAL)
    except (TypeError, ValueError, OverflowError, OSError):
        return "—"
    return f"{d.day} {d:%b %H:%M}"


def _num(value) -> str:
    """``30,906,005``; an empty cell when the file does not carry the table, never a ``0``."""
    if value is None:
        return '<span class="bs-none">—</span>'
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return esc(str(value))


def _chip(text: str, cls: str) -> str:
    return f'<span class="st {cls}">{esc(text)}</span>'


def _mode_cell(row: dict) -> str:
    if not row.get("built"):
        return (f'{_chip("nothing built yet", "st-missing")}'
                f'<span class="bs-det">{esc(", ".join(row.get("datasets") or []) or "no dataset")}</span>')
    mode = row.get("mode")
    text, cls, _ = MODES.get(mode, (str(mode), "st-missing", 3))
    det = _at(row.get("built_at"))
    if row.get("build_id"):
        det += f' · {row["build_id"]}'
    return f'{_chip(text, cls)}<span class="bs-det">{esc(det)}</span>'


def _flags(row: dict) -> str:
    """The chips that say how the **next** build is made, which the mode cannot say."""
    out = []
    if not row.get("incremental"):
        out.append(_chip("whole every run", "st-stale"))
    if row.get("by_hand"):
        out.append(_chip("by hand", "st-missing"))
    return f'<span class="bs-chips">{"".join(out)}</span>' if out else ""


def _audit_cell(row: dict) -> str:
    a = row.get("audit") or {}
    if not a or a.get("checked_at") is None:
        return '<span class="bs-none">—</span><span class="bs-det">no audit round yet</span>'
    det = f'{a.get("keys", 0):,} key(s) checked · {a.get("differs", 0):,} differ'
    return f'{esc(_at(a.get("checked_at")))}<span class="bs-det">{esc(det)}</span>'


def _row(row: dict) -> str:
    if row.get("error"):
        return (f'<tr><td class="bs-first" data-label="Kind"><span class="bs-kind">{esc(str(row.get("kind")))}</span>'
                f'</td><td data-label="Last build" colspan="4">'
                f'{_chip("could not be read", "st-unreadable")}'
                f'<span class="bs-det">{esc(str(row["error"]))}</span></td></tr>')
    cells = [
        f'<td class="bs-first" data-label="Kind"><span class="bs-kind">{esc(str(row.get("kind")))}</span>'
        f'{_flags(row)}</td>',
        f'<td data-label="Last build">{_mode_cell(row)}</td>',
        f'<td data-label="Parquet files">{_num(row.get("parquet_files"))}</td>',
        f'<td data-label="Last audit round">{_audit_cell(row)}</td>',
        f'<td data-label="Keys waiting">{_num(row.get("audit_dirty"))}</td>',
    ]
    return "<tr>" + "".join(cells) + "</tr>"


def _order(kinds: list[dict]) -> list[dict]:
    """The kinds worth a look first: built whole, then unreadable, then carried over; each group by name."""
    def key(r: dict):
        if r.get("error"):
            return (1, str(r.get("kind")))
        if not r.get("built"):
            return (3, str(r.get("kind")))
        return (MODES.get(r.get("mode"), ("", "", 3))[2], str(r.get("kind")))
    return sorted(kinds, key=key)


def section(data: dict | None = None) -> str:
    """The part's HTML. ``data`` is :func:`collect`'s answer; ``None`` reads it now."""
    data = collect() if data is None else data
    head = ('<section class="part" id="build-state" aria-labelledby="build-state-h">'
            '<h2 id="build-state-h">Serving builds</h2>'
            '<p class="sub">How each served DuckDB file\'s <b>last</b> build was made: on a <b>live copy</b> '
            '(only what changed was rebuilt) or <b>whole</b> (the Parquet tree read from the start). It is the last '
            'build, not a setting: a kind whose build code changed since then is built whole next time. '
            '<b>by hand</b> means the hourly pass does not start that kind\'s whole build — press Fetch or run it '
            'from the server. <b>Keys waiting</b> are the keys an audit found a difference for, which the next '
            'build rebuilds. An empty cell means the file does not carry that table yet, not zero. '
            'Times are Amsterdam.</p>')
    if data.get("error"):
        return head + f'<p class="warn">Could not be read: {esc(str(data["error"]))}</p></section>'
    kinds = data.get("kinds") or []
    if not kinds:
        return head + '<p class="empty">No serving kind is registered.</p></section>'
    thead = "".join(f"<th>{esc(c)}</th>" for c in COLUMNS)
    body = "".join(_row(r) for r in _order(kinds))
    return (head + f'<table><thead><tr>{thead}</tr></thead><tbody>{body}</tbody></table></section>')
