# RevenueChaser v2 — screen-by-screen visual spec

- **Written:** 21 November 2026, Amsterdam, from a live read-only walk of Fincept Terminal 4.5.3 (Community) on
  the owner's Windows PC. The walk, with pixel sizes and verbatim wording, is
  [`live-walk-2026-11-21.md`](live-walk-2026-11-21.md); the earlier source-code reading is
  [`README.md`](README.md) and [`ui-structure.md`](ui-structure.md) (#1217 / PR #1218).
- **Status:** specification only. Nothing is built, merged, deployed or written to live data by this document.
- **The rule it serves** (owner, 20 Nov 2026): *"gorsel yapisinii bire bir alalim"* — Fincept's **visual
  structure is taken one to one, its colours are not.** v2 keeps our own theme (Mürekkep light, Gece dark) and
  the sizes and touch targets of [`../dashboard_ui.md`](../dashboard_ui.md); where the two disagree on a phone,
  our phone rule wins.
- **Licence:** Fincept is AGPL-3.0. Layouts, patterns and wording *ideas* are free to learn from; no code, no
  screen file and no string is copied from it into this repository. Every sentence quoted below is quoted as
  evidence of a pattern, and v2 writes its own.
- **Reading marks:** `[SEEN]` observed in the running application; `[DECIDED]` the owner's word, with the date;
  `[OPEN]` still to decide.

## 1. Scope, as the owner set it on 21 November 2026

| Area | Decision | Source |
|---|---|---|
| Crypto | **Out.** No crypto screen, no crypto widget. | `[DECIDED]` 00:17 |
| Portfolio | **In, and needed.** First version imports from IBKR and is **read-only**: positions, quantity, cost, cash. No orders, no writes. | `[DECIDED]` 00:18 |
| Equity Research | **In.** It is the shape of our per-ticker 360 page: Financials, Fundamentals, SEC 13F and news live under that one roof. | `[DECIDED]` 00:18 |
| News | **In, as an improvement.** We already have a News board; it moves onto this pattern rather than being rebuilt. | `[DECIDED]` 00:19 |
| AI Chat | **In.** (This reverses `ui-structure.md`, which listed it as not planned.) Answers cite our own data; a paid model call stays off until the owner turns it on in writing. | `[DECIDED]` 00:19 |
| Backtest | **In.** (D7 of the v2 plan said "backtesting later"; that line is corrected to "in scope, order to be set".) Our counterpart is the Hit Rate board. | `[DECIDED]` 00:19 |
| Settings, Grafana included | **First slice.** | `[DECIDED]` 20 Nov 23:42 |
| Data-source catalogue | Every source we *could* use is listed, not only the ones we use, with its state; a key can be added and tested from the screen. | `[DECIDED]` 00:23–00:24 |
| Trading, algo deployment, order tickets | **Out of v2.** Fincept's broker list is India-heavy and has no IBKR; our trade side is a separate question. | `[SEEN]` + scope |

## 2. The frame

Fincept's frame is eight rows deep `[SEEN]`. v2 keeps the idea and drops what our hourly data cannot honour.

| Fincept row | v2 | Why |
|---|---|---|
| OS title bar that marquees screen names | — | noise |
| App toolbar: menus · symbol search · LIVE dot · pin strip · clock · account | **one app bar**: our mark · **one command box** · data-freshness dot · clock (Amsterdam) · account | the command box is the single entry point: a ticker *or* a board name |
| Screen tab row (15 buttons, active = filled block) | **board tab row**, same shape; on a phone it folds into a menu, one board at a time | |
| Open-document tab row (dockable) | **kept, but only for sub-screens.** Clicking a board replaces the view; opening a ticker page from a board splits the view and gives the second pane its own tab, toolbar and status line | `[SEEN]`, and it is the behaviour that makes the terminal feel like a desk |
| Screen toolbar: name · state · item count · scope · LAYOUTS · COMPACT · REFRESH · ADD · SAVE · RESET | **kept in full.** Every board carries its own toolbar with the same button order | the count and the density switch are what make a dense board legible |
| Ticker tape | **off by default** | our data is hourly, not live; a moving tape would lie |
| Work area: panel grid + a fixed right rail | **kept**: a draggable grid with saved layouts, plus one fixed rail per board | |
| Status bar | **kept, and it is a contract** (section 4) | |

A floating round **ask-Claude bubble** sits bottom-right on every screen `[SEEN]`; v2 keeps it and wires it to
section 9.

## 3. The panel

Every Fincept panel has the same four parts `[SEEN]`, and that is what makes the screen read as one system.
v2's generic panel renderer (decision D2: the server describes a board, the client draws it) implements exactly
these:

1. **Header strip** (25 px there): a 3 px coloured tick · the title in small capitals · the scope after a dot
   (`MARKET INDICES · UNITED STATES`) · spacer · a **count badge** · an add button · a panel menu.
2. **Optional segmented control** under the header (`1D / 1W / 1M / YTD`, `GAINERS / LOSERS / MOST ACTIVE`,
   `PANELS | HEATMAP | MOVERS`). Exclusive, never a dropdown when there are five or fewer choices.
3. **Body**: a dense table (monospaced figures, numbers right-aligned, green and red deltas, a small range bar
   or sparkline inside the row), a treemap, a gauge, or a chart.
4. **Footer line** in small dim type that states **source, as-of and delay** — see section 4.

Table density `[SEEN]`: row 27 px, header 27 px, 11–13 rows visible in a panel, the whole terminal set in
**JetBrains Mono 14 px** with one `Default / Compact` density switch. v2 uses our own mono face at our own size,
keeps the one density switch, and on a phone falls back to stacked cards with 44 px targets.

**Tile pattern**, used on every summary strip `[SEEN]`: caps label · big value · a delta chip with an arrow ·
a comparison line (`FY2026 vs FY2025`) · optionally a mini sparkline under the tile. v2 uses this one tile
everywhere a number is headlined — Welcome, Earnings Radar, the ticker page, Settings counts.

## 4. Freshness and provenance — the thing worth stealing most

Fincept never hides where a number came from, and it says it in words, not icons `[SEEN]`:

- panel footer: `United States defaults · as of 23:36 (44m ago) · delayed up to 10 min`
- status bar: `120/120 quotes · ▲ 33 ▼ 87 = 0 · Updated 00:23:45 · Yahoo Finance · delayed up to 20 min`
- a method footnote under a chart, in full sentences, naming the rule that produced the line
- a **scope sentence** above a list that could be mistaken for the whole market:
  *"From the 120 symbol(s) in your panels — not the whole market."*
- a **lineage pane** under a surface: dataset, schema, symbology, symbols, range, rows, cost
- a sample-data banner that admits itself: *"the sample surface stays until it arrives"*

**v2 rule.** Every panel footer states `source · as of <time Amsterdam> · <age> · <delay or build id>`. Every
board's status bar states rows, the build or job that produced them, and the as-of. Every derived judgement
states its rule (section 6). A board that shows a subset says so in a sentence above the table. A screen that
shows sample or stale data says so in a banner rather than looking live.

## 5. The boards, screen by screen

### 5.1 Settings — the first slice `[DECIDED]`

Fincept splits it in two `[SEEN]`: a **quick view** inside Settings (four KPI tiles, a connection list, bulk
actions, and a link to the full screen) and a **full Data Sources screen** in three columns. v2 copies both.

**Left rail**, two groups of rows with a search box above them, exactly as there: *Shell* (appearance, density,
number and currency format, notifications, keyboard) and *Data* (sources, credentials, jobs, storage, Grafana,
security).

**Data Sources, three columns:**

1. **Sources** (the catalogue, widest column). Header `SOURCES` + a live `N shown` badge. A fuzzy search box
   that searches **within the selected category only**. Two dropdowns: kind and category. A checkbox
   `Only what works here` that hides everything unavailable. Table `SOURCE | CATEGORY | HERE`, sortable, ~33 px
   rows. **Every source we could use is listed, not only the ones we use** `[DECIDED]`.
   **The `HERE` column is the whole point**: one coloured state word, never an icon. v2's set:
   `works here` (green) · `no key needed` (green) · `optional key` (amber) · `key missing` (amber) ·
   `upstream broken` (red) · `not available` (grey). Our rows: WRDS, Compustat, SEC EDGAR, FINRA, Alpaca,
   Unusual Whales, IBKR (FTP borrow file and gateway as two rows), OpenFIGI, FRED, Wikipedia index lists, and
   every catalogue source we have not connected.
2. **Saved connections**. Filter box + `+ NEW`, a count badge, a `Only <source>` checkbox that re-labels itself,
   and an empty state that explains the next step in two sentences rather than showing a bare "none".
3. **Detail pane**. Avatar · `New: <source>` · `<source> · <category>` · `TEST` · `SAVE` · `DUPLICATE` ·
   `DELETE`. Tabs `SETTINGS | BROWSE | DATA`. With nothing selected the pane is an **info card**: what the
   source is, the equivalent command line, and a `THIS TYPE` key/value box (works here, reached through, browse,
   query, saved connections).
   - `SETTINGS` = a right-aligned label form, `*` on required fields, one `Tags` field, an `Enabled` checkbox.
   - `BROWSE` = what the source exposes (for us: datasets and jobs).
   - `DATA` = a sample fetch with a row cap.

**Keys** `[DECIDED]`. A key is added on this screen, `TEST` sends one real request, `SAVE` keeps it. The key is
stored encrypted on homesrv, never echoed back, never written into this repository, and the screen shows only
`present / missing / invalid`. Fincept's own wording is the model: *"Secrets are stored encrypted on this
computer (never in the connection table). EXPORT leaves them out unless you choose to include them, encrypted
with a passphrase."* The export dialog's two radio buttons (leave secrets out, recommended / include them under
a passphrase) are copied as behaviour.

**Grafana** `[DECIDED]`. The live health, fetch and data-health views are framed inside this Settings area, as
decision B2 requires — they are not re-drawn as our own panels.

**Guardrails, copied from Fincept's Security page** `[SEEN]`: an auto-lock with a timeout; an audit log of
security events with a timestamp and an event word; and one master switch, off by default, that decides whether
an agent may change anything — with the consequence spelled out in a paragraph rather than a tooltip. v2's
version of that switch governs the jobs an assistant may start.

A **state table** is the pattern for anything with an installed/signed-in shape (Fincept's AI-agent table):
columns for state, name, version, sign-in, default, path, and a detail card for the selected row.

### 5.2 The ticker page (Equity Research) `[DECIDED]`

The richest screen in Fincept and the model for our per-ticker 360 page `[SEEN]`.

- **Toolbar**: `TICKER` · symbol search · actions (`BACKTEST`, `CSV`, `+ WATCHLIST`, `OPEN IN ▾`) and a hint
  line naming the command-bar prefixes.
- **Quote line**: price, change, volume, high/low, market cap, our own verdict chip.
- **Two tab rows**: subject (`OVERVIEW FINANCIALS FILINGS ANALYSIS TECHNICALS PEERS NEWS SENTIMENT VALUATION
  DIVIDENDS EARNINGS OPTIONS ANALYST OWNERSHIP`) and, inside a subject, its own row (`OVERVIEW · INCOME
  STATEMENT · BALANCE SHEET · CASH FLOW · RATIOS & QUALITY · PEERS`). v2's subjects are our boards: Overview,
  Financials, Fundamentals, SEC 13F, Ownership, Relatedness, Value Chain, News, Earnings, Options, Hit Rate.
- **Return tile strip**: eight tiles `1W 1M 3M 6M YTD 1Y 3Y 5Y`, coloured by sign.
- **Chart block**: `LINE | CANDLES | INDICATORS ▾ | COMPARE ▾ | EVENTS` on the left, `LOG % =100` and the range
  buttons on the right, a legend naming every series, volume in its own sub-pane.
- **Right rail of stacked cards**: 52-week range (a bar with both ends labelled and `Last` marked), analyst
  targets (low / mean / high on one bar with a sentence under it), trading, valuation, shares, profitability.
- **Financials subject**: a context strip stating units, period basis and source (`USD · BILLIONS | ANNUAL |
  QUARTERLY | TTM | FY ends September · <source> · as of …`), **12 metric tiles**, then a 3-column panel grid in
  which **every panel ends in a plain sentence that states its own numbers** — e.g. *"FY2026 revenue $478.8B
  (+15.1% YoY) · operating margin 33.0% (+1.0 pp) · net margin 27.6%"*. The most recent period is banded in the
  accent colour in every chart.

### 5.3 The judgement cards — the pattern for every rule we own

Fincept's `ANALYSIS` tab is a 3 × 2 grid of cards `[SEEN]`. Each card is: a coloured top rule, a caps title, **a
single big coloured verdict word**, three metric lines, and **a rationale naming the yardstick** —
*"P/E 38.1 vs a usual 18-35 for Technology."*

v2 renders **every score, flag and rule we own** this way: Earnings Radar rules, the asymmetric-growth and
swing screens, data-health verdicts. One word, the numbers behind it, and the rule that decided it. No score
appears without its rule.

### 5.4 Boards that are lists (Markets, Screener, Watch lists)

- **Three views on one toolbar**: `PANELS | HEATMAP | MOVERS` `[SEEN]`. The heatmap prints its own colour rule
  on the screen (*"colour = today's change, ±3 % = full colour"*) and shows the group average on each block's
  header. The movers view prints its scope sentence and a `PANEL` column saying which list a row came from.
- **Index strip** of cards above the grid: caps label, big value, change, sparkline.
- **In-row graphics**: a day-range bar with both ends labelled, a 5-day sparkline, a relative-volume bar, and
  heat-filled `1M %` / `YTD %` cells.
- **Detail pane** on the right, opened by a `DETAIL` toggle, closable: price block, range buttons, chart, a
  two-column stat grid, then footer actions that jump to the ticker page, news or the watch list.
- **Screener**: a left rail of saved screens grouped `LIVE / MOVERS / STRATEGIES`, then a **screen builder** of
  three blocks — `UNIVERSE`, `CRITERIA` (a row = field · operator · value · unit · remove, plus `+ ADD
  CRITERION` and a help line explaining `K / M / B / T` and percent points), `SORT`. Paging as
  `Rows [100] ◀ 1-100 / 444 ▶`. Our filter rules stay exactly as `revenuechaser-conventions` defines them; only
  the shape changes.

### 5.5 Relatedness and Value Chain (Relationship Map)

Fincept's closest screen `[SEEN]`, and it is a three-toolbar screen worth copying whole:

1. subject + analyze + history arrows + a `Loading X · 7 of 11 sections` progress phrase;
2. **layout** (`TIERED | HIERARCHY | RADIAL | FORCE | SANKEY | MATRIX`), **edge weight** (`% HELD | VALUE |
   CHANGE | ρ CORR`), **depth** (`1 HOP | 2 HOPS`), fit, legend, tables, export, refresh;
3. **`SHOW` chips with counts** that toggle each relation class on and off.

Then a 10-tile KPI strip, a canvas with a legend card and a centre node card carrying a stacked share bar, and a
**bottom dock whose tabs are the relation classes**, each with a donut, a one-sentence summary, a method note
and a ranked table with an inline `% held` bar. Sections that have not arrived are grey `Loading…` cards;
classes with no data say so in a sentence. v2 maps this onto Value Chain, Relatedness and Co-movement, with our
own classes (customers, suppliers, peers, co-movement, holders).

### 5.6 Portfolio `[DECIDED]`

Fincept's empty state is three cards — create, import JSON, load a demo — each with a two-line explanation
`[SEEN]`. The filled workspace was not opened (the walk did not write data into the owner's installation), so
the table shape below is taken from the trading screen's positions table and the watch-list table, which share
it `[SEEN]`.

v2's Portfolio:
- **source**: an IBKR import, **read-only** in the first version; no order path, no broker write.
- **positions table**: `Symbol | Opened | Side | Qty | Avg price | Last | P&L | P&L % | Weight`, with the same
  in-row graphics as the watch lists.
- **cards**: value and day P&L, allocation donut by sector, largest positions, ex-ante risk (volatility, beta,
  contribution by holding) — mirroring Fincept's `Portfolio Summary` / `Portfolio Performance` /
  `Portfolio Risk` tiles.
- every panel states the import's as-of, as section 4 requires.

### 5.7 News `[DECIDED]`

Keep our board, take the shape `[SEEN]`:
- a filter row of category chips, an age row (`1H 6H 24H 48H 7D 30D`), a sort row (`REL | NEW | WIRE`);
- a **feed-health row**: feeds, articles, clusters, sources, how many are current and how many paused, and a
  tone bar with the count of positive and negative items;
- the feed itself as **one dense line per item**: age · unread dot · CAPS SOURCE · headline · right-aligned
  ticker chips · two tiny bars for impact and sentiment;
- a context strip that says, in words, whether a filter is on: *"… the feed is not filtered."*

### 5.8 Backtest / Hit Rate `[DECIDED]`

Fincept has two `[SEEN]`: a rule builder with an instant backtest beside it (Algo), and a deeper backtest screen
of its own. v2 takes the **deeper one** and leaves rule-authoring for later:
- a setup line: symbols, period, bar size, capital, benchmark, with a `DONE` badge, an as-of and a
  `⚠ N NOTE(S)` chip;
- **10 metric tiles**, each with a sub-line that names the comparison (`SHARPE 0.06 (rf ^IRX 3.80%)`,
  `VS SPY -36.8 pp (SPY +57.7% · α -2.2% · β 0.41)`);
- a left rail of collapsible blocks — strategy parameters, sizing and risk, **costs and execution** (with the
  fill rule written out: *"signal on the close of bar t, filled at the next bar's open, no look-ahead"*), data
  and its adjustment, reset;
- content tabs `OVERVIEW | PERFORMANCE | RISK | TRADES | EXPOSURE | COSTS | MONTE CARLO | COMPARE | ASSUMPTIONS
  | RUNS`, with **ASSUMPTIONS carrying a count** so the notes cannot be missed;
- an equity-vs-benchmark chart with numbered trade markers and a drawdown sub-chart, a monthly heat grid, a top
  drawdowns table including the ongoing one.

### 5.9 Derivatives and the surfaces (SPX Gamma, Implied Probability)

A calculator screen `[SEEN]`: input cards on the left, a `RESULTS` panel on the right with a 9-tile grid, each
tile carrying its unit or method in a dim line (`CONVEXITY 4.9107 (years²)`), a chart, and a **method footnote
in full sentences**. Under a surface, the three panes `RAW DATA | LINEAGE | STATUS / ERRORS`. v2 adopts the
lineage pane for every derived surface we publish.

### 5.10 Dashboard / Welcome

A free widget grid plus a fixed **pulse rail** `[SEEN]`. The rail is the clearest panel-anatomy example:
sections of 32 px heads, a big composite number with its state word beside it, breadth rows with a two-segment
bar, mover rows, and a market-hours list reading `After hours · 1h 36m`. v2's rail: data freshness, running
jobs, today's alerts, next earnings, market hours.

## 6. The widget catalogue `[SEEN]`

`Add Widget`: a search box, category chips (`ALL | TOOLS | TRADING | RESEARCH | MARKETS | PORTFOLIO`), a
two-column card grid — icon, name, a category badge, and **two lines that say what the widget is for** — then
`CANCEL` / `ADD WIDGET`. 54 widgets, each with a one-sentence description; several of those sentences also
state the scope honestly (*"of a named basket …, not the whole exchange"*) or the precondition (*"needs a
connected F&O broker"*).

v2 ships the same dialog over our own panels, and **every panel must carry a one-sentence description and an
honest scope**. The full 54-row list is in the walk notes as a source of ideas, not a to-do list.

## 7. Empty, loading and error states — copy the discipline

| situation | Fincept `[SEEN]` | v2 |
|---|---|---|
| loading a table | skeleton bars in the real column layout + a strip naming what is running + a progress line, repeated in the status bar | same |
| loading part of a graph | the missing sections drawn as grey `Loading…` cards | same |
| nothing configured | a card that says what the thing is and what the next step is, with that step as a button | same |
| a class with no data | a sentence: *"Customers and suppliers are not available…"* | same |
| sample data on screen | a banner that says it is sample and what it is waiting for | same |
| gated by cost | the panel shows its description, the price per call and a `LOAD` button; it never fetches on its own | same, for anything that spends money or a long job |
| unsaved edit | a modal naming what is unsaved and offering `Discard` / `Cancel` | same |

## 8. Number and currency formatting

Fincept gives formatting a whole settings page with **six live preview tiles** `[SEEN]`: a price, a converted
total with the rate and its timestamp underneath, a loss, a pence-quoted London price, a lakh/crore amount, and
a sub-cent crypto price. Rules worth taking: prices stay in the instrument's own currency while totals convert;
a mixed-currency column prints the ISO code on every cell; a rate is marked stale after a set age; prices keep
the precision their market quotes.

v2: one formatting settings page with a live preview; totals in the portfolio's base currency; the as-of and the
rate shown wherever a conversion happened; a staleness age for every rate.

## 9. AI chat `[DECIDED]`

Fincept's shape `[SEEN]`: sessions on the left; a centre empty state with **five columns of suggested prompts**
(markets, company research, portfolio, macro, code/data), each card holding the real prompt text; a right rail
showing attached context, the tool count by group, the message count and saved prompts; a composer with the
keyboard hints printed under it and the token/reply budget beside the send button; and the sentence *"nothing is
sent until you press Send."*

v2's version answers from **our** data — board payloads and the ticker page — and every answer cites its source
rows. Paid model calls stay off until the owner turns them on in writing, and the screen says which model would
answer and what it would cost before anything is sent.

## 10. What v2 does not take

Equity Trading and the order ticket; broker accounts (the list is India-heavy and has no IBKR); algo deployment;
the node editor; the notebook; QuantLib's paid endpoint catalogue; crypto; geopolitics and maritime; credits,
plan badges and upgrade walls. Our counterparts with nothing on their side: Earnings Radar, the data-health
boards, and the job runner.

## 11. Open questions `[OPEN]`

1. The filled Portfolio workspace was not seen; the table above is inferred from two other screens that share
   it. Worth one more look once v2's own table exists.
2. Panel drag, resize, saved layouts and the density switch were not exercised, so the saved-layout contract is
   specified from the buttons, not from behaviour.
3. Whether v2's board tab row keeps 15 slots or fewer depends on the board list we end with.
