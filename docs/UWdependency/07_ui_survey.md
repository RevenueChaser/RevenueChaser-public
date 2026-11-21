# Task 2.1 — what the UW web interface survey adds to the plan

The survey itself is a separate thread's work ("Explore UW dashboard and screenshot it", 21 Nov 2026, in avo's
own logged-in Chrome). Its record is `ui/README.md` (the survey index), `ui/UI-only-features.md` and
`ui/nav-links.md`. **The 681 screenshots and avo's own exported data stay out of this repository** — this tree is
code only, and the watchlist export and alert rules are personal data. They live beside the thread at
`/mnt/project-files/UWdependency/`, folder by folder, each with a `notlar.md` holding the full URL and the
capture time of every shot.

This file is only the part that changes the migration plan.

## 1. Three things exist only inside UW, and they are avo's own

Not data we can re-derive from a provider: **configuration avo typed into UW**.

| What | Where in the survey | State |
|---|---|---|
| Six stock watchlists | `watchlists/` (`avo_stock_watchlists.json`) | **exported** to the project folder |
| Four custom alert rules, with their thresholds | `custom-alerts/` (`notlar.md`, `alert-types_all-29-forms.md`) | **recorded** as text |
| Console habits — which of the 229 commands and which presets | `console/commands_all-229.md` | **recorded** |

Saved Flows is empty, there is no backtest saved and no brokerage account is linked, so there is nothing else to
preserve. This is lane **I** below: it has the same 8 December deadline as everything else, but it is cheap and it
is the one item that cannot be recovered after the plan lapses.

## 2. "highest-volume-contracts" is one table in four places

Console `/moso`, the ticker Overview page, the ticker NOPE page's "Most Active Chains", and the options screener
sorted by volume all show the same ranking (`console/`, `ticker-page/`, `screeners/`). **One chain snapshot that
carries volume reproduces all four.** That is plan A — IBKR plus Cboe — and it needs no tape.

## 3. The split that decides the cost: tape or snapshot

The survey sorts every UW page onto one side of the line in `03_options_track.md`.

**Needs a trade tape with bid/ask side** (so IBKR OPRA or a paid tape, not a chain snapshot): Live Options Flow,
flow alerts, Net Premium, NOPE, delta flow, bullish/bearish premium, the bid/ask volume bars.

**A daily chain snapshot rebuilds**: OI changes, max pain, GEX / vanna / charm by strike and by expiry, the
options grid, highest OI, implied move per expiry.

This is the same conclusion the code analysis reached from the other end, which is the useful part: the only UW
pages that survive losing the tape are the ones layer 3 already covers.

## 4. UW is retiring DEX

A banner on the Delta tab says so (`periscope/`). **Do not rebuild DEX.** `03_options_track.md` lists it under
layer 3 as pure arithmetic, which it is, but it is not worth the lane.

## 5. The free public sources the UW pages sit on

Named per page in the survey, and each one is already a source we hold or can hold: Form 4 for insiders (with the
10b5-1 flag and the stake change, which is what the UW insider page shows), 13F for institutions, FINRA short
volume, SEC fails-to-deliver, House and Senate disclosures, FEC. Nothing here changes the verdicts in
`02_provider_replacement.md`; it confirms them from the UI side.

## 6. Data Downloads: the last 8 trading days, and it is avo's call

`Other > Data Downloads` (`data-downloads/`) offers five daily files for the **last 8 trading days only**. After
8 December 2026 they are gone. A few reference days would be the cheapest possible input for M1 and M3 — real UW
chain and print files to score our own build against, with no API call and no quota burned.

The terms are personal use. **Nothing was downloaded**, by the survey thread or by this one. Taking reference days
is avo's decision, and it is time-boxed by the window, not by the renewal date: a file from 1 December is only
offered until roughly 11 December.

## 7. One plan question is now answered

`05_migration_plan.md` §5 asked whose server "Traders' Pub" is. avo answered on 21 Nov 2026 17:02 Amsterdam: it is
his own server, run with friends, and the UW bot in it runs on the UW API. The remaining Discord unknowns are
whether that bot feed stops when the plan lapses, and how avo wants the window walked — he will explain the
method himself. **Nothing in Discord is touched before that.**
