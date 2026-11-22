# Stock Screener — all 224 columns (label = API field name)

Source: Columns panel ("Table setup", "Columns · 23 of 224") on https://unusualwhales.com/stock-screener, read 2026-11-21T14:46Z.
The field names are the same ones the query language and `/api/screener/stocks` use.

## Identity (6)
Ticker=ticker, Sector=sector, Industry=industry_type, Type=issue_type, ER Time=er_time, Date=date

## Price & Volume (21)
Open=open, High=high, Low=low, Price=close, Prev Close=prev_close, Bid=bid, Ask=ask, 52W High=week_52_high, 52W Low=week_52_low, Bid Size=bid_quantity, Ask Size=ask_quantity, Stock Vol=stock_volume, Avg 30D Stock Vol=avg30_volume, Quote Time=quote_time, Intraday %=intraday_change, Rel Vol=relative_volume, Z-Score=z_score, Mkt Cap=marketcap, Shares Out=shares_outstanding, Short Int=short_int, Reg SHO=reg_sho_status

## Returns (21)
1D %=one_day_perc, 1W %=one_week_perc, 1M %=one_month_perc, 1D σ=one_day_return_stddevs, 1W σ=one_week_return_stddevs, 1M σ=one_month_return_stddevs, σ to 52W High=distance_to_52w_high_30d_stddevs, σ to 52W Low=distance_to_52w_low_30d_stddevs, 52W Range Pos=log_52w_range_position_perc, 3M %=three_month_perc, 6M %=six_month_perc, YTD %=ytd_perc, 1Y %=one_year_perc, 5Y %=five_year_perc, 1W Ref Price=one_week_close, 1M Ref Price=one_month_close, 3M Ref Price=three_month_close, 6M Ref Price=six_month_close, YTD Ref Price=ytd_close, 1Y Ref Price=one_year_close, 5Y Ref Price=five_year_close

## Option Volume (23)
Opt Vol=volume, C Vol=call_volume, P Vol=put_volume, C Vol Ask=call_volume_ask_side, C Vol Bid=call_volume_bid_side, C Vol Mid=call_volume_mid_side, P Vol Ask=put_volume_ask_side, P Vol Bid=put_volume_bid_side, P Vol Mid=put_volume_mid_side, Prev C Vol=prev_call_volume, Prev P Vol=prev_put_volume, Opt Vol 1D Ago=prev_day_option_volume, Opt Vol 2D Ago=prev_2_day_option_volume, Opt Vol 3D Ago=prev_3_day_option_volume, Opt Vol 4D Ago=prev_4_day_option_volume, C Vol 3D Avg=avg_3_day_call_volume, P Vol 3D Avg=avg_3_day_put_volume, C Vol 7D Avg=avg_7_day_call_volume, P Vol 7D Avg=avg_7_day_put_volume, C Vol 30D Avg=avg_30_day_call_volume, P Vol 30D Avg=avg_30_day_put_volume, P/C Ratio=put_call_ratio, Rep Hits=repeated_hits

## Premium (9)
C Prem=call_premium, P Prem=put_premium, Bull Prem=bullish_premium, Bear Prem=bearish_premium, C Prem Mid=call_premium_mid_side, P Prem Mid=put_premium_mid_side, Net Prem=net_premium, Net C Prem=net_call_premium, Net P Prem=net_put_premium

## Open Interest (7)
OI=total_open_interest, C OI=call_open_interest, P OI=put_open_interest, Prev C OI=prev_call_oi, Prev P OI=prev_put_oi, C OI 30D Avg=avg_30_day_call_oi, P OI 30D Avg=avg_30_day_put_oi

## Greeks (3)
Dir Delta=cum_dir_delta, Dir Gamma=cum_dir_gamma, Dir Vega=cum_dir_vega

## Volatility (38)
IV 30D=volatility, IV 30D 1D Ago=iv30d_1d, IV 30D 1W Ago=iv30d_1w, IV 30D 1M Ago=iv30d_1m, RV 20D=realized_volatility, Impl Move % 30D=implied_move_perc, VRP=variance_risk_premium, Impl Move 30D=implied_move, IV Rank=iv_rank, IV Rank 1M=iv_rank_1m, IV Pctl 1M=iv_percentile_1m, IV Pctl 1Y=iv_percentile_1y, Earn RV/Impl=rv_1d_last_12q, IV Steepness=steepness_180_30,
then for N in 1, 5, 7, 14, 60, 90, 180, 365: IV ND=volatility_N, Impl Move % ND=implied_move_perc_N, Impl Move ND=implied_move_N (24 columns)

## Technicals (46)
RSI 14=rsi_14, MFI 14=mfi_14, CCI 14=cci_14, ADX 14=adx_14, Williams %R=willr_14, Stoch %K=stoch_5_3_3_k, Stoch %D=stoch_5_3_3_d, Aroon Up=aroon_14_up, Aroon Down=aroon_14_down, MACD=macd_12_26_9, MACD Signal=macd_12_26_9_signal, MACD Hist=macd_12_26_9_histogram, ATR 14=atr_14, OBV=obv,
levels: sma_10, sma_14, sma_20, sma_50, sma_200, ema_9, ema_14, ema_20, ema_21, ema_50, bb_20_2_upper, bb_20_2_middle, bb_20_2_lower, bb_14_2_upper, bb_14_2_middle, bb_14_2_lower (16),
distance of price to each of those 16: distance_to_sma_10 ... distance_to_bb_14_2_lower (16)

## GEX (26)
Gamma/1% (OI)=gex_gamma_per_one_percent_move_oi, Delta/1% (OI)=gex_delta_per_one_percent_move_oi, Charm/1% (OI)=gex_charm_per_one_percent_move_oi, Vanna/1% (OI)=gex_vanna_per_one_percent_move_oi, the same four with _vol (Vol), Gamma/Charm/Vanna with _dir (Dir) (3), Call GEX=gex_daily_call_gex, Put GEX=gex_daily_put_gex, Net GEX=gex_daily_net_gex, Call DEX=gex_daily_call_delta, Put DEX=gex_daily_put_delta, Net DEX=gex_daily_net_delta, Call Charm=gex_daily_call_charm, Put Charm=gex_daily_put_charm, Net Charm=gex_daily_net_charm, Call Vanna=gex_daily_call_vanna, Put Vanna=gex_daily_put_vanna, Net Vanna=gex_daily_net_vanna, GEX Chg=gex_net_change, GEX Chg %=gex_perc_change, GEX P/C=gex_ratio

## Earnings (8)
Next Earnings=next_earnings_date, Last Earnings=last_earnings_date, Since Earnings %=earnings_perc, EPS Δ 4Q=eps_growth_4q, EPS Δ 8Q=eps_growth_8q, EPS Δ 12Q=eps_growth_12q, EPS Δ 16Q=eps_growth_16q, Pre-ER Price=last_earnings_price

## Dividends (6)
Next Ex-Div=next_dividend_date, Last Ex-Div=latest_dividend_date, Div Paid=latest_dividend_payment_date, Last Dividend=latest_dividend, TTM Dividend=ttm_dividend, Div Yield=dividend_yield

## Fundamentals (3)
Shares Δ 4Q=shares_outstanding_growth_4q, Shares Δ 8Q=shares_outstanding_growth_8q, Shares Δ 12Q=shares_outstanding_growth_12q

## Insiders (6)
insider_buy_volume_3m, insider_sell_volume_3m, insider_buy_volume_6m, insider_sell_volume_6m, insider_buy_volume_12m, insider_sell_volume_12m

## ETF (1)
ETF Share Flow=etf_share_flow

## avo's current table (format "Overview", 23 columns, in order)
ticker (pinned), close, marketcap, one_day_perc, stock_volume, relative_volume, sector, volume, call_volume, put_volume, put_call_ratio, call_premium, put_premium, net_premium, iv_rank, volatility, implied_move_perc, variance_risk_premium, next_earnings_date, distance_to_sma_200, distance_to_52w_high_30d_stddevs, distance_to_52w_low_30d_stddevs, shares_outstanding_growth_12q
