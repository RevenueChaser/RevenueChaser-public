"""Value Chain engine — corpus -> mentions -> edges, plus 2-hop.

On the layer the corpus is the SEC form reader's (#841): ``sec/forms`` cuts every stored annual report once and
this board reads ``filing_section``'s business row, so a Fetch downloads and slices nothing. Off the layer the
old path stands: Fetch pulls the latest 10-K/20-F per issuer and slices Item 1/4 into ``chain_filings``. The
model-only (``no_fetch``) path reads the cached corpus and never touches the network either way. Edges are
persisted so a Refresh re-renders with zero network.
"""
from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone

from RevenueChaser.core import rawstore
from RevenueChaser.core.providers import sec_edgar
from RevenueChaser.rcdata import opens  # #566: pooled reads count for this run

from . import aliases
from . import config
from . import edgar_text
from . import health as health_mod
from . import precision as precision_mod
from . import splitter

logger = logging.getLogger(__name__)

_TABLE = "chain_filings"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Everything the board and the cache check need; ``item_text`` (~50 KB per issuer) is not.
_LIGHT_COLUMNS = ["ticker", "form", "filed", "quality", "primary_doc"]


def _cached_filings() -> dict[str, dict]:
    return {r["ticker"]: r for r in rawstore.get_all(_TABLE, columns=["ticker"])}


# ── the corpus: the shared SEC layer, or chain_filings off it (plan 2026-11-11 F2) ──
def _reads_layer() -> bool:
    """The layer is the corpus once the SEC form reader has built too (#841): the board cuts no section of its own
    any more, it reads the one independent cut ``sec/forms`` serves.

    Two datasets have to be there, not one. ``reads_layer`` only asks for companyfacts, and the ticker -> CIK map
    (``read.fundamental_companies``) is the fundamentals layer's; the text is ``sec/forms``'. An unbuilt
    ``filing_section`` would let a Fetch replace every stored edge with none of the layer's, which is why this is
    a gate and not a preference.
    """
    from RevenueChaser.core import fundamentals_layer
    from RevenueChaser.rcdata import ops
    from RevenueChaser.rcdata.build.sec_forms import forms
    # shortcut: a partly built sec/forms still counts; add a coverage floor if a partial first build ever happens.
    return fundamentals_layer.reads_layer() and ops.ever_built(forms.NAME)


def _default_tickers() -> list[str]:
    if config.USE_SHARED_UNIVERSE:
        from RevenueChaser.core.universe import BOARD_OPERATING_ONLY, classification_universe
        return classification_universe(operating_only=BOARD_OPERATING_ONLY["module_value_chain"])
    return list(config.SEED)


# Companies one layer read holds at once (memory guard). 50, not the 200 of the ``filing_item`` days: ``ours-2``
# stores a business section whole, so one is p50 55 KB and up to 489 KB (#841's measurement), where the capped cut
# was at most 200 KB.
_LAYER_BATCH = 50


def _layer_filings(tickers: list[str] | None = None, text: bool = False):
    """Batches of ``chain_filings``-shaped rows from the SEC form reader: per ticker the newest annual report's
    business section ``sec/forms`` serves (``read.form_business``, ``filing_section``). A ticker without a document
    is absent. ``text`` adds ``item_text``.

    Since #841 this is the one cut the board reads, and it is nobody's copy: the board asked ``sec/filings`` for
    ``filing_item`` until now, which is a second cut of the same documents by the same rule. ``primary_doc`` is the
    row's ``document``, which for a 40-F can be the AIF exhibit rather than the primary document - the exhibit is
    where that form's business section is, and the newest document of the newest filing is what the reader serves.
    A row cut with another ``rules_version`` than :data:`splitter.VERSION` is read and logged, not dropped: the
    board has lived with a version pin ahead of its stored text before (``splitter``'s docstring), and dropping
    rows would empty the corpus instead of showing it.
    """
    from RevenueChaser.rcdata import read
    tickers = _default_tickers() if tickers is None else tickers
    by_cik: dict[str, list[str]] = {}
    for c in read.fundamental_companies(tickers):
        if c.get("cik"):
            by_cik.setdefault(read._cik(c["cik"]), []).append(str(c["ticker"]).upper())
    ciks = sorted(by_cik)
    off_version: dict[str, int] = {}
    for i in range(0, len(ciks), _LAYER_BATCH):
        batch = []
        for d in read.form_business(ciks[i:i + _LAYER_BATCH], text=text):
            version = str(d.get("rules_version") or "")
            if version != splitter.VERSION:
                off_version[version] = off_version.get(version, 0) + 1
            row = {"cik": read._cik(d["cik"]), "form": d.get("form"), "filed": str(d.get("filing_date") or ""),
                   "accession": d.get("accession"), "primary_doc": d.get("document"),
                   "quality": d.get("quality"),
                   # The period the filing reports on (``filing_section.report_date``, the SEC's reportDate): G-E's "FY<year>",
                   # plan v31 step 1(h).
                   "period_end": str(d.get("report_date") or "")}
            if text:
                row["item_text"] = d.get("text") or ""
            batch.extend({"ticker": t, **row} for t in by_cik.get(row["cik"], []))
        yield batch
    if off_version:
        logger.warning("value_chain: %s business sections are cut with %s, not %s; the board reads them as they are",
                       sum(off_version.values()),
                       ", ".join(f"{v or 'no version'} ({n})" for v, n in sorted(off_version.items())),
                       splitter.VERSION)


def _corpus_batches():
    """The filings ``build_edges`` reads, in batches: the form reader's when the board reads the layer (#841), else
    ``chain_filings``."""
    if _reads_layer():
        yield from _layer_filings(text=True)
    else:
        yield rawstore.get_all(_TABLE)


def _board_filings_rows() -> list[dict]:
    """The board's filing list without the text, from the same corpus ``build_edges`` reads."""
    if _reads_layer():
        return [r for batch in _layer_filings() for r in batch]
    return rawstore.get_all(_TABLE, columns=_LIGHT_COLUMNS)


# ── the one write path for chain_filings (#116 C6) ──────────────────────────
_DB = rawstore.MANIFEST[_TABLE]["db"]   # chain_filings and chain_meta share it
# A slice is replaced only by one of the same rank or better. ``overrun`` still
# holds all of Item 1, and ``capped`` its start (cut only at the cap), so both
# are protected too; ``short`` and ``missing`` rank 0.
_RANK = {"ok": 2, "overrun": 1, "capped": 1}


def store_slices(rows: list[dict]) -> tuple[int, int]:
    """Write sliced filings; return ``(written, kept)``.

    A stored slice is never replaced by a worse one (``ok`` > ``overrun`` /
    ``capped`` > ``short`` / ``missing``), whatever the caller (sync, ``fetch_corpus``,
    ``force``); between two of the same rank the new filing wins. The stored quality is read and
    the rows written in one transaction. A written row clears its ``miss:`` key.
    """
    if not rows:
        return 0, 0
    tickers = [r["ticker"] for r in rows]

    def _write(tx):
        tx.ensure_table(_TABLE)
        tx.ensure_table("chain_meta")
        marks = ", ".join("?" * len(tickers))
        stored = {t: (q, acc) for t, q, acc in tx.execute(
            f"SELECT ticker, quality, accession FROM {_TABLE} WHERE ticker IN ({marks})",
            tickers).fetchall()}
        write, kept = [], []
        for r in rows:
            old_q, old_acc = stored.get(r["ticker"], (None, None))
            if _RANK.get(splitter.base(r.get("quality")), 0) < _RANK.get(splitter.base(old_q), 0):
                kept.append((r, old_q, old_acc))
            else:
                write.append(r)
        tx.write_rows(_TABLE, write)
        if write:
            keys = [_MISS_PREFIX + r["ticker"] for r in write]
            tx.execute(f"DELETE FROM chain_meta WHERE key IN ({', '.join('?' * len(keys))})", keys)
        return write, kept

    write, kept = rawstore.atomic(_write, db=_DB)
    for r, old_q, old_acc in kept:
        logger.warning("value_chain %s: kept %s slice %s; new %s is %s",
                       r["ticker"], old_q, old_acc, r.get("accession"), r.get("quality"))
    return len(write), len(kept)


# ── recorded misses (#116 C26): chain_meta ``miss:<TICKER>`` keys ───────────
# Only a CIK with no usable annual filing is recorded; a missing CIK costs no
# request (the CIK map is local), so it is counted, never stored.
_MISS_PREFIX = "miss:"
MISS_NOTES = {"no_filing": "no 10-K / 20-F", "form_40f": "40-F, not supported yet"}


def _cik_str(cik) -> str:
    try:
        return str(int(cik))
    except (TypeError, ValueError):
        return str(cik or "")


def miss_row(ticker: str, reason: str, cik) -> dict:
    return {"key": _MISS_PREFIX + ticker.upper(), "value": json.dumps({
        "reason": reason, "note": MISS_NOTES.get(reason, reason),
        "cik": _cik_str(cik), "checked": _now()})}


def record_misses(rows: list[dict]) -> None:
    if rows:
        rawstore.ensure_table("chain_meta")
        now = time.time()
        rawstore.write_rows("chain_meta", [{**r, "fetched_at": now} for r in rows])


def stored_misses() -> dict[str, dict]:
    """``{ticker: {reason, note, cik, checked}}`` from ``chain_meta`` (read only)."""
    out: dict[str, dict] = {}
    for r in rawstore.get_all("chain_meta"):
        key = str(r.get("key") or "")
        if not key.startswith(_MISS_PREFIX):
            continue
        v = r.get("value")
        if isinstance(v, str):
            try:
                v = json.loads(v)
            except ValueError:
                continue
        if isinstance(v, dict):
            out[key[len(_MISS_PREFIX):]] = v
    return out


def miss_is_current(miss: dict | None, cik, now: datetime | None = None) -> bool:
    """A recorded miss still holds: same CIK, checked less than MISS_RETRY_DAYS ago."""
    if not miss or _cik_str(miss.get("cik")) != _cik_str(cik):
        return False
    try:
        checked = datetime.fromisoformat(str(miss.get("checked")))
    except ValueError:
        return False
    if checked.tzinfo is None:
        checked = checked.replace(tzinfo=timezone.utc)
    now = now or datetime.now(timezone.utc)
    return now - checked < timedelta(days=config.MISS_RETRY_DAYS)


def corpus_miss_summary(tickers: list[str]) -> dict | None:
    """Recorded misses for ``tickers`` by reason, plus the no-CIK count (read only).

    Store reads only, no network: the CIK map comes from the spine (``_stored_ciks``), never through
    ``sec_edgar._cik_map`` (which fetches when empty).
    A ``miss:`` key is deleted only when a slice is written, so a ticker that left
    the universe keeps its key; only ``tickers`` are counted. ``due`` is the
    misses the next sync asks SEC about again (``not miss_is_current``).

    Unknown is not zero (F4): ``None`` when the store cannot be read, and
    ``no_cik`` is ``None`` when no CIK map is stored, so a missing map never
    reads as "every ticker has no CIK".
    """
    try:
        ciks = _stored_ciks()
        misses = stored_misses()
    except Exception:  # noqa: BLE001 - unreadable store reads as "unknown"
        return None
    out = {"recorded": 0, "no_filing": 0, "form_40f": 0, "due": 0,
           "no_cik": (sum(1 for t in tickers if t.upper() not in ciks) if ciks else None)}
    for t in tickers:
        miss = misses.get(t.upper())
        if not miss:
            continue
        out["recorded"] += 1
        reason = miss.get("reason")
        if reason in ("no_filing", "form_40f"):
            out[reason] += 1
        if not miss_is_current(miss, ciks.get(t.upper())):
            out["due"] += 1
    return out


def _stored_ciks() -> dict[str, str]:
    """The ticker -> CIK map of the spine (``rcdata.read.identity``), read only and never the network: no spine is
    "unknown" (``{}``), not a fetch. The old SEC exchange file rows (``sec_exchange_file`` / ``sec_company_tickers``
    in ``raw.duckdb``) were the source until #860 removed the old store."""
    from RevenueChaser.rcdata import read
    try:
        rows = read.identity()
    except Exception:  # noqa: BLE001 - no spine file reads as no map
        return {}
    return {r["ticker"]: str(r["cik"]).strip().lstrip("0") or "0" for r in rows if r.get("ticker") and r.get("cik")}


def fetch_corpus(tickers: list[str] | None = None, no_fetch: bool = False,
                 limit: int | None = None, client=None, force: bool = False,
                 workers: int = 8) -> dict:
    """Fetch + slice filings for tickers with no cached row (cache-first).

    ``pending`` leaves out tickers with no CIK (``no_cik``) and recorded misses
    (``misses``). ``no_fetch`` computes it from reads only and writes nothing.
    """
    tickers = _default_tickers() if tickers is None else list(tickers)
    if _reads_layer():
        # The layer (rcdata sec/filings) is the corpus: nothing is downloaded into chain_filings (plan F2, F3).
        have = {r["ticker"] for batch in _layer_filings(tickers) for r in batch}
        return {"requested": len(tickers), "cached": len(have), "pending": len(set(tickers) - have),
                "fetched": 0, "failed": 0, "no_cik": 0, "misses": 0, "no_fetch": no_fetch, "corpus": "layer"}
    have = {} if force else _cached_filings()
    todo = [t for t in tickers if t not in have]
    if limit is not None:
        todo = todo[:limit]
    misses = stored_misses()
    if no_fetch:
        ciks = _stored_ciks()
        # An empty map means "not loaded yet", not "no CIK anywhere".
        no_cik = [t for t in todo if ciks and not ciks.get(t.upper())]
        missed = [t for t in todo if t.upper() in misses and t not in no_cik]
        return {"requested": len(tickers), "cached": len(tickers) - len(todo),
                "pending": len(todo) - len(no_cik) - len(missed), "fetched": 0,
                "failed": 0, "no_cik": len(no_cik), "misses": len(missed), "no_fetch": True}
    if not todo:
        return {"requested": len(tickers), "cached": len(tickers),
                "pending": 0, "fetched": 0, "failed": 0, "no_cik": 0, "misses": 0,
                "no_fetch": False}

    cmap = sec_edgar._cik_map()
    now = datetime.now(timezone.utc)
    counts = {"failed": 0, "no_cik": 0, "known_miss": 0, "no_filing": 0, "form_40f": 0}
    pairs: list[tuple[str, str]] = []
    for t in todo:
        cik = (cmap.get(t.upper()) or {}).get("cik")
        if not cik:
            counts["no_cik"] += 1
            continue
        if not force and miss_is_current(misses.get(t.upper()), cik, now):
            counts["known_miss"] += 1
            continue
        pairs.append((t, cik))

    rows: list[dict] = []
    miss_rows: list[dict] = []
    if pairs:
        # Parallel fetch; sec_edgar._throttle is shared and lock-guarded, so the
        # aggregate request rate stays within SEC's 10 req/s regardless of workers.
        with ThreadPoolExecutor(max_workers=workers, **opens.pool_kwargs()) as ex:
            futs = {ex.submit(edgar_text.fetch_filing, t, cik, client): (t, cik)
                    for t, cik in pairs}
            for f in as_completed(futs):
                t, cik = futs[f]
                try:
                    res = f.result()
                except Exception as exc:  # noqa: BLE001 - per-ticker network failure
                    logger.warning("value_chain %s: %s", t, exc)
                    res = None
                if res and res.get("miss"):
                    counts[res["miss"]] = counts.get(res["miss"], 0) + 1
                    miss_rows.append(miss_row(t, res["miss"], cik))
                elif res and not res.get("error"):
                    rows.append(res)
                else:  # a network error is retried next run, never recorded
                    counts["failed"] += 1
    record_misses(miss_rows)
    written, kept = store_slices(rows)
    missed = counts["known_miss"] + counts["no_filing"] + counts["form_40f"]
    return {"requested": len(tickers), "cached": len(tickers) - len(todo),
            "pending": len(todo) - counts["no_cik"] - missed, "fetched": written,
            "kept": kept, **counts, "misses": missed, "no_fetch": False}


def _xbrl_customer_edges(ticker: str, customers: list[dict], names: dict | None = None) -> list[dict]:
    """``customer`` edges from the annual report's inline XBRL (``customer_share`` rows of the filer, G6 build plan
    PR 20): a major customer the alias list names, with its share of revenue. An anonymised customer ("Customer A")
    names no company and gives none.

    A customer the hand-kept alias list does not know is named by the spine (``names``, ``aliases.spine_names``;
    #400 WP5): VRTX's McKesson.
    """
    me, out = aliases.issuer(ticker), {}
    for c in customers:
        hit = aliases.resolve(c.get("customer") or "", names)
        if hit is None or aliases.issuer(hit["ticker"]) == me or hit["ticker"] in out:
            continue
        pct = round(float(c["share"]) * 100, 2)
        filed = str(c.get("document_date") or c.get("period_end") or "")
        out[hit["ticker"]] = {
            "dst_name": hit["name"], "dst_ticker": hit["ticker"], "relation": "customer",
            "snippet": (f"Annual report XBRL: {c['customer']} {pct:g}% of revenue (period ending {c.get('period_end')}"
                        + (f", {c['form']} {c['accession']})" if c.get("accession") else f", {c.get('source')})")),
            "filed": filed, "share_pct": pct, "source": "xbrl"}
    return list(out.values())


def _stored_customers(rows: list[dict]) -> dict[str, list[dict]]:
    """``{ticker: customer_share rows}`` of the filings' companies on the fundamentals layer; empty off it."""
    from RevenueChaser.core import fundamentals_layer
    if not fundamentals_layer.reads_layer():
        return {}
    from RevenueChaser.rcdata import read
    by_cik: dict[str, list[dict]] = {}
    for c in read.customer_shares({r.get("cik") for r in rows}):
        by_cik.setdefault(str(c["cik"]), []).append(c)
    return {r["ticker"]: by_cik[read._cik(r.get("cik"))] for r in rows
            if r.get("cik") and read._cik(r.get("cik")) in by_cik}


def _spine_names() -> dict:
    """The spine's company names for the XBRL customers (only read when a filing has some, on the layer)."""
    from RevenueChaser.rcdata import read
    return aliases.spine_names(read.identity())


def filing_edges(ticker: str, text: str, filed: str = "", customers: list[dict] | None = None,
                 names: dict | None = None) -> list[dict]:
    """Edges one filing states on its own, without a model: its XBRL major customers.

    ``customers`` (the filer's ``customer_share`` rows, G6) each give a ``customer`` edge with the share of revenue
    the filer tagged. A company naming itself (or its other share class) is not an edge.

    The two text scans that used to feed this -- the keyword window (``mentions``) and the share sentences
    (``concentration``) -- are gone (#748): the first scored 31 of 80 on its own labelled fixture, and of the 27
    shares the second put on the board 9 were right. ``text`` is kept in the signature for the callers; nothing
    reads it here.
    """
    return [{"src": ticker, "dst_name": c["dst_name"], "dst_ticker": c["dst_ticker"],
             "relation": c["relation"], "snippet": c["snippet"], "filed": c["filed"],
             "share_pct": c.get("share_pct"), "source": c.get("source") or "xbrl"}
            for c in _xbrl_customer_edges(ticker, customers or [], names)]


# A profile field and the relation its companies have to the filer (rcdata/sec_profile.py).
_PROFILE_RELATIONS = (("customers", "customer"), ("suppliers", "supplier"), ("named_competitors", "competitor"))


def _counterparty(edge: dict) -> str:
    return aliases.issuer(edge["dst_ticker"]) if edge.get("dst_ticker") else aliases._key(edge.get("dst_name") or "")


def profile_edges(ticker: str, profile: dict, filed: str = "", names: dict | None = None) -> list[dict]:
    """``chain_mentions`` rows of one Relatedness profile (#410): each named customer, supplier and competitor, with
    its quote and stated share, resolved to a ticker through ``aliases.resolve``; a name it cannot resolve stays as
    text with an empty ``dst_ticker``. The filer itself is no edge."""
    me, out = aliases.issuer(ticker), []
    for field, relation in _PROFILE_RELATIONS:
        for p in profile.get(field) or []:
            p = {"name": p} if isinstance(p, str) else (p if isinstance(p, dict) else {})
            name = str(p.get("name") or "").strip()
            hit = aliases.resolve(name, names) if name else None
            if not name or (hit and aliases.issuer(hit["ticker"]) == me):
                continue
            share = p.get("share")
            out.append({"src": ticker, "dst_name": name, "dst_ticker": hit["ticker"] if hit else "",
                        "relation": relation, "snippet": p.get("quote") or "", "filed": filed,
                        "share_pct": round(float(share) * 100, 2) if isinstance(share, (int, float)) else None,
                        "source": "profile"})
    return out


def _party_relation(edge: dict) -> tuple[str, str]:
    """The key a ``chain_mentions`` row really has: the counterparty *and* the relation (#725).

    ``(src, dst_name, relation)`` is the store's key (``core/rawstore.py``), so one company can be both a customer
    and a competitor of the same filer. Keying the merge by the company alone made the profile's first edge swallow
    every other relation of that company: an XBRL customer edge with its share of revenue vanished whenever the
    profile named the same company as a competitor (measured 12 Nov 2026: 0 of 265 ``customer_share`` rows of 121
    profiled tickers survived), and a profile edge in a second relation could never pick up a stated share.
    """
    return _counterparty(edge), edge["relation"]


def merge_profile(regex_edges: list[dict], prof_edges: list[dict]) -> list[dict]:
    """One filer's edges, one row per (counterparty, relation) (#725): for a pair both sources state, the filing's
    XBRL row, which the filer tagged; for any other pair, the edge of whichever source states it (plan v31 step 1(b)).
    No share is copied from one row to another: a row's share is the one its own source stated, so a served share
    always has the quote or the tagged line it came from.

    A display-only ``other`` edge (written by the keyword scan until #748; stored rows may still hold some) is the
    one exception to the per-relation key: it states no relation at all, so a profile that names that company in
    *any* relation already says more, and the ``other`` row would only double the company on the board.
    """
    if not prof_edges:
        return regex_edges
    filed = {_party_relation(e) for e in regex_edges if e["relation"] != "other"}
    parties = {_counterparty(e) for e in prof_edges}
    return ([e for e in prof_edges if _party_relation(e) not in filed]
            + [e for e in regex_edges if not (e["relation"] == "other" and _counterparty(e) in parties)])


def _stored_profiles() -> dict[str, dict]:
    """The stored Relatedness v3 profiles (``relatedness_profiles.profile_json``); empty when none can be read."""
    from RevenueChaser.module_relatedness import store
    try:
        return store.load_profile_json()
    except Exception:  # noqa: BLE001 - no profile table yet reads as "no profiles": the regex edges stand
        logger.exception("value_chain: Relatedness profiles could not be read; regex edges only")
        return {}


def build_edges(info: dict | None = None) -> list[dict]:
    """Recompute mentions from the cached corpus and persist them.

    A caller that passes ``info`` (the result history, #387) learns how many filings were read (``filings``) and
    whether the stored edges were kept because none came out (``kept``)."""
    edges: list[dict] = []
    covered: set[str] = set()   # the tickers this run scanned: only their stored keys can be retired
    profiles = _stored_profiles()
    n_filings, names = 0, (_spine_names() if profiles else None)
    for rows in _corpus_batches():
        n_filings += len(rows)
        customers = _stored_customers(rows)
        if customers and names is None:
            names = _spine_names()
        twins = _share_class_twins(rows)
        for f in rows:
            t, filed = f["ticker"], f.get("filed") or ""
            if t in twins:
                covered.add(t)      # its edges come from the issuer's kept ticker; a stored row of its own retires
                continue
            # ``splitter.base``: a label can carry suspect flags (``missing;suspect:S1``), and a bare ``==`` would
            # read such a row as having text.
            text = "" if splitter.base(f.get("quality")) == "missing" else (f.get("item_text") or "")
            if not text and t not in customers and t not in profiles:
                continue
            covered.add(t)
            found = filing_edges(t, text, filed, customers.get(t), names)
            edges.extend(merge_profile(found, profile_edges(t, profiles[t], filed, names)) if t in profiles else found)
    rawstore.ensure_table("chain_mentions")
    if info is not None:
        info.update(filings=n_filings, kept=not edges, retired=0)
    if not edges:
        # No filing yielded an edge (every row missing or text-less, an empty corpus): a degraded run retires
        # nothing. Keep the stored edges and return what the store holds, so the board, ``n_mentions`` and a
        # later Refresh agree (#284).
        kept = rawstore.get_all("chain_mentions")
        logger.warning("value_chain: no edges came out of %d filings; kept the %d stored chain_mentions",
                       n_filings, len(kept))
        return kept
    retired = _sync_mentions(edges, covered)
    if info is not None:
        info["retired"] = retired
    logger.info("value_chain: %d chain_mentions written, %d retired", len(edges), retired)
    # A ticker this run did not scan keeps its stored edges, and they stay on the board.
    return edges + [r for r in rawstore.get_all("chain_mentions") if r["src"] not in covered]


def _share_class_twins(rows: list[dict]) -> set[str]:
    """The tickers whose filing another ticker of the same CIK already stands for (#408).

    Two share classes of one issuer (GOOG/GOOGL, FOX/FOXA) carry the same filing and the same profile, so each used
    to write the same edges: "Links drawn" counted them twice and a focal company saw two incoming lines for one
    filing. One ticker per CIK keeps the edges: the class ``aliases.SAME_ISSUER`` names, else the first in order."""
    by_cik: dict[str, list[str]] = {}
    for r in rows:
        if r.get("cik"):
            by_cik.setdefault(str(r["cik"]).lstrip("0"), []).append(r["ticker"])
    twins: set[str] = set()
    for tickers in by_cik.values():
        if len(set(tickers)) > 1:
            keep = min(set(tickers), key=lambda t: (aliases.issuer(t) != t.upper(), t))
            twins.update(t for t in tickers if t != keep)
    return twins


_MENTION_KEY = ("src", "dst_name", "relation")   # the MANIFEST key of chain_mentions


def _sync_mentions(edges: list[dict], covered: set[str]) -> int:
    """Upsert ``edges`` by key and delete, in the same transaction, only the stored keys of the ``covered`` tickers
    this run no longer produces (plan 2026-11-08 §10: a board table is never written from scratch, #863). Returns
    the number of keys retired."""
    new = {tuple(e.get(k) for k in _MENTION_KEY) for e in edges}

    def _write(tx):
        tx.ensure_table("chain_mentions")
        gone = [k for k in tx.execute("SELECT src, dst_name, relation FROM chain_mentions").fetchall()
                if k[0] in covered and tuple(k) not in new]
        for i in range(0, len(gone), 500):
            chunk = gone[i:i + 500]
            tx.execute("DELETE FROM chain_mentions WHERE (src, dst_name, relation) IN ("
                       + ", ".join(["(?, ?, ?)"] * len(chunk)) + ")", [v for k in chunk for v in k])
        tx.write_rows("chain_mentions", edges)
        return len(gone)

    return rawstore.atomic(_write, db=_DB)


def _board_filings(filings: list[dict]) -> list[dict]:
    """Filing rows plus the fields the universal dashboard filters need."""
    from RevenueChaser.core.gics_map import sector_or_unclassified, sector_path
    from RevenueChaser.core.universe import filter_fields
    meta = filter_fields([f["ticker"] for f in filings])
    out = []
    for f in sorted(filings, key=lambda r: r["ticker"]):
        m = meta.get(f["ticker"]) or {}
        out.append({
            "ticker": f["ticker"], "form": f.get("form"), "filed": f.get("filed"),
            "quality": f.get("quality"), "primary_doc": f.get("primary_doc"),
            "name": m.get("name") or f["ticker"],
            "sector": sector_or_unclassified(m.get("sector")),
            "industry": m.get("industry") or "",
            "market_cap": m.get("market_cap"),
            "earnings_date": m.get("earnings_date"),
            "index": m.get("index") or [],
            # The shared filter row (core.universe.filter_fields, #383 C1b).
            "gics": m.get("gics") or sector_path(sector_or_unclassified(m.get("sector")), m.get("industry") or ""),
            "theme_ids": m.get("theme_ids") or [],
        })
    return out


def _board_payload(filings: list[dict], edges: list[dict], as_of: str,
                   fetch: dict | None) -> dict:
    """The board's payload. Filings and edges of an excluded security type (Identity
    R4, #87: funds, SPACs, preferreds, ...) are left out of it; the stored rows stay.

    Only the filing's own ticker and an edge's ``src`` are filtered — a counterparty
    (``dst``) is a name in a filing's text, whatever type it is. Below-floor names
    that were synced earlier are not filtered here (out of scope: type only).
    """
    from RevenueChaser.core.universe import (BOARD_OPERATING_ONLY, classification_universe, excluded_tickers,
                                             theme_catalog)
    excluded = excluded_tickers()
    filings = [f for f in filings if f["ticker"] not in excluded]
    edges = [e for e in edges if e.get("src") not in excluded and e.get("relation") in config.SERVED_RELATIONS]
    # Plan v31 step 1(f): a profile edge waits for the census; the count says what the switch holds back.
    profile_hidden = 0 if config.SERVE_PROFILE_EDGES else sum(1 for e in edges if e.get("source") == "profile")
    if profile_hidden:
        edges = [e for e in edges if e.get("source") != "profile"]
    universe = classification_universe(operating_only=BOARD_OPERATING_ONLY["module_value_chain"])
    universe_total = len(universe)
    # Universe tickers with no filing row that are known not to be fetchable:
    # a recorded miss, or no CIK in the stored map (reads only).
    have = {f["ticker"] for f in filings}
    misses, ciks = stored_misses(), _stored_ciks()
    unfiled = [t for t in universe if t not in have and t not in excluded]
    no_cik = {t for t in unfiled if ciks and not ciks.get(t)}
    missed = {t for t in unfiled if t in misses} - no_cik
    # Pending is always read from the store (D4, DF58): a Fetch's own ``pending`` is its to-do list before it
    # ran, so it still holds the names it just wrote; it stays in ``fetch`` for the job message. Counting the
    # unfiled universe names, not ``universe_total - len(filings)``, keeps a stored filing of a name now
    # below the floor from hiding a pending one; it is the count a Refresh's ``fetch_corpus`` gives.
    pending = len(unfiled) - len(no_cik) - len(missed)
    return {
        "as_of": as_of,
        "filings": _board_filings(filings),
        "edges": edges,
        "fetch": fetch,
        "universe_total": universe_total,
        "pending": pending,
        "misses": len(missed),
        "no_cik": len(no_cik),
        "corpus": "layer" if _reads_layer() else _TABLE,
        "profile_hidden": profile_hidden,
        # G-F (#284): the last sync found no edge and kept the stored ones; the board says so.
        "kept": _stored_meta().get("edges_kept") == "1",
        # Hand-labelled fixture precision (file read only: no store, no network).
        "precision": precision_mod.gate(served=edges),
        # The Theme facet's vocabulary: the pinned theme run (#383 C1b), a store read.
        "theme_catalog": theme_catalog(),
    }


def run(no_fetch: bool = False, tickers: list[str] | None = None,
        limit: int | None = None, force: bool = False, run_id: str | None = None) -> dict:
    """The board's payload. ``run_id`` is kept for the callers; the result history it keyed went with history.duckdb
    (#860). A Refresh writes nothing."""
    if not no_fetch:
        health_mod.EDGAR.reset()      # this run's SEC calls only (#299); a Refresh makes none
    fetch = fetch_corpus(tickers=tickers, no_fetch=no_fetch, limit=limit, force=force)
    if no_fetch:
        # Refresh is pure: it re-renders what the store holds and writes nothing,
        # so ``chain_meta.last_sync`` never claims a sync that did not happen.
        # Rescanning Item 1/4 for the live universe would hang the request thread.
        rawstore.ensure_table("chain_mentions")
        edges = rawstore.get_all("chain_mentions")
        filings = _board_filings_rows()
        # No stored sync means nothing was ever synced: the header says so, rather than printing today (#392).
        return _board_payload(filings, edges, _stored_sync() or "", fetch)
    info: dict = {}
    edges = build_edges(info)
    filings = _board_filings_rows()
    as_of = _now()
    rawstore.ensure_table("chain_meta")
    # write_rows, not replace_all: chain_meta is a "replace" table keyed by
    # ``key``, so only these keys are rewritten and the ``miss:`` keys survive.
    fetched_at = time.time()
    rawstore.write_rows("chain_meta", [
        {"key": "last_sync", "value": as_of, "fetched_at": fetched_at},
        {"key": "n_filings", "value": str(len(filings)), "fetched_at": fetched_at},
        {"key": "n_mentions", "value": str(len(edges)), "fetched_at": fetched_at},
        {"key": "edges_kept", "value": "1" if info.get("kept") else "0", "fetched_at": fetched_at},
    ])
    payload = _board_payload(filings, edges, as_of, fetch)
    # The banner the board already renders, and the run's recorded health (#299). A Refresh leaves the field
    # out, so re-rendering never replaces a Fetch's banner with zeros.
    payload["provider_health"] = health_mod.EDGAR.health()
    return payload


def _stored_meta() -> dict[str, str]:
    return {r["key"]: r["value"] for r in rawstore.get_all("chain_meta")}


def _stored_sync() -> str | None:
    return _stored_meta().get("last_sync")


def load_payload() -> dict:
    """Board payload from the store (zero network)."""
    filings = _board_filings_rows()
    edges = rawstore.get_all("chain_mentions")
    return _board_payload(filings, edges, _stored_sync() or "", None)      # never today when nothing synced (#392)


def _norm(edges: list[dict]) -> dict[str, list[dict]]:
    """Index edges by source ticker."""
    out: dict[str, list[dict]] = {}
    for e in edges:
        out.setdefault(e["src"], []).append(e)
    return out


def edge_index(edges: list[dict]) -> dict[str, dict]:
    """Edges by source and by resolved target, built once for many ``focal_graph``
    calls (#118 C19: a per-ticker rebuild made the board O(tickers x edges))."""
    by_dst: dict = {}
    for e in edges:
        by_dst.setdefault(e.get("dst_ticker"), []).append(e)
    return {"by_src": _norm(edges), "by_dst": by_dst}


# Seen from the focal company, an incoming edge's relation is the other way round (#405).
_INVERSE = {"supplier": "customer", "customer": "supplier"}


def focal_graph(edges: list[dict], ticker: str, depth: int = 2,
                max_hop2: int = config.MAX_HOP2, index: dict | None = None) -> dict:
    """Upstream/downstream edges for ``ticker`` plus one more hop on resolved names.

    Hop 2 only follows resolved supplier/customer edges (never ``other``, never a
    private name), and is capped so the sankey stays readable. ``index`` is an
    optional prebuilt ``edge_index(edges)``; without it one is built per call.
    """
    ticker = (ticker or "").upper()
    index = index or edge_index(edges)
    by_src = index["by_src"]
    seen = {ticker}
    links: list[dict] = []

    def _add(e, hop, incoming=False):
        # ``share_pct``: the share of the filer's (``src``'s) sales the edge states (#387 D7); None when it states
        # none and on an edge stored before the column.
        # ``relation`` stays the filing's own statement, which the page's sentence quotes ("NXPI's filing names
        # AAPL as a possible customer"). ``focal_relation`` is the same relationship seen from the focal company,
        # which is what the legend defines and the chip and colour must read (#405): on an incoming edge the
        # filer's customer is the focal company's supplier.
        links.append({"src": e["src"], "dst": e.get("dst_ticker") or e["dst_name"],
                      "dst_ticker": e.get("dst_ticker") or "",
                      "relation": e["relation"],
                      "focal_relation": _INVERSE.get(e["relation"], e["relation"]) if incoming else e["relation"],
                      "snippet": e.get("snippet") or "",
                      "share_pct": e.get("share_pct"), "hop": hop, "incoming": incoming,
                      # #410: the edge's source; absent on an edge stored before the column.
                      **({"source": e["source"]} if e.get("source") else {})})

    first = [e for e in by_src.get(ticker, []) if e["relation"] in ("supplier", "customer")]
    for e in first:
        _add(e, 1)
        if depth >= 2 and e.get("dst_ticker"):
            seen.add(e["dst_ticker"])
    # Incoming: other issuers' filings that name this company. The link keeps the
    # filing's direction (src names dst); it never seeds a second hop.
    for e in index["by_dst"].get(ticker, []):
        if e["src"] != ticker and e["relation"] in ("supplier", "customer"):
            _add(e, 1, incoming=True)
    if depth >= 2:
        hop2 = 0
        for e in first:
            dst = e.get("dst_ticker")
            if not dst or hop2 >= max_hop2:
                continue
            for e2 in by_src.get(dst, []):
                if e2["relation"] not in ("supplier", "customer"):
                    continue
                _add(e2, 2)
                hop2 += 1
                if hop2 >= max_hop2:
                    break
    return {"ticker": ticker, "links": links}
