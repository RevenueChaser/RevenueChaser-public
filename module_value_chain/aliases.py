"""Company-name aliases for the Value Chain board.

A filing names its suppliers and customers in prose ("Taiwan Semiconductor
Manufacturing Company Limited", "TSMC"), not by ticker. This table maps the
legal names we expect to the ticker, after light suffix normalisation. It is a
hand-maintained list on purpose — a general resolver is a different product.
"""
from __future__ import annotations

import re

# The legal form of a company, which a filer writes or leaves out at will ("Pfizer", "Pfizer Inc.").
_FORMS = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|limited|ltd|plc|llc|"
    r"nv|sa|ag|gmbh|kk|oyj|pty)\b", re.I)

# Words neither side of the comparison owns: a leading "The", which Compustat moves into brackets at the end
# ("Home Depot Inc. (The)"), and "and", which a filer writes for the registrant's "&" ("Eli Lilly and Co" is
# "ELI LILLY & Co"). ``&`` itself is punctuation now, so both spellings leave the same gap (#1145).
_NOISE = re.compile(r"\b(the|and)\b", re.I)

# "Cos" is Compustat's spelling of "Companies" ("Lowe's Cos Inc" is "Lowe's Companies, Inc."). The word is
# **not** dropped: it is part of the name for "Capstone Companies" and "Comstock Holding Companies", which
# dropping it merged into two other issuers (#1145). It is only spelled one way.
_COS = re.compile(r"\bCOS\b")

# Words that are part of the name itself, however generic they look: two companies that differ in one of them are
# two companies ("Orion Corporation" is not "Orion Group Holdings", "Rafael Technologies" is not "Rafael
# Holdings"). ``normalize`` still drops them, so every alias key keeps its spelling; ``strict`` keeps them, and
# that is what a one-word name is matched on (#1142).
_NAME_WORDS = re.compile(
    r"\b(holdings?|group|technologies|technology|semiconductor|manufacturing|international)\b", re.I)

_SUFFIXES = re.compile(
    r"\b(incorporated|inc|corporation|corp|company|co|limited|ltd|plc|llc|"
    r"holdings?|group|technologies|technology|semiconductor|manufacturing|"
    r"international|nv|sa|ag|gmbh|kk|oyj|pty)\b", re.I)


def _clean(name: str) -> str:
    """The name upper-cased, with punctuation and the words of ``_NOISE`` gone: what both comparisons start from."""
    s = re.sub(r"[^A-Z0-9 ]+", " ", (name or "").upper())
    return " ".join(_COS.sub("COMPANIES", _NOISE.sub(" ", s)).split())


def normalize(name: str) -> str:
    return " ".join(_SUFFIXES.sub(" ", _clean(name)).split())


def strict(name: str) -> str:
    """``normalize`` without dropping the name's own words: "Rafael Technologies" -> ``RAFAEL TECHNOLOGIES``."""
    return " ".join(_FORMS.sub(" ", _clean(name)).split())


# Canonical alias -> ticker. Keys are matched after ``normalize``.
ALIASES: dict[str, str] = {
    "NVIDIA": "NVDA",
    "TAIWAN SEMICONDUCTOR": "TSM",
    "TSMC": "TSM",
    "ADVANCED MICRO DEVICES": "AMD",
    "ASML": "ASML",
    "APPLIED MATERIALS": "AMAT",
    "LAM RESEARCH": "LRCX",
    "KLA": "KLAC",
    "MICRON": "MU",
    "INTEL": "INTC",
    "QUALCOMM": "QCOM",
    "TEXAS INSTRUMENTS": "TXN",
    "BROADCOM": "AVGO",
    "MARVELL": "MRVL",
    "SYNOPSYS": "SNPS",
    "CADENCE": "CDNS",
    "APPLE": "AAPL",
    "MICROSOFT": "MSFT",
    "ALPHABET": "GOOGL",
    "GOOGLE": "GOOGL",
    "META PLATFORMS": "META",
    "FACEBOOK": "META",
    "AMAZON": "AMZN",
    "ORACLE": "ORCL",
    "SALESFORCE": "CRM",
    "ADOBE": "ADBE",
    "SERVICENOW": "NOW",
    "PALO ALTO NETWORKS": "PANW",
    "CROWDSTRIKE": "CRWD",
    "SNOWFLAKE": "SNOW",
    "CLOUDFLARE": "NET",
    "DATADOG": "DDOG",
    "ARISTA NETWORKS": "ANET",
    "DELL": "DELL",
    "HEWLETT PACKARD": "HPQ",
    "WESTERN DIGITAL": "WDC",
    "SEAGATE": "STX",
    "MICROCHIP": "MCHP",
    "ANALOG DEVICES": "ADI",
    "SKYWORKS": "SWKS",
    "QORVO": "QRVO",
    "MONOLITHIC POWER SYSTEMS": "MPWR",
    "ENTEGRIS": "ENTG",
    "COHERENT": "COHR",
    "SUPER MICRO": "SMCI",
    "VERTIV": "VRT",
    "EATON": "ETN",
    "AMPHENOL": "APH",
    "SAMSUNG": "SSNLF",
    "UNITED MICROELECTRONICS": "UMC",
    "GLOBALFOUNDRIES": "GFS",
    # Longest alias wins at a position, so HPE never falls through to HPQ.
    "HEWLETT PACKARD ENTERPRISE": "HPE",
    "HPE": "HPE",
}

# Aliases that are also ordinary English words ("a regular cadence", "our
# salesforce", "sub-micron", "coherent optical", "a microchip shortage"). They
# only match as a proper noun: Title-case ("Cadence") or ALL CAPS ("CADENCE
# DESIGN SYSTEMS").
CASE_SENSITIVE: frozenset[str] = frozenset({
    "CADENCE", "INTEL", "MICRON", "COHERENT", "SALESFORCE", "AMAZON", "APPLE",
    "ORACLE", "EATON", "DELL", "MICROCHIP",
})

# The next word proves the name is not the company ("the Amazon region",
# "our Intel Graph", "Cadence Bank", "Apple Hospitality REIT", "Eaton Vance").
DROP_FOLLOWERS: dict[str, frozenset[str]] = {
    "AMAZON": frozenset({"region", "rainforest", "basin", "river"}),
    "INTEL": frozenset({"graph"}),
    "CADENCE": frozenset({"bank"}),
    "APPLE": frozenset({"hospitality"}),
    "EATON": frozenset({"vance"}),
}

# The next word is a capitalised word of the *same* company's name, so the hit stands ("Amazon Web Services",
# "Samsung Electronics", "Super Micro Computer", "KLA Tencor"). Any other capitalised word that is not the legal
# form makes the name a different, listed company -- "Samsung SDI" is not Samsung (#1142, census row 12) -- and
# the hit is dropped, so the name is left to the spine or to no ticker at all.
NAME_CONTINUATION: frozenset[str] = frozenset({
    "WEB", "CLOUD", "AZURE", "ELECTRONICS", "COMPUTER", "COMPUTERS", "DESIGN", "TENCOR", "FOUNDRY", "SERVICES",
    "SOLUTIONS", "NETWORKS", "PLATFORMS", "DIGITAL", "SYSTEMS", "MATERIALS", "DEVICES", "INSTRUMENTS",
    "RESEARCH", "LABS", "LABORATORIES", "STORAGE", "AMERICA", "AMERICAS", "USA", "EUROPE", "ASIA", "JAPAN",
    "KOREA", "CHINA", "INDIA", "GLOBAL", "WORLDWIDE",
})

# A capitalised word straight before the name makes it part of another proper
# noun ("Avo Intel", "Private Capital Intel", "Our Intel Graph").
DROP_AFTER_CAPITALISED: frozenset[str] = frozenset({"INTEL"})

# The next word makes it a product or platform, not a counterparty ("Apple
# Pay", "Amazon Alexa", "Microsoft Teams"): kept as a display-only ``other``.
PRODUCT_FOLLOWERS: dict[str, frozenset[str]] = {
    "APPLE": frozenset({"Pay", "Music", "TV", "App", "Watch", "CarPlay", "iPad", "iPads",
                        "iPhone", "Wallet", "Maps", "Card", "News"}),
    "AMAZON": frozenset({"Alexa", "Fire", "Prime", "Sidewalk", "Appstore", "Echo", "Kindle",
                         "Bedrock", "MGM", "Basics"}),
    "GOOGLE": frozenset({"Pay", "Play", "Maps", "Chrome", "Android", "Assistant", "TV"}),
    "MICROSOFT": frozenset({"Teams", "365", "Office", "Windows", "Xbox"}),
}

# Subsidiary, operating-company and former names of a listed parent, read from the parent's own SEC Exhibit 21
# ("Subsidiaries of the Registrant") or from the filing that recorded the acquisition: "Harris Teeter Supermarkets
# Inc" is Kroger, "LinkedIn Corp" is Microsoft, "Seagen Inc" is Pfizer. A filing names the subsidiary it actually
# sells to, and a Compustat customer line carries the same name, so without this table the name reaches no
# registrant and the edge has no ticker (#1156; the headroom measurement found 92 such customer labels, of which
# these are the ones a by-hand check of every pair kept).
#
# Keys are ``_key``: ``normalize`` with the spaces gone, so the legal form and the generic name words are already
# off, and the whole name must match -- this is never a substring hit. ``resolve`` reads the table **last**, after
# the aliases and the spine, so it only fills a gap and cannot change a name that resolves today.
SUBSIDIARIES: dict[str, str] = {
    "ACADEMY": "ASO",                        # Academy LTD
    "ACCELERONPHARMA": "MRK",                # Acceleron Pharma Inc
    "ACCENTUREFEDERALSERVICES": "ACN",       # Accenture Federal Services LLC
    "ACCENTURELLP": "ACN",                   # Accenture LLP
    "ADMSARL": "ADM",                        # ADM International SARL
    "ADVANCESTORES": "AAP",                  # Advance Stores Co Inc
    "AEROJETROCKETDYNE": "LHX",              # Aerojet Rocketdyne Holdings Inc
    "ALASKAAIRLINES": "ALK",                 # Alaska Airlines Inc
    "ANTARESPHARMA": "HALO",                 # Antares Pharma Inc
    "ASDSPECIALTYHEALTHCARE": "COR",         # ASD Specialty Healthcare LLC
    "ATMELECTRONIC": "ARW",                  # ATM Electronic Corp
    "BURLINGTONCOATFACTORYINVESTMENTS": "BURL",# Burlington Coat Factory Investments Holdings Inc
    "CAREMARK": "CVS",                       # Caremark LLC
    "CARRIER": "CARR",                       # Carrier Corp
    "CELGENESWITZERLAND": "BMY",             # Celgene Switzerland LLC
    "CHENIEREMARKETINGLLP": "LNG",           # Cheniere Marketing International LLP
    "CHEVRONUSA": "CVX",                     # Chevron U.S.A. Inc
    "CONOCOPHILLIPSSKANDINAVIAAS": "COP",    # Conocophillips Skandinavia AS
    "DKTRADINGSUPPLY": "DK",                 # DK Trading & Supply LLC
    "DOLLARTREESTORES": "DLTR",              # DOLLAR TREE STORES INC
    "ENTERPRISECRUDEOIL": "EPD",             # Enterprise Crude Oil LLC
    "EQUITABLEFINANCIALLIFEINSURANCE": "EQH",# Equitable Financial Life Insurance Co
    "ETCTEXASPIPELINE": "ET",                # ETC Texas Pipeline LTD
    "EXPRESSSCRIPTS": "CI",                  # EXPRESS SCRIPTS INC
    "FEDERALEXPRESS": "FDX",                 # Federal Express Corp
    "FLORIDAPOWERLIGHT": "NEE",              # Florida Power & Light Co
    "FRANKLINTEMPLETONCOMPANIES": "BEN",     # Franklin Templeton Companies LLC
    "FRONTIERAIRLINES": "ULCC",              # Frontier Airlines Holdings Inc
    "GOODEARTHOILS": "COOT",                 # Good Earth Oils Pty Ltd
    "GOODYEAR": "GT",                        # Goodyear
    "GPMINVESTMENTS": "ARKO",                # GPM Investments LLC
    "HARRISTEETERSUPERMARKETS": "KR",        # Harris Teeter Supermarkets Inc
    "HDSUPPLY": "HD",                        # HD Supply Holdings Inc
    "IDAHOPOWER": "IDA",                     # Idaho Power Co
    "JANSSENPHARMACEUTICA": "JNJ",           # Janssen Pharmaceutica NV
    "JANSSENPHARMACEUTICALS": "JNJ",         # Janssen Pharmaceuticals Inc
    "JUNOTHERAPEUTICS": "BMY",               # Juno Therapeutics Inc
    "L3": "LHX",                             # L3 Technologies Inc
    "LIFETIME": "LTH",                       # Life Time Inc
    "LINKEDIN": "MSFT",                      # LinkedIn Corp
    "LUMENTUMOPERATIONS": "LITE",            # Lumentum Operations LLC
    "MAGELLANHEALTH": "CNC",                 # Magellan Health Inc
    "MARATHONPETROLEUMSUPPLYTRADING": "MPC", # Marathon Petroleum Supply & Trading LLC
    "MARRIOTT": "MAR",                       # Marriott International Inc
    "MCKESSONSPECIALTYCAREDISTRIBUTION": "MCK",# McKesson Specialty Care Distribution LLC
    "MERCKSHARPDOHME": "MRK",                # Merck Sharp & Dohme LLC
    "MERCKSHARPDOHMERESEARCH": "MRK",        # Merck Sharp & Dohme Research GmbH
    "MOTIONINDUSTRIES": "GPC",               # Motion Industries Inc
    "MPCPARTNERSHIP": "RMR",                 # MPC Partnership Holdings LLC
    "MSGNETWORKS": "SPHR",                   # MSG Networks Inc
    "MYOKARDIA": "BMY",                      # MyoKardia Inc
    "NBCUNIVERSALMEDIA": "CMCSA",            # NBCUniversal Media LLC
    "NEVADAPOWER": "BRK-B",                  # Nevada Power Co
    "NORFOLKSOUTHERNRAILWAY": "NSC",         # Norfolk Southern Railway Co
    "NORTHROPGRUMMANSYSTEMS": "NOC",         # Northrop Grumman Systems Corp
    "NRGBUSINESSMARKETING": "NRG",           # NRG Business Marketing LLC
    "OCCIDENTALPETROLEUM": "OXY",            # Occidental Petroleum Corp
    "ORGANON": "OGN",                        # Organon International GmbH
    "OUTBACKSTEAKHOUSEOFFLORIDA": "BLMN",    # Outback Steakhouse of Florida LLC
    "OVINTIVUSA": "OVV",                     # Ovintiv USA Inc
    "PILOTTRAVELCENTERS": "BRK-B",           # Pilot Travel Centers LLC
    "PJTPARTNERSLP": "PJT",                  # PJT Partners Holdings LP
    "PREVAILTHERAPEUTICS": "LLY",            # Prevail Therapeutics Inc
    "PRIMORISRENEWABLEENERGY": "PRIM",       # Primoris Renewable Energy Inc
    "PROMETHEUSBIOSCIENCES": "MRK",          # Prometheus Biosciences Inc
    "RAYTHEON": "RTX",                       # RAYTHEON CO / Raytheon Technologies Corp
    "ROHR": "RTX",                           # Rohr Inc
    "SAFEWAY": "ACI",                        # Safeway Inc
    "SAIAMOTORFREIGHTLINE": "SAIA",          # Saia Motor Freight Line LLC
    "SEAGEN": "PFE",                         # Seagen Inc
    "SHAWINDUSTRIES": "BRK-B",               # Shaw Industries Inc
    "SIERRAPACIFICPOWER": "BRK-B",           # Sierra Pacific Power Co
    "SPLUNK": "CSCO",                        # Splunk Inc
    "STARMARKETS": "ACI",                    # Star Markets Co Inc
    "SUPERVALU": "UNFI",                     # SUPERVALU INC
    "TECHDATA": "SNX",                       # Tech Data Corp
    "VONSCOMPANIES": "ACI",                  # Vons Companies Inc
    "WESTERNREFINING": "MPC",                # Western Refining Inc
}


# A legal form that makes the name a **different** company from the subsidiary its key stands for. "Safeway plc"
# was the British supermarket Morrisons bought in 2004, not the US "Safeway Inc" that Albertsons owns, and
# ``normalize`` drops both forms, so the two names share the one key ``SAFEWAY`` (#1156; measured read-only on the
# live store, 8 ``customer_share`` rows carry the British spelling). The form is read off ``_clean``, which keeps
# it.
SUBSIDIARY_REFUSED_FORMS: dict[str, frozenset[str]] = {
    "SAFEWAY": frozenset({"PLC"}),
}


# Tickers of one issuer: a filing naming its own other share class is not an edge.
SAME_ISSUER: dict[str, str] = {"GOOG": "GOOGL", "BRK-B": "BRK-A", "BRK.B": "BRK.A",
                               "FOX": "FOXA", "NWS": "NWSA"}


# A word that names a kind of counterparty and no company, however a listed issuer is called ("Employers
# Holdings Inc" is on the spine, so "we provide solutions to employers" resolved to EIG, #1142 census row 96).
GENERIC_PARTIES: frozenset[str] = frozenset({
    "EMPLOYERS", "CONSUMERS", "CUSTOMERS", "CLIENTS", "RETAILERS", "DISTRIBUTORS", "SUPPLIERS", "HOSPITALS",
    "GOVERNMENTS", "UNIVERSITIES", "PARTNERS", "BANKS", "INSURERS", "CARRIERS", "PHARMACIES", "MANUFACTURERS",
    "CONTRACTORS", "OPERATORS", "AIRLINES", "UTILITIES", "AGENCIES", "PROVIDERS", "PAYERS", "VENDORS", "BROKERS",
    "DEALERS", "RESELLERS", "MEMBERS", "PATIENTS", "STUDENTS", "SCHOOLS", "ENTERPRISES", "CORPORATIONS",
})


def _key(name: str) -> str:
    return normalize(name).replace(" ", "")


def _strict_key(name: str) -> str:
    return strict(name).replace(" ", "")


def spine_names(rows) -> dict[str, str | None]:
    """``{name key: ticker}`` of the spine's ``security`` rows; None for a name two issuers share (#400 WP5).

    Each row is keyed twice: under ``_key`` (the normalised name, which drops the generic words of
    ``_NAME_WORDS``) and under ``"=" + _strict_key`` (which keeps them). ``resolve`` reads the second one to
    check a one-word name against the registrant's full name (#1142).

    A name several rows carry is not ambiguous when the rows are one company (#1145; 117 of the live store's 119
    ambiguous customer labels were). ``_one_ticker`` decides, over the rows' share lines only:

    * **one CIK** (or one ``SAME_ISSUER`` group) is one company, and the name takes its first share line by
      ``_rank`` -- "FORD MOTOR CO" is F and three preferred lines, "JPMORGAN CHASE & CO" is JPM, six preferred
      lines and two ETNs;
    * **two issuers** keep the name only when exactly one of them is a Tier A share line, so a tiny OTC namesake
      loses ("Target Corp" is TGT, not Target Group Inc.) and two real namesakes stay ambiguous.
    """
    rows = [r for r in (rows or []) if str(r.get("ticker") or "").strip()]
    lines = {str(r["ticker"]).upper(): r for r in rows}
    by_key: dict[str, set[str]] = {}
    for r in rows:
        name, t = r.get("name") or "", str(r["ticker"]).upper()
        keys = [_key(name), "=" + _strict_key(name)]
        # A registrant whose name needs two of ``_NAME_WORDS`` dropped is reachable by its full name only: the
        # normalised key of "Orion Group Holdings, Inc." is ORION, which a filer's "Orion Corporation" (a Finnish
        # pharmaceutical company, not this one) matched (#1142, census row 140).
        if len(strict(name).split()) - len(normalize(name).split()) >= 2:
            keys = keys[1:]
        for k in keys:
            if len(k.lstrip("=")) >= 3:
                by_key.setdefault(k, set()).add(t)
    return {k: _one_ticker(ts, lines) for k, ts in by_key.items()}


# How much a listed line looks like the company itself, for a registrant name several of its lines carry. Tier A
# comes first, so a preferred line, an ETN and an OTC line never beat the operating share; among a company's Tier
# A lines the common share beats the ADR (none of today's spine rows has both), and an untyped line comes last --
# "COMCAST CORP" is CCZ (exchangeable notes, untyped) and CMCSA under one CIK, and the board wants CMCSA (#1145).
_LINE_RANK = {"common": 0, "adr": 1, "reit": 2, "mlp": 3}


def _rank(t: str, lines: dict[str, dict]) -> tuple:
    r = lines.get(t) or {}
    return (str(r.get("tier") or "") != "A", _LINE_RANK.get(str(r.get("security_type") or ""), 9),
            issuer(t) != t, t)


def _shares(t: str, lines: dict[str, dict]) -> bool:
    """True for a line typed as the company's own shares (#1145).

    A preferred line, an exchangeable note, an ETN, a unit, a warrant and an untyped line are not the company for
    an edge's purpose, and no board shows one: "COMCAST CORP" is CCZ (notes) as well as CMCSA, and Triton
    International has nothing listed but seven preferred lines. A name with no share line left is ambiguous.
    """
    return str((lines.get(t) or {}).get("security_type") or "") in _LINE_RANK


def _cik(t: str, lines: dict[str, dict]) -> str:
    """The CIK of ticker ``t``, or a value of its own when the spine row carries none (two such rows are two
    issuers, because nothing says they are one)."""
    return str((lines.get(t) or {}).get("cik") or "").lstrip("0") or f"?{t}"


def _one_ticker(tickers: set[str], lines: dict[str, dict]) -> str | None:
    """The one ticker a shared registrant name means, or None (#1145). See ``spine_names`` for the two rules."""
    if len(tickers) == 1:
        return next(iter(tickers))
    shares = {t for t in tickers if _shares(t, lines)}
    if not shares:
        return None
    if len({_cik(t, lines) for t in shares}) == 1 or len({issuer(t) for t in shares}) == 1:
        return min(shares, key=lambda t: _rank(t, lines))
    # Different issuers: only one of them may be a listed operating company, or the name stays ambiguous.
    real = {t for t in shares if not _rank(t, lines)[0]}
    if real and len({_cik(t, lines) for t in real}) == 1:
        return min(real, key=lambda t: _rank(t, lines))
    return None


def spine_ticker(name: str, names: dict | None) -> str | None:
    """The ticker the spine gives ``name`` (an XBRL member's label: "Mc Kesson Corporation"), or None."""
    return (names or {}).get(_key(name))


def resolve(name: str, names: dict | None = None) -> dict | None:
    """``{name, ticker}`` of the one company a free-text name means (a profile's customer or supplier, an XBRL
    member's label), or None (#410 G1).

    The hand-kept alias list and its rules come first (a product mention such as "Apple Pay" names no company);
    then the spine's names (``spine_names``); last ``SUBSIDIARIES``, the listed parent of a name that is no
    registrant itself (#1156). A name that holds two companies ("Apple and Dell"), an anonymised one
    ("Customer A") and a name two issuers share resolve to nothing; the caller keeps it as text.
    """
    hits = {h["ticker"]: h for h in find_aliases(name or "") if not h["context_only"]}
    if hits:
        return next(iter(hits.values())) if len(hits) == 1 else None
    if not spine_candidate(name or ""):
        return None
    # The strict key is read when the normalised one is not on the spine at all -- it is the only key of a
    # registrant ``spine_names`` keeps whole. A normalised key two issuers share stays ambiguous (#400 WP5).
    ticker = spine_ticker(name or "", names)
    if ticker is None and _key(name or "") not in (names or {}):
        ticker = (names or {}).get("=" + _strict_key(name or ""))
    # A name that carries one of ``_NAME_WORDS`` itself must match the registrant's name with those words kept:
    # "Rafael Technologies" is not Rafael Holdings (RFL) and "STEMCELL Technologies" is not International Stem
    # Cell (ISCO), although ``normalize`` leaves all three as the same key (#1142, census rows 19 and 40).
    if ticker and strict(name) != normalize(name) and (names or {}).get("=" + _strict_key(name)) != ticker:
        ticker = None
    # Last: a name that is a listed parent's subsidiary and no registrant of its own (#1156), unless its legal
    # form says it is a different company that shares the key.
    if ticker is None:
        key = _key(name or "")
        if not (SUBSIDIARY_REFUSED_FORMS.get(key) or frozenset()) & set(_clean(name or "").split()):
            ticker = SUBSIDIARIES.get(key)
    return {"name": name, "ticker": ticker} if ticker else None


def spine_candidate(name: str) -> bool:
    """False for a free-text name that identifies no company and must never reach the spine (#1142).

    Two shapes made four of the census's five wrong tickers: a kind of counterparty rather than a company
    ("employers" -> EIG, because "Employers Holdings Inc" is listed), and a name written with no capital letter at
    all, which a filer does not do for a company it names.
    """
    if not (name or "").strip():
        return False
    if not any(w[:1].isupper() for w in re.findall(r"[A-Za-z][A-Za-z0-9&.]*", name)):
        return False
    return not all(w in GENERIC_PARTIES for w in normalize(name).split())


# A customer a filing withholds the name of: "Customer A", "Customer 1", "One customer", "big customer" (D, owner
# 17 Nov 2026). The D2 measurement's rule, with a few more lead words.
_UNNAMED = re.compile(
    r"^\s*(?:(?:one|a|an|our|the|its|largest|large|major|significant|single|big|key|another|other|second|third)\s+)*"
    r"(?:customer|client|distributor|wholesaler|retailer|reseller|partner|payer|tenant|oem)s?"
    r"(?:\s+(?:[A-Z]|[0-9]{1,2}|one|two|three|four|five|no\.?\s*[0-9]{1,2}|#\s*[0-9]{1,2}))?\s*$", re.I)


def unnamed(name: str | None) -> bool:
    """True for a placeholder that names no company ("Customer A", "One customer")."""
    return bool(_UNNAMED.match(name or ""))


# The profile fields that name other companies (rcdata/sec_profile.py).
PROFILE_PARTIES = ("customers", "suppliers", "named_competitors")


def resolve_rate(profiles: dict[str, dict], names: dict | None) -> dict:
    """How many of the profiles' named companies ``resolve`` gives a ticker, per field: ``{field: {names,
    resolved, rate}}`` plus ``all``. Read only; the number #410 asks for before the profile edges are built."""
    out = {}
    for field in PROFILE_PARTIES:
        got = [p if isinstance(p, str) else (p or {}).get("name") for prof in profiles.values()
               for p in (prof.get(field) or [])]
        got = [g for g in got if g]
        out[field] = {"names": len(got), "resolved": sum(1 for g in got if resolve(g, names))}
    out["all"] = {k: sum(v[k] for v in out.values()) for k in ("names", "resolved")}
    for v in out.values():
        v["rate"] = round(v["resolved"] / v["names"], 3) if v["names"] else None
    return out


def issuer(ticker: str) -> str:
    t = (ticker or "").upper()
    return SAME_ISSUER.get(t, t)


def share_class_groups(rows: list[dict]) -> dict[str, list[str]]:
    """``{kept ticker: [its other share classes]}`` for every CIK with two or more tickers in ``rows`` (#408).

    Two share classes of one issuer (GOOG/GOOGL, FOX/FOXA) carry the same filing and the same profile, so a board
    keeps one ticker per CIK: the class ``SAME_ISSUER`` names, else the first alphabetically. Value Chain and
    Relatedness both read this one rule."""
    by_cik: dict[str, set[str]] = {}
    for r in rows:
        if r.get("cik"):
            by_cik.setdefault(str(r["cik"]).lstrip("0"), set()).add(r["ticker"])
    groups: dict[str, list[str]] = {}
    for tickers in by_cik.values():
        if len(tickers) > 1:
            keep = min(tickers, key=lambda t: (issuer(t) != t.upper(), t))
            groups[keep] = sorted(tickers - {keep})
    return groups


def _pattern() -> "re.Pattern[str]":
    alts = sorted(ALIASES, key=len, reverse=True)
    body = "|".join(re.escape(a).replace(r"\ ", r"\s+") for a in alts)
    return re.compile(r"\b(" + body + r")\b", re.I)


_ALIAS_RE = _pattern()
_NEXT_WORD = re.compile(r"\s+([A-Za-z0-9]+)")
_PREV_CAPITALISED = re.compile(r"\b[A-Z][a-z]+ $")


def find_aliases(text: str) -> list[dict]:
    """Every company-name hit in ``text``: ``{name, ticker, start, end, context_only}``.

    Common-word aliases must be a proper noun, and a few follower/preceder rules
    drop place names and product names; product mentions are ``context_only``.
    """
    text = text or ""
    hits: list[dict] = []
    for m in _ALIAS_RE.finditer(text):
        raw = m.group(0)
        key = " ".join(raw.upper().split())
        if key not in ALIASES:
            continue
        if key in CASE_SENSITIVE and raw not in (key.title(), key):
            continue
        nxt = _NEXT_WORD.match(text, m.end())
        word = nxt.group(1) if nxt else ""
        if word.lower() in DROP_FOLLOWERS.get(key, ()):
            continue
        if key in DROP_AFTER_CAPITALISED and _PREV_CAPITALISED.search(text, max(0, m.start() - 30), m.start()):
            continue
        if (word[:1].isupper() and word.upper() not in NAME_CONTINUATION
                and not _SUFFIXES.fullmatch(word) and word not in PRODUCT_FOLLOWERS.get(key, ())):
            continue
        hits.append({"name": key.title(), "ticker": ALIASES[key], "start": m.start(),
                     "end": m.end(), "context_only": word in PRODUCT_FOLLOWERS.get(key, ())})
    return hits

