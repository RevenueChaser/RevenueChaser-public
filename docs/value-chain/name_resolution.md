# How far a customer name reaches a ticker, 19-20 Nov 2026

`module_value_chain/aliases.resolve` names a counterparty from the hand-kept `ALIASES` table and then from the
spine's own registrant names (`aliases.spine_names`). There is no WRDS customer-to-gvkey table on the layer, so
the written name is all there is. These are the measurements of how far that gets, read-only against the live
store.

## Compustat segment customers (`customer_share`, COMPANY-typed rows)

Measured 19 Nov 2026 (`/mnt/project-files/customer_share_company_type_match.json`), then again after PR #1146:

| | candidate labels | resolved labels | candidate rows | resolved rows | rate (rows) | tickers |
|---|---|---|---|---|---|---|
| before #1146 | 4,984 | 621 | 19,428 | 5,101 | **26.3%** | 499 |
| after #1146 | — | +142 | 19,428 | 6,589 | **33.9%** | — |

PR #1146 took the two certain classes of #1145 — a name two spine rows share (one issuer's several listed
lines) and a legal form spelled differently (`Home Depot Inc. (The)`, `Lowe's Cos Inc`, `Eli Lilly and Co`) —
and all 142 newly resolved labels were checked by hand: 141 right, 1 doubtful.

Over the whole `wrds/segments` table, not only the COMPANY type
(`/mnt/project-files/customer_share_name_match.json`, 20 Nov 2026): 85,545 rows, 9,197 distinct labels, 633
candidate labels resolved, 5,180 rows (7.3% of rows, 7% of labels), 508 distinct tickers. The SEC-side table
(`sec/filings`) in the same measurement: 6,094 rows, 1,576 labels, 138 resolved labels, 284 rows (11.2%).

## What is left unresolved, and why

Measured and **not** worth a change (19-20 Nov 2026): `strict_blocked` is 14 labels over 37 rows (`CGI Group`,
`Compass Group`, `Cigna`), and `not_candidate` is 6 labels over 17 rows of brands written in lower case
(`lululemon`, `salesforce.com`) — that second rule is what killed four of the five wrong tickers of the first
edge census.

A sample of 200 of the 4,223 still-missing COMPANY labels (`unresolved_200_marks.json`, judged from the label
and the spine names only, no filing read):

| mark | labels |
|---|---|
| not a listed US company at all | 158 |
| a subsidiary of a listed parent | 23 |
| a listed company we should have matched | 12 |
| doubtful | 7 |

So about four fifths of the residue is not reachable in principle, and the reachable part is mostly
subsidiaries — which is what #1156 measured next.

## Subsidiary headroom (Exhibit 21), 20 Nov 2026

`/mnt/project-files/subsidiary_headroom.json`: of 4,227 still-unresolved customer labels, 222 match a
subsidiary named in some registrant's SEC Exhibit 21 (1,631 rows in total).

| kind | labels | rows |
|---|---|---|
| one current parent in the spine | **92** | **365** |
| parent in the spine, only old filings | 57 | 259 |
| parent not in our spine | 71 | 250 |
| several current parents | 2 | 5 |

Only the first kind is safe to add — one parent, currently filing, on our spine — and that is the 92 avo asked
for on 20 Nov 2026 02:56 ("Edges ve 92 yan kuruluş eşleşmesini alalım.", #1156).

## Known follow-ups with their measured size (#1145, PR #1146)

- **Former names, 195 rows**: `Wal-Mart Stores Inc` (89 + 34 + 23 rows across three spellings) and
  `AmerisourceBergen Corp` (49) are the same CIK as WMT and COR under an earlier name. Waits on the SELECT test
  for WRDS `wrdsapps_link_supplychain.seglink`, which would make a second hand-kept table dead code.
- **`SoftBank Corp` → SFTBF, 1 row**: a label carrying no name word matches a registrant that has one; the
  mirror of #1142's rule would fix it.
- **An off-Tier-A foreign company takes its ordinary OTC line, not its ADR** (`SoftBank Group Corp` → SFTBF
  rather than SFTBY, `PetroChina Company Limited` → PCCYF): about 25 rows, same company either way.
