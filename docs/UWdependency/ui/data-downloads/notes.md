# Data Downloads

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 2 (kept outside the repository, see ../README.md).

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `01_data-downloads_top.jpg` | https://unusualwhales.com/data/download | 21.11.2026 16:48:19 |
| `02_data-downloads_daily-table.jpg` | https://unusualwhales.com/data/download | 21.11.2026 16:48:19 |

## Notes (what the page shows, buttons pressed, nearest API path)

### /data/download (Data Downloads) — 21 Nov 2026. Nothing was downloaded.
- Text: "Historical data is available to download by Retail Pro/Max and Bundle subscribers. For additional data please visit the data shop." "This data is STRICTLY for personal use. Sharing this data will result in your account being terminated."
- "Flow + Dark Pool Filtered Download": the flow and dark pool feeds have their own download of the filtered result (those CSV buttons were seen on the feed pages, not pressed).
- Individual Ticker Download: "The complete options tape for the specified ticker will be provided for download. Limit 5 per day." (ticker input).
- Daily Downloads table: one row per trading day, last 8 trading days only (Fri 20 Nov back to Wed 11 Nov 2026), five files per day: Options Flow, Options Screener, Stock Screener, OI Changes, Dark Pool.
- Migration relevance: HIGH as a one-off. While the plan is active (until 8 Dec 2026) these files are the cheapest way to keep reference days for testing an own build against UW output: full options tape, screener snapshots (224 stock fields), OI changes and dark pool prints per day. The window is rolling (8 days), so reference days must be saved before they roll off. Personal-use licence: keep them out of the public repository.
- /data_shop and /enterprise are sales pages (paid datasets, enterprise plans); not opened further.

