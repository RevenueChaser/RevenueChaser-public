"""Seed the SEC reading service's ``company.profile`` answers for a Relatedness test (#1520).

The board keeps no profile of its own since #894 step 3b: it reads the service's answers where they are
(``engine.service_rows``) and copied none into ``relatedness_profiles`` / ``relatedness_attributes``, which #1520
retired. A test that needs profiles on the board therefore **answers the service** instead of writing a table, as
``store.save_profile`` used to let it.

Two seams, on purpose:

* The real one is the serving row: build the fundamentals layer, let the service read the filing and read it back.
  It is slow and it is what ``test_profiles_from_service.py`` drives, so the read path is covered once, for real,
  by the fixtures here (:func:`layer`, :func:`world`, :func:`ask_the_service`).
* :func:`seed` answers at ``engine.service_rows`` instead. It is for the many tests whose subject is the
  similarity, the themes, the staleness or the payload and not where a profile came from -- the tests that used to
  write a row with ``store.save_profile`` and read it straight back.

Nothing here calls a model or the network: the writer both sides talk to is a fake, and the service's HTTP
boundary is the usual mock.
"""
from __future__ import annotations

import json

import pytest

from revenuechaser.core import universe
from revenuechaser.core.providers import evren, sec_edgar
from revenuechaser.rcdata.build.fundamentals import companyfacts, filings
from revenuechaser.rcdata.build.sec_forms import forms
from revenuechaser.rcdata.build.sec_reads import company_profile as cp
from revenuechaser.rcdata.build.sec_reads import questions, reads
from revenuechaser.rcdata.tests import fund_fixture as fx

from .. import config, store

#: Microsoft's CIK in the fixtures below: the one company the layer fixture builds.
MSFT = "789019"

#: The business section ``_stored`` plants in the stored 10-K, long enough to profile from.
BUSINESS = "We build cloud software and developer tools for enterprises. " * 40

#: The v3 profile the fake writer answers with.
PROFILE = {"summary": "Builds cloud software.", "stage": "mature", "keywords": ["cloud"],
           "segments": [{"name": "Cloud", "share": None, "source": "text",
                         "products": ["cloud software"], "end_markets": ["enterprises"]}]}


# ── the service's own rows, read for real ───────────────────────────────────────────────────────────────────────
def _stored(http_mock) -> None:
    """One company's stored annual report: ``sec/filings`` built over a 10-K whose Item 1 is :data:`BUSINESS`."""
    fx.spine()
    fx.sec_routes(http_mock, {MSFT: fx.msft_facts()})
    ten_k = fx.ten_k().replace("We develop software and cloud services. Our customers include enterprises. ", "")
    ten_k = ten_k.replace("<p>Item 1. Business</p><p>", "<p>Item 1. Business</p><p>" + BUSINESS, 1)
    fx.filing_routes(http_mock, {MSFT: fx.submissions(789019, fx.MSFT_FILINGS, "MICROSOFT CORP")},
                     {"msft-10k.htm": ten_k, "msft-def14a.htm": fx.proxy()})
    fx.run(companyfacts.NAME, mode="backfill", to="2026-10-26")
    fx.run(filings.NAME, mode="backfill", to="2026-10-28")


@pytest.fixture
def filings_only(monkeypatch, http_mock):
    """``sec/filings`` built, ``sec/forms`` never: the state the service cannot read a business section in."""
    monkeypatch.setattr(sec_edgar, "SEC_WWW_BASE", "https://sec.test")
    monkeypatch.setattr(sec_edgar, "SEC_DATA_BASE", "https://data.sec.test")
    _stored(http_mock)
    return http_mock


@pytest.fixture
def layer(filings_only):
    """The layer the board reads: ``sec/filings`` and ``sec/forms`` both built."""
    fx.run(forms.NAME, "2026-10-28")
    return filings_only


@pytest.fixture
def world(layer, monkeypatch):
    """The layer, a universe of that one company, and the writer the **service** talks to (a fake at its HTTP
    boundary). Returns the mock the service's requests reach."""
    monkeypatch.setenv("LITELLM_RC_KEY", "sentinel-gate")
    monkeypatch.setenv("RC_EVREN_BASE", "https://evren.test/v1")
    monkeypatch.setattr(evren, "_sleep", lambda s: None)
    monkeypatch.setattr(questions, "QUESTIONS", {})
    monkeypatch.setattr(reads, "QUESTIONS", questions.QUESTIONS)
    monkeypatch.setattr(universe, "classification_universe", lambda *a, **k: ["MSFT"])

    def gate(request):
        return 200, json.dumps({"choices": [{"message": {"content": json.dumps(PROFILE)}}],
                                "usage": {"total_tokens": 3}}), {}
    layer.add("/chat/completions", gate)
    return layer


def ask_the_service() -> dict:
    """Run the SEC reading service once, so it answers ``company.profile`` for the stored filing."""
    cp.register_all()
    return fx.run(reads.NAME, reread=True)


# ── the rows, answered at the board's reader ────────────────────────────────────────────────────────────────────
def row(ticker: str, attributes: dict | None = None, *, cik: str = "", status: str = "ok",
        model: str = "a-model", provider: str = "evren", prompt_version: str | None = None,
        fetched_at: float = 1.0, input_hash: str = "h", accession: str | None = None,
        profile_json: dict | None = None, label_source: dict | None = None) -> dict:
    """One profile row in the shape :func:`engine.service_rows` builds from a service answer.

    ``attributes`` are the tag lists the board scores (``config.PROFILE_FIELDS``); the fields left out are empty.
    ``prompt_version`` left out is the current one, so the row is not stale (``store.is_stale``).
    """
    version = config.PROMPT_VERSION if prompt_version is None else prompt_version
    attrs = {f: list((attributes or {}).get(f) or []) for f in config.PROFILE_FIELDS}
    return {"ticker": ticker.upper(), "cik": str(cik or ""), "model": model, "prompt_version": version,
            "fetched_at": fetched_at,
            "cache_key": store.cache_key(model, False, "", version, ticker, input_hash, provider=provider),
            "status": status, "attempts": 0, "provider": provider,
            "profile_json": profile_json, "label_source": label_source, "accession": accession,
            "attributes": attrs}


def rows_of(profiles: dict[str, dict], **over) -> list[dict]:
    """:func:`row` per ticker of ``{ticker: {field: [tag, ...]}}``."""
    return [row(t, attrs, **over) for t, attrs in profiles.items()]


def seed(monkeypatch, rows: list[dict]) -> list[dict]:
    """Answer ``rows`` wherever the board asks the service for its profiles.

    Replaces what ``store.save_profile`` did for a test before #1520. ``engine.service_rows`` is the one reader
    (``store.profile_rows`` imports it per call), so patching it reaches every path: ``load_profiles``,
    ``load_profile_json``, ``profile_meta``, the staleness readers and the payload.
    """
    from .. import engine
    by_ticker = {r["ticker"]: r for r in rows}

    def service_rows(tickers=None):
        if tickers is None:
            return [dict(r) for r in by_ticker.values()]
        return [dict(by_ticker[t]) for t in (x.upper() for x in tickers) if t in by_ticker]

    monkeypatch.setattr(engine, "service_rows", service_rows)
    return rows


def seed_profiles(monkeypatch, profiles: dict[str, dict], **over) -> list[dict]:
    """:func:`seed` of :func:`rows_of`: the one-liner a test that only needs tags on the board uses."""
    return seed(monkeypatch, rows_of(profiles, **over))
