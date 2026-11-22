# `module_swing` — a working folder for the Swing Potential board

What we learn about the board and its backtests as we go. One note per session or investigation, named
`YYYY-MM-DD_<slug>.md`, newest first. A note records what was measured and how, so a later reader can re-run it
rather than trust it, and says plainly what it does **not** claim.

| note | what it covers |
|---|---|
| [2026-11-22_rules-and-first-backtest.md](2026-11-22_rules-and-first-backtest.md) | The four gates and their thresholds, the card filter, how quality is scored and sorted, the #1331 replay method, the #1266 verdict, and the eight defects found in that replay |

## The one thing to read before trusting a Swing backtest number

A replay that does not apply the board's **card filter** — `evaluate_direction` passing **and** at least one
method passing (`pipeline.py:158-170`) — is measuring the whole scored market, not the board. On the card
population the quality score's 12-week rank IC falls from 0.058 to **0.009**. Most of what looks like signal in
an unfiltered replay is "gate passers beat non-passers", which the board already filters on.
