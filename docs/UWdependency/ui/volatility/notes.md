# Volatility Hub, Radar, Character

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 15.

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `hub2_01_top_vix-term_market-vrp.jpg` | https://unusualwhales.com/volatility | 21.11.2026 16:44:06 |
| `hub2_02_summary_what-options-expect.jpg` | https://unusualwhales.com/volatility | 21.11.2026 16:44:06 |
| `hub2_03_summary_tiles_the-setup.jpg` | https://unusualwhales.com/volatility | 21.11.2026 16:44:06 |
| `hub2_04_history.jpg` | https://unusualwhales.com/volatility?view=history | 21.11.2026 16:44:06 |
| `hub2_05_smiles.jpg` | https://unusualwhales.com/volatility?view=smiles | 21.11.2026 16:44:06 |
| `hub2_06_term.jpg` | https://unusualwhales.com/volatility?view=term | 21.11.2026 16:44:06 |
| `hub2_07_heatmap.jpg` | https://unusualwhales.com/volatility?view=heatmap | 21.11.2026 16:44:06 |
| `hub2_08_advanced.jpg` | https://unusualwhales.com/volatility?view=advanced | 21.11.2026 16:44:06 |
| `hub2_09_info-panel.jpg` | https://unusualwhales.com/volatility?view=advanced | 21.11.2026 16:44:06 |
| `radar2_01_sell-vol-candidates.jpg` | https://unusualwhales.com/volatility-radar | 21.11.2026 16:44:35 |
| `radar2_02_buy-vol-candidates.jpg` | https://unusualwhales.com/volatility-radar | 21.11.2026 16:44:35 |
| `volatility-character_scroll-2.jpg` | https://unusualwhales.com/volatility-character | 21.11.2026 14:54:48 |
| `volatility-character_scroll-3.jpg` | https://unusualwhales.com/volatility-character | 21.11.2026 14:54:48 |
| `volatility-character_scroll-4-bottom.jpg` | https://unusualwhales.com/volatility-character | 21.11.2026 14:55:10 |
| `volatility-character_top.jpg` | https://unusualwhales.com/volatility-character | 21.11.2026 14:54:48 |

## Notes (what the page shows, buttons pressed, nearest API path)

### /volatility-character "Volatility Hub / Character" (2026-11-21 14:54 Amsterdam)
"Ranked by mean-reversion half-life (fastest-reverting first = cleanest premium sells)." Limit 25/50/100/200.
Filters: Ticker search; Character select (any / mean-reverting / moderate / persistent); Half-life min-max; Hurst min-max; Predict. >= ; Obs >= (default 60).
Columns: Ticker, Character, Half-life (d), Hurst (ΔRV), Predict., Obs.
Footnote: "Half-life = AR(1) mean-reversion speed of log realized-vol (trading days). Hurst (ΔRV) = clustering of vol moves (>0.5 = persistent). Predict. = negative entropy of next-day vol direction (higher = more predictable). Admin-only preview."

### /volatility (Volatility Hub) — second pass 21 Nov 2026, every tab
- Top: three link cards (Volatility Radar, Volatility Character, Options Sentiment). VIX Term Structure tile (M1 35.89, M2 30.94, contango ratio -13.79%, 30D trend, "Backwardation"). Market VRP tile ("Buy-vol bias", avg z -2.87, SPY -3.32, QQQ -2.70, IWM -2.60, "200 tickers flagged as short-vol candidates", Open radar). Relative Index Vol (RVX/VIX, VXD/VIX; both empty "—" when visited) with the note "Cross-index vol dislocation (Mack & Sinclair Ch 18)".
- "VIX volatility" block = the same Volatility component each ticker has at /stock/<T>/volatility. Tabs:
  - Summary: "What options expect" sentence (implied move ±% and $ range over 30 days, vs realized), cone chart (price, implied move, 1 SD from IV, range priced a month earlier), hit rate ("closed inside the implied move on 33 of 64 days"), Coming up list (expiries/earnings, Implied / 1 SD toggle), tiles: IV 30d, IV rank · percentile, Realized 30d, IV − RV 30d, IV vs SPY 30d, Move by <expiry>, Earnings (actual vs priced), Put − Call skew 30d (25Δ/10Δ); "The setup": Premium (cheap/rich), Level (low/high), Term (backwardation/contango) with one-line readings.
  - History: metric chips (IV 30d, 1Y range, RV 30d, IV − RV 30d, Vol of vol, Term spread, IV ÷ SPY IV, Price), Quick views, IV/RV window, Range, Earnings markers, Chart height, Range stats panel, Volatility cone 1y.
  - Smiles: Smile by strike / by delta / Risk reversal; Calls & puts; strikes ±30/20/10%; Same expiry / Same DTE; compare vs 1D/3D/1W/1M; Calendar box (sell/buy expiry, net pts, "Open calendar in profit calculator"); Skew by expiry table (ATM, 25Δ RR, 10Δ RR).
  - Term: ATM IV / Implied move / Forward vol; Listed expiries / Constant maturity; wings 10Δ P, 25Δ P, 25Δ C, 10Δ C; range 3M/6M/1Y/All; Earnings premium; Calendar (forward vol between two expiries, back − front IV, forward 1W ago); Expiries table (Expiry, DTE, IV, Move, Δ1W).
  - Heatmap: IV level / Change, vs 1D/3D/1W/1M, Same expiry / Same DTE; grid expiry x delta bucket (10Δ P ... ATM ... 10Δ C) with IV and 1W change; side panel smile and term for the selected cell, "Biggest moves".
  - Advanced: Volatility Context (term structure slope, skew 25Δ, IV vs realized ratio, IV rank/percentile, expiry implied move, market VIX vs VIX3M); Volatility Anomaly Score (0-100 composite of VRP z-score, IV percentile, vol-of-vol, 25Δ skew percentile, regime; vol cone 10/30/60/90/180d); Volatility character (mean-reversion half-life, Hurst of ΔlogRV, direction predictability / neg. entropy, RV observations); Options Positioning Sentiment (VWKS + AVAR score); charts IV vs Realized & IV Rank, Historical Volatility Windows (HV 10/20/30/60/90d), Volatility Cone, Variance Premium Signal (VRP rank, sell zone / stand down), Interpolated IV (implied move for 1/5/7/14/30/60/90/180/365 days).
- Info drawer "Volatility Information": explanatory article; "Notes on the data: IV here is the at-the-money IV, unless a chart says otherwise 'IV' means 30 calendar day IV."
- Inputs needed to rebuild: option chain IV per expiry/strike (delta buckets), daily closes for realized vol, VIX futures M1/M2. Everything shown is derived from those.

### /volatility-radar — second pass
- Tabs: Sell vol candidates / Buy vol candidates. Limit 25/50/100/200. Filter inputs: Ticker search, Score min/max, Inputs ≥, VRP min/max, IV % min/max, VoV % min/max, Skew % min/max, Regime min/max ("Filters apply on Enter or blur").
- Columns: Ticker, Score (sortable), Dir (short/long), VRP, IV %ile, VoV %ile, Skew %ile, Regime, Inputs (n/5).
- Footer definition: "Composite score blends VRP z-score, 1-yr IV percentile, 30-day vol-of-vol percentile, 25Δ skew percentile, and regime score. Sign indicates direction."
- Sell side top on 21 Nov: BITO1 100 (1/5 inputs), SPXW 89, NDXP 89, XSP 89, RUT 88 ... SPY 76, NVDA 76. Buy side: CAR -26, GRPN -26, INFY -27 ...
- Index roots (SPXW, NDXP, XSP, RUT, XND, MXEF, VIXW) are included, not only equities.

