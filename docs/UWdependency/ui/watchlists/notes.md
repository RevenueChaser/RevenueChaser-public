# Option and Stock Watchlists

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 19 (kept outside the repository, see ../README.md).

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `01_options-watchlist_bookmarks.jpg` | https://unusualwhales.com/flow/option-watchlist | 21.11.2026 16:20:08 |
| `02_options-watchlist_info-banner.jpg` | https://unusualwhales.com/flow/option-watchlist | 21.11.2026 16:21:14 |
| `03_options-watchlist_columns-drawer.jpg` | https://unusualwhales.com/flow/option-watchlist | 21.11.2026 16:21:14 |
| `04_options-watchlist_create-menu.jpg` | https://unusualwhales.com/flow/option-watchlist | 21.11.2026 16:21:32 |
| `05_options-watchlist_create-form_not-saved.jpg` | https://unusualwhales.com/flow/option-watchlist | 21.11.2026 16:21:39 |
| `06_options-watchlist_note-dialog_not-saved.jpg` | https://unusualwhales.com/flow/option-watchlist | 21.11.2026 16:21:54 |
| `07_options-watchlist_contract-panel.jpg` | https://unusualwhales.com/flow/option-watchlist | 21.11.2026 16:21:54 |
| `08_stock-watchlist_list1_top.jpg` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:22:22 |
| `09_stock-watchlist_columns-list.jpg` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:22:33 |
| `10_stock-watchlist_scrolled-right.jpg` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:22:56 |
| `11_stock-watchlist_scrolled-bottom.jpg` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:22:56 |
| `12_stock-watchlist_settings_rename-delete_not-pressed.jpg` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:22:56 |
| `13_stock-watchlist_ai-cip-semi.jpg` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:23:27 |
| `14_stock-watchlist_cloud-quantum-kripto.jpg` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:23:27 |
| `15_stock-watchlist_defense-uzay-madencilik.jpg` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:23:27 |
| `16_stock-watchlist_enerji.jpg` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:23:27 |
| `17_stock-watchlist_finance-healthcare.jpg` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:23:27 |
| `18_stock-watchlist_create-menu.png` | https://unusualwhales.com/flow/watchlist | 21.11.2026 16:23:43 |
| `19_investor-lists_empty.jpg` | https://unusualwhales.com/flow/investor-lists | 21.11.2026 16:24:45 |

## Other files in this folder

- `avo_stock_watchlists.json`

## Notes (what the page shows, buttons pressed, nearest API path)

### Watchlists (My Workspace) - raw notes, 21 Nov 2026 ~16:20-16:25 Amsterdam
Top tabs: Stock Watchlist /flow/watchlist | Options Watchlist /flow/option-watchlist | Investor Lists | Contract Look-up.

### Options Watchlist (/flow/option-watchlist)
- Tabs: Create (menu: "Create new watchlist", "Import a list") | Bookmarks. "1/10000 contracts". Search "Contract or Keyword", "Add Chain", gear, Columns.
- Gear shows the banner: "This is your default watchlist for recently viewed contracts in Contract Look-up. You can also access this watchlist
  from the mobile app." -> BOOKMARKS IS FILLED AUTOMATICALLY BY VIEWING A CONTRACT.
- The single row (STM $25 put 2027-01-15, "Added 11/21 15:30" local time) was added by THIS SESSION when it opened that contract's Flow Alert
  Breakdown at 14:30 UTC during the Flow Alerts pass. Removing it was attempted through the "On Bookmarks" toggle and was blocked by the
  session's safety layer, so the row is STILL THERE. avo can remove it with the trash icon at the end of the row.
- Columns: Added, Last Trade, Ticker, Contract, DTE, Stock, Chg %, Mark, Last fill, Return (Day), Return (Total), Vol, OI, Vol/OI, OI +/-
  (Overnight), OI +/- (Since add), 1D Vol (10min), Bid/Ask, Floor, Sweep, Multi, Premium, Note, Earnings, delete. Hidden: Fill Range, Sector.
  Row actions in the Columns drawer: View Flow (on), Options Profit Calculator, Copy Contract Link, View in Contract Look-up (off).
- Create Watchlist form: "Watchlists: 1/1000, Contracts: 0/10000", name, "Add a chain" search, upload icon, Cancel / Save (cancelled).
- Note icon: dialog "Add Note STM $25 P 15/1/2027 (55D)", Cancel / Save (closed with Escape).
- Chart icon on the contract opens the Contract Look-up panel (Summary / Analysis / Time & Sales / Volume / Multi-legs), documented in options-flow.
- "Add Chain" with an empty search box did nothing.

### Stock Watchlist (/flow/watchlist, URL carries watchlist_id)
- avo has SIX lists, 286 tickers in total; exact contents exported to avo_stock_watchlists.json (via the UW connector, read-only):
  AI Veri Merkezi & Yazılım 48, AI Çip & Semi 45, Cloud Quantum & Kripto 46, Defense Uzay & Madencilik 49, Enerji 49, Finance & Healthcare 49.
- Toolbar: Create (same two-item menu), list tabs, "48/10000 tickers", "Add ticker..." box, gear, search, sector select (only the sectors
  present in the list), Columns (checkbox list), Gainers / Losers counters.
- Column groups: STOCK (Last Trade, Ticker, Chart sparkline, Price, Change, Volume + relative volume, 52w Range, Mkt Cap) | OPTIONS (P/C,
  Net Prem, IV Rank, IV, Implied 7D, Implied 30D) | STATISTICS (RV, Mean, Std Dev, Daily +-1 sigma) | TECHNICALS (RSI, EMA 9, EMA 21,
  SMA 50, SMA 200 with % distance) | INFO (Name, Sector, Earnings date) | trash per row (NOT pressed).
- Gear: "Rename Watchlist" (name, colour, Save) and "Delete Watchlist" (Delete) - neither pressed; Close.
- Switching list tabs changes watchlist_id; returned to the first list afterwards.
- Migration relevance: HIGH. These six lists are avo's own data and exist only in UW; copy them into RevenueChaser's watchlists store
  before 8 Dec. The table itself = quote + IV rank + implied move + RV + RSI/EMA/SMA: all computable from IBKR/Cboe data.
- The public API does have watchlist paths: /api/watchlists/stocks, /stocks/{id}, /stocks/{id}/add-tickers, /remove-tickers, /api/watchlists/options, /options/{id} (checked against public_api_paths.txt).

### Investor Lists (/flow/investor-lists)
- Empty for avo. Text: "Group 13F filers into lists, then pick a list in the Live Options Flow sidebar. Each print then shows which funds on
  the list held that ticker in their latest 13F, with the value of their shares, calls and puts." Controls: "New list" name box + Create
  (disabled until a name is typed; nothing created). UI-only join of flow with 13F holdings; RevenueChaser already has its own 13F board.

