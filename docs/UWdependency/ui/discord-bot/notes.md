# UW Discord bot (server "Traders' Pub") — notes

Status: **plan B** (avo, 21 Nov 2026 14:02 Amsterdam). Used only if our own option-flow alert
(IBKR, tested against the UW API) cannot be built. The channels are listed in the idea-creator
Discord archive but **not followed**; nothing was exported.

## Screenshots (from avo, not from a browser session — no URL)

| File | Shows | Received |
|---|---|---|
| `channel-list_2026-11-21.png` | idea-creator hub, Discord > Channels: the 9 UW bot channels, all "Last export: never" | 2026-11-21 14:00 Amsterdam |
| `stock-updates_52w-low_2026-11-21.png` | Discord channel `-stock-updates`, app "UW 52 Week High/Low Updates" | 2026-11-21 14:03 Amsterdam |
| `highest-volume-contracts_2026-11-21.png` | Discord channel `-highest-volume-contracts`, app "UW Highest Volume Contracts" | 2026-11-21 14:03 Amsterdam |

## What `-stock-updates` posts (read from the screenshot)

One embed per event, title "52 Week Low" (a "52 Week High" variant is implied by the app name, not seen).
Fields: ticker + company name (link), the new low price, 52-week range, price with day change %,
market cap. Messages seen: TRAK, FLNG, GRBK, 20 Nov 2026 21:54-21:55 (Discord client local time).

## What `-highest-volume-contracts` posts (read from the screenshot)

The bot posts a **rendered image**, not text: the output of the slash command
`/highest_volume_contracts`, titled "Highest Volume Contracts / No Index/ETFs", dated Fri Nov 20, 2026.
Columns: Ticker, Contract (strike, C/P, expiry), DTE, Volume (sort key), OI, Vol/OI, OI +/-, Prev Vol,
and a bull/bear premium split bar with a percentage. 15 rows; on that day 14 NVDA 0DTE and 1 AAPL.
The same table is reposted with refreshed numbers. Consequence for an archive: the numbers live in a
PNG, so a text export would hold no values; reading them needs the image or the API.

## Channels and the nearest public API path (candidate mapping, NOT verified by a call)

| Channel | Nearest path in `../public_api_paths.txt` |
|---|---|
| analyst-ratings | `/api/screener/analysts` |
| congress-trades-fillings | `/api/congress/recent-trades`, `/api/congress/late-reports` |
| highest-volume-contracts | `/api/screener/option-contracts` |
| insider-trades | `/api/insider/transactions` |
| live-option-flow | `/api/option-trades/*` (flow alerts) |
| news-feed | `/api/news/headlines` |
| stock-updates (52-week high/low) | no dedicated path; possibly a `/api/screener/stocks` filter or an `/api/alerts` type — open |
| trump-schedule | `/api/potus/schedule` |
| unusual-command-line | bot slash commands; no API equivalent as such |

## avo's direction, 21 Nov 2026 14:04 Amsterdam

"zaten hazirda bu akis bizim icin mevcut, RC ye kendimiz baglayabiliriz bunu. Ideacreator de olmasina
gerek yok" — if used, the bot feed would be wired to RevenueChaser directly, not through idea-creator.

Open points before that can be planned (none verified):
1. Whose server is "Traders' Pub"? Reading a channel by program needs either our own bot in that server
   (only the server's admin can add one) or a user token (what DiscordChatExporter uses; automated use of
   a user account is against Discord's terms). On avo's own server both the UW bot and our reader bot
   could be added cleanly.
2. Does the UW bot's feed depend on the paid UW plan that ends 8 Dec, or on the server owner's plan?
3. Some channels post rendered images (highest-volume-contracts), so those values are not machine-readable
   without OCR.

## avo's build-or-keep call per channel, 21 Nov 2026 14:04 Amsterdam

| Channel | avo | Note |
|---|---|---|
| live-option-flow | we can build it | plan A: IBKR tape + our own rules, tested against the UW API |
| unusual-command-line | we can learn it and build it | the bot's slash commands; each is a query over data we would hold |
| insider-trades, analyst-ratings "vs" | hard | insider trades are SEC Form 4 filings (public, EDGAR); analyst ratings have no free primary source |

avo, 14:05: "yani discord uzerinden yapabiliriz" — the hard channels (insider-trades, analyst-ratings and
the like) are the candidates to take from the Discord bot feed. Still gated on open points 1 and 2 above.

avo, 14:06: the insider-trades posts link straight to the SEC filing index, e.g.
`https://www.sec.gov/Archives/edgar/data/1647639/000183281226000016/0001832812-26-000016-index.htm`
(not fetched from this thread). So the bot's insider feed is a pointer to EDGAR Form 4; the primary
source is EDGAR itself, which moves insider-trades from "hard" to "replaceable without UW".
avo, 14:06: "bunu bizde yapabiliriz" — insider-trades moves to the build-ourselves group (EDGAR Form 4).

## `-stock-updates`, second message type: "Unusual Stock Volume" (app "UW Stock Updates")

Screenshot `stock-updates_unusual-volume_2026-11-21.png` (from avo, 2026-11-21 14:08 Amsterdam).
Fields: ticker + name (link), "Trading at Nx average stock volume", current volume, 30-day average,
price with day change %, market cap. Seen: BIPC 3x, BSP 3x, PCAP 4x, 20 Nov 2026 21:57-21:58.
Rule as shown: current day volume / 30-day average volume, posted at whole multiples (3x, 4x).
avo: "bunu da yapabiliriz gibi duruyor" — inputs are daily volume history plus the running day volume;
an end-of-day version needs only daily bars, an intraday one needs a live or delayed quote source.
The same goes for the 52-week high/low type (daily high/low history plus the current price).

avo, 14:08, on `-highest-volume-contracts`: "iste bu zor". Why it is hard: it is a ranking over every
option contract in the market (volume, OI, Vol/OI, OI change, previous volume), plus a bull/bear premium
split that needs per-trade side. A per-ticker chain source covers the first five columns for a fixed
ticker list only; the split needs the tape. Nearest UW API path: `/api/screener/option-contracts`.

## `-unusual-command-line`: the bot's command interface

Screenshot `unusual-command-line_help_2026-11-21.png` (from avo, 2026-11-21 14:10 Amsterdam; avo ran
`/help` at 14:09). Read from it:
- The app is **Premium_UnusualWhalesBot** (verified app). Header: "All data is LIVE, unless otherwise specified".
- "There are currently **103 commands** available", browsed by topic dropdown + Prev/Next page; some topics
  carry examples or a video.
- `/troubleshooting` is "for the owner and the administrators of a server with a premium subscription",
  so the bot runs on a **paid premium subscription held for this server** (whose, not known).
- The `/help` answer is **ephemeral** ("Only you can see this").
- Above it, a chart command's controls are visible: Put & Call Premium / Net Premium toggles, day paging
  (7d <<, 1d <, Curr day, > 1d, >> 7d) and a "how many market days" dropdown.

avo, 14:10: this is what we must work on. Plan A = IBKR + Cboe, our own build. Plan B = use this Discord
bot interface.

Limits of plan B as an automated feed (from how Discord works, not tested):
- A slash command is started by a person. A program cannot start one except by automating a user account,
  which Discord's terms forbid. Another bot cannot invoke this bot's commands.
- An ephemeral answer is visible only to the person who ran the command; no reader bot sees it.
- What a reader can collect is the **automatic channel posts** (stock-updates, live-option-flow and so on),
  and some of those are images.
So plan B fits avo using the bot by hand, and reading the auto-post channels; it is not a query API.

Still open: the full list of the 103 commands (walk `/help` topic by topic) — that list is the spec for
what "our own command line" would have to cover.

## avo's explanation (21 Nov 2026 17:02 Amsterdam)
- "Traders' Pub" is the server avo set up with friends. A UW bot is attached to it; the bot runs on the UW API.
- Aim: see how the bot works and whether it can be tied into avo's own system.
- If we can do what the bot does ourselves, the bot is not needed; a record of it is kept either way.
- The Discord pass comes after the UW web survey, in a web window avo opened, by a method avo will explain.

## Browser pass (21 Nov 2026)

Done for the eight feed channels: see [`discord-pass_2026-11-21.md`](discord-pass_2026-11-21.md). The channel-to-API
mapping above was written from screenshots; where the two differ, the pass file is the one read from the live channels.
