"""#410 part 2: the company profile's customers, suppliers and competitors are Value Chain edges.

Since #894 step 4 the profile is the SEC reading service's ``company.profile`` answer, read by CIK, and not the
Relatedness board's own table.

Each named company becomes a ``source = "profile"`` edge with its quote and stated share, resolved to a ticker
through ``aliases.resolve``; a name it cannot resolve stays as text. For a (counterparty, relation) pair both the
profile and the filing's XBRL state, the XBRL row is kept and no share is copied (plan v31 step 1(b); #725 made the
relation part of that key); a filer without a profile gets no edge from its text (#748).
"""
from __future__ import annotations

from revenuechaser.core import rawstore
from revenuechaser.module_value_chain import aliases, engine
from revenuechaser.rcdata.tests.conftest import market_roots  # noqa: F401  (fixture)

TEXT = "Direct sales to Apple accounted for 29.8% of our net sales. We compete with Intel in some markets."
PROFILE = {"customers": [{"name": "Apple Inc.", "type": "company", "share": None, "quote": "Apple is our largest"},
                         {"name": "Acme Widgets", "type": "company", "share": 0.12, "quote": "Acme 12%"}],
           "suppliers": [{"name": "Taiwan Semiconductor", "type": "company", "quote": "TSMC makes our chips"}],
           "named_competitors": ["Amkor Technology", "Intel"]}


# ── the SEC reading service's answers, at the boundary the board reads them from (#894 step 4) ──────────────────
# Written here and not under ``rcdata/tests/`` on purpose: ``scripts/red_on_base.py`` copies the PR's test files
# onto the merge-base and nothing else, so a helper in a module of its own would make every new test red for a
# missing import instead of for the behaviour it is about.
#: Every ``read_answer`` column but ``cik`` and ``answer``; the live prompt version of ``company.profile``.
ANSWER = {"question": "company.profile", "prompt_version": "v3d", "accession": "a", "document": "d",
          "filing_date": "2026-02-01", "input_hash": "h", "provider": "evren", "model": "m", "status": "ok",
          "attempts": 1, "raw": None, "missing_chunks": None, "rules_version": "ours-2", "fetched_at": 1.0,
          "run_id": "fixture", "form": "10-K", "input_kind": "section:business", "calls": 1, "tokens_in": 10,
          "tokens_out": 10, "error": None, "report_date": "2025-12-31"}


def answer_row(cik, profile: dict | None, **over) -> dict:
    """One ``read_answer`` row; ``cik`` is keyed as the layer keys it, so ``0000789019`` and ``789019`` are one."""
    import json

    from revenuechaser.rcdata import read
    return {**ANSWER, "cik": read._cik(cik), "answer": None if profile is None else json.dumps(profile), **over}


def serve_answers(rows: list[dict], *, replace: bool = False) -> None:
    """Add ``rows`` to the live ``sec_reads`` serving file, building it when there is none.

    A test that seeds several companies one call at a time needs the second call to keep the first one's row, so
    the build starts from the live file unless ``replace``. The columns come from the dataset's own schema, so a
    serving version that adds one does not leave a stale copy here.
    """
    from revenuechaser.rcdata import serving
    from revenuechaser.rcdata.build.sec_reads.reads import SCHEMA, TABLE

    names = [name for name, _ in SCHEMA]
    cols = ", ".join(f"{name} {sql}" for name, sql in SCHEMA)
    with serving.build("sec_reads", base="fresh" if replace else "live") as b:
        b.con.execute(f"CREATE TABLE IF NOT EXISTS {TABLE} ({cols})")
        if rows:
            b.con.executemany(f"INSERT INTO {TABLE} ({', '.join(names)}) VALUES ({', '.join('?' * len(names))})",
                              [[r.get(n) for n in names] for r in rows])
        (count,) = b.con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()
        b.swap({TABLE: int(count)})


def _filing(ticker="AMKR", text=TEXT, cik="1"):
    rawstore.write_rows("chain_filings", [{"ticker": ticker, "cik": cik, "form": "10-K", "filed": "2026-02-01",
                                           "accession": "a", "primary_doc": "u", "item_text": text,
                                           "quality": "ok", "fetched_at": 1.0}])


def _profile(ticker="AMKR", profile=PROFILE, cik=None, **over):
    """The ticker's ``company.profile`` answer in the SEC reading service (#894 step 4).

    The service answers by CIK, so the answer is served under the CIK the ticker's own corpus row states; a
    caller with no ``chain_filings`` row (the layer's corpus) passes ``cik``.
    """
    if cik is None:
        row = next((r for r in rawstore.get_all("chain_filings") if str(r["ticker"]).upper() == ticker.upper()), None)
        cik = (row or {}).get("cik") or "1"
    serve_answers([answer_row(cik, profile, **over)])


def test_profile_edges_resolve_names_and_keep_unresolved_ones_as_text():
    names = aliases.spine_names([{"ticker": "AMKR", "name": "Amkor Technology Inc"}])
    got = {(e["dst_name"], e["dst_ticker"], e["relation"], e["share_pct"])
           for e in engine.profile_edges("AMKR", PROFILE, "2026-02-01", names)}
    assert got == {("Apple Inc.", "AAPL", "customer", None), ("Acme Widgets", "", "customer", 12.0),
                   ("Taiwan Semiconductor", "TSM", "supplier", None), ("Intel", "INTC", "competitor", None)}


def test_the_profile_wins_per_counterparty(rawstore_tmp_db, market_roots):  # noqa: F811
    _filing()
    _profile()
    edges = [e for e in engine.build_edges() if e["src"] == "AMKR"]
    apple = [e for e in edges if e["dst_ticker"] == "AAPL"]
    assert [(e["source"], e["relation"], e["share_pct"], e["snippet"]) for e in apple] == [
        ("profile", "customer", None, "Apple is our largest")]   # no sentence share since #748
    assert {e["source"] for e in edges} == {"profile"}          # Intel too: the profile names it
    assert all(e["source"] == "profile" for e in rawstore.get_all("chain_mentions") if e["src"] == "AMKR")


def test_a_filer_without_a_profile_gets_no_edge_from_its_text(rawstore_tmp_db, market_roots):  # noqa: F811
    _filing("NVTS", cik="2")                                      # its own CIK: the service answers by CIK
    _profile()                                                    # AMKR's profile, not NVTS's
    assert engine.build_edges() == []                             # #748: the text scans are gone


def test_the_board_names_the_source_of_a_link():
    edges = engine.profile_edges("AMKR", PROFILE, "2026-02-01")
    assert {l["source"] for l in engine.focal_graph(edges, "AMKR")["links"]} == {"profile"}
