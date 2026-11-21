# Formula builder: field dictionary for the "Option Trades" stream
Read from /custom-alerts/create (Formula tab, FIELDS drawer) on 21 Nov 2026 16:30 Amsterdam. These are UW's own definitions, so they are the
reference for rebuilding the same measures from IBKR / OPRA data. Other streams in the TYPE dropdown: Option Contracts, Interval Flow, Flow
Alert, Multi-leg Trade, FLEX Consolidations, Stock Prints, Ticker Flow, News, Trading Halts (their field lists were not read).

## Language ("Start here" tab)
- A rule is `where <conditions>`; `and`, `or`, parentheses; number shortcuts `k`, `m`, `b`, `%` (50k, 1.5m, 5%).
- Scope before `where`: `$AAPL` one ticker, `@tech` a sector, `#mylist` a watchlist.
- Placeholder shown in the box: `where call and premium >= 50000 and ln(strike / spot) / (ivol * sqrt(dte / 365)) > 2 and size > open_int`
  (so arithmetic and functions such as ln and sqrt are allowed).

## Examples tab (UW's own presets, verbatim logic)
- Ask Flow: `where otm and not bidside and ask_perc >= 50% and issue_type in (stock, adr) and not complex and add_agg_trades and premium >= 10k and volume >= 500 and volume > open_int and open_int <= 5000 and price <= 25 and dte <= 180`
- Bid Flow: same with `not askside and bid_perc >= 50%`.
- Big Trades - Ask: `where not bidside and not midside and ask_perc >= 60% and issue_type in (stock, adr) and not complex and add_agg_trades and size >= 500 and premium >= 50k and volume > open_int and diff >= -10%`
- Big Trades - Bid: same with `not askside and bid_perc >= 60%`.
- ETF Flows - Ask: the Big Trades - Ask rule with `issue_type in (etf, index)`.

## Money and size
- premium = contracts * price * shares per contract
- size = trade size; volume (vol) = option volume at trade time; open_int (oi) = open interest at trade date
- notional = contracts * spot * shares per contract
- price = trade price; spot = spot at trade time; diff (spot_chg) = spot change on the day at trade time
- dollar_impact = size * abs(delta) * spot * shares per contract
- delta_impact = contracts * delta * shares per contract
- hedge_quantity = size * delta * shares
- gamma_shares = contracts * gamma * shares per contract
- gamma_dollar = contracts * gamma * spot * shares per contract
- vega_dollar = contracts * vega * shares per contract; theta_dollar = contracts * theta * shares per contract
- vol_oi_ratio = volume / open interest; marketcap = underlying market cap

## Greeks and pricing
- delta, gamma, vega, theta, rho, theo (theoretical value), iv (ivol) at trade time
- prev_iv (prior_iv) = prior session's closing IV of the contract; iv_change (iv_chg) = IV minus prior close, in vol points
- strike; dte (dtx) = days to expiry; bid, ask = NBBO at trade time; ewma_bid, ewma_ask = EWMA NBBO; bid_ask_spread (spread) = spread %

## Type, moneyness, expiry
- call / put, put_call (option_type), otm, itm, divcapture (dividend capture trade)
- expiry; weekly; third_friday (monthly, opex); quarterly; am / pm settlement; jan ... dec = third Friday of that month

## Trade condition
- sweep = multi-part trade (sweep or split ticket); cross, floor, late, normal, iso, auction = from the OPRA condition code
- complex = spread or tied or cob or legged or part_of_spread
- bidside / askside / midside = where the trade printed against the NBBO
- bid_perc / ask_perc = share of the contract's volume traded at bid / ask
- bull_perc = calls at ask + puts at bid; bear_perc = calls at bid + puts at ask
- opening = "trades that are definitely opened"; size_greater_oi; volume_greater_oi; exclude_deep_itm
- add_agg_trades = include aggregations of several single transactions; condition = OPRA mnemonic (LATE, SPD, TIED ...)
- delta_neutral (stock_tied, tied) = option executed with an offsetting stock leg; multileg / singleleg from the OPRA code
- flex = contract whose OCC root starts with a digit; noflex; tag(s) = bid_side, ask_side, mid_side, dividend, arbitrage ...
- report_flag(s) = OPRA report flag (opening, closing, cross_trade, odd_lot ...)

## Earnings, symbol, sector, exchange
- earnings_dte = days to next earnings; days_between_expiry_and_earnings = expiry minus next earnings date, signed
- symbol / ticker, usymbol (underlying), osi_symbol, sector (11 GICS-like names), industry, issue_type (stock, etf, adr, index),
  marketcap_size (micro, small, mid, large, big)
- exchange by MIC or mnemonic; keywords amex, arca, box, bxo, bzx, c2, cboe, edgx, emld, gem, ise, nom, merc, miax, pearl, phlx, memx, sphr, mx2, iex

## Ticker-level context
- ticker_open_int (ticker_oi) = total OI across all contracts of the underlying
- avg30d_volume = 30-day average daily stock volume, in shares
- option_volume (ticker_volume) = underlying's total option volume for the day at trade time
- option_mw_mult (ticker_vol_mult) = that volume as a multiple of its 30-day average
- ticker_avg_7_day_volume, ticker_avg_30_day_volume = average daily option volume over the previous 7 / 30 trading days
- ticker_prev_option_volume = previous trading day's option volume
- size_ticker_oi_ratio, volume_ticker_oi_ratio; size_avg_7_day_volume_ratio, size_avg_30_day_volume_ratio;
  volume_avg_7_day_volume_ratio, volume_avg_30_day_volume_ratio
- transaction_count = number of trades in the contract so far in the session
