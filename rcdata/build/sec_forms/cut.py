"""edgartools' answer file, read as our business row (#754, #894).

:mod:`cutter_worker` stores edgartools' own sections unmapped, one JSON line each; this is the mapping the worker's
docstring names. It runs at ``to_parquet``, so a change here re-types the cached answers without a new pass.

Only the business section is mapped: Item 1 of a 10-K and Item 4 of a 20-F, the two forms edgartools has a
vocabulary for among the annual reports this layer cuts (``cutter.KNOWN_FORMS``). A 40-F and a 10-KT are cut by
our own rule, as before.
"""
from __future__ import annotations

import gzip
import json
import re
from pathlib import Path

from ... import sec_sections

#: The item that is the business section, per form edgartools cuts.
BUSINESS_ITEM = {"10-K": "1", "20-F": "4"}
#: Below this the section is served but flagged, so ``module_relatedness.locator.asks`` reads it as a doubtful cut.
#: edgartools' own scale: 0.95 for a table-of-contents anchor, 0.5 for a pointer it warns about (12 Nov 2026
#: measurement, plan v2 §4a).
MIN_CONFIDENCE = 0.8
#: The flag an edgartools row carries when its confidence is low or it came with a warning. Our S1-S5 are not
#: computed on this text: S5 reads the slice's place in the document, and edgartools' text is its own, not a
#: substring of ``strip_html``'s.
SUSPECT = "suspect:ET"


def _item(value: object) -> str:
    """``"Item 1"``, ``"item 1"``, ``"1"`` -> ``"1"``."""
    return re.sub(r"(?i)^\s*item\s*", "", str(value or "")).strip().upper()


def business(answer: Path, form: str) -> tuple[str, str] | None:
    """``(text, quality)`` of the business section in ``answer``, or None when edgartools found none.

    A section that holds the item among several (``covered_items``, "Items 1 and 2. Business and Properties")
    counts. None hands the document back to our own rule; so does a section under :data:`MIN_ITEM_CHARS`
    with no text worth serving.
    """
    want = BUSINESS_ITEM.get(str(form).upper())
    if want is None:
        return None
    found = None
    with gzip.open(answer, "rt", encoding="utf-8") as fh:
        for line in fh:
            row = json.loads(line) if line.strip() else {}
            items = {_item(row.get("item"))} | {_item(i) for i in (row.get("covered_items") or [])}
            if want in items and str(row.get("text") or "").strip():
                found = row
                break
    if found is None:
        return None
    text = str(found["text"])
    if len(text) < sec_sections.MIN_ITEM_CHARS:
        return None
    confidence = found.get("confidence")
    doubtful = found.get("warnings") or (isinstance(confidence, (int, float)) and confidence < MIN_CONFIDENCE)
    return text, f"ok;{SUSPECT}" if doubtful else "ok"
