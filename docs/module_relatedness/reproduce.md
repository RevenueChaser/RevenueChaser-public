# Reproduce

Nothing below writes to a store. Every script reads the serving layer through `rcdata.read` with
`RC_STORE_AUTO_ENSURE=0`, and was run on homesrv under `systemd-run --user --scope -p MemoryMax=3G`. Research
scripts are not kept in this repository (`CLAUDE.md`, "Research scripts"); they are archived in the private
coordinator repository under `ref/relatedness-research-2026-11/`, with the small LLM outputs. The scratch files are
on homesrv under `/srv/life/work/step0` ... `step6`; that tree is scratch and may be cleaned.

## Inputs

| input | where | note |
|---|---|---|
| universe | `core.universe.classification_universe(operating_only=...)` | 5,352 tickers, 5,308 companies, as of 17 Nov 2026 |
| business sections | `rcdata.read.filing_texts(ciks, "business")` | newest annual report per company; 5,039 companies |
| whole reports | `rcdata.read.filing_texts(ciks, "whole")` | about 500 KB each; reading 2,500 takes about 70 minutes |
| segment revenue | `segment_revenue` (fundamentals serving version 4) | `report_tables` after #1050 and #1068 |
| total revenue | `fundamental_fact`, field `revenue`, annual, not preliminary | |
| GICS | spine `security`: `gsector`, `ggroup`, `gind`, `gsubind` | |

## Steps, in the order run

| step | script (archive name) | output | run time | model calls |
|---|---|---|---|---|
| segment coverage and sums | `step0/measure_a.py` | printed | 1 min | none |
| Competition passages, all companies | `step1/cut.py` | `passages-all.json` (4,301 passages) | 8 min | none |
| named rivals | `step1/extract_all.py`, `analyse_all.py` | `extracted-all-{1,2}.json`, `rows-all.json` | 23 min | 4,301 DeepSeek Flash; 2.24 M tokens in, 1.47 M out |
| line table, flat rule | `step2/lines_table.py` | `lines-table.json` | 4 min | none |
| linkbase prototype | `step2/proto_roles.py` | printed | 2 min, 160 SEC requests | none |
| texts for the comparison | `step3/prep.py` | `texts-full.jsonl.gz`, `texts-units.json` | 6-10 min | none |
| word method and leak checks | `step3/trial_b.py`, `trial_b_nc.py`, `trial_b_nonames.py` | `simB*.npy` | 90 s each | none |
| company sentences | `step3/trial_a_llm.py` | `sells-{1,2}.json` | 22 min | 6,823 DeepSeek Flash; 3.58 M in, 0.26 M out |
| the comparison table | `step3/compare.py` with `evalkit.py` | `compare.json` | 8 min | none (local embedding) |
| line level, Item 1 texts | `step4/lines_v3.py`, `trial_lines_v3.py` | `lines-v3.json` | 8 + 10 min | none |
| line level, whole-report texts | `step5/extract_whole.py`, `trial_lines_v4.py` | `lines-v4.json` | 70 + 15 min | none |
| line sentences | `step6/lines_v5.py`, `deepseek_lines.py`, `eval_lines.py` | `lines-v5.json`, `line-sells-deepseek.jsonl` | 70 + 25 + 6 min | 5,689 DeepSeek Flash; 3.29 M in, 0.19 M out |

DeepSeek goes through the LiteLLM gate with the board's key (`life-with-keys rc-llm -- <venv python> script`), at
most 3,500 calls per wrapper run, `use_cache=False` so nothing is written to `llm_cache`, and only in the off-peak
window (the provider refuses in peak hours). The local embedding model is the board's
(`module_relatedness.embeddings`, `BAAI/bge-small-en-v1.5`); embed in batches of 8-32, a batch of 256 long texts
exceeds 3 GB.

## The test kit

`step3/evalkit.py`: `load()` returns GICS per company and the `same_product` universe pairs of `rows-all.json`;
`recall_at(S, companies, pairs, ks)` is the score of `results.md`; `company_from_units` turns a unit-by-unit
similarity into company-by-company by the closest pair.

## Reviews

Each step's plan was reviewed by a second model before it ran (Grok, through the xReview tool, with a Claude
answer): the two theme runs, the exposure plan, the named-rival step, the line step, the line-level trial. Their
texts and the running plan with every measurement are in the coordinator repository
(`plans/2026-11-17_2220_revenuechaser_relatedness-theme-exposure-plan.md`, sections 15-28, and `reviews/`).
