# WRDS catalog: what the login can read, measured

What this file answers: which WRDS data sets our login can actually read, how big and how fresh each is, which of
them the code already uses, and what each could give the boards (Relatedness, Value Chain, Co-movement, Fundamentals).
It is a measurement, not a plan: nothing here is fetched until an issue of its own says so (#1147).

Every readable table, one row each, is in [`wrds_catalog_tables.md`](wrds_catalog_tables.md), with the names of the
schemas we cannot read at its end. Column names and five sample rows per table are **not** in this repository (it
carries no market data); they are in the scan output, `wrds-catalog.tar.gz` in the project files.

## The scan

Run once on the server on 20 Nov 2026, read-only, 826 queries, one connection. For every schema the login has
`USAGE` on: all columns, the planner's row estimate, five rows from each table, and the oldest and newest date of
tables under 5 million estimated rows.

| | count |
|---|---|
| schemas the login has `USAGE` on | 385 |
| schemas with no access | 1,574 |
| tables and views seen in the 385 | 51,409 |
| **readable** (a `SELECT` returned) | **4,072**, in 241 schemas |
| readable and returned rows | 3,955 |
| readable but empty | 117 |
| not readable | 47,337 |

Why 47,337 are not readable:

| reason | tables |
|---|---|
| a view over a schema we have no `USAGE` on (not asked with a `SELECT`) | 45,770 |
| `SELECT` asked and refused (permission denied) | 1,221 |
| CRSP legacy objects that raise an error on any read (`crspa.*`) | 243 |
| timed out at the scan's limit (sample schemas: `taqsamp` 50, `ciqsamp` 8, `msciesmp` 6, `compsamp` 2) | 66 |
| **the scan's own error, not an answer** (`ciq` 26, `cboe` 9, `calcbnch` 1, `ciqsamp` 1) | 37 |

How to read the numbers:

- **A schema being visible says nothing.** WRDS shows every schema, table and column name to everybody; only a real
  `SELECT` shows whether the subscription covers it. `information_schema` cannot answer "can we read it".
- **Rows are estimates** (`pg_class.reltuples`), never a `count(*)`. A view has no estimate; the umbrella schemas
  (`comp`, `crsp`, `audit`, `boardex`, `wrdsapps`, `contrib`) are views over the product schemas listed beside them.
- **A newest date after the scan day** is the vendor's placeholder or a fiscal period end, not data from the future.
  The per-schema table below ignores such dates; the per-table file prints them as stored.
- 126 date ranges were not asked (table too large), 10 failed on a column name the query could not quote.
- Schemas whose name ends in `_old` are frozen copies of a product and were left out of the scan on purpose.
- The WRDS driver reads `%s`, `%r`, `%f` inside SQL as placeholders and fails with `immutabledict is not a
  sequence`; a pattern such as `ILIKE '%revere%'` needs `%%` or `strpos()`.

## What the code reads today

`comp.secd`, `comp.sec_divid`, `comp.sec_split`, `comp.sec_idhist`, `comp.security`, `comp.company`, `comp.g_security`,
`comp.g_company`, `comp.idxcst_his`, `comp.co_hgic`, `comp.r_giccd`, `comp.funda`, `comp.fundq`,
`comp_na_daily_all.r_ex_codes`, `crsp.dsf_v2`, `crsp_a_stock.stkdelists`, `crsp_a_stock.dsi`,
`comp_segments_hist_daily.wrds_segmerged` and `comp_segments_hist_daily.seg_customer`
(`rcdata/build/prices/wrds_history.py`, `rcdata/build/fundamentals/wrds_fund.py`, `rcdata/build/spine/`). All of them
are in the readable list.

## What we asked about and do not have

| product | what the scan saw | consequence |
|---|---|---|
| IBES analyst estimates (`ibes`) | 194 views, all over `tr_ibes`, no access | no "same analysts cover both firms" measure, no consensus or guidance history |
| FactSet Revere, full (`revere`, `factset_revere_*`) | 66 views, no access; only the 2015 sample reads | no ready customer / supplier / competitor relationships, no RBICS sectors |
| Supply Chain with IDs (`wrdsapps_link_supplychain`) | `SELECT` refused | Compustat customer names keep being matched to tickers by name |
| CRSP/Compustat Merged (`crsp_a_ccm`) | no access | no gvkey to permno bridge; it is also the listed precondition of Supply Chain with IDs |
| Capital IQ (`ciq`) | 259 not readable: 233 views over schemas with no access, **26 scan errors** | most of it is not ours; the 26 are unanswered and need one more query each |
| WRDS SEC Analytics (`wrdssec`) | 314 views, no access; one MIDAS table reads | no ready 10-K text tables; our own SEC store stays the source |
| Thomson 13F (`tfn`), OptionMetrics (`optionm`), TAQ milliseconds (`taqmsec`) | 27, 578 and 39,262 views, no access | nothing |
| Hoberg-Phillips TNIC | no schema or table of that name anywhere in WRDS | published by its authors outside WRDS, free; the comparison for our word method |

## What each board could use

Sizes and dates are from the scan; "could" is a judgement, nothing here has been tried on a board.

### Relatedness

| data set | size, newest | what it would add |
|---|---|---|
| `contrib_general.common_own_firm` | 1.14 bn rows, yearly | A ready firm-pair measure: common ownership of `gvkey_a` and `gvkey_b` per year (five variants). A second, independent signal next to text; years covered were not asked (too large). |
| `boardex_na.na_wrds_company_networks` | 5.0 m rows | Company-to-company links through shared directors, with start and end of the overlap. A relationship graph that owes nothing to text or price. `na_wrds_individual_networks` (1.6 bn) is the person-level version. |
| `comp_segments_hist_daily.seg_product`, `seg_naics` | 758 k and 1.42 m rows, to 2026-09-30 | Per business segment: product name, NAICS and SIC code, sales. Splits a many-business company (the AMZN case) into lines with an industry code each, without an LLM. |
| `comp.co_hgic` | 46 k rows, to 2026-11-18 | GICS history per company with from/thru dates (in use for the spine); the yardstick the exam already compares against. |
| `comp.company` (`busdesc`, `gsubind`, `naics`, `sic`) | 58.8 k rows | Compustat's own short business description: a second text per company, uniform in length. |
| `wrdsapps_patents.uspatents_citations`, `uspatents_gvkey_linking`; `contrib_patent_firm_link.patent_level` | 54.4 m, 1.47 m, 8.5 m rows; link ends 2019-12-31 | Technology closeness: which firms cite each other's patents, CPC class per patent. Stale after 2019. |
| `fjc_linking.wrds_civil_link` | 180 k rows, to 2024-12-12 | Federal civil cases with plaintiff gvkey and defendant gvkey: firms that sue each other are often rivals or partners. |
| `contrib_general.as_firm_risks` | 132 k rows, to 2025-01-07 | Item 1A risk factors classified into classes per filing: a coarse "exposed to the same risks" vector. |
| `factsamp_revere.wrds_relationship`, `wrds_sector` | 27 k and 20 k rows, **frozen May 2015** | Shows the format of Revere's competitor links and sector tree. Too old and too narrow to score against. |

Not available for this board: analyst co-coverage (IBES), Revere competitors and RBICS, Capital IQ competitors.

### Value Chain

| data set | size, newest | what it would add |
|---|---|---|
| `comp_segments_hist_daily.seg_customer` | 736 k rows, 1976 to 2026-09-30 | In use: the named customers with sales and customer type. The table also carries customer geography (`gareac`, `gareat`). |
| `wrdsapps_subsidiary.wrds_relationships` | 12.3 m rows | Exhibit 21: subsidiary name to parent `cik` / `gvkey`. Measured by the Value Chain work on 20 Nov 2026: 92 of the 4,255 unresolved customer labels match a subsidiary safely. Small; no `wrds/subsidiaries` data set is planned, the 92 matches are taken as a derived mapping in separate work. |
| `contrib_general.blocksv` | 608 k rows | Blockholder to company by year: ownership links, not trade links. |
| `fjc_linking.wrds_civil_link` | 180 k rows | Contract disputes name both sides; weak, indirect evidence of a commercial tie. |
| `factsamp_revere.wrds_relationship` | 27 k rows, frozen 2015 | Customer 6,649 / supplier 4,142 / competitor 5,713 rows with revenue percent (counts measured by the Value Chain work). Format reference for a request to subscribe; not servable. |

The two real levers are outside this login: Supply Chain with IDs and the full Revere.

### Co-movement

| data set | size, newest | what it would add |
|---|---|---|
| `crsp_a_stock.dsf_v2` (`crsp.dsf_v2`) | 110 m rows | In use for prices. Daily returns back to 1925 for every US common stock: long windows for return correlation. |
| `comp_na_daily_all.secd` (`comp.secd`) | 162 m rows | In use: the primary price source. |
| `comp_global_daily.g_secd` | 320 m rows | Daily prices of non-US listings: co-movement with foreign peers (BMW, Roche) that have no US line. |
| `crsp_q_indexhist.eod_sector`, `eod_cap`, `eod_vg` | 3.5 k to 3.9 k rows, to 2026-09-30 | CRSP sector, size and style index levels: the common part to take out of a pair's correlation. |
| `ff_all.factors_daily`, `fivefactors_daily` | 26 k and 16 k rows, to 2026-09-30 | Fama-French daily factors: residual (factor-adjusted) co-movement instead of raw. |
| `contrib_global_factor.ctff_daily_ret`, `global_factor` | 103 m and 16 m rows | Daily excess returns and 444 characteristics per stock, worldwide. Ends 2023-11-30 where measured. |
| `wrdsapps_windices.dwcountryreturns` | 299 k rows, to 2026-06-26 | Daily country portfolio returns: the country part of a foreign peer's move. |

### Fundamentals

| data set | size, newest | what it would add |
|---|---|---|
| `comp.funda`, `comp.fundq` | 943 k and 2.15 m rows | In use. |
| `comp_snapshot.wrds_csq_pit` and the `csco_*` tables | 10.2 m rows; 125 tables | Point-in-time fundamentals: each value with the date it became known. The honest input for any backtest; today's `fundq` is restated. |
| `wrdsapps_finratio.firm_ratio` | 2.9 m rows, to 2025-10-31 | About 70 ready ratios per firm and month (valuation, profitability, leverage). A cross-check of our own ratios; about a year behind. |
| `comp_bank_daily.bank_fundq`, `bank_funda` | 274 k and 73 k rows, to 2026-09-30 | Bank-specific lines (deposits, loans, capital ratios) the general tables leave empty. |
| `comp_global_daily.g_funda`, `g_fundq` | 1.1 m and 4.2 m rows, to 2026-09-30 | Fundamentals of non-US companies. |
| `audit_audit_comp`, `audit_acct_os` (Audit Analytics) | 59 and 64 tables, to 2026-09-25 | Restatements, going-concern opinions, late filings, auditor changes, internal-control weaknesses: quality flags for a company's numbers. |
| `totalq_all.total_q` | 486 k rows, to 2025-05-31 | Intangible capital and total q per firm-year. |
| `comp_execucomp.anncomp` | 383 k rows, to 2026-10-26 | Executive pay; no board uses it. |

### The other boards and the stores

Read against the code on 20 Nov 2026: every dataset under `rcdata/build/` and every board module, matched to the
readable tables. Coverage of our own universe was not measured for any row below; the match is by table, columns,
size and dates.

| what the code does today | WRDS table | size, dates | what it would add |
|---|---|---|---|
| Short interest: `finra/short_interest`, back to 2017-12-29 (Earnings Radar's positioning rule, SEC 13F) | `comp.sec_shortint`, `sec_shortint_legacy` | 5.4 m and 4.8 m rows; 2006-07-14 to 2026-11-13, legacy 1973 to 2024 | Eleven more years of history, split-adjusted (`shortintadj`), and a check of FINRA's number. |
| Float: Yahoo's and UW's value of today (`yfinance/float`, `uw/total_float`); 13F totals from the SEC's filings | `comp_na_daily_all.io_qaggregate`, `io_qholders`, `io_qbuysell`, `io_qfloatadj` | 157 k, 962 k, 1.5 m, 36 k rows; 2004-03-31 to 2026-06-30 | Institutional ownership per security and quarter (holders, shares, buyers and sellers, top holders) and a float adjustment (insider and 5% holder shares). A float with a history, and a check of our 13F totals. One quarter behind. |
| Report dates: UW's reported EPS and Alpha Vantage's coming dates; `rdq` is fetched by `wrds/fundq` and used only in the check | `comp.fundq` (`rdq`), `comp_na_daily_all.co_idesind`, `co_filedate` | 2.15 m rows from 2002; 2.67 m rows, 1966 to 2026-10-31 | Every past report date and filing date per company: the history Earnings Radar and Hit Rate need to measure reactions. Already in our raw files. |
| Screener history: Hit Rate freezes picks from today on; the screeners read restated facts | `comp_snapshot.wrds_csq_pit`, `wrds_csa_pit` | 10.2 m and 4.2 m rows; 1986-12-14 to 2026-11-04 | Statements as they were known on each day: the Fundamentals, Asymmetric Growth and Swing rules could be replayed over past years without look-ahead. |
| FX: `yfinance/fx` | `comp.exrt_dly` | 2.24 m rows; 1982-02-01 to 2026-11-18 | Daily rates from a licensed source instead of Yahoo, or a check of it. |
| Corporate-event flag: 8-K items of `sec/filings` | `audit_audit_comp.f39_restatement_filings`, `f20_nt_*`, `f17_dno_change` | 83.5 k, 179 k, 258 k rows; to 2026-09-23 / 24 | Restatements with their size, late-filing notices with a reason, director and officer changes: quality flags the 8-K item code alone does not give. About two months behind. |
| CIK history: the spine's own snapshots and a hand-seeded `successor_ciks.csv` | `comp_na_daily_all.co_acthist`, `sec_history` | 56.8 k and 336 k rows; 1988 to 2026-11-18 | Name, ticker, CUSIP and exchange changes with the acquiring `gvkey`: successors from a source instead of a typed seed. |
| Sector Rotation: sector ETFs against SPY; SPX Gamma: SPX from UW | `comp_na_daily_all.idx_daily`, `idx_index` | 8.8 m rows, 2,257 indexes | Daily levels of the S&P index family, the sector indexes themselves instead of an ETF proxy. Date range not asked (over 5 m rows). |
| Bank filers are left out of the Compustat check (`BANK_SIC`) | `comp_bank_daily.bank_fundq` | 274 k rows; to 2026-09-30 | Bank lines for Financials and Fundamentals. |
| Financials' comps and ratios are computed from the SEC facts | `comp_na_daily_all.wrds_ratios` | 4.17 m rows, 95 columns; to 2026-08-31 | A check of our ratios and a ready peer table. |
| Returns are adjusted from our own split and dividend rows | `comp_na_daily_all.sec_dtrt` | 1.2 m rows; 1984 to 2026-11-18 | Compustat's own total-return factor: a check of the adjustment. |

Nothing readable for: options (OptionMetrics; so SPX Gamma, Implied Probability, LEAPS and UW Interaction gain nothing),
analyst estimates and guidance (IBES; a sample ends 2013), insider transactions and 13F holdings in detail (Thomson
Reuters, WRDS SEC), ETF and fund holdings (CRSP Mutual Funds), news (RavenPack is a trial frozen at 2020-09-30; Capital
IQ Key Developments is a sample), short volume (a sample to 2020). Readable but stale: `frb_all.rates_daily` ends
2025-02-13, `comp.adsprate` (S&P credit ratings) 2017-02-28, `contrib_general.better_beta` 2019-12-31,
`cboe_all.cboe` (VIX) 2026-10-30, three weeks behind the Cboe file we already read.

## Every readable schema

241 schemas. Several are the same product under two names (`comp_snapshot` / `compsnap`, `bank` / `bank_all`,
`execcomp` / `comp_execucomp`); the one with a row estimate holds the tables, the other is views.

| schema | readable tables | rows (estimate) | newest date | what it is | could serve |
|---|---|---|---|---|---|
| `aha_sample` | 4 | 1,083 | 2023-01-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ahasamp` | 4 | views, no count | 2023-01-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `altrata_exec_samp` | 35 | 8,067,382 | 2026-07-24 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `altsamp` | 35 | views, no count | 2026-07-24 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `audit` | 260 | views, no count | 2026-09-26 | Audit Analytics: auditors, fees, restatements, internal-control opinions, other filings data | Fundamentals |
| `audit_acct_os` | 64 | 4,330,843 | 2026-09-25 | Audit Analytics: auditors, fees, restatements, internal-control opinions, other filings data | Fundamentals |
| `audit_audit_comp` | 59 | 7,412,514 | 2026-09-25 | Audit Analytics: auditors, fees, restatements, internal-control opinions, other filings data | Fundamentals |
| `audit_common` | 2 | 985,868 | 2026-09-25 | Audit Analytics: auditors, fees, restatements, internal-control opinions, other filings data | Fundamentals |
| `audit_europe` | 25 | 1,209,804 | 2026-09-25 | Audit Analytics: auditors, fees, restatements, internal-control opinions, other filings data | Fundamentals |
| `audit_oia` | 110 | 75,016,367 | 2026-09-26 | Audit Analytics: auditors, fees, restatements, internal-control opinions, other filings data | Fundamentals |
| `auditsmp` | 15 | views, no count | 2020-03-31 | Audit Analytics sample | - |
| `auditsmp_all` | 15 | 1,491 | 2020-03-31 | Audit Analytics sample | - |
| `bank` | 21 | views, no count | 2026-11-03 | Bank regulatory: call reports and holding-company filings | - |
| `bank_all` | 21 | 9,299,277 | 2026-11-03 | Bank regulatory: call reports and holding-company filings | - |
| `bank_premium_samp` | 9 | 163,006 | 2024-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `banksamp` | 9 | views, no count | 2024-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `block` | 3 | views, no count | 2001-12-20 | Small legacy data set | - |
| `block_all` | 3 | 62,925 | 2001-12-20 | Small legacy data set | - |
| `boardex` | 126 | views, no count | 2026-11-13 | BoardEx: directors, their roles and the networks between boards and people | Relatedness |
| `boardex_eur` | 42 | 710,546,241 | 2026-11-13 | BoardEx: directors, their roles and the networks between boards and people | Relatedness |
| `boardex_na` | 42 | 3,312,767,056 | 2026-11-13 | BoardEx: directors, their roles and the networks between boards and people | Relatedness |
| `boardex_trial` | 40 | 790,813 | 2025-01-02 | BoardEx sample | - |
| `boardex_uk` | 42 | 798,635,582 | 2026-11-13 | BoardEx: directors, their roles and the networks between boards and people | Relatedness |
| `boardsmp` | 40 | views, no count | 2025-01-02 | BoardEx sample | - |
| `bvd_amadeus_trial` | 3 | 1,021 | 2013-07-16 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `bvd_bvdbankf_trial` | 6 | 1,369 | 2017-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `bvd_orbis_trial` | 9 | 4,402 | 2015-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `bvdsamp` | 18 | views, no count | 2017-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `calcbench_trial` | 3 | 128,402 | 2016-05-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `calcbnch` | 2 | views, no count | 2016-05-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `candid_samp` | 1 | 30 | 2023-09-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `cboe` | 1 | views, no count | 2026-10-30 | CBOE indexes (VIX family) | - |
| `cboe_all` | 1 | 10,830 | 2026-10-30 | CBOE indexes (VIX family) | - |
| `cboe_sample` | 7 | 170,278 | 2023-12-29 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `cboesamp` | 7 | views, no count | 2023-12-29 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `cddsamp` | 1 | views, no count | 2023-09-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ciqsamp` | 50 | views, no count | 2025-09-26 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ciqsamp_capstrct` | 5 | 68,379 | 2011-11-05 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ciqsamp_common` | 13 | 1,146,986 | 2025-09-26 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ciqsamp_keydev` | 3 | 206,972 | 2023-12-08 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ciqsamp_pplintel` | 14 | 606,534 | 2019-06-19 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ciqsamp_ratings` | 9 | 975,919 | 2011-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ciqsamp_transactions` | 12 | 40,151 | 2025-05-23 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ciqsamp_transcripts` | 2 | 2,109 | 2008-10-30 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `cisdmsmp` | 2 | views, no count | 2013-08-13 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `columnar` | 1 | views, no count | - | Reference / technical table | - |
| `comp` | 292 | views, no count | 2026-11-19 | Compustat, the umbrella views over the North America and Global products | Fundamentals and Prices (in use), Relatedness |
| `comp_bank_daily` | 20 | 1,720,732 | 2026-09-30 | Compustat Bank: bank-specific fundamentals | Fundamentals |
| `comp_execucomp` | 15 | 3,466,857 | 2026-10-26 | ExecuComp: executive and director pay | - |
| `comp_global_daily` | 125 | 766,416,555 | 2026-11-19 | Compustat Global, daily update: non-US fundamentals and prices | Fundamentals, Prices (in use for two identifier tables) |
| `comp_na_daily_all` | 206 | 642,028,576 | 2026-11-19 | Compustat North America, daily update: fundamentals, security prices, index constituents, identifiers | Fundamentals and Prices (in use), Co-movement |
| `comp_segments_hist_daily` | 14 | 13,747,476 | 2026-09-30 | Compustat segments, historical: business, geographic, product and customer segments | Value Chain (in use), Relatedness |
| `comp_snapshot` | 125 | 635,702,080 | 2026-11-05 | Compustat Snapshot: fundamentals as first reported, with the date each value became known (point in time) | Fundamentals |
| `compsamp` | 13 | views, no count | 2025-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `compsamp_all` | 11 | 171,886 | 2021-03-12 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `compsamp_computext` | 2 | 2,791,706 | 2025-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `compsamp_snapshot` | 10 | 2,043,311 | 2015-04-28 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `compseg` | 14 | views, no count | 2026-09-30 | Compustat segments, historical: business, geographic, product and customer segments | Value Chain (in use), Relatedness |
| `compsnap` | 125 | views, no count | 2026-11-05 | Compustat Snapshot: fundamentals as first reported, with the date each value became known (point in time) | Fundamentals |
| `contrib` | 35 | views, no count | 2025-12-31 | Researcher-contributed data: common ownership of firm pairs, 10-K risk classes, blockholders, betas, factors | Relatedness, Co-movement |
| `contrib_ceo_turnover` | 1 | 1,438 | 2021-10-21 | Researcher-contributed data set | - |
| `contrib_char_returns` | 1 | 2,578,736 | 2021-12-31 | Researcher-contributed data set | - |
| `contrib_corp_fed_litigation` | 2 | 268,884 | 2021-12-31 | Researcher-contributed data set | - |
| `contrib_corporate_culture` | 1 | 102,688 | - | Researcher-contributed data set | - |
| `contrib_general` | 20 | 1,146,029,076 | 2025-03-31 | Researcher-contributed data: common ownership of firm pairs, 10-K risk classes, blockholders, betas, factors | Relatedness, Co-movement |
| `contrib_global_factor` | 4 | 120,760,939 | 2023-11-30 | Contributed: global factor data, firm characteristics and daily excess returns | Co-movement |
| `contrib_intangible_value` | 2 | 189,726 | 2018-12-31 | Researcher-contributed data set | - |
| `contrib_kpss` | 2 | 5,900,610 | 2019-09-26 | Contributed: patents linked to firms | Relatedness |
| `contrib_liva` | 1 | 531,795 | - | Researcher-contributed data set | - |
| `contrib_patent_firm_link` | 2 | 9,125,420 | - | Contributed: patents linked to firms | Relatedness |
| `contrib_shale` | 2 | 20,617 | 2019-08-01 | Researcher-contributed data set | - |
| `crsp` | 104 | views, no count | 2026-09-30 | CRSP, the umbrella views over the stock product | Co-movement, Prices (in use) |
| `crsp_a_stock` | 95 | 1,238,773,192 | 2025-12-31 | CRSP US stock, annual update: daily and monthly prices, returns, delistings, distributions | Co-movement, Prices (in use) |
| `crsp_q_indexhist` | 11 | 300,031,826 | 2026-09-30 | CRSP market indexes, intraday and end-of-day history (cap, value/growth, sector, ESG) | Co-movement |
| `crspsamp` | 63 | views, no count | 2025-09-30 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `crspsamp_all` | 47 | 1,676,070 | 2025-09-30 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `crspsamp_mf` | 16 | 21,753,201 | 2006-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `csmsamp_all` | 7 | 62,697 | 2019-01-08 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `djones` | 2 | views, no count | 2008-06-19 | Small legacy data set | - |
| `djones_all` | 2 | 30,502 | 2008-06-19 | Small legacy data set | - |
| `dmef` | 4 | views, no count | 1992-11-30 | Small legacy data set | - |
| `dmef_all` | 4 | 403,567 | 1992-11-30 | Small legacy data set | - |
| `doe` | 2 | views, no count | 2005-08-01 | Small legacy data set | - |
| `doe_all` | 2 | 7,730,012 | 2002-11-30 | Small legacy data set | - |
| `etfg_samp` | 4 | 91,269 | 2021-12-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `etfgsamp` | 4 | views, no count | 2021-12-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `execcomp` | 15 | views, no count | 2026-10-26 | ExecuComp: executive and director pay | - |
| `factsamp_all` | 28 | 492,707 | 2013-06-28 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `factsamp_revere` | 12 | 1,610,906 | 2015-05-11 | FactSet Revere SAMPLE, frozen in May 2015: relationships (customer, supplier, competitor), sectors, geographic revenue | format reference only |
| `ff` | 12 | views, no count | 2026-09-30 | Fama-French factors and portfolios, industry definitions | Co-movement |
| `ff_all` | 12 | 74,858 | 2026-09-30 | Fama-French factors and portfolios, industry definitions | Co-movement |
| `fisdsamp` | 9 | views, no count | 2011-04-18 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `fisdsamp_all` | 9 | 124,611 | 2011-04-18 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `fjc` | 7 | views, no count | 2026-06-30 | Federal Judicial Center: federal court cases, with a WRDS link of parties to gvkey | Relatedness (lawsuits between firms) |
| `fjc_linking` | 3 | 181,635 | 2024-12-12 | Federal Judicial Center: federal court cases, with a WRDS link of parties to gvkey | Relatedness (lawsuits between firms) |
| `fjc_litigation` | 4 | 61,970,780 | 2026-06-30 | Federal Judicial Center: federal court cases, with a WRDS link of parties to gvkey | Relatedness (lawsuits between firms) |
| `frb` | 4 | views, no count | 2025-02-28 | Federal Reserve Board: interest rates and FX | - |
| `frb_all` | 4 | 41,962 | 2025-02-28 | Federal Reserve Board: interest rates and FX | - |
| `fssamp` | 40 | views, no count | 2015-05-11 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ftsesamp` | 3 | views, no count | 2017-09-29 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ftsesamp_russell_us` | 3 | 45,411 | 2017-09-29 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `gutenberg` | 1 | 3,020 | - | Reference / technical table | - |
| `hfrsamp` | 7 | views, no count | 2011-09-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `hfrsamp_hfrdb` | 7 | 14,019 | 2011-09-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ibessamp_kpi` | 9 | 676,954 | 2020-12-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ifgrsamp` | 4 | views, no count | - | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `ims_obp_trial` | 2 | 50 | 2016-11-03 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `imssamp` | 2 | views, no count | 2016-11-03 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `infasamp` | 5 | views, no count | 2025-03-24 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `infogroupsamp_business` | 3 | 8,510 | - | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `infogroupsamp_residential` | 1 | 100 | - | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `infraclear_samp` | 5 | 45,321 | 2025-03-24 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `insdsamp` | 17 | views, no count | 2023-09-29 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `iri` | 15 | views, no count | - | Small legacy data set | - |
| `iri_all` | 15 | 203,902 | - | Small legacy data set | - |
| `iss` | 6 | views, no count | 2026-09-30 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `iss_climate_emissions` | 1 | 121,357 | - | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `iss_directors_global` | 5 | 14,377,979 | 2026-09-30 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `iss_va_mf` | 5 | 238,572,616 | - | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `iss_va_shareholder` | 3 | 20,867 | 2025-12-29 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `iss_va_vote_global` | 3 | 3,987,694 | 2025-12-31 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `iss_va_vote_us` | 3 | 887,341 | 2025-12-21 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `kpisamp` | 9 | views, no count | 2020-12-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `macrofin` | 24 | views, no count | 2019-12-31 | Macro-finance factors and portfolios (q-factors), commodities and FX | Co-movement |
| `macrofin_comm_trade` | 24 | 502,026 | 2019-12-31 | Macro-finance factors and portfolios (q-factors), commodities and FX | Co-movement |
| `midas` | 1 | views, no count | 2025-12-31 | SEC MIDAS: daily market-structure measures per security | - |
| `morningstarsamp_cisdm` | 2 | 11,750 | 2013-08-13 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `mpsych_sample` | 1 | 434,390 | 2024-10-20 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `mrktsamp` | 20 | views, no count | 2026-04-24 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `mrktsamp_cds` | 1 | 113,640 | 2011-03-21 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `mrktsamp_cdx` | 2 | 1,879 | 2021-05-27 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `mrktsamp_msf` | 4 | 146,377 | 2011-03-21 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `mrktsamp_red` | 13 | 200 | 2026-04-24 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `msci_climate_samp` | 16 | 575 | 2025-05-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `msci_common_samp` | 3 | 15,223 | 2026-04-30 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `msci_esg_samp` | 12 | 4,227 | 2024-06-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `mscicoms` | 3 | views, no count | 2026-04-30 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `mscicsmp` | 16 | views, no count | 2025-05-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `msciesmp` | 12 | views, no count | 2024-06-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `msrb` | 3 | views, no count | 2026-06-30 | MSRB: municipal bond trades | - |
| `msrb_all` | 3 | 224,591,547 | 2026-06-30 | MSRB: municipal bond trades | - |
| `msrbsamp` | 1 | views, no count | 2015-04-07 | MSRB: municipal bond trades | - |
| `msrbsamp_all` | 1 | 84,163 | 2015-04-07 | MSRB: municipal bond trades | - |
| `niq_samp` | 6 | 2,143 | 2026-08-22 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `omtrial` | 24 | views, no count | 2019-08-12 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `optionmsamp_europe` | 12 | 38,861 | 2018-12-21 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `optionmsamp_us` | 12 | 39,775 | 2019-08-12 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `otc` | 1 | views, no count | 2026-10-20 | OTC Markets: end-of-day quotes of over-the-counter securities | - |
| `otc_endofday` | 1 | 77,794,656 | - | OTC Markets: end-of-day quotes of over-the-counter securities | - |
| `panjiva_samp` | 4 | 2,855,156 | 2026-03-19 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `phlx` | 2 | views, no count | 1998-01-28 | Small legacy data set | - |
| `phlx_all` | 2 | 492,877 | 1998-01-28 | Small legacy data set | - |
| `pitchsmp` | 71 | 7,100 | 2026-08-05 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `pnjvasmp` | 4 | views, no count | 2026-03-19 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `preqsamp` | 11 | views, no count | 2019-08-02 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `preqsamp_all` | 11 | 73,297 | 2019-08-02 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `public` | 13 | views, no count | 2026-11-19 | WRDS public reference tables | - |
| `public_all` | 11 | 2,626 | - | WRDS public reference tables | - |
| `pwt` | 7 | views, no count | - | Penn World Table: country macro data | - |
| `pwt_all` | 7 | 78,081 | - | Penn World Table: country macro data | - |
| `ravenpack_trial` | 8 | 3,037,118 | 2020-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `reprisk_sample` | 11 | 2,613 | 2021-01-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `repsamp` | 11 | views, no count | 2021-01-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `revelio_samp` | 21 | 85,564,446 | 2026-05-08 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `revsamp` | 21 | views, no count | 2026-05-08 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `risk` | 20 | views, no count | 2025-12-31 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `risk_directors` | 5 | 486,257 | 2025-07-15 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `risk_proposals` | 3 | 39,414 | 2025-12-16 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `risk_votes` | 1 | 21,042 | 2006-11-02 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `risksamp` | 27 | views, no count | 2025-11-05 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `risksamp_all` | 27 | 34,187 | 2025-11-05 | ISS / RiskMetrics: directors, governance, shareholder proposals and votes | - |
| `rpnasamp` | 8 | views, no count | 2020-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `rq_all` | 1 | 52,779 | - | Small legacy data set | - |
| `rstat_samp` | 1 | 13 | 2021-03-23 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `rstatsmp` | 1 | views, no count | 2021-03-23 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `sdcsamp` | 16 | views, no count | 2024-02-12 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `secsamp` | 20 | views, no count | 2026-08-03 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `secsamp_all` | 20 | 3,458,469 | 2026-08-03 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `shvlsamp` | 2 | views, no count | 2020-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `snapsamp` | 10 | views, no count | 2015-04-28 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `snlsamp` | 4 | views, no count | 2017-09-30 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `snlsamp_fig` | 4 | 41,384 | 2017-09-30 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `sustainalyticssamp_all` | 9 | 171,500 | 2025-09-12 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `sustsamp` | 9 | views, no count | 2025-09-12 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `taqmsamp` | 58 | views, no count | 2009-02-13 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `taqmsamp_all` | 58 | 2,203,115,103 | - | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `taqsamp` | 14 | views, no count | 2008-01-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `taqsamp_all` | 14 | 2,174,649,690 | 2008-01-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `totalq` | 1 | views, no count | 2025-05-31 | Total q: intangible capital and Tobin's q per firm-year | Fundamentals |
| `totalq_all` | 1 | 485,746 | 2025-05-31 | Total q: intangible capital and Tobin's q per firm-year | Fundamentals |
| `tr_sdc_samples` | 12 | 6,227 | 2024-02-12 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trace` | 33 | views, no count | 2026-09-17 | FINRA TRACE: corporate and agency bond trades | - |
| `trace_enhanced` | 15 | 631,486,405 | 2026-09-17 | FINRA TRACE: corporate and agency bond trades | - |
| `trace_standard` | 24 | 497,711,157 | 2026-09-17 | FINRA TRACE: corporate and agency bond trades | - |
| `trcstsmp` | 15 | views, no count | 2021-03-25 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trdbdmismp` | 1 | views, no count | 2023-12-10 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trdbwbsmp` | 8 | views, no count | 2023-12-14 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trdssamp` | 19 | views, no count | 2021-11-18 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `tresgsmp` | 1 | views, no count | 2024-02-03 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp` | 21 | views, no count | 2020-11-15 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_all` | 13 | 22,699 | 2020-11-15 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_db_dmi` | 1 | 100 | 2023-12-10 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_db_wb` | 8 | 15,733 | 2023-12-14 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_ds_eq` | 8 | 624,534 | 2021-05-19 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_dscom` | 3 | 247,740 | 2020-11-18 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_dsecon` | 3 | 5,948,340 | 2009-07-01 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_dsfut` | 5 | 13,829,239 | 2021-11-17 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_esg` | 1 | 1,002 | 2024-02-03 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_sdc_ma` | 3 | 4,539 | 2016-03-19 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_sdc_ni` | 1 | 6,647 | 2016-03-19 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trsamp_worldscope` | 8 | 7,155 | 2015-05-02 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `trucost_samp` | 15 | 5,768 | 2021-03-25 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `twoiq_samp` | 3 | 49,355 | 2016-04-21 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `twoiqsmp` | 3 | views, no count | 2016-04-21 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `wabssamp` | 4 | views, no count | 2020-12-10 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `wappsamp` | 12 | views, no count | 2013-12-31 | WRDS applications sample | - |
| `wenvsmp` | 4 | views, no count | - | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `wmfsmp` | 21 | views, no count | 2019-06-04 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `wrds_abs_samp` | 4 | 23,057,274 | 2020-12-10 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `wrds_environmental_samp` | 4 | 6,621 | - | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `wrds_insiders_samp` | 17 | 13,113 | 2023-09-29 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `wrds_mutualfund_samp` | 21 | 213,887 | 2019-06-04 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `wrds_shortvolume_samp` | 2 | 15,883 | 2020-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `wrdsapps` | 22 | views, no count | 2026-09-24 | WRDS applications, the umbrella views over the wrdsapps_* products | see the products |
| `wrdsapps_eushort` | 1 | 441,393 | 2026-09-24 | WRDS European short positions | - |
| `wrdsapps_evtstudy_int` | 2 | 58,925 | - | WRDS event-study application output | - |
| `wrdsapps_evtstudy_int_ginsight` | 1 | 48 | 2007-01-24 | WRDS event-study application output | - |
| `wrdsapps_evtstudy_us` | 2 | 37,788 | - | WRDS event-study application output | - |
| `wrdsapps_finratio` | 2 | 2,944,444 | 2025-10-31 | WRDS financial ratios: about 70 ratios per firm and month | Fundamentals |
| `wrdsapps_link_comp_eushort` | 1 | 5,409 | - | WRDS link table | - |
| `wrdsapps_link_crsp_bond` | 1 | 383,120 | 2025-12-31 | WRDS link table | - |
| `wrdsapps_link_crsp_factset` | 1 | 343,249 | 2025-12-31 | WRDS link table: CRSP permno to FactSet ids | - |
| `wrdsapps_link_crsp_taq` | 1 | 1,988,835 | 2014-12-31 | WRDS link table | - |
| `wrdsapps_patents` | 3 | 58,631,352 | 2019-12-31 | WRDS US patents: grants, citations, link to gvkey | Relatedness |
| `wrdsapps_plink_exec_boardex` | 2 | 113,096 | - | WRDS link: ExecuComp executives to BoardEx directors | - |
| `wrdsapps_subsidiary` | 2 | 12,306,709 | - | WRDS subsidiary data: Exhibit 21 subsidiaries of each registrant | Value Chain (measured, see below) |
| `wrdsapps_windices` | 3 | 691,796 | 2026-06-26 | WRDS world indices: country portfolios and their constituents | Co-movement |
| `wrdsappssamp_all` | 12 | 12,600,211 | 2013-12-31 | WRDS applications sample | - |
| `wrdssec_midas` | 1 | 21,149,700 | - | SEC MIDAS: daily market-structure measures per security | - |
| `zacksamp` | 17 | views, no count | 2018-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |
| `zacksamp_all` | 17 | 344,516 | 2018-12-31 | Vendor sample or trial of a product we do not subscribe to (small, usually frozen) | - |

## Not checked

- The 37 tables that failed on the scan's own error (26 of them in `ciq`).
- Exact row counts and the date ranges of the 126 largest tables.
- Whether any of the candidates above improves a board: none was scored against the Relatedness exam or tried on
  Value Chain or Co-movement.
- The `_old` schemas.
