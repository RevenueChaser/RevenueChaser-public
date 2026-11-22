"""#763: score the section cutters against the hand-checked truth file, side by side.

    python -m revenuechaser.rcdata.build.sec_forms.score

Reads ``rcdata/tests/fixtures/sec_sections_truth.json`` and the **stored** raw documents
(``raw/sec/filings/documents``). It cuts nothing with edgartools: that cutter's answer is read from the answer
files the cutter already wrote, and a document it has not cut is ``n/a``. Offline: no network, no model, no write.

Per cutter it prints found / missed / wrong / unlocated, how many found slices are exact (both ends within the
file's ``end_slack``), the median start and end error and the median length ratio against the hand-checked
section, and for the cross-reference-only documents whether the cutter rightly cut nothing. Then the agreement
rates between the cutters over the file's ``agreement_ids``, and the documents they disagree on, which are the
queue for the next hand check.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import itertools
import json
import re
import statistics
from pathlib import Path
from typing import Callable

from ... import sec_sections
from .. import base
from . import cutter

TRUTH = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "sec_sections_truth.json"
SECTIONS = {"item_1": "1", "item_4": "4", "aif_business": None}
#: What the edgartools cutter answers for a document it has no answer for: not a miss, because it was never asked.
NOT_CUT = object()


def load_truth(path: Path = TRUTH) -> dict:
    return json.loads(Path(path).read_text("utf-8"))


def _documents() -> Path:
    return base.raw_root() / "sec" / "filings" / "documents"


def _read(path: Path) -> str:
    with gzip.open(path, "rt", encoding="utf-8", errors="replace") as fh:
        return sec_sections.strip_html(fh.read())


def document_text(accession: str, exhibit: str | None = None) -> str | None:
    """The stored document as the cutters see it, ``None`` when the corpus does not hold it. The CIK folder is
    globbed, not built, so its spelling (padded or not) is the store's business."""
    names = ([f"{accession}.{exhibit}.gz"] if exhibit else []) + [f"{accession}.html.gz"]
    for name in names:
        for path in sorted(_documents().glob(f"*/{name}")):
            return _read(path)
    return None


def _ours(version: str) -> Callable[[dict, str], str | None]:
    def cut(case: dict, text: str) -> str | None:
        if case["section"] == "aif_business":
            if version == sec_sections.OURS_1:
                return sec_sections.cut_aif_business(text, version=version)
            return sec_sections.cut_aif_business_q(text, version=version)[0]
        return sec_sections.cut_item(text, case["form"], version=version)[0]
    return cut


def _edgartools(case: dict, text: str):
    want = SECTIONS.get(case["section"])
    if want is None:
        return NOT_CUT                      # it has no vocabulary for an AIF, and only primary documents are cut
    try:
        path = cutter.answer_path(case["accession"])
    except cutter.CutterUnusable:
        return NOT_CUT                      # no pin to name the answer directory by
    if not cutter._is_cut(path):
        return NOT_CUT
    with gzip.open(path, "rt", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line) if line.strip() else {}
            if re.sub(r"(?i)^\s*item\s*", "", str(row.get("item") or "")).strip().upper() == want:
                return row.get("text") or None
    return None


CUTTERS: dict[str, Callable] = {"ours-1": _ours(sec_sections.OURS_1), "ours-2": _ours(sec_sections.OURS_2),
                                "edgartools": _edgartools}


def locate(text: str, piece: str) -> tuple[int, int] | None:
    """Where ``piece`` sits in ``text``. Exact first; otherwise by its first and last twelve words with any
    whitespace between them, because edgartools' text is its own and not ``strip_html``'s."""
    i = text.find(piece)
    if i >= 0:
        return i, i + len(piece)
    words = piece.split()
    if not words:
        return None
    head = re.search(r"\s+".join(map(re.escape, words[:12])), text)
    if head is None:
        return None
    size = len(" ".join(words))
    tails = [head.start() + m.end()
             for m in re.finditer(r"\s+".join(map(re.escape, words[-12:])), text[head.start():])]
    # A tail phrase can repeat (boilerplate), so the end is the candidate whose whitespace-collapsed length is
    # the piece's own; only candidates near that length are measured, so a long document stays cheap.
    near = [end for end in tails if size * 0.8 - 500 <= end - head.start() <= size * 1.5 + 500]
    if not near:
        return None
    return head.start(), min(near, key=lambda end: abs(len(" ".join(text[head.start():end].split())) - size))


def score_case(case: dict, text: str, piece, slack: int) -> dict:
    """One cutter's answer for one hand-checked case."""
    if piece is NOT_CUT:
        return {"outcome": "n/a"}
    if case["expect"] == "crossref":
        return {"outcome": "right" if piece is None else "false"}
    if piece is None:
        return {"outcome": "missed"}
    a, b = case["start"], case["end"]
    span = locate(text, piece)
    if span is None:
        return {"outcome": "unlocated", "ratio": len(piece) / (b - a)}
    s, e = span
    if e <= a or s >= b:
        return {"outcome": "wrong", "start_err": s - a, "end_err": e - b, "ratio": (e - s) / (b - a)}
    return {"outcome": "found", "start_err": s - a, "end_err": e - b, "ratio": (e - s) / (b - a),
            "exact": abs(s - a) <= slack and abs(e - b) <= slack}


def score(truth: dict, cutters: dict[str, Callable] = CUTTERS) -> tuple[list[dict], dict[str, str]]:
    """Every cutter over every hand-checked case: ``(rows, skipped)``, where ``skipped`` names each case whose
    document the corpus does not hold, or holds with a text other than the one that was checked."""
    rows, skipped = [], {}
    slack = int(truth.get("end_slack", 200))
    for case in truth["cases"]:
        exhibit = case.get("document") if case["section"] == "aif_business" else None
        text = document_text(case["accession"], exhibit)
        if text is None:
            skipped[case["id"]] = "not in the corpus"
            continue
        if case.get("doc_sha256") and hashlib.sha256(text.encode()).hexdigest() != case["doc_sha256"]:
            skipped[case["id"]] = "text differs from the hand-checked one"
            continue
        for name, cut in cutters.items():
            rows.append({"id": case["id"], "cutter": name, **score_case(case, text, cut(case, text), slack)})
    return rows, skipped


def table(rows: list[dict]) -> str:
    """One line per cutter, then one line per case."""
    out = []
    for name in dict.fromkeys(r["cutter"] for r in rows):
        mine = [r for r in rows if r["cutter"] == name]
        n = {k: sum(r["outcome"] == k for r in mine)
             for k in ("found", "missed", "wrong", "unlocated", "right", "false", "n/a")}
        found = [r for r in mine if r["outcome"] == "found"]
        med = (lambda key: f"{statistics.median(r[key] for r in found):+.0f}" if found else "-")
        ratio = f"{statistics.median(r['ratio'] for r in found):.2f}" if found else "-"
        out.append(f"{name:<11} found {n['found']} (exact {sum(r['exact'] for r in found)})  missed {n['missed']}  "
                   f"wrong {n['wrong']}  unlocated {n['unlocated']}  crossref right {n['right']} false {n['false']}  "
                   f"n/a {n['n/a']}  median start err {med('start_err')}  end err {med('end_err')}  "
                   f"length ratio {ratio}")
    out.append("")
    for r in rows:
        extra = "  ".join(f"{k} {r[k]:+.0f}" for k in ("start_err", "end_err") if k in r)
        if "ratio" in r:
            extra += f"  ratio {r['ratio']:.2f}"
        out.append(f"{r['id']:<16} {r['cutter']:<11} {r['outcome']:<9} {extra}".rstrip())
    return "\n".join(out)


def _section_of(form: str) -> str:
    return {"20-F": "item_4", "40-F": "aif_business"}.get(form, "item_1")


def _agreement_text(entry: dict) -> str | None:
    if entry["form"] == "40-F":
        # The corpus keeps only a 40-F's AIF exhibits beside its primary document (``filings.stored_exhibits``).
        for path in sorted(_documents().glob(f"*/{entry['accession']}.*.gz")):
            if not path.name.endswith(".html.gz"):
                return _read(path)
    return document_text(entry["accession"])


def agreement(truth: dict, cutters: dict[str, Callable] = CUTTERS):
    """``(pairs, disagree, skipped)``: ``pairs[(x, y)] = (agreed, compared)``; ``disagree[accession]`` lists the
    pairs that did not agree on it. Two cutters agree when both cut nothing, or both ends are within the slack."""
    slack = int(truth.get("end_slack", 200))
    pairs: dict[tuple[str, str], tuple[int, int]] = {p: (0, 0) for p in itertools.combinations(cutters, 2)}
    disagree: dict[str, list[str]] = {}
    skipped: dict[str, str] = {}
    for entry in truth.get("agreement_ids", []):
        text = _agreement_text(entry)
        if text is None:
            skipped[entry["accession"]] = "not in the corpus"
            continue
        case = {"accession": entry["accession"], "form": entry["form"], "section": _section_of(entry["form"])}
        spans = {}
        for name, cut in cutters.items():
            piece = cut(case, text)
            spans[name] = piece if piece is NOT_CUT or piece is None else (locate(text, piece) or "unlocated")
        for x, y in pairs:
            if spans[x] is NOT_CUT or spans[y] is NOT_CUT:
                continue
            same = spans[x] == spans[y] if None in (spans[x], spans[y]) or "unlocated" in (spans[x], spans[y]) \
                else abs(spans[x][0] - spans[y][0]) <= slack and abs(spans[x][1] - spans[y][1]) <= slack
            agreed, compared = pairs[(x, y)]
            pairs[(x, y)] = (agreed + same, compared + 1)
            if not same:
                disagree.setdefault(entry["accession"], []).append(f"{x}/{y}")
    return pairs, disagree, skipped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--truth", type=Path, default=TRUTH)
    args = parser.parse_args(argv)
    truth = load_truth(args.truth)
    rows, skipped = score(truth)
    print(table(rows))
    for case_id, why in skipped.items():
        print(f"skipped {case_id}: {why}")
    pairs, disagree, missing = agreement(truth)
    print("\nagreement")
    for (x, y), (agreed, compared) in pairs.items():
        print(f"  {x}/{y}: {agreed} of {compared}")
    for accession, which in disagree.items():
        print(f"  disagree {accession}: {', '.join(which)}")
    if missing:
        print(f"  {len(missing)} agreement document(s) not in the corpus")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
