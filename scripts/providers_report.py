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


def inventory() -> dict:
    needs = needs_by_provider()
    jobs, internal = builders(set(needs))
    names = sorted(set(needs) | set(jobs))
    caps = capped()
    return {
        "providers": [
            {
                "provider": n,
                "needs": sorted(needs.get(n, [])),
                "need_count": len(needs.get(n, [])),
                "jobs": sorted(jobs.get(n, [])),
                "capped": n in caps,
                "in_need_catalog": n in needs,
            }
            for n in names
        ],
        "internal_jobs": internal,
        "market_sources": market_sources(),
        "helper_modules": helpers(),
        "capped": caps,
        "totals": {
            "needs": sum(len(v) for v in needs.values()),
            "providers_in_catalog": len(needs),
            "providers_in_code": len(names),
        },
    }


def markdown(inv: dict) -> str:
    t = inv["totals"]
    lines = [
        "# Provider inventory (generated by scripts/providers_report.py)",
        "",
        f"{t['providers_in_catalog']} providers in the need catalog, {t['providers_in_code']} in the code, "
        f"{t['needs']} need-to-provider links.",
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
