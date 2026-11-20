"""The fundamentals layer's test sources: a small spine and each source's answers in its documented shape.

**Not recorded from the real sources** (no SEC, WRDS, Alpha Vantage, UW or Yahoo call is made from here). The shapes
follow each source's documentation (the SEC's XBRL ``companyfacts`` API and daily index, ``docs/openapi.yaml`` for
UW); the values are chosen for the tests. The SEC CIKs are the issuers' real ones as far as known here; the gvkeys
and GICS codes are illustrative.

| Name | Case |
|---|---|
| MSFT | a 10-K / 10-Q filer: long-term debt, its current portion and short-term borrowings all reported |
| ORCL | same sub-industry as MSFT (the peer ladder's first rung) |
| HEI, HEI-A | two share classes of one CIK (one company, two tickers) |
| TM | a 20-F filer (annual only) |
| WFC-PC | Tier B: never a fundamentals company |
"""
from __future__ import annotations

from datetime import date

SPINE_AS_OF = date(2026, 10, 27)

COMPANIES = [
    {"ticker": "MSFT", "cik": "789019", "name": "MICROSOFT CORP", "exchange": "Nasdaq", "tier": "A",
     "gvkey": "012141", "gsector": "45", "ggroup": "4510", "gind": "451030", "gsubind": "45103020",
     "sector": "Information Technology", "industry": "Software & Services"},
    {"ticker": "ORCL", "cik": "1341439", "name": "ORACLE CORP", "exchange": "NYSE", "tier": "A",
     "gvkey": "012142", "gsector": "45", "ggroup": "4510", "gind": "451030", "gsubind": "45103020",
     "sector": "Information Technology", "industry": "Software & Services"},
    {"ticker": "HEI", "cik": "46619", "name": "HEICO CORP", "exchange": "NYSE", "tier": "A", "gvkey": "005567",
     "gsector": "20", "ggroup": "2010", "gind": "201010", "gsubind": "20101010", "sector": "Industrials",
     "industry": "Capital Goods"},
    {"ticker": "HEI-A", "cik": "46619", "name": "HEICO CORP", "exchange": "NYSE", "tier": "A", "gvkey": "005567",
     "gsector": "20", "ggroup": "2010", "gind": "201010", "gsubind": "20101010", "sector": "Industrials",
     "industry": "Capital Goods"},
    {"ticker": "TM", "cik": "1094517", "name": "TOYOTA MOTOR CORP/", "exchange": "NYSE", "tier": "A",
     "gvkey": "010581", "gsector": "25", "ggroup": "2510", "gind": "251020", "gsubind": "25102010",
     "sector": "Consumer Discretionary", "industry": "Automobiles & Components"},
    {"ticker": "WFC-PC", "cik": "72971", "name": "WELLS FARGO & COMPANY/MN", "exchange": "NYSE", "tier": "B"},
]
TIER_A = sorted(c["ticker"] for c in COMPANIES if c["tier"] == "A")


def spine(rows: list[dict] | None = None, as_of: date = SPINE_AS_OF) -> None:
    """Build and swap in a ``spine.duckdb`` whose ``security`` table holds ``rows`` (the spine's own schema)."""
    from RevenueChaser.rcdata import serving
    from RevenueChaser.rcdata.build.spine import security
    full = [{**{c: None for c, _ in security.SECURITY}, "source": "sec/company_tickers_exchange",
             "source_as_of": as_of, "fetched_at": 1.0, "run_id": "spine-run", **r}
            for r in (COMPANIES if rows is None else rows)]
    with serving.build("spine") as b:
        counts = {"security": security._create(b.con, "security", full)}
        # The swap refuses a build that drops a table the live file holds, and the readers' fixture
        # (``spine_fixture.write_security``) creates all four, so the build carries the other three empty.
        for table in ("security_history", "gics_history", "index_membership"):
            counts[table] = security._create(b.con, table, [])
        b.swap(counts)


def parquet_root() -> None:
    """The builder refuses a missing Parquet root (the raw disk not mounted): the tests make it."""
    from RevenueChaser.rcdata.build import base
    base.parquet_root().mkdir(parents=True, exist_ok=True)


def run(name: str, as_of: str | None = None, *, sleep=None, clock=None, **params) -> dict:
    """One CLI request of dataset ``name`` (attended ones run too), daily unless ``params`` say otherwise; no real
    sleep unless ``sleep`` is given."""
    import time

    from RevenueChaser.rcdata.build import base
    parquet_root()
    p = dict(params)
    if as_of:
        p.setdefault("as_of", as_of)
    return base.run_request({"dataset": name, "requested_by": "cli", "params": p},
                            sleep=sleep or (lambda s: None), clock=clock or time.monotonic)


def q(sql: str, *params) -> list[tuple]:
    from RevenueChaser.rcdata import serving
    con = serving.open_read("fundamentals")
    try:
        return con.execute(sql, list(params)).fetchall()
    finally:
        con.close()


# ── The SEC: company facts and the daily index ────────────────────────────────────────────────────────────────

def _fact(val, end, accn, filed, form, fp, fy, start=None):
    f = {"val": val, "end": end, "accn": accn, "filed": filed, "form": form, "fp": fp, "fy": fy}
    if start:
        f["start"] = start
    return f


# MSFT (fiscal year to 30 June): FY2025 from the 10-K, Q1 FY2026 (to 30 Sep 2025) from the 10-Q, Q1 FY2027 (to 30
# Sep 2026) from the 10-Q filed 2026-10-27 when ``with_new_quarter``. Values in USD, chosen for the tests.
K25, Q26, Q27 = "0000950170-25-100001", "0000950170-25-130001", "0000950170-26-130001"


def msft_facts(with_new_quarter: bool = False) -> dict:
    def series(fy_val, q_val, q27_val=None, instant=False):
        fy_start, q_start, q27_start = (None, None, None) if instant else ("2024-07-01", "2025-07-01", "2026-07-01")
        out = [_fact(fy_val, "2025-06-30", K25, "2025-07-30", "10-K", "FY", 2025, fy_start),
               _fact(q_val, "2025-09-30", Q26, "2025-10-29", "10-Q", "Q1", 2026, q_start)]
        if with_new_quarter and q27_val is not None:
            out.append(_fact(q27_val, "2026-09-30", Q27, "2026-10-27", "10-Q", "Q1", 2027, q27_start))
        return out

    gaap = {
        "Revenues": {"units": {"USD": series(281_000, 77_000, 80_000)}},
        "CostOfRevenue": {"units": {"USD": series(87_000, 24_000, 25_000)}},
        "NetIncomeLoss": {"units": {"USD": series(101_000, 27_000, 28_000)}},
        "LongTermDebtNoncurrent": {"units": {"USD": series(40_000, 39_000, 38_000, instant=True)}},
        "LongTermDebtCurrent": {"units": {"USD": series(3_000, 2_500, 2_000, instant=True)}},
        "ShortTermBorrowings": {"units": {"USD": series(500, 400, 300, instant=True)}},
        "Assets": {"units": {"USD": series(500_000, 510_000, 520_000, instant=True)}},
        "CashAndCashEquivalentsAtCarryingValue": {"units": {"USD": series(30_000, 28_000, 27_000, instant=True)}},
        "ShortTermInvestments": {"units": {"USD": series(64_000, 60_000, 59_000, instant=True)}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": series(13.64, 3.65, 3.80)}},
    }
    return {"cik": 789019, "entityName": "MICROSOFT CORPORATION", "facts": {"us-gaap": gaap}}


# HEI (fiscal year to 31 October): one 10-K a year ago and quarters long past, so its newest statement is old.
def hei_facts() -> dict:
    gaap = {"Revenues": {"units": {"USD": [
        _fact(3_900, "2024-10-31", "0000046619-24-000050", "2024-12-20", "10-K", "FY", 2024, "2023-11-01"),
        _fact(1_000, "2025-04-30", "0000046619-25-000020", "2025-05-28", "10-Q", "Q2", 2025, "2025-02-01")]}}}
    return {"cik": 46619, "entityName": "HEICO CORP", "facts": {"us-gaap": gaap}}


# TM files IFRS facts only (a 20-F filer): no us-gaap taxonomy.
def tm_facts() -> dict:
    return {"cik": 1094517, "entityName": "TOYOTA MOTOR CORP", "facts": {"ifrs-full": {"Revenue": {"units": {
        "JPY": [_fact(48e12, "2025-03-31", "0001193125-25-150000", "2025-06-25", "20-F", "FY", 2025, "2024-04-01")]}}}}}


def daily_index(rows: list[tuple[str, str, str, str, str]]) -> str:
    """A ``master.<YYYYMMDD>.idx`` body: ``rows`` of (cik, company, form, YYYYMMDD, accession)."""
    head = ("Description:           Daily Index of EDGAR Dissemination Feed by Company Name\n"
            "Last Data Received:    October 27, 2026\n\n"
            "CIK|Company Name|Form Type|Date Filed|Filename\n"
            "--------------------------------------------------------------------------------\n")
    return head + "".join(f"{c}|{n}|{f}|{d}|edgar/data/{c}/{a}.txt\n" for c, n, f, d, a in rows)


def sec_routes(http_mock, facts_by_cik: dict, indexes: dict | None = None) -> None:
    """Answer the companyfacts and daily-index URLs: ``facts_by_cik`` {cik: body or callable}, ``indexes``
    {YYYYMMDD: body}. Anything else at the SEC answers 404 (the mock's default), except a daily index no test
    named: EDGAR publishes one for every open day, so that answers an index with no rows (an index the archive
    does not hold answers 403, which a reader reads as a day EDGAR was closed)."""
    for day, body in (indexes or {}).items():
        http_mock.add(f"master.{day}.idx", body)
    http_mock.fallback("master.", daily_index([]))
    for cik, body in facts_by_cik.items():
        http_mock.add(f"companyfacts/CIK{int(cik):010d}.json", body)


# ── The SEC: filing lists and documents ───────────────────────────────────────────────────────────────────────

def submissions(cik, rows: list[tuple[str, str, str, str, str, str]], name: str = "") -> dict:
    """A submissions answer: ``rows`` of (accession, form, filingDate, reportDate, primaryDocument, items)."""
    keys = ("accessionNumber", "form", "filingDate", "reportDate", "primaryDocument", "items")
    recent = {k: [r[i] for r in rows] for i, k in enumerate(keys)}
    return {"cik": str(cik), "name": name, "filings": {"recent": recent, "files": []}}


EIGHT_K = "0001193125-25-250001"
PROXY = "0001193125-25-240001"
MSFT_FILINGS = [
    (EIGHT_K, "8-K", "2025-10-29", "2025-10-29", "msft-8k.htm", "2.02,9.01"),
    (Q26, "10-Q", "2025-10-29", "2025-09-30", "msft-10q.htm", ""),
    (PROXY, "DEF 14A", "2025-10-20", "2025-12-05", "msft-def14a.htm", ""),
    (K25, "10-K", "2025-07-30", "2025-06-30", "msft-10k.htm", ""),
    ("0000789019-25-000077", "4", "2025-08-01", "2025-07-30", "xslF345X05/form4.xml", ""),
]


def ten_k(body_chars: int = 5_000, stop: bool = True) -> str:
    """A 10-K body: a contents page, then Item 1 Business of ``body_chars`` characters, then Item 1A."""
    words = ("We develop software and cloud services. Our customers include enterprises. " * (body_chars // 75 + 1))
    return ("<html><body><p>Item 1. Business</p><p>Item 1A. Risk Factors</p>"
            f"<p>PART I</p><p>Item 1. Business</p><p>{words[:body_chars]}</p>"
            + ("<p>Item 1A. Risk Factors</p><p>Risks.</p>" if stop else "") + "</body></html>")


def proxy(chars: int = 5_000) -> str:
    words = ("Executive compensation and the board. " * (chars // 38 + 1))[:chars]
    return "<html><body><p>" + words + "</p></body></html>"


def _ctx(cid: str, start: str | None, end: str, dims: dict | None = None) -> str:
    seg = "".join(f'<xbrldi:explicitMember dimension="{a}">{m}</xbrldi:explicitMember>'
                  for a, m in (dims or {}).items())
    period = (f"<xbrli:startDate>{start}</xbrli:startDate><xbrli:endDate>{end}</xbrli:endDate>" if start else
              f"<xbrli:instant>{end}</xbrli:instant>")
    return (f'<xbrli:context id="{cid}"><xbrli:entity><xbrli:identifier scheme="http://www.sec.gov/CIK">0000789019'
            f'</xbrli:identifier>{f"<xbrli:segment>{seg}</xbrli:segment>" if seg else ""}</xbrli:entity>'
            f"<xbrli:period>{period}</xbrli:period></xbrli:context>")


def _ix(name: str, ctx: str, value: str, unit: str = "usd", scale: str = "6", sign: str = "") -> str:
    sign_attr = f' sign="{sign}"' if sign else ""
    return (f'<ix:nonFraction name="{name}" contextRef="{ctx}" unitRef="{unit}" decimals="-6" scale="{scale}"'
            f'{sign_attr} format="ixt:num-dot-decimal"><span>{value}</span></ix:nonFraction>')


SEGMENT_AXIS = "us-gaap:StatementBusinessSegmentsAxis"
CUSTOMER_DIMS = {"us-gaap:ConcentrationRiskByBenchmarkAxis": "us-gaap:RevenueFromContractWithCustomerMember",
                 "us-gaap:ConcentrationRiskByTypeAxis": "us-gaap:CustomerConcentrationRiskMember",
                 "srt:MajorCustomersAxis": "msft:CustomerAMember"}


def ixbrl_10k() -> str:
    """MSFT's 10-K for FY2025 as inline XBRL: revenue by business segment (two, and the year before), by product,
    by country, one two-dimension context (not a segment), and Customer A's share of revenue (12%, 11% a year
    before). Values in millions (``scale`` 6), chosen for the tests."""
    fy25, fy24 = ("2024-07-01", "2025-06-30"), ("2023-07-01", "2024-06-30")
    rev = "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax"
    contexts = "".join([
        _ctx("c-fy25", *fy25),
        _ctx("c-cloud25", *fy25, {SEGMENT_AXIS: "msft:IntelligentCloudMember"}),
        _ctx("c-pc25", *fy25, {SEGMENT_AXIS: "msft:MorePersonalComputingMember"}),
        _ctx("c-cloud24", *fy24, {SEGMENT_AXIS: "msft:IntelligentCloudMember"}),
        _ctx("c-xbox25", *fy25, {"srt:ProductOrServiceAxis": "msft:XboxContentAndServicesMember"}),
        _ctx("c-us25", *fy25, {"srt:StatementGeographicalAxis": "country:US"}),
        _ctx("c-two25", *fy25, {SEGMENT_AXIS: "msft:IntelligentCloudMember", "srt:StatementGeographicalAxis":
                                "country:US"}),
        _ctx("c-cust25", *fy25, CUSTOMER_DIMS),
        _ctx("c-cust24", *fy24, CUSTOMER_DIMS),
    ])
    units = ('<xbrli:unit id="usd"><xbrli:measure>iso4217:USD</xbrli:measure></xbrli:unit>'
             '<xbrli:unit id="pure"><xbrli:measure>xbrli:pure</xbrli:measure></xbrli:unit>')
    facts = "".join([
        _ix(rev, "c-fy25", "281,724"), _ix(rev, "c-cloud24", "87,907"),      # the year before comes first
        _ix("us-gaap:Revenues", "c-cloud25", "106,000"), _ix(rev, "c-cloud25", "106,265"),
        _ix(rev, "c-pc25", "51,500"), _ix(rev, "c-xbox25", "23,455"),
        _ix(rev, "c-us25", "144,546"), _ix(rev, "c-two25", "1"),
        _ix("us-gaap:ConcentrationRiskPercentage1", "c-cust25", "12", unit="pure", scale="-2"),
        _ix("us-gaap:ConcentrationRiskPercentage1", "c-cust24", "11", unit="pure", scale="-2"),
    ])
    return ('<html><body><div style="display:none"><ix:header><ix:resources>' + contexts + units +
            "</ix:resources></ix:header></div>" + ten_k(5_000)[len("<html><body>"):-len("</body></html>")] +
            "<p>Item 8. Financial Statements</p><table><tr><td>" + facts + "</td></tr></table></body></html>")


def def_linkbase(roles: dict[str, dict[str, list[str]]]) -> str:
    """A definition linkbase (``_def.xml``) in the shape a filing has it: per role (``{role id: {axis: [members]}}``,
    names as the linkbase writes them, ``us-gaap_ProductMember``) a table whose axis reaches a domain and the
    domain its members."""
    arc = '<link:definitionArc xlink:arcrole="http://xbrl.org/int/dim/arcrole/{}" xlink:from="{}" xlink:to="{}"/>'
    loc = '<link:loc xlink:type="locator" xlink:label="{0}" xlink:href="https://sec.test/elts.xsd#{0}"/>'
    links = []
    for role, axes in roles.items():
        parts = [loc.format("us-gaap_StatementTable")]
        for axis, members in axes.items():
            domain = axis.replace("Axis", "Domain")
            parts += [loc.format(axis), arc.format("hypercube-dimension", "us-gaap_StatementTable", axis),
                      loc.format(domain), arc.format("dimension-domain", axis, domain)]
            for member in members:
                parts += [loc.format(member), arc.format("domain-member", domain, member)]
        links.append(f'<link:definitionLink xlink:type="extended" xlink:role="http://sec.test/role/{role}">'
                     + "".join(parts) + "</link:definitionLink>")
    return ('<?xml version="1.0" encoding="UTF-8"?><link:linkbase xmlns:link="http://www.xbrl.org/2003/linkbase" '
            'xmlns:xlink="http://www.w3.org/1999/xlink">' + "".join(links) + "</link:linkbase>")


# The linkbase of ``ixbrl_10k``'s filing: the two segments stand in the segment note, the country there and in a
# second table, and the product member in none.
MSFT_DEF_NAME = "msft-20250630_def.xml"
MSFT_DEF = def_linkbase({
    "SegmentDetails": {"us-gaap_StatementBusinessSegmentsAxis": ["msft_IntelligentCloudMember",
                                                                 "msft_MorePersonalComputingMember"],
                       "srt_StatementGeographicalAxis": ["country_US"]},
    "GeographicDetails": {"srt_StatementGeographicalAxis": ["country_US"]},
})


MSFT_XSD_NAME = "msft-20250630.xsd"


def schema(linkbase: str = "") -> str:
    """A filing's schema file (``.xsd``); ``linkbase`` (a ``def_linkbase``) is embedded as the filers who file no
    ``_def.xml`` do it (#1066), in the schema's ``appinfo``. Without one it still names the linkbase files' roles,
    as every filing's schema does."""
    return ('<?xml version="1.0" encoding="UTF-8"?><xsd:schema xmlns:xsd="http://www.w3.org/2001/XMLSchema" '
            'xmlns:link="http://www.xbrl.org/2003/linkbase" xmlns:xlink="http://www.w3.org/1999/xlink">'
            '<xsd:annotation><xsd:appinfo><link:linkbaseRef xlink:type="simple" xlink:href="msft-20250630_pre.xml" '
            'xlink:role="http://www.xbrl.org/2003/role/definitionLinkbaseRef"/>' + linkbase.split("?>", 1)[-1] +
            '</xsd:appinfo></xsd:annotation><xsd:element name="IntelligentCloudMember"/></xsd:schema>')


def linkbase_routes(http_mock, xml: str | None = MSFT_DEF, name: str = MSFT_DEF_NAME, xsd: str | None = None) -> None:
    """Answer a filing's ``index.json`` and the linkbase itself: ``name`` is listed when ``xml`` is given, the
    schema file when either is (a filing with a ``_def.xml`` has its ``.xsd`` too) and answered when ``xsd`` is."""
    items = [{"name": "msft-10k.htm", "size": "900000"}]
    items += [{"name": MSFT_XSD_NAME, "size": "50000"}] if xml or xsd is not None else []
    http_mock.add("index.json", {"directory": {"item": items + ([{"name": name, "size": "9000"}] if xml else [])}})
    if xml:
        http_mock.add(f"/{name}", xml)
    if xsd is not None:
        http_mock.add(f"/{MSFT_XSD_NAME}", xsd)


def filing_routes(http_mock, lists: dict, documents: dict | None = None) -> None:
    """Answer the submissions URLs (``lists`` {cik: body}) and the archive documents (``documents`` {file: html}).
    A daily index no test named answers an index with no rows, as EDGAR does for an open day."""
    for cik, body in lists.items():
        http_mock.add(f"submissions/CIK{int(cik):010d}.json", body)
    for name, html in (documents or {}).items():
        http_mock.add(f"/{name}", html)
    http_mock.fallback("master.", daily_index([]))


# ── WRDS: Compustat's statements and WRDS's ratios (a fake worker, never WRDS) ────────────────────────────────
# Compustat values are in millions (MSFT's 77,000 USD revenue is 0.077); as text, as the worker writes them.
# ``month`` 2 is the next monthly snapshot: MSFT's Sep-2025 net income revised, its Jun-2025 revenue gone, and a new
# quarter (not a revision).

def fundq_rows(month: int = 1) -> list[dict]:
    rows = [
        {"gvkey": "012141", "datadate": "2025-06-30", "fyearq": "2025", "fqtr": "4", "fyr": "6", "rdq": "2025-07-30",
         "revtq": "0.075", "niq": "0.025", "epsfxq": "3.4"},
        {"gvkey": "012141", "datadate": "2025-09-30", "fyearq": "2026", "fqtr": "1", "fyr": "6", "rdq": "2025-10-29",
         "revtq": "0.077", "cogsq": "0.024", "niq": "0.027", "epspxq": "3.66", "epsfxq": "3.65", "atq": "0.51",
         "dlttq": "0.039", "dlcq": "0.0029", "cheq": "0.028"},
        # HEI's quarter disagrees with the SEC's 1,000 USD revenue.
        {"gvkey": "005567", "datadate": "2025-04-30", "fyearq": "2025", "fqtr": "2", "fyr": "10",
         "rdq": "2025-05-28", "revtq": "0.0012"},
    ]
    if month >= 2:
        rows[0] = {**rows[0], "revtq": None}
        rows[1] = {**rows[1], "niq": "0.0272"}
        rows.append({"gvkey": "012141", "datadate": "2026-09-30", "fyearq": "2027", "fqtr": "1", "fyr": "6",
                     "revtq": "0.08"})
    return rows


FUNDA_ROWS = [{"gvkey": "012141", "datadate": "2025-06-30", "fyear": "2025", "fyr": "6", "revt": "0.281",
               "ni": "0.101", "epsfx": "13.64", "at": "0.5"}]

# Compustat's segments: MSFT's FY2025 business segment from two source filings (the newer one wins), a
# geographic one, and a state segment (not asked for, so not kept); Customer A's sales.
SEGMERGED_ROWS = [
    {"gvkey": "012141", "datadate": "2025-06-30", "srcdate": "2025-07-30", "stype": "BUSSEG", "sid": "1",
     "snms": "Intelligent Cloud", "sales": "0.106265"},
    {"gvkey": "012141", "datadate": "2025-06-30", "srcdate": "2024-07-30", "stype": "BUSSEG", "sid": "1",
     "snms": "Intelligent Cloud", "sales": "0.1"},
    {"gvkey": "012141", "datadate": "2025-06-30", "srcdate": "2025-07-30", "stype": "GEOSEG", "sid": "2",
     "snms": "United States", "sales": "0.144546"},
    {"gvkey": "012141", "datadate": "2025-06-30", "srcdate": "2025-07-30", "stype": "STSEG", "sid": "9",
     "snms": "Washington", "sales": "0.001"},
]
SEG_CUSTOMER_ROWS = [
    {"gvkey": "012141", "datadate": "2025-06-30", "cnms": "Customer A", "ctype": "COMPANY", "salecs": "0.03372",
     "stype": "BUSSEG", "sid": "1"},
]


# WRDS's catalog as the fake answers it: the relations a query may name and their columns, also the answer to an
# ``information_schema.columns`` query. One fact comes from the server run of 2026-10-29 (PR 249):
# ``seg_customer`` has no ``srcdate``. The rest is the documented columns, not checked against WRDS. A query that names a relation or a column not here fails as PostgreSQL's would.
_COMPUSTAT = ["gvkey", "datadate", "indfmt", "datafmt", "popsrc", "consol", "fyr"]
WRDS_CATALOG = {
    ("comp", "fundq"): _COMPUSTAT + ["fyearq", "fqtr", "rdq", "revtq", "cogsq", "oiadpq", "niq", "epspxq", "epsfxq",
                                     "atq", "dlttq", "dlcq", "cheq", "ceqq"],
    ("comp", "funda"): _COMPUSTAT + ["fyear", "revt", "cogs", "oiadp", "ni", "epspx", "epsfx", "at", "dltt", "dlc",
                                     "che", "ceq", "oancf", "capx"],
    ("comp_segments_hist_daily", "wrds_segmerged"): ["gvkey", "datadate", "srcdate", "stype", "sid", "snms",
                                                     "sales"],
    ("comp_segments_hist_daily", "seg_customer"): ["gvkey", "datadate", "cid", "cnms", "ctype", "salecs", "stype",
                                                   "sid"],
    ("comp", "exrt_dly"): ["fromcurd", "tocurd", "datadate", "exratd"],
    ("audit_audit_comp", "feed39_financial_restatements"): [
        "restatement_notification_key", "company_fkey", "file_date", "form_fkey", "res_begin_date", "res_end_date",
        "date_of_8k_402", "res_accounting", "res_fraud", "res_clerical_errors", "res_other", "res_adverse",
        "res_improves", "res_sec_investigation", "res_board_approval", "res_auditor_letter",
        "quarterly_restated_only", "disclosure_text"],
    ("audit_audit_comp", "feed20_nt"): ["nt_notify_key", "company_fkey", "file_date", "form_fkey", "pe_date_num",
                                        "nt_reas_keys", "nt_reas_titles", "narrative_text"],
    ("audit_audit_comp", "feed17_director_and_officer_chan"): [
        "do_change_key", "do_off_pers_key", "company_fkey", "file_date", "form_fkey", "eff_date", "action",
        "title_standard", "is_ceo", "is_cfo", "is_coo", "is_president", "is_chair", "is_c_level", "is_bdmem_pers",
        "interim", "last_name"],
}

# Audit Analytics' feeds (#1181 step C): ``company_fkey`` is the CIK without leading zeros (789019 is MSFT, 46619
# HEI; 999999 is no company of ours). Made-up events; the flag values are invented, their real coding is unmeasured.
AUDIT_ROWS = {
    "feed39_financial_restatements": [
        {"restatement_notification_key": "9001", "company_fkey": "789019", "file_date": "2025-08-01",
         "form_fkey": "8-K", "res_begin_date": "2024-07-01", "res_end_date": "2025-03-31", "res_accounting": "1",
         "res_fraud": "0", "disclosure_text": "never asked"},
        {"restatement_notification_key": "9002", "company_fkey": "999999", "file_date": "2026-09-21",
         "form_fkey": "10-K/A", "res_accounting": "1", "res_fraud": "1"},
    ],
    "feed20_nt": [
        {"nt_notify_key": "7001", "company_fkey": "46619", "file_date": "2026-09-15", "form_fkey": "NT 10-Q",
         "pe_date_num": "20260731", "nt_reas_titles": "Other", "narrative_text": "never asked"},
    ],
    "feed17_director_and_officer_chan": [
        {"do_change_key": "5001", "do_off_pers_key": "1", "company_fkey": "789019", "file_date": "2026-09-24",
         "form_fkey": "8-K", "eff_date": "2026-10-01", "action": "Appointed", "title_standard": "CFO",
         "is_cfo": "1", "is_ceo": "0", "last_name": "never asked"},
        {"do_change_key": "5001", "do_off_pers_key": "2", "company_fkey": "789019", "file_date": "2026-09-24",
         "form_fkey": "8-K", "action": "Resigned", "title_standard": "CFO", "is_cfo": "1", "is_ceo": "0"},
        {"do_change_key": "5002", "do_off_pers_key": "3", "company_fkey": "0000046619", "file_date": "2025-02-03",
         "form_fkey": "8-K", "action": "Retired", "is_ceo": "1"},
        {"do_change_key": "5002", "do_off_pers_key": "3", "company_fkey": "0000046619", "file_date": "2025-02-03",
         "form_fkey": "8-K", "action": "Retired", "is_ceo": "1"},                       # the same row twice
    ],
}

# Compustat's daily rates, every one quoted from GBP (measured 20 Nov 2026, #1181): 1.25 USD and 1.75 CAD per GBP.
EXRT_ROWS = [
    {"fromcurd": "GBP", "tocurd": "USD", "datadate": "2026-10-26", "exratd": "1.25"},
    {"fromcurd": "GBP", "tocurd": "CAD", "datadate": "2026-10-26", "exratd": "1.75"},
    {"fromcurd": "GBP", "tocurd": "GBP", "datadate": "2026-10-26", "exratd": "1"},
    {"fromcurd": "GBP", "tocurd": "USD", "datadate": "2026-10-23", "exratd": "1.2"},
    {"fromcurd": "GBP", "tocurd": "CAD", "datadate": "2026-10-23", "exratd": "0"},        # no rate that day
    {"fromcurd": "GBP", "tocurd": "JPY", "datadate": "2026-10-22", "exratd": "190"},      # no USD row that day
]


class FakeFundWrds:
    """A WRDS worker that answers ``comp.fundq``, ``comp.funda`` and the segment
    tables from the rows above, filtered by the query's gvkey list, and WRDS's catalog (``catalog``, by default
    ``WRDS_CATALOG``) from ``information_schema.columns``; it records every query."""

    def __init__(self, catalog: dict | None = None):
        self.queries: list[str] = []
        self.month = 1
        self.catalog = WRDS_CATALOG if catalog is None else catalog

    def query(self, sql: str, out) -> int:
        import re

        from RevenueChaser.rcdata.build import base

        from .spine_fixture import write_jsonl
        self.queries.append(sql)
        if "FROM information_schema.columns" in sql:
            want = set(re.findall(r"'(\w+)'", re.search(r"table_name IN \(([^)]*)\)", sql).group(1)))
            rows = [{"table_schema": lib, "table_name": table, "column_name": col}
                    for (lib, table), cols in self.catalog.items() if table in want for col in cols]
            write_jsonl(out, rows)
            return len(rows)
        library, table = re.search(r"FROM (\w+)\.(\w+)", sql).groups()
        if (library, table) not in self.catalog:
            raise base.SourceError(f'wrds query failed: relation "{library}.{table}" does not exist')
        select, where = re.match(r"SELECT (.*?) FROM \S+(?: WHERE (.*))?$", sql, re.S).groups()
        named = [c.strip() for c in select.split(",")] + re.findall(r"(\w+) (?:IN \(|>= |= )", where or "")
        for col in named:
            if col not in self.catalog[(library, table)]:
                raise base.SourceError(f'wrds query failed: column "{col}" does not exist')
        rows = {"fundq": fundq_rows(self.month), "funda": FUNDA_ROWS,
                "wrds_segmerged": SEGMERGED_ROWS, "seg_customer": SEG_CUSTOMER_ROWS, "exrt_dly": EXRT_ROWS, **AUDIT_ROWS}[table]
        gvkeys = re.search(r"gvkey IN \(([^)]*)\)", sql)
        if gvkeys:
            want = set(re.findall(r"'(\d+)'", gvkeys.group(1)))
            rows = [r for r in rows if r["gvkey"] in want]
        # The columns asked, as WRDS answers them (a row's other keys are not sent).
        rows = [{c: r.get(c) for c in select.split(", ")} for r in rows]
        write_jsonl(out, rows)
        return len(rows)

    def close(self):
        pass
