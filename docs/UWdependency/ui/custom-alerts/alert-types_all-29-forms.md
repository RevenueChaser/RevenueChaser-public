# Custom alert types and the fields of each Visual Builder form
Read from /custom-alerts/create on 21 Nov 2026 16:28 Amsterdam by selecting every type in turn (URL parameter `noti_type`). Nothing was saved.
Every form has a "WATCH" scope (All / Tickers / Watchlist / Option Chains where shown) and a Create button. The number after the name is the
count of input boxes in the form.

## Options
- **Chain OI Change** (`chain_oi_change`, 9): OI Change, OI Change %, OI Change / Prev Volume %, Prev Volume (min/max). Scope: All, Option Chains.
- **Flow alerts** (`flow_alerts`, 44): DTE, IV Change, Open Interest, Premium, Price, Size, Volume, Volume/OI, Bearish Prem %, Bullish Prem %,
  % OTM, Single-leg only, Multi-leg only, Expiry Dates, Rules; stock: Market Cap, In Index, Issue Types, Market Cap Bucket, Sectors; chain
  activity Ask % / Bid % / Skew %; flags Bid Side only, Ask Side only, Calls only, Puts only, Is Sweep, Delta Neutral, All Opening, Is OTM,
  Exclude ITM, Size > OI, Volume > OI.
- **Contract alert** (`option_contract`, 103): Avg Fill $, Close $, Days of OI Increases, Days of Vol > OI, DTE, From High, From Low, OI Change,
  OI Change %, Open Interest, Premium, Return on Capital, Spread, Strike, Transactions, Volume, Volume/OI, Bearish/Bullish Prem %, Cross Volume %,
  % OTM, Floor Volume %, IV, Multi-leg Volume %, Sweep Volume %; Type, Expiry Months, Expiry Dates; stock: Earnings Report, Market Cap, Stock
  Price, Daily % Change, Issue Types, Market Cap Bucket, Sectors, Exclude Ex-Dividend; Greeks Delta/Gamma/Theta/Vega; Contract 30D Avg Volume,
  Contract Vol/30D Avg Ratio, Ticker Vol/30D Avg Ratio; Ask % / Bid % / Skew %; flags Is New, Is OTM, Vol > OI, OPEX Only, Is Quarterly,
  Last Fill > Avg, Exclude ITM.
- **Interval alert** (`option_contract_interval`, 109): the Contract alert fields plus IV Change, Minute Interval, % of Total Volume, flag Total Vol > OI.
- **Option Trade alert** (`option_trade`, 89): DTE, IV Change, Open Interest, Premium, Price, Size, Spread, Strike, Underlying Price, Volume,
  Volume/OI, Bearish/Bullish Prem %, % OTM, IV; Expiry Months, Single-leg/Multi-leg only, FLEX only, Exclude FLEX, Tags, Excluded Tags,
  Exchanges, Trade Codes, Expiry Dates, Report Flags, Type, Settlement, Older Than; stock: Earnings Report, Market Cap, Industries, Issue Types,
  Market Cap Bucket, Sectors; Greeks Delta/Gamma/Theta; Prev IV; Ask % / Bid % / Skew %; Days Between Expiry And Earnings; Ticker Open Interest;
  Size and Volume against 7-day and 30-day average volume, Ticker Avg 7/30-day Volume; Size / Ticker OI Ratio.
- **Multi-leg Trade** (`multi_leg_trade`, 2): Strategy, Net Side (Bid/Ask/Mid/No), Put/Calls, Direction, Expiration Style, Exchanges; Issue Types,
  Market Cap Bucket, Sectors; flags All OTM, All Opening Legs, Exclude Other.
- **FLEX Consolidations** (`flex_consolidations`, 8): Open Interest, OTM; Include indexes / ETFs / stocks / ADRs.

## Stocks
- **Analyst ratings** (`analyst_rating`, 7): Min Upside/Downside, Ratings, Actions, a Cluster rule ("N ratings issued by at least N firms in the
  last N days, with at least N ratings with a ... of N %"); Market Cap, In Index, Sectors; Has Options.
- **Dividends** (`dividends`, 4): Yield, Alert Timing, Dividend Status; Market Cap, In Index, Sectors; Dividend Increased, Has Options; email with PDF.
- **Earnings** (`earnings`, 10): Expected Move %, Implied Move %, Total OI, Alert Timing; Market Cap, Stock Price, In Index, Sectors; email with PDF.
- **Ticker Interval Flow** (`ticker_interval_flow`, 105): Avg DTE, Avg OTM, Avg Prem, Avg Size, Opt Vol, Transactions, Underlying Price, Bearish %,
  Bull/Bear Skew %, Bullish %, Call/Put Vol % and 30d %, Cross/Floor/Multi/Sweep Vol %, Implied Move % 30d, Interval Implied Move % Change,
  Interval % Change, Interval Volatility % Change, Opt Vol 30d %, % Change, Volatility 30d, Sector, Interval Type; Market Cap, In Index, Issue
  Types, Market Cap Bucket; Net Call/Put/total Premium; Delta, Gamma, Vega Flow and their directional versions.
- **Price target** (`price_target`, 5): Lower / Upper target, Rearm Ticks, Repeat. Tickers only.
- **Stock splits** (`splits`, 1): Market Cap, In Index, Sectors; Has Options.
- **Stock alert** (`stock`, 345 - the stock screener as an alert): 30D Avg Stock Volume, Implied Move %, IV Rank, Open Interest, Premium, 30D
  Stock/Volume Ratio, Volume, Bearish %, Bullish %, Intraday Change %, Gap Up/Down, Reg SHO status; Earnings Report, Market Cap, Short Interest,
  Stock Price, Years Increased Dividend, Years Reducing Shares Outstanding, ETFs, In Index, Industries, Issue Types, Sectors, Has Dividends,
  S&P 500; Options Activity block (3/7/30-day call and put volume and OI averages, 30D Avg Option Volume, bullish/bearish premium, call/put OI
  change, call/put premium and volume by ask/bid/mid side, ETF Share Flow, FLEX OI, net premiums ...). The page text was cut at 1,600
  characters here; the full field set equals the 224-column stock screener list in screeners/stock-screener_all-224-columns.md.
- **Stock trades** (`stock_trade`, 17): Premium, Price, Size, Volume, Size as % of 30d Avg Vol, Size as % of Vol, Trade Codes, Sale Condition
  Codes, Trade Types, Market Times; Market Cap, Issue Types, Market Cap Buckets, Sectors; Hide Index ETF.
- **Insider trades** (`insider_trades`, 14): Value ($), Transactions, Holding % Change, Cluster rule ("Any transactions with at least $ of
  premium, executed by at least N insiders who are directors or 10% owners, within the last N days"), Trade Codes, Owner Name Contains; Market
  Cap, In Index, Sectors; Is Director, Exclude 10b5-1, Is Officer, Is 10% Owner, Is Reporter Public Company, Has Options.
- **Trading halts** (`trading_state`, 2): Status, Reason; Market Cap, In Index; Has Options.
- **FDA status** (`fda`, 12): Volume, Stock Price Change, Indication / Description / Drug Contains, FDA Phases; Market Cap, Stock Price, In Index;
  Has Options, Is Priority Review.
- **SEC filings** (`sec_filings`, 2): Form Type, Name Contains; Market Cap, In Index, Sectors; Has Options.
- **GEX** (`gex`, 4): GEX Change Type, Change %, Minutes, OI Change from Yesterday (all required). Tickers / Watchlist.
- **13F Alert** (`thirteen_f_alert`, 19): Share Value, Stock Added / Closed / New / Reduced Positions, Stock Positions, Total Value, Tags, Name
  Contains, Company CIK, Position Type, Option Changed Positions; Receive Alerts from Non-Super Investors, Exclude Funds with Options.

## Macro & Other
- **Economic events** (`economic_release`, 2): Text also contains, Time before event, Event Types.
- **News** (`news`, 3): Text also contains, Text does NOT contain, News Type; Market Cap; Is Major, Daytime Hours Only, Ignore Trump's Truth Social Posts.
- **Chat** (`chat`, 2): Contains Word, Rooms; Your Username Mentioned, Option Contract Mentioned, Ticker Mentioned.
- **Trump (POTUS) Schedule** (`potus_schedule`, 2): Coverage, Schedule, Contains Word, Time before event.
- **Market Tide** (`market_tide`, 1): Directional Alert Timeframe; Cross, Daily High/Low.
- **Politician trades** (`politician_trades`, 6): Trade Amount, Amount High, Amount Low, Politician name contains, Member Type, Asset, Market; Market Cap.
- **Stock Talk** (`stock_talk`, 1): "Subscribe to unlock" on avo's plan.

## Predictions
- **Prediction Insider** (`prediction_insider`, 14): Category, Min/Max Invested, Min/Max Z-Score, Min/Max Average Price, Min/Max PnL, Min/Max
  Positions, Min/Max Wallet Age; email with PDF.
