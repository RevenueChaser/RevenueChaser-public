# R8 — Sentiment

**Weight:** 10% of composite direction score
**Source:** UW `/stock/{ticker}/flow-recent` via `aggregate_flow` (size &lt; 10 = retail)
**File:** `module_earnings_radar/rules/rule8_sentiment.py`

## What It Measures (live)

Retail call share as a **momentum** signal. Same size split as R5:

```
retail_share = retail_call_premium / (retail_call_premium + inst_call_premium)
```

| Share | Score |
|-------|:-----:|
| no call premium | unavailable (`None`) |
| ≤ 65% | **0** (available) |
| &gt; 65% | **+20** (not scaled) |

Coverage is 1.0 when a share is present, else 0.

The polarity is the tunable `R8_SIGN` (`+1` momentum, default; `-1` fade/PEAD).
The calibration report (removed with Earnings Radar v2) used to run a
fade-vs-momentum sign sweep; a polarity change is a recorded, human-in-the-loop
tuning step.

## The text half (wired, #1214)

The pipeline also passes the **last reported earnings call**, split into prepared remarks and Q&A, so the
Loughran-McDonald tone terms in `_score_transcripts` score as well. This is what lets R8 vote **negative**: on
retail share alone it can only score +20 or 0.

- **Source:** `alphavantage/earnings_transcripts` → `earnings_transcript` (need `earnings.transcript`), read by
  `store_reads.transcript_halves` and warmed once a run (`pipeline._warm_transcripts`).
- **The split is inferred.** The provider sends a flat list of turns with no prepared-remarks / Q&A field, so the
  boundary is the **first analyst turn** (`rules/transcript_split.py`; measured 21 Nov 2026). A call with no
  analyst turn has no Q&A half, and R8 then scores its single-argument branch rather than a `tone_delta` whose
  "Q&A" is really more prepared remarks.
- **The quarter is the company's fiscal quarter**, which is how the provider labels a call, and the stored call is
  always a **reported** quarter's: the fetch takes its quarters from `earnings_report_history`, so the words can
  never be the coming print's.
- **Coverage climbs day by day.** The provider's free tier allows 25 requests a day (`rcdata/caps.py`) and the
  spine already spends 3, so the builder fetches at most ~22 new calls a day and stops cleanly at the cap. A name
  with no stored call scores exactly as before, which is why partial coverage is the normal state and not a fault.
- **The provider's own per-turn `sentiment` is not read.** The rule measures dictionary rates over our own
  tokenizer; swapping in the provider's number would change what every threshold means, and is its own decision
  with its own measurement.

The thresholds (0.03, 0.02, 0.01) are still the ones written for the literature's transcripts, **not** calibrated
against a measured distribution of these calls. That recalibration waits for enough stored calls to measure.

## Not wired

- **Small-lot share** — would re-count the same size&lt;10 prints already in retail.

Size &lt; 10 is a heuristic, not identity. Shared with R5 on purpose.
