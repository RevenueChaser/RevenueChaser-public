# RevenueChaser v2 — design contract (web and the Android app)

    contract_version: 1

**What this is.** One versioned description of the v2 design, written **once for both surfaces**: the web app in
`v2/web/` and the Android app of run plan step 18. It is a file, not a picture. A token, a scale, a state or a
component is defined **here**, and both surfaces implement what is written here.

**Why it exists.** avo, 21 Nov 2026 16:51 Amsterdam: *"Ilk basta yapacagimiz islerden biri tasarima karar vermek
olmali"* + *"Hem web hemde apk icin"*. On the card at 16:56 he chose option **A, "Tek tasarim sozlesmesi, once"**:
one shared contract, settled before step 8, and both surfaces implement it. Before that decision the Android app
was to inherit its design from whatever the finished web screens happened to settle on, and the approved mock
covered desktop widths only — so the two surfaces would have been designed twice, at different times, by
different threads.

**What it replaces.** Nothing that was approved. The 20-screen mock (`v2/mock/index.html`, step 2, approved by avo
21 Nov 2026 10:06) is this contract's **input**: it is not re-drawn, and no new web screenshot-approval round is
asked for. What avo approves here is the contract, not another picture — which is what keeps run-plan decision 3
("one approval only") workable: a later v2 screen that follows this file merges on green CI.

## 0. How to read it, and precedence

1. avo's newest words win over this file.
2. claude-coordinator `vault-memory/rules/rules.md` and `rules/ui-design.md` win over this file where they speak.
3. This file wins over the visual spec (`docs/v2/fincept/v2-visual-spec.md`), the mock and any plan file, for
   anything it states. The spec stays the source of the *intent* behind a shape; this file is the source of the
   shape itself.
4. `ref/design-system/tokens.css` in claude-coordinator wins over this file for a **token value**. This file
   quotes it; it never decides it.

**Amending it.** A v2 screen that needs a token, a scale, a state or a component this file does not define
**amends this file in the same PR**, and bumps `contract_version` when it changes something already built. A new
*colour* is not amendable here: it is a new token in `ref/design-system/tokens.css` first (DESIGN.md §1, "Names,
not hex"), then quoted here.

## 1. Where every value in this file comes from

| Source | What it gives |
|---|---|
| claude-coordinator `ref/design-system/tokens.css`, `tokens.json`, `DESIGN.md` | every token value, the scales, the contrast rule, the shell breakpoints |
| claude-coordinator `vault-memory/rules/ui-design.md` | the fixed target screens, cell grid, "same order, same place", currency symbols, board language, less-text density |
| claude-coordinator `vault-memory/rules/android-apps.md` | the phone app's compact sizes, parity rule, emulator-first order |
| `docs/v2/fincept/v2-visual-spec.md` §2–§8 | the frame, the panel's four parts, the freshness line, the state table, the formatting rules |
| `v2/mock/index.html` + its README | the approved shape of all 20 screens |
| `v2/README.md` (stack ADR) | React 19 + Vite, plain CSS, uPlot, no CDN, licences |
| `v2/web/src/theme/tokens.css` | the copy of the token file the web build reads; §2's table is compared against it in CI |

## 2. Tokens

**The token file is the one source.** Components on both surfaces use **token names**, never a hex value. The web
reads `v2/web/src/theme/tokens.css` (a byte-faithful copy of the design system's file, ADR decision 5). The
Android app reads `ref/design-system/tokens.json` through a generated `RcTokens` object — it **never retypes a
hex value**, for the same reason the web does not.

Dark is the default on every device and is stored as the *absence* of the `rc-theme` key; `light` and `auto` are
stored (`v2/web/src/theme/theme.ts`). Android follows the same three values and the same default.

### 2.1 Scale tokens

| Token | Value |
|---|---|
| `--font-sans` | Inter,system-ui,-apple-system,'Segoe UI',Roboto,sans-serif |
| `--fs-xs` | 11px |
| `--fs-sm` | 12.5px |
| `--fs-base` | 14px |
| `--fs-md` | 16px |
| `--fs-lg` | 20px |
| `--fs-xl` | 26px |
| `--sp-1` | 4px |
| `--sp-2` | 8px |
| `--sp-3` | 12px |
| `--sp-4` | 16px |
| `--sp-5` | 24px |
| `--sp-6` | 32px |
| `--sp-7` | 48px |
| `--r-sm` | 6px |
| `--r-md` | 10px |
| `--r-lg` | 14px |
| `--r-pill` | 999px |
| `--elev-1` | 0 1px 2px var(--shadow) |
| `--elev-2` | 0 12px 32px var(--shadow) |
| `--touch` | 44px |

### 2.2 Colour tokens — "Gece" dark, "Mürekkep" light

46 tokens, both schemes. CI compares this table against `v2/web/src/theme/tokens.css`
(`v2/tests/test_design_contract.py`), so the file and the contract cannot drift apart.

| Token | Dark | Light |
|---|---|---|
| `--bg` | `#11161D` | `#F6F5F1` |
| `--fg` | `#D5DBE3` | `#2E2C28` |
| `--bright` | `#F1F4F8` | `#1A1916` |
| `--card` | `#192029` | `#FFFFFF` |
| `--card-2` | `#1F2731` | `#F3F1EC` |
| `--border` | `rgba(213,219,227,.10)` | `rgba(40,36,30,.12)` |
| `--sidebar` | `#141A22` | `#EFEDE7` |
| `--pos` | `#6CC497` | `#2E7652` |
| `--neg` | `#E98A7F` | `#B0443A` |
| `--amber` | `#E0B060` | `#9A6212` |
| `--sky` | `#8DB8DA` | `#2F6690` |
| `--muted` | `#98A2AF` | `#67635B` |
| `--accent` | `#8DB8DA` | `#2F6690` |
| `--accent-soft` | `rgba(141,184,218,.14)` | `rgba(47,102,144,.10)` |
| `--pos-soft` | `rgba(108,196,151,.12)` | `rgba(47,122,85,.10)` |
| `--neg-soft` | `rgba(233,138,127,.12)` | `rgba(176,68,58,.09)` |
| `--amber-soft` | `rgba(224,176,96,.12)` | `rgba(154,98,18,.10)` |
| `--focus` | `#8DB8DA` | `#2F6690` |
| `--input-bg` | `#1E2631` | `#FFFFFF` |
| `--input-border` | `#323C49` | `#D6D2C8` |
| `--hover` | `#212A35` | `#EFECE5` |
| `--topbar` | `rgba(17,22,29,.85)` | `rgba(246,245,241,.85)` |
| `--nav-fg` | `rgba(241,244,248,.72)` | `#4A4741` |
| `--nav-on` | `#26303C` | `#E9E5DC` |
| `--hover-faint` | `rgba(255,255,255,.03)` | `rgba(40,36,30,.04)` |
| `--frame-bg` | `#11161D` | `#F6F5F1` |
| `--overlay` | `rgba(17,22,29,.72)` | `rgba(246,245,241,.75)` |
| `--scroll-thumb` | `#3C4655` | `#C4BFB3` |
| `--scroll-thumb-hover` | `#4C5767` | `#A9A396` |
| `--scroll-track` | `#141A22` | `#EEEBE4` |
| `--primary-bg` | `#E6EBF1` | `#2E2C28` |
| `--primary-fg` | `#11161D` | `#FAF9F6` |
| `--oi-bg` | `rgba(25,32,41,.6)` | `rgba(255,255,255,.7)` |
| `--scrim` | `rgba(0,0,0,.5)` | `rgba(30,28,24,.32)` |
| `--shadow` | `rgba(0,0,0,.35)` | `rgba(30,28,24,.10)` |
| `--badge-blue` | `#8DB8DA` | `#2F6690` |
| `--badge-gray` | `#A3ACB8` | `#67635B` |
| `--hover-soft` | `rgba(255,255,255,.05)` | `rgba(40,36,30,.06)` |
| `--hover-day` | `rgba(255,255,255,.08)` | `rgba(40,36,30,.09)` |
| `--gex-pos-bg` | `rgba(108,196,151,.20)` | `rgba(47,122,85,.14)` |
| `--gex-pos-fg` | `#CDEEDC` | `#1F5A3D` |
| `--gex-neg-bg` | `rgba(233,138,127,.20)` | `rgba(176,68,58,.12)` |
| `--gex-neg-fg` | `#F6D3CE` | `#8A3128` |
| `--data-1` | `#4F93D2` | `#2A6FB0` |
| `--data-2` | `#D9773F` | `#C0602E` |
| `--grid` | `rgba(213,219,227,.07)` | `rgba(40,36,30,.08)` |

### 2.3 Two notes on colour that a reader will otherwise trip over

- **Light `--pos` is `#2E7652`.** `#2F7A55` measured 4.44:1 on `--sidebar`, under AA, and was moved on
  12 Nov 2026. v2 is already correct — both the design system's file and `v2/web/src/theme/tokens.css` carry
  `#2E7652`. The drift that issue **#1247** reports is the **old dashboard's**: `core/reporting_common.py`
  `THEME_TOKENS` light `pos` is still `#2F7A55` (line 83 on `4c78fabd`). Nothing in v2 changes for it, and the
  run plan already placed that one-line correction as a rider on the next PR that touches `reporting_common.py`.
  It is recorded here only so that nobody "fixes" v2 toward the wrong value.
- **The categorical series ramp `--c1 … --c6` is not in the token file yet.** `DESIGN.md` §4 decides it —
  `#0C87CC #C77C09 #0A9E6E #8B5CF6 #E8445F #2F9E8F`, in that order, validated for lightness band, chroma floor,
  colour-blind separation of adjacent pairs and 3:1 against both surfaces — but `tokens.css` defines only
  `--data-1` and `--data-2`. Because `v2/web/src/theme/tokens.test.ts` fails any `var(--name)` the token file
  does not define, **a categorical chart in v2 is blocked until those six tokens are added to
  `ref/design-system/tokens.css`** (one change, in claude-coordinator, where colour is owned). Until then: a
  one- or two-series chart uses `--data-1` / `--data-2` and is not blocked. §10 states the rule; §14 carries the
  dependency. The order is part of the decision — a reorder needs re-validation.

## 3. Type and numbers

- **Inter**, self-hosted (SIL OFL-1.1), never a font host. The web's `@font-face` arrives with step 8 and
  `tokens.test.ts` fails a font rule pointing at a file that is not there. Android ships the same family.
- **Icons of one row sit on one line and in one size.** A font glyph (★, ◈, ☰) carries its own metrics and
  shifts against its neighbour, which is visible the moment two sit side by side (avo, 21 Nov 2026 16:15:
  *"simgeler ayni hizada olsun"*). Every icon is therefore an **SVG in a fixed box** — 12 px inside the watch-list
  control, 16 px in the bottom bar and the app bar — centred in that box, so a change of row height never moves it.
- **Every number is `font-variant-numeric: tabular-nums`** (Android: the equivalent `fontFeatureSettings("tnum")`).
- **Body text is `--fs-base` (14 px).** The scale is the only source of a text size; a component never names a px.
- **Value and change in one cell:** the value on line 1, its Δ% under it, small and coloured. There is **no**
  separate Δ%-column group. (avo, 12 Nov 2026: *"daha az yer kaplar ve okumasi kolay olur"*.) This is the rule for
  a **per-period** figure, such as a quarter's shares and its change against the quarter before.
- **A price change is shown over two horizons, `1D` and `1W`** (avo, 21 Nov 2026 16:20). `1D` is the previous
  close against the last price; `1W` is five trading days. Both definitions are written in the panel footer, not
  left to the reader, and a single unlabelled "change" column is not allowed on a price row.
- **The two horizons sit under the price, in the price's own cell**, not in two columns of their own (avo,
  21 Nov 2026 16:28: *"1D ve 1W current pricein altinda olmali, eskisi gibi"*). They are **not labelled on the
  row**: the header carries the names once, on two lines — `Price` above `1D | 1W` — and in the row the two
  values are separated by a thin muted `|` (avo, 21 Nov 2026 16:37-16:38: *"1D 1W yazmana gerek yok"*,
  *"% degerlerini | ile ayirsan yeterli"*). **That separator is the cell's centre line, and it stands exactly
  there** (avo, 21 Nov 2026 16:42: *"orta cizgisini tam orasina koy, biraz logic"*): the column is sized to the
  widest price, the `|` sits at its midpoint, `1D` is right-aligned against it and `1W` left-aligned, so the
  divider runs straight down the price's own middle and both percentages line up down every row — §11's cell
  rule holds inside a cell as well as between cells.
- **A currency is its symbol, not its code:** `$`, `€`, `£`, `¥`, `₺`. Said **once** — in the column header or
  before the figure (`$1.2B`) — never after every value. A code only where two currencies share one symbol in the
  same view (`US$` / `C$`).
- **Formatting rules both surfaces implement** (spec §8): a price stays in the instrument's own currency; a total
  converts to the portfolio's base currency and shows the rate **and its as-of** wherever a conversion happened;
  a mixed-currency column prints the code on every cell; every rate has a staleness age; a price keeps the
  precision its market quotes. One Settings page owns these, with a live preview — a format rule is only
  judgeable against a real string.
- **English, every string** a screen, banner, badge, empty state, alert or help line shows, including times
  ("2 min ago"). Turkish is only what Claude writes **to avo**. (avo, 19 Nov 2026 13:21: *"Turkce hic sey
  olmamali, hersey ingilizce"*.)

## 4. Shape

- **Radius:** `--r-sm` (6) for controls, `--r-md` (10) for cards, panels and tables, `--r-lg` (14) for dialogs,
  `--r-pill` for chips.
- **Elevation, three levels and no fourth:** border only; card (`--elev-1`); dialog or popover (`--elev-2`).
- **Spacing is the 4 px scale**, `--sp-1 … --sp-7`. A gap, padding or inset that is not on the scale is a defect.

## 5. The two surfaces: sizes, shells, touch

The surfaces are **not** two renderings of one layout. Each has its own shape, stated here so neither invents one.

### 5.1 Web — desktop only

| | |
|---|---|
| Target widths | **1187 px** (laptop; 64 px icon rail, board gets ~1123 px) and **1884 px** (extra screen; 240 px sidebar, board gets ~1644 px). avo's real `window.innerWidth`, measured 12 Nov 2026. |
| Shell | below 1440 px a 64 px icon rail, each item a 44 px icon with its name as a tooltip; from 1440 px a 240 px sidebar. |
| Screenshots | 1187 and 1884, light and dark, from CI's `screenshots-v2-web` artifact. |
| Touch target | 44 px (`--touch`) for every control. **One exception, avo's:** the symbol tile is drawn small (§9.1), and its hit area, not its drawing, carries the target — at least the row's height. The separate 36 px bookmark button of the old dashboard does not exist in v2 (§9.1). |
| No sideways scroll | a board fits its pane at 1187 px: fewer columns, value and change stacked, detail behind a row click. |

**v2 web is not given a phone layout.** avo decided on 21 Nov 2026 00:41 that the phone view **is** the native
Android app (and 14 Nov 23:48: the website's phone layout is not designed further). So no v2 web screen is drawn,
screenshot or approved at 412 or 720 px, and the mock is desktop-only by the same decision. Where a v2 web page
is nevertheless opened on a phone it must stay **readable** — single column, nothing clipped, no horizontal page
scroll — but that is a floor, not a design round.

### 5.2 Android — the phone

| | |
|---|---|
| Device | realme GT2 Pro: **411 × 806 dp** is the viewport avo actually reads (the Claude app's first screen); screen 412 × 919; DPR 3.5. The emulator matches it with `adb shell wm density 420`. |
| Shape | **single column, full-width cards.** A table never scrolls sideways: it becomes stacked row cards. Charts scale to their container. |
| Compact sizes, avo's exception to 44 px (21 Nov 2026 12:11, Energy canvas: *"44px den de asagi dusebilirsin"*) | rows and buttons **36 dp**, top bar **48 dp**, cards **12 dp** inside and **8 dp** apart. |
| Explanations | behind a click: a screen's explanatory sentences live in one closed "About these figures" fold at the bottom. **Warnings stay in view** (missing prices, stale reads, sample data). |
| Grouping | rows that belong together are **one card with a thin line between them**, not separate boxes with gaps. Headers are more prominent than body rows. |
| Figures | as tiles, two per row; a line under a figure is **data**, never a description. |
| Navigation | five bottom-bar destinations, **grouped as the dashboard's own headers are** (avo, 21 Nov 2026 16:18): **Welcome · Watch lists · Research ▴ · Screeners ▴ · More ▴**. The first two open a board directly; the three marked ▴ open a small menu **upward** from the bar, listing that group's boards — Research: News, Earnings Radar, SPX Gamma, Implied Probability, Financials; Screeners: Sector Rotation, Asymmetric Growth, Swing Potential, Fundamentals, Hit Rate; More: Classification, Ownership and Ops. Swipe moves between the bar's destinations; back from a destination goes to Welcome; back from Welcome closes the app. |
| Charts | **native** (run plan decision 5), drawn from the same door payloads and schemas as the web. §10 is what they share. |
| Screenshots | emulator, at his width, light and dark, onto the review canvas — **before** any APK, and an APK only on avo's word. |

## 6. The frame

Eight rows in the reference terminal; v2 keeps seven and drops one (spec §2). Both surfaces carry the same
**content**, in the shape their shell allows.

| Part | Web | Android |
|---|---|---|
| App bar | our mark · the command box · the data-freshness dot · the clock (Amsterdam) · the account | 48 dp top bar: mark · search icon opening the command sheet · freshness dot · overflow |
| Board tab row | the same shape as the reference: one filled block per board, 12 visible and the rest behind an overflow | the bottom navigation bar's destinations, one board at a time, the rest in a sheet |
| Document tab row | **kept, for sub-screens only.** Clicking a board replaces the view; opening a ticker page from a board **splits** the view and gives the second pane its own tab, toolbar and status line (60/40 at 1187 px, side by side at 1884 px) | **no split on a phone.** The navigation back stack carries it, and an "Open pages" sheet lists what the split would have shown |
| Screen toolbar | every board carries it, same button order: name · state · item count · scope · LAYOUTS · COMPACT · REFRESH · ADD · SAVE · RESET | one row of the same actions in the same order, the tail behind an overflow menu |
| Ticker tape | **off.** Our data is hourly; a moving tape would lie | not present |
| Work area | a draggable panel grid with saved layouts, plus one fixed rail per board (freshness, running jobs, today's alerts, next earnings, market hours) | the panels stacked in one column; the rail's five items become the first card |
| Status bar | rows, the build or job that produced them, and the as-of | the same line under the content, 36 dp |
| Ask-Claude bubble | a floating round button, bottom right, on every screen | a FAB, bottom right |

## 7. The panel

**Four parts, always, on both surfaces** (spec §3). This is what makes a screen read as one system.

1. **Header strip** — a 3 px coloured tick · the title in small capitals · the scope after a dot
   (`MARKET INDICES · UNITED STATES`) · spacer · a **count badge** · an add button · a panel menu.
2. **Optional segmented control** under the header (`1D / 1W / 1M / YTD`, `GAINERS / LOSERS / MOST ACTIVE`).
   Exclusive, and **never a dropdown at five or fewer choices**.
3. **Body** — a dense table, a tile strip, a chart, a map, a gauge or a treemap.
4. **Footer line**, small and dim, in this exact order:

       source · as of <HH:MM Amsterdam> · <age> · <delay or build id>

   for example `WRDS · as of 23:36 · 44m ago · build 1f2c9ab`.

Every panel also carries **a one-sentence description and an honest scope** (spec §6), shown in the widget
catalogue and in the panel menu. A board showing a subset says so in a sentence above the table: *"From the 120
symbols in your panels — not the whole market."*

**Density:** one `Default / Compact` switch per board, in the screen toolbar; 11–13 rows visible in a panel at
Default. On Android there is no density switch — the phone is Compact.

## 8. States — they are the design, not an afterthought

Spec §7, with each surface's component named. A screen is not done until every row below that can happen on it
is implemented.

| Situation | What is shown | Web | Android |
|---|---|---|---|
| A table is loading | skeleton bars **in the real column layout**, a strip naming what is running, a progress line, repeated in the status bar | `SkeletonRows` | `RcSkeletonRows` |
| Part of a graph is loading | the missing sections as grey `Loading…` cards; never an empty space | `SkeletonRows` | `RcSkeletonRows` |
| Nothing configured | a card saying what the thing is and what the next step is, **with that step as a button** | `NextStepCard` | `RcNextStepCard` |
| A class has no data | a sentence: *"Customers and suppliers are not available for this name."* Never a blank panel | `Notice` | `RcNotice` |
| Sample data on screen | a banner that admits it and says what it is waiting for | `Banner` | `RcBanner` |
| Stale or partial data | marked **where the number is** — a dotted amber rule under the cell, a `*` in its header, a chip naming what is missing — not only in a note elsewhere | `Banner` + the cell's own mark | `RcBanner` + the cell's own mark |
| An upstream is down | a plain sentence with its probe result (2 s timeout), never a 500 and never a spinner that never ends | `Notice` | `RcNotice` |
| Gated by cost or a long job | the panel shows its description, the price per call and a `LOAD` button; **it never fetches on its own** | `EstimateGate` | `RcEstimateDialog` |
| An edit is unsaved | a modal naming what is unsaved, offering `Discard` / `Cancel` | `UnsavedDialog` | `RcUnsavedDialog` |
| A write is refused | the refusal in words, with the reason (login missing, Guarded route), never a silent no-op | `Notice` | `RcNotice` |

## 9. The component list — and every one's Android counterpart

This is the list **step 8 builds** on the web, and the list **step 18 implements** on Android. `v2/parity.json`
is seeded from it: every row below is a row there, and a row with no Android counterpart is a **contract gap**,
visible before the APK is written rather than after. Where a phone cannot carry a desktop behaviour, the
counterpart names **what it becomes** — that is a stated difference, not a gap.

| id | Web component | Android counterpart | Notes |
|---|---|---|---|
| `shell` | `Shell` | `RcScaffold` | rail/sidebar on the web; `TopAppBar` + `NavigationBar` + drawer on the phone (§6) |
| `app-bar` | `AppBar` | `RcTopBar` | 48 dp on the phone |
| `command-box` | `CommandBox` | `RcCommandSheet` | one entry point: a ticker **or** a board name |
| `board-tabs` | `BoardTabs` | `RcBoardDestinations` | bottom bar + overflow sheet on the phone |
| `nav-group-sheet` | `BoardMenu` | `RcNavGroupSheet` | the menu a grouped bottom-bar destination opens **upward** (§5.2); the web's overflow menu is its counterpart |
| `document-tabs` | `DocumentTabs` | `RcOpenPagesSheet` | the phone has no split view; the back stack carries it |
| `screen-toolbar` | `ScreenToolbar` | `RcScreenToolbar` | same action order, tail in an overflow menu |
| `status-bar` | `StatusLine` | `RcStatusLine` | rows · build/job · as-of |
| `detail-rail` | `DetailRail` | `RcDetailSheet` | a row opens it; `ModalBottomSheet` on the phone |
| `panel` | `Panel` | `RcPanel` | the four parts of §7 |
| `panel-footer` | `PanelFooter` | `RcPanelFooter` | the §7 footer line, exactly |
| `segmented` | `SegmentedControl` | `RcSegmented` | exclusive; never a dropdown at ≤ 5 choices |
| `table` | `DataTable` | `RcRowList` | stacked row cards on the phone; never a sideways scroll |
| `row-card` | `RowCard` | `RcRowCard` | the phone's unit of a table row; 36 dp rows |
| `column-sort` | `SortableHeader` | `RcSortableHeader` | a tappable column header that sorts the table and shows the direction (§11); its hit area is **44 px** tall even where the label is one line |
| `tile` | `Tile` | `RcTile` | caps label · big value · delta chip · comparison line · optional sparkline |
| `sparkline` | `Sparkline` | `RcSparkline` | native Canvas on the phone |
| `range-bar` | `RangeBar` | `RcRangeBar` | in-row graphic |
| `heat-cell` | `HeatCell` | `RcHeatCell` | the colour rule is printed on the screen, not left to a legend |
| `chart-block` | `ChartBlock` | `RcChartBlock` | uPlot on the web, native on the phone; §10 is shared |
| `legend` | `Legend` | `RcLegend` | names every series; §10 |
| `filter-bar` | `FilterBar` | `RcFilterSheet` | a context strip says in words whether a filter is on |
| `chip` | `Chip` | `RcChip` | pill radius; each chip its own fixed column in a row |
| `badge` | `Badge` | `RcBadge` | count badge, state badge |
| `judgement-card` | `JudgementCard` | `RcJudgementCard` | coloured top rule · caps title · **one big verdict word** · three metric lines · a rationale naming the yardstick. No score without its rule |
| `symbol-tile` | `SymbolTile` | `RcSymbolTile` | the company's own mark or a generated monogram, square for a share and a pill for an ETF; **it is the watch-list control** and carries the on-a-list mark (§9.1) |
| `watchlist-sheet` | `WatchListMenu` | `RcWatchListSheet` | the lists the tile opens, with ticks and a `+ New list` row |
| `skeleton` | `SkeletonRows` | `RcSkeletonRows` | §8 |
| `next-step-card` | `NextStepCard` | `RcNextStepCard` | §8 |
| `notice` | `Notice` | `RcNotice` | §8: no data, upstream down, refused |
| `banner` | `Banner` | `RcBanner` | §8: sample, stale, partial |
| `estimate-gate` | `EstimateGate` | `RcEstimateDialog` | nothing that spends starts without it |
| `unsaved-dialog` | `UnsavedDialog` | `RcUnsavedDialog` | §8 |
| `dialog` | `Dialog` | `RcDialog` | `--r-lg`, `--elev-2`; `ModalBottomSheet` on the phone |
| `widget-catalogue` | `WidgetCatalogue` | `RcWidgetCatalogSheet` | search · category chips · two-column cards, each with a sentence and an honest scope |
| `theme-switch` | `ThemeSwitch` | `RcThemeSetting` | dark / light / auto, the `rc-theme` contract of §2 |
| `ask-bubble` | `AskBubble` | `RcAskFab` | bottom right on every screen |
| `format-preview` | `FormatPreview` | `RcFormatPreview` | the live preview of §3's formatting rules |
| `settings-rail` | `SettingsRail` | `RcSettingsList` | search box above two groups: Shell and Data |

### 9.1 The symbol tile

Every row that names an instrument carries a **symbol tile** before the ticker, after the watch-list box (avo,
21 Nov 2026 16:19). It is square for a share and a pill for an ETF, so the two read apart at a glance, and its
size follows the row height.

**The company's own mark where we have it, a generated monogram where we do not** (avo, 21 Nov 2026 16:28:
*"sirketin kendi simgesini kullanacaksin burada, daha kucuk olsun"*). The tile is **26 px on every row height**
(avo, 21 Nov 2026 16:52: *"26 px olsun"*), not a fraction of the row: a mark smaller than that stopped being
readable in the mock, and one size keeps the ticker column aligned whatever the row height is. The two cases are
one component with one fallback, never two layouts.

- **The mark is served by us, never hot-linked and never taken from another product's icon set.** TradingView's
  and Unusual Whales' sets are their assets: no file, sprite or URL of theirs is copied into this repository or
  fetched by a screen. A mark enters the cache only from the company's own site, through a job that maps a ticker
  to its domain, and the door serves it from our own store, so a screen makes no outbound request.
- **The source is a ticker-keyed logo service, cached by us.** Measured 21 Nov 2026 against two of them:
  `financialmodelingprep.com/image-stock/<TICKER>.png` answered **17 of 17** symbols tried, ETFs included
  (SPY, XLK, QQQ, IWM); `eodhd.com/img/logos/US/<TICKER>.png` answered 11 of 17. So FMP is the source the
  ticker→domain job replaces, and the licence of whichever one ships is checked and named in `docs/v2/` before
  the first cached file. Reaching a company's own site stays the fallback path.
- **A wordmark is not a tile.** Three of those 17 (ISRG, CDNS, SPY) are served as a horizontal wordmark — 96 × 19 px
  after trimming — which is unreadable in a 26 px square. **A mark whose trimmed aspect ratio is wider than 2.2 : 1
  is rejected by the cache job and the row falls back to its monogram**, rather than printing a smear.
- **The monogram is the fallback and it must look finished.** The letters come from the ticker and the tint is a
  deterministic hash over the palette's data colours, so every instrument — an ETF, an index, a name no logo set
  covers — gets one, offline, with no request.
- **Square for a share, a pill for an ETF**, in both cases.
- **The tile is also the watch-list control** (avo, 21 Nov 2026 16:38: *"ticker simgesine basinca watchlist e
  ekleme secenegi olacak sekilde yap, diger watchlist ekleme kutusunu kaldir"*). **The separate watch-list box is
  removed**, which supersedes the 18 Nov 2026 rule of a 36 px bookmark button split in two halves — for v2 only;
  the old dashboard is not touched. A name already on a list wears a small mark on the corner of its tile, so the
  state is readable without opening anything. Tapping the tile opens `watchlist-sheet`: the lists avo owns, each
  with a tick where the name is already on it, the options watch list among them, and a `+ New list` row. Its hit
  area is at least the row's height even though the tile is drawn smaller.

## 10. The chart contract — shared inputs, per-surface renderer

Decision 5 put **native charts on the phone**, so the renderer differs by surface (uPlot on the web,
`RcChartBlock` on Android). Everything below is **shared**, and a chart that breaks one of these is wrong on
both surfaces.

- **Input.** A chart is drawn from the board's envelope — `{schema_version, board, run_id, data_asof, built_at,
  private, renderer, layout, data}` — and from nothing else. No surface fetches its own series.
- **One y-axis per chart. No dual axes.** A price line behind value bars makes two unrelated scales look
  comparable; use **two stacked panels on one x-axis** instead.
- **The legend names every series**, in words, with its own number where the series has one. A chart whose legend
  is a colour key with no names is incomplete.
- **The as-of is on the chart**, not only in the panel footer: a vertical as-of rule where the x-axis is time,
  and the `data_asof` in the method line otherwise.
- **A method line under the chart**, in a full sentence, naming the rule that produced the line. Every panel that
  carries a chart **ends in a plain sentence stating its own numbers**, so the chart and the text cannot be read
  two different ways.
- **Series colour: a fixed order, never a cycle.** One or two series use `--data-1` then `--data-2`. Anything
  categorical uses `--c1 … --c6` in that order — **once those tokens exist** (§2.3, §14); until then a
  categorical chart is not built.
- **A seventh category is "Other", never a generated hue.** When every category matters, use **small multiples**:
  one panel per category on one shared scale, each labelled with its own number.
- **A partial series is drawn as partial** (dashed, or stopped at the last complete point with its own note),
  never as a finished line.
- **Grid lines use `--grid`.** A chart scales to its container on both surfaces.
- A line chart with a fixed axis offers a **`Fixed | Fit`** choice (avo, Energy canvas, 21 Nov 2026).

## 11. Tables, cells and order

These are the rules a dense board breaks first. They hold on both surfaces.

- **A table never scrolls sideways; it splits by meaning.** In this order: (1) write each axis once — a period is
  one column, value on line 1 and Δ% under it; (2) stack the blocks as separate tables, each with its own heading
  and sort, the lower one a focused top N; (3) give the remaining columns to the wider screen, a column set per
  breakpoint. Measured: the 13F board wanted 2,060 px for 24 columns against a 1,187 px laptop, and rule (1)
  alone took it to 12.
- **The first screen carries data.** A title, status chips and the table head may use it; rows start on it.
- **A box is a grid of cells.** Every cell of one column has the width of the widest element in that column; a row
  never sizes its own cells (one grid on the parent with `subgrid` rows, or fixed tracks — never a flex row per
  item). Alignment follows the cell's place: leftmost left, middle centred, rightmost right — and this holds for
  **every box that has text in it**, not only a grid's cells. A missing value leaves its cell **empty**; the
  others do not move.
- **Same order, same place.** Sibling boxes and lists show the same items in the same order at the same
  coordinates: the same rows in the same sequence and height in every box of a row of boxes, the same columns in
  every table of one kind, a box's action pinned to its bottom. A row with no value **stays in its place and
  shows "—"**; it is never dropped so the rows below move up. A value never wraps in one box and not in its
  neighbour: shorten the format instead.
- **Cells never overlap the next column.** A long value is written `figure · detail` — the figure on line 1 (at
  most 15 characters per part), the detail on a small muted second line that wraps. Short columns (time, result,
  counts) never wrap and are sized to their widest value plus padding.
- **Row actions before the label.** The watch-list control stands **left of the ticker**, as the rule has always said — in v2 it *is* the symbol tile (§9.1), not a box beside it.
- **Every column a reader would rank by is sortable** (avo, 21 Nov 2026 16:52: *"ayrica stunlari siralama
  ozelligi de istiyorum"*). The header cell is the control: the first tap sorts descending, the second reverses,
  and **only the active column carries a caret**, pointing the way the values run. The sorted column and its
  direction are part of the board's URL, so a sorted view can be sent to someone and comes back the same. Two
  rules follow from §11's own grid: a row whose value in the sorted column is missing **sinks to the bottom
  whichever way the column points**, never to the top as a zero would; and sorting reorders rows only, so every
  cell keeps its column, width and alignment. Where a cell stacks two figures — the price with `1D` and `1W`
  under it — **each figure is its own sort target in the header**, because the cell is one column but three
  questions.
- **One table, one period.** A table that sorts rows from different report periods together answers "who bought
  most" wrongly by construction. Pin the period, or do not show the row.
- **Problems first.** A status strip answers "do I need to act now?". Only problem cards show; everything fine
  folds into one "all good" line. Groups with problems come first and open; fresh groups are collapsed, their
  header carrying the missing count.
- **Less prose, more density** — one line per item with a status dot and one value; help, sources and logs behind
  a click — **but not sparse**: gauges, charts with legend tables, donuts and tables, not rows of identical text.

## 12. Honesty rules that are part of the design

- Every panel footer states `source · as of · age · delay/build`. Every board's status bar states rows, the
  producing build or job, and the as-of. Every derived judgement states its rule.
- A composite score appears **only when every input is in**.
- A screen that shows sample or stale data **says so in a banner** rather than looking live.
- **Private data** (the portfolio: account id, balances, positions) has its own board file, is shown on the
  tailnet only, and never reaches a log, a PR body, an issue, a fixture, a mock or the AI chat.
- Mocks and screenshots of a screen that shows data are rendered against **real rows** on homesrv, read-only,
  never invented values — except where there is no data behind the screen yet, which the PR states. The approved
  v2 mock is the stated exception: it is a picture and says on its own Portfolio screen that its figures are
  invented.

## 13. What CI checks about this contract

`v2/tests/test_design_contract.py`, in the unit tier:

1. Every colour and scale token in §2's tables has **exactly** the value `v2/web/src/theme/tokens.css` gives it,
   and the file holds no token the contract omits. The contract cannot drift from the token file.
2. Every component row of §9 is a row of `v2/parity.json`, and every `parity.json` row is a §9 component.
3. Every row has a non-empty Android counterpart — **no web-only component**.
4. `contract_version` is the same in both files.

Already in CI and unchanged by this file: `v2/web/src/theme/tokens.test.ts` (every `var(--name)` names a token
the file defines — the silent failure of `var(--panel, #12161e)`), `ref/design-system/check_contrast.py` (every
text colour reaches AA on bg, card and card-2 in both schemes), and the `web` tier's Playwright screenshots at
1187 and 1884 px in light and dark.

## 14. Open dependencies, and what this contract does not decide

- **`--c1 … --c6` must be added to `ref/design-system/tokens.css`** (claude-coordinator) before any categorical
  chart is built. The values and their order are decided (§2.3); only the token file lags. This is the one thing
  step 8 can hit that this contract cannot answer by itself.
- **Issue #1247** stays open against the **old dashboard**, where the drift actually is; v2 needs nothing.
- **Not decided here:** which boards exist and in what order the board tab row shows them (that follows the board
  list v2 ends with, spec §11.3); the saved-layout behaviour beyond its buttons (not exercised in the walk, spec
  §11.2); the Portfolio table's filled shape (inferred, spec §11.1); and anything about the door, the envelope or
  a provider. A component's *data* comes from its board's schema in `v2/schemas/`, not from here.
