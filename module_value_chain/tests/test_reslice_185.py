"""#185: the stored-corpus re-slice dry run (read only, no network).

Since #116/#200 the slicer has new Item 1 patterns; the stored ``chain_filings``
rows were cut with the old ones. ``reslice.dry_run`` re-slices the stored
documents offline and reports how the corpus would change, without writing either
DuckDB file or the document tree.
"""
from __future__ import annotations

import hashlib
import json
import os
import zlib
from pathlib import Path

import duckdb

from RevenueChaser.core import edgar_docs
from RevenueChaser.module_value_chain import __main__ as cli
from RevenueChaser.module_value_chain import edgar_text, reslice, splitter

_BODY = "We make widgets for many industries and sell them worldwide. " * 60
_BODY_B = "We design chips for data centers across the world. " * 60


def _blob(text: str) -> bytes:
    return zlib.compress((text or "").encode("utf-8"), 6)


def _doc(body: str, stop: bool = True) -> str:
    inner = f"<p>{body}</p>"
    if stop:
        inner += "<p><b>Item 1A. Risk Factors</b></p><p>Risks.</p>"
    return f"<html><body><p><b>Item 1. Business</b></p>{inner}</body></html>"


_NO_DOC_HTML = "<html><body><p>Exhibit index only.</p></body></html>"


def _slice_text(doc: str) -> str:
    item, _q = splitter.slice_item(splitter.strip_html(doc), "10-K")
    return item or ""


def _row(ticker, cik, acc, quality, text, form="10-K", filed="2025-01-01"):
    return {"ticker": ticker, "cik": cik, "form": form, "filed": filed, "accession": acc,
            "primary_doc": f"https://www.sec.gov/Archives/{acc}/doc.htm",
            "item_text": text, "quality": quality}


def _edgar_db(path, rows, mentions=()):
    conn = duckdb.connect(str(path))
    conn.execute(
        "CREATE TABLE chain_filings (ticker TEXT PRIMARY KEY, cik TEXT, form TEXT, filed TEXT, "
        "accession TEXT, primary_doc TEXT, item_text BLOB, quality TEXT, fetched_at DOUBLE)")
    conn.execute(
        "CREATE TABLE chain_mentions (src TEXT, dst_name TEXT, dst_ticker TEXT, relation TEXT, "
        "snippet TEXT, filed TEXT)")
    for r in rows:
        conn.execute("INSERT INTO chain_filings VALUES (?,?,?,?,?,?,?,?,?)",
                     [r["ticker"], r["cik"], r["form"], r["filed"], r["accession"],
                      r["primary_doc"], _blob(r["item_text"]), r["quality"], None])
    for m in mentions:
        conn.execute("INSERT INTO chain_mentions VALUES (?,?,?,?,?,?)",
                     [m["src"], m["dst_name"], m.get("dst_ticker", ""), m["relation"],
                      m.get("snippet", ""), m.get("filed", "")])
    conn.close()


def _raw_db(path):
    conn = duckdb.connect(str(path))
    conn.close()


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── the five groups + no_doc ────────────────────────────────────────────────


# ── read only ───────────────────────────────────────────────────────────────




# ── edge diff ───────────────────────────────────────────────────────────────


# ── CLI ─────────────────────────────────────────────────────────────────────
def test_cli_reslice_dry_run_parses_and_calls(monkeypatch, capsys):
    seen = {}

    def fake(edgar, docs, out, sample=20):
        seen.update(edgar=edgar, docs=docs, out=out)
        return {"counts": {"improve": 1}, "total": 1, "edges": {}}

    monkeypatch.setattr(cli.reslice, "dry_run", fake)
    code = cli.main(["--reslice-dry-run", "--edgar", "e.duckdb", "--docs", "docs", "--out", "out"])
    assert code == 0
    assert seen["edgar"] == Path("e.duckdb")
    assert seen["docs"] == Path("docs") and seen["out"] == Path("out")
    assert "improve" in capsys.readouterr().out


# ── a row whose slice raised keeps its edges (review follow-up) ─────────────


# ── the dry run runs before the --floor / --tickers selection (stack R1, SHOULD 5) ──
def test_the_dry_run_never_reads_the_selection(monkeypatch, capsys, tmp_path):
    from RevenueChaser.module_value_chain import __main__ as cli

    def selection(_args):
        raise AssertionError("--reslice-dry-run must not resolve --floor through the live store")

    monkeypatch.setattr(cli, "_selection", selection)
    monkeypatch.setattr(cli.reslice, "dry_run",
                        lambda edgar, docs, out: {"counts": {"unchanged": 1}, "total": 1, "edges": {"added": 0}})
    assert cli.main(["--reslice-dry-run", "--edgar", str(tmp_path / "e.duckdb"), "--docs", str(tmp_path),
                     "--floor", "50"]) == 0
    assert '"unchanged": 1' in capsys.readouterr().out
