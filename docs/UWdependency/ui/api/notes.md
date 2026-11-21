# API dashboard and the public API spec

Unusual Whales web UI survey, 21 November 2026. Times are Amsterdam time (UTC+1). Screenshots: 9.

## Screenshots

| File | Full URL | Captured (Amsterdam time) |
|---|---|---|
| `api-dashboard_scroll-2_skills.jpg` | https://unusualwhales.com/dashboard/api | 21.11.2026 14:56:54 |
| `api-dashboard_scroll-3_plan.jpg` | https://unusualwhales.com/dashboard/api | 21.11.2026 14:56:54 |
| `api-dashboard_scroll-4_daily-requests.jpg` | https://unusualwhales.com/dashboard/api | 21.11.2026 14:56:54 |
| `api-dashboard_scroll-5-bottom_busiest-endpoints.jpg` | https://unusualwhales.com/dashboard/api | 21.11.2026 14:56:54 |
| `api-dashboard_skill-data-lake.jpg` | https://unusualwhales.com/dashboard/api | 21.11.2026 14:57:35 |
| `api-dashboard_skill-earnings-vol-scan.jpg` | https://unusualwhales.com/dashboard/api | 21.11.2026 14:57:35 |
| `api-dashboard_skill-institutional-13f.jpg` | https://unusualwhales.com/dashboard/api | 21.11.2026 14:57:35 |
| `api-dashboard_skill-unusual-flow-filter.jpg` | https://unusualwhales.com/dashboard/api | 21.11.2026 14:57:35 |
| `api-dashboard_top.jpg` | https://unusualwhales.com/dashboard/api | 21.11.2026 14:56:54 |

## Other files in this folder

- `public_api_paths.txt`
- `uw_public_api_openapi.yaml`

## Notes (what the page shows, buttons pressed, nearest API path)

### /dashboard/api "API Dashboard" (2026-11-21 14:56 Amsterdam)
The API key field is blacked out in the two screenshots that showed it (it is partly masked on the page too). Reveal / Copy / Regenerate were NOT pressed.
Sections: MCP setup prompt (remote MCP server https://api.unusualwhales.com/api/mcp, Bearer key) with "Copy MCP setup prompt" and "Manual setup guide"; Build with the API (API Docs "100+ endpoints across 18 categories", Example Notebooks "15 ready-to-fork Jupyter projects", Websocket Examples "Not included in your plan", Discord #api); Skills tabs (Unusual Whales Skill, Data Lake Skill, Earnings Volatility Scan Skill, Institutional 13F Skill, Unusual Flow Filter Skill; "Copy API skill", "Download skill", CLI `npx skills add https://unusualwhales.com --all`); API key (created Sep 6, 2026).
Plan: (plan name) (Active). Used today 1,312 / 100M, window resets 8:00pm ET. Daily requests included 100M, lookback window 2 years, Websockets: "Upgrade to bundle Pro" (not in plan).
Included in this plan: Real-Time Options Flow (100% Market Coverage), Real-Time Nasdaq Equities Data, Congressional and Insider Trades, Darkpool, Net Premium / Market Tide / Earnings etc., GEX / Gamma Exposure, Daily Open Interest including FLEX OI transfer, 2 Year Historical Lookback, Unlimited requests per day, MCP Support, Custom Skills for your agents.
Daily requests, past 30 days: total 148K, daily average 5K, peak day 35K, days over 80%: 0.
Busiest endpoints, past 30 days: /api/stock/:ticker/greek-exposure/strike-expiry 36,893 (22.9%); /api/shorts/:ticker/interest-float/v2 35,806 (22.2%); /api/stock/:ticker/option-contracts 19,423 (12.0%); /api/stock/:ticker/ohlc/:candle_size 17,870 (11.1%); /api/stock/:ticker/earnings 11,229 (7.0%).
Request health, past 24 h: 429: 0, 404: 0, 403: 0, other errors: 9. Links: Troubleshooting, Fix 404 errors. Kits: Alerts Bot.
Top buttons: Welcome guide, Link Discord (not pressed: links an account).
Skill tabs: Data Lake Skill (uw-options-data-lake: "durable, offline copy of the transaction-level Full Tape on your own machine, day by day or back-filled across a range; bronze layer of daily Parquet files, 1-minute bar layer, worked screener"); Earnings Volatility Scan Skill (uw-earnings-vol-scan: IV-crush setups, Recommended/Consider/Avoid verdict); Institutional 13F Skill (uw-institutional-13f: live API calls + optional local SQLite); Unusual Flow Filter Skill (uw-unusual-flow-filter: presets for unusual option activity). Copy / Download skill buttons not pressed.

