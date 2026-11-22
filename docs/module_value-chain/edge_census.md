# Profile edge census, 20 Nov 2026

The question: of the customer and supplier edges the board would serve from a company profile, what share is
right? An edge is read against the filing it was written from — the quoted sentence must say that the filer
stands in that relation to that company, and the ticker must be that company.

## The counting rule (avo, 20 Nov 2026 01:26)

> "Anladım. Yani gevşek okuma bizim için daha mantıklı."

A channel, distributor, broker, royalty, collaboration or dependency link counts as **right** (the lenient
rule). The strict rule counts only a direct buy or sell. Both numbers are kept for the first sample; the second
was marked lenient from the start. The gate of the Value Chain plan (§6) is a Wilson 95% lower bound at or
above **0.70**.

## Sample 1 — 200 edges, before the wrong-edge filter

Drawn from the served-candidate edges, read against the filings; marks in
`/mnt/project-files/value-chain-census/marks.json`. 195 markable (5 quotes not found in the document, 5
documents not found).

| | n | right | doubtful | wrong | strict | strict 95% LB | lenient | lenient 95% LB |
|---|---|---|---|---|---|---|---|---|
| all | 195 | 143 | 24 | 28 | 73.3% | 66.7% | 85.6% | 80.0% |
| customer | 98 | 71 | 12 | 15 | 72.4% | 62.9% | 84.7% | 76.3% |
| supplier | 97 | 72 | 12 | 13 | 74.2% | 64.7% | 86.6% | 78.4% |

The 24 doubtful rows are what the lenient rule turns into right: 11 channel or distributor, 9 collaboration,
4 royalty.

The 28 wrong rows, by cause — this list is what #1142 / PR #1143 was built from:

| cause | rows |
|---|---|
| a partner, landlord, lender or joint venture labelled customer or supplier | 9 |
| the named company deals with a third party, not with the filer | 7 |
| the name matched the wrong listed company | 5 |
| a prospect, not a counterparty today | 3 |
| an example in a sentence about the market | 2 |
| the direction reversed | 2 |

The five wrong tickers were "employers" → EIG, "Orion Corporation" → ORN, "STEMCELL Technologies" → ISCO,
"Rafael Technologies" → RFL, "Samsung SDI" → SSNLF (`module_value_chain/aliases.py`).

**avo marked 20 of these rows himself** (`avo_20.md`, his verdicts in the `avo_pick` list of `marks.json`):
18 agreed with the thread's mark, 0 hard disagreements.

## Sample 2 — a fresh 200, after the filter (the gate)

Drawn after #1142 / PR #1143 landed, 20 random rows shown to avo as well (`avo_20_v2.md`, seed 20261122),
marks in `marks_v2.json`; lenient rule. 194 markable (2 documents not found, 4 quotes unverifiable).

| | right | markable | rate | Wilson 95% LB |
|---|---|---|---|---|
| all | 166 | 194 | 85.6% | **79.9%** |
| customer | 83 | 95 | 87.4% | 79.2% |
| supplier | 83 | 99 | 83.8% | 75.3% |

The 28 wrong rows of this sample: partner 7, wrong ticker 5, example 5, direction reversed 4, historical 3,
third party 3, prospect 1.

**This is the number the switch was flipped on** (#1159): `SERVE_PROFILE_EDGES` went on, and these 194 marks
are the board's Precision card fixture (`module_value_chain/fixtures/labeled_80.json`, 200 rows).

What the board gained with the switch, measured on the live code: **951 → 3,761 pairs** (customer 2,321 +
supplier 1,440); the overlap with the XBRL edges is 7.6%, so nearly all of it is new.

## What the censuses cannot say

Both samples are drawn from the edges the board would **serve**, so they measure precision, never recall: an
edge the profile never wrote cannot show up in them. The counts of what is there are in
[`edge_counts.md`](edge_counts.md), and the reach of the names in [`name_resolution.md`](name_resolution.md).
