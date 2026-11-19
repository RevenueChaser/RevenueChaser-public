"""One whole build of a RevenueChaser serving kind on a GitHub runner (avo, 17 Nov 2026: slow one-off rebuilds go to a
runner; the output is a DuckDB file the code would have built on homesrv).

    python runner/scripts/rc_github_rebuild.py KIND [--allow-shrink]
        build KIND from the unpacked Parquet with RevenueChaser's own builder; write result.json: the build's checks
        and every table's (row count, checksum)

Runs inside .github/workflows/rc-github-rebuild.yml with RC_MARKET_DIR / RC_MARKET_RAW_DIR pointed at the unpacked input
bundle (home-server bin/rc-github-rebuild send).
It is RevenueChaser's ``base.build_kind_many`` itself, never a copy of its rules:
- RC_BUILD_WHOLE=1 (set by the workflow) makes ``dirty.plan`` build the kind whole and still write its manifest, so
  homesrv's next pass sees the Parquet as already built;
- the live file of KIND is in the bundle, so the swap's shrink guard runs against it exactly as on homesrv;
  ``allow_shrink`` is passed only when the run asks for it with ``--allow-shrink``, and **never** for ``prices``
  (a prices table may never shrink: avo's standing rule). A kind whose own correction drops rows on purpose needs
  it, or the build spends its hours and then fails at the swap: the ownership rebuild of #935 drops the partial
  first 13F quarter, which takes ``sec13f_periods`` from ~53 rows to ~52 and empties 2013-06-30's ``started`` rows
  out of ``sec13f_filer_breaks``, both over ``serving.MAX_SHRINK`` (#1125, avo's word of 19 Nov 2026). The flag
  relaxes only this kind's own and derived tables (``base.shrink_scope``) and still never lets a table empty;
- nothing is fetched: no provider is called and no key is needed.
"""
import json
import sys
import time

from RevenueChaser.rcdata import backup, serving
from RevenueChaser.rcdata.build import base


# The one kind whose tables may never be narrowed, whatever a run asks for (avo's standing rule; DECISIONS S18).
NEVER_SHRINK = "prices"


def parse_argv(argv: list[str]) -> tuple[str, bool]:
    """``KIND [--allow-shrink]``; anything else exits, so a typo never builds the wrong thing for hours."""
    rest = [a for a in argv if a != "--allow-shrink"]
    if len(rest) != 1 or rest[0].startswith("-"):
        sys.exit(f"usage: rc_github_rebuild.py KIND [--allow-shrink] (got {argv})")
    return rest[0], "--allow-shrink" in argv


def main(kind: str, allow_shrink: bool = False) -> int:
    members = base.kind_datasets(kind)
    if not members:
        sys.exit(f"unknown kind {kind!r}")
    if allow_shrink and kind == NEVER_SHRINK:
        sys.exit(f"refused: --allow-shrink is never passed for {NEVER_SHRINK!r} (its tables are never narrowed)")
    # The kind's derived dataset (no provider: prices/serving, ownership/serve, ...) leads, as its own request would.
    lead = next((d for d in members if not tuple(d.providers)), members[0])
    ctx = base.RunContext(run_id=base.new_run_id(), dataset=lead.name, trigger="rc-github-rebuild")
    ctx.as_of = lead.default_as_of()
    ctx.allow_shrink = allow_shrink
    t0 = time.monotonic()
    checks = base.build_kind_many(kind, [(lead, ctx)], lead=ctx)
    out = {"kind": kind, "lead": lead.name, "as_of": ctx.as_of.isoformat(), "notes": ctx.notes,
           "build_s": round(time.monotonic() - t0), "checks": checks, "allow_shrink": allow_shrink,
           "tables": backup._table_fingerprints(serving.live_path(kind))}
    json.dump(out, open("result.json", "w"), indent=1, default=str)
    print(json.dumps({k: out[k] for k in ("kind", "lead", "as_of", "build_s", "allow_shrink", "notes")},
                     default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main(*parse_argv(sys.argv[1:])))
