"""``etf``: the ETF universe, one row per ticker, built by ``spine/security`` from the staging of
``alphavantage/listing_status`` and ``sec/ncen`` and from the ``etp`` rows of ``security`` (#346).

**The universe** (avo, 1 Nov 2026): Alpha Vantage's active ``assetType=ETF`` rows ∪ N-CEN's ``IS_ETF=Y`` series
(with a ticker) ∪ ``security``'s ``security_type='etp'`` rows. ``source`` says which: ``both`` (AV and N-CEN),
``av``, ``ncen``, or ``etp`` (the spine alone; mostly banks' notes). Every one is stored: there is **no threshold
and no ``active`` column** here; a board's thresholds (AUM, dollar volume) are its settings, applied when it reads.

**ETNs and notes** are flagged ``is_etn`` by a name rule (:data:`ETN_NAME`), kept, and not counted as ETFs.
**Closed-end funds** are flagged ``is_cef`` the same way (avo, 1 Nov 2026): Alpha Vantage lists some as ``ETF``
(DHY), and a row the spine types ``cef`` (``security.security_type``) stays, flagged, not counted as an ETF.

**What fills which column in this PR:** the ``is_*`` fund flags and ``aum`` (``DAILY_AVG_NET_ASSETS``, else
``MONTHLY_AVG_NET_ASSETS``, with the filing's report end as ``aum_as_of``) from the series' newest N-CEN, NULL for
a row N-CEN does not hold (unknown, not false); ``inception`` from AV's ``ipoDate``; ``is_option_income`` by a name
rule; ``asset_class`` ``commodity`` by the trust rule below, else (spine 11) TickerInside's category through
:data:`CATEGORY_ASSET_CLASS`, else the fund's newest N-PORT holdings mix (:func:`nport_class`); ``expense_ratio`` and the identity columns (``gvkey``, ``iid``, ``cusip``, ``figi``,
``composite_figi``, ``identity_source``) as :func:`rows` says. NULL until later PRs: ``focus`` and ``country``. ``adv_usd_20d`` is the
20-session average daily dollar volume, read from the **raw** Compustat ``comp.secd`` Parquet
(:func:`adv_usd_20d`); it is what decides a fund N-CEN gives no AUM for in ``my_universe`` (avo, 4 Nov 2026), and
it is measured from the raw file rather than the live ``prices.duckdb`` because that store keeps only today's
universe (#357, avo's decision B of 5 Nov 2026).

**The commodity rule.** An ``etp`` row of the spine that is no note, has no N-CEN series, and whose CIK filed no
N-CEN at all is not a registered investment company: a grantor trust or commodity pool registered under the 1933
Act only (GLD, SLV, USO, the bitcoin trusts), so ``asset_class='commodity'``, or ``crypto`` where its name says
so (:data:`CRYPTO_NAME`: IBIT, FBTC, GBTC, ETHA; avo, 23 Nov 2026). A unit investment trust does file
N-CEN (SPY and DIA as S-6 registrants, with no series row), so it is not caught. Until ``sec/ncen`` holds four
quarters (a fund files once a fiscal year) the rule says nothing: one quarter holds a fraction of the filers.
Such a row is a **trust** to ``my_universe`` (:data:`TRUST_SQL`), not an ETF.

**A label on a security that is no fund** (avo, 23 Nov 2026). Alpha Vantage labels some operating companies and
listed notes ``ETF`` (PAM, an ADR; PFX; SPAC units), and the spine's ``etp`` type reaches baby bonds through
Compustat's ``tpci`` ``R`` and the note name rule (OXLCG, ECCU). A ticker ``security`` types
:data:`NOT_A_FUND_TYPES`, or ``etp`` by :data:`NOTE_TYPE_SOURCES`, for which the SEC holds no fund record (no
``sec/company_tickers_mf`` row, no N-CEN series with the ticker, under the security's own CIK) gets no row here,
and one ``etf_label_not_a_fund`` issue. A CEF, an ETN by its issuer and a plain fund ``etp`` (SPY, GLD) are untouched.
"""
from __future__ import annotations

import re
from datetime import date
from pathlib import Path

import duckdb

from ....core.identity.types import EXCLUDED_TYPES, OPERATING_TYPES
from .. import base, secd
from .av_listing import STAGING as AV
from . import ncen, stage
from .ncen import FILERS, STAGING as NCEN
from .tier import NOTE_NAME

TABLE = "etf"
SCHEMA = [("ticker", "TEXT PRIMARY KEY"), ("name", "TEXT"), ("series_id", "TEXT"), ("cik", "TEXT"),
          ("source", "TEXT"), ("is_etn", "BOOLEAN"),
          # is_cef: the spine types the ticker a closed-end fund (AV calls some CEFs ETF); kept, not counted as ETFs.
          ("is_cef", "BOOLEAN"), ("asset_class", "TEXT"), ("focus", "TEXT"), ("country", "TEXT"),
          ("is_index", "BOOLEAN"), ("is_lev_inverse", "BOOLEAN"), ("is_money_market", "BOOLEAN"),
          ("is_option_income", "BOOLEAN"), ("is_fund_of_funds", "BOOLEAN"), ("inception", "DATE"),
          # aum (spine 9, #357): the fund's own shares times its close on aum_as_of (``shares_x_close``), else N-CEN's
          # average net assets over the filing's fiscal year, aum_as_of that year's end (``ncen_series``: the whole
          # series, mutual-fund classes included). aum_source says which.
          ("aum", "DOUBLE"), ("aum_as_of", "DATE"), ("aum_source", "TEXT"), ("adv_usd_20d", "DOUBLE"),
          ("expense_ratio", "DOUBLE"),
          # ETF identity (spine 11, #1334 K-A, SP1): the Compustat series the spine already resolves the fund's
          # ticker to (gvkey, iid, and the CUSIP of that series' newest priced day), and TickerInside's composite
          # FIGI; identity_source names the sources a row's identity came from.
          ("gvkey", "TEXT"), ("iid", "TEXT"), ("cusip", "TEXT"), ("figi", "TEXT"), ("composite_figi", "TEXT"),
          ("identity_source", "TEXT"),
          ("source_as_of", "DATE"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT")]

#: A note, by its name: ETN / ETRACS, a dated note, or a bank issuer's name (Alpha Vantage lists BMO's, UBS's,
#: Barclays' and Deutsche Bank's products under the bank's name, and the spine's etp rows carry the SEC's).
ETN_NAME = re.compile(
    r"\bETNs?\b|\bETRACS\b|" + NOTE_NAME +
    r"|\b(?:bank\s+of\s+montreal|ubs\s+ag|barclays\s+bank|deutsche\s+bank\s+ag|credit\s+suisse\s+ag"
    r"|jpmorgan\s+chase\s+(?:bank|financial|&\s+co)|citigroup\s+global\s+markets|morgan\s+stanley\s+finance"
    r"|goldman\s+sachs\s+international|royal\s+bank\s+of\s+canada|canadian\s+imperial\s+bank)\b", re.I)
#: Option income, by the fund's name: a **name rule** (the plan's words: option income, covered call, buffer,
#: autocallable, defined outcome, target outcome; avo's of 1 Nov 2026: premium income, buy-write, put-write, option
#: strategy, managed floor, defined or structured protection); nothing in N-CEN says it.
OPTION_INCOME_NAME = re.compile(
    r"\boptions?\s+income\b|\bcovered\s+call|\bbuffer|\bautocallable\b|\bdefined\s+outcome\b|\btarget\s+outcome\b"
    r"|\bpremium\s+income\b|\bbuy-?write\b|\bput-?write\b|\boptions?\s+strategy\b|\bmanaged\s+floor\b"
    r"|\b(?:defined|structured)\s+protection\b", re.I)
#: Leveraged or inverse, by the fund's name: a **name rule** beside N-CEN's ``IS_MULTI_INVERSE_INDEX``, which 185
#: leveraged ``IS_ETF=Y`` series leave blank (review S1 of PR 349: Tradr 2X Long IBM, Defiance 2X Long RIOT). A
#: multiple (2x-5x, 1.25x, -1x, 1x short), ProShares' Ultra / UltraPro / UltraShort / Short (only ProShares':
#: elsewhere "Ultra" is an ultra-short bond fund, a buffer or a dividend fund, measured over the N-CEN names of
#: 1 Nov 2026), inverse, leveraged (not a leveraged-loan fund), and a daily fund that is long, short, bull or bear.
#: A bare "short" is not enough: "iShares Short Treasury Bond" is no such fund.
LEV_INVERSE_NAME = re.compile(
    r"\b(?:[2-5]|1\.\d+)\s*x\b|-\s*1\s*x\b|\b1\s*x\s+short\b"
    r"|\bproshares\s+(?:ultra|short\b)|\binverse\b|\bleveraged\b(?!\s+loans?)"
    r"|\bdaily\b.*\b(?:long|short|bull|bear)\b|\b(?:long|short|bull|bear)\b.*\bdaily\b", re.I)

#: A crypto asset by the fund's or trust's name (avo's E, 17 Nov 2026; ``etf_class`` reads it from here).
CRYPTO_NAME = re.compile(r"\b(bitcoin|btc|ether|ethereum|crypto\w*|solana|sol|xrp|litecoin|dogecoin|doge|zcash|"
                         r"polkadot|avalanche|cardano|hedera|chainlink|hyperliquid|digital assets?|digital holdings)\b",
                         re.IGNORECASE)
#: A currency or a VIX trust by its name (avo, 23 Nov 2026, "Evet düzenle": FXE, FXY, UUP, UVXY, SVXY).
CURRENCY_NAME = re.compile(r"\b(currencyshares|currency|dollar index|euro|yen|swiss franc|british pound|yuan)\b", re.I)
VOLATILITY_NAME = re.compile(r"\b(vix|volatility)\b", re.I)
#: The classes the trust rule gives, first match wins; anything else is a commodity trust or pool.
TRUST_CLASSES = ("crypto", "volatility", "currency", "commodity")


def trust_class(names) -> str:
    """The ``asset_class`` of a 1933-Act trust or pool from its names: crypto, VIX, currency, else commodity."""
    names = [n for n in names if n]
    for cls, rx in (("crypto", CRYPTO_NAME), ("volatility", VOLATILITY_NAME), ("currency", CURRENCY_NAME)):
        if any(rx.search(n) for n in names):
            return cls
    return "commodity"


#: An ``etf`` row that is a **trust** (avo, 23 Nov 2026, "Bence trust lazım"): a 1933-Act grantor trust or commodity
#: pool, no 40-Act fund -- no N-CEN series, no note, no CEF, and a class of :data:`TRUST_CLASSES`. The one definition.
TRUST_SQL = ("series_id IS NULL AND NOT coalesce(is_etn, FALSE) AND NOT coalesce(is_cef, FALSE) "
             f"AND asset_class IN {TRUST_CLASSES}")


#: A carbon-allowance fund (KCCA, KRBN): a commodity whatever its collateral or category says (Grok xReview,
#: 23 Nov 2026; avo "Ok yap").
CARBON_NAME = re.compile(r"\bcarbon (?:allowance|credit)s?\b|\bcarbon strategy\b", re.I)


#: The ``security_type`` values of a security that is no fund: an operating company, a SPAC, a preferred, a unit or
#: a warrant. ``cef`` and ``etp`` are fund types; an ``etp`` is no fund only by :data:`NOTE_TYPE_SOURCES`.
NOT_A_FUND_TYPES = tuple(sorted(OPERATING_TYPES | (EXCLUDED_TYPES - {"cef", "etp"})))
#: The ``type_source`` of an ``etp`` that is a listed note or baby bond (``tier.TPCI_TYPES`` ``R``, the note rule).
NOTE_TYPE_SOURCES = ("compustat_tpci(R)", "name_rule(note)")


def is_etn(*names) -> bool:
    return any(ETN_NAME.search(n) for n in names if n)


def is_option_income(*names) -> bool:
    return any(OPTION_INCOME_NAME.search(n) for n in names if n)


def is_lev_inverse(*names) -> bool:
    return any(LEV_INVERSE_NAME.search(n) for n in names if n)


def _flag(nc: bool, value) -> bool | None:
    return bool(value) if nc else None


#: ``adv_usd_20d`` is the average of the fund's newest :data:`ADV_SESSIONS` **priced Compustat** sessions, and only
#: of a fund that has all of them: an average over three sessions is not the number avo's rule asks for ("son 20
#: gunun ortalama gunluk islem hacmi", 4 Nov 2026), so a fund with fewer stays unmeasured (NULL) and the universe
#: rule reports it undecided rather than judging it on a short window.
ADV_SESSIONS = 20
#: How recent (calendar days before Compustat's newest priced day) a series' own newest priced day must be for the
#: ticker it carries there to name this fund: two weeks covers a holiday week and a late Compustat row. The twin of
#: ``prices/universe.ETF_TIC_RECENT_DAYS`` (PR 382), which resolves a universe ETF's series the same way.
TIC_RECENT_DAYS = 14
#: How many of Compustat's newest year partitions the window is read from. Twenty sessions are a month, so two
#: years cover a build in early January and a year the fetch has not refreshed yet, without scanning 33 years.
ADV_YEARS = 2


#: ``asset_class`` (spine 11, SP7) from TickerInside's category id (``funds.json`` ``cat_id``, which "never changes
#: meaning"), filled only where the commodity rule left it NULL. The 103 ids of 20 Nov 2026 but ``unclassified``; an
#: id not here leaves the column NULL and is one ``etf_category_unmapped`` issue (plan v4 X9). Leveraged, inverse,
#: option-income and defined-outcome funds keep the class of what they track; their own flags say the rest.
ASSET_CLASSES = ("equity", "bond", "cash", "commodity", "crypto", "multi_asset", "alternative", "currency",
                 "volatility")
_CATEGORIES = {
    "equity": "asia-pacific asia-pacific-ex-japan canada china communication-services consumer-discretionary "
              "consumer-staples emerging-markets energy europe financials global-large-blend global-large-growth "
              "global-large-value global-small-mid gold-silver-miners health-care india industrials infrastructure "
              "international-large-blend international-large-growth international-large-value "
              "international-small-mid-blend international-small-mid-value japan latin-america materials "
              "middle-east-africa natural-resources real-estate technology thematic utilities us-large-blend "
              "us-large-growth us-large-value us-mid-blend us-mid-growth us-mid-value us-small-blend us-small-growth "
              "us-small-value single-stock inverse-equity leveraged-equity inverse-single-stock leveraged-single-stock "
              "option-income single-stock-option-income defined-outcome hedged-equity long-short-equity",
    "bond": "bank-loans clo convertible-bonds core-bond corporate-intermediate corporate-long corporate-short "
            "emerging-markets-bond high-yield inflation-protected international-bond inverse-bond leveraged-bond "
            "long-term-bond mortgage-backed multisector-bond municipal-intermediate municipal-long municipal-short "
            "preferred-securities securitized short-term-bond target-maturity treasury-bills treasury-intermediate "
            "treasury-long treasury-short ultrashort-bond",
    "cash": "money-market",
    "commodity": "broad-commodities energy-commodities inverse-commodity leveraged-commodity other-commodities "
                 "precious-metals",
    "crypto": "bitcoin ether crypto-other inverse-crypto leveraged-crypto",
    "multi_asset": "allocation-aggressive allocation-conservative allocation-moderate",
    "alternative": "alternative-other managed-futures volatility inverse-other leveraged-other",
    "currency": "currency",
}
CATEGORY_ASSET_CLASS = {cat: cls for cls, cats in _CATEGORIES.items() for cat in cats.split()}
COMPUSTAT_SECD, TICKERINSIDE = "compustat_secd", "tickerinside"

#: ``asset_class``'s third source, below the commodity rule and TickerInside's category and never over either: the
#: fund's newest N-PORT report (``sec/nport``, newest of the last :data:`NPORT_QUARTERS` quarters held, linked by
#: ``series_id``), read as ``etf_class`` buckets its lines (:data:`etf_class.BUCKET`; a held fund is ``fund``).
#: :data:`NPORT_SHARE` and :data:`NPORT_DERIVATIVE` are ``etf_class``'s own cuts (``Cuts.share``, ``Cuts.derivative``).
NPORT_SHARE, NPORT_DERIVATIVE, NPORT_QUARTERS = 60.0, 10.0, 4
#: The class of a synthetic or leveraged fund from the N-PORT ``asset_cat`` of the contracts it holds most (``d:<cat>``
#: keys of the mix; avo, 23 Nov 2026, "opsiyon 1"): buffer funds' SPY options, 2x single-stock swaps. ``DO`` is unread.
DERIVATIVE_CLASS = {"DE": "equity", "DIR": "bond", "DCR": "bond", "DCO": "commodity", "DFE": "currency"}


def nport_class(mix: dict[str, float], lev: bool = False, mm: bool = False, opt: bool = False,
                crypto: bool = False) -> str | None:
    """The asset class of one N-PORT mix (``etf_class`` bucket to percent of net assets), or None where the report
    does not say it. Leveraged, inverse or 10 % in derivatives: the exposure is in the contracts, not the lines. One
    of equity, bond (``debt``), commodity at 60 % is the class; cash at 60 % only for an N-CEN money market fund
    (elsewhere it is the collateral of futures or swaps); else equity, bond and commodity together at 60 % are
    ``multi_asset``, and a mix mostly of held funds or unbucketed lines stays None. An option-income fund
    (:data:`OPTION_INCOME_NAME`) is read only as ``equity``, where it holds the shares it writes on: a buffer or
    put-write fund's Treasuries are collateral (Innovator's Premium Income funds, 100 % bills, 23 Nov 2026).
    Leveraged, inverse or synthetic, it is the class of its largest contract type (:data:`DERIVATIVE_CLASS`); FX
    contracts of a fund whose name says crypto (``crypto``) are its crypto futures."""
    if lev or mix.get("derivative", 0.0) >= NPORT_DERIVATIVE:
        held = sorted((v, k[2:]) for k, v in mix.items() if k.startswith("d:"))
        cls = DERIVATIVE_CLASS.get(held[-1][1]) if held else None
        return "crypto" if crypto and cls == "currency" else cls
    held = {"equity": mix.get("equity", 0.0), "bond": mix.get("debt", 0.0), "commodity": mix.get("commodity", 0.0)}
    k, v = max(sorted({**held, "cash": mix.get("cash", 0.0)}.items()), key=lambda kv: kv[1])
    cls = (None if k == "cash" and not mm else k) if v >= NPORT_SHARE else (
        "multi_asset" if sum(held.values()) >= NPORT_SHARE else None)
    return None if opt and cls != "equity" else cls


def nport_mix(series_ids: list[str]) -> dict[str, dict[str, float]]:
    """``{series_id: {bucket: percent of net assets}}`` of each series' newest N-PORT report among the newest
    :data:`NPORT_QUARTERS` quarters of ``sec/nport`` Parquet (derivatives as absolute values); empty without it."""
    from .etf_class import _FUND_NAME, BUCKET, NPORT          # ``etf_class`` imports this module
    wanted = sorted({s for s in series_ids if s})
    root = base.parquet_root().joinpath(*NPORT.split("/"))
    held = [f.parent for _, f in stage.partitions(root, "quarter", "fund.parquet")
            if (f.parent / "holdings.parquet").is_file()][-NPORT_QUARTERS:]
    if not wanted or not held:
        return {}

    def src(name: str) -> str:
        return f"read_parquet([{', '.join(base.sql_path(d / name) for d in held)}], union_by_name = true)"
    con = base.scratch_con()
    try:
        found = con.execute(f"""
            WITH r AS (SELECT series_id, accession FROM {src('fund.parquet')}
                       WHERE series_id IN ({', '.join('?' * len(wanted))})
                       QUALIFY row_number() OVER (PARTITION BY series_id ORDER BY report_date DESC NULLS LAST,
                                                  filed DESC NULLS LAST, accession DESC) = 1),
                 l AS (SELECT r.series_id, h.pct_of_net_assets AS pct, {BUCKET} AS bucket, h.asset_cat,
                              coalesce(h.issuer_type = 'RF', false) AS is_rf,
                              regexp_matches(upper(coalesce(h.issuer_name, '')), '{_FUND_NAME}') AS fund_name
                       FROM r JOIN {src('holdings.parquet')} h ON h.accession = r.accession)
            -- a held fund is ``fund`` as ``etf_class`` says it: a registered fund always, a fund's name on equity
            SELECT series_id, CASE WHEN is_rf OR (bucket = 'equity' AND fund_name) THEN 'fund' ELSE bucket END AS b,
                   sum(CASE WHEN bucket = 'derivative' THEN abs(pct) ELSE pct END)
            FROM l GROUP BY 1, 2
            UNION ALL   -- each contract type on its own, for :data:`DERIVATIVE_CLASS`
            SELECT series_id, 'd:' || asset_cat, sum(abs(pct)) FROM l WHERE bucket = 'derivative' GROUP BY 1, 2""",
            wanted).fetchall()
    finally:
        con.close()
    out: dict[str, dict[str, float]] = {}
    for s, b, v in found:
        out.setdefault(str(s), {})[str(b)] = float(v or 0.0)
    return out


def _cik(value) -> str | None:
    text = str(value or "").strip()
    return str(int(text)) if text.isdigit() else None


def secd_files(as_of: date | None = None) -> list[Path]:
    """The newest :data:`ADV_YEARS` Compustat ``secd`` year partitions that exist, oldest first; a year after
    ``as_of`` is not read at all, so a build of an earlier day reads that day's Compustat (``build/secd.py``)."""
    return secd.files(ADV_YEARS, as_of)


def adv_usd_20d(tickers: list[str], as_of: date | None = None) -> dict[str, float]:
    """``{ticker: average daily dollar volume}`` over the newest :data:`ADV_SESSIONS` priced sessions of the
    Compustat series the ticker names, read from the **raw** ``comp.secd`` Parquet (#357, avo's decision B of
    5 Nov 2026).

    **Not from the live ``prices.duckdb``.** That store keeps only today's universe (PR 382), and a fund enters the
    universe *on this number*: reading it there would mean a fund that is not in the store yet could never get a
    volume, and so never enter. The raw Compustat partitions hold every fund Compustat prices, whatever our
    universe says.

    A session's dollar volume is its close (``prccd``) times its volume (``cshtrd``), the same two columns the
    served Compustat bar carries, in US dollars only (``curcdd``); a day with no price, no volume or another
    currency is no session. The fund's **series** is the one whose own newest priced day carries the ticker
    (Compustat's ``tic``, its dots read as the spine's dashes) within :data:`TIC_RECENT_DAYS` of Compustat's newest
    priced day: a series that carried the ticker long ago is a reused ticker's, not this fund's. Where two live
    series still claim one ticker the larger average is the answer; the spine's own routing is not consulted,
    because one live ticker is one security's and a dead series is already out by the recency rule. A fund with
    fewer than :data:`ADV_SESSIONS` priced sessions, or no Compustat partition at all, is absent from the answer
    and its ``adv_usd_20d`` stays NULL (unknown, not zero).
    """
    wanted = sorted({str(t).strip().upper() for t in tickers if str(t or "").strip()})
    files = secd_files(as_of)
    if not wanted or not files:
        return {}
    src = f"read_parquet([{', '.join(base.sql_path(f) for f in files)}], union_by_name = true)"
    cutoff = "" if as_of is None else f" AND datadate <= DATE '{as_of.isoformat()}'"
    con = base.scratch_con()
    try:
        rows = con.execute(f"""{_claimed(src, cutoff, len(wanted))}
            SELECT ticker, adv FROM (SELECT ticker, gid, avg(dollars) AS adv FROM recent GROUP BY 1, 2
                                     HAVING count(*) = {ADV_SESSIONS})
            QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY adv DESC, gid) = 1""", wanted).fetchall()
    finally:
        con.close()
    return {str(t): float(v) for t, v in rows if v is not None}


def _claimed(src: str, cutoff: str, n: int) -> str:
    """The series rule of :func:`adv_usd_20d`, as SQL CTEs: ``recent`` holds the newest :data:`ADV_SESSIONS` priced
    sessions of each series whose own newest priced day carries one of the ``n`` asked tickers, within
    :data:`TIC_RECENT_DAYS` of Compustat's newest priced day."""
    return f"""
            WITH priced AS (
                SELECT gvkey, iid, gvkey || ':' || iid AS gid, replace(upper(tic), '.', '-') AS ticker, datadate,
                       prccd * cshtrd AS dollars, cusip
                FROM {src}
                WHERE {secd.PRICED_USD} AND cshtrd IS NOT NULL AND tic IS NOT NULL{cutoff}),
            last_day AS (SELECT gid, ticker, datadate FROM priced
                         QUALIFY row_number() OVER (PARTITION BY gid ORDER BY datadate DESC) = 1),
            claim AS (SELECT gid, ticker FROM last_day
                      WHERE ticker IN ({', '.join('?' * n)})
                        AND datadate > (SELECT max(datadate) FROM priced)
                                       - INTERVAL {TIC_RECENT_DAYS} DAY),
            recent AS (SELECT c.ticker, p.gid, p.gvkey, p.iid, p.cusip, p.datadate, p.dollars
                       FROM priced p JOIN claim c USING (gid)
                       QUALIFY row_number() OVER (PARTITION BY p.gid ORDER BY p.datadate DESC) <= {ADV_SESSIONS})"""


def etf_series(tickers: list[str], as_of: date | None = None) -> dict[str, tuple[str, str, str | None]]:
    """``{ticker: (gvkey, iid, cusip)}``: the Compustat series :func:`adv_usd_20d` resolves each fund's ticker to
    (the same rule, and where two live series claim one ticker the larger average dollar volume), with the CUSIP of
    that series' newest priced day. Unlike the volume it needs no full window: a series with three sessions is
    still the fund's series (spine 11, #1334 K-A: the spine is the one owner of ETF identity)."""
    wanted = sorted({str(t).strip().upper() for t in tickers if str(t or "").strip()})
    files = secd_files(as_of)
    if not wanted or not files:
        return {}
    src = f"read_parquet([{', '.join(base.sql_path(f) for f in files)}], union_by_name = true)"
    cutoff = "" if as_of is None else f" AND datadate <= DATE '{as_of.isoformat()}'"
    con = base.scratch_con()
    try:
        rows = con.execute(f"""{_claimed(src, cutoff, len(wanted))}
            SELECT ticker, gvkey, iid, cusip FROM (
                SELECT ticker, gid, any_value(gvkey) AS gvkey, any_value(iid) AS iid, avg(dollars) AS adv,
                       arg_max(cusip, datadate) AS cusip
                FROM recent GROUP BY ticker, gid)
            QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY adv DESC, gid) = 1""", wanted).fetchall()
    finally:
        con.close()
    return {str(t): (str(g), str(i), (str(c).strip().upper() or None) if c else None) for t, g, i, c in rows}


SHARES_X_CLOSE, NCEN_SERIES = "shares_x_close", "ncen_series"


def shares_x_close(tickers: list[str], as_of: date | None = None) -> dict[str, tuple[float, date]]:
    """``{ticker: (shares outstanding x close, its day)}`` from the same raw ``comp.secd`` Parquet and the same
    series rule as :func:`adv_usd_20d` (#357): N-CEN's figure is a fiscal-year average of the whole series (VTI
    1.90 T$ with Vanguard's mutual-fund classes, against 679 B$ here) and is silent on a unit trust (SPY, QQQ).

    The day is the series' newest priced US-dollar day with a share count (``cshoc`` > 0) within
    :data:`TIC_RECENT_DAYS` of Compustat's newest priced day; where two live series claim the ticker the larger
    figure is the answer. A fund Compustat has no such day for is absent (unknown, not zero).
    """
    wanted = sorted({str(t).strip().upper() for t in tickers if str(t or "").strip()})
    files = secd_files(as_of)
    if not wanted or not files:
        return {}
    src = f"read_parquet([{', '.join(base.sql_path(f) for f in files)}], union_by_name = true)"
    cutoff = "" if as_of is None else f" AND datadate <= DATE '{as_of.isoformat()}'"
    con = base.scratch_con()
    try:
        found = con.execute(f"""
            WITH priced AS (
                SELECT gvkey || ':' || iid AS gid, replace(upper(tic), '.', '-') AS ticker, datadate, prccd, cshoc
                FROM {src}
                WHERE {secd.PRICED_USD} AND tic IS NOT NULL{cutoff}),
            recent AS (SELECT * FROM priced WHERE datadate > (SELECT max(datadate) FROM priced)
                                                             - INTERVAL {TIC_RECENT_DAYS} DAY),
            claim AS (SELECT gid, ticker FROM recent
                      QUALIFY row_number() OVER (PARTITION BY gid ORDER BY datadate DESC) = 1),
            counted AS (SELECT c.ticker, r.gid, r.prccd * r.cshoc AS aum, r.datadate FROM recent r
                        JOIN claim c USING (gid) WHERE r.cshoc > 0 AND c.ticker IN ({', '.join('?' * len(wanted))})
                        QUALIFY row_number() OVER (PARTITION BY r.gid ORDER BY r.datadate DESC) = 1)
            SELECT ticker, aum, datadate FROM counted
            QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY aum DESC, gid) = 1""", wanted).fetchall()
    finally:
        con.close()
    return {str(t): (float(v), d) for t, v, d in found}


def rows(ctx: base.RunContext, con: duckdb.DuckDBPyConnection, issues: list | None = None) -> list[dict]:
    """Every ETF ticker's row, from the staging tables and the ``security`` table this build just created.

    **Identity (spine 11, #1334 K-A, SP1, SP7, plan v4 X9).** ``gvkey``, ``iid`` and ``cusip`` from Compustat's
    series of the ticker (:func:`etf_series`). TickerInside's ``identifiers.json`` and ``funds.json`` (the newest
    ``funds/etf_holdings`` keeps on or before the build day) are taken for a ticker only where its CIK agrees: a
    row whose ``cik`` is filled takes nothing from a TickerInside row under another CIK, or under none (a ticker
    can pass to another security), and the conflict is one ``etf_cik_conflict`` issue in ``issues``. Where the CIK
    agrees, or ``cik`` is empty: the composite FIGI (``figi`` and ``composite_figi``), ``cik`` and ``series_id``
    only where empty (never overwritten), ``expense_ratio`` (percent, as TickerInside gives it), and
    ``asset_class`` through :data:`CATEGORY_ASSET_CLASS` only where the commodity rule left it NULL; an unmapped
    category is one ``etf_category_unmapped`` issue per category."""
    from .etf_holdings import tickerinside_meta
    cur = con.execute(f"""
        WITH av AS (SELECT ticker, name, ipo_date, source_as_of, fetched_at FROM {AV}
                    WHERE asset_type = 'ETF' AND status = 'Active'
                    QUALIFY row_number() OVER (PARTITION BY ticker ORDER BY ipo_date DESC NULLS LAST, symbol) = 1),
             -- N-CEN is annual and writes the ticker of its filing day; SEC's fund file is current. A series the
             -- fund file lists under one ETF ticker, none of them N-CEN's, was renamed: it takes that ticker
             -- (SPLG -> SPYM, PHB -> IFLN: 15 of 16 such funds on 24 Nov 2026, each with bars under the new one).
             mf AS (SELECT series_id, min(ticker) AS ticker FROM stg_sec_mf WHERE is_etf AND series_id IS NOT NULL
                    GROUP BY series_id HAVING count(DISTINCT ticker) = 1),
             nc AS (SELECT n.* REPLACE (CASE WHEN EXISTS (SELECT 1 FROM stg_sec_mf s WHERE s.series_id = n.series_id
                                                          AND s.ticker = n.ticker) THEN n.ticker
                                             ELSE coalesce(mf.ticker, n.ticker) END AS ticker)
                    FROM {NCEN} n LEFT JOIN mf ON mf.series_id = n.series_id
                    WHERE n.is_etf AND n.ticker IS NOT NULL
                    QUALIFY row_number() OVER (PARTITION BY coalesce(mf.ticker, n.ticker)
                                               ORDER BY n.filing_date DESC NULLS LAST, n.accession DESC,
                                                        n.series_id) = 1),
             etp AS (SELECT ticker, cik, name, source_as_of, fetched_at FROM security WHERE security_type = 'etp'),
             cef AS (SELECT ticker FROM security WHERE security_type = 'cef'),
             -- a fund record counts only under the security's own CIK (CORZ: N-CEN files Tradr's 2x ETF under it)
             not_fund AS (SELECT ticker, security_type, type_source FROM security s
                          WHERE (security_type IN ({", ".join(f"'{t}'" for t in NOT_A_FUND_TYPES)})
                                 OR (security_type = 'etp'
                                     AND type_source IN ({", ".join(f"'{t}'" for t in NOTE_TYPE_SOURCES)})))
                            AND NOT EXISTS (SELECT 1 FROM (SELECT ticker, cik FROM stg_sec_mf
                                                          UNION ALL SELECT ticker, cik FROM {NCEN}) f
                                            WHERE f.ticker = s.ticker AND (s.cik IS NULL
                                                  OR try_cast(f.cik AS BIGINT) = try_cast(s.cik AS BIGINT))))
        SELECT t.ticker, nf.security_type AS nf_type, nf.type_source AS nf_source,
               av.ticker IS NOT NULL AS in_av, nc.ticker IS NOT NULL AS in_nc,
               etp.ticker IS NOT NULL AS in_etp, cef.ticker IS NOT NULL AS is_cef,
               av.name AS av_name, av.ipo_date, nc.fund_name, nc.series_id, nc.cik AS nc_cik, nc.is_index,
               nc.is_multi_inverse_index, nc.is_money_market, nc.is_fund_of_fund, nc.daily_avg_net_assets,
               nc.monthly_avg_net_assets, nc.report_end, etp.cik AS etp_cik, etp.name AS etp_name,
               greatest(av.source_as_of, nc.source_as_of, etp.source_as_of) AS source_as_of,
               greatest(av.fetched_at, nc.fetched_at, etp.fetched_at) AS fetched_at
        FROM (SELECT ticker FROM av UNION SELECT ticker FROM nc UNION SELECT ticker FROM etp) t
        LEFT JOIN av ON av.ticker = t.ticker LEFT JOIN nc ON nc.ticker = t.ticker
        LEFT JOIN etp ON etp.ticker = t.ticker LEFT JOIN cef ON cef.ticker = t.ticker
        LEFT JOIN not_fund nf ON nf.ticker = t.ticker
        ORDER BY t.ticker""")
    cols = [d[0] for d in cur.description]
    found = [dict(zip(cols, x)) for x in cur.fetchall()]      # before the next execute replaces the result
    issues = [] if issues is None else issues
    issues += [("etf_label_not_a_fund", r["ticker"],
                f"{'Alpha Vantage lists' if r['in_av'] else 'the spine types'} {r['ticker']} "
                f"({r['av_name'] or r['etp_name']}) as an ETF, but security types it {r['nf_type']} by "
                f"{r['nf_source']} and the SEC holds no fund record for it under its CIK: no etf row")
               for r in found if r["nf_type"]]
    found = [r for r in found if not r["nf_type"]]
    filers = {r[0] for r in con.execute(f"SELECT DISTINCT cik FROM {FILERS}").fetchall()}
    # Fewer quarters hold a fraction of the filers: "files no N-CEN" is only known over a full year (review M1).
    year_held = ncen.quarters_held() >= ncen.BACKFILL_QUARTERS
    adv = adv_usd_20d([r["ticker"] for r in found], ctx.as_of)
    own = shares_x_close([r["ticker"] for r in found], ctx.as_of)
    ids_of = etf_series([r["ticker"] for r in found], ctx.as_of)
    ti_ids, ti_funds = tickerinside_meta(ctx.as_of)
    unmapped: dict[str, list[str]] = {}
    out = []
    for r in found:
        names = (r["fund_name"], r["av_name"], r["etp_name"])
        nc = r["in_nc"]
        etn = not nc and is_etn(*names)          # N-CEN's IS_ETF=Y is a registered fund's word: no note (N3)
        aum = r["daily_avg_net_assets"] if r["daily_avg_net_assets"] is not None else r["monthly_avg_net_assets"]
        aum, aum_day, aum_src = ((*own[r["ticker"]], SHARES_X_CLOSE) if r["ticker"] in own else
                                 (aum, r["report_end"], NCEN_SERIES) if aum is not None else (None, None, None))
        commodity = r["in_etp"] and not nc and not etn and year_held and r["etp_cik"] not in filers
        t, raw_cik, series_id = r["ticker"], r["nc_cik"] or r["etp_cik"], r["series_id"]
        cik = _cik(raw_cik)                       # compared as the SEC file writes it; served as the source gave it
        ti = ti_ids.get(t)
        if ti is not None and raw_cik and ti["cik"] and ti["cik"] != cik:
            issues.append(("etf_cik_conflict", t, f"TickerInside lists {t} under CIK {ti['cik']}, the etf row's is "
                                                  f"{cik}: nothing taken from TickerInside"))
        ti = ti if ti is not None and (not raw_cik or ti["cik"] == cik) else None
        fund = ti_funds.get(t) if ti is not None else None
        asset_class = (trust_class(names) if commodity else
                       "commodity" if any(CARBON_NAME.search(n) for n in names if n) else None)
        if asset_class is None and fund and fund["category"]:
            asset_class = CATEGORY_ASSET_CLASS.get(fund["category"])
            if asset_class is None:
                unmapped.setdefault(fund["category"], []).append(t)
        gvkey, iid, cusip = ids_of.get(t, (None, None, None))
        figi = (ti or {}).get("composite_figi")
        out.append({
            "ticker": t, "name": next((n for n in names if n), None),
            "series_id": series_id or (ti or {}).get("series_id"), "cik": raw_cik or (ti or {}).get("cik"),
            "source": "both" if r["in_av"] and nc else "av" if r["in_av"] else "ncen" if nc else "etp",
            "is_etn": etn, "is_cef": r["is_cef"], "asset_class": asset_class, "focus": None,
            "country": None,
            "is_index": _flag(nc, r["is_index"]),
            "is_lev_inverse": True if is_lev_inverse(*names) else _flag(nc, r["is_multi_inverse_index"]),
            "is_money_market": _flag(nc, r["is_money_market"]), "is_option_income": is_option_income(*names),
            "is_fund_of_funds": _flag(nc, r["is_fund_of_fund"]), "inception": r["ipo_date"], "aum": aum,
            "aum_as_of": aum_day, "aum_source": aum_src,
            "adv_usd_20d": adv.get(r["ticker"]), "expense_ratio": (fund or {}).get("expense_ratio"),
            "gvkey": gvkey, "iid": iid, "cusip": cusip, "figi": figi, "composite_figi": figi,
            "identity_source": "+".join(s for s, v in ((COMPUSTAT_SECD, gvkey), (TICKERINSIDE, figi)) if v) or None,
            "source_as_of": r["source_as_of"],
            # The newest of its sources' fetch times; run_id is the build that wrote the row (it is derived).
            "fetched_at": r["fetched_at"], "run_id": ctx.run_id})
    # The third source of asset_class: what the earlier two left NULL, from the newest N-PORT mix (never over them).
    mixes = nport_mix([r["series_id"] for r in out if r["asset_class"] is None])
    from_nport = 0
    for r in out:
        if r["asset_class"] is None and r["series_id"] in mixes:
            r["asset_class"] = nport_class(mixes[r["series_id"]], lev=bool(r["is_lev_inverse"]),
                                           mm=bool(r["is_money_market"]), opt=r["is_option_income"],
                                           crypto=bool(CRYPTO_NAME.search(r["name"] or "")))
            from_nport += r["asset_class"] is not None
    ctx.notes.append(f"etf asset_class: {from_nport} from N-PORT ({len(mixes)} reports read), "
                     f"{sum(1 for r in out if r['asset_class'] is None)} still NULL")
    issues += [("etf_category_unmapped", cat, f"TickerInside category {cat} has no asset class here: "
                + ", ".join(sorted(ts))[:300]) for cat, ts in sorted(unmapped.items())]
    ctx.notes.append(f"etf identity: {sum(1 for r in out if r['gvkey'])} with a Compustat series, "
                     f"{sum(1 for r in out if r['figi'])} with a TickerInside FIGI, "
                     f"{sum(1 for r in out if r['expense_ratio'] is not None)} with an expense ratio")
    etns = sum(1 for r in out if r["is_etn"])
    cefs = sum(1 for r in out if r["is_cef"] and not r["is_etn"])
    ctx.notes.append(f"{len(out)} in etf: {len(out) - etns - cefs} ETFs, {etns} ETNs flagged, {cefs} CEFs flagged; "
                     f"{len(adv)} with a {ADV_SESSIONS}-session dollar volume")
    return out
