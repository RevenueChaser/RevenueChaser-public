# Unusual Whales migration — working folder

Why: avo's Whale Bundle Basic renews **9 December 2026**, so every decision has to be made **before 8 December
2026**. This folder is the evidence and the plan for leaving, or re-sizing, Unusual Whales (UW).

Written 21 November 2026 against `alsanvolkan/revenuechaser-public` `main` = `b97c1a4`. Every code claim below
carries a `file:line` from that tree; every price carries the page it was read from and the time it was read.
Anything unverified says so in the line itself.

| File | What it holds |
|---|---|
| [`01_dependency_inventory.md`](01_dependency_inventory.md) | Task 1 — every place the code depends on UW, by need, dataset, endpoint and board |
| [`02_provider_replacement.md`](02_provider_replacement.md) | Task 2 — each dependency marked fully / partly / not replaceable, and by what |
| [`03_options_track.md`](03_options_track.md) | Task 3 — the options track in avo's three layers: raw tape, sweep/block detection, GEX |
| [`04_existing_work.md`](04_existing_work.md) | Task 4 — what already exists here and in Fincept Terminal that can be reused |
| [`05_migration_plan.md`](05_migration_plan.md) | Task 2.2 + 5 — the sequenced plan, effort, V2 sync points, the decisions only avo can make |
| [`06_risk_register.md`](06_risk_register.md) | Task 5 — data quality, latency, cost, rate limits, licence and redistribution |
| `ui/` | Task 2.1 — the UW web-interface survey, written by the thread "Explore UW dashboard and screenshot it" |

## Rules this folder was written under

- **No live UW API request was made** from this work; the quota is not burned. UW's own published path list
  (241 paths, read from `GET https://api.unusualwhales.com/api/openapi` on 21 Nov 2026 12:59 UTC by the UI thread)
  is in `ui/public_api_paths.txt`.
- No endpoint is named here unless the code names it. No price is quoted here unless the vendor's own page was
  read today, or the line says the number is unverified.
