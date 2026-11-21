# Task 4 — what already exists and can be reused

## 1. In this repository

| Asset | Where | Why it matters |
|---|---|---|
| **The side and package rules** | `core/option_prints.py:44-60` | layer 2, half written and measured against UW's own tags (235/241) |
| **IBKR as a second IV provider, in production** | `rcdata/build/options/ibkr_iv.py` — `OPTION_IMPLIED_VOLATILITY`, 1-year daily bars, one request a name | proves the Gateway path works for an options measure, and already fills `iv_daily` as source `ibkr` |
| **A minimal TWS client we own** | `core/providers/ibkr_tws.py:1-33` — handshake, `startApi`, `reqContractDetails`, `reqHistoricalNews`, `reqMktData` (news), `reqHistoricalData` | the socket framing is already written; a chain or tape request is a new message type on an existing client, not a new subsystem. It deliberately avoids `ib_async` because that library asks for positions on connect |
| **Gateway login state** | `core/ibkr_login.py` | the health check the new lane would reuse |
| **Cboe as a keyless source, in production** | `rcdata/build/sources/cboe.py` — index history CSVs from `cdn-api.cboe.com` | a Cboe fetch already has a home, a pacer and a raw/parquet layout |
| **The provider seam itself** | `rcdata/needs/catalog.py` `providers=`/`fallbacks=`, `core/credentials.py` | a new provider is a module plus catalogue edits; boards do not change |
| **The call-accounting layer** | `rcdata/caps.py`, `core/providers/spend.py`, `ops.provider_calls_daily` | a new provider gets limits and a counter for free |
| **The parked research** | issue [#418](https://github.com/alsanvolkan/RevenueChaser-public/issues/418) (UW cost / Cboe / IBKR, parked by avo 5 Nov to December 2026) | this migration is that issue, unparked by the 8 December deadline |

## 2. Fincept Terminal

Surveyed on 20-21 November 2026; the write-ups are in `docs/v2/fincept/` (`data-sources.md`, 204 connectors;
`source-usage.md`, which screen uses which source; `live-walk-2026-11-21.md`).

- **Option chains: Cboe delayed first, Yahoo as fallback** — `scripts/derivatives/deriv_market.py:1-8`.
- **Paid depth: Databento**; brokers feed live quotes on the F&O screen.
- **No UW connector. No flow tape. No sweep detection.** Nothing in Fincept replaces layers 1 and 2.
- Licence AGPL-3.0: structure may be copied, source may not (`v2/README.md` decision 1).

## 3. The UW Discord bot feed (plan B, and a substitute for the hard items)

avo's server carries nine UW bot channels; the survey is in `/mnt/project-files/UWdependency/discord-bot/notlar.md`.
avo's direction, 21 November 2026: **if it is used, it is wired to RevenueChaser directly, not through
idea-creator**, and it is plan B for option flow — but it is a candidate substitute for the items we cannot build.

avo's classification of the channels:

| Class | Channels |
|---|---|
| **We can build it ourselves** | `live-option-flow` (= layers 1+2 of the options track) |
| **We can learn it and build it** | `unusual-command-line` (a command/query surface over our own data) |
| **Hard — needs a substitute source, and Discord is a candidate** | `insider-trades`, `analyst-ratings`, `congress-trades-fillings`, `news-feed`, `trump-schedule`, `stock-updates`, `highest-volume-contracts` |

Three things must be answered before any of that can be planned (all unverified, all for avo):

1. **Whose server is it?** A program can read a channel only with our own bot in that server (the server admin
   adds it) or with a user token, which is against Discord's terms. On avo's own server both bots sit cleanly.
2. **Does the bot feed depend on the UW plan that renews 9 December**, or on the server owner's plan?
3. Some channels post **rendered images** (`highest-volume-contracts`), so their numbers are not machine-readable
   without OCR.

### 3.1 The hard items, checked against the code

| Item | Verdict |
|---|---|
| **insider-trades** | **already ours, in production.** `rcdata/build/ownership/form4.py` reads Form 4 and 4/A from the EDGAR daily index; the need is `ownership.insider`, provider `sec` (`rcdata/needs/catalog.py:264`). UW's own `insider` client method has **no caller** (`01_dependency_inventory.md` §5). avo's EDGAR link is the same source we already read. Nothing to migrate |
| **congress trades** | not in the catalogue at all — nothing in production depends on it; it would be new work on a free source, not a migration |
| **analyst-ratings** | **the one genuinely missing item.** No need, no table, no source in this tree. Candidates: Yahoo (what Fincept uses), UW `/screener/analysts`, or the Discord feed. New work either way |
| **news-feed** | the News board is on **IBKR headlines** already (`core/providers/ibkr_tws.py`, avo's choice 9 Nov 2026) |
| **stock-updates (52-week high/low)** | computable from the prices store (`price_bar_daily`); no provider needed |
| **highest-volume-contracts** | a scan over the chain; needs the chain source of layer 3, not UW |

### 3.2 Congress trades — measured 21 November 2026

avo: "bunu da yapabiliriz". Checked, rather than assumed:

- **House**: the Clerk publishes a bulk file per year.
  `GET https://disclosures-clerk.house.gov/public_disc/financial-pdfs/2026FD.zip` answered **HTTP 200, 66,320
  bytes** on 21 Nov 2026 13:09 UTC; it holds `2026FD.txt` (**1,867 rows**) and `2026FD.xml`, columns
  `Prefix, Last, First, Suffix, FilingType, StateDst, Year, FilingDate, DocID`. `FilingType` `P` is a periodic
  transaction report; the `DocID` names the PDF of that filing. No key, no robots.txt (404 on
  `/robots.txt`), no sign-in.
- **Senate**: `efdsearch.senate.gov` is reachable, but its search sits behind an agreement page, so machine
  access needs a session and its terms must be read before anything is written. **Unverified.**
- **The work UW sells here is not the filings, it is the processing**: the transaction lines live inside the
  **PDF**, many of them scanned, and each has to be parsed and matched to a ticker. That is the whole cost.

Classification: **ours, with PDF/OCR parsing as the hard part.** Nothing in production depends on congress
data today (no need in `rcdata/needs/catalog.py`), so this is new work, not a migration — it only matters if
avo wants the board.

### 3.3 The bot itself, read from avo's screenshot (21 November 2026 14:09 Amsterdam)

Channel `-unusual-command-line`, server **"Traders' Pub"**, app **`Premium_UnusualWhalesBot`**, banner
"Unusual Whales Options Bot - All data is LIVE, unless otherwise specified", **103 commands**.

Two things that change the Discord route's feasibility:

1. The `/help` answer is marked **"Only you can see this"** — a slash-command reply is **ephemeral**, visible to
   the person who typed it. Another bot cannot read it. So the command surface (`/highest_volume_contracts` and
   the other 102) is **not harvestable by a reader bot**; only what the bot *posts publicly* into a channel is.
2. `/troubleshooting` is described as being "for the owner and the administrators of a server with a **premium
   subscription**", which says the feed hangs on the **server's** UW subscription, not necessarily on avo's. So
   avo's own plan ending on 9 December may not stop these channels — **still to be confirmed with the server
   owner**, but the earlier worry is weaker than it looked.

### 3.5 The channels themselves, read 21 November 2026 (supersedes §3.3's screenshot reading)

A read-only pass over the eight UW bot channels in Traders' Pub, 17:49-17:56 Amsterdam; nothing was written, no
command was sent. The record is `ui/discord-bot/` here and
`/mnt/project-files/UWdependency/discord-bot/discord-pass_2026-11-21.md` beside the thread. What it settles:

- **Nothing in those channels is avo's own data.** They are UW push-notification topics delivered into the server.
  If the bot goes, no data of ours goes with it — only the feed stops. That removes the Discord route from the
  "preserve before 8 December" list entirely (lane I is unaffected).
- **Already ours or nearly so:** `insider-trades` (one post per Form 4 transaction, and the post itself links
  sec.gov — only codes S and P seen, so the Form 4 build covers it), `stock-updates` (**two rules over daily
  bars**: a new 52-week extreme, and volume at 3× or more of the 30-day average), `highest-volume-contracts`
  (a 15-row table every 15 minutes — one chain snapshot with volume), congress filings (public reports).
- **Needs a trade tape with side:** `live-option-flow`, as everything else does. Read off 30 posts in the last
  20 minutes before the close, the alert floors look like Hot Contract volume ≥ 2,500, Interval (5 min) volume
  ≥ 1,000, premium ≥ about USD 84K — **read off the sample, not from the alert's own settings**.
- **No source on our side:** `analyst-ratings`, as §3.1 already said.
- **A second bill may be hiding here.** The image cards come from a bucket path `notifications/premium/`, and two
  channels carry `utm_content=custom_alert`; UW's own Discord-bot page says custom alerts to Discord need the
  **Premium Server Subscription, USD 124.99/month** (user tier USD 6.99). Whether Traders' Pub pays that
  separately from avo's UW web plan is not visible from Discord. **Question for avo** — see
  `05_migration_plan.md` §5 and risk R19.
- The ninth channel, `unusual-command-line`, was left alone: avo walks that one himself.

### 3.6 Plan B may not survive leaving UW at all (21 November 2026, the bot's own help)

The follow-up pass on the ninth channel read the bot's own help text, and it changes what plan B is worth:

- **Custom alerts posted into a channel are the alerts of ONE linked UW web account**, delivered by webhook, and
  they need a premium server subscription. The `custom_alert` feeds are `live-option-flow` and part of
  `congress-trades-fillings` — i.e. **exactly the feed we would be leaning on**. If the linked account is avo's,
  and his plan ends on 9 December, **those feeds stop with it.** Whose account is linked shows only in
  `/configure`, which was not opened.
- **Two UW bots are installed** in Traders' Pub — `Premium_UnusualWhalesBot` and the free
  `unusual_whales_crier` — which is why several feeds post twice.
- The help also says a "super buffet" UW subscriber with a linked Discord gets Premium Bot user privileges
  automatically, so some of what the server shows may be riding on a subscription rather than on the server.
- **Command answers are rendered images, not text** (`/flow`, `/flow_ticker`, `/oi_change`, `/congress_late`,
  `/netflow`; 103 commands in 23 topics). So the command surface is not harvestable even in principle, on top of
  the earlier finding that slash-command replies are ephemeral.

**So plan B is not a fallback for leaving UW.** At best it is a fallback for *someone else* still paying for UW.
It survives only in the narrow case where the linked account is not avo's and the server subscription is someone
else's — which is a question for avo, not an assumption to plan on.

### 3.4 Market-wide contract ranking (`highest-volume-contracts`, and our own `options.far_contracts`)

avo, 21 November 2026: "bu bizim üzerinde çalışmamız gereken bir şey. Tamam IBKR ve CBOE dedik. veya B planı
… Discord'daki bot arayüzü." Written as two routes:

| | **A — IBKR + Cboe (chosen direction)** | **B — the Discord bot feed** |
|---|---|---|
| Where the ranking comes from | our own scan over a chain we hold | UW's own ranking, already computed |
| Coverage | Cboe serves a whole chain per symbol with no line limit, so a market-wide scan means **one request per symbol**; IBKR's 100 market-data lines against 19,774 contracts in one chain (`rcdata/build/options/tables.py:37-39`) means IBKR cannot carry breadth — it carries SPX and the watch list live, Cboe carries the width |
| Latency | Cboe ~15 min delayed; IBKR real time on the narrow set | the bot's own cadence |
| Effort | the scan is ordinary code once lane B (the Cboe chain provider) exists | reading a **rendered PNG**: `highest-volume-contracts` posts its table as an image, so the numbers need OCR |
| Permission | none | needs our bot in that server (only its admin can add one); a user token is against Discord's terms |
| Honesty of the number | ours, reproducible, with its own as-of | UW's, and we cannot see the rule behind it |

**Direction: A.** B stays written down as the fallback, and it is worth nothing until the server-owner question
is answered. The universe cut for A (how many symbols a nightly market-wide scan fetches from Cboe) is decided
with measurement M1's contract counts, not guessed here.
