# Fincept data sources: the connector catalogue

Generated on 20 Nov 2026 from `fincept-qt/resources/data_connectors.json` of FinceptTerminal at commit `914134d`
(release 4.5.3). **[READ]** every row is the file's own content: name, script, region, whether a key is required, the
environment variable names it lists, and the number of commands. The last column is ours and is **[INFERRED]** by
matching names against the files on RevenueChaser-public `main` at `7bfbec1`; an empty cell means no source of that
name was found in `rcdata/build/sources/` or `core/providers/`, not that the data is missing from our store.

Totals: **204 connectors**, 145 need no key, 59 need a key. 4 are marked `broken` in the file.

Fincept's catalogue says whether a key is required; it does not say what the key costs. "Key" below therefore
means "an account is needed", free tier or paid.

| Category | Connectors | No key | Key |
|---|---|---|---|
| Macro & Central Banks | 45 | 41 | 4 |
| Government & Statistics | 48 | 40 | 8 |
| Markets & Equities | 34 | 17 | 17 |
| Crypto & DeFi | 12 | 6 | 6 |
| China & Asia | 5 | 4 | 1 |
| Energy, Commodities & Climate | 28 | 15 | 13 |
| Shipping | 3 | 0 | 3 |
| Geospatial & Geopolitics | 14 | 10 | 4 |
| News & Alternative Data | 6 | 5 | 1 |
| Academic & Research | 8 | 6 | 2 |
| Other | 1 | 1 | 0 |

## Macro & Central Banks

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| Banco Central do Brasil (BCB) (`bcb_data.py`) | Fetches data from the BCB SGS (Sistema Gerenciador de Series Temporais) API. | Brazil | no |  | 19 |  |
| Bank Negara Malaysia (BNM) (`bnm_data.py`) | Fetches data from the BNM Open API. | Malaysia | no |  | 16 |  |
| Bank of Canada (BoC) (`boc_data.py`) | Fetches data from the Bank of Canada Valet API. | Canada | no |  | 19 |  |
| Bank of England (BoE) (`boe_data.py`) | Bank of England Statistical Interactive Database: Bank Rate, SONIA, sterling exchange rates, quoted and eff... | United Kingdom | no |  | 12 |  |
| Bank of Israel (BOI) (`boi_data.py`) | Fetches data from the Bank of Israel public APIs. | Israel | no |  | 11 |  |
| Bank of Japan (BoJ) (`boj_fetcher.py`) | Bank of Japan Time-Series Data Search: any BoJ series by code (FX, rates, money, prices) as a dated table. | Japan | no |  | 1 |  |
| BIS (Bank for International Settlements) (`bis_data.py`) | Bank for International Settlements SDMX API: effective exchange rates, central bank policy rates, credit to... | Global | no |  | 31 |  |
| BIS Data Portal (`bis_stats_data.py`) | Global credit, debt securities, banking stats, effective exchange rates, property prices. No API key required. | Global | no |  | 7 |  |
| Central Bank FX Rates (CEE) (`public_apis_finance_data.py`) | Official exchange-rate tables from the central banks of Poland (incl. gold), Croatia, the Czech Republic, H... | Central & Eastern Europe | no |  | 6 |  |
| Central Bank of Turkey (TCMB) (`tcmb_data.py`) | Fetches exchange rate data from the TCMB public XML bulletin service. | Turkey | no |  | 8 |  |
| Croatian National Bank (HNB) (`hnb_data.py`) | Fetches exchange rate data from the HNB public REST API. | Croatia | no |  | 8 |  |
| Czech National Bank (CNB) (`cnb_data.py`) | Fetches data from the CNB public REST API. | Czech Republic | no |  | 14 |  |
| ECB SDMX (`ecb_sdmx_data.py`) | Official ECB exchange rates, monetary stats, bond yields, balance of payments. No API key required. | Euro Area | no |  | 6 |  |
| EconDB (`econdb_data.py`) | EconDB: global economic indicators by country, country profiles and main macro series. | Global | no |  | 5 |  |
| Economic calendar (Forex Factory) (`economic_calendar.py`) | Economic calendar of the current week from Forex Factory's public export: release time, currency, impact, f... | Global | no |  | 1 |  |
| European Central Bank (ECB) (`ecb_data.py`) | ECB statistical data: euro reference exchange rates and euro-area AAA / all-ratings yield curves (spot, ins... | Euro Area | no |  | 4 |  |
| Federal Reserve (`federal_reserve_data.py`) | Federal Reserve data: fed funds, SOFR and overnight bank funding rates, Treasury rates and yield curve, mon... | United States | no |  | 9 | Fed (`rcdata/build/sources/fed.py`) |
| FRED (St. Louis Fed) (`fred_data.py`) | Federal Reserve Economic Data: 800k+ US and international series — observations, search, categories and rel... | United States | yes | `FRED_API_KEY` | 6 | FRED (`rcdata/build/sources/fred.py`) |
| FRED Macro Dashboards (`fred_economic_data.py`) | Broader macro coverage from FRED — yield curves, money supply, credit conditions, financial stress, consume... | United States | yes | `FRED_API_KEY` | 6 | FRED (`rcdata/build/sources/fred.py`) |
| Global Competitiveness (`global_competitiveness_data.py`) | IMD World Competitiveness Yearbook + WEF GCI proxy via World Bank: competitiveness indicators by country. | Global | no |  | 6 |  |
| Global Debt Monitor (`global_debt_monitor_data.py`) | Government, corporate, and household debt ratios globally via the IMF Data Mapper API (covers fiscal monito... | Global | no |  | 6 |  |
| Global Financial Development (GFD) (`gfd_data.py`) | Banking system depth, efficiency, stability, and access indicators for 200+ countries via the World Bank Gl... | Global | no |  | 6 |  |
| IMF (International Monetary Fund) (`imf_data.py`) | IMF World Economic Outlook series and projections (DataMapper), international reserves (IRFCL), direction o... | Global | no |  | 7 |  |
| IMF DataMapper (`imf_datamapper_data.py`) | IMF DataMapper API: WEO forecasts, global debt, fiscal monitor, and financial soundness indicators for 190+... | Global | no |  | 6 |  |
| Inter-American Development Bank (IADB) (`iadb_data.py`) | IDB lending operations in Latin America and the Caribbean - projects, approvals by country/sector/year, sec... | Latin America & Caribbean | no |  | 5 |  |
| Macro Trends (`wisesheets_macro_data.py`) | Long-term US market valuation and macro history (no key): Shiller CAPE, S&P 500 P/E and price levels (multp... | United States | no |  | 6 |  |
| Maddison Project (`maddison_project_data.py`) | Fetches long-run GDP per capita estimates for 169 countries back to year 1 from the Maddison Project Databa... | Global | no |  | 6 |  |
| Multpl (S&P 500 Multiples) (`multpl_data.py`) | S&P 500 valuation history from multpl.com: Shiller CAPE, P/E, dividend and earnings yield, price/sales and ... | United States | no |  | 12 |  |
| National Bank of Hungary (MNB) (`mnb_data.py`) | Fetches exchange rate data from the MNB SOAP web service. | Hungary | no |  | 9 |  |
| National Bank of Poland (NBP) (`nbp_data.py`) | Fetches data from the NBP Public Web API. | Poland | no |  | 10 |  |
| National Bank of Romania (BNR) (`bnr_data.py`) | Fetches data from the BNR public XML API. | Romania | no |  | 9 |  |
| NBER (`nber_data.py`) | Fetches NBER (National Bureau of Economic Research) business cycle dates, macroeconomic datasets, and publi... | United States | no | `FRED_API_KEY` | 6 |  |
| Norges Bank (Bank of Norway) (`norges_bank_data.py`) | Fetches data from the Norges Bank open data SDMX API. | Norway | no |  | 15 |  |
| OECD (`oecd_data.py`) | OECD SDMX API: real GDP, CPI, unemployment, GDP forecasts, interest rates and trade balance by country, plu... | Global | no |  | 8 |  |
| Penn World Tables (`penn_world_table_data.py`) | Fetches national accounts, productivity, and living standards data from the Penn World Tables (PWT 10.x) fo... | Global | no |  | 6 |  |
| Reserve Bank of Australia (RBA) (`rba_data.py`) | Fetches statistical data from RBA published CSV tables. | Australia | no |  | 19 |  |
| Sveriges Riksbank (Sweden) (`riksbank_data.py`) | Fetches data from the Riksbank SWEA REST API. | Sweden | no |  | 18 |  |
| Swiss National Bank (SNB) (`snb_data.py`) | Fetches data from the SNB Data Portal REST API. | Switzerland | no |  | 19 |  |
| Trading Economics (`trading_economics_data.py`) | Fetches sovereign credit ratings and government bond yields from the Trading Economics API. | Global | yes | `TRADING_ECONOMICS_API_KEY` | 16 |  |
| UNCTAD Statistics (broken) (`unctad_data.py`) | United Nations Conference on Trade and Development: world trade, FDI flows, maritime transport, investment ... | Global | no |  | 6 |  |
| UNDP Human Development (`undp_data.py`) | Human Development Index (HDI), Gender Inequality Index (GII), and Multidimensional Poverty Index (MPI) for ... | Global | yes | `UNDP_API_KEY` | 6 |  |
| World Bank Extra (`world_bank_extra_data.py`) | World Bank extended indicators: climate, poverty, gender, education, health, and governance data beyond bas... | Global | no |  | 6 |  |
| World Bank Global Findex (`global_findex_data.py`) | Fetches financial inclusion data — bank accounts, digital payments, credit access, savings rates, and mobil... | Global | no |  | 6 |  |
| World Bank Open Data (`worldbank_data.py`) | World Bank Open Data (WDI): countries, indicators, GDP per capita, commodity prices, economic snapshots and... | Global | no |  | 8 |  |
| World Bank Sovereign Fiscal (`fitch_connect_data.py`) | Sovereign debt, fiscal balance, tax revenue, expenditure, debt service and external debt from the World Ban... | Global | no |  | 6 |  |

## Government & Statistics

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| Australian Bureau of Statistics (`abs_data.py`) | ABS Data API (SDMX, keyless): Australian GDP, CPI, labour force, merchandise exports, population and any of... | Australia | no |  | 8 |  |
| BEA (Bureau of Economic Analysis) (`bea_data.py`) | Bureau of Economic Analysis: NIPA and regional accounts, GDP by industry, international transactions and in... | United States | yes | `BEA_API_KEY` | 18 |  |
| BLS (Bureau of Labor Statistics) (`bls_data.py`) | US labor statistics: CPI, employment, wages, productivity and employment-cost series and overviews. | United States | yes | `BLS_API_KEY` | 8 | BLS (`rcdata/build/sources/bls.py`) |
| Census International (`census_international_data.py`) | US Census International Data: population, demographics, economic development indicators for all countries (... | Global | yes | `CENSUS_API_KEY` | 6 |  |
| CKAN open-data portals (`universal_ckan_api.py`) | National CKAN open-data portals (Argentina, Australia, Chile, Ireland, Italy, Latvia, Mexico, Netherlands, ... | Global | no |  | 8 |  |
| Congress.gov (`congress_gov_data.py`) | Congress.gov: bills by congress and type, bill details, full text, summaries and related data. | United States | yes | `CONGRESS_GOV_API_KEY` | 7 |  |
| data.gov.au (Australia) (`datagov_au_api.py`) | data.gov.au (CKAN): Australian government organizations, datasets, resources and keyword search. | Australia | no | `AUS_DATA_API_KEY` | 13 |  |
| data.gov.uk (`datagovuk_api.py`) | data.gov.uk (CKAN): publishers, datasets, resources, previews and keyword search. | United Kingdom | no | `DATAGOVUK_API_KEY` | 10 |  |
| Eurostat (`eurostat_data.py`) | GDP, employment, trade, prices, population for all EU/EEA countries. No API key required. | European Union | no |  | 7 |  |
| Eurostat Extra (`eurostat_extra_data.py`) | Eurostat additional datasets: energy balance, industrial production, retail trade, construction output, tra... | European Union | no |  | 6 |  |
| French Government Open Data (`french_gov_api.py`) | French public APIs: data.gouv.fr datasets and tabular resources, API Géo (municipalities, departments, regi... | France | no | `ENTREPRISE_API_KEY` | 12 |  |
| GovData.de (Germany) (`govdata_de_api_complete.py`) | GovData.de (CKAN): German federal and state publishers, datasets, resources, previews and keyword search. | Germany | no | `GOVDATA_API_KEY` | 10 |  |
| GovInfo API (`govinfo_data.py`) | GovInfo (US GPO): collections, packages, Congressional Record, Federal Register, court opinions, public law... | United States | no | `GOVINFO_API_KEY` | 22 |  |
| GovTrack (broken) (`govtrack_data.py`) | GovTrack US Congress: bill tracking, voting records, committee data, member statistics. | United States | no |  | 6 |  |
| HUD (Housing and Urban Development) (`hud_data.py`) | HUD: Fair Market Rents, income limits, public housing, opportunity zones via HUD User API (free key required). | United States | yes | `HUD_API_KEY` | 6 |  |
| ILOSTAT (`ilostat_data.py`) | ILOSTAT (ILO): unemployment, employment, wages, hours of work, informality and social protection statistics. | Global | no |  | 28 |  |
| IRS Statistics of Income (`irs_data.py`) | Fetches US tax data from the IRS Statistics of Income (SOI) program — individual income, corporate taxes, a... | United States | no |  | 6 |  |
| OECD Development Cooperation (`oecd_dev_data.py`) | Official Development Assistance (ODA) flows, multilateral aid, aid by sector, ODA/GNI and donor/recipient l... | Global | no |  | 6 |  |
| OECD Health Statistics (`oecd_health_data.py`) | Provides health expenditure, life expectancy, disease burden, pharmaceutical market data, health workforce,... | Global | no |  | 6 |  |
| ONS (UK Office for National Statistics) (`ons_data.py`) | UK Office for National Statistics (ONS): UK GDP, CPI, labour market, trade, earnings, debt, house prices. | United Kingdom | no |  | 7 |  |
| Open Government Canada (`canada_gov_api.py`) | Open Government Canada (CKAN): federal publishers, datasets, resources, previews and keyword search. | Canada | no | `CANADA_GOV_API_KEY` | 10 |  |
| Open Parliament (`open_parliament_data.py`) | Open Parliament / They Vote For You: parliamentary votes, member records for multiple countries (TheyWorkFo... | United Kingdom | yes | `TWFY_API_KEY` | 6 |  |
| openAFRICA (`openafrica_api.py`) | openAFRICA: African open-data portal (CKAN) organizations and datasets. | Africa | no | `AFRICA_API_KEY` | 10 |  |
| opendata.swiss (Switzerland) (`swiss_gov_api.py`) | opendata.swiss (CKAN): Swiss publishers, datasets, resources, previews and keyword search. | Switzerland | no | `SWISS_GOV_API_KEY` | 11 |  |
| OpenSecrets (`open_secrets_data.py`) | OpenSecrets: US campaign finance, lobbying data, PAC contributions, revolving door. | United States | yes | `OPENSECRETS_API_KEY` | 6 |  |
| Our World in Data (`owid_data.py`) | Our World in Data grapher charts (CO2, energy, life expectancy, poverty, GDP per capita, democracy) by coun... | Global | no |  | 10 |  |
| Spain Open Data (datos.gob.es) (`spain_data.py`) | datos.gob.es: Spanish government catalogues, datasets and resources. | Spain | no |  | 7 |  |
| Statistics Canada (`statcan_data.py`) | Statistics Canada: Canadian economic, social, demographic data — GDP, trade, labour, housing. | Canada | no |  | 9 |  |
| Statistics Finland (PxWeb) (`pxweb_fetcher.py`) | Statistics Finland PxWeb API: browse the table tree (nodes), read table metadata and query table data. | Finland | no |  | 3 |  |
| Statistics Sweden (SCB) (`scb_data.py`) | Statistics Sweden PxWeb API: category tree, table metadata, population, GDP, employment and CPI. | Sweden | no |  | 11 |  |
| TreasuryDirect (US Treasury securities) (`government_us_data.py`) | TreasuryDirect: Treasury security prices and auction results (prices are published end-of-day on business d... | United States | no |  | 4 |  |
| UN Comtrade (`un_comtrade_data.py`) | UN Comtrade: bilateral trade flows by reporter, partner, commodity and period; country import/export profil... | Global | no | `UN_COMTRADE_API_KEY` | 22 |  |
| UN Comtrade Extended (`un_comtrade_extended_data.py`) | Detailed bilateral trade flows by HS chapter, trade balances, and services trade via the UN Comtrade public... | Global | no | `COMTRADE_API_KEY` | 6 |  |
| UN Population (`un_population_data.py`) | UN World Population Prospects: population projections, demographic indicators for all countries 1950-2100. | Global | no |  | 6 |  |
| UN SDG Statistics (`un_sdg_data.py`) | All 17 SDG goals, 230+ indicators for all countries. No API key required. | Global | no |  | 8 |  |
| UN Statistics Division (`un_stats_data.py`) | Fetches national accounts, environment accounts, demographic statistics, and gender statistics for all coun... | Global | no |  | 6 |  |
| UNESCO Institute for Statistics (UIS) (`unesco_data.py`) | UNESCO Institute for Statistics: education, science and culture indicators by country and region. | Global | no |  | 17 |  |
| UNHCR Refugee Statistics (`unhcr_data.py`) | Provides refugee populations, displacement figures, asylum applications, demographic breakdowns, stateless ... | Global | no |  | 6 |  |
| UNICEF (`unicef_data.py`) | Child mortality, immunization, nutrition, education and water/sanitation indicators for all countries via t... | Global | no |  | 7 |  |
| US Census Bureau (`census_data.py`) | US Census Bureau API: ACS demographics, trade statistics, economic census, and population estimates. | United States | yes | `CENSUS_API_KEY` | 6 |  |
| US Treasury Fiscal Data (`treasury_data.py`) | US Treasury fiscal data: debt to the penny, interest rates, exchange rates, and account statements via the ... | United States | no |  | 5 | Treasury (`rcdata/build/sources/treasury.py`) |
| US Treasury FiscalData (`fiscal_data.py`) | US Treasury FiscalData: debt to the penny, average interest rates, interest expense, exchange rates and rec... | United States | no |  | 7 |  |
| WHO Global Health Observatory (GHO) (`who_data.py`) | Provides mortality, disease burden, health systems, nutrition, and immunization data for 200+ countries via... | Global | no |  | 6 |  |
| WHO Immunization (`who_immunization_data.py`) | Vaccination coverage (WHO/UNICEF WUENIC estimates) and reported cases of vaccine-preventable diseases, by c... | Global | no |  | 5 |  |
| World Bank Health/Education/Poverty (`worldbank_health_data.py`) | Provides life expectancy, literacy, Gini coefficient, HDI-related indicators, and poverty headcount data fo... | Global | no |  | 6 |  |
| World Bank WITS (`wits_trade_data.py`) | World Bank WITS: trade statistics, tariffs and non-tariff measures by reporter, partner, product and year. | Global | no |  | 6 |  |
| Worldometers (`worldometers_data.py`) | Worldometers real-time statistics: world population counter, COVID stats, countries data via disease.sh API. | Global | no |  | 6 |  |
| WTO (World Trade Organization) (`wto_data.py`) | WTO APIs: quantitative restrictions, ePing SPS/TBT notifications, trade timeseries indicators and trade-fac... | Global | no | `WTO_API_KEY` | 19 |  |

## Markets & Equities

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| Alpha Vantage (`alphavantage_data.py`) | Alpha Vantage real-time and delayed stock quotes. | Global | yes | `ALPHA_VANTAGE_API_KEY` | 1 | Alpha Vantage (day cap 25, `rcdata/caps.py`) |
| Alpha Vantage (FX, crypto, commodities, macro) (`alpha_vantage_extra_data.py`) | Forex, crypto, commodities, economic indicators, sector performance. | Global | yes | `ALPHA_VANTAGE_API_KEY` | 6 | Alpha Vantage (day cap 25, `rcdata/caps.py`) |
| Cboe (`cboe_data.py`) | Cboe delayed quotes and history for equities and indices, index constituents and snapshots, symbol / index ... | United States | no |  | 9 | Cboe index history (`rcdata/build/sources/cboe.py`) |
| Cboe VIX & volatility indices (`cboe_vix_data.py`) | CBOE VIX historical data and CBOE indices: VIX, VIX3M, VVIX, SKEW directly from the CBOE CDN CSV endpoint. ... | United States | no |  | 5 | Cboe index history (`rcdata/build/sources/cboe.py`) |
| CFTC Commitments of Traders (`cftc_data.py`) | CFTC Commitments of Traders: COT positions by market, market sentiment, position summaries and historical t... | United States | no | `CFTC_APP_TOKEN` | 7 | CFTC (`rcdata/build/sources/cftc.py`) |
| EODHD (`eodhd_data.py`) | End-of-day historical data for 70+ exchanges, fundamental data, bulk downloads. | Global | yes | `EODHD_API_KEY` | 6 |  |
| ExchangeRate (open.er-api.com) (`exchangerate_data.py`) | 200+ currencies, no key, no rate limit. Uses open.er-api.com and fawazahmed0 CDN as fallback. | Global | no |  | 6 |  |
| FDIC BankFind Suite (`fdic_data.py`) | US bank financial health, assets, capital ratios, NPL, and data for all FDIC-insured banks via the FDIC Ban... | United States | no |  | 6 |  |
| Financial Modeling Prep (DCF, estimates, holders) (`fmp_extra_data.py`) | DCF valuations, analyst estimates, insider trading, institutional holdings — extended free tier. | Global | yes | `FMP_API_KEY` | 6 |  |
| Financial Modeling Prep (FMP) (`fmp_data.py`) | Financial Modeling Prep: quotes, profiles, price history, financial statements and ratios, ETFs, crypto, ne... | Global | yes | `FMP_API_KEY` | 21 |  |
| Finnhub (`finnhub_data.py`) | Real-time quotes, fundamentals, earnings calendar, SEC filings, sentiment, forex, and crypto data via the F... | Global | yes | `FINNHUB_API_KEY` | 7 |  |
| Frankfurter (ECB FX rates) (`frankfurter_data.py`) | ECB reference exchange rates, 30+ currencies, daily history back to 1999. No API key required. | Global | no |  | 6 |  |
| GLEIF (Legal Entity Identifiers) (`lei_data.py`) | Fetches Legal Entity Identifier (LEI) data including global company identification, ownership structures, a... | Global | no |  | 6 |  |
| Intrinio (`intrinio_data.py`) | Financial data, news sentiment, economic indicators — free tier. | Global | yes | `INTRINIO_API_KEY` | 6 |  |
| Marketstack (`marketstack_data.py`) | End-of-day data for 70+ global exchanges, tickers, splits, dividends. | Global | yes | `MARKETSTACK_API_KEY` | 6 |  |
| Nasdaq (`nasdaq_data.py`) | Nasdaq public data: equity search and screener, dividend / earnings / IPO / economic calendars and market o... | United States | no | `NASDAQ_API_KEY` | 8 |  |
| Nasdaq Data Link (Quandl) (`quandl_nasdaq_data.py`) | Financial, economic, and alternative datasets — Fed data, commodities, futures. | Global | yes | `NASDAQ_DATA_LINK_API_KEY` | 6 |  |
| Nasdaq Data Link WIKI Prices (`quandl_wiki_data.py`) | Fetches adjusted end-of-day US stock prices, dividends, and splits for 3000+ stocks via the Nasdaq Data Lin... | Global | yes | `NASDAQ_DATA_LINK_API_KEY` | 6 |  |
| Open Exchange Rates (`open_exchange_data.py`) | Open Exchange Rates free tier: 170+ currency rates, historical rates, time-series, and OHLC data. | Global | yes | `OPENEXCHANGERATES_API_KEY` | 6 |  |
| OpenBB (`openbb_data.py`) | OpenBB Platform public endpoints: stocks, macro, alternatives, ETF holdings, economic calendar. | Global | yes | `OPENBB_API_KEY` | 6 |  |
| OpenCorporates (`openCorporates_data.py`) | Fetches global corporate registry data — company information, officers, and filings for 200M+ companies wor... | Global | yes | `OC_API_KEY` | 6 |  |
| OpenFIGI (`openfigi_data.py`) | Map tickers/ISINs/CUSIPs to global FIGI identifiers. 1700+ asset classes globally. No key for basic use (hi... | Global | no | `OPENFIGI_API_KEY` | 4 | OpenFIGI (`core/providers/openfigi.py`) |
| Polygon.io (`polygon_io_data.py`) | US stocks OHLCV, trades, quotes, market-wide aggregates, options, crypto, and forex data via the Polygon.io... | Global | yes | `POLYGON_API_KEY` | 6 |  |
| Quiver Quantitative (`quiverquant_data.py`) | Congress trades, government contracts, insider transactions, lobbying — free tier. | Global | yes | `QUIVER_API_KEY` | 6 |  |
| Redfin housing market (`redfin_data.py`) | Redfin Data Center: US housing market metrics — median sale price, days on market, sale-to-list ratio, new ... | United States | no |  | 6 |  |
| SEC EDGAR (`sec_data.py`) | SEC EDGAR: company filings, CIK/symbol mapping, filing content, insider and institutional ownership, compan... | United States | no |  | 14 | SEC EDGAR (`core/providers/sec_edgar.py`, `rcdata/build/sec_forms`) |
| SEC EDGAR XBRL company facts (`sec_xbrl_data.py`) | SEC EDGAR XBRL Company Facts: structured financial data — revenue, EPS, balance sheet for all public US com... | United States | no |  | 6 | SEC EDGAR (`core/providers/sec_edgar.py`, `rcdata/build/sec_forms`) |
| SimFin (`simfin_data.py`) | Free fundamental financial data — income statements, balance sheets, cash flows for 4000+ US companies. | Global | yes | `SIMFIN_API_KEY` | 6 |  |
| Tiingo (`tiingo_data.py`) | EOD stock prices, intraday IEX data, crypto prices, forex, news — generous free tier. | Global | yes | `TIINGO_API_KEY` | 6 |  |
| TradingView screener (`tradingview_data.py`) | Screener data, economic calendar, market overview using public endpoints. | Global | no |  | 5 |  |
| Twelve Data (`twelve_data.py`) | Global stocks, forex, crypto, ETFs OHLCV — 800+ exchanges, 70+ countries. | Global | no | `TWELVE_DATA_API_KEY` | 7 |  |
| Yahoo Finance (market summary, movers, options) (`yh_finance_data.py`) | Market summary, trending, movers, options chain via public Yahoo JSON APIs. | Global | no |  | 6 |  |
| Yahoo Finance (yfinance) (`yfinance_data.py`) | Yahoo Finance via yfinance: quotes, price history, company info, financial statements and ratios, news and ... | Global | no |  | 15 | Yahoo (`rcdata/build/sources/yahoo.py`, `core/providers/yfinance.py`) |
| Zillow Research housing data (`zillow_data.py`) | Zillow Research: median home values, rents, inventory, price cuts by zip/metro/state via direct CSV downloa... | United States | no |  | 6 |  |

## Crypto & DeFi

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| Alternative.me (Fear & Greed) (`alternative_me_data.py`) | Alternative.me: Fear & Greed Index, crypto fear gauge, global market sentiment (no API key required). | Global | no |  | 5 |  |
| Blockchain.com (Bitcoin network) (`blockchain_com_data.py`) | Bitcoin network stats, hashrate, mempool, tx volumes, address data. No API key required. | Global | no |  | 7 |  |
| CoinCap v3 (`coincap_data.py`) | 1000+ crypto prices, market caps, volumes, exchange data, candles. Requires a free CoinCap API key (COINCAP... | Global | yes | `COINCAP_API_KEY` | 7 |  |
| CoinGecko (`coingecko.py`) | CoinGecko: coin prices, markets, history, trending coins, exchanges, NFTs and public-company treasuries. | Global | no | `COINGECKO_API_KEY` | 11 |  |
| CoinGlass (`coinglass_data.py`) | Crypto futures open interest, funding rates, liquidations, long/short ratios across 30+ exchanges. | Global | yes | `COINGLASS_API_KEY` | 6 |  |
| CoinMarketCap (`coinmarketcap_data.py`) | CoinMarketCap Basic tier: top crypto listings, prices, market caps, categories, and global metrics via the ... | Global | yes | `CMC_API_KEY` | 6 |  |
| CoinPaprika (`coinpaprika_data.py`) | 71000+ assets, market caps, OHLCV, exchanges, events. No API key required for public endpoints. | Global | no |  | 10 |  |
| CryptoCompare (`cryptocompare_data.py`) | OHLCV historical for 5700+ coins, social stats, news, exchange volume. Requires a free CoinDesk Data / Cryp... | Global | yes | `CRYPTOCOMPARE_API_KEY` | 7 |  |
| DeFiLlama (`defillama_data.py`) | TVL for 3000+ DeFi protocols, chain TVL, yield pools, bridges, fees. No API key required. | Global | no |  | 8 |  |
| DexScreener (`dexscreener_data.py`) | DEX pair prices, volume, liquidity across 80+ chains. No API key required. | Global | no |  | 7 |  |
| Glassnode (`glassnode_data.py`) | Bitcoin/Ethereum on-chain metrics — active addresses, tx count, hash rate, NVT ratio. | Global | yes | `GLASSNODE_API_KEY` | 6 |  |
| Messari (`messari_data.py`) | Crypto asset directory (sector, category, tags, rank) and the metrics catalogue keyless; asset details, mar... | Global | yes | `MESSARI_API_KEY` | 7 |  |

## China & Asia

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| Asian Development Bank (ADB) KIDB (`adb_data.py`) | Asian Development Bank Key Indicators Database (KIDB): population, GDP, financial and trade indicators for ... | Asia-Pacific | no |  | 10 |  |
| BaoStock (`baostock_data.py`) | BaoStock: China A-share daily bars, fundamentals (profit, growth, balance sheet, cash flow, DuPont), index ... | China | no |  | 24 |  |
| Data.gov.hk (Hong Kong) (`data_gov_hk_api.py`) | Hong Kong government data portal: categories, datasets, resources and historical files. | Hong Kong | no |  | 13 |  |
| Data.gov.sg (Singapore) (`datagovsg_data.py`) | Provides access to Singapore's open data portal including real-time APIs and catalog APIs. | Singapore | no | `DATAGOVSG_API_KEY` | 6 |  |
| e-Stat (Japan official statistics) (`estat_japan_api.py`) | e-Stat: Japanese official statistics — table catalogue, metadata, classifications and data by area and period. | Japan | yes | `ESTAT_APP_ID` | 12 |  |

## Energy, Commodities & Climate

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| Climate TRACE (`climate_trace_data.py`) | GHG emissions for 350M+ assets globally, country/sector level, 2015-2024. No API key required (Climate TRAC... | Global | no |  | 8 |  |
| Climate Watch (Paris Agreement NDCs) (`paris_agreement_data.py`) | National climate pledges (NDCs), GHG emissions inventories, sectoral targets, and adaptation data via the C... | Global | no | `CLIMATE_WATCH_API_KEY` | 6 |  |
| Copernicus Climate Change Service (C3S) (`copernicus_data.py`) | Provides ERA5 reanalysis data, seasonal forecasts, climate indicators, sea level data, and temperature anom... | Europe | yes | `COPERNICUS_API_KEY` | 6 |  |
| EIA (US Energy Information Administration) (`eia_data.py`) | Provides access to Weekly Petroleum Status Report and Short Term Energy Outlook data. | United States | no | `EIA_API_KEY` | 11 |  |
| EIA Electricity (`eia_electricity_data.py`) | EIA Electricity: US generation by source, grid demand, net imports, retail prices by state. | United States | yes | `EIA_API_KEY` | 6 |  |
| EIA Natural Gas (`eia_natural_gas_data.py`) | EIA Natural Gas: Henry Hub prices, storage levels, production, consumption, LNG exports. | United States | yes | `EIA_API_KEY` | 6 |  |
| EIA Petroleum (`eia_petroleum_data.py`) | EIA Petroleum data: crude oil inventory, imports/exports, refinery runs, gasoline prices by region. | United States | yes | `EIA_API_KEY` | 6 |  |
| EIA Short-Term Energy Outlook (STEO) (`eia_steo_data.py`) | Energy forecasts, oil/gas/coal/renewables projections by quarter via EIA API v2 (free key required via EIA_... | United States | yes | `EIA_API_KEY` | 6 |  |
| Ember Energy (`ember_energy_data.py`) | Provides yearly/monthly electricity generation, demand, CO2 emissions, and carbon intensity for 200+ countr... | Global | yes | `EMBER_API_KEY` | 6 |  |
| Energy Transition (`energy_transition_data.py`) | Renewable power capacity (IRENA), total energy supply by source and CO2 intensity (IEA) from the agencies' ... | Global | no |  | 6 |  |
| ENTSO-E (`entso_e_data.py`) | ENTSO-E (European electricity grid): power generation, load, cross-border flows, capacity, prices. | Europe | yes | `ENTSOE_API_KEY` | 6 |  |
| ENTSOG gas transparency (`gas_infrastructure_data.py`) | ENTSO-G (European gas grid): gas flows, storage levels, LNG sendout, interconnection capacities. | Europe | no |  | 6 |  |
| FAOSTAT (UN FAO) (broken) (`faostat_data.py`) | Wrapper for the UN Food and Agriculture Organization (FAO) FAOSTAT database. Covers crop production, trade,... | Global | no |  | 33 |  |
| Global Forest Watch (`global_forest_watch_data.py`) | Country-level tree cover loss and its emissions, integrated deforestation alerts, forest carbon stocks/flux... | Global | yes | `GFW_API_KEY` | 6 |  |
| Global Solar Atlas (`global_solar_atlas_data.py`) | Global Solar Atlas (World Bank/Solargis): long-term solar irradiance (GHI, DNI, DIF), optimal-tilt irradian... | Global | no |  | 6 |  |
| IEA (International Energy Agency) (`iea_data.py`) | IEA world energy statistics (free tier): total energy supply by source, final consumption, electricity gene... | Global | no |  | 6 |  |
| IRENA Renewable Energy Statistics (`irena_data.py`) | IRENASTAT (keyless PxWeb API): installed electricity capacity (MW) and generation (GWh) by country/region a... | Global | no |  | 5 |  |
| Metals.dev prices (`metals_prices_data.py`) | Gold, silver, platinum, palladium, and copper real-time and historical prices via the Metals.dev API. | Global | yes | `METALS_DEV_API_KEY` | 6 |  |
| NOAA Climate Data Online (CDO) (`noaa_climate_data.py`) | Provides weather observations, climate normals, storm events, and sea level data from NOAA's Climate Data O... | United States | yes | `NOAA_CDO_TOKEN` | 6 |  |
| Open-Meteo weather (`open_meteo_data.py`) | Global weather forecasts + 80yr historical for any lat/lon, free, no API key. | Global | no |  | 7 |  |
| OpenAQ (`openaq_data.py`) | Air quality data from 30,000+ stations in 100+ countries — PM2.5, PM10, NO2, CO, SO2, O3 via OpenAQ API v3 ... | Global | yes | `OPENAQ_API_KEY` | 6 |  |
| Our World in Data — CO2 & energy (`owid_co2_data.py`) | CO2 emissions, energy mix, per-capita emissions for all countries via OWID GitHub raw CSV (no key required). | Global | no |  | 6 |  |
| USDA ERS (`usda_ers_data.py`) | USDA Economic Research Service ARMS (Agricultural Resource Management Survey) API: farm income statements, ... | United States | yes | `USDA_ERS_API_KEY` | 7 |  |
| USDA Foreign Agricultural Service (FAS) PSD (`usda_fas_data.py`) | Production, Supply and Distribution (PSD) balance sheets - area, yield, production, trade, consumption and ... | United States | no | `USDA_FAS_API_KEY` | 6 |  |
| USDA NASS Quick Stats (`usda_nass_data.py`) | US agricultural production, prices, acreage, and livestock data for all commodities via the USDA National A... | United States | yes | `USDA_NASS_API_KEY` | 6 |  |
| World Air Quality Index (WAQI) (`waqi_data.py`) | AQI for 11000+ stations globally, PM2.5/PM10/NO2/CO/SO2/O3. Requires free API key via WAQI_TOKEN env var. | Global | no | `WAQI_TOKEN` | 6 |  |
| World Bank Climate Change Knowledge Portal (`world_bank_climate_data.py`) | CMIP6 temperature/precipitation projections, climate-hazard indicators and ERA5 history by country via the ... | Global | no |  | 6 |  |
| World Bank commodity prices (Pink Sheet) (`world_bank_commodity_data.py`) | World Bank Pink Sheet: 70+ commodity prices and price indices, monthly from 1960 (no key required). Read fr... | Global | no |  | 6 |  |

## Shipping

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| AISStream (`aisstream_data.py`) | Live AIS vessel positions and ship static data (name, type, destination, ETA) from the AISStream.io WebSock... | Global | yes | `AISSTREAM_API_KEY` | 2 |  |
| Global Fishing Watch (`global_fishing_watch_data.py`) | Provides vessel tracking, fishing activity hours, port events, and AIS data for vessels worldwide via the G... | Global | yes | `GLOBAL_FISHING_WATCH_API_KEY` | 6 |  |
| MarineTraffic (`marinetraffic_data.py`) | MarineTraffic free tier: vessel positions, expected arrivals, port congestion data via MarineTraffic API (f... | Global | yes | `MARINETRAFFIC_API_KEY` | 6 |  |

## Geospatial & Geopolitics

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| ACLED (Armed Conflict Location & Event Data) (`acled_data.py`) | Provides political violence events, protest data, conflict fatalities, actor information, and trend analysi... | Global | yes | `ACLED_EMAIL`, `ACLED_PASSWORD` | 6 |  |
| Global Trade Alert (`global_trade_alert_data.py`) | Global Trade Alert: protectionist and liberalizing trade-policy interventions worldwide (GTA API; jurisdict... | Global | no | `GTA_API_KEY` | 7 |  |
| HDX (Humanitarian Data Exchange) (`hdx_data.py`) | Humanitarian Data Exchange (OCHA): search datasets by keyword, country, organization, topic or data series. | Global | no |  | 14 |  |
| N2YO satellite tracking (`n2yo_satellite_data.py`) | N2YO: satellite TLEs, positions, visual and radio passes, and what is overhead a location. | Global | yes | `N2YO_API_KEY` | 8 |  |
| NASA GIBS satellite imagery (`nasa_gibs_api.py`) | NASA Global Imagery Browse Services: imagery layer catalogue, layer details and time periods, and WMTS tile... | Global | no |  | 9 |  |
| Open Budget Survey & GIFT Fiscal Openness (broken) (`transparency_budget_data.py`) | Provides government budget transparency scores, Open Budget Index (OBI), fiscal openness rankings, and gove... | Global | no |  | 6 |  |
| OpenStreetMap Nominatim geocoding (`nominatim_data.py`) | Global geocoding, reverse geocoding, place search, address lookup via Nominatim public API (no key, 1 req/s... | Global | no |  | 6 |  |
| OpenStreetMap Overpass (`overpass_api_data.py`) | Query OSM features — banks, ATMs, hospitals, airports, ports, industrial areas globally via Overpass API (n... | Global | no |  | 6 |  |
| ReliefWeb (OCHA) (`reliefweb_data.py`) | Provides humanitarian crisis reports, disaster events, emergency job listings, training opportunities, and ... | Global | yes | `RELIEFWEB_APP_ID` | 6 |  |
| RSF Press Freedom (`rsf_press_freedom_data.py`) | Reporters Without Borders World Press Freedom Index: annual scores, ranks and the five context indicators f... | Global | no |  | 6 |  |
| Sentinel Hub (`sentinelhub_data.py`) | Sentinel Hub: satellite scene search by bounding box or point and processed imagery (true colour, NDVI and ... | Global | yes | `SENTINELHUB_CLIENT_ID`, `SENTINELHUB_CLIENT_SECRET` | 7 |  |
| WMO OSCAR (Earth observation systems) (`oscar_data.py`) | WMO OSCAR: satellites, instruments and the Earth-observation variables they measure. | Global | no |  | 19 |  |
| WorldPop (`world_pop_data.py`) | High-resolution population grids, demographic estimates, and urbanization data from the University of South... | Global | no |  | 6 |  |
| Worldwide Governance Indicators (`prs_group_data.py`) | Political stability, rule of law, corruption control, and regulatory quality via the World Bank Worldwide G... | Global | no |  | 6 |  |

## News & Alternative Data

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| Company News (Google News) (`fetch_company_news.py`) | Latest news articles by company or symbol, by topic, or full article text — via GNews. | Global | no |  | 3 |  |
| GitHub repository stats (`github_stats_data.py`) | Repo commit activity, star history, contributor stats, language breakdown, trending repos. No key required ... | Global | no | `GITHUB_TOKEN` | 8 |  |
| Global price indices (Big Mac, PPP) (`global_price_index_data.py`) | Various global price indices: Big Mac Index, Economist commodity indices, CPI comparisons, PPP rates — fetc... | Global | no |  | 5 |  |
| IndexMundi / free statistics (`statista_free_data.py`) | Open/free statistics portals: IndexMundi and other free stat aggregators for cross-country data (no key req... | Global | no |  | 6 |  |
| Numbeo (`numbeo_data.py`) | Numbeo: Cost of living, quality of life, crime, healthcare, property prices by city/country (free key requi... | Global | yes | `NUMBEO_API_KEY` | 6 |  |
| Wikipedia Pageviews (`wikipedia_pageviews_data.py`) | Daily/monthly page traffic for any article, top-1000 lists, project-level stats. No API key required. | Global | no |  | 6 |  |

## Academic & Research

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| arXiv (`arxiv_data.py`) | Fetches research papers in finance, economics, machine learning, and quantitative finance from the ArXiv AP... | Global | no |  | 6 |  |
| CrossRef (`crossref_data.py`) | Fetches academic paper metadata, citations, and DOI resolution for 130M+ scholarly articles from the CrossR... | Global | no | `CROSSREF_EMAIL` | 6 |  |
| data.world (`data_world_data.py`) | Fetches community-published datasets from data.world covering finance, economics, ESG, demographics, and mo... | Global | yes | `DATA_WORLD_TOKEN` | 6 |  |
| Harvard Dataverse (`harvard_dataverse_data.py`) | Fetches research datasets in social science, economics, and public health from the Harvard Dataverse reposi... | Global | no | `HARVARD_DATAVERSE_TOKEN` | 6 |  |
| Kaggle Datasets (`kaggle_data.py`) | Fetches public finance, economics, and ML datasets from Kaggle — stock prices, economic indicators, alterna... | Global | yes | `KAGGLE_KEY`, `KAGGLE_USERNAME` | 6 |  |
| Semantic Scholar (`semantic_scholar_data.py`) | AI-powered academic search with citation graphs and paper recommendations for 200M+ papers from the Semanti... | Global | no | `SEMANTIC_SCHOLAR_API_KEY` | 6 |  |
| World Values Survey (`world_values_survey_data.py`) | World Values Survey: cross-national survey data on values, beliefs, norms from 100+ countries. | Global | no |  | 6 |  |
| Zenodo (`zenodo_data.py`) | Fetches open research data from Zenodo (CERN) — datasets, software, and papers across all scientific discip... | Global | no | `ZENODO_ACCESS_TOKEN` | 6 |  |

## Other

| Connector | What it is | Region | Key | Key variables | Commands | Same source in RevenueChaser |
|---|---|---|---|---|---|---|
| Local file (CSV, JSON, Excel, Parquet, Arrow) (`local_file_data.py`) | Reads a data file on this computer as a typed table: CSV/TSV (delimiter, encoding and header sniffed), JSON... | Local | no |  | 3 |  |
