"""Value Chain edge precision: the census gate of plan v31 section 6.

Labels live in ``module_value_chain/fixtures/labeled_80.json``: a list of
``{id, src, dst_ticker, relation, label, borderline, snippet}`` where ``label``
is ``true``/``false`` (a labeller's judgement, with the filing open, that the edge
is right: marks 1-4 of section 6), ``null`` for a row that could not be marked at
all, which ``precision`` leaves out of n.

The file holds the profile source's second census (#1159, 20 Nov 2026): 200 served
candidate edges drawn fresh after the wrong-edge filter of #1142, 194 markable,
166 right -- 85.6%, Wilson 95% lower bound 79.9%. The 80 labels that stood here
before judged the keyword scan #748 deleted and went with plan v31 step 1(g); the
file keeps its name.

The counting rule is avo's lenient one (20 Nov 2026): a sales channel, distributor,
broker, royalty payer or receiver, a research or technology collaboration and a
technical dependency are each a right link; only an outright wrong relation counts
against the gate.

The rule (section 6): the Wilson 95% lower bound of the right rate is at or above
0.70. At 175 labels that is 135 right; a writer whose true precision is 0.80 clears
about 85% of the time, one at 0.70 about 2%. The bound replaces the old fixed
minimum of 30 labels: a small sample has a low bound by itself.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "labeled_80.json"
MIN_PRECISION = 0.70
_Z = 1.959963984540054          # the two-sided 95% normal quantile
MAX_EDGES_PER_TICKER = 40


def load_labels(path: Path | None = None) -> list[dict]:
    p = Path(path or FIXTURE)
    if not p.is_file():
        return []
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    return data if isinstance(data, list) else []


def wilson_lower(right: int, n: int) -> float | None:
    """The Wilson score interval's 95% lower bound of ``right / n``; ``None`` for no labels."""
    if n <= 0:
        return None
    p, z2 = right / n, _Z * _Z
    return ((p + z2 / (2 * n)) - _Z * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / (1 + z2 / n)


def precision(labels: list[dict]) -> dict:
    judged = [l for l in labels if l.get("label") in (True, False)]
    tp = sum(1 for l in judged if l["label"])
    fp = len(judged) - tp
    prec = (tp / len(judged)) if judged else None
    lower = wilson_lower(tp, len(judged))
    if lower is None:
        status = "not measured"
    else:
        status = "pass" if lower >= MIN_PRECISION else "fail"
    return {"n": len(judged), "tp": tp, "fp": fp,
            "precision": round(prec, 4) if prec is not None else None,
            "lower_bound": round(lower, 4) if lower is not None else None,
            "passes": status == "pass", "status": status}


def edges_per_ticker(edges: list[dict]) -> dict[str, int]:
    return dict(Counter(e["src"] for e in edges))


def _key(e: dict) -> tuple:
    return (e.get("src"), e.get("dst_ticker"), e.get("relation"))


def served_links(served: list[dict]) -> set[tuple]:
    """Distinct ``(src, dst_ticker, relation)`` supplier / customer keys the board serves."""
    return {_key(e) for e in served if e.get("relation") in ("supplier", "customer")}


def served_labels(labels: list[dict], served: list[dict]) -> list[dict]:
    """Labels whose ``(src, dst_ticker, relation)`` edge is still served.

    A label for an edge the current extractor no longer emits says nothing
    about what the board shows, so it is left out of the served precision.
    """
    keys = {_key(e) for e in served}
    return [l for l in labels if _key(l) in keys]


def gate(edges: list[dict] | None = None, path: Path | None = None,
         served: list[dict] | None = None) -> dict:
    labels = load_labels(path)
    links: set[tuple] | None = None
    if served is not None:
        labels = served_labels(labels, served)
        links = served_links(served)
    rep = precision(labels)
    if links is not None:
        # How much of what the board draws the labels can speak for.
        rep["links"] = len(links)
        rep["covered"] = len({_key(l) for l in labels
                              if l.get("label") in (True, False) and _key(l) in links})
    if edges is not None:
        rep["over_max_edges"] = {t: n for t, n in edges_per_ticker(edges).items()
                                 if n > MAX_EDGES_PER_TICKER}
    return rep
