# RevenueChaser v2 — stack ADR

Step 4 of the v2 run plan (epic #1238, issue #1242; review finding **F14**). One page, and it is the contract
every later v2 step builds against. The order of the work is claude-coordinator
`plans/2026-11-21_0230_revenuechaser_v2-run-plan.md`; the design detail is
`plans/2026-11-20_2342_revenuechaser_v2-gui-plan.md`; the visual input is [`docs/v2/fincept/`](../docs/v2/fincept/).

## What lives here

| Folder | What | Lands in |
|---|---|---|
| `v2/web/` | the v2 web interface: frame, generic renderers, boards. Static files, served by the door. | step 8 onwards (this step leaves an **empty frame**) |
| `v2/door/` | the read-only `/api/v1` door (FastAPI), which also serves `v2/web/dist/` | step 6 |
| `v2/schemas/` | one JSON Schema per board payload, shared by the web app and the Android app | step 3 |
| `v2/design/` | `CONTRACT.md`: the one versioned design contract, for the web **and** the Android app — tokens, scales, panel anatomy, the state table, the component list with each one's Android counterpart, the shared chart contract | step 7b |
| `v2/parity.json` | the component parity list, seeded from the contract; a web-only component fails it | step 7b, enforced from step 18 |

The present dashboard (`app/dashboard.py`, Flask, port 8000) is **not touched** by any v2 step until step 21.

## Decisions

1. **Licences: MIT, Apache-2.0, BSD-2/3-Clause, ISC or 0BSD only.** Nothing AGPL, GPL or commercial ships in
   `v2/web`. Fincept is AGPL-3.0: we copy structure, never its source, images, names or strings. Fonts are the one
   other family: Inter is SIL OFL-1.1, which allows embedding, and is served from the app.
   `v2/web/tools/check-licences.mjs` reads the lockfile and fails the `web` CI job on a production dependency
   outside the allowlist, so the rule is a check and not a sentence in a document. Dev tooling is not shipped to a
   browser, so it is listed in `THIRD-PARTY-NOTICES.md` but not gated.
2. **No CDN, ever.** v2 runs on a tailnet with no guarantee of outbound internet from the browser. Every script,
   style and font is bundled or self-hosted; the door's CSP names no external origin except the Grafana frame
   origin (step 5).
3. **Language: TypeScript, strict.** `tsc --noEmit` is a CI step. A payload type is generated from the JSON Schema
   of step 3, so the web app and the Android app cannot drift from each other silently.
4. **Framework: React 19 + Vite 7, no meta-framework.** Reasons, in order: the table, chart, grid and virtual-list
   libraries we need all have maintained MIT releases in this ecosystem; the door is read-only JSON, so there is
   nothing for a server-rendering framework to do; and a plain `index.html` + `assets/` bundle is what a FastAPI
   static mount serves best. Rejected: Preact (`preact/compat` aliasing hides library bugs for a 30 kB saving we do
   not need on a LAN), htmx or server-rendered Jinja (the dashboard already is that, and the Android app would then
   share no contract with the web app), Next.js / Remix (a Node server on homesrv, which decision 6 forbids).
   JSX is compiled by Vite's own esbuild transform (`tsconfig` `"jsx": "react-jsx"`); `@vitejs/plugin-react` is only
   Fast Refresh and is not a dependency.
5. **Styling: the shared design system's tokens, plain CSS, no Tailwind.** `v2/web/src/theme/tokens.css` is a copy
   of claude-coordinator `ref/design-system/tokens.css` (dark is the default, `data-theme="light"` and
   `"auto"` switch), and `theme.ts` is the same contract as that folder's `theme.js` (`localStorage` key
   `rc-theme`). Components name tokens (`var(--card)`), never a hex value; a unit test fails any `var(--x)` the
   token file does not define — the silent failure `ref/design-system/DESIGN.md` §1 records. Tailwind is rejected
   because it would be a second source of colour and spacing beside the tokens.
6. **Build place: GitHub Actions, or the door's Docker image build. Never a Node toolchain on homesrv.**
   `npm ci --ignore-scripts` + `npm run build` produce `v2/web/dist/`; the door's image copies `dist/` from a
   `node:22-alpine` builder stage (step 6). homesrv installs no Node, no npm and no Playwright browser.
   Dependencies are pinned exactly (no `^`, no `~`) with `package-lock.json` committed, and `npm ci` is the only
   install command, so a build is reproducible from the merged SHA.
7. **Tests: Vitest for unit, Playwright for the browser, both in the `web` job in Actions.** The job runs the
   licence gate, `tsc --noEmit`, Vitest, the production build, then Playwright against `vite preview`, and uploads
   screenshots at **1187** and **1884** px, light and dark (412 px phone shots come with step 8's layout). No test
   runs in a Claude session, as everywhere else in this repository. This repository is public, so the job's minutes
   are free — unlike `home-server` and `idea-creator`, where CI minutes are the scarce thing.
8. **`select_tests` knows `v2/**`.** A change under `v2/web/**` selects the `web` job and no Python test, instead of
   falling back to FULL as it did for any file no Python file names (`scripts/select_tests.py`, F14). A change under
   `v2/door/**` is Python and follows the import graph as every other module does. The merge gate stays one check:
   `merge-gate` is green only when a FULL run's unit, e2e **and** web jobs passed.

## Libraries named for later steps (not installed yet)

Each arrives with the step that needs it, under decision 1, and is added to `THIRD-PARTY-NOTICES.md` with its
licence in the same PR.

| Need | Choice | Licence | Why, and what it replaces |
|---|---|---|---|
| Dense tables, sorting, grouping | TanStack Table v8 + TanStack Virtual | MIT | headless, so the panel anatomy stays ours; virtual rows for a 5,000-row screener |
| Time series, bars, candles | uPlot | MIT | ~50 kB against the **4.56 MB** plotly.js the present pages carry (round 1, F8) |
| One bespoke chart uPlot cannot draw | Apache ECharts, per board, lazily loaded | Apache-2.0 | only where a board needs it; never the default |
| Value Chain graph | Cytoscape.js | MIT | the one board that is a graph, not a table |
| Widget grid (step 14) | our own CSS grid, layout saved in the ops store | — | a drag library is added only if the grid proves it needs one |
| Icons | Tabler Icons (already in this repository) | MIT | same set as the present Settings board |

Rejected outright: Highcharts and AG Grid Enterprise (commercial), anything AGPL or GPL, and any library loaded
from a CDN at runtime.

## What this step does not decide

The door's own dependencies (step 6, Python), the Android app's stack (step 18, the LifeCycle `android/` template),
the AI chat's model (step 19, avo's word), and the backtest engine's venv (step 20, VectorBT — its current licence
is still unchecked).
