"""One whole build of a RevenueChaser serving kind on a GitHub runner (avo, 17 Nov 2026: slow one-off rebuilds go to a
runner; the output is a DuckDB file the code would have built on homesrv).

    python RevenueChaser/scripts/rc_rebuild.py KIND
        build KIND from the unpacked Parquet with RevenueChaser's own builder; write result.json: the build's checks
        and every table's (row count, checksum)

Runs inside .github/workflows/rc-rebuild.yml with RC_MARKET_DIR / RC_MARKET_RAW_DIR pointed at the unpacked input
bundle (home-server bin/rc-rebuild send).
It is RevenueChaser's ``base.build_kind_many`` itself, never a copy of its rules:
- RC_BUILD_WHOLE=1 (set by the workflow) makes ``dirty.plan`` build the kind whole and still write its manifest, so
  homesrv's next pass sees the Parquet as already built;
- the live file of KIND is in the bundle, so the swap's shrink guard runs against it exactly as on homesrv, and no
  ``allow_shrink`` is ever passed (a prices table may never shrink: avo's standing rule);
- nothing is fetched: no provider is called and no key is needed.
"""
import json
import sys
import time

from RevenueChaser.rcdata import backup, serving
from RevenueChaser.rcdata.build import base


def main(kind: str) -> int:
    members = base.kind_datasets(kind)
    if not members:
        sys.exit(f"unknown kind {kind!r}")
    # The kind's derived dataset (no provider: prices/serving, ownership/serve, ...) leads, as its own request would.
    lead = next((d for d in members if not tuple(d.providers)), members[0])
    ctx = base.RunContext(run_id=base.new_run_id(), dataset=lead.name, trigger="rc-rebuild")
    ctx.as_of = lead.default_as_of()
    t0 = time.monotonic()
    checks = base.build_kind_many(kind, [(lead, ctx)], lead=ctx)
    out = {"kind": kind, "lead": lead.name, "as_of": ctx.as_of.isoformat(), "notes": ctx.notes,
           "build_s": round(time.monotonic() - t0), "checks": checks,
           "tables": backup._table_fingerprints(serving.live_path(kind))}
    json.dump(out, open("result.json", "w"), indent=1, default=str)
    print(json.dumps({k: out[k] for k in ("kind", "lead", "as_of", "build_s", "notes")}, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1]))
