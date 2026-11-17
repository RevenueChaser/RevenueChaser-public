"""``etf_class``: what each ETF of ``my_universe`` is, read from its holdings, and ``etf_class_changes`` (#1031).

avo's rule (17 Nov 2026): a label comes from data with a named source, never typed by hand ("Elle doldurma yok.
Kesinlikle kaynağımız olması lazım"). The source is the fund's newest Form N-PORT report, read from the **Parquet**
of ``sec/nport`` (``parquet/sec/nport/quarter=<q>/{fund,holdings}.parquet``): the served ``etf_holdings_nport``
keeps only the lines whose CUSIP the spine holds, so a bond, a swap and a foreign share are not in it, and asset
class and country cannot be read from it.

**The rule** (v3; measured on the 2,228 universe ETFs of 17 Nov 2026, N-PORT 2026q3, reviewed twice and agreed
with the second reviewer):

- every holding line goes into one bucket by its N-PORT asset category: equity, debt, cash, derivative, commodity,
  real estate, other. A line whose issuer is a registered fund (issuer type ``RF``), whose ticker is an ``etf``
  row, or whose name says so, is bucket ``fund`` and never equity: TMF and BNDW hold funds, not stocks;
- an equity line gets its GICS from ``security`` by CUSIP, then ISIN, then ticker (Exxon Mobil's CUSIP found no
  spine row in 55 funds; the ISIN and the ticker did);
- **structure**: derivative lines of 10 % of net assets or more make a fund ``synthetic``; the ``etf`` flags say
  leveraged and option income. Such a fund is ``hidden_by_default`` (avo's B: labelled, hidden on boards unless
  the filter is switched on);
- under 50 % equity the largest bucket is the label at 60 % or more (``bond``, ``cash``, ``commodity``,
  ``fund_of_funds``, ``real_estate``), else ``multi_asset``; a leveraged or synthetic fund is ``synthetic``;
- **crypto** is its own class (avo's E), by a name rule on the fund's registered name, for a fund that holds no
  equity majority (a bitcoin trust files no N-PORT at all; a miners fund holds shares and is not one);
- an equity fund is tested from the sector down: the largest sector at 60 % of the **coded** equity, resting on
  at least 50 % of **all** equity. A finer level (industry group, industry, sub-industry) wins only when its share
  is also 25 points over that code's share inside its parent in the benchmark (IVV): a cap-weighted sector fund is
  concentrated because its sector is (Media is 92 % of Communication Services), so a bare threshold relabelled the
  sector SPDRs themselves;
- no such level: ``country`` at 60 % in one foreign country (China and Hong Kong together; Cayman, the BVI and
  Bermuda are places of incorporation and are left out), ``international`` under 50 % US, ``low_coverage`` when
  under 60 % of the equity is coded, ``broad`` when the sector mix is within 0.15 of the benchmark's (half the
  absolute differences; ``broad_global`` when not a US fund), else ``diversified`` (avo's A: two classes);
- **hysteresis**: a fund keeps its live label while that label, at its own level, still holds with every cut 10
  points lower (the distance 0.05 wider), so a fund sitting on a cut does not flip every quarter; a finer level that
  passes the full cuts is a new label and wins. The 10 % derivative cut and the fixed equity and US cuts have none;
  a fund that starts or stops being hidden writes a change row all the same;
- a fund with no report is ``unclassified`` and says why. It is never guessed.

:data:`MANUAL_FILE` corrects a wrong call; it does not fill a missing one. A line names a ticker, a ``primary_class``
and a reason, is changed only by a pull request, and a ticker that is no universe ETF is an
``etf_class_manual_unknown`` issue.

**An input outage is not a rule change.** With no N-PORT Parquet in a build, the live rows are carried forward as
they are: a build on a machine without the folder must not rewrite 2,000 labels to ``unclassified``.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, replace
from datetime import date
from pathlib import Path

import duckdb

from .. import base
from . import etf as etf_mod, my_universe, stage

TABLE = "etf_class"
CHANGES = "etf_class_changes"
#: The dataset whose Parquet this reads (``dirty.read_dirs`` through ``SpineSecurity.parquet_reads``).
NPORT = "sec/nport"
#: Corrections by hand. Owned by avo; changed only by a pull request.
MANUAL_FILE = Path(__file__).with_name("etf_class_manual.json")
ISSUES = ("etf_class_manual_unknown",)

#: The share columns are percent of the **coded** equity; ``equity_pct`` is percent of net assets and
#: ``coded_pct`` percent of the equity that has a GICS code. ``source`` is the dataset and its quarter, ``as_of``
#: the report's own day, ``since`` the build day the current ``primary_class`` and ``code`` first held.
#: ``primary_class`` and not ``primary``: that is a reserved word in SQL, and a reader would have to quote it.
SCHEMA = [("ticker", "TEXT PRIMARY KEY"), ("primary_class", "TEXT"), ("code", "TEXT"), ("label", "TEXT"),
          ("reason", "TEXT"), ("structure", "TEXT"), ("is_synthetic", "BOOLEAN"),
          ("hidden_by_default", "BOOLEAN"), ("asset_class", "TEXT"), ("geo", "TEXT"), ("country", "TEXT"),
          ("equity_pct", "DOUBLE"), ("coded_pct", "DOUBLE"),
          ("gsector", "TEXT"), ("gsector_share", "DOUBLE"), ("ggroup", "TEXT"), ("ggroup_share", "DOUBLE"),
          ("gind", "TEXT"), ("gind_share", "DOUBLE"), ("gsubind", "TEXT"), ("gsubind_share", "DOUBLE"),
          ("benchmark_distance", "DOUBLE"), ("manual", "BOOLEAN"), ("source", "TEXT"), ("as_of", "DATE"),
          ("since", "DATE"), ("run_id", "TEXT")]
CHANGES_SCHEMA = [("ticker", "TEXT"), ("change", "TEXT"), ("was", "TEXT"), ("now", "TEXT"), ("reason", "TEXT"),
                  ("as_of", "DATE"), ("run_id", "TEXT")]
ENTERED, CHANGED, LEFT = "entered", "changed", "left"

#: The GICS levels, coarse to fine: the primary's name, the ``security`` column, the code's length.
LEVELS = (("sector", "gsector", 2), ("industry_group", "ggroup", 4), ("industry", "gind", 6),
          ("sub_industry", "gsubind", 8))
#: Tried in this order; the first that has a coded report in the build is the benchmark.
BENCHMARKS = ("IVV", "VOO", "SPLG")
#: Places of incorporation, not of business (CQQQ read "KY 61 %"): left out of the geography test.
OFFSHORE = frozenset({"KY", "VG", "BM"})
UNCLASSIFIED = "unclassified"
#: The fund's registered name says it holds a crypto asset (avo's E, 17 Nov 2026).
CRYPTO_NAME = re.compile(r"\b(bitcoin|btc|ether|ethereum|crypto\w*|solana|sol|xrp|litecoin|dogecoin|doge|"
                         r"digital assets?)\b", re.IGNORECASE)
_FUND_NAME = r"\bETF\b|ISHARES TRUST|SELECT SECTOR SPDR"


@dataclass(frozen=True)
class Cuts:
    """The numbers of the rule, in percent (``broad`` is a distance). Read off one quarter (17 Nov 2026)."""
    share: float = 60.0          # a level's share of the coded equity, a country's share, a non-equity bucket's
    excess: float = 25.0         # points over the code's share inside its parent in the benchmark
    floor: float = 50.0          # the label must rest on this much of ALL equity
    cover: float = 60.0          # coded equity under this is ``low_coverage``
    broad: float = 0.15          # sector-mix distance to the benchmark at or under this is ``broad``
    derivative: float = 10.0     # derivative lines at or over this make a fund synthetic
    leave: float = 10.0          # hysteresis: a held label is left this many points under its cut

    def relaxed(self) -> "Cuts":
        return replace(self, share=self.share - self.leave, excess=self.excess - self.leave,
                       floor=self.floor - self.leave, broad=self.broad + self.leave / 200.0)


def _top(d: dict) -> tuple[str | None, float]:
    return max(sorted(d.items()), key=lambda kv: kv[1]) if d else (None, 0.0)


def _roll(g: dict[str, float], n: int) -> Counter:
    out: Counter = Counter()
    for code, w in g.items():
        out[code[:n]] += w
    return out


def benchmark_of(g: dict[str, float]) -> dict:
    """The benchmark's sector mix (``sector``) and, per finer level, each code's share inside its parent."""
    total = sum(g.values())
    out = {"sector": {k: v / total for k, v in _roll(g, 2).items()} if total else {}}
    for name, _, n in LEVELS[1:]:
        child, parent = _roll(g, n), _roll(g, n - 2)
        out[name] = {k: v / parent[k[:n - 2]] for k, v in child.items() if parent[k[:n - 2]]}
    return out


def classify(p: dict, bench: dict | None, cuts: Cuts = Cuts(), upto: int | None = None) -> dict:
    """One fund's axes, ``primary_class``, ``code`` and ``reason`` from its profile ``p``.

    ``p``: ``name``, the ``etf`` flags (``lev``, ``opt``, ``fof``, ``mm``), ``asset_class`` (the ``etf`` row's), and
    either ``no_report`` (with ``why``) or the buckets in percent of net assets (``equity``, ``preferred``, ``debt``,
    ``cash``, ``derivative``, ``commodity``, ``fund``, ``real_estate``, ``coded``), ``g`` (gsubind to percent) and
    ``country`` (code to percent of equity lines). ``bench`` is :func:`benchmark_of` the benchmark fund, or None
    when the build has none: then no finer level and no ``broad`` is decided, because both are relative to it.
    ``upto`` stops the search at that index of :data:`LEVELS` (the hysteresis asks about the live level only).
    """
    crypto = bool(CRYPTO_NAME.search(p.get("name") or ""))
    out = {"code": None, "is_synthetic": False, "asset_class": None, "geo": None, "country": None,
           "equity_pct": None, "coded_pct": None, "benchmark_distance": None,
           **{f"{col}{s}": None for _, col, _ in LEVELS for s in ("", "_share")}}

    def done(primary: str, reason: str, **more) -> dict:
        out.update(more)
        synthetic = out["is_synthetic"]
        out["structure"] = ("leveraged" if p.get("lev") else "option_income" if p.get("opt")
                            else "synthetic" if synthetic else "plain")
        out["hidden_by_default"] = out["structure"] != "plain"
        out["primary_class"], out["reason"] = primary, reason
        return out

    if p.get("no_report"):
        why = p.get("why") or "no N-PORT report"
        # A registered fund (it has a series) files N-PORT: its name alone decides nothing until the report is in
        # ("Crypto Industry Innovators" holds shares). A trust files none, so its name is all there is.
        if crypto and not p.get("series_id"):
            return done("crypto", f"registered name; {why}", asset_class="crypto")
        if p.get("asset_class"):
            return done(p["asset_class"], f"the etf row's asset class; {why}", asset_class=p["asset_class"])
        if p.get("mm"):
            return done("cash", f"money market fund (N-CEN); {why}", asset_class="cash")
        return done(UNCLASSIFIED, why)

    eq = p["equity"]
    out["equity_pct"] = round(eq, 2)
    out["is_synthetic"] = p["derivative"] >= cuts.derivative
    if eq < 50.0:
        parts = {"bond": p["debt"], "cash": p["cash"], "derivative": p["derivative"], "commodity": p["commodity"],
                 "fund_of_funds": p["fund"], "real_estate": p["real_estate"], "equity": eq}
        k, v = _top(parts)
        mix = f"{k} {v:.0f}%, equity {eq:.0f}%"
        if crypto:
            return done("crypto", f"registered name; {mix}", asset_class="crypto")
        if out["is_synthetic"] or p.get("lev"):
            return done("synthetic", mix, asset_class="derivative")
        if p.get("mm"):
            return done("cash", f"money market fund (N-CEN); {mix}", asset_class="cash")
        if v >= cuts.share and k not in ("derivative", "equity"):
            return done(k, mix, asset_class=k)
        return done("multi_asset", mix, asset_class="multi_asset")
    out["asset_class"] = "equity"
    if p["preferred"] >= 0.5 * eq:
        return done("preferred", f"preferred {p['preferred']:.0f}% of net assets", asset_class="preferred")

    coded = p["coded"]
    cover = 100.0 * coded / eq
    out["coded_pct"] = round(cover, 2)
    countries = {k: v for k, v in p["country"].items() if k not in OFFSHORE}
    ctot = sum(countries.values()) or 1.0
    china = sum(countries.pop(c, 0.0) for c in ("CN", "HK"))
    if china:
        countries["CN+HK"] = china
    us = 100.0 * countries.get("US", 0.0) / ctot
    fc, fw = _top({k: v for k, v in countries.items() if k != "US"})
    fshare = 100.0 * fw / ctot
    geo = "US" if us >= 80 else "global" if us >= 50 else "country" if fshare >= cuts.share else "international"
    out["geo"], out["country"] = geo, (fc if geo == "country" else None)

    best = None
    for i, (name, col, n) in enumerate(LEVELS):
        code, w = _top(_roll(p["g"], n))
        share = 100.0 * w / coded if coded else 0.0
        out[col], out[f"{col}_share"] = code, (round(share, 2) if code else None)
        if not code or share < cuts.share or 100.0 * w / eq < cuts.floor or (upto is not None and i > upto):
            continue
        if name == "sector":
            best = (name, code, share, None)
        elif best is not None and bench is not None:
            inside = bench[name].get(code, 0.0)
            over = share - 100.0 * inside
            if over >= cuts.excess and inside < 0.95:
                best = (name, code, share, over)
    cov = f"coded {cover:.0f}% of equity"
    if best is not None:
        name, code, share, over = best
        return done(name, f"{code} {share:.0f}% of coded equity, {cov}"
                          + (f", +{over:.0f} over the benchmark" if over is not None else "") + f", geo {geo}",
                    code=code)
    if geo == "country":
        return done("country", f"{fc} {fshare:.0f}% of equity, {cov}", code=fc)
    if geo == "international":
        if fc is None and not us:
            return done("international", f"every equity line is incorporated offshore ({', '.join(sorted(OFFSHORE))}): "
                                         f"no country of business, {cov}")
        return done("international", f"US {us:.0f}%, largest {fc} {fshare:.0f}%, {cov}")
    if cover < cuts.cover:
        return done("low_coverage", f"{cov}, geo {geo}")
    sec_code, sec_share = out["gsector"], out["gsector_share"] or 0.0
    if bench is None:
        return done("diversified", f"no benchmark fund in this build; largest sector {sec_code} {sec_share:.0f}%, "
                                   f"{cov}, geo {geo}")
    mix = {k: v / coded for k, v in _roll(p["g"], 2).items()}
    d = round(0.5 * sum(abs(mix.get(k, 0.0) - bench["sector"].get(k, 0.0)) for k in set(mix) | set(bench["sector"])), 3)
    out["benchmark_distance"] = d
    if d <= cuts.broad:
        return done("broad" if geo == "US" else "broad_global", f"sector-mix distance {d} to the benchmark, {cov}, "
                                                                f"geo {geo}")
    return done("diversified", f"sector-mix distance {d} to the benchmark, largest sector {sec_code} "
                               f"{sec_share:.0f}%, {cov}, geo {geo}")


def load_manual(path: Path | None = None) -> list[dict]:
    """The lines of :data:`MANUAL_FILE` (or ``path``): ``ticker`` (upper-cased), ``primary_class``, optional ``code``,
    ``reason``. A line without a primary_class or a reason raises: a correction nobody can explain is a hand-filled row."""
    path = Path(path) if path is not None else MANUAL_FILE
    out = []
    for row in json.loads(path.read_text(encoding="utf-8")).get("set") or []:
        line = {k: str(row.get(k) or "").strip() for k in ("ticker", "primary_class", "code", "reason")}
        line["ticker"] = line["ticker"].upper()
        if not (line["ticker"] and line["primary_class"] and line["reason"]):
            raise ValueError(f"{path.name}: a line needs ticker, primary_class and reason: {row!r}")
        out.append(line)
    return out


def _norm(name) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(name or "").upper())


def newest_quarter() -> tuple[str, Path] | None:
    """``(quarter, folder)`` of the newest N-PORT quarter that has both Parquet files, or None."""
    root = base.parquet_root().joinpath(*NPORT.split("/"))
    held = [(q, f.parent) for q, f in stage.partitions(root, "quarter", "fund.parquet")
            if (f.parent / "holdings.parquet").is_file()]
    return held[-1] if held else None


def _universe(con: duckdb.DuckDBPyConnection) -> list[dict]:
    cur = con.execute(f"""
        SELECT e.ticker, e.name, e.series_id, e.asset_class, coalesce(e.is_lev_inverse, false) AS lev,
               coalesce(e.is_option_income, false) AS opt, coalesce(e.is_fund_of_funds, false) AS fof,
               coalesce(e.is_money_market, false) AS mm
        FROM {my_universe.TABLE} m JOIN {etf_mod.TABLE} e USING (ticker)
        WHERE m.kind = '{my_universe.ETF}' ORDER BY e.ticker""")
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def profiles(con: duckdb.DuckDBPyConnection, funds: list[dict], folder: Path | None) -> dict[str, dict]:
    """``{ticker: profile}`` for :func:`classify`, from the N-PORT Parquet in ``folder`` and the ``security`` and
    ``etf`` tables of ``con``. A fund is linked to its series by ``etf.series_id``, else by its registered name where
    exactly one series and one fund carry it (the N-CEN ticker match missed about 60 registered funds)."""
    out = {f["ticker"]: {**f, "no_report": True, "why": "no N-PORT Parquet in this build"} for f in funds}
    if folder is None:
        return out
    fund, hold = (base.sql_path(folder / n) for n in ("fund.parquet", "holdings.parquet"))
    reports = con.execute(f"""
        SELECT series_id, series_name, accession, report_date FROM read_parquet({fund})
        WHERE series_id IS NOT NULL
        QUALIFY row_number() OVER (PARTITION BY series_id
                                   ORDER BY report_date DESC NULLS LAST, filed DESC NULLS LAST, accession DESC) = 1
        """).fetchall()
    by_series = {s: (acc, day) for s, _, acc, day in reports}
    names = Counter(_norm(n) for _, n, _, _ in reports if _norm(n))
    by_name = {_norm(n): (acc, day) for _, n, acc, day in reports if names[_norm(n)] == 1}
    ours = Counter(_norm(f["name"]) for f in funds)
    linked = []
    for f in funds:
        p, key = out[f["ticker"]], _norm(f["name"])
        hit = by_series.get(f["series_id"]) if f["series_id"] else None
        if hit is None and not f["series_id"] and ours[key] == 1:
            hit = by_name.get(key)
        if hit is None:
            p["why"] = (f"series {f['series_id']} has no N-PORT report in the newest quarter" if f["series_id"]
                        else "no N-PORT report: the fund has no series (a unit trust, a grantor trust, or not linked)")
            continue
        p["as_of"] = hit[1]
        linked.append({"ticker": f["ticker"], "accession": hit[0]})
    if not linked:
        return out
    base.rows_table(con, "_ec_fund", [("ticker", "TEXT"), ("accession", "TEXT")], linked)
    con.execute(f"""
        CREATE OR REPLACE TEMP TABLE _ec_h AS
        WITH bc AS (SELECT cusip, min(gsubind) AS g FROM security WHERE cusip IS NOT NULL AND gsubind IS NOT NULL
                    GROUP BY 1 HAVING count(*) = 1),
             bi AS (SELECT isin, min(gsubind) AS g FROM security WHERE isin IS NOT NULL AND gsubind IS NOT NULL
                    GROUP BY 1 HAVING count(*) = 1),
             bt AS (SELECT ticker, gsubind AS g FROM security WHERE gsubind IS NOT NULL),
             h AS (SELECT f.ticker AS etf, h.pct_of_net_assets AS pct, h.country, h.asset_cat,
                          h.cusip, h.isin, replace(h.ticker, '.', '-') AS tic,
                          -- a ticker is a US ticker only on a US line: a local ticker abroad can spell the same
                          (h.country = 'US' OR h.isin LIKE 'US%' OR (h.country IS NULL AND h.isin IS NULL)) AS us_line,
                          CASE WHEN h.asset_cat IN ('EC', 'EP') THEN 'equity'
                               WHEN h.asset_cat IN ('DBT', 'LON', 'SN') OR h.asset_cat LIKE 'ABS%' THEN 'debt'
                               WHEN h.asset_cat IN ('STIV', 'RA') THEN 'cash'
                               WHEN h.asset_cat IN ('DCO', 'DCR', 'DE', 'DFE', 'DIR', 'DO') THEN 'derivative'
                               WHEN h.asset_cat = 'COMM' THEN 'commodity'
                               WHEN h.asset_cat = 'RE' THEN 'real_estate' ELSE 'other' END AS bucket,
                          h.issuer_type = 'RF' AS is_rf,
                          regexp_matches(upper(coalesce(h.issuer_name, '')), '{_FUND_NAME}') AS fund_name
                   FROM _ec_fund f JOIN read_parquet({hold}) h ON h.accession = f.accession)
        SELECT h.etf, h.pct, h.country, h.asset_cat,
               -- a registered fund is a fund whatever its asset category says (AOR, HEFA); a ticker or a name
               -- only decides a line N-PORT calls equity
               CASE WHEN coalesce(h.is_rf, false) THEN 'fund'
                    WHEN h.bucket = 'equity' AND (e.ticker IS NOT NULL OR h.fund_name) THEN 'fund'
                    ELSE h.bucket END AS bucket,
               CAST(coalesce(bc.g, bi.g, bt.g) AS VARCHAR) AS gsubind
        FROM h LEFT JOIN bc ON bc.cusip = h.cusip LEFT JOIN bi ON bi.isin = h.isin
        LEFT JOIN bt ON bt.ticker = h.tic AND h.us_line
        LEFT JOIN {etf_mod.TABLE} e ON e.ticker = h.tic AND h.us_line""")
    keys = ("equity", "preferred", "debt", "cash", "derivative", "commodity", "fund", "real_estate", "coded")
    for r in con.execute("""
            SELECT etf, sum(pct) FILTER (WHERE bucket = 'equity'),
                   sum(pct) FILTER (WHERE bucket = 'equity' AND asset_cat = 'EP'),
                   sum(pct) FILTER (WHERE bucket = 'debt'), sum(pct) FILTER (WHERE bucket = 'cash'),
                   sum(abs(pct)) FILTER (WHERE bucket = 'derivative'), sum(pct) FILTER (WHERE bucket = 'commodity'),
                   sum(pct) FILTER (WHERE bucket = 'fund'), sum(pct) FILTER (WHERE bucket = 'real_estate'),
                   sum(pct) FILTER (WHERE bucket = 'equity' AND gsubind IS NOT NULL)
            FROM _ec_h GROUP BY 1""").fetchall():
        p = out[r[0]]
        p.update({k: float(v or 0.0) for k, v in zip(keys, r[1:])}, g={}, country={})
        p.pop("no_report"), p.pop("why")
    for t, k, w in con.execute("SELECT etf, gsubind, sum(pct) FROM _ec_h WHERE bucket = 'equity' "
                               "AND gsubind IS NOT NULL GROUP BY 1, 2").fetchall():
        out[t]["g"][k] = float(w or 0.0)
    for t, k, w in con.execute("SELECT etf, country, sum(pct) FROM _ec_h WHERE bucket = 'equity' "
                               "GROUP BY 1, 2").fetchall():
        out[t]["country"][k or "?"] = float(w or 0.0)
    for t in ("_ec_h", "_ec_fund"):
        con.execute(f"DROP TABLE {t}")
    for f in linked:                       # a linked report with no holding line at all
        p = out[f["ticker"]]
        if p.get("no_report"):
            p["why"] = "its N-PORT report has no holding line"
    return out


def _label(primary: str, code: str | None) -> str | None:
    from . import security                 # ``security`` imports this module
    if primary == "sector":
        return security.GICS_SECTORS.get(code or "")
    if primary == "industry_group":
        return security.GICS_GROUPS.get(code or "")
    return None


def _key(r: dict) -> str:
    return r["primary_class"] + (f" {r['code']}" if r.get("code") else "")


def hold(p: dict, bench: dict | None, cuts: Cuts, was: dict, r: dict) -> dict:
    """``r`` (the rule's answer), or the live label ``was`` where it still holds with every cut ``leave`` points
    lower. The live label is asked about at its OWN level: the lower cuts also let a finer level in, which is not
    the live label holding (review finding 6). A finer level that passed the full cuts is a new label and wins."""
    level = {name: i for i, (name, _, _) in enumerate(LEVELS)}
    live, new = level.get(was["primary_class"]), level.get(r["primary_class"])
    if _key(was) == _key(r) or p.get("no_report") or (live is not None and new is not None and new > live):
        return r
    held = classify(p, bench, cuts.relaxed(), upto=live)
    if _key(held) != _key(was):
        return r
    return {**held, "reason": held["reason"] + f"; kept, within {cuts.leave:.0f} points of the cut"}


def rows(ctx: base.RunContext, con: duckdb.DuckDBPyConnection, manual: list[dict] | None = None,
         cuts: Cuts = Cuts()) -> tuple[list[dict], list[dict], list[tuple[str, str, str]]]:
    """``(etf_class rows, etf_class_changes rows, issues)`` for the ETFs of the ``my_universe`` table of ``con``."""
    as_of = ctx.as_of or date.today()
    funds = _universe(con)
    newest = newest_quarter()
    live_rows = stage.live_rows(TABLE, [c for c, _ in SCHEMA])
    live = {r["ticker"]: r for r in live_rows or []}
    profs = profiles(con, funds, newest[1] if newest else None)
    bench_name = next((t for t in BENCHMARKS if profs.get(t, {}).get("coded")), None)
    bench = benchmark_of(profs[bench_name]["g"]) if bench_name else None
    source = f"{NPORT} {newest[0]}" if newest else None
    out: dict[str, dict] = {}
    for f in funds:
        t, p, was = f["ticker"], profs[f["ticker"]], live.get(f["ticker"])
        if newest is None and was is not None:
            out[t] = {**was, "run_id": ctx.run_id}          # an input outage is not a rule change
            continue
        r = classify(p, bench, cuts)
        if was is not None and not was.get("manual"):
            r = hold(p, bench, cuts, was, r)
        r.update(ticker=t, label=_label(r["primary_class"], r["code"]), manual=False, as_of=p.get("as_of"),
                 source=None if p.get("no_report") else source, run_id=ctx.run_id)
        out[t] = r
    issues: list[tuple[str, str, str]] = []
    for line in manual if manual is not None else load_manual():
        r = out.get(line["ticker"])
        if r is None:
            issues.append(("etf_class_manual_unknown", line["ticker"],
                           f"a line of {MANUAL_FILE.name} naming a ticker that is no ETF of my_universe"))
            continue
        code = line["code"] or None
        r.update(primary_class=line["primary_class"], code=code, label=_label(line["primary_class"], code), manual=True,
                 reason=f"by hand in {MANUAL_FILE.name}: {line['reason']} (the rule said: {r['reason']})")
    changes = list(stage.live_rows(CHANGES, [c for c, _ in CHANGES_SCHEMA]) or [])
    for t in sorted(out):
        r, was = out[t], live.get(t)
        same = was is not None and _key(was) == _key(r)
        r["since"] = (was.get("since") or as_of) if same else as_of
        # A fund that starts or stops being hidden on the boards is a change too, though its label stands.
        flip = same and was.get("hidden_by_default") is not None and bool(was["hidden_by_default"]) != bool(
            r.get("hidden_by_default"))
        if not same or flip:
            why = f"structure {was.get('structure')} -> {r.get('structure')}; {r['reason']}" if flip else r["reason"]
            changes.append({"ticker": t, "change": CHANGED if was is not None else ENTERED,
                            "was": _key(was) if was is not None else None, "now": _key(r), "reason": why,
                            "as_of": as_of, "run_id": ctx.run_id})
    changes += [{"ticker": t, "change": LEFT, "was": _key(was), "now": None, "reason": "no longer an ETF of "
                 "my_universe", "as_of": as_of, "run_id": ctx.run_id} for t, was in sorted(live.items())
                if t not in out]
    kinds = Counter(r["primary_class"] for r in out.values())
    ctx.notes.append(f"{len(out)} in {TABLE} from {source or 'no N-PORT Parquet'}, benchmark {bench_name}: "
                     + ", ".join(f"{k} {n}" for k, n in kinds.most_common(6)))
    return [out[t] for t in sorted(out)], changes, issues
