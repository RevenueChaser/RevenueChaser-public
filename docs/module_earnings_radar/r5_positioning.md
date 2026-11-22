# R5 — Positioning & Short Squeeze

**Weight:** 0 — R5 is a **tag**, never a direction vote (`docs/module_earnings_radar/redesign.md` R5: "R5 vote: NONE").
It never opens R4's OPTIONS gate and the drawer shows no signed score for it.
**Sources:** Unusual Whales `/stock/{ticker}/flow-recent` (option prints) · FINRA settlement short interest and
days to cover · IBKR borrow fee, both from the ownership store (`module_earnings_radar/store_reads.short_interest`).
**Files:** `module_earnings_radar/rules/rule5_positioning.py` · the print slice `module_earnings_radar/lean.py`

## What it measures

Who is positioned how. Two independent components, **at least one of which must be present** or the rule is
`unavailable` (score `None`, never a 0 fill):

1. **Institutional lean** — which side of the quote the big prints went off on.
2. **Squeeze tag** — is there fuel for a squeeze in the short book: `none` or `fuel`, no number.

> Retail-call euphoria is **not** read here. The same `retail_call / (retail_call + inst_call) > 65%` share is R8's
> job; reading it in both doubled one signal.

## The lean

**Side, not buckets** (`core/option_prints.py`, `aggregate_flow`): bullish = ask-side calls + bid-side puts,
bearish = bid-side calls + ask-side puts, **mid dropped**. Institutional = size ≥ 10 **and** premium ≥ `$10k`
(`INST_PRINT_MIN_PREMIUM`). A multi-leg or stock-tied package is left out of the lean math and, when material,
tagged `package-risk`. No print carried a side → no lean (absent, never neutral).

```
score += 20 × inst_lean_net / (inst_bull_side + inst_bear_side)
|inst_lean_net| < $25k (INST_FLOW_MIN_NET) → Thin: present, no lean
```

### The prints the lean reads (#256)

`flow-recent` cannot slice itself, so the slice is local (`module_earnings_radar/lean.py`, no extra request —
the same answer the card's tape buckets and R8 read whole):

| Filter | Cut | Missing figure |
|---|---|---|
| Window | the newest `R5_LEAN_SESSIONS` = **3** sessions the tape served | a print with no timestamp is kept |
| Strike band | `spot × (1 ± expected_move × R5_LEAN_BAND_SLACK)`, slack **1.5** | no spot or no expected move keeps every strike |
| Expiry | from the report day out to `R5_LEAN_EXPIRY_DAYS` = **45** days after it | no earnings date, or no expiry on the print, keeps it |

The newest print sets the window, not the clock, so a Fetch of a past day slices the same way as tonight's.

## The squeeze tag

`none` / `fuel` from the short interest or the borrow fee (`redesign.md` R5: "`none` / `fuel` from `si_float` or
`fee_rate`. **No Z ladder. Low SI ≠ bearish**"):

| Condition | Tag |
|---|---|
| SI ≥ `R5_FUEL_SI_PCT` = **20%** of float, or borrow fee ≥ `R5_FUEL_FEE_PCT` = **10%** a year | `fuel` |
| both below | `none` |
| neither figure stored | the component is **missing**, not `none` |

**Neither tag scores a point.** There is no utilization figure: UW serves none and the parser never derives one
(#250). Days to cover is shown in the drawer's metrics and is not part of the tag, because it rests on the same
twice-monthly FINRA count. The short interest reason names FINRA's settlement day, since the figure can be weeks
old (#287); a fee-only read does not, because the fee is IBKR's own, of today. Where no float is stored the
percent is of the shares outstanding and the reason says so.

The peer Z ladder that scored +40 / +25 / +15 above peer Z 3 / 2 / 1 and **−10** below −1 is gone with #256: the
−10 made a quiet short book bearish, which the design rules out, and the Z compared borrow fees across names whose
float and listing age differ.

## Minimum signal gate

R5 needs at least one of {lean, squeeze}. Neither → `unavailable`, never a neutral 0.

## Coverage

`coverage = present / 2` over {lean, squeeze} — 0.5 or 1.0. A field present makes its component present with score
0, not missing (`redesign.md` R5 Coverage). Coverage feeds composite confidence; since R5's weight is 0 it moves no
direction score.

## Interpretation

| Component | Reads |
|---|---|
| Lean | ask-side call / bid-side put premium against the other side, over the slice above |
| Squeeze | `fuel` = room for a short-driven move; `none` = no fuel, and **not** a bearish read |
