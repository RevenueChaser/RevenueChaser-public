# UW Console (/console) — all 229 commands, read from the "Commands / FAQ" pane, 21 Nov 2026
Format: `/command [args]` — what the pane says it does. Section counts are the pane's own.

## Syntax & tips (11)
- Historical day or range: add a trade date after the ticker (8/27, 8/27/26, 2026-08-27, 20260827), ranges with two dots (8/25..8/27). Works on every flow command. `/top insw 8/27`
- Asset class, sector or watchlist scope: in place of a ticker use @equity (stocks+ADRs, no index/ETF), @stock, @etf, @index, @adr, @energy, @tech, @consumer_cyclical (join with +), #my_list (stock watchlist by name). `/vtop @equity`
- Filter the tape by watchlist: `/filter #mylist` (stock watchlist tickers or option watchlist contracts); `/filter clear`.
- Option trigger: type a ticker and a contract count (`googl 1000`) to stream that ticker's prints of at least that size; under 100 needs a c (`googl 50c`).
- where clause: `expiry=9/18 · dte<30 · premium>=250k · size>=500 · volume>1000 · oi<200 · strike, price, delta, iv ranges · calls, puts, sweep, floor, cross, otm, opening, opex, multi, single, ask, bid, mid · flex · amer, euro`. `/top googl where premium>=250k and calls and expiry=9/18`
- Sort: `sort=vega | gamma | gross_vega | gross_gamma | gross_notional | prem | size | volume | oi | time`. Definitions: vega = position vega (vega × contracts × 100, per vol point); gamma = dollar gamma per 1% move (gamma × contracts × spot²); gross vega/gamma sum |greek| across every leg; gross notional = contracts × 100 × spot.
- Multi-leg structures rank beside single prints in /top: net Vega, TV (mid of the structure's net market), Edge = (TV − traded) × units × 100.
- Life-To-Date flow history: /chainhist.
- Contract views: /som (side of market, volume by exchange), /volxpx (volume at price), /volxiv (volume at IV), /flow (ten-minute contract flow); each has a [download] link.
- Trade-Alert style prints (Settings): four-line tape with size, contract, price, side, venue, time to the ms, IV and change, screen quote, condition, TV, vega, delta, impact, premium, volume, OI, edge, spot ref.
- IV precision: one decimal.

## Live options flow (25)
- Per-exchange flow, all `[ticker] [date] [where …]`: /amex, /arca, /box, /bxo, /bzx, /c2, /cboe, /edgx, /emld, /gem (GEMX), /ise, /memx, /merc, /miax, /mprl, /nom, /phlx, /sphr
- /cancel — most recent cancelled/modified trades
- /cross — top cross trades; /floor — top floor trades
- /recent — most recent trades (e.g. `/recent nvda 8/27 where sweep`)
- /top — top trades, sweeps and multi-leg structures; market-wide, per ticker, sector, asset class or watchlist; history and where/sort as above
- /vegatop, /vtop — top trades ranked by position vega

## Expirations (18)
- Monthly expiry flow: /nov26 /dec26 /jan27 /feb27 /mar27 /apr27 /may27 /jun27 /jul27 /aug27 /sep27 /oct27 /nov27 /dec27 /jan28 /feb28 /mar28 /apr28

## Greeks & exposure (15)
- /bsoc [ticker] — market-maker greek exposure by strike (API Enterprise)
- /charm, /deltaex, /vanna, /gammaex (spot/daily/strike), /gex (MM gamma exposure by strike), /greeks (full MM greek exposure: spot, gamma, delta, vanna, charm), /spotgamma (GEX/vanna/charm by strike)
- /deltaflow — net delta & vega greek flow
- /details [contract] — Trade Alert's Contract Details: quote with sizes and venues, volume, VWAP, OI change, theoreticals with greeks, expected trading range
- /mmtable, /tgexheatmap — SPX market-maker net GEX heatmap by strike & expiry
- /nope — net options pricing effect
- /optionchain — full chain: strikes, IV, greeks, OI
- /vannacrush — pre-earnings dealer re-hedge lean

## Volatility (25)
- /crashprob (model crash probability), /exchange-vol (options volume by exchange), /fwdvar (forward variance curve), /histskew (risk-reversal skew over time), /ivix (UW implied-vol index), /ivpct, /ivrank, /ivterm, /kurtosis, /oivol (OI vs volatility), /relvol (RVX/VIX & VXD/VIX), /reports (daily digest), /rvol (realized vs implied), /skew (call vs put IV skew), /skewness, /smile, /theo [contract] (theoretical price from the expiry's fitted smile, with edge against the market), /volatility, /volchar, /volradar, /volregime, /volseason (realized vol by weekday / OpEx), /volsurface, /vov, /vrp

## Chains & open interest (16)
- /13fo [ticker] — institutions holding OPTIONS on the ticker (puts/calls/%OI); `/13fo 6/30` lists every 13F option filer
- /bucket — net flow + option volume by expiry & strike
- /chainhist [osi] — life-to-date daily volume & OI
- /chains — full option chain breakdown
- /maxpain — current, per-expiry & historical
- /offlit — options vs off-exchange volume by price
- /oi, /topoi — top OI positions (OI, expiry, strike, P/C, change on the day, bid/mid/ask share)
- /oi-changes [ticker] [--side Calls] [--dte 1-30], /oichg, /oidown, /oiup, /oiexp
- /sharedchains — community-shared option chains
- /strikeflow — flow by strike
- /volbreak — option volume summary by expiry & strike

## Screeners & presets (17)
- /analyzer — multi-leg strategy builder
- /bcrd — bullish credit trades (put-selling, 20%+ ROC); /bcrt — bearish credit trades (call-selling, 20%+ ROC)
- /decc — deep conviction calls (high-delta call buying); /decp — deep conviction puts
- /leap — long-dated $1M+ call positions
- /moso [TICKER|#watchlist] [date] [where expiry=…] — most active contracts by volume. Market-wide: every issue type incl. indexes, ≥1k volume, ≥$100k premium, max 5 per name. With a ticker or #basket: ranked by volume, no floors
- /multileg, /spreads [ticker] [strategy], /topstrats [ticker]
- /optionscreener, /screener, /stockscreener
- /psel — premium-selling puts
- /unbe — unusually bearish: OTM put buyers, $500K+ premium; /unbu — unusually bullish: OTM call buyers, $500K+ premium
- /zerodte — 0-DTE flow tide

## Dark pool & blocks (5)
- /blocks, /qccblocks — dark pool / block trades; /darkpool — dark pool vs lit volume & prints; /flex — institutional FLEX options (top chains & OI); /litflow — lit-exchange stock trades

## Contracts (7)
- /analysis [osi], /cats [osi] (CBOE open-close account type, API Enterprise), /contract [osi or search] [tab], /exposures [osi], /legs [osi], /search, /timesales [osi]

## Stock & fundamentals (26)
- /13f, /breadth, /catalysts, /cd (short for /details), /chca (cheap calls: low-cost short-dated calls), /correlation, /dividends, /earnchg (earnings date changes and affected option expiries), /earnings, /earningshist, /etf, /financials, /fund & /inst (a fund's latest 13F portfolio), /hds (a fund's 13F option holdings), /heatmap, /hp (historical prices), /insiders [ticker | insider] (open-market insider buys & sells), /institutions, /marketmap, /marketstats, /performance, /risk (VaR, drawdown, beta), /seasonality, /shorts, /stats

## Alerts (13)
- /alertfeed, /myalerts — your alerts' recent matches; /alerts — view and edit; /del, /delete — delete alerts by name or row; /dsl — alert builder; /filter; /flowalerts; /mute, /muted, /unmute; /pause, /resume; /presets — "create the Part-1 active-push alerts"

## Market & macro (20)
- /analyst, /analysts, /ratings [ticker | analyst | firm]; /clock; /congress; /crypto; /etfheatmap; /futuresflow (live CME futures flow); /interval; /market; /monitor; /netflow; /netprem; /periscope; /predictions; /privatemarkets; /sectors; /som [contract] [date]; /tide; /topnet

## Watchlists & nav (8)
- /basket <list> += FMC (also @list += / -= / =), /ow (option watchlist), /ww (watchlist), /watchlists, /pin, /n, /p, /to [page]

## Help (6)
- /faq, /list, /news [ticker], /selftest (check every command's data endpoint live), /settings [general|filters|templates|tradealert], /template (option-alert row templates)

## Other (28)
- /at [ticker] [HH:MM:SS.mmm] [date] — every print and structure that executed at that instant (Eastern)
- /backtest, /backtesting; /calc, /opc; /catalyst [ticker]; /chart; /econ; /etfexposure; /etfholdings; /expiry [ticker|osi] [date]; /fda; /filings; /flow [contract] [date]; /flowbias (VWKS + IV asymmetry directional tilt); /flowhistory; /import (paste Trade Alert /list output to create custom alerts); /interpiv; /openclose [ticker] (CBOE open-close by account type, Trading Enterprise); /portfolios; /pulse (Nasdaq Options Pulse customer vs pro sentiment); /putcall; /tradecode [ticker|osi] [code] (trades carrying one OPRA condition code); /tradeflag [ticker|osi] [floor|cross|sweep]; /trades [osi]; /universe [top50|spy|qqq|dia|iwm|mag7|<etf>]; /volxiv; /volxpx

## Things only the Console states (useful for the rebuild)
- Preset thresholds: /unbu and /unbe = OTM call/put buyers with $500K+ premium; /leap = long-dated $1M+ calls; /bcrd /bcrt = 20%+ ROC credit trades; /moso market-wide floors = ≥1k volume, ≥$100k premium, max 5 per name.
- Greek ranking formulas (vega, dollar gamma, gross notional) and multi-leg Edge formula, quoted above.
- Enterprise-only data named here: /bsoc (MM greek exposure), /cats and /openclose (Cboe open-close account type).
- The Console is modelled on Trade Alert (imports Trade Alert rules, "Trade-Alert style prints").
