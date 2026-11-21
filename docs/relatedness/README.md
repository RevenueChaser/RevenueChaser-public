# Relatedness research, November 2026

What this folder is: the record of the work done on 17-18 November 2026 to replace the Relatedness board's "themes"
with something that holds up against a test. Nothing in here is live on a board yet. The numbers were measured on
homesrv against the live serving files and the stored SEC texts; every one of them names its conditions.

Read in this order:

| file | what it holds |
|---|---|
| [`results.md`](results.md) | the test, and every method's number on it, in one place |
| [`method.md`](method.md) | the three parts that work, exactly as run: the word method, the named rivals, the business lines |
| [`dropped.md`](dropped.md) | what was tried and dropped, with the number that dropped it |
| [`open.md`](open.md) | what is decided, what waits on a decision, what to build next, known limits |
| [`reproduce.md`](reproduce.md) | scripts, inputs, outputs, run times, model calls, and where the files are |
| [`similarity_v2.md`](similarity_v2.md) | the method the board serves today, scored on the same test (20 Nov 2026) |
| [`competition_coverage.md`](competition_coverage.md) | who has no Competition passage, by size band (20 Nov 2026) |

## The short version

- **Goal** (avo, 17 Nov 2026): relate companies that do the same business, from SEC filings only, US-listed only.
  "Same business" means rivals that sell the same product; a supplier and its customer are the Value Chain board's
  matter. A company with several businesses relates to others business by business, with a strength.
- **Word list of the project** (avo, 17 Nov): *ETF class* (what a fund is; spine), *ETF theme* (the thematic-fund
  list; watch lists), *Related group* (same-business companies from SEC forms; this board), *Watch list* (avo's own
  lists). "Theme" alone is not used for what this board computes.
- **What works**: the words of each company's 10-K business section, compared company to company
  ([`method.md`](method.md) §1). Its 112 nearest companies hold 67.1% of the rivals a company names in its own 10-K;
  112 GICS sub-industry mates hold 42.4%.
- **What also works**: splitting a company into the business lines its filing reports, with each line's share of
  revenue (§3), now that the builder reads the filing's definition linkbase (#1048, #1066, #1070).
- **What adds a little**: one LLM sentence per business line, added to the word method: 69.7% (§4 of
  [`results.md`](results.md)).
- **What did not work**: fixed groups cut from embeddings or NMF, GICS in front of the text, line texts taken from
  headings or by pattern ([`dropped.md`](dropped.md)).
- **Not built**: any table, job, board element or group name. The old `themes.py` runs (one NMF, one embedding) were
  measured and neither was cut over.
