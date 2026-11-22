# The Swing board's rules, and what its first backtest did and did not show

Written 2026-11-22 after #1331's first swing backtest. Code read at RevenueChaser-public `37146a94` for the
replay and `400073ab` for this note; `module_swing_potential/` and `core/tristate.py` are byte-identical between
them, so every citation holds for both. Reviewed by Fable, then Grok xReview for three rounds; both overturned
claims this thread had made, and the corrections are kept below rather than quietly dropped.

## 1. How the board scores

**Pre-filter** (`core/screen_common.py:77-86`), two rules only, both liquidity:

| filter | threshold | drops as |
|---|---|---|
| price | `MIN_PRICE = 5.0` per **share** (`config.py:18`) | `low_price` |
| dollar volume | `MIN_DOLLAR_VOLUME = 250_000` /day, price × average volume | `low_dollar_volume` |

No market-cap filter — the config says so explicitly. Note the live pre-filter reads each name's **newest**
close, not the close of the day being scored, so applied to history it is not point-in-time.

**Four gates.** Every rule is tri-state; an unknown input is never a pass (`core/tristate.py`).

- **Direction (2 rules, both required, mandatory on every card)**: 50-day MA ≥ 200-day MA; 3-month return ≥ 0.
- **Minervini (8 rules shown and counted, 7 decide)**: price above the 150- and 200-day MAs; 150 above 200;
  200-day rising over a month; 50 above 150; price above the 50-day; ≥ 30 % above the 52-week low
  (`ABOVE_52W_LOW = 1.30`); within 25 % of the 52-week high (`WITHIN_52W_HIGH = 0.75`); and **RS Rating ≥ 70**,
  which is *shown and counted into quality but does not decide `passed`* (`screeners.py:92`, #65).
- **Weinstein (5 rules, all required)**: price above the 30-week (150-day) MA; that MA rising; **≥ 98 % of the
  52-week high** (`BREAKOUT_HIGH_PCT = 0.98`); volume ≥ 1.5× the 20-day average on one of the last 5 sessions;
  3-month RS above SPY.
- **Qullamaggie (7 rules, 6 suffice, two of them mandatory)**: **preceding move ≥ 25 %** over 1-3 months
  (*required*); price above the 10- and 20-day EMAs; 10-day EMA above the 20-day; short-term EMAs rising; average
  daily range ≥ 3 %; and **tightening** — the last 10 sessions' mean range below the previous 20's (*required*).

**The card filter** (`pipeline.py:158-170`): a name reaches a card only when **direction passes and at least one
method passes**. This is the single most important line for anyone measuring the board.

**Quality** = `40 × M/8 + 30 × W/5 + 30 × Q/7` over all *known* passes (`ranking.py:51-59`). Watch out:
`ranking.py:52` and `config.py:41` both write the formula as `30 × Q/6`, but the code uses
`Q_RULE_TOTALS["qullamaggie"] = 7` and the gate emits 7 rules. **The comments are wrong by one; the code is
right.**

**Sort**: quality descending, ties broken by momentum = `0.50 × (12-1 momentum) + 0.25 × (52-week proximity) +
0.25 × (6-month consistency)`, each a **cross-sectional percentile over the names scored that day**
(`pipeline.py:143-146`). RS Rating is the same shape: the percentile of the 12-month return versus SPY.

**Which series feeds what** (`indicators.py:129-136`): levels — price, all MAs and EMAs, the 52-week range, ADR,
ATR, volume — come from **nominal** bars (split-adjusted, not dividend-adjusted); returns — daily/weekly/monthly
change, the 1-3 month move, 12-1 momentum, RS versus SPY — come from the **dividend-adjusted** bars. MAs are
plain means of closes including the current session (`_sma`, `:59-63`).

## 2. The #1331 replay: what it is

A two-stage replay re-scores the board at 208 weekly dates (2022-10-04 … 2026-11-18), feeding each date only the
bars up to it, with the live thresholds pinned from the export, and attaches the realized 1/4/12-week forward
return. 943,913 rows, 5,098 distinct tickers, ~4,538 scored per date. Stage 1 is per ticker (91 min single-core);
stage 2 takes the cross-sectional percentiles per date and calls the real gates (105 s).

It calls the board's own `compute_indicators`, `evaluate_*` and `quality_403030`, so it tests the board rather
than a model of it. It refuses rather than guesses: a name with fewer than 260 bars at the date, or whose last
bar is more than 14 days old, is not scored. Unfinished forward windows are null, never 0.

**It is not a portfolio backtest.** No positions, entries, exits, stops, sizing, costs, slippage, equity curve,
drawdown or Sharpe. It produces a dataset — the board's score as of each week plus what each name then did.

Script and the `--ticker-slice` option for running stage 1 on four cores: `RevenueChaser/claude-coordinator`
PR #1215. Report: PR #1216.

## 3. The #1266 verdict: do not adopt Option A

Option A drops two Weinstein rules from that gate's count (denominator 3 instead of 5). Measured with a paired
per-date rank IC difference, Newey-West at 12 lags plus a block bootstrap over contiguous 12-week blocks:

| population | names/date | IC_a | IC_b | B − A | 95 % CI |
|---|---|---|---|---|---|
| whole scored export | 4,505 | 0.0552 | 0.0582 | +0.0030 | [+0.0019, +0.0043] |
| price ≥ 5 | 3,670 | 0.0694 | 0.0729 | +0.0035 | [+0.0023, +0.0050] |
| price ≥ 5 **and** ≥ 1 method | 892 | 0.0026 | 0.0092 | **+0.0066** | **[+0.0020, +0.0127]** |

196 weeks. No pooled interval covers zero; by year on the card-ish population every interval **does** (2023
+0.0089, 2024 +0.0096, 2025 +0.0068, 2026 +0.0018), and 2022 fell below the week threshold and was never
estimated. The advantage is small and no single year establishes it.

**#1266's premise is also wrong on both rules.** `overhead_breakout` tests `within_52w_high_pct >= 0.98` against
Minervini's `>= 0.75` on the **same input** — a stricter, distinct rule, not a restatement. `price_above_30w`
(`price > sma150`) is *implied by*, not equal to, `price_above_150_200` (`price > sma150 AND > sma200`): a name
above the 150 and below the 200 passes the first and fails the second. So dropping them is information loss.

**Option A is not cosmetic**: scores differ on 70.7 % of rows and the top 20 by the board's own key overlaps only
about **41 %** (11.8 of 20 names change per date).

**Why A loses is not identified.** A delete-only variant (`6 × W3`, no reweight) scores D − A = +0.0006 (interval
covers 0) and D − B = −0.0024 on the export, −0.0078 on the card set — so "the deletion costs" and "the
reweighting costs" are both unsupported, and the mechanism stays open.

## 4. What else the data showed

- **Gate passes, 12-week mean minus the equal-weighted universe of the same date**: Minervini **+1.35 pt**
  (141,831 rows), Weinstein +0.52 (13,429), Qullamaggie +0.53 (82,236), **all three +1.04** (2,493), none −0.31
  (686,550). All-three is a *subset* of Minervini, so this is not a horse race — and 2,493 rows over 208 dates
  cannot resolve +1.35 against +1.04.
- **All three gates together**: 2,577 (date, ticker) rows, 1,521 distinct tickers, on 198 of 208 dates, mean
  **13.0 names a date** (median 10, min 1, max 69). Weinstein is the bottleneck at 67.2 names a date against
  Minervini's 716.3 and Qullamaggie's 411.1, out of ~4,538 scored.
- **The universe trailed the index**: equal-weighted, the scored names returned +2.82 % at 12 weeks against SPY's
  +4.69 %. So "no decile beat SPY" is a size-and-weighting fact, not a property of the score. The equal-weighted
  universe of the same date is the comparison that isolates the score — and it has its own biases (it is the
  average of names the board does not show).

## 5. The eight defects found in this replay, all verified

1. **No card filter.** The replay never calls `evaluate_direction` and never applies "≥ 1 method", so it measured
   the whole market: 686,550 of 943,913 rows (72.7 %) pass no method at all.
2. **Nominal SPY baseline** where production reads `basis="adjusted"` (`core/screen_common.py:152,176`).
   Differential, not common: Option A moves `rs_3m_gt_spy` from 6 to 10 points, so it has more exposure to the
   defect than B.
3. **The decile analysis was not reproducible.** `ntile` over a tie-heavy integer score splits ties by physical
   row order: four runs gave 12-week top-minus-bottom spreads of +0.97, +1.03, +1.05, +1.06 and 2022 values from
   −16.26 to −17.68, with the A/B ordering flipping between runs. The biggest single-score group averages 7.5 %
   of a date's names; names tied at the date's maximum average 22.6 under A against 6.3 under B.
4. **`price >= 5` was applicable from the published parquet and never applied** — 19.3 % of rows.
5. **Stock and SPY forward windows do not start on the same day** for a name with gaps: the stock bases on its
   last bar at or before the date (up to 14 days early) and steps on its own index, while SPY steps on SPY's
   calendar from the replay date.
6. **Survivorship sits inside the score**, not only the label: `rs_rating` is a percentile over today's export and
   is counted into quality through `rs_ge_70`.
7. **Analysis arithmetic**: the universe-vs-SPY row is row-weighted while labelled a date mean, its 1w/4w figures
   are conditioned on a finished 12-week window, and the hit-rate SQL counts a null excess as a miss.
8. **Docs defect**: the Qullamaggie denominator (section 1).

## 6. Claims this thread made and withdrew

Kept here because each was reported before it was checked:

- "This data cannot separate A from B" — **wrong**. The paired test was never run; its SE is 0.0006, not 0.006.
- "The top decile has no edge, deciles 7-9 carry the signal" — **withdrawn**, it rested on unstable `ntile`
  deciles, and decile 4 was as high as 7-9 in the same table.
- "Minervini beat all three gates" — **withdrawn**: a subset is not a competitor, and no standard error was computed.
- "The dropped rules carry negative information" and then "positive information" — **both withdrawn**. Demeaning
  the cross-tab by date destroys the gradient; the cell means identify nothing.
- "Ceiling ties degrade the board" — a description of the export, not harm.
- "The equal-weighted universe is the board's benchmark" — withdrawn; it is one comparison with its own biases.

## 7. What a number from this replay cannot tell you

- **No replay row has ever been matched against a live board row.** No Swing Fetch has run since at least
  8 Nov 2026, so there was nothing current to compare. "This is what the board would have said" rests on reading
  the code path.
- The universe is **today's**, for all 208 past dates. The delisted store has never been built, and Compustat's
  index-membership snapshot holds current members only, so no as-of universe is available. Served bars do already
  exist only on days `sec_idhist` says the security was exchange-listed (`wrds_history.py:757-780`, from
  1998-04-01), which makes it less bad than it sounds.
- The thresholds pinned are today's, applied to 2022 — parameter anachronism, not look-ahead, and it applies
  equally to A and B.
- Weekly dates with 4- and 12-week horizons overlap, so about 16 independent 12-week blocks underlie the panel.
  The t values are not significance tests.
- The export predates the #661 price fix, which touches 65 of the replay's tickers — 13,473 of 943,913 rows
  (1.43 %), including 2,755 Minervini-passing rows. Whether that moves B − A is unmeasured.
- Costs, slippage, sizing, capacity and turnover: none of it is here.

## 8. The corrected replay, written and not run

A patched script exists with the adjusted SPY baseline and with `direction_passed`, `methods_passed` and
`on_board` recorded per row — recorded rather than filtered, so the percentiles stay over the whole field as
`pipeline.py:143-146` does and one run answers both "ranks the market" and "ranks the cards". It was smoke-tested
(`on_board` 53 of 1,004 rows on a 447-ticker subset, `direction_passed` 221) and **cancelled on avo's word** part
way through stage 1, because the data itself was the bigger problem. `/work/out2` on the CI box holds its partial
stage 1.
