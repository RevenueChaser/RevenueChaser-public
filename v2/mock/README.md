# RevenueChaser v2 — design mock

`index.html` is step 2 of the v2 run plan: the design mock of the v2 screens. Open it in a browser; it needs
nothing else and fetches nothing. It is a **picture**, not an application — no route, no payload and no store is
touched by it, and no part of it is wired to the door.

## What it holds

Twenty screens, each drawn in the v2 frame:

| # | Screen | # | Screen |
|---|---|---|---|
| 01 | The frame and the panel, named | 11 | Ticker page — Analysis, judgement cards |
| 02 | Welcome — the widget grid | 12 | News |
| 03 | Add widget — the catalogue | 13 | Portfolio — read-only |
| 04 | Settings — Shell, with the live preview | 14 | Prediction markets |
| 05 | Settings — Data sources, three columns | 15 | AI chat |
| 06 | Settings — Fetch & Health, Grafana framed | 16 | Backtest |
| 07 | Screeners — saved screens, builder, results | 17 | Value chain & Relatedness |
| 08 | Markets — panels, heatmap, movers | 18 | The widgets on data we already serve |
| 09 | Ticker page — Overview | 19 | Loading, empty, stale and refused |
| 10 | Ticker page — Financials | 20 | Two screens side by side |

Two buttons at the top of the page switch **light / dark** and **1187 / 1884 px**, so each screen can be read in
all four combinations. The page scales itself to the window, so it also reads on a phone — that is how the mock is
reviewed, not a phone layout of v2 itself.

Below the screens: a **"Not in the mock"** list, and the **`rules/ui-design.md` checklist** with what the mock
meets and what it deliberately does not.

## Rules it was drawn under

- **Our theme, not Fincept's.** Every colour is a token from claude-coordinator `ref/design-system/tokens.css`
  (Mürekkep light, Gece dark); the type scale, spacing scale, radius and elevations are the shared ones. No
  component carries a hex value.
- **Fincept is AGPL-3.0.** Its visual *structure* was measured on a read-only walk (`docs/fincept/v2-visual-spec.md`)
  and written again from scratch here. No code, string, image, icon or asset of Fincept is in this folder, and the
  walk's screenshots stay off GitHub.
- **Desktop only.** avo decided on 21 Nov 2026 00:41 that the phone view is the native Android app, so no v2 web
  screen is drawn at 412 or 720 px. Those checks belong to the APK mock.
- **English, every string** a screen shows.
- **No real data.** Every figure is invented. The Portfolio screen in particular carries no real position, balance
  or account id, and says so on the screen itself.

## Changing it

The file is self-contained: tokens and component CSS at the top, then small helpers (`panel`, `tile`, `frame`,
`spark`, `lineChart`), then one `shot(...)` call per screen. Add a screen by adding a `shot(...)`; it renders in
order. Keep the token names — a hex value in this file is a defect.
