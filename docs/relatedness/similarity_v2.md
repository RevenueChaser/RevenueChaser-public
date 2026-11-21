# The served method on the same test, 20 Nov 2026

[`results.md`](results.md) scored the research methods. This file scores the method the board actually serves
today — similarity v2, `module_relatedness.similarity.blended_peer_lists` — on the same test, so the two can be
read against each other. Measured from the stored profiles and vectors, no model call
(`/mnt/project-files/relatedness_method1_exam.json`).

The served score is

> 0.6 x cos(stored profile embedding)
> + 0.25 x (0.6 x Jaccard(customer/supplier types) + 0.4 x shared party name)
> + 0.15 x share of (business_model, channel, stage, sector),

with the sector taken from the spine's `security.sector` (the board's GICS canonical sector).

## The numbers (share of a namer's 10-K rivals in the top k)

| method | 10 | 25 | 30 | 112 |
|---|---|---|---|---|
| similarity v2, scored over the same pool as the word method | 23.5% | 33.2% | 36.3% | 57.2% |
| similarity v2, scored over the whole board universe | 23.3% | 33.0% | 36.1% | 57.1% |
| similarity v2, the stored top-25 lists exactly as served | 23.0% | 32.8% | — | — |
| the word method ([`results.md`](results.md) §1) | 41.7% | — | 54.2% | 67.1% |
| GICS sub-industry mates, random order | 11.8% | — | 26.6% | 42.4% |

So the served method is clearly better than GICS at every k, and clearly worse than the word method — the gap
at k = 10 is 23.5% against 41.7%. Scoring the whole universe instead of the word method's pool costs almost
nothing, and the stored lists match a fresh scoring, so the served lists are not stale.

## Coverage of the measurement

| | |
|---|---|
| CIKs in the word method's pool | 5,020 |
| of those, tickers similarity v2 scores | 4,967 |
| board-universe tickers scored | 5,066 |
| naming companies scored | 1,172 |
| profiles with status ok | 5,111 |
| stored vectors | 5,110 |
| stored list length | 25 |

The test, its limits and what it cannot say are in [`results.md`](results.md) — it is recall only, and the
namers are 22% of the universe and heavy in pharma.
