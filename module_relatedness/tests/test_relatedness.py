"""Relatedness core — profiles, similarity, engine (no network)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from revenuechaser.core import rawstore
from revenuechaser.module_comovement.tests import prices_bars
from revenuechaser.module_relatedness import config, engine, profile_v3, similarity
from revenuechaser.module_relatedness.tests import service_fixture
from revenuechaser.rcdata.tests import spine_fixture, universe_store


# ── profiles ────────────────────────────────────────────────────────────────
def test_parse_profile_cleans_and_limits():
    """The v3 reply (#400) as the board's attribute rows: lower-cased, de-duplicated, a wrong type dropped."""
    raw = v3_reply(["AI Accelerators", "gpu ", "GPU", ""], ["Data Center", "gaming"], business_model=7,
                   keywords=["cuda"])
    p = profile_v3.to_attributes(profile_v3.parse(raw))
    assert p["products"] == ["ai accelerators", "gpu"]     # lowercased, de-duped
    assert p["end_markets"] == ["data center", "gaming"]
    assert p["business_model"] == []                       # wrong type -> empty
    assert p["keywords"] == ["cuda"]
    assert set(p) == set(config.PROFILE_FIELDS)


def test_parse_profile_bad_json_is_empty():
    p = profile_v3.to_attributes(profile_v3.parse("not json"))
    assert all(p[f] == [] for f in config.PROFILE_FIELDS)


# ── similarity ──────────────────────────────────────────────────────────────
def _prof(**kw):
    base = {f: [] for f in config.PROFILE_FIELDS}
    base.update(kw)
    return base


def test_identical_profiles_score_one_and_unrelated_zero():
    import pytest
    a = _prof(products=["gpu"], end_markets=["data center"])
    b = _prof(products=["gpu"], end_markets=["data center"])
    c = _prof(products=["bread"], end_markets=["grocery"])
    assert similarity.score_pair(a, b)[0] == pytest.approx(1.0)
    assert similarity.score_pair(a, c)[0] == 0.0


def test_shared_terms_reported():
    a = _prof(products=["gpu", "cpu"], end_markets=["data center"])
    b = _prof(products=["gpu"], end_markets=["data center"])
    score, shared = similarity.score_pair(a, b)
    assert "gpu" in shared and "data center" in shared and score > 0


def test_percentile_bounds():
    assert similarity.percentile(0.5, [0.1, 0.2, 0.9]) == 66.7
    assert similarity.percentile(0.5, []) == 0.0


# ── engine ──────────────────────────────────────────────────────────────────
def _seed_universe(tickers):
    """The old universe (cap, price: the board's filters until #642 PR 6) and the spine's ``security`` rows (name,
    sector, industry: the profile run's only source since #642 PR 3)."""
    spine_fixture.write_security([{"ticker": t, "name": t + " Inc", "sector": "Technology",
                                   "industry": "Semiconductors"} for t in tickers], replace=True)


# Item 1 texts a test seeds have to clear the profile floor (#313,
# ``rcdata.sec_profile_input.MIN_INPUT_CHARS``): the service never sends a shorter one to its writer. ``long_body`` pads a distinctive sentence past it; an empty text stays empty,
# because that is the ``no_text`` case.
_PAD = "This annual report describes the company's business in detail. " * 40


def v3_reply(products=(), end_markets=(), **fields) -> str:
    """A writer's v3 reply (#400) whose attribute rows carry ``products`` / ``end_markets`` (one segment)."""
    import json as _json
    body = {"summary": "", "segments": [{"name": "main", "share": None, "source": "text",
                                         "products": list(products), "end_markets": list(end_markets)}],
            **fields}
    return _json.dumps(body)


def long_body(text: str) -> str:
    return f"{text} {_PAD}" if text else text


def _seed_filings(tickers):
    rawstore.write_rows("chain_filings", [{
        "ticker": t, "cik": "1", "form": "10-K", "filed": "2026-02-01",
        "accession": "acc-" + t, "primary_doc": "http://x",
        "item_text": long_body("We design gpu accelerators for data center customers."),
        "quality": "ok", "fetched_at": 1.0,
    } for t in tickers])


def _seed_ohlc(prices: pd.DataFrame):
    rows = []
    for t in prices.columns:
        for ts, p in prices[t].items():
            rows.append({"ticker": t, "ts": ts.isoformat(), "open": float(p),
                         "high": float(p), "low": float(p), "close": float(p),
                         "volume": 1.0, "cached_at": 1.0})
    prices_bars.write_bars(rows)


def _correlated_prices(n: int = 260, seed: int = 7) -> pd.DataFrame:
    """Two names sharing both a market and an idiosyncratic common factor."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2025-01-02", periods=n, freq="B")
    market = rng.normal(0.0003, 0.010, n)
    common = rng.normal(0.0002, 0.008, n)
    nvda = market + common + rng.normal(0.0, 0.002, n)
    amd = market + common + rng.normal(0.0, 0.002, n)
    spy = market + rng.normal(0.0, 0.001, n)

    def px(r):
        return 100.0 * np.exp(np.cumsum(r))

    return pd.DataFrame({"NVDA": px(nvda), "AMD": px(amd), "SPY": px(spy)}, index=idx)


def test_select_pilot_is_the_shared_universe():
    from revenuechaser.core.universe import classification_universe
    tickers = ["NVDA", "AMD", "TSM", "AAPL"]
    _seed_universe(tickers)
    pilot = engine.select_pilot()
    assert pilot == classification_universe()
    assert engine.select_pilot(limit=2) == pilot[:2]


def test_run_no_fetch_reads_cached_profiles(rawstore_tmp_db, monkeypatch, tmp_path):
    tickers = ["NVDA", "AMD", "TSM"]
    _seed_universe(tickers)
    _seed_filings(tickers)
    monkeypatch.setattr(engine.config, "RELATEDNESS_JSON", tmp_path / "r.json")
    # the service's answers, which is where the board's profiles are (#1520)
    service_fixture.seed(monkeypatch, [
        service_fixture.row("NVDA", _prof(products=["gpu"], end_markets=["data center"]), cik="cik-NVDA"),
        service_fixture.row("AMD", _prof(products=["gpu"], end_markets=["data center"]), cik="cik-AMD"),
        service_fixture.row("TSM", _prof(products=["foundry"], end_markets=["semiconductors"]), cik="cik-TSM")])
    monkeypatch.setattr(engine.vc_engine, "fetch_corpus",
                        lambda *a, **k: {"no_fetch": True})

    payload = engine.run(no_fetch=True, tickers=tickers)
    assert payload["n"] == 3
    assert "universe_total" in payload
    assert payload["companies"][0].get("index") is not None
    peers = {p["peer"] for p in payload["peers"]["NVDA"]}
    assert "AMD" in peers
    nvda_amd = next(p["score"] for p in payload["peers"]["NVDA"] if p["peer"] == "AMD")
    assert nvda_amd > 0
    # zero-cosine peers are omitted (the peer matrix is sparse)
    assert "TSM" not in peers


def test_peer_move_hides_when_prices_missing(rawstore_tmp_db):
    _seed_universe(["NVDA", "AMD"])
    peers = {
        "NVDA": [{"peer": "AMD", "score": 1.0, "percentile": 100, "shared": []}],
        "AMD": [{"peer": "NVDA", "score": 1.0, "percentile": 100, "shared": []}],
    }
    engine._attach_peer_market(peers)
    for entries in peers.values():
        for p in entries:
            assert p.get("move") is None
            assert p.get("beyond_spy") is None
            assert p.get("cluster") is None


def test_peer_move_from_ohlc(rawstore_tmp_db):
    _seed_universe(["NVDA", "AMD", "SPY"])
    _seed_ohlc(_correlated_prices())
    peers = {
        "NVDA": [{"peer": "AMD", "score": 1.0, "percentile": 100, "shared": []}],
        "AMD": [{"peer": "NVDA", "score": 1.0, "percentile": 100, "shared": []}],
    }
    engine._attach_peer_market(peers)
    p = peers["NVDA"][0]
    assert p.get("move") is not None
    assert set(p["move"].keys()) == {1, 3, 5, 10}
    assert all(-1.0 <= float(v) <= 1.0 for v in p["move"].values())
    assert float(p["move"][5]) > 0.3
    assert p.get("beyond_spy") is not None
    assert -1.0 <= float(p["beyond_spy"]) <= 1.0
    assert float(p["beyond_spy"]) > 0.3


def test_companies_carry_theme_levels(rawstore_tmp_db, monkeypatch):
    from revenuechaser.module_relatedness import store
    _seed_universe(["NVDA"])
    service_fixture.seed_profiles(monkeypatch, {"NVDA": _prof(products=["gpu"])}, cik="cik-NVDA")
    rawstore.write_rows("theme_runs", [{
        "id": "nmf-test", "created_at": "2026-01-01T00:00:00Z", "k_fine": 1,
        "k_medium": 1, "k_coarse": 1, "jaccard": 1.0, "is_current": 1}])
    rawstore.write_rows("ticker_themes", [
        {"ticker": "NVDA", "theme_id": "nmf-test:c0", "theme": "Semiconductors",
         "level": "coarse", "theme_run_id": "nmf-test"},
        {"ticker": "NVDA", "theme_id": "nmf-test:m0", "theme": "Chips",
         "level": "medium", "theme_run_id": "nmf-test"},
        {"ticker": "NVDA", "theme_id": "nmf-test:f0", "theme": "AI Accelerators",
         "level": "fine", "theme_run_id": "nmf-test"},
    ])
    payload = engine._payload(store.load_profiles(["NVDA"]), {})
    row = payload["companies"][0]
    assert row["theme_coarse"] == "Semiconductors"
    assert row["theme_medium"] == "Chips"
    assert row["theme_fine"] == "AI Accelerators"


def test_report_renders(rawstore_tmp_db, tmp_path, monkeypatch):
    from revenuechaser.module_relatedness import report
    payload = {
        "as_of": "2026-09-19T00:00:00+00:00", "model": "deepseek-v4-flash", "n": 2,
        "companies": [
            {"ticker": "NVDA", "name": "NVIDIA", "sector": "Technology",
             "industry": "Semiconductors", "market_cap": 1e12, "weights": {"gpu": 1.0}, "profile": {},
             "theme_coarse": "Semiconductors", "theme_medium": "Chips",
             "theme_fine": "AI Accelerators"},
            {"ticker": "AMD", "name": "Advanced Micro Devices", "sector": "Technology",
             "industry": "Semiconductors", "market_cap": 1e11, "weights": {"gpu": 1.0},
             "profile": {}, "theme_coarse": "Semiconductors",
             "theme_medium": "Chips", "theme_fine": "CPUs"},
        ],
        "peers": {
            "NVDA": [{"peer": "AMD", "name": "Advanced Micro Devices", "score": 1.0,
                      "shared": ["gpu"], "percentile": 100,
                      "move": {1: 0.67, 3: 0.74, 5: 0.76, 10: 0.75},
                      "beyond_spy": 0.72,
                      "cluster": {"coarse": True, "medium": True, "fine": False}}],
            "AMD": [{"peer": "NVDA", "name": "NVIDIA", "score": 1.0,
                     "shared": ["gpu"], "percentile": 100}],
        },
        "scores": [1.0], "thinking_compare": {}, "fields": list(config.PROFILE_FIELDS),
    }
    html = report.render_relatedness_dashboard(payload)
    assert "Relatedness" in html
    assert "What am I looking at?" in html
    assert "NVDA" in html and "AMD" in html
    assert 'id="q"' in html
    # Native A/B focal selects and a closed <details class="filters"> are gone.
    assert '<select id="a"' not in html
    assert '<select id="b"' not in html
    assert '<details class="filters">' not in html
    # The shared searchable combobox is the focal picker.
    assert 'id="ticker-combo"' in html
    assert 'role="combobox"' in html
    assert "RCCombobox.mount(" in html
    assert "clear: true" in html.split("RCCombobox.mount(", 1)[1].split("});", 1)[0]   # the × works
    # The shared filter bar (#383 C1b) comes before the combobox (chrome order); the constants kit is gone.
    assert '<section class="rcf-bar" id="rc-filters"></section>' in html
    assert html.index('id="rc-filters"') < html.index('id="ticker-combo"')
    for gone in ('id="mc-tabs"', 'id="index-tabs"', 'id="eweek-tabs"', '<select id="theme"', "initTickerCombo",
                 'MC = "all"'):
        assert gone not in html, f"constants kit left: {gone}"
    # Peer row copy for move / beyond SPY; the cluster chips stay hidden until #894 (decision E).
    assert "move" in html and "beyond SPY" in html
    assert "prow-cluster" not in html
    assert '"name": "NVIDIA"' in html


def test_report_empty_state():
    from revenuechaser.module_relatedness import report
    html = report.render_relatedness_dashboard({"as_of": "", "companies": []})
    assert "No profiles yet" in html


def _two_sector_board():
    from revenuechaser.module_relatedness import report
    co = lambda t, sec, ind, theme: {
        "ticker": t, "name": t, "sector": sec, "industry": ind, "market_cap": 1e12,
        "weights": {"gpu": 1.0}, "profile": {}, "theme_coarse": theme}
    return report.render_relatedness_dashboard({
        "as_of": "2026-09-19T00:00:00+00:00", "model": "m", "n": 2,
        "companies": [co("MSFT", "Technology", "Software - Application", "Cloud"),
                      co("JPM", "Financial Services", "Banks - Diversified", "Banking")],
        "peers": {"MSFT": [], "JPM": []}, "scores": []})


def test_the_focal_line_shows_the_sector_then_the_industry(tmp_path):
    """#266: ``sector · industry``; no theme until #894 (decision E), no sub-industry."""
    from revenuechaser.core.tests.board_js import run_board_js
    tail = 'FOCAL = "MSFT"; render(); console.log(JSON.stringify(_els["meta"].textContent));'
    assert run_board_js(_two_sector_board(), tail, tmp_path) == "Technology · Software - Application"


def test_the_sector_filter_narrows_the_picker_at_either_level(tmp_path):
    """The shared kit reads each card's ``sector`` and ``industry`` (its ``gics`` path when the payload has one)."""
    from revenuechaser.core.tests.board_js import run_board_js
    tail = """
function pool(){ return DATA.filter(pass).map(function(c){ return c.ticker; }); }
var log = {all: pool()};
RCF.set({gics: {key: "Financial Services", label: "Financial Services", level: 1}}); log.sector = pool();
RCF.set({gics: {key: "Technology›Software - Application", label: "Software - Application", level: 2}});
log.industry = pool();
console.log(JSON.stringify(log));"""
    got = run_board_js(_two_sector_board(), tail, tmp_path)
    assert got == {"all": ["MSFT", "JPM"], "sector": ["JPM"], "industry": ["MSFT"]}


def test_the_board_hides_themes_until_the_sec_service_owns_profiles(tmp_path):
    """Decision E option 2 (avo, 16 Nov 2026): no Theme facet, no cluster chips, no theme in the meta line (#894)."""
    from revenuechaser.core.tests.board_js import run_board_js
    from revenuechaser.module_relatedness import report
    co = lambda t, ids: {"ticker": t, "name": t, "sector": "Technology", "industry": "Semiconductors",
                         "market_cap": 1e12, "theme_coarse": "Chips", "theme_ids": ids}
    html = report.render_relatedness_dashboard({
        "as_of": "2026-09-19T00:00:00+00:00", "model": "m", "n": 2,
        "companies": [co("NVDA", ["r:c0"]), co("AMD", ["r:c0"])],
        "peers": {"NVDA": [{"peer": "AMD", "score": 0.9, "percentile": 99, "shared": [],
                            "cluster": {"coarse": True, "medium": False, "fine": False}}]},
        "scores": [],
        "theme_catalog": {"r:c0": {"label": "Chips", "level": "coarse", "parent": ""}}})
    assert "fmtCluster" not in html and "prow-cluster" not in html
    tail = """console.log(JSON.stringify({facets: META.facets, themes: META.themes || null,
  meta: _els['meta'].textContent, focal: FOCAL, peers: _els['peers'].innerHTML.indexOf('cluster')}));"""
    got = run_board_js(html, tail, tmp_path)
    assert got == {"facets": ["index", "mc", "gics", "earnings"], "themes": None,
                   "meta": "Technology · Semiconductors", "focal": "NVDA", "peers": -1}


def test_no_filter_set_keeps_every_name_and_the_first_one_focal(tmp_path):
    """#383 C1b parity: no filter set = the same names as before the move (all of them), same default focal."""
    from revenuechaser.core.tests.board_js import run_board_js
    got = run_board_js(_two_sector_board(), "console.log(JSON.stringify({pool: DATA.filter(pass).length, "
                       "n: DATA.length, focal: FOCAL, count: _els['count'].textContent, active: RCF.active()}));",
                       tmp_path)
    assert got == {"pool": 2, "n": 2, "focal": "MSFT", "count": "2 names", "active": False}


def test_companies_carry_the_filter_path_and_theme_ids(rawstore_tmp_db, monkeypatch):
    """#383 C1b: each company is a kit row (``gics`` + ``theme_ids``) and the payload carries the theme catalog."""
    from revenuechaser.module_relatedness import store
    _seed_universe(["NVDA"])
    service_fixture.seed_profiles(monkeypatch, {"NVDA": _prof(products=["gpu"])}, cik="cik-NVDA")
    payload = engine._payload(store.load_profiles(["NVDA"]), {})
    row = payload["companies"][0]
    assert row["gics"] == [row["sector"], row["industry"]] and row["theme_ids"] == []
    assert payload["theme_catalog"] == {}             # no pinned run in a fresh store


def test_two_share_classes_are_one_row_and_never_each_others_peer(rawstore_tmp_db, monkeypatch):
    """Decision C (avo, 16 Nov 2026; #408): one row per CIK; the kept class lists the other on its row."""
    from revenuechaser.module_relatedness import store
    _seed_universe(["GOOG", "GOOGL", "MSFT"])
    service_fixture.seed(monkeypatch, [
        service_fixture.row(t, _prof(products=["search", "cloud"]), cik=cik)
        for t, cik in (("GOOG", "0001652044"), ("GOOGL", "1652044"), ("MSFT", "789019"))])
    payload = engine._payload(store.load_profiles(["GOOG", "GOOGL", "MSFT"]), {})
    rows = {c["ticker"]: c["also"] for c in payload["companies"]}
    kept = "GOOGL" if "GOOGL" in rows else "GOOG"
    assert set(rows) == {kept, "MSFT"} and rows[kept] == [({"GOOG", "GOOGL"} - {kept}).pop()]
    assert all(p["peer"] in rows for ps in payload["peers"].values() for p in ps)


def test_companies_with_an_unknown_sector_read_unclassified(rawstore_tmp_db, monkeypatch):
    """R3 (#86): the legacy vendor ``Other`` and a missing sector both read as the unknown bucket."""
    from revenuechaser.module_relatedness import store
    universe_store.replace([
        {"ticker": t, "name": t, "market_cap": 1e9, "sector": sec, "price": 1.0, "industry": "x",
         "quote": {}}
        for t, sec in (("LEG", "Other"), ("NUL", None), ("OKK", "Energy"))])
    service_fixture.seed(monkeypatch, [service_fixture.row(t, _prof(products=["x"]), cik=f"cik-{t}")
                                       for t in ("LEG", "NUL", "OKK")])
    payload = engine._payload(store.load_profiles(["LEG", "NUL", "OKK"]), {})
    assert {c["ticker"]: c["sector"] for c in payload["companies"]} == {
        "LEG": "Unclassified", "NUL": "Unclassified", "OKK": "Energy"}


def test_companies_carry_the_sector_and_the_industry_not_the_gics_levels(rawstore_tmp_db, monkeypatch):
    """#266: a card is ``sector`` (Morningstar name) + ``industry`` (the provider text), nothing deeper.

    ``OLD`` is a row the identity master has not re-applied yet: it still holds the GICS spelling.
    """
    from revenuechaser.module_relatedness import store
    rows = (("NVDA", "Technology", "Semiconductors"), ("JPM", "Financial Services", "Banks - Diversified"),
            ("OLD", "Information Technology", "Software - Application"), ("NOI", "Energy", ""))
    universe_store.replace([
        {"ticker": t, "name": t, "market_cap": 1e9, "sector": sec, "industry": ind, "price": 1.0,
         "quote": {}} for t, sec, ind in rows])
    service_fixture.seed(monkeypatch, [service_fixture.row(t, _prof(products=["x"]), cik=f"cik-{t}")
                                       for t, _sec, _ind in rows])
    payload = engine._payload(store.load_profiles([r[0] for r in rows]), {})
    cards = {c["ticker"]: c for c in payload["companies"]}
    assert {t: (c["sector"], c["industry"]) for t, c in cards.items()} == {
        "NVDA": ("Technology", "Semiconductors"), "JPM": ("Financial Services", "Banks - Diversified"),
        "OLD": ("Technology", "Software - Application"), "NOI": ("Energy", "")}
    assert all("sub_industry" not in c and "industry_group" not in c for c in cards.values())


def test_the_payload_reads_the_universe_once_for_the_company_fields(rawstore_tmp_db, monkeypatch):
    """#49: ``_payload`` used to read the universe twice — its own name/sector/cap query beside
    ``core.universe.filter_fields`` — and the two reads could only ever disagree. One read must give the same
    card: the name, the Morningstar sector and the cap the seeded row holds.

    Since #642 PR 6 the fields come from the spine, so the count is on ``filter_fields`` itself (the engine's
    "one read of the company fields") rather than on the SQL text of the old table's query."""
    from revenuechaser.core import universe as core_universe
    from revenuechaser.module_relatedness import store
    rows = (("AAA", "Aaa Corp", "Information Technology", "Software - Application", 2.0e9),
            ("BBB", "Bee Corp", "Energy", "", 1.0e9),
            ("CCC", "", "Utilities", "Regulated Electric", None))
    universe_store.replace([
        {"ticker": t, "name": name, "market_cap": cap, "sector": sec, "industry": ind, "price": 1.0,
         "quote": {}} for t, name, sec, ind, cap in rows])
    service_fixture.seed(monkeypatch, [service_fixture.row(t, _prof(products=["x"]), cik=f"cik-{t}")
                                       for t, _name, _sec, _ind, _cap in rows])

    reads = []
    real = core_universe.filter_fields

    def counting(*a, **k):
        reads.append(a)
        return real(*a, **k)

    monkeypatch.setattr(core_universe, "filter_fields", counting)
    payload = engine._payload(store.load_profiles([r[0] for r in rows]), {})

    assert len(reads) == 1, reads
    cards = {c["ticker"]: c for c in payload["companies"]}
    assert {t: (c["name"], c["sector"], c["market_cap"]) for t, c in cards.items()} == {
        "AAA": ("Aaa Corp", "Technology", 2.0e9),
        "BBB": ("Bee Corp", "Energy", 1.0e9),
        # an empty stored name falls back to the ticker; a NULL cap stays NULL (no cap, not zero)
        "CCC": ("CCC", "Utilities", None)}




def test_the_universe_tile_says_operating_companies():
    from revenuechaser.module_relatedness import report
    html = report.render_relatedness_dashboard({
        "as_of": "2026-09-19T00:00:00+00:00", "n": 1, "universe_total": 5, "pending": 0,
        "companies": [{"ticker": "NVDA", "name": "NVIDIA", "sector": "Technology",
                       "industry": "Semiconductors", "market_cap": 1e12, "weights": {"gpu": 1.0},
                       "profile": {}}],
        "peers": {}, "scores": []})
    assert ('<div class="l">Universe</div>'
            '<div class="d">operating companies, no market-cap floor</div>') in html
    assert "Universe (≥" not in html               # the floor is gone; the tile must not claim one
    # ("< $300M" still appears: that is the Micro bucket of the cap filter, not a floor.)
    assert "classification spine" not in html


def test_beyond_spy_label_uses_default_horizon(monkeypatch):
    """DF63: the 'beyond SPY' residual is computed at DEFAULT_HORIZON; the label says so."""
    from revenuechaser.module_comovement import config as comov_config
    from revenuechaser.module_relatedness import report
    payload = {"as_of": "", "companies": []}
    html = report.render_relatedness_dashboard(payload)
    assert "(5d)'" not in html
    monkeypatch.setattr(comov_config, "DEFAULT_HORIZON", 3)
    assert "' (3d)'" in report.render_relatedness_dashboard(payload)


def test_the_kit_meta_filters_by_earnings_and_takes_the_registry_indexes(tmp_path):
    """#383 C1b review (N2): Relatedness mounts the kit as its own board, with the earnings facet as a filter (not a
    mark) and the index list from the registry."""
    from revenuechaser.core.index_registry import filter_labels
    from revenuechaser.core.tests.board_js import run_board_js
    got = run_board_js(_two_sector_board(), "console.log(JSON.stringify({mode: META.earnings_mode, board: META.board, "
                       "indexes: META.indexes}));", tmp_path)
    assert got == {"mode": "filter", "board": "relatedness", "indexes": filter_labels()}
