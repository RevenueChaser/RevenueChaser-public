"""Durable Relatedness store (``boards/relatedness.duckdb``) — Phase 6.

What the board keeps of its own: the company vectors (``relatedness_embeddings``), the peer scores
(``relatedness_scores``), the theme tables and the shared ``llm_cache``.

A **profile** is none of them any more. It is the SEC reading service's ``company.profile`` answer, read where it
is (``engine.service_rows``, #894 step 3b; avo, 24 Nov 2026: "Relatedness da Value chain gibi olsun, ek
kopyalamaya gerek yok"). The board had its own writer and its own ``relatedness_profiles`` /
``relatedness_attributes`` until #1520 took both; this module's readers serve the service's rows in the shape
those tables had, so every caller reads the same keys it always did. Nothing here writes a profile.
"""
from __future__ import annotations

import json
import logging

from revenuechaser.core import rawstore

from . import config
from . import store_reads as sr

logger = logging.getLogger(__name__)

PROMPT_VERSION = config.PROMPT_VERSION


# The filing a profile was read from (build plan PR 20, G6): the company, the accession, the form and the day filed.
SOURCE_KEYS = ("cik", "accession", "form", "filed")


def cache_key(model, thinking, effort, prompt_version, ticker, input_hash, provider=None, source=None) -> str:
    """Structured (sorted-keys) cache key — stable across dict ordering.

    ``provider`` names a writer other than DeepSeek (``"evren"``, #360); a DeepSeek key carries none, so its bytes
    are what they were before other writers. ``source`` (G6) is the filing the prompt's text came from (``SOURCE_KEYS``);
    a key made without one carries none. Staleness never reads it (``is_stale``): the input hash already moves
    with the text.
    """
    key = {
        "model": model or "", "thinking": int(bool(thinking)), "effort": effort or "",
        "prompt_version": prompt_version, "ticker": (ticker or "").upper(),
        "input_hash": input_hash,
    }
    if provider and provider != "deepseek":
        key["provider"] = provider
    if source:
        key["source"] = {k: (None if source.get(k) is None else str(source[k])) for k in SOURCE_KEYS}
    return json.dumps(key, sort_keys=True, separators=(",", ":"))


def profile_source(cache_key_value) -> dict | None:
    """The filing a stored profile was read from (``cache_key``'s ``source``), or None for a profile made before
    G6 or from no filing."""
    src = (_key_mode(cache_key_value or "") or {}).get("source")
    return dict(src) if isinstance(src, dict) else None


def mode_stamp(writer: tuple[str, str] | None = None) -> dict:
    """The mode a current profile matches. ``writer`` is ``(provider, model)`` (#360; default DeepSeek and its
    ``MODEL``): a DeepSeek mode is the stamp it always was; another writer's names its provider and sends no
    thinking knob."""
    from revenuechaser.core.providers import deepseek
    provider, model = writer or ("deepseek", deepseek.MODEL)
    if provider == "deepseek":
        # v3 (#400) sends no thinking: a DeepSeek stamp names neither knob, as every other writer's.
        return {"model": model, "thinking": False, "effort": "", "prompt_version": PROMPT_VERSION}
    return {"provider": provider, "model": model, "thinking": False, "effort": "", "prompt_version": PROMPT_VERSION}


def profile_rows(tickers: list[str] | None = None) -> list[dict]:
    """The board's profile rows of ``tickers``, every row when None or empty.

    They are the SEC reading service's ``company.profile`` answers, read where they are, as Value Chain reads them
    (``engine.service_rows``, #894 step 3b); each also carries ``attributes``, the tag lists. The row has the shape
    the board's own ``relatedness_profiles`` had until #1520, so this module's readers did not change with it.
    """
    from .engine import service_rows
    return service_rows(tickers)


def load_profiles(tickers: list[str] | None = None) -> dict[str, dict]:
    """``{ticker: {field: [str, ...]}}``: every profile when ``tickers`` is None, none when it is empty (an empty
    list once read every profile, #642 PR 3). The tag lists come from :func:`profile_rows`' ``attributes``."""
    if tickers is not None and not tickers:
        return {}
    return {r["ticker"]: {f: (r["attributes"].get(f) or []) for f in config.PROFILE_FIELDS}
            for r in profile_rows(tickers)}


def load_profile_json(tickers: list[str] | None = None) -> dict[str, dict]:
    """``{ticker: v3 profile}`` for the rows that carry one (#669; a v2 row has none)."""
    return {r["ticker"]: r["profile_json"] for r in profile_rows(tickers) if isinstance(r.get("profile_json"), dict)}


def load_vectors(model: str, tickers: list[str]) -> dict[str, bytes]:
    """``{ticker: vector blob}`` stored for ``model`` (``embeddings`` reads the blob's layout)."""
    want = set(tickers)
    return {r["ticker"]: bytes(r["vector"]) for r in rawstore.get_all(sr.EMBEDDINGS)
            if r["model"] == model and r["ticker"] in want and r.get("vector") is not None}


def save_vectors(model: str, blobs: dict[str, bytes], dim: int) -> None:
    """Upsert one vector row per ticker (key ``(ticker, model)``): a re-embedded company replaces its row."""
    if blobs:
        rawstore.write_rows(sr.EMBEDDINGS,
                            [{"ticker": t, "model": model, "dim": dim, "vector": b} for t, b in blobs.items()])


def profile_meta(tickers: list[str] | None = None) -> dict[str, dict]:
    """``{ticker: {status, attempts, cache_key, cik}}`` for the profile rows (``profile_rows``)."""
    return {r["ticker"]: {"status": r.get("status") or "ok",
                          "attempts": int(r.get("attempts") or 0),
                          "cache_key": r.get("cache_key") or "",
                          "cik": r.get("cik") or ""}
            for r in profile_rows(tickers)}


def _key_mode(cache_key_value) -> dict | None:
    if isinstance(cache_key_value, dict):      # rawstore auto-decodes JSON text
        return cache_key_value
    try:
        k = json.loads(cache_key_value)
    except (json.JSONDecodeError, TypeError):
        return None
    return k if isinstance(k, dict) else None


def input_hash(cache_key_value) -> str | None:
    """The ``input_hash`` the service's answer was written from (the hash of its exact prompt), or ``None``.

    The service compares it with the hash of today's prompt: a new filing text or company name redoes the answer
    (#388 D5, now ``rcdata/build/sec_reads``). The board only reads it.
    """
    k = _key_mode(cache_key_value or "")
    return (k or {}).get("input_hash") or None


def is_stale(meta: dict, mode: dict) -> bool:
    """True when a stored profile was made under another prompt version than ``mode``'s (or its key is unreadable).

    Mixed writers (avo, 11 Nov 2026: "sadece ilk tur claude ile sonra deepseek e donebiliriz"): a profile stays
    current whoever wrote it, so a first round by Claude is not redone when the board's writer goes back to DeepSeek.
    This replaces #360's "one writer per board", under which another provider or model made a profile stale. A new
    filing text or company name still redoes a profile through its input hash (#388 D5), with the board's writer.
    """
    k = _key_mode(meta.get("cache_key") or "")
    return k is None or k.get("prompt_version") != mode.get("prompt_version")


def key_writer(cache_key_value) -> tuple[str, str] | None:
    """``(provider, model)`` a stored profile's key names (no provider = DeepSeek), or None for an unreadable key."""
    k = _key_mode(cache_key_value or "")
    return None if k is None else (k.get("provider") or "deepseek", k.get("model") or "")


def other_writer_tickers(tickers: list[str] | None, writer: tuple[str, str]) -> set[str]:
    """Tickers whose usable profile another writer made. Counted for the board (``other_writer``); since mixed
    writers (11 Nov 2026) they stay current and in the peer matrix."""
    return {t for t, meta in profile_meta(tickers).items()
            if meta["status"] == "ok" and key_writer(meta.get("cache_key")) not in (None, tuple(writer))}


def profile_writers(tickers: list[str] | None = None) -> dict[str, str]:
    """``{ticker: "provider/model"}`` of each usable stored profile (the board names the writer per profile)."""
    out = {}
    for t, meta in profile_meta(tickers).items():
        w = key_writer(meta.get("cache_key")) if meta["status"] == "ok" else None
        if w is not None:
            out[t] = f"{w[0]}/{w[1]}"
    return out


def stale_tickers(tickers: list[str] | None = None, writer: tuple[str, str] | None = None) -> set[str]:
    """Tickers whose non-empty profile predates the current mode of ``writer`` (kept, badged)."""
    mode = mode_stamp(writer)
    out = set()
    for t, meta in profile_meta(tickers).items():
        if meta["status"] == "ok" and is_stale(meta, mode):
            out.add(t)
    return out


def score_rows(peers: dict[str, list[dict]]) -> list[dict]:
    """The ``relatedness_scores`` rows of ``{ticker: [{peer, score}, ...]}`` (its result history,
    ``relatedness_scores_history``, is their mirror)."""
    return [{"ticker": t, "peer": p["peer"], "score": p["score"]}
            for t, scored in peers.items() for p in scored]


def save_scores(peers: dict[str, list[dict]]) -> int:
    """Persist ``{ticker: [{peer, score}, ...]}`` to ``relatedness_scores``.

    The table is the **record** of what was scored, not a read path (#594, avo's "tut" of 19 Nov 2026):
    the board's neighbours come from the run's own payload, so no board reads these rows back. It is
    kept because it is the only durable record of which pair scored what -- ``relatedness_scores_history``
    mirrors it, the guard below stops a run that scored nothing from wiping it, and the incremental
    scoring of #884 would read it as the previous score.
    """
    rows = score_rows(peers)
    if not rows:
        # A run that scored nothing (cold cache, peak-hours stop) must not wipe the last good
        # Fetch: retiring every pair it did not score would delete every stored score (#284).
        logger.warning("relatedness_scores: the run produced no peer scores; kept the %d stored rows",
                       rawstore.count(sr.SCORES))
        return 0
    retired = rawstore.sync_rows(sr.SCORES, rows)   # incremental, plan §10
    logger.info("relatedness_scores: %d pairs written, %d retired", len(rows), retired)
    return len(rows)
