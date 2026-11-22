# Decided, open, next

## Decided by avo (17-18 Nov 2026)

- The board computes **relatedness**, not themes: companies that do the same business, from SEC forms, US only,
  refreshed monthly after the Sunday scoring. Its unit of display is the *Related group / related companies*.
- "Same business" = rivals selling the same product. Supplier-customer stays with Value Chain.
- A company can relate through several businesses, each with a strength: **purity** (the line's share of the
  company's revenue) and **weight** (the line's share of the group's revenue). Example given: Amazon is 18% cloud
  by revenue and must still be the largest cloud name.
- No hand-filled values: every list and threshold has a source or is put to avo as a decision.
- Thematic-fund themes are the ETF lane's list. Here they are a **test only**: issuer theme names are compared
  with what the board finds, never used as input (spine `etf_theme.theme`, 9 funds at the time of writing).
- Neither of the two old theme runs is cut over.
- Put on the board **everything found so far**: the related-companies list and each company's business lines with
  revenue shares (18 Nov, 23:39).
- LLM descriptions of business lines continue after the board work.

## What to build next (not started)

1. **Related companies per company.** The word method's nearest companies with their score, monthly. Beside it,
   the rivals the company names itself and the companies that name it (5,159 pairs today), marked as "named in
   the 10-K" so that a reader can tell the two sources apart.
2. **Business lines per company.** The chosen segment set with each line's share of revenue, its axis and the
   report table it comes from.
3. **Storage.** Tables in the Relatedness store with a stable key and a list version; most likely a
   `_SCHEMA_VERSION` bump, which is its own PR with a store checkpoint before the merge.
4. **The job.** The word method needs the business sections of about 5,000 companies (reading them took 5-10
   minutes, the similarity 90 seconds, under 3 GB). The 5,159-pair list needs about 4,300 DeepSeek Flash calls
   (23 minutes, 3.7 M tokens) when the 10-Ks change, with answers cached on the passage text.
5. **Board.** The "Themed" label on the cards and the Theme facet hidden by #953 no longer have groups behind
   them. Either they are removed, or they show "has related companies". The watch-list bookmark icon moves to the
   left of the ticker in the focal panel title (`module_relatedness/report.py`, the design rule of
   `docs/dashboard_ui.md` 2c).

## Waiting on avo

- **How many related companies to show**, and whether to cut by a score floor. No source for either number.
- **The segment-set rule's "10 companies"** for a common geographic name (`method.md` §3). No source.
- **Which set when a company has several usable ones** (607 companies; Disney: three segments or nine revenue
  types). The test could not choose. The scratch rule prefers the business axis.
- **Line descriptions by LLM** (about 5,700 calls a month for +2.6 points): whether to keep, after the excerpt step
  is fixed for abbreviations such as "AWS".
- **Groups.** Nothing in this work produced fixed groups that beat GICS. The lists are per company. Whether the
  board needs named groups at all is open.

## Known limits of what was measured

- One test, recall only, from 22% of the companies, heavy in pharma. No per-sector table for the word method.
- The word method is company-level. For a company of many businesses it is weak (Amazon).
- The named-rival list has unresolved names (10,132 of 16,019 rows), some of them universe companies under brand
  or former names; 3 of 30 audited prefix matches were wrong.
- LLM outputs were checked by the literal guard (rivals) or not at all (the line and company sentences).
- USD cost of the DeepSeek runs was not measured; token counts are in `reproduce.md`.
- The 25% word cut and the three-letter minimum are the published or plain defaults, not tuned on our data.
- Foreign filers: 20-F filers are in the universe and carry segment rows and business sections; they were not
  looked at apart.
