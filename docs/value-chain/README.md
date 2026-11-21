# Value Chain measurements, November 2026

What this folder is: the record of the measurements the Value Chain board was decided on. Every number names
its date, its sample and the file or issue it was measured in. Nothing here is code, and nothing here is a plan
(see AGENTS.md: a dated work order does not belong in `docs/`).

Read in this order:

| file | what it holds |
|---|---|
| [`edge_census.md`](edge_census.md) | the precision of the profile edges: the two 200-edge censuses of 20 Nov 2026 and avo's counting rule |
| [`name_resolution.md`](name_resolution.md) | how far a Compustat customer name reaches a ticker, before and after the two name fixes, and what is left |
| [`edge_counts.md`](edge_counts.md) | how many edges the board holds and serves, and the SEC reader service's answer inventory behind them |

## The short version

- **The profile edges are good enough to serve.** On a fresh sample of 200 served-candidate edges, drawn after
  the wrong-edge filter of #1142 / PR #1143, 166 of 194 markable edges are right: **85.6%, Wilson 95% lower
  bound 79.9%**, against a gate of 0.70 ([`edge_census.md`](edge_census.md)). `SERVE_PROFILE_EDGES` went on
  with #1159.
- **The counting rule is avo's** (20 Nov 2026 01:26, "Anladım. Yani gevşek okuma bizim için daha mantıklı."):
  a channel, distributor, broker, royalty, collaboration or dependency link counts as right. Both the strict and
  the lenient number are kept for every sample.
- **A Compustat customer name reaches a ticker for a third of the rows.** 5,101 of 19,428 COMPANY-typed
  `customer_share` rows (26.3%) before #1146, 6,589 (33.9%) after it; the residue is measured and classified
  ([`name_resolution.md`](name_resolution.md)).
- **The board's edges are mostly profile edges.** 45,898 profile rows over 4,135 tickers against 753 XBRL rows
  over 409 tickers, read on 21 Nov 2026 before the #894 step 4 deploy ([`edge_counts.md`](edge_counts.md)).

## Where the raw marks are

The mark files are avo's own and the measuring threads' output, not repository data:
`/mnt/project-files/value-chain-census/` (`marks.json`, `marks_v2.json`, `unresolved_200_marks.json`,
`avo_20.md`, `avo_20_v2.md`) and `/mnt/project-files/customer_share_company_type_match.json`,
`customer_share_name_match.json`, `subsidiary_headroom.json`, `diag.json`. They are kept there; this folder
holds the numbers.
