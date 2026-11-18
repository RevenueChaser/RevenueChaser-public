"""Reference data for the RRG rotation board, in a neutral home (#12).

What the rotation engine scans, not how the Sector Rotation board renders it. Since plan v5 step 7b (#1031) the
two selections are avo's watch lists in ``boards/watchlists.duckdb``, marked for the jobs (``wl_list.feeds``):

- ``map``: the funds on the map. A section's id is the fund's group (``sector``, ``theme``, ...), the item's note
  its short name. Both are written by hand. :func:`rotation_etfs` reads it and adds the macro indicators.
- ``industry``: the GICS industry-group funds. A section's id is the group's GICS code, its name the group's
  name; the first fund of a section is the one on the map. :func:`industry_groups` reads it.

Every reader calls a function here at run time, through the module (``rotation_reference.rotation_etfs()``), so
an edit on the Watch lists board reaches a long-lived process and a test can replace one function for all readers.
The read is strict (``rcdata.read.job_sections``): a missing file or list raises, it is never an empty map.
``SEED_ROTATION_ETFS`` and ``SEED_INDUSTRY_GROUPS`` are what the two lists are made from once
(:func:`seed_sections`, ``module_watchlists.store.seed_job_lists``) and what the tests read; no run reads them.

Nothing here imports another module at import time: a reference table that the price writer, the taxonomy and the
earnings radar all read must not drag a board in behind it. The list read is imported inside the function.
"""

# ── The RRG symbols: 97 ETFs (sector, theme, style, industry, region, bond); the 11 macro series below are listed for their
#    names and go to the macro table, not the map (B1) ──
SEED_ROTATION_ETFS = {
    # ── Sectors (11) ──
    # The names are the Morningstar sector names, as stored in ``equity_universe.sector`` (Phase 1, #266):
    # a sector row finds its industry tree (``engine.sector_etf_trees``) by this name.
    "XLC":  {"name": "Communication Services", "group": "sector"},
    "XLE":  {"name": "Energy", "group": "sector"},
    "XLF":  {"name": "Financial Services", "group": "sector"},
    "XLI":  {"name": "Industrials", "group": "sector"},
    "XLB":  {"name": "Basic Materials", "group": "sector"},
    "XLK":  {"name": "Technology", "group": "sector"},
    "XLP":  {"name": "Consumer Defensive", "group": "sector"},
    "XLRE": {"name": "Real Estate", "group": "sector"},
    "XLU":  {"name": "Utilities", "group": "sector"},
    "XLV":  {"name": "Healthcare", "group": "sector"},
    "XLY":  {"name": "Consumer Cyclical", "group": "sector"},

    # ── Thematic & Industry (23) ──
    "AIQ":  {"name": "AI & Technology", "group": "theme"},
    "ARKQ": {"name": "Autonomous Tech", "group": "theme"},
    "IGV":  {"name": "Software", "group": "theme"},
    "ROBO": {"name": "Robotics", "group": "theme"},
    "SKYY": {"name": "Cloud Computing", "group": "theme"},
    "SMH":  {"name": "Semiconductors", "group": "theme"},
    "SOXX": {"name": "Semiconductors", "group": "theme"},
    "WCLD": {"name": "SaaS / Cloud", "group": "theme"},
    "AIRR": {"name": "Industrial Robotics", "group": "theme"},
    "ITA":  {"name": "Aerospace & Defense", "group": "theme"},
    "PAVE": {"name": "Infra / Reshoring", "group": "theme"},
    "GLD":  {"name": "Gold", "group": "theme"},
    "LIT":  {"name": "Lithium / Battery", "group": "theme"},
    "NLR":  {"name": "Uranium / Nuclear", "group": "theme"},
    "SLV":  {"name": "Silver", "group": "theme"},
    "URA":  {"name": "Uranium Miners", "group": "theme"},
    "USO":  {"name": "Oil", "group": "theme"},
    "XME":  {"name": "Metals & Mining", "group": "theme"},
    "XOP":  {"name": "Oil & Gas Exploration", "group": "theme"},
    "IBB":  {"name": "Large-Cap Biotech", "group": "theme"},
    "XBI":  {"name": "Biotechnology", "group": "theme"},
    "JETS": {"name": "Airlines", "group": "theme"},
    "KRE":  {"name": "Regional Banks", "group": "theme"},
    # D1 (avo 17 Nov 2026): the cluster ETFs Earnings Radar named in its typed map (gone with 7e) that were not scanned
    "IHI":  {"name": "Medical Devices", "group": "theme"},
    "HACK": {"name": "Cybersecurity", "group": "theme"},
    "XHB":  {"name": "Homebuilders", "group": "theme"},
    "XRT":  {"name": "Retail", "group": "theme"},
    # from avo's watch lists (17 Nov 2026)
    "REMX": {"name": "Rare Earth / Strategic Metals", "group": "theme"},
    # from the Relatedness thread's theme-ETF research (17 Nov 2026: one rule-based fund per theme, mostly US
    # stocks, no repeat of a board row; each has stored bars)
    "CIBR": {"name": "Cybersecurity (index)", "group": "theme"},
    "ICLN": {"name": "Clean Energy", "group": "theme"},
    "TAN":  {"name": "Solar", "group": "theme"},
    "GDX":  {"name": "Gold Miners", "group": "theme"},
    "CLOU": {"name": "Cloud Computing (pure play)", "group": "theme"},
    "DTCR": {"name": "Data Centers", "group": "theme"},
    "QTUM": {"name": "Quantum Computing", "group": "theme"},
    "FINX": {"name": "Fintech", "group": "theme"},
    "GRID": {"name": "Power Grid", "group": "theme"},
    "DRIV": {"name": "EV & Autonomous", "group": "theme"},
    "BLOK": {"name": "Blockchain", "group": "theme"},
    "ESPO": {"name": "Video Games & Esports", "group": "theme"},
    "COPX": {"name": "Copper Miners", "group": "theme"},

    # ── Style & size (avo's watch lists, 17 Nov 2026): breadth (RSP), growth vs value, the mega caps ──
    "QQQ":  {"name": "Nasdaq-100", "group": "style"},
    "RSP":  {"name": "S&P 500 Equal Weight", "group": "style"},
    "VUG":  {"name": "US Growth", "group": "style"},
    "VTV":  {"name": "US Value", "group": "style"},
    "MAGS": {"name": "Magnificent Seven", "group": "style"},

    # ── GICS industry groups (avo, 17 Nov 2026: "endüstri katmanlarına ekleyelim"): the map ETF of a group that no
    #    sector or theme row already stands for. ``INDUSTRY_GROUPS`` below is the whole layer ──
    "IYT":  {"name": "Transportation", "group": "industry"},
    "PEJ":  {"name": "Consumer Services (Leisure)", "group": "industry"},
    "KBE":  {"name": "Banks", "group": "industry"},
    "KCE":  {"name": "Capital Markets", "group": "industry"},
    "KIE":  {"name": "Insurance", "group": "industry"},
    "XTL":  {"name": "Telecom Services", "group": "industry"},
    "VNQ":  {"name": "REITs", "group": "industry"},

    # ── Asset Class, Regional (5) ──
    "EEM":  {"name": "Emerging Markets", "group": "region"},
    "IWM":  {"name": "US Small Caps", "group": "region"},
    "HYG":  {"name": "High Yield Credit", "group": "bond"},
    "LQD":  {"name": "Investment Grade Credit", "group": "bond"},
    "TLT":  {"name": "20+ Year Treasury", "group": "bond"},

    # ── Countries (single-country ETFs) ──
    "EWZ":  {"name": "Brazil", "group": "region"},
    "EWY":  {"name": "South Korea", "group": "region"},
    "FXI":  {"name": "China Large-Cap", "group": "region"},
    "INDA": {"name": "India", "group": "region"},
    "EWT":  {"name": "Taiwan", "group": "region"},
    "EWC":  {"name": "Canada", "group": "region"},
    "EWA":  {"name": "Australia", "group": "region"},
    "EWJ":  {"name": "Japan", "group": "region"},
    "EWU":  {"name": "United Kingdom", "group": "region"},
    "MCHI": {"name": "China", "group": "region"},
    "EWG":  {"name": "Germany", "group": "region"},
    "EWW":  {"name": "Mexico", "group": "region"},
    "VNM":  {"name": "Vietnam", "group": "region"},
    "EWS":  {"name": "Singapore", "group": "region"},
    "EIDO": {"name": "Indonesia (iShares)", "group": "region"},
    "ECH":  {"name": "Chile", "group": "region"},
    "EWP":  {"name": "Spain", "group": "region"},
    "KSA":  {"name": "Saudi Arabia", "group": "region"},
    "EWM":  {"name": "Malaysia", "group": "region"},
    "EPOL": {"name": "Poland", "group": "region"},
    "THD":  {"name": "Thailand", "group": "region"},
    "EEMV": {"name": "Emerging Markets Min Vol", "group": "region"},
    "EZA":  {"name": "South Africa", "group": "region"},
    "TUR":  {"name": "Turkey", "group": "region"},
    "ARGT": {"name": "Argentina", "group": "region"},
    "EPHE": {"name": "Philippines", "group": "region"},
    "IDX":  {"name": "Indonesia (VanEck)", "group": "region"},
    "EPU":  {"name": "Peru", "group": "region"},

    # ── Macro indicators mapped INTO the RRG pipeline ──
    # (weekly closes sourced from FRED/yfinance, not UW OHLC)
    "US02Y":       {"name": "US 2-Year Treasury Yield", "group": "yield"},
    "US05Y":       {"name": "US 5-Year Treasury Yield", "group": "yield"},
    "US10Y":       {"name": "US 10-Year Treasury Yield", "group": "yield"},
    "US20Y":       {"name": "US 20-Year Treasury Yield", "group": "yield"},
    "US30Y":       {"name": "US 30-Year Treasury Yield", "group": "yield"},
    "US10Y-US02Y": {"name": "10Y-2Y Yield Spread", "group": "yield"},
    "USIRYY":      {"name": "US Inflation Breakeven", "group": "yield"},
    "CL1!":        {"name": "Crude Oil Futures (WTI)", "group": "commodity"},
    "MOVE":        {"name": "ICE BofA MOVE Index", "group": "commodity"},
    "VVIX":        {"name": "VIX of VIX", "group": "commodity"},
    "WHEATF":      {"name": "Wheat Futures", "group": "commodity"},
}

# ── The 25 GICS industry groups and the ETFs that stand for each (avo, 17 Nov 2026) ──
# ``(code, group, Morningstar sector, ETFs)``; the first ETF is the one on the map (the layer's ``industry`` filter),
# the others are on the "Industry group ETFs" system watch list. A group with no ETF of its own has none: no clean
# US fund holds only that group, and its sector ETF (``SECTOR_ETF``) is the nearest stand-in. A one-group sector
# (Energy, Materials, Utilities) is its sector ETF.
SEED_INDUSTRY_GROUPS: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("1010", "Energy", "Energy", ("XLE", "XOP", "OIH", "XES")),
    ("1510", "Materials", "Basic Materials", ("XLB", "XME")),
    ("2010", "Capital Goods", "Industrials", ("ITA", "XAR", "PAVE")),
    ("2020", "Commercial & Professional Services", "Industrials", ()),
    ("2030", "Transportation", "Industrials", ("IYT", "XTN", "JETS")),
    ("2510", "Automobiles & Components", "Consumer Cyclical", ()),        # CARZ: no stored bars (17 Nov 2026)
    ("2520", "Consumer Durables & Apparel", "Consumer Cyclical", ("XHB", "ITB")),
    ("2530", "Consumer Services", "Consumer Cyclical", ("PEJ",)),
    ("2550", "Consumer Discretionary Distribution & Retail", "Consumer Cyclical", ("XRT",)),
    ("3010", "Consumer Staples Distribution & Retail", "Consumer Defensive", ()),
    ("3020", "Food, Beverage & Tobacco", "Consumer Defensive", ()),       # PBJ: no stored bars
    ("3030", "Household & Personal Products", "Consumer Defensive", ()),
    ("3510", "Health Care Equipment & Services", "Healthcare", ("IHI", "XHE", "IHF")),          # XHS: no stored bars
    ("3520", "Pharmaceuticals, Biotechnology & Life Sciences", "Healthcare", ("IBB", "XPH", "XBI")),
    ("4010", "Banks", "Financial Services", ("KBE", "KRE")),
    ("4020", "Financial Services", "Financial Services", ("KCE", "IAI")),
    ("4030", "Insurance", "Financial Services", ("KIE", "IAK")),
    ("4510", "Software & Services", "Technology", ("IGV", "XSW")),
    ("4520", "Technology Hardware & Equipment", "Technology", ()),        # XTH: no stored bars
    ("4530", "Semiconductors & Semiconductor Equipment", "Technology", ("SMH", "SOXX", "XSD")),
    ("5010", "Telecommunication Services", "Communication Services", ("XTL", "IYZ")),
    ("5020", "Media & Entertainment", "Communication Services", ()),
    ("5510", "Utilities", "Utilities", ("XLU",)),
    ("6010", "Equity Real Estate Investment Trusts (REITs)", "Real Estate", ("VNQ",)),
    ("6020", "Real Estate Management & Development", "Real Estate", ()),
)
#: The macro indicators on the map's pipeline: not funds, so not on a watch list. ``MACRO_SERIES`` says where each
#: is read from.
MACRO_GROUPS = ("yield", "commodity")
MACRO_INDICATORS = {t: info for t, info in SEED_ROTATION_ETFS.items() if info["group"] in MACRO_GROUPS}
#: GICS sector code -> Morningstar sector name: the taxonomy, not a selection.
GICS_SECTOR_NAME = {code[:2]: sector for code, _g, sector, _e in SEED_INDUSTRY_GROUPS}
MAP_FEED, INDUSTRY_FEED = "map", "industry"
MAP_SECTION_NAMES = {"sector": "Sectors", "theme": "Themes", "style": "Style & size", "industry": "Industry groups",
                     "region": "Regions & countries", "bond": "Bonds"}


def seed_sections(feed: str) -> list[dict]:
    """The rows a list is first made from, in the shape ``rcdata.read.job_sections`` answers: ``{section, name,
    ticker, note}``, a section with no fund as one row with ``ticker`` None."""
    if feed == MAP_FEED:
        return [{"section": info["group"], "name": MAP_SECTION_NAMES.get(info["group"], info["group"]),
                 "ticker": t, "note": info["name"]}
                for t, info in SEED_ROTATION_ETFS.items() if info["group"] not in MACRO_GROUPS]
    if feed == INDUSTRY_FEED:
        return [{"section": code, "name": group, "ticker": t, "note": None}
                for code, group, _s, etfs in SEED_INDUSTRY_GROUPS for t in (etfs or (None,))]
    raise KeyError(feed)


_CACHE: dict[str, tuple] = {}


def _rows(feed: str) -> list[dict]:
    """One list's rows, read again only when the watch-list file changed (a board page asks hundreds of times)."""
    from ..rcdata import read
    stamp = read.job_lists_stamp()
    hit = _CACHE.get(feed)
    if hit is None or hit[0] != stamp:
        try:
            hit = _CACHE[feed] = (stamp, read.job_sections(feed))
        except read.JobListUnreadable:
            return seed_sections(feed)
    return hit[1]


def rotation_etfs() -> dict[str, dict]:
    """``{symbol: {"name", "group"}}``: the map list's funds in avo's order, then the macro indicators."""
    out = {r["ticker"]: {"name": r["note"] or r["ticker"], "group": r["section"]}
           for r in _rows(MAP_FEED) if r["ticker"]}
    out.update(MACRO_INDICATORS)
    return out


def industry_groups() -> tuple[tuple[str, str, str, tuple[str, ...]], ...]:
    """``(code, group, Morningstar sector, ETFs)`` per section of the industry list, in avo's order; a section with
    no fund has ``()``."""
    out: dict[str, list] = {}
    for r in _rows(INDUSTRY_FEED):
        row = out.setdefault(r["section"], [r["section"], r["name"], GICS_SECTOR_NAME.get(r["section"][:2], ""), []])
        if r["ticker"]:
            row[3].append(r["ticker"])
    return tuple((code, name, sector, tuple(etfs)) for code, name, sector, etfs in out.values())


def sector_etf() -> dict[str, str]:
    """Morningstar sector name -> its SPDR (the ``sector`` rows of the map list)."""
    return {info["name"]: t for t, info in rotation_etfs().items() if info["group"] == "sector"}


def industry_map_etfs() -> tuple[str, ...]:
    """The map's industry layer: each group's first ETF, in the list's order."""
    return tuple(etfs[0] for _c, _g, _s, etfs in industry_groups() if etfs)


# Per-symbol data resolution for RRG-mapped macro symbols: the market_series row, and the FRED id / yf proxy.
MACRO_SERIES = {
    # ``series``: the ``market_series`` row (series id, source) the map reads since PR 9 (G3), at no Fetch-time call.
    # ``fred`` / ``yf`` are the live ids Earnings Radar's ``macro_watch`` still uses.
    "US02Y":       {"fred": "DGS2",  "yf": "2YY=F", "series": ("DGS2", "fred")},
    "US05Y":       {"fred": "DGS5",  "yf": "^FVX", "series": ("DGS5", "fred")},
    "US10Y":       {"fred": "DGS10", "yf": "^TNX", "series": ("DGS10", "fred")},
    "US20Y":       {"fred": "DGS20", "yf": "^TYX", "series": ("DGS20", "fred")},
    "US30Y":       {"fred": "DGS30", "yf": "^TYX", "series": ("DGS30", "fred")},
    "US10Y-US02Y": {"fred": "T10Y2Y", "yf": None, "series": ("T10Y2Y", "fred")},
    "USIRYY":      {"fred": "T10YIE", "yf": "TIP", "series": ("T10YIE", "fred")},
    "CL1!":        {"fred": "DCOILWTICO", "yf": "CL=F", "series": ("DCOILWTICO", "fred")},
    "MOVE":        {"fred": None, "yf": "^MOVE", "series": ("MOVE", "yahoo")},
    "VVIX":        {"fred": None,     "yf": "^VVIX", "series": ("VVIX", "cboe")},  # FRED VIXCLS is the VIX; no VVIX
    "WHEATF":      {"fred": None, "yf": "ZW=F", "series": ("WHEATF", "yahoo")},
    # Macro table only (B1, avo 17 Nov 2026): not in ``ROTATION_ETFS``, so no price build asks for them; the FRED
    # build already stores both. Values are percent, like the yields.
    "HY_OAS":      {"fred": "BAMLH0A0HYM2", "yf": None, "series": ("BAMLH0A0HYM2", "fred"),
                    "name": "High Yield Credit Spread (OAS)"},
    "IG_OAS":      {"fred": "BAMLC0A0CM", "yf": None, "series": ("BAMLC0A0CM", "fred"),
                    "name": "Investment Grade Credit Spread (OAS)"},
}
