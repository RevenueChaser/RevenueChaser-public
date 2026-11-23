"""What else a 13F says beside the long book (#1447, #1449, #1450; the xReview of 22 Nov 2026, agreed top 5): built by
``ownership/serve`` after its long-equity tables, from the same active filings (``_active``), the same VALUE factor
(``sec13f_filer_period.value_factor``, #208/#780) and the same CUSIP names (``sec13f_cusip_map``).

- ``sec13f_option_exposure`` (#1447): per ticker, quarter, ``PUT`` or ``CALL`` and whether the filer is a market
  maker (``MARKET_MAKERS``, by filer name; the 13F has no flag): filers, underlying shares and dollars. The shares on
  an option line are the underlying's, its value the underlying's fair value: no delta, no premium, no written
  options and no trades are in a 13F, so this is **exposure**, never a put/call ratio, a volume or a leverage, and it
  is never added to the long book, the holders or % Out. A line whose dollars per share sit 30-300 times the
  quarter's consensus price was written in contracts (a filer such as CTC: value/shares ~100x price), so its shares
  are read times 100 (``contracts_read`` counts them).
- ``sec13f_option_holders`` (#1447): the same lines per ticker, quarter and filer, call and put side by side (the
  board's list of who holds them), from ``DETAIL_FROM`` on.
- ``sec13f_filer_options`` (#1447): per filer, quarter and ``PUT``/``CALL`` the option book in names and dollars.
- ``sec13f_prn_par`` (#1450): per ticker and quarter the principal (``PRN``) its issuer's debt lines carry in 13F
  books, mostly convertibles: par, dollars, filers. The issuer is the CUSIP's first six characters when exactly one
  spine ticker has a CUSIP starting with them (two share classes of one issuer share the six, so such an issuer is
  left out rather than guessed). Shown beside FINRA short interest, never subtracted from it.
- ``sec13f_prn_holders`` (#1450): the same lines per ticker, quarter, filer and note (CUSIP), from ``DETAIL_FROM`` on.
- ``sec13f_reported_by`` (#1449, cost A): per filer and quarter of its active filings, a ``13F COMBINATION REPORT``
  is ``partial`` (other managers report part of its book), and the cover page's List of Other Managers Reporting for
  this Manager (``managers`` kind ``cover``) names who, one row each. It says who files, not how much; a list on a
  plain holdings report is names only, not proof that the book is partial. ``other_manager`` on a holding is never
  a key and no manager is matched to a fund by name.
- ``sec13f_late_reveals`` (#1450): a ``NEW HOLDINGS`` amendment filed after the quarter's deadline by a filer whose
  earlier report for that quarter left holdings out under confidential treatment (``confidential_omitted``): the
  positions it reveals, in long-equity dollars and names, and the days past the deadline. ``confidential_omitted``
  says that something was left out, not which line, so the amendment's own lines are what was revealed.
"""
from __future__ import annotations

import duckdb

from . import common, sec13f

OPTIONS = [("ticker", "TEXT"), ("period", "DATE"), ("put_call", "TEXT"), ("market_maker", "BOOLEAN"),
           ("filers", "INTEGER"), ("shares", "DOUBLE"), ("value", "DOUBLE"), ("contracts_read", "INTEGER")]
FILER_OPTIONS = [("cik", "TEXT"), ("period", "DATE"), ("filer_name", "TEXT"), ("market_maker", "BOOLEAN"),
                 ("put_call", "TEXT"), ("names", "INTEGER"), ("value", "DOUBLE")]
PRN = [("ticker", "TEXT"), ("period", "DATE"), ("filers", "INTEGER"), ("cusips", "INTEGER"), ("par", "DOUBLE"),
       ("value", "DOUBLE")]
OPTION_HOLDERS = [("ticker", "TEXT"), ("period", "DATE"), ("cik", "TEXT"), ("filer_name", "TEXT"),
                  ("market_maker", "BOOLEAN"), ("call_shares", "DOUBLE"), ("call_value", "DOUBLE"),
                  ("put_shares", "DOUBLE"), ("put_value", "DOUBLE"), ("contracts_read", "INTEGER")]
PRN_HOLDERS = [("ticker", "TEXT"), ("period", "DATE"), ("cik", "TEXT"), ("filer_name", "TEXT"), ("cusip", "TEXT"),
               ("name_of_issuer", "TEXT"), ("title_of_class", "TEXT"), ("par", "DOUBLE"), ("value", "DOUBLE")]
REPORTED_BY = [("cik", "TEXT"), ("period", "DATE"), ("filer_name", "TEXT"), ("report_type", "TEXT"),
               ("partial", "BOOLEAN"), ("seq", "INTEGER"), ("manager_cik", "TEXT"), ("manager_name", "TEXT"),
               ("form13f_file_number", "TEXT")]
REVEALS = [("cik", "TEXT"), ("period", "DATE"), ("filer_name", "TEXT"), ("accession", "TEXT"), ("filed", "DATE"),
           ("days_late", "INTEGER"), ("names", "INTEGER"), ("value", "DOUBLE"), ("top_issuer", "TEXT")]
SCHEMAS = {"sec13f_option_exposure": OPTIONS, "sec13f_option_holders": OPTION_HOLDERS,
           "sec13f_filer_options": FILER_OPTIONS, "sec13f_prn_par": PRN, "sec13f_prn_holders": PRN_HOLDERS,
           "sec13f_reported_by": REPORTED_BY, "sec13f_late_reveals": REVEALS}
DETAIL_FROM = "2019-03-31"               # the per-filer lists start with the board (``module_sec_13f.engine``, #1442)
TEMPS = ("_opt", "_prn", "_optx", "_prnx")

# Options market makers and the dealer banks' 13F filers, matched as whole words in the filer's name (the 13F carries
# no market-maker flag). shortcut: a name list, kept by hand; upgrade to a CIK list once the board shows which
# filers it catches.
MARKET_MAKERS = ("CITADEL ADVISORS", "CITADEL SECURITIES", "SUSQUEHANNA", "JANE STREET", "OPTIVER", "IMC",
                 "WOLVERINE", "GROUP ONE", "SIMPLEX", "PEAK6", "BELVEDERE", "HUDSON RIVER", "VIRTU", "AKUNA", "CTC",
                 "XR SECURITIES", "PARALLAX", "GOLDMAN SACHS GROUP", "MORGAN STANLEY", "UBS GROUP", "BARCLAYS",
                 "BNP PARIBAS", "JPMORGAN", "BANK OF AMERICA", "CITIGROUP", "WELLS FARGO", "ROYAL BANK OF CANADA",
                 "TORONTO DOMINION", "DEUTSCHE BANK", "NOMURA", "MIZUHO", "SOCIETE GENERALE",
                 "TWO SIGMA SECURITIES", "SIG", "ALTIUM", "BOOTHBAY")
CONTRACT_BAND = (30.0, 300.0)            # dollars per share this many times the consensus price: written in contracts
SHARES_PER_CONTRACT = 100


def market_maker_sql(col: str) -> str:
    """SQL: whether the filer name ``col`` names one of ``MARKET_MAKERS`` as whole words."""
    words = "|".join(MARKET_MAKERS)
    return f"coalesce(regexp_matches(upper({col}), '(^|[^A-Z0-9])({words})([^A-Z0-9]|$)'), false)"


def _lines(con: duckdb.DuckDBPyConnection, files, table: str, where: str) -> None:
    """``table`` (TEMP): the active filings' holdings that ``where`` keeps, by quarter, with the filer's VALUE factor
    applied to ``value`` (the long book's post-#208 dollars; ``value_scale`` is not applied again)."""
    cols = [("accession", "TEXT"), ("cik", "TEXT"), ("period", "DATE"), ("filer_name", "TEXT"), ("cusip", "TEXT"),
            ("name_of_issuer", "TEXT"), ("title_of_class", "TEXT"), ("put_call", "TEXT"), ("shares", "DOUBLE"),
            ("value", "DOUBLE")]
    common.temp_rows(con, table, cols, [])
    if not files:
        return
    con.execute(f"""INSERT INTO {table}
        SELECT h.accession, h.cik, {common.quarter_end('h.period')}, f.filer_name, upper(h.cusip), h.name_of_issuer,
               h.title_of_class, upper(trim(h.put_call)), h.shares, h.value_usd * coalesce(p.value_factor, 1)
        FROM {common.files_sql(files)} h
        JOIN _active a ON a.accession = h.accession
        JOIN {sec13f.TABLE} f ON f.accession = h.accession
        LEFT JOIN sec13f_filer_period p ON p.cik = h.cik AND p.period = {common.quarter_end('h.period')}
        WHERE h.cusip IS NOT NULL AND h.cik IS NOT NULL AND h.period IS NOT NULL AND ({where})""")


def build(con: duckdb.DuckDBPyConnection, pad) -> dict[str, int]:
    """The seven tables, from ``_active``, ``_px``, ``_deadline``, ``_sp_security``, ``sec13f_filer_period`` and
    ``sec13f_cusip_map`` that ``ownership/serve`` has built; ``pad(con, table)`` gives an eight-digit CUSIP its lost
    leading zero as the long book does (#937). Their row counts."""
    files = sec13f.DATASET.holding_files()
    _lines(con, files, "_opt", "upper(trim(h.put_call)) IN ('PUT', 'CALL')")
    _lines(con, files, "_prn", "upper(h.sh_type) = 'PRN' AND coalesce(trim(h.put_call), '') = ''")
    pad(con, "_opt")
    pad(con, "_prn")
    lo, hi = CONTRACT_BAND
    con.execute(f"""CREATE OR REPLACE TEMP TABLE _optx AS
        SELECT m.ticker, o.period, o.cik, o.filer_name, o.put_call, {market_maker_sql('o.filer_name')} AS market_maker,
               o.value,
               o.shares * CASE WHEN o.shares > 0 AND px.px > 0
                                    AND o.value / o.shares BETWEEN {lo!r} * px.px AND {hi!r} * px.px
                               THEN {SHARES_PER_CONTRACT} ELSE 1 END AS shares,
               coalesce(o.shares > 0 AND px.px > 0
                        AND o.value / o.shares BETWEEN {lo!r} * px.px AND {hi!r} * px.px, false) AS contracts
        FROM _opt o
        JOIN sec13f_cusip_map m ON m.cusip = o.cusip AND m.period = o.period AND m.ticker IS NOT NULL
        LEFT JOIN _px px ON px.cusip = o.cusip AND px.period = o.period""")
    counts = {"sec13f_option_exposure": common.create_table(con, "sec13f_option_exposure", OPTIONS, """
        SELECT ticker, period, put_call, market_maker, count(DISTINCT cik) AS filers, sum(shares) AS shares,
               sum(value) AS value, count(*) FILTER (WHERE contracts) AS contracts_read
        FROM _optx GROUP BY ALL ORDER BY ticker, period, put_call, market_maker""")}
    counts["sec13f_option_holders"] = common.create_table(con, "sec13f_option_holders", OPTION_HOLDERS, f"""
        SELECT ticker, period, cik, max(filer_name), bool_or(market_maker),
               sum(shares) FILTER (WHERE put_call = 'CALL'), sum(value) FILTER (WHERE put_call = 'CALL'),
               sum(shares) FILTER (WHERE put_call = 'PUT'), sum(value) FILTER (WHERE put_call = 'PUT'),
               count(*) FILTER (WHERE contracts)
        FROM _optx WHERE period >= DATE '{DETAIL_FROM}'
        GROUP BY ticker, period, cik ORDER BY ticker, period, cik""")
    counts["sec13f_filer_options"] = common.create_table(con, "sec13f_filer_options", FILER_OPTIONS, f"""
        SELECT cik, period, max(filer_name) AS filer_name, {market_maker_sql('max(filer_name)')} AS market_maker,
               put_call, count(DISTINCT cusip) AS names, sum(value) AS value
        FROM _opt GROUP BY cik, period, put_call ORDER BY period, cik, put_call""")
    con.execute("""CREATE OR REPLACE TEMP TABLE _prnx AS
        WITH issuer AS (SELECT left(cusip, 6) AS c6, min(ticker) AS ticker FROM _sp_security
                        WHERE cusip IS NOT NULL AND length(cusip) >= 6 AND ticker IS NOT NULL
                        GROUP BY 1 HAVING count(DISTINCT ticker) = 1)
        SELECT i.ticker, p.* FROM _prn p JOIN issuer i ON i.c6 = left(p.cusip, 6)""")
    counts["sec13f_prn_par"] = common.create_table(con, "sec13f_prn_par", PRN, """
        SELECT ticker, period, count(DISTINCT cik) AS filers, count(DISTINCT cusip) AS cusips,
               sum(shares) AS par, sum(value) AS value
        FROM _prnx GROUP BY ALL ORDER BY ticker, period""")
    counts["sec13f_prn_holders"] = common.create_table(con, "sec13f_prn_holders", PRN_HOLDERS, f"""
        SELECT ticker, period, cik, max(filer_name), cusip, max(name_of_issuer), max(title_of_class),
               sum(shares), sum(value)
        FROM _prnx WHERE period >= DATE '{DETAIL_FROM}'
        GROUP BY ticker, period, cik, cusip ORDER BY ticker, period, cik, cusip""")
    counts["sec13f_reported_by"] = _reported_by(con)
    counts["sec13f_late_reveals"] = _reveals(con, files)
    return counts


def _reported_by(con: duckdb.DuckDBPyConnection) -> int:
    common.create_table(con, "sec13f_reported_by", REPORTED_BY)
    files = [f for _, f in sec13f.partitions(sec13f.DATASET.parquet_dir() / "managers", "day")]
    cover = (f"SELECT accession, seq, manager_cik, name, form13f_file_number FROM {common.files_sql(files)} "
             f"WHERE kind = 'cover'") if files else \
        "SELECT NULL::TEXT AS accession, NULL::INTEGER AS seq, NULL::TEXT AS manager_cik, NULL::TEXT AS name, " \
        "NULL::TEXT AS form13f_file_number WHERE false"
    con.execute(f"""INSERT INTO sec13f_reported_by
        WITH f AS (SELECT f.accession, f.cik, {common.quarter_end('f.period')} AS period, f.filer_name, f.report_type
                   FROM {sec13f.TABLE} f JOIN _active a ON a.accession = f.accession),
             c AS ({cover})
        SELECT f.cik, f.period, f.filer_name, f.report_type, coalesce(f.report_type LIKE '%COMBINATION%', false),
               c.seq, ltrim(c.manager_cik, '0'), c.name, c.form13f_file_number
        FROM f LEFT JOIN c ON c.accession = f.accession
        WHERE c.accession IS NOT NULL OR f.report_type LIKE '%COMBINATION%'
        ORDER BY f.period, f.cik, c.seq""")
    return common.count(con, "sec13f_reported_by")


def _reveals(con: duckdb.DuckDBPyConnection, files) -> int:
    common.create_table(con, "sec13f_late_reveals", REVEALS)
    if not files:
        return 0
    con.execute(f"""INSERT INTO sec13f_late_reveals
        WITH f AS (SELECT accession, cik, {common.quarter_end('period')} AS period, filed, filer_name, amendment_type,
                          confidential_omitted
                   FROM {sec13f.TABLE} WHERE status = 'ok' AND cik IS NOT NULL AND period IS NOT NULL),
             r AS (SELECT a.accession, a.cik, a.period, a.filed, a.filer_name, d.deadline
                   FROM f a JOIN _deadline d ON d.period = a.period
                   WHERE a.amendment_type = 'NEW HOLDINGS' AND a.filed > d.deadline
                     AND EXISTS (SELECT 1 FROM f o WHERE o.cik = a.cik AND o.period = a.period AND o.filed <= a.filed
                                 AND o.accession <> a.accession AND o.confidential_omitted)),
             l AS (SELECT r.accession, h.name_of_issuer, h.cusip,
                          h.value_usd * coalesce(p.value_factor, 1) AS value
                   FROM {common.files_sql(files)} h JOIN r ON r.accession = h.accession
                   LEFT JOIN sec13f_filer_period p ON p.cik = r.cik AND p.period = r.period
                   WHERE upper(h.sh_type) = 'SH' AND coalesce(trim(h.put_call), '') = '')
        SELECT r.cik, r.period, r.filer_name, r.accession, r.filed, CAST(date_diff('day', r.deadline, r.filed) AS INTEGER),
               count(DISTINCT l.cusip), sum(l.value), arg_max(l.name_of_issuer, l.value)
        FROM r LEFT JOIN l ON l.accession = r.accession
        GROUP BY r.cik, r.period, r.filer_name, r.accession, r.filed, r.deadline
        ORDER BY r.period, r.filed, r.cik""")
    return common.count(con, "sec13f_late_reveals")
