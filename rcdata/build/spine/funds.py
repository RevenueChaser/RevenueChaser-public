"""``funds/index_holdings``: index membership from the ETF holdings files and Nasdaq's list API (daily).

**Checked against the real files of 28 Oct 2026** (homesrv's first fetch, and the files a cloud thread read for #237):
SSGA parsed there; the iShares link and the formats had moved and are read as of that day. The
tests use small files of those shapes. A format that moves again is a ``source_failed`` build issue for that file (the
others go on), never a guess.

| Index | Files |
|---|---|
| ``sp500`` | SSGA SPY (xlsx), iShares IVV (``latest-holdings.csv``) |
| ``sp400`` | SSGA MDY, iShares IJH |
| ``sp600`` | SSGA SPSM, iShares IJR |
| ``ndx`` | Nasdaq ``/api/quote/list-type/nasdaq100`` (json), Invesco QQQ (json) |
| ``dow`` | SSGA DIA (xlsx): the one file, so no vote (SP5); ``etf_class`` reads it too, the trust files no N-PORT |
| ``russell*`` (14), ``nasdaq100_top30`` | one iShares ``latest-holdings.csv`` each (:data:`SINGLE_FILE`), no vote |
| ``sp{500,400,600}_{growth,value}`` | SSGA SPYG/SPYV, MDYG/MDYV, SLYG/SLYV with iShares IVW/IVE, IJK/IJJ, IJT/IJS |
| ``sp100``, ``sp500_ex_sp100``, ``sp900_*``, ``sp1500``, ``sp_*``, ``dj_us*`` | one SSGA or iShares file each |
| ``sp*_dividend_aristocrats`` (3) | one ProShares CSV each: NOBL, REGL, TDV (:data:`PROSHARES`) |
| ``nasdaq`` | Nasdaq's stock screener (json), warrants, rights and units dropped; asked with :data:`NASDAQ_BROWSER` |
| ``sp500_<sector>`` (11), ``sp_<industry>`` (11), ``dj_us_<industry>`` (5) | the sector and industry funds' files that
  ``funds/etf_holdings`` fetches daily, read from its Parquet (:data:`DERIVED`, :func:`derived_lines`), one each |

Vanguard's VOO, IVOO and VIOO creation baskets were removed on 22 Nov 2026 (avo): they answer 401 to every keyless
request since 30 Oct, so each S&P index is voted from its SSGA and iShares files, and a name must be in both.

One request per file, every file each run (51 a run), each under its provider's day cap. Base URLs:
``RC_SSGA_BASE``, ``RC_ISHARES_BASE``, ``RC_NASDAQ_API_BASE``, ``RC_INVESCO_API_BASE``, ``RC_PROSHARES_BASE``.

**The membership rule (working choice).** On each day, a file counts when it parsed and holds at least its index's
floor (``FLOOR``: about 80% of the index); a short file is a ``fund_file_short`` build issue and does not count. A
ticker is a member of the index that day when more than half of the counting files hold it (for ``ndx``: both the
Nasdaq list and QQQ, or the one that counts when the other failed; for ``dow``: DIA's file alone). Cash, futures
and other non-equity lines are dropped by each parser. Tickers are written as the SEC file writes them (``BRK.B``
and ``BRK/B`` -> ``BRK-B``); ``spine/security`` matches them to the SEC file, by CUSIP first.

Raw: ``raw/funds/index_holdings/<as-of>/<provider>-<fund>.<ext>`` (+ ``.meta.json``). Parquet:
``parquet/funds/index_holdings/date=<as-of>/part-0.parquet`` (every holding line kept, with its file). Staging:
``stg_fund_lines`` (every day's lines) and ``stg_fund_files`` (which files counted each day).
"""
from __future__ import annotations

import csv
import io
import json
import os
import re
import time
from dataclasses import dataclass
from functools import partial
from datetime import date
from pathlib import Path
from typing import Callable

import duckdb

from ....core import calendar
from .. import base
from . import KIND, stage

NAME = "funds/index_holdings"
#: The indexes one iShares file each gives, so, like ``dow``, a member is "the file holds it" (avo, 22 Nov 2026
#: 22:42-22:43, "Russell için ulaşabileceğim bütün endeksleri ekle"): (slug, fund, product id, page slug, typed shape,
#: floor). Each CSV was read once from homesrv on 22 Nov 2026 (holdings of 20 Nov); the floor is 80 % of its
#: stock lines.
SINGLE_FILE = (
    ("russell1000", "IWB", "239707", "ishares-russell-1000-etf", True, 816),                 # 1,021 lines
    ("russell2000", "IWM", "239710", "ishares-russell-2000-etf", False, 1567),               # 1,959
    ("russell3000", "IWV", "239714", "ishares-russell-3000-etf", False, 2059),               # 2,574
    ("russell_microcap", "IWC", "239716", "ishares-micro-cap-etf", False, 1080),             # 1,350
    ("russell_midcap", "IWR", "239718", "ishares-russell-midcap-etf", True, 656),            # 820
    ("russell_top200", "IWL", "239721", "ishares-russell-top-200-etf", False, 160),          # 201
    ("russell1000_growth", "IWF", "239706", "ishares-russell-1000-growth-etf", True, 297),   # 372
    ("russell1000_value", "IWD", "239708", "ishares-russell-1000-value-etf", True, 694),     # 868
    ("russell2000_growth", "IWO", "239709", "ishares-russell-2000-growth-etf", False, 890),  # 1,113
    ("russell2000_value", "IWN", "239712", "ishares-russell-2000-value-etf", True, 1111),    # 1,389
    ("russell_midcap_growth", "IWP", "239717", "ishares-russell-midcap-growth-etf", True, 216),     # 271
    ("russell_midcap_value", "IWS", "239719", "ishares-russell-midcap-value-etf", False, 572),      # 716
    ("russell_top200_growth", "IWY", "239720", "ishares-russell-top-200-growth-etf", False, 80),    # 101
    ("russell_top200_value", "IWX", "239722", "ishares-russell-top-200-value-etf", False, 121),     # 152
    ("nasdaq100_top30", "QTOP", "339775", "ishares-nasdaq-top-30-stocks-etf", False, 24),          # 31
)
#: Group A of the index sources inventory (avo, 22 Nov 2026 23:17, "hepsini istiyorum, evet"): S&P and Dow Jones
#: indexes from their funds' SSGA xlsx and iShares CSV. Where an SSGA and an iShares fund track one index, both files
#: vote (a name must be in both, as for sp500); one file alone is "the file holds it", as for dow. (slug, SSGA funds,
#: iShares funds, floor). Each file was read once from homesrv on 22 Nov 2026 (SSGA holdings of 19 Nov, iShares of
#: 20 Nov); the floor is 80 % of the shorter file's lines.
WIDE = (
    ("sp100", (), ("OEF",), 80),                                         # OEF 101 lines
    ("sp500_growth", ("SPYG",), ("IVW",), 122),                          # SPYG 155, IVW 153
    ("sp500_value", ("SPYV",), ("IVE",), 347),                           # 436, 434
    ("sp500_ex_sp100", (), ("XOEF",), 322),                              # 403
    ("sp400_growth", ("MDYG",), ("IJK",), 196),                          # 248, 246
    ("sp400_value", ("MDYV",), ("IJJ",), 238),                           # 300, 298
    ("sp600_growth", ("SLYG",), ("IJT",), 278),                          # 353, 348
    ("sp600_value", ("SLYV",), ("IJS",), 371),                           # 466, 464
    ("sp900_growth", (), ("IUSG",), 319),                                # 399 (iShares Core S&P U.S. Growth)
    ("sp900_value", (), ("IUSV",), 586),                                 # 733 (iShares Core S&P U.S. Value)
    ("sp1500", ("SPTM",), (), 1212),                                     # 1,516
    ("sp_total_market", (), ("ITOT",), 1941),                            # 2,427
    ("sp_hy_dividend_aristocrats", ("SDY",), (), 125),                   # 157
    ("sp500_high_dividend", ("SPYD",), (), 64),                          # 80
    ("dj_us", (), ("IYY",), 752),                                        # 941
    ("dj_us_select_dividend", (), ("DVY",), 78),                         # 98
    ("dj_us_select_reit", ("RWR",), (), 78),                             # 98
)
#: Group B (avo, 22 Nov 2026 23:17): the sector and industry indexes whose fund ``funds/etf_holdings`` already
#: fetches every day. Their lines are read from that dataset's Parquet at build time (:func:`derived_lines`), never
#: fetched again here; one fund each, so a member is "the file holds it". (slug, fund, floor): 80 % of the lines of
#: the fund's file of 20 Nov 2026 in the live ``etf_holdings`` Parquet (read on homesrv, no request).
DERIVED = (
    ("sp500_energy", "XLE", 19), ("sp500_materials", "XLB", 21), ("sp500_industrials", "XLI", 68),       # 24, 27, 86
    ("sp500_consumer_discretionary", "XLY", 40), ("sp500_consumer_staples", "XLP", 29),                  # 50, 37
    ("sp500_health_care", "XLV", 51), ("sp500_financials", "XLF", 64),                                   # 64, 80
    ("sp500_information_technology", "XLK", 63), ("sp500_communication_services", "XLC", 20),            # 79, 25
    ("sp500_utilities", "XLU", 27), ("sp500_real_estate", "XLRE", 26),                                   # 34, 33
    # the S&P Select Industry indexes (SPDR), and IYT's S&P Transportation Select Industry index (iShares)
    ("sp_biotech", "XBI", 133), ("sp_oil_gas_exploration", "XOP", 42), ("sp_metals_mining", "XME", 32),  # 167, 53, 40
    ("sp_regional_banks", "KRE", 135), ("sp_homebuilders", "XHB", 28), ("sp_retail", "XRT", 60),         # 169, 36, 76
    ("sp_insurance", "KIE", 44), ("sp_banks", "KBE", 87), ("sp_capital_markets", "KCE", 54),             # 56, 109, 68
    ("sp_pharmaceuticals", "XPH", 48), ("sp_transportation", "IYT", 35),                                 # 61, 44
    # the Dow Jones U.S. Select industry indexes (iShares)
    ("dj_us_aerospace_defense", "ITA", 40), ("dj_us_home_construction", "ITB", 33),                      # 50, 42
    ("dj_us_insurance", "IAK", 47), ("dj_us_medical_equipment", "IHI", 39),                              # 59, 49
    ("dj_us_health_care_providers", "IHF", 48),                                                          # 61
)
#: Group C (avo, 22 Nov 2026 23:17): ProShares' S&P dividend funds, one CSV each, so no vote. (slug, fund, floor):
#: 80 % of the ticker lines (NOBL 68 and REGL 64 measured by the inventory; TDV 37, read once on 22 Nov 2026 with
#: the builder's own headers).
PROSHARES = (("sp500_dividend_aristocrats", "NOBL", 54), ("sp400_dividend_aristocrats", "REGL", 51),
             ("sp_technology_dividend_aristocrats", "TDV", 29))
#: Group C: the Nasdaq Composite, every stock listed on the Nasdaq, from Nasdaq's stock screener (one file, no vote).
#: 4,274 rows on 22 Nov 2026, 3,593 after the warrants, rights and units (this parser, on that answer); the floor is
#: 80 % of those.
NASDAQ_COMPOSITE = ("nasdaq", "COMP", 2875)
#: The browser headers avo approved for Nasdaq (22 Nov 2026): the screener and the nasdaq100 list send them.
NASDAQ_BROWSER = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/130.0 Safari/537.36",
                  "Accept": "application/json, text/plain, */*", "Accept-Language": "en-US,en;q=0.9",
                  "Origin": "https://www.nasdaq.com", "Referer": "https://www.nasdaq.com/"}
INDEXES = (("sp500", "sp400", "sp600", "ndx", "dow") + tuple(s[0] for s in SINGLE_FILE)
           + tuple(w[0] for w in WIDE) + tuple(d[0] for d in DERIVED) + tuple(p[0] for p in PROSHARES)
           + (NASDAQ_COMPOSITE[0],))
FLOOR = {"sp500": 400, "sp400": 320, "sp600": 480, "ndx": 80, "dow": 24, **{s[0]: s[5] for s in SINGLE_FILE},
         **{w[0]: w[3] for w in WIDE}, **{d[0]: d[2] for d in DERIVED}, **{p[0]: p[2] for p in PROSHARES},
         NASDAQ_COMPOSITE[0]: NASDAQ_COMPOSITE[2]}
#: The indexes whose members get a ``member_not_in_sec`` / ``member_not_tier_a`` issue one by one: the Russell files
#: hold thousands of small names, and per-name issues for them would flood the build issues list.
CHECKED = ("sp500", "sp400", "sp600", "ndx", "dow")
SCHEMA = [("as_of", "DATE"), ("index_slug", "TEXT"), ("provider", "TEXT"), ("fund", "TEXT"), ("ticker", "TEXT"),
          ("ticker_raw", "TEXT"), ("cusip", "TEXT"), ("name", "TEXT"), ("weight", "DOUBLE"),
          ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]
FILE_SCHEMA = [("as_of", "DATE"), ("index_slug", "TEXT"), ("provider", "TEXT"), ("fund", "TEXT"),
               ("lines", "INTEGER"), ("counted", "BOOLEAN")]
META_SUFFIX = ".meta.json"
_TICKER = re.compile(r"^[A-Z][A-Z0-9]{0,5}(-[A-Z0-9]{1,3})?$")
# iShares' product pages, by fund: (product id, page slug, typed). The CSV is the page's ``latest-holdings.csv``
# download (the page's own slug is now ``ishares-core-s-p-500-etf``; the old one still answers the same file).
# ``typed`` is which of the issuer's two CSV shapes the fund serves (``parse_ishares``), as each file answered, like
# ``etf_holdings.ISHARES_PRODUCTS``: the shape is the fund's, so a file that changes shape fails loudly.
ISHARES_PRODUCTS = {"IVV": ("239726", "ishares-core-sp-500-etf", True),
                    "IJH": ("239763", "ishares-core-sp-midcap-etf", True),
                    "IJR": ("239774", "ishares-core-sp-smallcap-etf", True),
                    **{s[1]: (s[2], s[3], s[4]) for s in SINGLE_FILE},
                    # group A, product ids from one call to the iShares product screener (22 Nov 2026)
                    "OEF": ("239723", "ishares-s-p-100-etf", False),
                    "IVW": ("239725", "ishares-s-p-500-growth-etf", True),
                    "IVE": ("239728", "ishares-s-p-500-value-etf", True),
                    "XOEF": ("344551", "ishares-s-p-500-ex-s-p-100-etf", False),
                    "IJK": ("239762", "ishares-s-p-mid-cap-400-growth-etf", True),
                    "IJJ": ("239764", "ishares-s-p-mid-cap-400-value-etf", True),
                    "IJT": ("239773", "ishares-s-p-small-cap-600-growth-etf", True),
                    "IJS": ("239775", "ishares-s-p-small-cap-600-value-etf", True),
                    "IUSG": ("239713", "ishares-core-s-p-u-s-growth-etf", True),
                    "IUSV": ("239715", "ishares-core-s-p-u-s-value-etf", True),
                    "ITOT": ("239724", "ishares-core-s-p-total-u-s-stock-market-etf", False),
                    "IYY": ("239513", "ishares-dow-jones-u-s-etf", False),
                    "DVY": ("239500", "ishares-select-dividend-etf", False)}


def norm_ticker(raw) -> str | None:
    """A holdings ticker as the SEC file writes it; None for a line that is no stock ticker (cash, futures, ``-``)."""
    t = str(raw or "").strip().upper().replace(".", "-").replace("/", "-").replace(" ", "-")
    return t if _TICKER.match(t) else None


def _cusip(raw) -> str | None:
    t = str(raw or "").strip().upper()
    return t if len(t) == 9 and t.isalnum() else None


def weight_of(raw) -> float | None:
    try:
        return float(str(raw).replace("%", "").replace(",", "").strip())
    except (TypeError, ValueError):
        return None


# ── Parsers: bytes -> [{ticker_raw, cusip, name, weight}] ──────────────────────────────────────────────────────

def parse_ssga(data: bytes) -> list[dict]:
    """SSGA's daily holdings xlsx: preamble rows, then a header row ``Name, Ticker, Identifier, SEDOL, Weight,
    Sector, Shares Held, Local Currency``; lines until the first empty row. ``Identifier`` is the CUSIP."""
    from openpyxl import load_workbook
    ws = load_workbook(io.BytesIO(data), read_only=True, data_only=True).worksheets[0]
    head, out = None, []
    for row in ws.iter_rows(values_only=True):
        cells = [str(c).strip() if c is not None else "" for c in row]
        if head is None:
            if "Ticker" in cells and "Name" in cells:
                head = {name: i for i, name in enumerate(cells) if name}
            continue
        if not any(cells):
            break
        get = lambda col: cells[head[col]] if col in head and head[col] < len(cells) else ""  # noqa: E731
        if get("Sector") in ("", "-") and not _cusip(get("Identifier")):
            continue                                         # cash and futures lines carry no sector and no CUSIP
        out.append({"ticker_raw": get("Ticker"), "cusip": _cusip(get("Identifier")), "name": get("Name"),
                    "weight": weight_of(get("Weight"))})
    if head is None:
        raise base.SourceError("ssga: no header row with Name and Ticker")
    return out


def parse_ishares(data: bytes, typed: bool = True, weight_col: str | None = None) -> list[dict]:
    """iShares' ``latest-holdings.csv``: preamble lines (fund name, ``Fund Holdings as of``), a header line starting
    ``Ticker,``, the lines, then a blank line. The issuer serves **two shapes**, both measured 30 Oct 2026, and the
    caller says which one its fund has, so a file that changed shape fails loudly instead of being read the other way:

    - ``typed`` (IVV, IJH, IJR, IAK): a ``Type`` column, and the weight in ``Market Weight``. Only ``Type`` EQUITY
      lines are a holding of the stock: swaps and warrants are filed under ``Asset Class`` Equity too;
    - not ``typed`` (SOXX, IBB, ITA, ITB, IGV): neither column. There the holdings are the ``Asset Class`` Equity
      lines and the weight is ``Weight (%)``; the lines that are no stock are a money-market fund, cash collateral,
      a future and cash, each under an ``Asset Class`` of its own. Without ``Type`` a swap filed as Equity cannot be
      told from a stock — none of those five files held one on the day they were read, and that is the whole reason
      the shape is the fund's and not the file's.

    A third shape, measured 9 Nov 2026 on ICLN: ``Type``, but the weight in ``Weight (%)``. The caller names that
    column in ``weight_col``; it is the fund's, like ``typed``.

    A file without the columns its fund's shape needs is a failed file, never a quiet reshape."""
    text = data.decode("utf-8-sig", errors="replace")
    lines = text.splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("Ticker,")), None)
    if start is None:
        raise base.SourceError("ishares: no header line starting with Ticker")
    body = []
    for line in lines[start:]:
        if not line.strip() or line.startswith("\xa0"):
            break
        body.append(line)
    reader = csv.DictReader(io.StringIO("\n".join(body)))
    fields = reader.fieldnames or ()
    held_col, default_weight = ("Type", "Market Weight") if typed else ("Asset Class", "Weight (%)")
    weight_col = weight_col or default_weight
    missing = [c for c in (held_col, weight_col) if c not in fields]
    if missing:
        shape = "typed" if typed else "untyped"
        raise base.SourceError(f"ishares: the {shape} shape needs {' and '.join(missing)}, and the file has neither"
                               if len(missing) == 2 else
                               f"ishares: the {shape} shape needs {missing[0]}, which the file has not")
    want = "EQUITY" if typed else "Equity"
    out = []
    for r in reader:
        if (r.get(held_col) or "").strip() != want:
            continue
        out.append({"ticker_raw": r.get("Ticker"), "cusip": _cusip(r.get("CUSIP")), "name": r.get("Name"),
                    "weight": weight_of(r.get(weight_col))})
    return out


def parse_nasdaq(data: bytes) -> list[dict]:
    """Nasdaq's list API: ``{"data": {"data": {"rows": [{"symbol", "companyName", ...}]}}}``."""
    body = json.loads(data)
    try:
        rows = body["data"]["data"]["rows"]
    except (KeyError, TypeError) as e:
        raise base.SourceError("nasdaq: no data.data.rows list") from e
    return [{"ticker_raw": r.get("symbol"), "cusip": None, "name": r.get("companyName"), "weight": None}
            for r in rows or [] if (r or {}).get("symbol")]


# A screener row that is no share of the company: a warrant or a right anywhere in its name, a unit at its end
# (a SPAC's ``... Units``, ``... Unit.``). An LP's "Common Units representing Limited Partner Interests" is the
# share itself and stays, as the Nasdaq Composite counts it.
_NOT_A_SHARE = re.compile(r"\b(warrants?|rights?)\b|\bunits?\.?\s*$", re.IGNORECASE)


def parse_nasdaq_screener(data: bytes) -> list[dict]:
    """Nasdaq's stock screener (``/api/screener/stocks?exchange=NASDAQ&download=true``): ``{"data": {"rows":
    [{"symbol", "name", "marketCap", "sector", ...}]}}``, every listed symbol; warrants, rights and units dropped."""
    body = json.loads(data)
    try:
        rows = body["data"]["rows"]
    except (KeyError, TypeError) as e:
        raise base.SourceError("nasdaq screener: no data.rows list") from e
    if not isinstance(rows, list):
        raise base.SourceError("nasdaq screener: no data.rows list")
    return [{"ticker_raw": r.get("symbol"), "cusip": None, "name": r.get("name"), "weight": None}
            for r in rows if (r or {}).get("symbol") and not _NOT_A_SHARE.search(str(r.get("name") or ""))]


def parse_proshares(data: bytes) -> list[dict]:
    """ProShares' daily holdings CSV: three preamble lines, then the header ``Fund Ticker, Fund Name, Security
    Ticker, Security Sedol, Security Description, ..., Market Value`` (a space after each comma). A holding is a line
    with a ``Security Ticker``; the cash line has none. The file carries no CUSIP (a SEDOL) and no weight."""
    lines = data.decode("utf-8-sig", errors="replace").splitlines()
    start = next((i for i, line in enumerate(lines) if line.startswith("Fund Ticker,")), None)
    if start is None:
        raise base.SourceError("proshares: no header line with Fund Ticker and Security Ticker")
    reader = csv.DictReader(io.StringIO("\n".join(lines[start:])), skipinitialspace=True)
    if "Security Ticker" not in (reader.fieldnames or ()):
        raise base.SourceError("proshares: no Security Ticker column")
    return [{"ticker_raw": r["Security Ticker"].strip(), "cusip": None,
             "name": (r.get("Security Description") or "").strip(), "weight": None}
            for r in reader if (r.get("Security Ticker") or "").strip()]


# Invesco's security types that are a holding of the stock: common stock and the ADRs (ASML, ARM, PDD in Oct 2026).
INVESCO_EQUITY_TYPES = ("COM", "ADR", "DRNY")


def parse_invesco(data: bytes) -> list[dict]:
    """Invesco's fund holdings API (QQQ): ``{"effectiveDate", "holdings": [{"ticker", "issuerName", "cusip",
    "percentageOfTotalNetAssets", "securityTypeCode", ...}]}``. Stock and ADR lines only (no future, currency, cash)."""
    body = json.loads(data)
    try:
        holdings = body["holdings"]
    except (KeyError, TypeError) as e:
        raise base.SourceError("invesco: no holdings list") from e
    return [{"ticker_raw": h.get("ticker"), "cusip": _cusip(h.get("cusip")), "name": h.get("issuerName"),
             "weight": weight_of(h.get("percentageOfTotalNetAssets"))}
            for h in holdings or [] if (h or {}).get("securityTypeCode") in INVESCO_EQUITY_TYPES]


# ── The files ─────────────────────────────────────────────────────────────────────────────────────────────────

def provider_base(env: str, default: str) -> str:
    return (os.getenv(env) or default).strip().rstrip("/")


@dataclass(frozen=True)
class FundFile:
    index_slug: str
    provider: str
    fund: str
    ext: str
    parse: Callable[[bytes], list[dict]]

    def url(self) -> str:
        if self.provider == "ssga":
            return (provider_base("RC_SSGA_BASE", "https://www.ssga.com")
                    + "/us/en/intermediary/library-content/products/fund-data/etfs/us/"
                    + f"holdings-daily-us-en-{self.fund.lower()}.xlsx")
        if self.provider == "ishares":
            pid, slug, _typed = ISHARES_PRODUCTS[self.fund]
            return (provider_base("RC_ISHARES_BASE", "https://www.ishares.com")
                    + f"/us/products/{pid}/{slug}/latest-holdings.csv")
        if self.provider == "proshares":
            return (provider_base("RC_PROSHARES_BASE", "https://accounts.profunds.com")
                    + f"/etfdata/ByFund/{self.fund}-psdlyhld.csv")
        if self.provider == "invesco":
            return (provider_base("RC_INVESCO_API_BASE", "https://dng-api.invesco.com")
                    + f"/cache/v1/accounts/en_US/shareclasses/{self.fund}/holdings/fund?idType=ticker&productType=ETF")
        if self.fund == NASDAQ_COMPOSITE[1]:
            return (provider_base("RC_NASDAQ_API_BASE", "https://api.nasdaq.com")
                    + "/api/screener/stocks?tableonly=true&exchange=NASDAQ&download=true")
        return provider_base("RC_NASDAQ_API_BASE", "https://api.nasdaq.com") + "/api/quote/list-type/nasdaq100"

    def headers(self) -> dict[str, str]:
        """The request headers: avo's approved browser ones for both Nasdaq files, else ``Accept: */*`` (the builder's
        own UA). Without them Nasdaq's edge closes the connection unanswered (homesrv, 22 Nov 2026: HTTP/2 reset after
        TLS, HTTP/1.1 no answer in 15 s; with them 200 and the 101 nasdaq100 rows); ``ndx`` failed so since 28 Oct."""
        return dict(NASDAQ_BROWSER) if self.provider == "nasdaq" else {"Accept": "*/*"}

    def raw_name(self) -> str:
        return f"{self.provider}-{self.fund}.{self.ext}"


def _ishares(slug: str, fund: str) -> FundFile:
    """The fund's iShares file, read as its own CSV shape (``ISHARES_PRODUCTS``)."""
    typed = ISHARES_PRODUCTS[fund][2]
    return FundFile(slug, "ishares", fund, "csv", parse_ishares if typed else partial(parse_ishares, typed=False))


FILES = (
    FundFile("sp500", "ssga", "SPY", "xlsx", parse_ssga),
    _ishares("sp500", "IVV"),
    FundFile("sp400", "ssga", "MDY", "xlsx", parse_ssga),
    _ishares("sp400", "IJH"),
    FundFile("sp600", "ssga", "SPSM", "xlsx", parse_ssga),
    _ishares("sp600", "IJR"),
    FundFile("ndx", "nasdaq", "NDX", "json", parse_nasdaq),
    FundFile("ndx", "invesco", "QQQ", "json", parse_invesco),
    # The only ``dow`` file (SP5): with one counting file the vote is "the file holds it". ``etf_class`` reads it too.
    FundFile("dow", "ssga", "DIA", "xlsx", parse_ssga),
    *(_ishares(s[0], s[1]) for s in SINGLE_FILE),
    *(FundFile(w[0], "ssga", fund, "xlsx", parse_ssga) for w in WIDE for fund in w[1]),
    *(_ishares(w[0], fund) for w in WIDE for fund in w[2]),
    *(FundFile(slug, "proshares", fund, "csv", parse_proshares) for slug, fund, _floor in PROSHARES),
    FundFile(NASDAQ_COMPOSITE[0], "nasdaq", NASDAQ_COMPOSITE[1], "json", parse_nasdaq_screener),
)
PROVIDERS = tuple(dict.fromkeys(f.provider for f in FILES))
_BY_RAW = {f.raw_name(): f for f in FILES}


def raw_dir() -> Path:
    return base.raw_root() / "funds" / "index_holdings"


def parquet_dir() -> Path:
    return base.parquet_root() / "funds" / "index_holdings"


def _meta(raw: Path) -> Path:
    return raw.with_name(raw.name + META_SUFFIX)


def derived_lines(con: duckdb.DuckDBPyConnection) -> int:
    """Add the :data:`DERIVED` funds' lines of every day ``funds/etf_holdings`` wrote to ``stg_fund_lines``, under
    their index's slug, so those files are fetched once (by that dataset) and vote here like any other file. The
    raw ticker and CUSIP are that dataset's parse of the same issuer file; the count of lines added."""
    from . import etf_holdings                  # imported here: it imports this module's parsers
    files = [f for _, f in stage.partitions(etf_holdings.parquet_dir(), "date")]
    if not files:
        return 0
    src = (f"read_parquet([{', '.join(base.sql_path(f) for f in files)}], union_by_name = true, "
           "hive_partitioning = false)")
    cases = " ".join(f"WHEN '{fund}' THEN '{slug}'" for slug, fund, _floor in DERIVED)
    funds = ", ".join(f"'{fund}'" for _slug, fund, _floor in DERIVED)
    before = stage.count(con, "stg_fund_lines")
    con.execute(f"INSERT INTO stg_fund_lines SELECT as_of, CASE etf {cases} END, provider, etf, ticker, ticker_raw, "
                f"cusip, name, weight, fetched_at, run_id FROM {src} WHERE etf IN ({funds})")
    return stage.count(con, "stg_fund_lines") - before


class FundHoldings:
    name = NAME
    kind = KIND
    providers = PROVIDERS
    tables: tuple[str, ...] = ()
    feeds = ("index_membership",)     # the fund lines are the membership vote
    cadence = "daily"
    backfill_needs_from = False
    starts_by_hand = True             # not due until a first CLI run or Fetch built it (review should-fix 2)

    def default_as_of(self) -> date:
        return calendar.today_ny()

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        out, failed = [], []
        for f in FILES:
            raw = raw_dir() / as_of.isoformat() / f.raw_name()
            if raw.exists():
                out.append(raw)
                continue
            try:
                r = base.http_get(ctx, f.provider, f.url(), headers=f.headers())
                f.parse(r.content)                                # refuse a file of the wrong shape before keeping it
            except Exception as e:  # noqa: BLE001 - one file down must not stop the others
                failed.append(f.raw_name())
                ctx.issue("source_failed", f.raw_name(), f"{type(e).__name__}: {e}"[:300])
                continue
            base.write_raw_json(_meta(raw), {"as_of": as_of.isoformat(), "fetched_at": time.time(),
                                             "run_id": ctx.run_id, "url": f.url().split("?")[0]})
            out.append(base.write_raw(raw, r.content))
        if failed:
            ctx.notes.append("failed files: " + ", ".join(failed))
            if len(failed) == len(FILES):
                raise base.SourceError("every fund file failed")
        return out

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        # The files hold today's holdings only: a backfill is today's fetch. Membership history is WRDS's.
        self.to_parquet_all(ctx, self.fetch(ctx, end))

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        return self.to_parquet_all(ctx, [raw])

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        by_day: dict[date, list[dict]] = {}
        for raw in raws:
            f = _BY_RAW.get(raw.name)
            if f is None:
                continue
            meta = base.read_raw_json(_meta(raw))
            as_of = date.fromisoformat(meta["as_of"])
            lines = f.parse(base.read_raw(raw))
            day = by_day.setdefault(as_of, [])
            for line in lines:
                day.append({"as_of": as_of, "index_slug": f.index_slug, "provider": f.provider, "fund": f.fund,
                            "ticker": norm_ticker(line["ticker_raw"]), "ticker_raw": line["ticker_raw"],
                            "cusip": line["cusip"], "name": line["name"], "weight": line["weight"],
                            "fetched_at": meta["fetched_at"], "run_id": meta["run_id"]})
        out = []
        for as_of, rows in sorted(by_day.items()):
            final = parquet_dir() / f"date={as_of.isoformat()}" / "part-0.parquet"
            if final.exists():                       # the day's other files, typed by an earlier run, stay in
                con = base.scratch_con()
                try:
                    keep = [dict(zip([c for c, _ in SCHEMA], r)) for r in con.execute(
                        f"SELECT * FROM read_parquet({base.sql_path(final)})").fetchall()]
                finally:
                    con.close()
                new = {(r["provider"], r["fund"]) for r in rows}
                rows = [r for r in keep if (r["provider"], r["fund"]) not in new] + rows
            con = base.scratch_con()
            try:
                base.rows_table(con, "rows", SCHEMA, rows)
                out.append(base.write_parquet(con, "SELECT * FROM rows ORDER BY index_slug, provider, ticker", final))
            finally:
                con.close()
        return out

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        stage.create(con, "stg_fund_lines", SCHEMA, [f for _, f in stage.partitions(parquet_dir(), "date")])
        derived_lines(con)
        floors = " ".join(f"WHEN '{k}' THEN {v}" for k, v in FLOOR.items())
        cols = ", ".join(f'"{c}" {t}' for c, t in FILE_SCHEMA)
        con.execute(f"CREATE OR REPLACE TEMP TABLE stg_fund_files ({cols})")
        con.execute("INSERT INTO stg_fund_files SELECT as_of, index_slug, provider, fund, count(*)::INTEGER, "
                    f"count(*) >= CASE index_slug {floors} ELSE 1 END FROM stg_fund_lines "
                    "WHERE ticker IS NOT NULL OR cusip IS NOT NULL GROUP BY as_of, index_slug, provider, fund")
        return {}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        # This dataset's own files: the group B lines are etf_holdings' days, which may run ahead of or behind ours.
        own = f"index_slug NOT IN ({', '.join(repr(d[0]) for d in DERIVED)})"
        latest = con.execute(f"SELECT max(as_of) FROM stg_fund_files WHERE {own}").fetchone()[0]
        counted = stage.count(con, "stg_fund_files", f"as_of = DATE '{latest}' AND counted AND {own}") if latest else 0
        # The members themselves are voted in spine/security's build (after matching to the SEC file), whose
        # index_membership is in this build already: the current members against the live file's.
        current = f"source = '{NAME}' AND valid_to IS NULL"
        added, removed = stage.compare_live(con, f"SELECT index_slug, ticker FROM index_membership WHERE {current}",
                                            "index_membership", ["index_slug", "ticker"], where=current)
        return {"dataset": NAME, "result": "changed" if added or removed else "unchanged",
                "source_as_of": (latest or ctx.as_of or self.default_as_of()).isoformat(),
                "rows": stage.count(con, "stg_fund_lines", f"as_of = DATE '{latest}' AND {own}") if latest else 0,
                "added": added, "removed": removed, "coverage": round(counted / len(FILES), 4)}


DATASET = FundHoldings()
