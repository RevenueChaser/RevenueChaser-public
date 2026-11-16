"""The stored Relatedness profiles as rows of the SEC reading service: the dry run (#894; plan 2026-11-15_1722
§12.3 step 3). **Nothing is written here**: :func:`plan` reads and counts, and the write is a later step that needs
a backup and the owner's word.

Why an import: the service's staleness hash is not the board's (``company_profile``: the text alone; the board's:
the system prompt, the company's name and the text), so without it the service would ask every company again.

A stored profile is imported when it was made from the text the company's newest annual report holds today. That
is checked with the board's own hash, under both system prompts ``v3d`` has had: #748 (15 Nov 2026) took the
sentence about candidate names out and kept the version, and the stored hash is over the system prompt. An
imported row carries the service's hash of the same text, and the stored row's own writer, status, attempts and
``fetched_at``.

    python -m RevenueChaser.module_relatedness.service_import        # the counts, as JSON

On the server: read-only, with ``RC_STORE_AUTO_ENSURE=0`` (``CLAUDE.md``, Data safety).
"""
from __future__ import annotations

import json

from ..core import rawstore
from ..rcdata import sec_profile
from . import store

RUN_ID = "import:relatedness"
PARTIAL = ":partial"
#: What ``label_source.input`` says the profile was read from, as the service names it.
KIND = {"item": "section:business", "llm_locator": "located"}
_NOW = "this filing is silent. A blank-check"
_CANDIDATES = ("this filing is silent. Candidates, when given, are company names a keyword scan of this filing "
               "found: list one only when the text names it as a customer, supplier or competitor. A blank-check")
assert _NOW in sec_profile.SYSTEM, "the profile's system prompt changed: the import cannot rebuild the one before #748"
#: The system prompts a stored ``v3d`` hash may be over, by name.
SYSTEMS = {"today": sec_profile.SYSTEM, "before #748": sec_profile.SYSTEM.replace(_NOW, _CANDIDATES)}


def plan() -> dict:
    """``{"counts": {...}, "rows": [read_answer rows]}``: what the import would write, and why a company is left
    out (``no_profile``: nothing usable stored; ``text_changed``: stored from another text or name, so the service
    asks it again; ``no_text``: nothing to send today)."""
    from ..rcdata.build.sec_reads import company_profile as cp

    comp = cp.companies()
    stored = {r["ticker"]: r for r in rawstore.get_all("relatedness_profiles")}
    counts = {"companies": len(comp), "imported": 0, "no_profile": 0, "text_changed": 0, "no_text": 0}
    rows, seen = [], set()
    for cik, got in cp.survey(list(comp), comp, located=False):
        seen.add(cik)
        company = comp[cik]
        row = stored.get(str(company["ticker"]).upper()) or {}
        key = store._key_mode(row.get("cache_key") or "") or {}
        v3 = row.get("profile_json")
        if row.get("status") != "ok" or not v3 or not key.get("input_hash"):
            counts["no_profile"] += 1
            continue
        had = str(key["input_hash"])
        partial = had.endswith(PARTIAL)
        had = had[:-len(PARTIAL)] if partial else had
        user = sec_profile.build_user(company["name"], got["hash_text"])
        system = next((name for name, s in SYSTEMS.items() if store.prompt_hash(s, user) == had), None)
        if system is None:
            counts["text_changed"] += 1
            continue
        counts["imported"] += 1
        counts[f"hash of {system}"] = counts.get(f"hash of {system}", 0) + 1
        doc, labels = got["doc"], row.get("label_source") or {}
        filed = doc.get("filing_date")
        provider, model = store.key_writer(key)
        rows.append({
            "question": cp.PROFILE_ID, "prompt_version": key.get("prompt_version"), "cik": cik,
            "accession": str(doc.get("accession") or ""), "document": str(doc.get("document") or ""),
            "filing_date": filed.isoformat() if hasattr(filed, "isoformat") else filed,
            "input_hash": cp._hash(got["hash_text"]), "provider": provider, "model": model,
            "status": "partial" if partial else "ok", "attempts": int(row.get("attempts") or 0) or 1,
            "answer": json.dumps(v3, sort_keys=True), "raw": "[]",
            "missing_chunks": ",".join(map(str, labels.get("missing_chunks") or [])),
            "rules_version": str(doc.get("rules_version") or ""), "fetched_at": row.get("fetched_at"),
            "run_id": RUN_ID, "form": str(doc.get("form") or ""),
            "input_kind": KIND.get(labels.get("input"), got["kind"]), "calls": 0, "tokens_in": 0, "tokens_out": 0,
            "error": None})
    counts["no_text"] = len(comp) - len(seen)
    return {"counts": counts, "rows": rows}


if __name__ == "__main__":
    print(json.dumps(plan()["counts"], indent=1))
