"""Relatedness engine — pilot selection, profiles, similarity.

Profiles are the SEC reading service's ``company.profile`` answers, read where
they are (``service_rows``, #894 step 3b) and copied nowhere. The board's own
writer, and its ``relatedness_profiles`` / ``relatedness_attributes``, went with
#1520: nothing here calls a model, so a Fetch and a Refresh are both
zero-network and a Fetch's writing is its vectors and its peer scores.
"""
from __future__ import annotations

import json
import logging
import math
from datetime import datetime, timezone

from revenuechaser.core import job_lock
from revenuechaser.core.reporting_common import write_artifact
from revenuechaser.core.providers import deepseek, evren
from revenuechaser.module_value_chain import engine as vc_engine

from . import config
from . import profile_v3
from . import similarity
from . import store_reads as sr

logger = logging.getLogger(__name__)

#: A call that names no writer runs on ``config.default_writer()``, the registry's default, which is unpaid
#: (EVREN). Every function here defaulted to the paid ``deepseek`` until 20 Nov 2026 (avo: "Fetch ve build
#: sirasinda deepseek api kullanilan islem kalmasin hepsi evren deepseek olmali"); a Fetch always passed the
#: board's writer, so nothing scheduled changes, but a caller that forgets the argument no longer spends money.
#: A paid run names ``deepseek`` itself. It is resolved at call time, never bound into a signature.
NO_WRITER = ""
#: A partial answer's input hash carries this suffix, so the next run of the service redoes it.
PARTIAL = ":partial"


class RunStopped(RuntimeError):
    """A profile run stopped early. Nothing raises it since #1520: it belonged to the board's own writer (a
    DeepSeek peak hour, an auth failure, repeated transient failures, a free writer's unusable replies, no spine,
    or a business text the SEC form reader could not serve). The SEC reading service carries those rules now
    (``rcdata/build/sec_reads/asker.py``). Kept as the name the board's callers catch.
    """

    def __init__(self, reason: str, next_off_peak=None, message: str | None = None):
        self.reason = reason
        self.next_off_peak = next_off_peak
        self.message = message
        super().__init__(message or reason)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def select_pilot(limit: int | None = None) -> list[str]:
    """The shared classification universe (no market-cap floor), cap-descending.

    One selector for every classification board (core/universe.py). ``limit``
    caps the set for tests/demos.
    """
    from revenuechaser.core.universe import BOARD_OPERATING_ONLY, classification_universe
    # The board's type filter (PR 2): profiles need a 10-K, so operating companies only by default.
    tickers = classification_universe(operating_only=BOARD_OPERATING_ONLY["module_relatedness"])
    return tickers[:limit] if limit else tickers


def _save(path, data: dict) -> None:
    """Write the payload atomically (REL-11): a crash mid-write leaves the previous file whole."""
    write_artifact(path, json.dumps(data, ensure_ascii=False))


# What the service says a profile was read from (``read_answer.input_kind``), in the board's words.
_SERVICE_INPUT = {"section:business": "item", "located": "llm_locator"}


def service_rows(tickers: list[str] | None = None) -> list[dict]:
    """The board's profile rows, read straight from the SEC reading service's ``company.profile`` answers (#894
    step 3b; avo, 24 Nov 2026: "Relatedness da Value chain gibi olsun, ek kopyalamaya gerek yok"). No model call,
    no SEC request, and nothing is written: the rows have the shape of ``relatedness_profiles`` (plus
    ``attributes``, the tag lists) so the store's readers serve them as they served the table.

    ``tickers`` None (or empty) is the whole board (``select_pilot``). Every ticker of a company gets its company's
    answer; a company the service has no answer for is absent. The key carries the service's input hash, writer and
    filing, and ``fetched_at`` is when the service asked, so the scoring gate sees a new answer the day it lands.
    A failing read raises: an empty board must never be saved over the last good payload.
    """
    from revenuechaser.rcdata import read
    from . import store
    tickers = [t.upper() for t in tickers] if tickers else select_pilot()
    # The layer's company, never ``_cik_for``'s SEC ticker map: that one downloads, and a Refresh is zero-network.
    got = {str(c["ticker"]).upper(): str(c.get("cik") or "") for c in read.fundamental_companies(tickers)}
    ciks = {t: got.get(t, "") for t in tickers}
    wanted = {read._cik(c) for c in ciks.values() if c}
    answers = {read._cik(r["cik"]): r for r in read.sec_reads(wanted, "company.profile")} if wanted else {}
    # A company the service found no text for is ``no_text`` on the board, counted apart, not pending (195 of the
    # 199 "pending" on 25 Nov 2026 were these).
    unread = wanted - set(answers)
    no_text = ({read._cik(r["cik"]): r for r in read.sec_reads(unread, "company.profile", statuses=("no_text",))}
               if unread else {})
    # shortcut: a company the service leaves out (SIC 6770) gets no ``shell`` row here and counts as pending.
    out = []
    for t in tickers:
        cik = read._cik(ciks.get(t)) if ciks.get(t) else ""
        if cik in no_text:
            r = no_text[cik]
            out.append({"ticker": t, "cik": str(ciks.get(t)), "model": r.get("model"),
                        "prompt_version": r.get("prompt_version"), "fetched_at": r.get("fetched_at"),
                        "cache_key": "", "status": "no_text", "attempts": int(r.get("attempts") or 0),
                        "provider": r.get("provider"), "profile_json": None, "label_source": None,
                        "accession": r.get("accession") or None,
                        "attributes": {f: [] for f in config.PROFILE_FIELDS}})
            continue
        r = answers.get(cik)
        v3 = (r or {}).get("answer")
        if not v3 or not isinstance(v3, dict):
            continue
        partial = r["status"] == "partial"
        ck = store.cache_key(r["model"], False, "", r["prompt_version"], t,
                             r["input_hash"] + (PARTIAL if partial else ""), provider=r["provider"],
                             source={"cik": r["cik"], "accession": r["accession"], "form": r.get("form"),
                                     "filed": r.get("filing_date")})
        kind = str(r.get("input_kind") or "")
        labels = {"input": _SERVICE_INPUT.get(kind, "whole_document" if kind.startswith("whole") else kind),
                  "from": "sec/reads"}
        if r.get("missing_chunks"):
            labels["missing_chunks"] = [int(i) for i in str(r["missing_chunks"]).split(",") if i]
        shell = profile_v3.is_shell(v3)
        out.append({"ticker": t, "cik": str(ciks.get(t) or ""), "model": r["model"],
                    "prompt_version": r["prompt_version"], "fetched_at": r.get("fetched_at"), "cache_key": ck,
                    "status": "shell" if shell else "ok", "attempts": int(r.get("attempts") or 0),
                    "provider": r["provider"], "profile_json": v3, "label_source": labels,
                    "accession": r.get("accession") or None,
                    "attributes": ({f: [] for f in config.PROFILE_FIELDS} if shell
                                   else profile_v3.to_attributes(v3))})
    return out


def _writer(provider: str) -> tuple[str, bool, str]:
    """``(model, thinking, effort)`` a profile written by ``provider`` records in its cache key.

    DeepSeek's are the profile mode's; EVREN is sent no DeepSeek knob (#360). Staleness compares the writer's
    provider and model (``store.is_stale``). Which writer answered is the service's doing now (#1520): the board
    reads it off the answer and names it per company."""
    if provider == "evren":
        return evren.MODEL, False, ""
    return deepseek.MODEL, False, ""         # v3 sends no thinking (#400)


def build_profiles(tickers: list[str], use_llm: bool = True,
                   workers: int | None = None,
                   usd_cap: float | None = None,
                   provider: str = NO_WRITER,
                   max_calls: int | None = None,
                   model: str | None = None) -> dict[str, dict]:
    """``{ticker: {field: [str, ...]}}`` of ``tickers``: the SEC reading service's answers, read where they are.

    It calls nobody and writes nothing. The board had its own writer here until #1520 (avo's "Sil simdi",
    25 Nov 2026): ~300 lines that read a filing, cut its business section, asked DeepSeek or EVREN for a v3
    profile and saved it to ``relatedness_profiles`` / ``relatedness_attributes``, with the attempt, shell, peak,
    budget and unusable rules around it. The service owns every one of those now
    (``rcdata/build/sec_reads/company_profile.py``), and both tables are retired
    (``rawstore.RETIRED_TABLES``), so this is a read (``store.load_profiles`` -> ``service_rows``).

    Every argument is kept because the callers pass them (the dashboard's ``usd_cap``, the CLI's ``--limit``, the
    board's writer): none of them can reach a model from here any more.
    """
    from . import store
    return store.load_profiles(tickers)


# The shared coarse / medium / fine order. It names theme levels directly and
# maps co-movement's three cuts (broad -> tight, docs/dashboard_ui.md §8) so the
# first cut is Coarse and the last is Fine.
_LEVELS = ("coarse", "medium", "fine")


def _theme_levels() -> dict[str, dict]:
    """``{ticker: {coarse/medium/fine: label}}`` for the current theme run.

    The level comes from the ticker's ``ticker_themes`` rows (the current run
    only) but the **label** comes from ``core.universe.theme_catalog`` — the one
    Theme vocabulary — so Relatedness, Co-movement and Sector Rotation read the
    same coarse label. Store-only: a missing table, an unpinned run, or a query
    failure yields an empty map so a company simply carries empty theme strings.
    """
    try:
        from revenuechaser.core.universe import theme_catalog
        from . import themes as rel_themes
        run_id = rel_themes.current_run_id()
        if not run_id:
            return {}
        rows = sr.ticker_theme_levels(run_id)
        catalog = theme_catalog()
    except Exception:  # noqa: BLE001 - optional enrichment, never fatal
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        level = r.get("level")
        if level not in _LEVELS:
            continue
        label = (catalog.get(r.get("theme_id")) or {}).get("label")
        if label is None:
            label = r.get("theme") or ""      # no catalog row: fall back to the copy
        out.setdefault(r["ticker"], {})[level] = label
    return out


def _cluster_levels() -> dict[str, dict]:
    """``{ticker: {level: cluster_id}}`` from the latest default run.

    Reads the co-movement board's own default ``(horizon, benchmark)`` — a
    hardcoded ``horizon = 5`` went stale the moment that default moved to 1d
    (S7). Empty when no matching run exists, so the peer row omits the chips.

    Among those runs: the newest prices first, then the board's default window
    (a Fetch also stores other windows, #95, which must not displace it), then
    the latest.
    """
    from revenuechaser.module_comovement import config as comov_config
    from revenuechaser.module_comovement import settings as comov_settings
    from revenuechaser.module_comovement import store_reads as comov_reads

    as_of = comov_reads.default_run_as_of(
        comov_config.DEFAULT_HORIZON, comov_config.DEFAULT_BENCHMARK,
        comov_settings.effective().default_window)
    if not as_of:
        return {}
    try:
        cuts = comov_reads.cuts_of_run(as_of)
        member_rows = comov_reads.cluster_members(as_of)
    except Exception:  # noqa: BLE001 - optional enrichment, never fatal
        return {}
    level_by_cut = {c: _LEVELS[i] for i, c in enumerate(cuts)
                    if i < len(_LEVELS)}
    out: dict[str, dict] = {}
    for r in member_rows:
        level = level_by_cut.get(r["cut"])
        if level:
            out.setdefault(r["ticker"], {})[level] = r["cluster_id"]
    return out


def _same_clusters(cluster_map: dict, focal: str, peer: str) -> dict | None:
    """Per level, whether ``focal`` and ``peer`` share a cluster id."""
    if not cluster_map or not focal or not peer:
        return None
    a = cluster_map.get(focal) or {}
    b = cluster_map.get(peer) or {}
    out = {lvl: (a.get(lvl) == b.get(lvl))
           for lvl in _LEVELS if a.get(lvl) is not None and b.get(lvl) is not None}
    return out or None


def _attach_peer_market(peers: dict) -> None:
    """Attach ``move`` / ``beyond_spy`` / ``cluster`` to every focal's peers (store-only).

    Loads closes for the focals, their peers and SPY only, and correlates just
    the unique (focal, peer) pairs - never an N-by-N matrix, so it covers every
    focal. The values equal the matrix entries (same pairwise-complete rule and
    ``min_periods``). Horizons with too little overlap are omitted rather than
    filled with a fake ``0.0``.
    """
    if not peers:
        return
    from revenuechaser.module_comovement import config as comov_config
    from revenuechaser.module_comovement import ohlc as comov_ohlc
    from revenuechaser.module_comovement import returns as comov_returns
    from revenuechaser.module_comovement import settings as comov_settings

    focals = set(peers)
    peer_tickers = {p.get("peer") for entries in peers.values() for p in entries}
    price_tickers = sorted((focals | peer_tickers) - {None} | {"SPY"})
    try:
        # ``log_returns`` uses the last ``window + horizon`` sessions only, so read just those (#388): the same
        # rows, not every stored bar.
        need = comov_settings.effective().window + max(comov_config.HORIZONS)
        prices = comov_ohlc.price_frame(price_tickers, start=comov_ohlc.window_start(price_tickers, need))
    except Exception:  # noqa: BLE001 - missing/empty store must not break a run
        return
    if prices is None or getattr(prices, "empty", True):
        return

    pairs = list(dict.fromkeys(
        (focal, p["peer"]) for focal, entries in peers.items()
        for p in entries if p.get("peer") is not None))

    move_by_pair: dict[tuple[str, str], dict[int, float]] = {}
    default_ret = None
    for n in comov_config.HORIZONS:
        ret, _dropped = comov_returns.log_returns(prices, horizon=n)
        if n == comov_config.DEFAULT_HORIZON:
            default_ret = ret          # reused below, not recomputed
        if ret.empty:
            continue
        for pair, value in zip(pairs, comov_returns.pair_correlation(ret, pairs)):
            if not math.isnan(value):
                move_by_pair.setdefault(pair, {})[int(n)] = round(float(value), 4)

    spy_by_pair: dict[tuple[str, str], float] = {}
    if default_ret is None:
        default_ret, _dropped = comov_returns.log_returns(
            prices, horizon=comov_config.DEFAULT_HORIZON)
    if not default_ret.empty and "SPY" in default_ret.columns:
        cols = [c for c in default_ret.columns if c != "SPY"]
        if cols:
            resid = comov_returns.residualize(default_ret[cols], default_ret["SPY"])
            for pair, value in zip(pairs, comov_returns.pair_correlation(resid, pairs)):
                if not math.isnan(value):
                    spy_by_pair[pair] = round(float(value), 4)

    cluster_map = _cluster_levels()
    for focal, entries in peers.items():
        for p in entries:
            other = p.get("peer")
            move = move_by_pair.get((focal, other))
            if move:
                p["move"] = dict(move)
            spy = spy_by_pair.get((focal, other))
            if spy is not None:
                p["beyond_spy"] = spy
            same = _same_clusters(cluster_map, focal, other)
            if same:
                p["cluster"] = same


def _changed_since(as_of, profiles: dict[str, dict], stored: set[str]) -> tuple[set[str], set[str]] | None:
    """``(changed, gone)`` against a saved payload's ``as_of``: the profiles stored since it (plus the names new to
    the board) and the names the payload scored that are no longer profiled. ``None`` when ``as_of`` is unreadable."""
    try:
        cutoff = datetime.fromisoformat(str(as_of)).timestamp()
    except (TypeError, ValueError):
        return None
    from . import store
    changed = {r["ticker"] for r in store.profile_rows(list(profiles))
               if r["ticker"] in profiles and float(r.get("fetched_at") or 0) > cutoff}
    return changed | (set(profiles) - stored), stored - set(profiles)


def _incremental_peers(profiles: dict[str, dict], pjs: dict[str, dict], vectors: dict, sectors: dict,
                       reuse: dict):
    """``(peers, fresh, counts)`` from the saved payload plus the rows a changed profile touches (#1132), or
    ``None`` when the full matrix has to be scored after all: an unreadable payload date, or more of the board
    changed than ``config.INCREMENTAL_MAX_SHARE``."""
    from . import incremental
    stored_peers = reuse.get("peers") or {}
    stored = {c.get("ticker") for c in (reuse.get("companies") or []) if c.get("ticker")} | set(stored_peers)
    moved = _changed_since(reuse.get("as_of"), profiles, stored)
    if moved is None:
        return None
    changed, gone = moved
    tickers = sorted(profiles)
    rows = incremental.rows_to_rescore(stored_peers, tickers, changed, gone)
    share = len(rows) / len(tickers) if tickers else 1.0
    if share > config.INCREMENTAL_MAX_SHARE:
        logger.info("relatedness: %d of %d profiles changed, %d rows to score (%.0f%% of the board); "
                    "scoring the whole matrix", len(changed), len(tickers), len(rows), 100 * share)
        return None
    logger.info("relatedness: %d changed profiles, %d of %d rows scored, %d lists carried",
                len(changed), len(rows), len(tickers), len(tickers) - len(rows))
    blend = similarity.Blend(profiles, pjs, vectors, sectors)
    peers, fresh = incremental.peer_lists(blend, stored_peers, rows, changed, config.TOP_PEERS)
    return peers, fresh, {"changed": len(changed), "rows": len(rows), "carried": len(tickers) - len(rows)}


def _peers(profiles: dict[str, dict], companies: list[dict], write: bool, reuse: dict | None = None):
    """``(peers, scores, method, pjs, incremental)``: similarity v2 on the local embeddings when any profile has a
    vector (#669), else the tag cosine. A failing embedder (no model file, no network for its first download) falls
    back to the tag cosine with a warning, so the board still renders.

    ``reuse`` is a saved payload a whole-board Refresh may score incrementally against (#1132). Taken, ``scores``
    is ``None`` (no upper triangle was built) and the fifth value carries ``(fresh, counts)``: the entries this run
    made, and what it scored. The tag cosine never takes it -- its idf is run-wide, so no pair's score survives a
    changed profile.
    """
    from . import embeddings, store
    pjs = store.load_profile_json(list(profiles))
    try:
        vectors = embeddings.company_vectors(pjs, write=write)
    except Exception as exc:  # noqa: BLE001 - the board renders on the tag cosine instead
        logger.warning("relatedness embeddings failed, scoring on tags: %s", exc)
        vectors = {}
    if vectors:
        # "Unclassified" is no sector two companies share (review of #680).
        sectors = {c["ticker"]: c["sector"] for c in companies if c["sector"] != "Unclassified"}
        try:
            if reuse is not None and len(profiles) > 1:
                try:
                    out = _incremental_peers(profiles, pjs, vectors, sectors, reuse)
                except Exception as exc:  # noqa: BLE001 - a saved payload this run cannot use costs time, not
                    # the board: the full matrix below scores it, and the tag cosine is not reached.
                    logger.warning("relatedness incremental scoring failed, scoring every pair: %s", exc)
                    out = None
                if out is not None:
                    peers, fresh, counts = out
                    return peers, None, "embedding", pjs, (fresh, counts)
            peers, scores = similarity.blended_peer_lists(profiles, pjs, vectors, sectors, config.TOP_PEERS)
            return peers, scores, "embedding", pjs, None
        except Exception as exc:  # noqa: BLE001 - a bad cached vector must not empty the board
            logger.warning("relatedness similarity v2 failed, scoring on tags: %s", exc)
    peers, scores = similarity.peer_lists(profiles, config.TOP_PEERS)
    return peers, scores, "tags", pjs, None


def _score_grid(arr) -> list[float]:
    """``config.SCORE_QUANTILES`` points of a run's sorted pair scores, saved in the payload so the next
    incremental run can rank a new peer without the upper triangle (#1132)."""
    import numpy as np
    if not len(arr):
        return []
    idx = np.linspace(0, len(arr) - 1, min(config.SCORE_QUANTILES, len(arr))).astype("int64")
    return [round(float(x), 6) for x in np.asarray(arr)[idx]]


def _payload(profiles: dict[str, dict], stale: set[str] | None = None, model: str | None = None,
             write: bool = False, reuse: dict | None = None) -> dict:
    from revenuechaser.core.gics_map import canonical_sector, sector_path
    from revenuechaser.core.universe import (BOARD_OPERATING_ONLY, classification_universe, filter_fields,
                                             theme_catalog)
    # One read of the company fields (#49): ``filter_fields`` carries name/sector/industry/market_cap already,
    # so the second ``equity_universe`` query this function used to run only risked disagreeing with it.
    from revenuechaser.module_value_chain import aliases
    from . import store
    meta = store.profile_meta(list(profiles))
    # Decision C (avo, 16 Nov 2026; #408): one row per CIK. GOOG/GOOGL share a filing and a profile, so each was the
    # other's top peer; the kept ticker lists its other classes.
    classes = aliases.share_class_groups([{"ticker": t, "cik": m.get("cik")} for t, m in meta.items()])
    twins = {t for others in classes.values() for t in others}
    profiles = {t: p for t, p in profiles.items() if t not in twins}
    extra = filter_fields(list(profiles))
    scale = similarity.idf(profiles)       # one idf for the company weights and the peer scores (#395)
    themes = _theme_levels()
    sources = {t: store.profile_source(m.get("cache_key")) for t, m in meta.items() if t in profiles}
    companies = []
    for t in sorted(profiles):
        x = extra.get(t) or {}
        tl = themes.get(t) or {}
        companies.append({
            "ticker": t,
            "name": x.get("name") or t,
            # An old GICS spelling still in the store reads as its Morningstar name (filter_fields normalises it,
            # and ``canonical_sector`` is idempotent on the names it returns).
            "sector": canonical_sector(x.get("sector")),
            "industry": x.get("industry") or "",
            "market_cap": x.get("market_cap"),
            "earnings_date": x.get("earnings_date"),
            "index": x.get("index") or [],
            # The shared filter row (core.universe.filter_fields, #383 C1b): the sector path and every level of
            # the pinned theme run the Theme facet filters on.
            "gics": x.get("gics") or sector_path(canonical_sector(x.get("sector")),
                                                 x.get("industry") or ""),
            "theme_ids": x.get("theme_ids") or [],
            "theme_coarse": tl.get("coarse") or "",
            "theme_medium": tl.get("medium") or "",
            "theme_fine": tl.get("fine") or "",
            "stale": t in (stale or ()),
            "also": classes.get(t, []),
            # Build plan PR 20 (G6): the filing the profile was read from (CIK, accession, form, filed).
            "source": sources.get(t),
            "weights": similarity.term_weights(profiles[t], scale),
            "profile": profiles[t],
        })

    names = {c["ticker"]: c["name"] for c in companies}
    import numpy as np
    peers, raw_scores, method, pjs, incr = _peers(profiles, companies, write, reuse=reuse)
    # ``n_pairs`` is every unordered pair of profiled tickers; the tag path ranks a peer among the scored
    # (non-zero) pairs only (#395, review RL-3): with two thirds of the pairs at zero, a 0.06 peer read as p90.
    # The embedding path (#669) scores every pair, so there it ranks among all of them.
    n_pairs = len(profiles) * (len(profiles) - 1) // 2
    if incr is None:
        # float32 for the v2 path: every pair is kept (~12.5M at 5,000 names), so no float64 copy (review of #680).
        arr = (np.sort(np.asarray(raw_scores, dtype="float32" if method == "embedding" else "float64"))
               if len(raw_scores) else np.zeros(0))
        grid = _score_grid(arr)
        n_scored = len(arr)
        rank_over, scored = arr, peers
    else:
        # Incremental Refresh (#1132): only this run's own entries are ranked and priced; a carried entry keeps the
        # name, percentile and market stats the run that scored it gave it. The percentile is read off the saved
        # grid, because the upper triangle was never built -- a handful of changed profiles out of thousands moves
        # the distribution by less than the grid's 0.1-percentile resolution.
        fresh, counts = incr
        grid = [float(x) for x in (reuse or {}).get("score_quantiles") or []]
        rank_over = np.asarray(grid, dtype="float64")
        n_scored = int((reuse or {}).get("n_scored") or 0)
        scored = fresh
    for a in scored:
        for p in scored[a]:
            p["name"] = names.get(p["peer"]) or p["peer"]
            raw = p.pop("score_raw", p["score"])    # compare the unrounded score
            p["percentile"] = (round(100.0 * float(np.searchsorted(rank_over, raw, side="left")) / len(rank_over), 1)
                               if len(rank_over) else 0.0)

    # Market stats for every focal's peers, computed pair-only (never N x N); incrementally, for this run's own
    # pairs only.
    _attach_peer_market(scored)

    payload = {
        "as_of": _now(),
        "model": model or deepseek.MODEL,
        "n": len(companies),
        "companies": companies,
        "peers": peers,
        "n_pairs": n_pairs,
        "n_scored": n_scored,
        "similarity": method,
        "fields": list(config.PROFILE_FIELDS),
        # Plan 16 Nov step 12 (V3): profiles that name no customer, supplier or competitor at all (live: 900, MSFT
        # and AAPL among them). Value Chain gets no edge from them; the prompt fix waits for #894.
        "no_parties": sorted(t for t in profiles
                             if not any((pjs.get(t) or {}).get(k) for k in aliases.PROFILE_PARTIES)),
        "universe_total": len(classification_universe(operating_only=BOARD_OPERATING_ONLY["module_relatedness"])),
        "theme_catalog": theme_catalog(),
        # The score grid the next incremental Refresh ranks against (#1132); an incremental run carries the grid of
        # the full run that built it.
        "score_quantiles": grid,
    }
    if incr is not None:
        payload["incremental"] = dict(counts)
    return payload


def _stop_health(provider: str, reason: str | None, message: str | None) -> dict | None:
    """The banner's health when this run stopped on a provider failure (#80).

    A peak stop is a schedule, not a failed call, so it leaves the banner empty. ``auth`` carries
    HTTP 401 so the banner names a rejected key."""
    if reason not in ("auth", "transient", "unusable"):
        return None
    name = provider or "deepseek"
    return {"provider": name, "calls": 1, "failed": 1,
            "auth_error": {"status": 401} if reason == "auth" else None,
            "failures": [{"endpoint": name, "error": message or reason}],
            "breaker_open": False, "skipped_calls": 0}


class AlreadyRunning(RuntimeError):
    """A Fetch run holds the ``relatedness`` job lock."""


def run(no_fetch: bool = False, tickers: list[str] | None = None,
        limit: int | None = None, usd_cap: float | None = None, run_id: str | None = None,
        provider: str = NO_WRITER, max_calls: int | None = None, model: str | None = None) -> dict:
    """A Fetch of the profiles and scores. ``run_id`` is kept for the callers; the result history it keyed went with
    history.duckdb (#860).

    ``provider`` is the profile writer (``writers.WRITERS``, #360): the CLI and the dashboard pass the board's
    (``settings.writer``); a call without one runs on ``config.default_writer()``, the unpaid EVREN. A free writer
    (``evren``) writes the missing and stale profiles with no call cap unless ``max_calls`` is given (``limit``
    slices the names). ``model`` is the board's model (``None``: the chat module's ``MODEL``). Mixed writers (avo,
    11 Nov 2026): every writer's current profile is shown and scored; each company names its writer."""
    provider = provider or config.default_writer()
    if no_fetch:
        if tickers is None and limit is None:
            cached = _reusable_payload(provider, model)
            if cached is not None:
                return cached
            # Something is newer than the saved payload. Score the pairs it touches, not the matrix (#1132).
            return _run(True, tickers, limit, usd_cap, provider=provider, model=model, reuse=_incremental_base())
        return _run(True, tickers, limit, usd_cap, provider=provider, model=model)
    # Scheduled (CLI) and dashboard Fetch runs must not overlap. Refresh writes
    # nothing, so it never needs the lock.
    with job_lock.acquire("relatedness", wait=0) as got:
        if not got:
            raise AlreadyRunning("Another Relatedness run is already in progress.")
        if provider == "deepseek" and model is None:
            payload = _run(False, tickers, limit, usd_cap, run_id, provider=provider)
        else:
            payload = _run(False, tickers, limit, usd_cap, run_id, provider=provider, max_calls=max_calls,
                           model=model)
        # Decision F (avo, 16 Nov 2026): a whole-board Fetch keeps its peer scores in the store. A sliced run scored
        # a subset only, and syncing it would retire every other pair.
        if tickers is None and not limit:
            from . import store
            store.save_scores(payload.get("peers") or {})
        return payload


def score(only_if_new: bool = True, provider: str = NO_WRITER, model: str | None = None) -> dict:
    """Rescore every pair from the SEC service's answers, persist the scores and the payload. No call.

    The scoring step of #884, **daily and only when the SEC reading service answered something new** (avo, 20 Nov
    2026: "Sec raporunda degisiklik var ise yapilacak sekilde ayarla, gunluk olsun"; his 16 Nov weekly Sunday word
    was what the cadence was before). It is the Fetch's second half:

    * the profiles are the service's ``company.profile`` answers, read where they are (``service_rows``,
      #894 step 3b; the board copied them into its own tables until then, and #1520 retired those). Each carries
      the time the service asked, so the gate below sees a new answer the day it lands, and a day on which the
      service read nothing changes nothing;
    * then it rescores. What it does that a Refresh does not: it writes. The new company vectors are cached
      (``relatedness_embeddings``) and the peers go to ``relatedness_scores``, so the next render reads them
      instead of making them again.

    It calls no writer and spends nothing: there is no path from this board to a model any more (#1520).

    ``only_if_new`` skips the day whose profiles are all older than the saved payload (the comparison
    ``_reusable_payload`` makes); the answer then carries ``skipped`` and nothing is written. ``--force`` rescores
    anyway. It holds the board's job lock, as a Fetch does, because it writes.
    """
    from . import store
    provider = provider or config.default_writer()
    with job_lock.acquire("relatedness", wait=0) as got:
        if not got:
            raise AlreadyRunning("Another Relatedness run is already in progress.")
        if only_if_new:
            cached = _reusable_payload(provider, model)
            if cached is not None:
                logger.info("relatedness score: no profile is newer than the saved payload (%s); nothing rescored",
                            cached.get("as_of"))
                return {**cached, "skipped": "no profile is newer than the saved payload"}
        payload = _run(True, None, None, None, provider=provider, model=model, write=True)
        store.save_scores(payload.get("peers") or {})
        return payload


def _run(no_fetch: bool, tickers: list[str] | None, limit: int | None,
         usd_cap: float | None, run_id: str | None = None, provider: str = NO_WRITER,
         max_calls: int | None = None, model: str | None = None, write: bool | None = None,
         reuse: dict | None = None) -> dict:
    # ``write`` overrides the default "a Fetch writes, a Refresh does not" (``not no_fetch``): the weekly scoring
    # step fetches nothing and still writes its vectors (``score``).
    from . import store
    provider = provider or config.default_writer()
    tickers = select_pilot() if tickers is None else list(tickers)
    if limit:
        tickers = tickers[:limit]
    # On the layer Relatedness reads the filings the layer serves, so downloading ``chain_filings`` again is wasted
    # (plan 11 Nov 2026, F3: about 4,970 SEC files for a full Fetch).
    from revenuechaser.core import fundamentals_layer
    vc_engine.fetch_corpus(tickers, no_fetch=no_fetch or fundamentals_layer.reads_layer())

    # The profiles are a read of the service's answers (#1520), so this board has no peak hour, no day cap and no
    # unusable reply of its own to stop on: the DeepSeek branches that caught those are gone with its writer. A
    # ``RunStopped`` is still rendered rather than raised, because it is what the board's banner reads (#80).
    next_off_peak = None
    stopped_reason = None
    stopped_message = None
    try:
        profiles = build_profiles(tickers, use_llm=not no_fetch, usd_cap=usd_cap, provider=provider,
                                  max_calls=max_calls, model=model)
    except RunStopped as exc:
        stopped_reason, next_off_peak, stopped_message = exc.reason, exc.next_off_peak, exc.message
        profiles = store.load_profiles(tickers)

    # "Profiled" counts usable profiles only: empty / no_text / short_text rows are not done. Mixed writers (avo,
    # 11 Nov 2026): another writer's profiles stay current and in the matrix; the board names each one's writer.
    writer = (provider, model or _writer(provider)[0])
    other = store.other_writer_tickers(list(profiles), writer)
    profiles = {t: p for t, p in profiles.items() if any(p.values())}
    payload = _payload(profiles, stale=store.stale_tickers(list(profiles), writer=writer), model=writer[1],
                       write=(not no_fetch) if write is None else write, reuse=reuse)
    by_writer = store.profile_writers(list(profiles))
    for c in payload.get("companies") or []:
        c["writer"] = by_writer.get(c["ticker"])
    payload["other_writer"] = len(other)
    payload["writer"] = {"provider": writer[0], "model": writer[1]}
    # Pending is what a next run can still profile (#388 D4): a name whose filing has no text, or one too short to
    # profile from (#313), waits for a better filing, not for the writer, so both are counted apart.
    meta_now = store.profile_meta(tickers)
    no_text = {t for t, m in meta_now.items() if m["status"] == "no_text" and t not in profiles}
    short_text = {t for t, m in meta_now.items() if m["status"] == "short_text" and t not in profiles}
    # A shell (#400) is no company to profile: neither a peer nor pending.
    shell = {t for t, m in meta_now.items() if m["status"] == "shell" and t not in profiles}
    payload["no_text"] = len(no_text)
    payload["short_text"] = len(short_text)
    payload["shell"] = len(shell)
    # Which companies' Item the writer located from the headings (avo, 8 Nov 2026: logged per company).
    payload["llm_located"] = sorted(
        r["ticker"] for r in store.profile_rows(tickers)
        if r["ticker"] in set(tickers) and isinstance(r.get("label_source"), dict)
        and r["label_source"].get("input") == "llm_locator")
    payload["pending"] = max(0, len(tickers) - len(profiles) - len(no_text) - len(short_text) - len(shell))
    if next_off_peak is not None:
        payload["next_off_peak"] = next_off_peak.strftime("%Y-%m-%d %H:%M")
    if stopped_reason:
        payload["stopped_reason"] = stopped_reason
    if stopped_message:
        payload["error"] = stopped_message
    # The banner reads this key (#80). A Refresh has no live provider call: the last Fetch's stored health.
    health = _stop_health(provider, stopped_reason, stopped_message)
    if health:
        payload["provider_health"] = health
    _save(config.RELATEDNESS_JSON, payload)
    return payload


def _reusable_payload(provider: str, model: str | None) -> dict | None:
    """The saved payload (``RELATEDNESS_JSON``) when a Refresh of the whole board can render it as it is: no stored
    profile is newer than its ``as_of``, whichever writer wrote it, for the scores the run had just written.
    Scoring every pair is not what makes that worth avoiding: it is ~27 s of CPU for 5,111 profiles on the server
    (measured 20 Nov 2026, #884), and the ~2 h read off the 15 Nov 2026 run was somewhere else in the run -- #1163
    measures where. What the saved payload still skips is the market stage (~16 s) and assembling the 41 MB JSON."""
    payload = load_payload()
    as_of = payload.get("as_of")
    if not as_of or not payload.get("companies"):
        return None
    # The writer is not compared: another writer's profiles stay current and in the matrix (avo, 11 Nov 2026), so
    # a payload the DeepSeek batch wrote serves a board whose writer is EVREN (measured 15 Nov 2026 19:27: the
    # writer check sent the Refresh back into a full rescoring).
    try:
        cutoff = datetime.fromisoformat(str(as_of)).timestamp()
    except ValueError:
        return None
    from . import store
    # A ``no_text`` row is no profile: the service re-checking a company with no text is nothing to rescore.
    newest = max((float(r.get("fetched_at") or 0) for r in store.profile_rows() if r.get("status") != "no_text"),
                 default=None)
    if newest is None or newest > cutoff:
        return None
    return payload


def _incremental_base() -> dict | None:
    """The saved payload a whole-board Refresh can score incrementally against (#1132), or ``None`` when it cannot:
    no payload, no score grid (one written before #1132), or a payload the tag cosine scored -- its idf is run-wide,
    so a changed profile moves every pair."""
    payload = load_payload()
    if not payload.get("as_of") or not payload.get("companies") or not payload.get("peers"):
        return None
    if payload.get("similarity") != "embedding" or not payload.get("score_quantiles"):
        return None
    return payload


def load_payload() -> dict:
    if config.RELATEDNESS_JSON.exists():
        try:
            return json.loads(config.RELATEDNESS_JSON.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            pass
    return {"as_of": None, "model": deepseek.MODEL, "n": 0, "companies": [],      # #392: no file, no data date
            "peers": {}, "n_pairs": 0, "fields": list(config.PROFILE_FIELDS)}
