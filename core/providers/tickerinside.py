"""TickerInside (``https://tickerinside.com/api/v1``): US ETF holdings, keyless, one JSON file per fund.

**Why it is here.** 93 of the 133 ring-1 ETFs (#354 C6) have no issuer file wired in this tree, and the quarterly
SEC N-PORT set we hold is older than the same filings on EDGAR: ``2026q3_nport.zip`` carries report periods
29 May to 31 Jul 2026, while SMH's report for the period ended 2026-09-30 was filed 2026-11-17. Measured
22 Nov 2026 over the ring-1 set: TickerInside covers **133 of 133** -- 76 from the issuers' own daily files
(iShares, State Street SPDR and Global X, 472 funds in all) and 57 from each fund's **newest** N-PORT filing, whose
report dates reach 2026-09-30. Rejected in the same pass: Alpaca serves no holdings at all, FMP only on its
139 USD/month tier, EODHD's commercial licence from 399 USD/month (#1365 has the table).

**No key, no account, no quota** (`https://tickerinside.com/api/sections/terms.md`). The files are built on weekday
nights from 22:00 UTC and due by 02:00 UTC, so one read a day is what they are for; the asked User-Agent names the
program with a contact, which ``base.user_agent()`` already does through ``RC_HTTP_CONTACT``.

**Licence, and the one line we must not cross.** The snapshots and the figures computed from them are CC BY 4.0,
and keeping each night's copy -- *including to build your own series* -- is explicitly allowed, against an
attribution link where a figure is shown. The **holdings history and the ETF flows are not CC BY 4.0**
(`https://tickerinside.com/legal/#history`): free per request, but republishing the archive or *fetching many
funds' history on a schedule to store it* is not allowed. So nothing in this tree may walk ``/history/``,
``/quarterly/`` or ``/flows`` on a schedule: ``check_path`` refuses those paths in code, not in a comment, and our
own history keeps coming from the SEC bulk sets (#354 C7).

**What it does not serve:** no CUSIP and no ISIN (licensed codes), no price series, nothing intraday. A holding is a
ticker and a weight in percent, so a row from here carries ``cusip`` None and ``name`` None.
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import re

#: The API root. ``RC_TICKERINSIDE_BASE`` is the mock's, as every other provider's base is.
BASE = (os.getenv("RC_TICKERINSIDE_BASE") or "https://tickerinside.com/api/v1").rstrip("/")
#: The provider slug used by the call counter, the pacer and the ``provider`` column of a stored row.
PROVIDER = "tickerinside"
LICENCE = "CC BY 4.0"
#: Where a figure from here must link back to, the licence's condition. A fund file's own ``cite_as`` says it too.
SITE = "https://tickerinside.com"
#: The path segments the history terms keep out of a scheduled job. Not a comment: ``check_path`` raises on them.
HISTORY_PATHS = ("/history/", "/history.json", "/quarterly/", "/flows/", "/flows.json")
#: A fund file's ``source_layer``: the issuer's own daily file, or the fund's newest SEC filing.
DAILY_LAYER = "issuer"
_TICKER = re.compile(r"[A-Z0-9][A-Z0-9.\-]{0,11}\Z")


class LicenceError(RuntimeError):
    """A path the history terms do not allow a scheduled job to fetch."""


def check_path(path: str) -> str:
    """``path`` unchanged, or ``LicenceError``: the history and flows files are not CC BY 4.0 and may not be
    collected on a schedule, so no builder may ask for them (`https://tickerinside.com/legal/#history`)."""
    low = path.lower()
    if any(seg in low for seg in HISTORY_PATHS):
        raise LicenceError(f"tickerinside: {path} is history or flows, which a scheduled job may not fetch "
                           "(https://tickerinside.com/legal/#history); history comes from the SEC sets")
    return path


def fund_url(ticker: str) -> str:
    """The one file a fund's holdings are read from. Tickers go in the path in lower case."""
    t = (ticker or "").strip().upper()
    if not _TICKER.match(t):
        raise ValueError(f"tickerinside: {ticker!r} is no ticker")
    return BASE + check_path(f"/fund/{t.lower()}.json")


def funds_url() -> str:
    """Every covered fund with its layer, report date and position count, in one file."""
    return BASE + check_path("/funds.json")


def manifest_url() -> str:
    """The night's build: ``files.list_sha256`` checks the list of every file's sha256."""
    return BASE + check_path("/manifest.json")


def sums_url() -> str:
    """Every published file's sha256, one ``<sha256>  <path from the site's root>`` line each, gzipped."""
    return BASE + check_path("/sha256sums.txt.gz")


def status_url() -> str:
    """The night's run: ``run.fetch_holdings.kept_previous`` names the funds served from an older issuer file."""
    return BASE + check_path("/status.json")


def fund_hashes(manifest: bytes, sums: bytes) -> dict[str, str]:
    """Each ``fund/<ticker>.json``'s sha256 by upper-case ticker, from ``sha256sums.txt.gz``.

    The list is trusted only when its sha256 is the manifest's ``files.list_sha256``, which is the hash of the
    *uncompressed* list (measured 22 Nov 2026): a list of another night would call a changed file unchanged. A body
    an HTTP layer already unzipped is read the same. Raises ``ValueError`` on any other shape."""
    try:
        want = json.loads(manifest)["files"]["list_sha256"]
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"tickerinside: manifest.json has no files.list_sha256 ({type(e).__name__})") from e
    text = gzip.decompress(sums) if sums[:2] == b"\x1f\x8b" else sums
    if hashlib.sha256(text).hexdigest() != want:
        raise ValueError("tickerinside: sha256sums.txt.gz is not the list manifest.json's list_sha256 names")
    out = {}
    for line in text.decode("utf-8", errors="replace").splitlines():
        sha, _, path = line.partition("  ")
        if path.startswith("api/v1/fund/") and path.endswith(".json"):
            out[path[len("api/v1/fund/"):-len(".json")].upper()] = sha
    return out


def kept_previous(status: bytes) -> list[dict]:
    """``status.json``'s ``run.fetch_holdings.kept_previous``: the funds whose issuer file the site could not
    refresh, each ``{ticker, issuer, since, holdings_as_of}``. Raises ``ValueError`` when the list is missing."""
    try:
        rows = json.loads(status)["run"]["fetch_holdings"]["kept_previous"]
    except (ValueError, KeyError, TypeError) as e:
        raise ValueError(f"tickerinside: status.json has no kept_previous ({type(e).__name__})") from e
    if not isinstance(rows, list):
        raise ValueError("tickerinside: kept_previous is not a list")
    return [r for r in rows if isinstance(r, dict) and r.get("ticker")]


def served_ticker(key: str) -> str | None:
    """The US ticker a holdings key names, or None when the key is no US common-stock ticker.

    The keys are TickerInside's own (`https://tickerinside.com/api/sections/sources.md`, read 22 Nov 2026):
    a US share class keeps its dot (``BRK.B``, ``BF.B``), a line listed outside the US carries its market as a
    two-letter country code (``7203.JP`` Toyota in Tokyo, ``SAP.DE``), and a preferred share a file writes under its
    issuer's common ticker is that ticker and ``.PFD`` (``JPM.PFD``). So the suffix decides: one letter is a class
    and becomes our dash form, two letters is a foreign listing, ``PFD`` is not the common stock, and neither is
    served. A key of digits and a letter that an issuer file gives in place of a ticker is left to the normal rule
    and simply matches no spine ticker.
    """
    t = (key or "").strip().upper()
    if not t or not _TICKER.match(t):
        return None
    if "." in t:
        suffix = t.rsplit(".", 1)[1]
        if len(suffix) != 1 or not suffix.isalpha():
            return None
    return t.replace(".", "-")


def parse_fund(data: bytes, ticker: str) -> dict:
    """A ``fund/<ticker>.json`` answer as ``{"holdings": [...], "as_of", "layer", "positions", "cite_as"}``.

    ``holdings`` is this tree's own line shape -- ``ticker_raw``, ``ticker``, ``cusip`` (always None here: no CUSIP
    is served), ``name`` (None: the file gives none) and ``weight`` in percent -- heaviest first. A key the file
    lists under ``abroad`` is a foreign company's local code that the US list gives to another company, so it is
    kept raw with no ticker rather than served as that other company. A file for another fund, or without a
    ``holdings`` object, is a failed file, never a quiet reread."""
    try:
        doc = json.loads(data)
    except ValueError as e:
        raise ValueError(f"tickerinside: not JSON ({e})") from e
    if not isinstance(doc, dict):
        raise ValueError("tickerinside: the answer is not an object")
    got = str(doc.get("ticker") or "").strip().upper()
    want = (ticker or "").strip().upper()
    if got != want:
        raise ValueError(f"tickerinside: the file for {want} holds {got or 'no ticker'}")
    holdings = doc.get("holdings")
    if not isinstance(holdings, dict):
        raise ValueError(f"tickerinside: {want} has no holdings object")
    abroad = {str(a).strip().upper() for a in (doc.get("abroad") or []) if a}
    lines = []
    for key, weight in holdings.items():
        raw = str(key).strip().upper()
        served = None if raw in abroad else served_ticker(raw)
        try:
            w = float(weight)
        except (TypeError, ValueError):
            w = None
        lines.append({"ticker_raw": raw, "ticker": served, "cusip": None, "name": None, "weight": w})
    lines.sort(key=lambda h: h["weight"] if h["weight"] is not None else -1.0, reverse=True)
    return {"holdings": lines,
            "as_of": str(doc.get("holdings_as_of") or "") or None,
            "layer": str(doc.get("source_layer") or "") or None,
            "positions": doc.get("positions"),
            "cite_as": str(doc.get("cite_as") or "") or None}
