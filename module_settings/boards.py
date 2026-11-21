"""Board inputs — what each board reads, its knobs, and its own funnel.

Store-only: a card is built from the board's last rendered payload JSON in
``.cache`` and never recomputes the board (zero network). The funnel shown is
the one the board itself emitted (``core.funnel`` format), so the Settings card
and the board cannot disagree. See ``docs/data_health.md``.

``funnel`` on an entry is the payload key the board emits (``funnel_steps``),
or ``no_funnel`` when the payload emits none. The card reads that key through
``core.funnel`` and does not invent steps. A missing artifact is
``not_rendered``. A funnel board whose payload has no steps is ``no_funnel``
(the existing "refresh" note). A ``no_funnel`` board never asks for a refresh
to grow a funnel it does not emit.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from RevenueChaser.core import board_settings
from RevenueChaser.core import funnel as funnel_mod
from RevenueChaser.core.config import OUTPUT_DIR
from RevenueChaser.core.universe import DEFAULT_MC_MIN
from RevenueChaser.module_comovement import config as comov_config
from RevenueChaser.module_comovement import settings as comov_settings
from RevenueChaser.module_comovement import store_reads as _comov
from RevenueChaser.module_fundamentals import settings as fund_settings
from RevenueChaser.module_news import store_reads as _news
from RevenueChaser.module_relatedness import store_reads as _rel
from RevenueChaser.module_swing_potential import config as swing_config
from RevenueChaser.module_swing_potential import settings as swing_settings


def _comovement_params() -> list[str]:
    """Plain-label knobs, read from ``module_comovement.config`` at call time."""
    c = comov_config
    eff = comov_settings.effective()
    bench = c.BENCHMARKS.get(c.DEFAULT_BENCHMARK) or "off"
    return [
        f"Window {eff.window} sessions",
        f"Min observations {eff.min_obs}",
        f"Out-of-sample holdout {eff.oos_holdout} sessions",
        ("Market-cap floor none (every member)" if not DEFAULT_MC_MIN
         else f"Market-cap floor ${DEFAULT_MC_MIN / 1e6:,.0f}M"),
        f"Default benchmark {bench}",
        f"Default horizon {c.DEFAULT_HORIZON} day",
        f"Price history {c.OHLC_PERIOD}",
        f"Winsorize at {eff.winsor_k} sigma",
    ]


_WINDOW_LABELS = {21: "1m", 42: "2m", 126: "6m", 189: "9m", 252: "1y", 378: "1.5y"}
_INPUT_KEYS = ("WINDOW", "MIN_OBS", "OOS_HOLDOUT")
_FINE_KEYS = ("WINSOR_K", "MIN_PERIODS", "BENCH_STALE_SESSIONS", "OPERATING_ONLY")

# The type filter's two values in words (PR 2), for the cards' select.
_TYPE_FILTER_LABELS = {0: "Every security type", 1: "Operating companies only"}


def _type_filter_field(f: dict) -> dict:
    """The ``OPERATING_ONLY`` row as a card prints it: a two-way choice, never a numeric range."""
    f["range"] = " or ".join(f"{c} = {_TYPE_FILTER_LABELS[c].lower()}" for c in f["choices"])
    f["choices"] = [[c, _TYPE_FILTER_LABELS[c]] for c in f["choices"]]
    return f


def _range_text(f: dict) -> str:
    """The allowed range, as the Settings card prints it next to the field."""
    key, lo, hi = f["key"], f["lo"], f["hi"]
    if key == "WINDOW":
        return ", ".join(_WINDOW_LABELS.get(c, str(c)) for c in f["choices"])
    if key == "MIN_OBS":
        return f"{lo:g}–WINDOW"
    if key == "MIN_PERIODS":
        return f"{lo:g}–MIN_OBS"
    return f"{lo:g}–{hi:g}"


def _comovement_settings() -> dict:
    """Editable inputs for the card: effective value, default, override flag, range."""
    rows = {f["key"]: f for f in board_settings.describe(comov_settings.BOARD)}
    for f in rows.values():
        if f["key"] == "OPERATING_ONLY":
            _type_filter_field(f)
            continue
        f["range"] = _range_text(f)
        if f["choices"] is not None:
            f["choices"] = [[c, f"{_WINDOW_LABELS.get(c, c)} ({c})"] for c in f["choices"]]
    holdout = int(rows["OOS_HOLDOUT"]["value"])
    return {
        "board": comov_settings.BOARD,
        "custom": any(f["overridden"] for f in rows.values()),
        "inputs": [rows[k] for k in _INPUT_KEYS],
        "fine": [rows[k] for k in _FINE_KEYS],
        "derived": {"key": "OOS_MIN_OBS",
                    "label": "Held-out observations needed (derived)",
                    "value": comov_settings.oos_min_obs_for(holdout)},
    }


def _plain_range(f: dict) -> str:
    """``lo–hi`` as the card prints it (every Swing key has both ends)."""
    return f"{f['lo']:g}–{f['hi']:g}"


_SWING_INPUT_KEYS = ("MIN_PRICE", "MIN_DOLLAR_VOLUME", "RS_MIN")
_SWING_FINE_KEYS = ("VOL_CONFIRM", "BREAKOUT_HIGH_PCT", "MOVE_MIN", "ADR_MIN",
                    "W_PROX", "W_CONS", "STOP_ATR", "TARGET_R", "OPERATING_ONLY")


def _swing_params() -> list[str]:
    """Plain-label knobs, read from the effective settings at call time (#384 SW-S4)."""
    e = swing_settings.effective()
    return [
        f"Minimum price ${e.min_price:g}",
        f"Minimum dollar volume ${e.min_dollar_volume:,.0f} a day",
        f"Relative strength rating {e.rs_min:g} (ranks only, a percentile among the scanned names)",
        f"Breakout volume {e.vol_confirm:g}× the 20-day average on one of the last {swing_config.VOL_WINDOW} sessions",
        f"Overhead breakout at {round(e.breakout_high_pct * 100, 2):g}% of the 52-week high",
        f"Preceding move {round(e.move_min * 100, 2):g}% over 1–3 months",
        f"Average daily range {round(e.adr_min * 100, 2):g}%",
        f"Stop {e.stop_atr:g}× the average true range · target {e.target_r:g}× the risk",
        f"Rank weights: proximity {e.w_prox:g}, consistency {e.w_cons:g}",
    ]


def _swing_settings() -> dict:
    """Editable thresholds for the Swing card: effective value, default, override flag, range."""
    rows = {f["key"]: f for f in board_settings.describe(swing_settings.BOARD)}
    for f in rows.values():
        if f["key"] == "OPERATING_ONLY":
            _type_filter_field(f)
        else:
            f["range"] = _plain_range(f)
    return {
        "board": swing_settings.BOARD,
        "custom": any(f["overridden"] for f in rows.values()),
        "inputs": [rows[k] for k in _SWING_INPUT_KEYS],
        "fine": [rows[k] for k in _SWING_FINE_KEYS],
    }


_FUND_INPUT_KEYS = ("MIN_PRICE", "MIN_DOLLAR_VOLUME")
_FUND_FINE_KEYS = ("OPERATING_ONLY",)


def _fundamentals_params() -> list[str]:
    """Plain-label knobs, read from the effective settings at call time (PR 2)."""
    e = fund_settings.effective()
    return [
        f"Minimum price ${e.min_price:g}",
        f"Minimum dollar volume ${e.min_dollar_volume:,.0f} a day",
        "Operating companies only" if e.operating_only else "Every security type",
    ]


def _fundamentals_settings() -> dict:
    """Editable inputs for the Fundamentals card (PR 2): the prefilter's two floors and the type filter."""
    rows = {f["key"]: f for f in board_settings.describe(fund_settings.BOARD)}
    for f in rows.values():
        if f["key"] == "OPERATING_ONLY":
            _type_filter_field(f)
        else:
            f["range"] = _plain_range(f)
    return {
        "board": fund_settings.BOARD,
        "custom": any(f["overridden"] for f in rows.values()),
        "inputs": [rows[k] for k in _FUND_INPUT_KEYS],
        "fine": [rows[k] for k in _FUND_FINE_KEYS],
    }


def llm_writers_card() -> dict:
    """The LLM writers card (#404): one row per LLM job, its chosen provider and model, and the writers it could
    run on. A writer whose credential is absent is offered greyed with the variable's NAME
    (``llm_writers.missing_text``), never a value; a paid writer is marked as paid.
    """
    from RevenueChaser.core import llm_jobs
    jobs = llm_jobs.options()
    return {
        "board": llm_jobs.BOARD,
        "jobs": jobs,
        "paid": [j["label"] for j in jobs if j["paid"]],
    }


# A board whose payload does not emit ``funnel_steps`` (or ``funnel``). The card
# degrades by showing reads and, when a JSON payload exists, its as-of — never
# by inventing steps or telling the user to Refresh for a funnel.
NO_FUNNEL = "no_funnel"


def _no_params() -> list[str]:
    return []


def _json(*parts: str) -> Path:
    """A regenerable payload under ``.cache`` (``RC_CACHE_DIR`` via ``OUTPUT_DIR``)."""
    return OUTPUT_DIR.joinpath(*parts)


def _html(name: str) -> Path:
    return OUTPUT_DIR / f"{name}_latest.html"


def _watchlists_latest() -> dict | None:
    """Watch lists has no artifact: the lists themselves are the board (#786). The newest list write is its as-of,
    and a store with no list yet reads as "not rendered", which is what the page should say."""
    from RevenueChaser.module_watchlists import store as wl_store
    rows = wl_store.lists()
    if not rows:
        return None
    newest = max(float(r.get("updated_at") or 0.0) for r in rows)
    return {"as_of": datetime.fromtimestamp(newest, tz=timezone.utc).isoformat() if newest else None}


def _spx_latest() -> dict | None:
    """SPX Gamma's latest pointer lives in its board file (``spx_meta``), not in a file (review F4)."""
    from RevenueChaser.module_spx_gamma import store as spx_store
    return spx_store.latest()


def _leaps_latest() -> dict | None:
    """LEAPS has no artifact (#746): the newest session of ``option_far_contract`` is its as-of, none yet is
    "not rendered"."""
    from RevenueChaser.rcdata import read
    sessions = read.far_contract_sessions()
    return {"as_of": str(sessions[0]["session_date"])} if sessions else None


def _hit_rate_latest() -> dict | None:
    """Hit Rate has no artifact (#25): the newest freeze date in ``forecast_ledger`` is its as-of."""
    from RevenueChaser.core import rawstore
    rows = rawstore.query("SELECT max(forecast_date) AS d FROM forecast_ledger", db="forecast")
    return {"as_of": str(rows[0]["d"])} if rows and rows[0]["d"] is not None else None


def _board(key: str, label: str, tables: list[str], payload_path, *,
           funnel: str = NO_FUNNEL, price_basis: str = "", params=None,
           settings=None, ops_tables: list[str] = ()) -> dict:
    row = {
        "key": key, "label": label, "tables": list(tables), "ops_tables": list(ops_tables),
        "price_basis": price_basis, "params": params or _no_params,
        "payload_path": payload_path, "funnel": funnel,
    }
    if settings is not None:
        row["settings"] = settings
    return row


# Nav order (``app/dashboard.py`` TABS), minus Settings and Logs. ``tables`` are the
# **board-file** tables each board's engine or pipeline reads, not the tables it writes; ``ops_tables`` the
# ops.sqlite tables it reads (the stock watch list, PR 4). ``funnel_steps`` only where the rendered payload emits
# that list.
#
# What a board reads from the builder's serving files is **not** typed here (#642 N1): the card takes it from the
# board's own ``READS`` through ``rcdata.needs.boards.reads_of``, so the card, the flow diagram and the board
# cannot disagree, and a retired table cannot stay on this screen as a second copy of the record. Every name below
# is a table of a board file (``core.rawstore.MANIFEST``), and a test holds that.
BOARD_INPUTS: list[dict] = [
    # Welcome (decision A) and News (S9, S16) write their own board files; these are the stored tables they read.
    # #643 PR 5: the four market tiles read market.duckdb's ``market_series`` through their needs, so the three
    # old series tables are gone from this record; the earnings and freshness cards read the old files and went
    # with them (#860).
    # The three News tables by the News board's own names (#217), and ``news_headlines`` among them: the Welcome
    # card has always read the headlines too (``module_welcome/report.py`` ``_headlines_card``), and this record
    # left it out.
    _board("module_welcome", "Welcome",
           [_news.EVENTS, _news.HIGHLIGHT, _news.HEADLINES],
           lambda: _html("welcome"), price_basis="last stored closes, not live quotes",
           ops_tables=["watchlist_stock"]),
    # Watch lists (#786) is avo's own typed data, not a board result: nothing recomputes it, there is no artifact
    # and no Fetch. Its card accounts for the four tables of ``boards/watchlists.duckdb``; the numbers beside each
    # symbol come from the rcdata needs the package declares (``module_watchlists/__init__.py`` READS).
    _board("module_watchlists", "Watch lists",
           ["wl_list", "wl_section", "wl_item", "wl_change"], _watchlists_latest,
           price_basis="last stored closes through rcdata, not live quotes"),
    _board("module_news", "News", [], lambda: _html("news")),      # reads market.economic_event, market.fda_event
    # #860: ``earnings_calendar``, ``estimate_snapshots``, ``short_interest`` and ``price_bars_daily`` went with
    # the old store; what the board reads is served (its needs) and its own rows are the render's.
    _board("module_earnings_radar", "Earnings Radar", [],
           lambda: _html("earnings_radar"),
           price_basis="daily price bars, nominal closes for reactions", ops_tables=["watchlist_stock"]),
    # #860: the old ``index_levels_daily`` went with the price file; the board's own ``spx_*`` rows are its file's.
    _board("module_spx_gamma", "SPX Gamma",
           [], _spx_latest,
           price_basis="the index closes of its own stored snapshots"),
    # #1059: the board fits ``option_eod`` of the nightly options build through ``rcdata.read``; its own
    # ``oipd_chain`` / ``oipd_meta`` are no longer written, so they are not its inputs.
    _board("module_oipd", "Implied Probability",
           [], lambda: _json("oipd", "oipd_latest.json"),
           price_basis="option chain marks, not equity closes"),
    _board("module_financials", "Financials",
           [],
           lambda: _json("financials", "financials_latest.json")),
    _board("module_comovement", "Co-movement",
           # The engine reads the daily price bars since #379 (module_comovement/ohlc.py) and the universe from
           # the spine (#642 PR 6), both served. It does read its *own* dated runs back, which this record used
           # to deny: a Refresh re-renders from them with zero network, a store-only run serves one, and the
           # persistence verdicts come from the newest run with the same config hash. The names come from the
           # board's one reader (#217), so a rename is a change to one file.
           [_comov.RUNS, _comov.NODES, _comov.MEMBERS, _comov.LAG],
           lambda: comov_config.COMOVEMENT_JSON,
           funnel="funnel_steps",
           price_basis="daily price bars, split- and dividend-adjusted closes; correct for returns",
           params=_comovement_params, settings=_comovement_settings),
    _board("module_value_chain", "Value Chain",
           ["chain_filings", "chain_mentions", "chain_meta"],
           lambda: _json("value_chain", "value_chain_latest.json")),
    _board("module_relatedness", "Relatedness",
           # The names come from the board's one reader (#217), so a rename is a change to one file. The record
           # left out the seven theme tables the board has always read — the run pointer, the themes at the three
           # levels, their tags, their members and their ETF overlaps — and the attributes and embeddings the
           # profile step reads back; the reader makes that checkable.
           [_rel.PROFILES, _rel.ATTRIBUTES, _rel.EMBEDDINGS, _rel.SCORES, _rel.THEME_RUNS, _rel.THEMES,
            _rel.THEME_TAGS, _rel.THEME_MEMBERS, _rel.THEME_ETFS, "chain_filings", _rel.TICKER_THEMES],
           # The writer pair is no longer a knob of this board: every LLM job's pair is on the
           # LLM writers card (#404, ``llm_writers_card``).
           lambda: _json("relatedness", "relatedness_latest.json")),
    _board("module_sector_rotation", "Sector Rotation",
           # #642 PR 5: the board fetches no holdings itself any more, so the spine's ``etf_holdings`` is a
           # served need and not a table of its own; the universe went with #860.
           ["rotation_snapshots"],
           lambda: _html("sector_rotation"),
           price_basis="ETF levels stored in rotation snapshots"),
    _board("module_asymmetric_growth", "Asymmetric Growth",
           [],
           lambda: _json("asymmetric_growth", "asymmetric_growth_latest.json"),
           funnel="funnel_steps",
           price_basis="daily price bars, nominal closes for momentum"),
    _board("module_swing_potential", "Swing",
           [],
           lambda: swing_config.SWING_JSON,
           funnel="funnel_steps",
           price_basis="daily price bars: levels nominal, returns adjusted",
           params=_swing_params, settings=_swing_settings),
    _board("module_fundamentals", "Fundamentals",
           [],
           lambda: _json("fundamentals", "fundamentals_latest.json"),
           funnel="funnel_steps",
           price_basis="daily price bars: levels nominal, returns adjusted",
           params=_fundamentals_params, settings=_fundamentals_settings),
    # #25: rendered in memory from the forecast store on every load, like LEAPS.
    _board("module_hit_rate", "Hit Rate", ["forecast_ledger", "forecast_outcomes", "forecast_baselines"],
           _hit_rate_latest),
    # #732: the board reads its own file (``boards/sec_13f.duckdb``); the served reads are ``rcdata/needs/boards.py``'s.
    _board("module_sec_13f", "SEC 13F",
           ["sec13f_board_cells", "sec13f_board_breaks"],
           lambda: _html("sec_13f")),
    # #746: the board reads only ``option_far_contract`` through its need (``options.far_contracts``), rendered in
    # memory on every load, so its as-of is the newest stored session, not a file.
    _board("module_leaps", "LEAPS", [], _leaps_latest, ops_tables=["watchlist_stock"]),
    _board("module_uw_interaction", "Unusual Whales Interaction (lab)", [],
           lambda: _json("uw_interaction", "uw_interaction_latest.json")),
]


def _path_of(entry: dict):
    p = entry["payload_path"]
    return p() if callable(p) else p


def _needs_of(key: str) -> dict:
    """The served needs this board reads, from the board's own record (#642 N1).

    ``declared`` is False for a board that has not migrated to the API yet: its needs are then the planned ones
    (``rcdata.needs.boards.PLANNED_READS``), which the card marks as planned exactly as the flow diagram does. A
    record that cannot be read is no needs, never a raise: this is a card on a status screen.
    """
    try:
        from RevenueChaser.rcdata.needs import boards as api_boards
        reads = api_boards.reads_of(key)
        return {"needs": list(reads["needs"]), "declared": bool(reads["declared"])}
    except Exception:  # noqa: BLE001 - an unreadable record is "none recorded", not a broken page
        return {"needs": [], "declared": False}


def _card(entry: dict) -> dict:
    reads = _needs_of(entry["key"])
    card = {
        "key": entry["key"], "label": entry["label"], "tables": list(entry["tables"]),
        "needs": reads["needs"], "needs_declared": reads["declared"],
        "ops_tables": list(entry.get("ops_tables") or []),
        "price_basis": entry["price_basis"], "params": entry["params"](),
        "as_of": None, "window": {}, "funnel_steps": [], "state": "ok", "error": None,
    }
    if entry.get("settings"):
        card["settings"] = entry["settings"]()
    path = _path_of(entry)
    if path is None or (not isinstance(path, dict) and not path.exists()):
        card["state"] = "not_rendered"
        return card
    funnel_key = entry.get("funnel") or "funnel_steps"
    # An HTML board that emits no funnel has no JSON to parse. Existence is the
    # rendered signal; json.loads on the page would be a false error.
    if funnel_key == NO_FUNNEL and not isinstance(path, dict) and path.suffix.lower() != ".json":
        return card
    try:
        # A board whose payload is a store row hands the dict itself (SPX Gamma, spx_meta).
        payload = path if isinstance(path, dict) else json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("payload JSON is not an object")
    except Exception as exc:  # noqa: BLE001 - a bad artifact is shown, never raised
        card["state"] = "error"
        card["error"] = f"{type(exc).__name__}: {exc}"
        return card
    card["as_of"] = payload.get("as_of") or payload.get("generated_at")
    card["window"] = {k: payload.get(k) for k in
                      ("window_start", "oos_start", "window_end", "prices_through")}
    if funnel_key == NO_FUNNEL:
        return card
    steps = funnel_mod.from_dict(payload.get(funnel_key))
    if not steps:
        card["state"] = "no_funnel"
        return card
    card["funnel_steps"] = steps
    problems = funnel_mod.validate(steps)
    if problems:
        card["state"] = "invalid"
        card["error"] = "; ".join(problems)
    return card


def board_cards() -> list[dict]:
    """One card per registered board. Never raises."""
    cards = []
    for entry in BOARD_INPUTS:
        try:
            cards.append(_card(entry))
        except Exception as exc:  # noqa: BLE001
            cards.append({"key": entry.get("key"), "label": entry.get("label"),
                          "tables": [], "needs": [], "needs_declared": False,
                          "price_basis": "", "params": [], "as_of": None,
                          "window": {}, "funnel_steps": [], "state": "error",
                          "error": f"{type(exc).__name__}: {exc}"})
    return cards
