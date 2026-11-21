# Discord pass: the UW bot channels in Traders' Pub (21 Nov 2026)

Read-only pass in avo's logged-in Chrome, 21 Nov 2026 between 17:49 and 17:56 Amsterdam time. Nothing was written,
no command was sent, no reaction was added. For each channel the newest posts that Discord loaded were read (12 to 36
per channel; avo: "30 post yeterli", four channels gave 12 because Discord opened them at the unread marker and the
content is uniform). Link targets were read from the link itself or from Discord's "Leaving Discord" dialog, then
"Go Back" was pressed. Two targets were opened in a separate tab: the analyst "Interactive chart" page and the UW
"Discord bot" product page. The ninth channel, `unusual-command-line`, was not opened: avo does that one together.

Server: Traders' Pub, guild `1353449857569787934`, category "Unusual Whales".

## What the bot is

- Every post comes from an author marked APP whose profile holds only a name (no "Add App", no bio). The names are
  the UW **push notification topics**: UW Economic News, UW Trump News + Schedule, UW Live Options Flow,
  UW Analyst Ratings, UW Insider Trades, UW Congress Trade Filings, UW Stock Updates, UW 52 Week High/Low Updates,
  UW Highest Volume Contracts.
- UW's own page (https://unusualwhales.com/discord-bot, shot `uw-discord-bot-page_01.jpg`) says: 84 free and 21
  premium-exclusive slash commands; 17 push topics, 10 free and 7 premium-exclusive; topics are subscribed with
  `/configure`; the Premium bot gives live instead of delayed data. Prices on that page: user subscription
  $6.99/month, **server subscription $124.99/month** ($1,250/year). "Send your custom UW alerts straight to
  Discord ... Available only with the Premium Server Subscription."
- The 17 topics as listed there: Highest Volume Contracts (15 minute), Snorlax's tweets, Unusual whales' tweets,
  Economic news, Market updates, Trading states, Ticker state updates, Upcoming Dividends, Discord Bot Announcements,
  UW Platform Announcements, Congress Trade Filings, Trump News + Schedule, Live Options Flow, Analyst Ratings,
  Insider Trades, Stock Updates, 52 Week High/Low Updates. The page marks the premium ones with an icon the text
  dump does not carry; the last seven are the likely premium set (guess, by order and by the image paths below).
- Evidence that Traders' Pub runs the **Premium** bot: image cards are served from
  `storage.googleapis.com/uw-discord-bot-images/notifications/premium/<topic>/<uuid>.jpg`, and links carry
  `utm_content=custom_alert` in two channels. Whether that is a server subscription billed separately from avo's
  UW web plan was not visible from Discord. **Open question for avo.**
- Every outbound link carries `utm_source=discord&utm_campaign=<guild id>&utm_medium=foreign_discord_server` and
  `utm_content=notification` or `utm_content=custom_alert`. So there are two delivery mechanisms:
  **notification** (a fixed topic) and **custom_alert** (a UW custom alert routed to a channel).

## Channel by channel

| # | Channel (id) | Author | Mechanism | Post shape | Rate seen | Source behind it | Nearest API path / own build |
|---|---|---|---|---|---|---|---|
| 1 | news-feed (`1356612205742915724`) | UW Economic News | notification | plain text `h:mm AM - headline`, 1-3 headlines per message, no link, no image. **Every message arrives twice**, 20-60 s apart | 36 messages (18 distinct) in 17.5 h | wire headlines (text credits NBC, WSJ, Washington Post), "X Stock Price Prediction" articles, "<politician> has just disclosed new stock trades" | `/api/news/headlines`. Own: any headline feed; low value |
| 2 | trump-schedule (`1356895198180806749`) | UW Trump News + Schedule | notification | plain text `headline (Fri Nov 20, 12:52 PM EST)`; schedule items carry a Discord relative time and post about 5 min before the event; one bare ft.com link | 30 in 20 h, bursts during a speech | wire headlines, the White House public schedule, the disclosure line | `/api/potus/posts`, `/api/potus/schedule`. Own: not needed |
| 3 | live-option-flow (`1356897646769606716`) | UW Live Options Flow | **custom_alert** | embed. Title `Hot Contract - Ask Side / Bid Side` or `Interval (5 Min) - Ask Side / Bid Side`; contract (link), "Time and sales" (link), Overall or Interval Volume, Open Interest, Vol/OI, OTM %, Bid/Ask %, Premium, Average Fill, Multi-leg Volume %; footer "Happy Hunting!" | **30 posts in 20 minutes** (21:40 to 21:59 Amsterdam, the last 20 min before the close); nothing outside market hours | UW flow alerts over the options trade tape | `/api/option-trades/flow-alerts`, `/api/alerts`. Own: needs a trade tape with bid/ask side (IBKR or Cboe), same as the web "Live Flow" item |
| 4 | analyst-ratings (`1356897841317937213`) | UW Analyst Ratings | notification (premium image) | text line `SNPS - INITIATED AT BUY - Overweight - Barclays` + image card (target, action, rating, upside, analyst, chart of price vs every firm's target, consensus, Buy/Hold counts, "Source: Barclays, Nov 19, 2026") + buttons Interactive chart / All SNPS analyst ratings / All Barclays ratings | 12 in 29 h (about 6-8 a trading day) | analyst rating feed, filtered by UW ("based on automated filters") | `/api/screener/analysts`. Own: needs an analyst-rating source; we have none free |
| 5 | insider-trades (`1356898029482938485`) | UW Insider Trades | notification (premium image) | text line `UPST - BUY (Code P) - Common Stock - Paul Gu - Chief Executive Officer, Director` + image card (total value, shares, price, trade date, owned after, stake change, "Source: SEC Form 4 filed Nov 20, 2026") + buttons All UPST insider trades / All trades by the insider / **Form 4 on SEC.gov** | 12 in 80 min after the close; one post per Form 4 transaction (one person, 3 posts) | SEC Form 4, linked directly: `https://www.sec.gov/Archives/edgar/data/<cik>/<accession>/<accession>-index.htm` | `/api/insider/transactions`. Own: **the Form 4 build covers it**; only codes S and P were posted |
| 6 | congress-trades-fillings (`1356898202456166406`) | UW Congress Trade Filings | **both** | (a) custom_alert embed `Politician Trade - Alan Armstrong`: Buy/Sell with amount range, Asset, Notes, Rate/Coupon, Matures, Trade date, Filed date (days between). (b) notification: text line `GS - SELL - Ted Cruz - $250,001 - $500,000 - Traded Nov 11, 2026 - Filed Nov 20, 2026` + image card (owner account, party, chamber, price at trade, price now, since trade, "Source: Senate transaction report filed Nov 20, 2026") + buttons All trades by the politician / All GS congress trades | 12 in 2 min (one filing with 11 municipal bonds = 11 posts) | House and Senate disclosure reports | `/api/congress/recent-trades`. Own: free public source, low priority |
| 7 | stock-updates (`1356900096851050533`) | UW 52 Week High/Low Updates and UW Stock Updates | notification | embeds. `52 Week Low`: ticker and name (link to `/stock/<T>/overview`), "just hit a new 52 week low of $5.92", 52 week range, Price (% change), Marketcap. `Unusual Stock Volume`: "Trading at 3x average stock volume", Current volume, 30 Day average, Price, Marketcap | 12 in 4 min near the close | daily prices and volume | no dedicated path (see `UI-only-features.md`). Own: **a rule over daily bars**: new 52-week extreme; volume >= 3x the 30-day average (3x and 4x seen) |
| 8 | highest-volume-contracts (`1356902200349036594`) | UW Highest Volume Contracts | notification | embed "Unusual Whales Options Bot", title `Highest Volume Contracts / No Index/ETFs` (link to `/flow/hot_chains/v2?limit=50&issue_types[]=Common Stock&issue_types[]=ADR&order=volume&order_direction=desc`), an image of the `/highest_volume_contracts` table (15 rows: Ticker, Contract, DTE, Volume, OI, Vol/OI, OI +/-, Prev Vol, bull/bear premium bar), text "Type '/help' ..." | **every 15 minutes, two posts each time**: one image under `notifications/premium/`, one under `notifications/free/` | chain volume snapshot | `/api/screener/option-contracts` sorted by volume. Own: one chain snapshot with volume gives it (same table as Console `/moso`) |
| 9 | unusual-command-line (`1356903006175625266`) | | | not opened: avo does it together | | | |

## What this means for the migration

1. **Nothing in these eight channels is avo's own data.** They are UW feeds pushed into the server. If the bot goes,
   nothing of ours is lost; only the feed stops.
2. **What we can already replace:** insider-trades (Form 4 build; the bot itself links sec.gov), stock-updates
   (two rules over daily bars), highest-volume-contracts (a chain snapshot), congress (public reports).
3. **What needs a trade tape:** live-option-flow. The sample suggests the alert floors: Hot Contract volume
   >= 2,500 (lowest seen 2,503), Interval volume >= 1,000 in 5 minutes (lowest seen 1,055), premium >= about $84K.
   These are read off 30 posts, not from the alert's own settings.
4. **What we have no source for:** analyst-ratings; the two news channels (not needed for RevenueChaser).
5. **Tying the bot into our system:** the posts are machine-readable (fixed text lines and embed fields), so a
   reader of these channels could feed our store. That is the Discord-following route avo has ruled out for
   idea-creator; it is recorded here as possible, not proposed.
6. **Duplicates:** news-feed posts every headline twice and highest-volume-contracts posts a premium and a free
   table each time. This looks like the same topic subscribed twice (or the free and the premium bot both in the
   channel). `/configure` would show it; that is avo's to look at.

## Screenshots

| File | What | Captured (Amsterdam) |
|---|---|---|
| `ch1_news-feed_01.jpg` | news-feed, duplicate headlines | 17:49 |
| `ch1_news-feed_02_app-profile.jpg` | profile popout of "UW Economic News" | 17:49 |
| `ch2_trump-schedule_01.jpg` | trump-schedule | 17:50 |
| `ch3_live-option-flow_01.jpg`, `_02.jpg` | Hot Contract and Interval embeds | 17:50, 17:51 |
| `ch4_analyst-ratings_01.jpg` | analyst card and buttons | 17:52 |
| `ch4_analyst-ratings_02_leaving-discord-dialog.jpg` | Discord's link confirm | 17:52 |
| `ch4_analyst-ratings_03_interactive-chart-page.jpg` | the static chart page on UW's bucket | 17:53 |
| `ch5_insider-trades_01.jpg` | insider card and buttons | 17:53 |
| `ch6_congress-trades_01.jpg` | both congress formats | 17:54 |
| `ch7_stock-updates_01.jpg` | Unusual Stock Volume embeds | 17:55 |
| `ch8_highest-volume-contracts_01.jpg`, `_02_table-zoom.png`, `_03_premium-and-free-pair.jpg` | the 15-minute table, zoom, the pair | 17:55, 17:56 |
| `uw-discord-bot-page_01.jpg` | https://unusualwhales.com/discord-bot | 17:56 |

## Not done

- "All <ticker> analyst ratings", "All <firm> ratings" and "All <ticker> insider trades" targets were not read.
- No slash command was run, so command output (and whether results are live or delayed here) is untested.
- Older history was not scrolled; four channels are described from 12 posts.
