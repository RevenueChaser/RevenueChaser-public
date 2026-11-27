"""Print the provider inventory, read from the code itself (never from a note).

A hand-written provider list rots: `rcdata/needs/catalog.py` changed twice in the 90 days to 27 Nov 2026, and a
note written on 22 Nov already missed four providers (`fed`, `federalregister`, `proshares`, `tradingview`) and
still named one that had gone (`vanguard`). So the list is generated:

    python scripts/providers_report.py              # markdown table
    python scripts/providers_report.py --json       # the same as JSON

What it reads, all by parsing, nothing executed and no provider called:

* ``rcdata/needs/catalog.py`` -- every ``Need(...)``'s first argument and its ``providers=`` tuple (AST).
* ``rcdata/build/**/*.py`` -- each builder's ``NAME`` (``<provider>/<job>``) and ``PROVIDER`` constant.
* ``rcdata/build/sources/*.py`` -- each market-series source's ``SOURCE``, and ``market_series.SOURCES``.
* ``rcdata/caps.py`` -- which providers have a request cap.
* ``core/providers/*.py`` -- the provider helper modules, with the first line of each docstring.

A provider that appears in a builder or a helper but in no ``providers=`` tuple is reported too, under
``not in the need catalog``: `openfigi`, `treasury`, `bls` and `tickerinside` live there, and a list that drops
them is wrong in the direction that matters.
"""
from __future__ import annotations

import argparse
import ast
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "rcdata" / "needs" / "catalog.py"
BUILD = ROOT / "rcdata" / "build"
SOURCES = BUILD / "sources"
CAPS = ROOT / "rcdata" / "caps.py"
HELPERS = ROOT / "core" / "providers"
DATASETS = ROOT / "core" / "datasets.py"
SCREEN = ROOT / "rcdata" / "needs" / "screen.py"
SCANNED = ("rcdata", "core")


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"))


def _const_str(node: ast.AST) -> str | None:
    return node.value if isinstance(node, ast.Constant) and isinstance(node.value, str) else None


def needs_by_provider(path: Path = CATALOG) -> dict[str, list[str]]:
    """``{provider: [need key, ...]}`` from every ``Need(...)`` call's ``providers=`` tuple."""
    out: dict[str, list[str]] = defaultdict(list)
    for node in ast.walk(_tree(path)):
        if not (isinstance(node, ast.Call) and getattr(node.func, "id", None) == "Need"):
            continue
        key = _const_str(node.args[0]) if node.args else None
        provs = [
            p for kw in node.keywords if kw.arg == "providers"
            for p in (_const_str(e) for e in getattr(kw.value, "elts", []))
            if p
        ]
        for prov in provs:
            out[prov].append(key or "?")
    return dict(out)


def module_constants(path: Path) -> dict[str, str]:
    """The module-level ``NAME = "..."`` style constants of one file."""
    out: dict[str, str] = {}
    for node in _tree(path).body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1:
            name = getattr(node.targets[0], "id", None)
            value = _const_str(node.value)
            if name and name.isupper() and value:
                out[name] = value
    return out


def builders(known: set[str] | None = None) -> tuple[dict[str, list[str]], list[str]]:
    """``({provider: [job, ...]}, [internal job, ...])`` from each builder's ``NAME`` and ``PROVIDER``.

    A ``NAME`` reads ``<prefix>/<job>``, and the prefix is a provider only when the module declares ``PROVIDER``
    or the prefix is a provider the need catalog knows. Everything else is one of our own serving lanes
    (``prices/serving``, ``ownership/serve``, ``spine/security``, ``public/fda_calendar`` ...), which a provider
    list must not swallow.
    """
    known = known if known is not None else set(needs_by_provider())
    out: dict[str, list[str]] = defaultdict(list)
    internal: list[str] = []
    for path in sorted(BUILD.rglob("*.py")):
        if "tests" in path.parts:
            continue
        consts = module_constants(path)
        name = consts.get("NAME")
        if not name or "/" not in name or name.startswith("/"):
            continue
        declared = consts.get("PROVIDER")
        prefix = name.split("/", 1)[0]
        if declared:
            out[declared].append(name)
        elif prefix in known:
            out[prefix].append(name)
        else:
            internal.append(name)
    return dict(out), sorted(internal)


def market_sources() -> dict[str, str]:
    """``{source: first docstring line}`` for the market-series sources."""
    out: dict[str, str] = {}
    for path in sorted(SOURCES.glob("*.py")):
        if path.name == "__init__.py":
            continue
        source = module_constants(path).get("SOURCE") or path.stem
        doc = (ast.get_docstring(_tree(path)) or "").strip().splitlines()
        out[source] = doc[0] if doc else ""
    return out


def capped() -> list[str]:
    """The providers ``caps.py`` gives a request cap."""
    for node in ast.walk(_tree(CAPS)):
        if isinstance(node, ast.Dict) and node.keys:
            keys = [_const_str(k) for k in node.keys]
            if all(keys):
                return [k for k in keys if k]
    return []


def helpers() -> dict[str, str]:
    """``{module: first docstring line}`` for ``core/providers/``."""
    out: dict[str, str] = {}
    for path in sorted(HELPERS.glob("*.py")):
        if path.name in ("__init__.py", "result.py", "spend.py", "validator.py"):
            continue
        doc = (ast.get_docstring(_tree(path)) or "").strip().splitlines()
        out[path.stem] = doc[0] if doc else ""
    return out


def _sources() -> list[Path]:
    """Every non-test module of the scanned trees, plus the module packages' own files."""
    out: list[Path] = []
    for top in (*SCANNED, *(d.name for d in sorted(ROOT.glob("module_*")) if d.is_dir())):
        for path in sorted((ROOT / top).rglob("*.py")):
            if "tests" in path.parts or path.name.startswith("test_"):
                continue
            out.append(path)
    return out


def dataset_cards(path: Path | None = None) -> dict[str, list[tuple[str, str]]]:
    """``{provider: [(job, label), ...]}`` from ``rcdata/needs/screen.py``'s ``DATASETS`` map.

    A builder's job name is not always a module constant: ``wrds_fund.py`` sets ``self.name = "wrds/segments"``
    inside a class, ``fx_rates.py`` names its second job ``EXRT_NAME = "wrds/exrt"``, and ``spine/wrds.py`` keeps
    its dataset names in a dict literal. So reading only ``NAME`` missed ``wrds/funda``, ``wrds/fundq``,
    ``wrds/segments``, ``wrds/exrt``, ``yfinance/float`` and ``tradingview/float`` (endpoint review of this
    script, 27 Nov 2026, claude-coordinator PR #1524).

    ``screen.py``'s ``DATASETS`` is the registry that does hold every one of them, keyed ``<provider>/<job>``,
    each with the label the Settings / Data screen shows -- which is also the plainest statement of what the job
    fetches. It is read here instead of scanning the tree for strings, because a string match cannot tell a job
    from a label: ``wrds/compustat`` and ``wrds/crsp`` are the two sources ``price_bar_daily`` tags its rows with
    (``rcdata/build/prices/wrds_history.py:84``) and ``finra/cftc`` is a ``Source`` enum value, and none of the
    three is a fetch.
    """
    path = path or SCREEN
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for node in _tree(path).body:
        targets = getattr(node, "targets", []) or ([node.target] if isinstance(node, ast.AnnAssign) else [])
        if not (targets and getattr(targets[0], "id", None) == "DATASETS"):
            continue
        for key, value in zip(node.value.keys, node.value.values):
            name = _const_str(key)
            if not (name and "/" in name):
                continue
            label = ""
            if isinstance(value, ast.Call) and value.args:
                label = _const_str(value.args[0]) or ""
            out[name.split("/", 1)[0]].append((name, label))
    return {k: sorted(v) for k, v in out.items()}


def module_providers() -> dict[str, str]:
    """``{provider: file:line}`` for a ``PROVIDER = "..."`` declared in a ``module_*`` package.

    A reader can live outside ``rcdata/``: ``module_news/x_lane.py`` declares ``PROVIDER = "x-follow"`` for the
    News board's X lane, which has no ``Need(...)`` of its own and so appears in no other section here.
    """
    out: dict[str, str] = {}
    for path in _sources():
        if not path.relative_to(ROOT).parts[0].startswith("module_"):
            continue
        for node in _tree(path).body:
            if not (isinstance(node, ast.Assign) and len(node.targets) == 1):
                continue
            if getattr(node.targets[0], "id", None) != "PROVIDER":
                continue
            value = _const_str(node.value)
            if value:
                out[value] = f"{path.relative_to(ROOT).as_posix()}:{node.lineno}"
    return out


def source_enum() -> list[str]:
    """The ``Source`` enum values of ``core/datasets.py``: a per-dataset label, not the provider list."""
    for node in ast.walk(_tree(DATASETS)):
        if isinstance(node, ast.ClassDef) and node.name == "Source":
            return sorted(v for stmt in node.body
                          if isinstance(stmt, ast.Assign) and (v := _const_str(stmt.value)))
    return []


def inventory() -> dict:
    needs = needs_by_provider()
    jobs, internal = builders(set(needs))
    outside = module_providers()
    names = sorted(set(needs) | set(jobs) | set(outside))
    cards = dataset_cards()
    caps = capped()
    enum = source_enum()
    return {
        "providers": [
            {
                "provider": n,
                "needs": sorted(needs.get(n, [])),
                "need_count": len(needs.get(n, [])),
                "jobs": sorted(jobs.get(n, [])),
                "datasets": [{"name": j, "label": lb} for j, lb in cards.get(n, [])],
                "capped": n in caps,
                "in_need_catalog": n in needs,
                "declared_outside_rcdata": outside.get(n, ""),
            }
            for n in names
        ],
        "internal_jobs": internal,
        "source_enum": enum,
        "source_enum_not_a_provider": sorted(set(enum) - set(names)),
        "market_sources": market_sources(),
        "helper_modules": helpers(),
        "capped": caps,
        "totals": {
            "needs": sum(len(v) for v in needs.values()),
            "providers_in_catalog": len(needs),
            "providers_in_code": len(names),
            "datasets": sum(len(v) for v in cards.values()),
        },
    }


def markdown(inv: dict) -> str:
    t = inv["totals"]
    lines = [
        "# Provider inventory (generated by scripts/providers_report.py)",
        "",
        f"{t['providers_in_catalog']} providers in the need catalog, {t['providers_in_code']} in the code, "
        f"{t['needs']} need-to-provider links, {t['datasets']} datasets on the Settings / Data screen.",
        "",
        "| Provider | In catalog | Needs | Jobs | Capped |",
        "|---|---|---|---|---|",
    ]
    for p in inv["providers"]:
        lines.append(
            f"| `{p['provider']}` | {'yes' if p['in_need_catalog'] else '**no**'} | {p['need_count']} "
            f"| {', '.join(f'`{j}`' for j in p['jobs']) or '-'} | {'yes' if p['capped'] else '-'} |"
        )
    lines += ["", "## Our own serving jobs (not providers)", "", ", ".join(f"`{j}`" for j in inv["internal_jobs"])]
    lines += ["", "## What each provider actually fetches (rcdata/needs/screen.py DATASETS)", ""]
    for p in inv["providers"]:
        for d in p["datasets"]:
            lines.append(f"- `{d['name']}` - {d['label']}")
    outside = [p for p in inv["providers"] if p["declared_outside_rcdata"]]
    if outside:
        lines += ["", "## Readers declared outside rcdata (no need of their own)", ""]
        lines += [f"- `{p['provider']}` - {p['declared_outside_rcdata']}" for p in outside]
    lines += ["", "## core/datasets.py `Source` enum (a per-dataset label, not this list)", "",
              ", ".join(f"`{v}`" for v in inv["source_enum"])]
    missing = sorted(p["provider"] for p in inv["providers"] if p["provider"] not in inv["source_enum"])
    lines += ["", f"Not an enum value: {', '.join(f'`{m}`' for m in missing) or '-'}.",
              f"An enum value that is not a provider name here: "
              f"{', '.join(f'`{m}`' for m in inv['source_enum_not_a_provider']) or '-'}."]
    lines += ["", "## Market-series sources", ""]
    lines += [f"- `{k}` - {v}" for k, v in inv["market_sources"].items()]
    lines += ["", "## Provider helper modules (core/providers)", ""]
    lines += [f"- `{k}` - {v}" for k, v in inv["helper_modules"].items()]
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--json", action="store_true", help="print JSON instead of the markdown table")
    args = ap.parse_args(argv)
    inv = inventory()
    print(json.dumps(inv, indent=2) if args.json else markdown(inv), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
