"""#118 PR B: C25 (no prefix name resolution), C27 (minimum labelled sample),
C19 (graph build indexes the edges once, same output). No network."""
from __future__ import annotations

import random

from RevenueChaser.module_value_chain import aliases, config, engine, precision, report


# ── C25 ────────────────────────────────────────────────────────────────────
def test_unsafe_prefix_resolver_is_gone():
    """``resolve_name`` mapped "Apple Hospitality REIT" to AAPL by prefix; it had
    no production caller, so it is deleted rather than kept as a trap."""
    assert not hasattr(aliases, "resolve_name")


# ── C27, replaced by plan v31 section 6 ─────────────────────────────────────
def _labels(n_true, n_false):
    return ([{"src": "A", "dst_ticker": "B", "relation": "supplier", "label": True}] * n_true
            + [{"src": "A", "dst_ticker": "C", "relation": "customer", "label": False}] * n_false)


def test_a_small_sample_fails_by_its_own_lower_bound():
    """C27's fixed minimum of 30 is gone: the Wilson lower bound of a small sample is low by itself."""
    assert not hasattr(precision, "MIN_LABELED_N")
    rep = precision.precision(_labels(1, 0))
    assert rep["precision"] == 1.0 and rep["passes"] is False and rep["status"] == "fail"


def test_tile_shows_the_lower_bound_and_the_gate():
    html = report._precision_tile({"n": 2, "tp": 2, "precision": 1.0, "lower_bound": 0.3424, "passes": False,
                                   "status": "fail", "links": 147, "covered": 2})
    assert 'class="stat warn"' in html
    assert "lower bound 34% · gate 70%" in html
    assert "hand-checked n=2" in html and "labels cover 2 of 147 distinct pairs" in html


# ── C19 ────────────────────────────────────────────────────────────────────
def _reference_focal_graph(edges, ticker, depth=2, max_hop2=config.MAX_HOP2):
    """The pre-#118 ``focal_graph``, verbatim in behaviour: the oracle. A link also carries the edge's
    ``share_pct`` (#387 D7), a copied field that the index does not change, and ``focal_relation``, the
    relation seen from the focal company (#405): inverted on an incoming edge, the filing's own otherwise."""
    ticker = (ticker or "").upper()
    by_src: dict = {}
    for e in edges:
        by_src.setdefault(e["src"], []).append(e)
    seen = {ticker}
    links = []

    def _add(e, hop, incoming=False):
        links.append({"src": e["src"], "dst": e.get("dst_ticker") or e["dst_name"],
                      "dst_ticker": e.get("dst_ticker") or "",
                      "relation": e["relation"],
                      "focal_relation": (engine._INVERSE.get(e["relation"], e["relation"])
                                         if incoming else e["relation"]),
                      "snippet": e.get("snippet") or "",
                      "share_pct": e.get("share_pct"),
                      "hop": hop, "incoming": incoming})

    first = [e for e in by_src.get(ticker, []) if e["relation"] in ("supplier", "customer")]
    for e in first:
        _add(e, 1)
        if depth >= 2 and e.get("dst_ticker"):
            seen.add(e["dst_ticker"])
    for e in edges:
        if (e.get("dst_ticker") == ticker and e["src"] != ticker
                and e["relation"] in ("supplier", "customer")):
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


def _fixture_edges(n_tickers=120, n_edges=3000, seed=118):
    rng = random.Random(seed)
    names = [f"T{i:03d}" for i in range(n_tickers)]
    rels = ["supplier", "customer", "competitor", "other"]
    out = []
    for i in range(n_edges):
        dst = rng.choice(names + ["", ""])  # some private (unresolved) names
        out.append({"src": rng.choice(names), "dst_name": dst or f"Private {i}",
                    "dst_ticker": dst, "relation": rng.choice(rels),
                    "snippet": f"s{i}", "filed": "2026-02-01"})
    return names, out


def test_indexed_graphs_equal_the_old_per_ticker_graphs():
    names, edges = _fixture_edges()
    tickers = names + ["NONE", "t001"]
    want = {t: _reference_focal_graph(edges, t, depth=2) for t in tickers}
    index = engine.edge_index(edges)
    for t in tickers:
        assert engine.focal_graph(edges, t, depth=2, index=index) == want[t]
        assert engine.focal_graph(edges, t) == want[t]   # old call shape still works
    assert engine.focal_graph(edges, "T001", depth=1) == _reference_focal_graph(edges, "T001", 1)


def test_graphs_index_the_edges_once(monkeypatch, tmp_path):
    """The per-ticker endpoint reads the payload file and indexes its edges once, not once per request."""
    import json
    names, edges = _fixture_edges(n_tickers=50, n_edges=500)
    path = tmp_path / "value_chain_latest.json"
    path.write_text(json.dumps({"edges": edges}), encoding="utf-8")
    calls = {"n": 0}
    real = engine._norm

    def _counting(e):
        calls["n"] += 1
        return real(e)

    monkeypatch.setattr(engine, "_norm", _counting)
    monkeypatch.setattr(engine, "_GRAPH_CACHE", {})
    for t in names:
        engine.focal_from_payload_file(path, t)
    assert calls["n"] == 1
