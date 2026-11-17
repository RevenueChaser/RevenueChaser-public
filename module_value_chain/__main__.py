"""Value Chain CLI.

    python -m RevenueChaser.module_value_chain --fetch [--limit N] [--floor M | --tickers A,B]
    python -m RevenueChaser.module_value_chain --reslice-dry-run \\
        --edgar PATH --docs DIR [--out DIR]
    python -m RevenueChaser.module_value_chain --reslice-apply [--out DIR]
    python -m RevenueChaser.module_value_chain --resolve-rate
    python -m RevenueChaser.module_value_chain --nightly

``--resolve-rate`` reads the stored Relatedness profiles and the spine and prints how many named customers,
suppliers and competitors resolve to a ticker (#410; read only, no network).

``--nightly`` (B, owner 17 Nov 2026; the RC-ValueChain-Sync task, chained on the nightly SEC read) rebuilds the links
from what the SEC layer and the stored Relatedness profiles hold: no download, no model call. The rebuild runs in the
dashboard, the one writer: the task posts ``/run/module_value_chain`` with the ``X-RC-Panel`` header and polls
``/api/job/<id>``, the way the SPX Gamma night task does. Off the layer a Fetch would download from SEC, so it exits
``EXIT_NOT_READY`` and asks for nothing.

``--floor`` (USD millions) and ``--tickers`` choose the names (#108 S0). Without either, the Fetch covers the
whole classification universe. WARNING: the command with a selection makes SEC requests
for those names (``--floor 50`` adds about 900 filers) and rebuilds the Value Chain edges; run it only with the
user's typed words, never under the standing permission.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import httpx

from . import aliases, config, engine, reslice

EXIT_NOT_READY = 3
DASHBOARD = "http://127.0.0.1:8000"     # app.dashboard.main's port
_HEADERS = {"X-RC-Panel": "cli"}        # every non-GET request needs it (CLAUDE.md)
_POLL_S = 10.0
_WAIT_S = 60 * 60                       # under the task's time limit; the job itself keeps running past it


def _nightly() -> int:
    """Queue the board's rebuild on the dashboard and wait for it; one JSON line, exit 0 only when it is done."""
    if not engine._reads_layer():
        print(json.dumps({"status": "not_ready", "reason": "the SEC layer is not the corpus; a Fetch would download"}))
        return EXIT_NOT_READY
    try:
        r = httpx.post(f"{DASHBOARD}/run/module_value_chain", headers=_HEADERS, timeout=60)
        body = r.json()
        if r.status_code != 202:
            out = {"status": "refused", "http": r.status_code, "error": body.get("error")}
        else:
            out, deadline = {"status": "timeout", "job_id": body["job_id"]}, time.monotonic() + _WAIT_S
            while time.monotonic() <= deadline:
                job = httpx.get(f"{DASHBOARD}/api/job/{body['job_id']}", timeout=30).json().get("job") or {}
                if job.get("status") in ("done", "error", "cancelled"):
                    out = {"status": job["status"], "job_id": body["job_id"],
                           "message": job.get("message") or job.get("error")}
                    break
                time.sleep(_POLL_S)
    except httpx.HTTPError as exc:
        out = {"status": "dashboard_down", "error": str(exc)}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["status"] == "done" else 1


def _print_summary(report: dict) -> None:
    """Print the counts and the edge totals only (a whole report could break a cp1252 pipe)."""
    edges = report.get("edges") or {}
    totals = {k: v for k, v in edges.items() if isinstance(v, int)}
    print(json.dumps({"counts": report.get("counts"), "total": report.get("total"),
                      "edges": totals}, ensure_ascii=False))


def _floor(value: str) -> float:
    """A market-cap floor in USD millions; above 0 (the universe at 0 would also keep the names with no cap)."""
    floor = float(value)
    if not floor > 0:
        raise argparse.ArgumentTypeError("--floor is USD millions and must be above 0")
    return floor


def _selection(args) -> list[str] | None:
    """The names ``--floor`` or ``--tickers`` choose; None keeps the default (the universe, no cap floor)."""
    if args.tickers:
        return [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    if args.floor is not None:
        from RevenueChaser.core.universe import BOARD_OPERATING_ONLY, classification_universe
        return classification_universe(args.floor * 1_000_000,
                                       operating_only=BOARD_OPERATING_ONLY["module_value_chain"])
    return None


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Value Chain corpus")
    p.add_argument("--fetch", action="store_true",
                   help="fetch the corpus for the (classification) universe")
    p.add_argument("--limit", type=int, default=None, help="cap tickers")
    p.add_argument("--force", action="store_true",
                   help="re-check recorded misses and re-slice stored filings from their stored "
                        "documents (no download)")
    reslice_pick = p.add_mutually_exclusive_group()
    reslice_pick.add_argument("--reslice-dry-run", action="store_true",
                              help="re-slice the stored corpus offline and report the change (writes nothing)")
    reslice_pick.add_argument("--reslice-apply", action="store_true",
                              help="re-slice stored filings from their stored documents and write them through "
                                   "the slice guard, then rebuild edges (no network; holds the edgar_sync lock)")
    # The chain tables moved to ``boards/value_chain.duckdb`` (#860 stage 1). ``--edgar`` stays as the old
    # spelling of the same argument, so a command line written before the move still runs.
    p.add_argument("--chain-db", "--edgar", dest="chain_db", default=None,
                   help="path to boards/value_chain.duckdb (--reslice-dry-run)")
    p.add_argument("--docs", default=None, help="path to the edgar_docs/ tree (--reslice-dry-run)")
    p.add_argument("--out", default=str(config.OUTPUT_DIR / "research" / "185"),
                   help="report directory (--reslice-dry-run / --reslice-apply)")
    pick = p.add_mutually_exclusive_group()
    warn = " Makes SEC requests for these names and rebuilds the Value Chain edges."
    pick.add_argument("--floor", type=_floor, default=None, metavar="M",
                      help="operating names with a market cap >= M USD millions (default: no floor, Tiers A and B)."
                           + warn)
    pick.add_argument("--tickers", default=None, metavar="A,B",
                      help="exactly these tickers, comma-separated." + warn)
    p.add_argument("--nightly", action="store_true",
                   help="rebuild the links from the SEC layer through the dashboard (the RC-ValueChain-Sync task)")
    p.add_argument("--resolve-rate", action="store_true",
                   help="print the share of the profiles' named companies the spine-name resolver gives a ticker "
                        "(read only)")
    args = p.parse_args(argv)
    if args.nightly:
        return _nightly()
    if args.resolve_rate:
        from RevenueChaser.module_relatedness import store
        from RevenueChaser.rcdata import read
        print(json.dumps(aliases.resolve_rate(store.load_profile_json(), aliases.spine_names(read.identity()))))
        return 0
    # The re-slice commands run before the selection, which (with --floor) would read the live store
    # through rawstore; the apply also refuses the flags that drive a fetch or a selection.
    if args.reslice_apply:
        if args.fetch or args.floor is not None or args.tickers:
            p.error("--reslice-apply cannot be combined with --fetch, --floor or --tickers")
        result = reslice.apply(out_dir=Path(args.out))
        print(json.dumps(result, ensure_ascii=False))
        return 1 if result.get("locked") else 0
    # The dry run reads the store copy it is given and nothing else.
    if args.reslice_dry_run:
        if not (args.chain_db and args.docs):
            p.error("--reslice-dry-run needs --chain-db and --docs")
        report = reslice.dry_run(Path(args.chain_db), Path(args.docs), Path(args.out))
        _print_summary(report)
        return 0
    chosen = _selection(args)
    if chosen == []:      # an empty list would read as "no selection" downstream: the whole universe
        p.error("--floor / --tickers selected no names")

    if args.fetch:
        print(json.dumps(engine.fetch_corpus(tickers=chosen, limit=args.limit), ensure_ascii=False))
    else:
        print("use --fetch")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
