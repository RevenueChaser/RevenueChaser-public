"""Drop the rendered board pages a plain load rebuilds by itself, so none survives a deploy.

``app/dashboard.py``'s ``view()`` serves the stored artifact on a plain ``/view/<mod>`` load and rebuilds it only
on ``?refresh=1``, so after a restart that changed how a board renders every board keeps its pre-deploy page until
someone presses Refresh once (#266 part 2). The cut belongs at start-up, and home-server's
``units/life-rc-dashboard.service`` runs this script as its ``ExecStartPre=``.

**It is not a blanket ``rm .cache/*_latest.html``.** A plain load self-heals only for a board the dashboard can
re-derive from the store with no provider call -- ``_STORE_REFRESHABLE`` in ``app/dashboard.py``. Earnings Radar
is not one of them: it has no Refresh, every run of it is a Fetch, and its ``run_earnings_range`` calls Unusual
Whales (``app/runners.py:294``). Removing its page would turn a working board into the "no data yet" empty state
until someone pressed Fetch, which is the provider call the issue picked this option to avoid. So the set of
artifacts comes from the dashboard itself rather than from a glob, and a board that cannot rebuild itself is kept
and named in the report.

The three files per board are the ones the dashboard's own Refresh drops: the page, the rows the page fetches
(``core/reporting_common.payload_path``) and the v2 door's envelope (``core/v2_envelope.envelope_path``). Nothing
else in the cache root is touched -- not the timestamped archives, the PNGs, the downloaded SEC zips, each
module's ``<module>/<module>_latest.json`` snapshot (``uw_interaction``'s is the last answer of a provider call,
not a re-render) or the dashboard's logs.

    python -m RevenueChaser.scripts.drop_board_artifacts            # report only, removes nothing
    python -m RevenueChaser.scripts.drop_board_artifacts --apply    # remove them
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path


def _dashboard():
    # Imported inside the functions, not at module level: the report-only form of this script, and its tests,
    # should not pay for Flask and the store bindings unless they are needed.
    from RevenueChaser.app import dashboard
    return dashboard


def droppable_boards() -> dict[str, Path]:
    """``{board key: its HTML artifact}`` for every board a plain load rebuilds from the store with no network.

    Both halves come from ``app/dashboard.py`` so there is no second copy of the mapping: ``_STORE_REFRESHABLE``
    says which boards re-derive from the store, and ``_module_file`` gives the artifact of the ones that keep one
    (LEAPS, Watch lists and Hit Rate render in memory and have no file).
    """
    d = _dashboard()
    out = {}
    for board in sorted(d._STORE_REFRESHABLE):
        path = d._module_file(board)
        if path is not None:
            out[board] = Path(path)
    return out


def kept_boards() -> dict[str, Path]:
    """``{board key: its HTML artifact}`` for the boards whose page is deliberately left in place.

    A board with an artifact that is not in ``_STORE_REFRESHABLE`` can only be rebuilt by a Fetch, which costs
    provider calls, so its page outlives a restart.
    """
    d = _dashboard()
    keys = [t["key"] for t in d.TABS if t.get("type") == "tab"]
    out = {}
    for board in keys:
        path = d._module_file(board)
        if path is not None and board not in d._STORE_REFRESHABLE:
            out[board] = Path(path)
    return out


def artifacts_of(html_path) -> list[Path]:
    """The three files a board's page is made of, in the order the dashboard's Refresh drops them."""
    from RevenueChaser.core.reporting_common import payload_path
    from RevenueChaser.core.v2_envelope import envelope_path
    p = Path(html_path)
    return [p, payload_path(p), envelope_path(p)]


def present_artifacts() -> list[Path]:
    """Every droppable artifact that is actually on disk now, sorted."""
    out = []
    for html in droppable_boards().values():
        out.extend(p for p in artifacts_of(html) if p.exists())
    return sorted(out)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--apply", action="store_true", help="actually remove them (default: report only)")
    a = ap.parse_args(argv)

    kept = kept_boards()
    victims = present_artifacts()
    if kept:
        print("kept (no store-only rebuild; a Fetch is a provider call): "
              + ", ".join(f"{b} -> {p.name}" for b, p in sorted(kept.items())))
    if not victims:
        print(f"nothing to drop: no board artifact on disk ({len(droppable_boards())} boards checked)")
        return 0

    print(f"{len(victims)} board artifacts to drop, from {len(droppable_boards())} boards")
    for p in victims:
        print(f"  {p.name}")
    if not a.apply:
        print("report only; pass --apply to remove them")
        return 0

    left = 0
    for p in victims:
        p.unlink(missing_ok=True)
        if p.exists():
            left += 1          # a reader holding the file open; the next start gets it
    print(f"dropped {len(victims) - left}, still present {left}; "
          "the next plain load rebuilds each board from the store with no provider call")
    return 0


if __name__ == "__main__":
    sys.exit(main())
