# RevenueChaser — notes for Claude Code

Read [`AGENTS.md`](AGENTS.md) first; it is the source of truth for how data is stored, retrieved and tested. This
file holds the short version plus the rules that are easy to get wrong.

## Where work happens

This repository is where RevenueChaser is developed. The private `alsanvolkan/RevenueChaser` still holds the
project board and two folders that are not published (`.hermes/`, the plan and research history, and
`scripts/pc/`, the machine-specific scripts), but **no new code goes there.** Work is authored, reviewed and
merged here, because this is where CI runs. The issues live here too, and so does `.bookkeeping/`.

- **Branch from `origin/main` of this repository,** push here, open the PR here.
- **Issues live here; the private tracker still holds the old ones.** A bare `#447` means issue 447 of
  *this* repository, so cite an issue that predates the move in full — `alsanvolkan/RevenueChaser#447` —
  which GitHub auto-links across repositories. The private numbering and this repository's do not line up,
  so never assume a number carries over.
- **Few pull requests, each carrying real work.** One per lane; a one-line follow-up rides the next PR that is
  open anyway rather than getting one of its own. An earlier rule of one batched PR per day existed because
  Actions minutes were scarce. They are not scarce here, and the two jobs run concurrently in well under an
  hour, so the reason to batch is now shared files, not cost.
- **Still its own PR, never batched:** a `_SCHEMA_VERSION` bump, a write to the live store, and a change to a
  job the dashboard runs. Each carries a backup and a rollback, and has to be revertable alone.
- **Work that touches only `.hermes/` or `scripts/pc/`** is the one exception to "nothing new in private",
  and it is rare. `.bookkeeping/` is published here, so it is not one of them.

## Dashboard UI

Before touching what a board shows, read the universal design rules (claude-coordinator
`ref/design-system/DESIGN.md` and `vault-memory/rules/ui-design.md`) and this repository's
[`docs/dashboard_ui.md`](docs/dashboard_ui.md). One rule that was missed before: the watch-list bookmark stands
**left of the ticker**, never after it (avo, 18 Nov 2026).

## Language

Code, comments, commit messages, issues and docs are written in **English**.

## Tracking and branches

- Every change maps to a **GitHub issue**, attached as a sub-issue of its area epic. The issues and the board
  live in the private repository — see **Where work happens** for how to reference one.
- Branch naming: `area/<key>/<slice>`, where `<key>` comes from the issue's `area:` label.
- **Every issue carries a `board:*` label saying which dashboard it belongs to** (owner's decision,
  5 Nov 2026: "herseyi github issuelarinda takip edelim"). One label per board it affects —
  `board:sec-13f`, `board:settings`, `board:value-chain`, and so on, one per **data board** tab
  (every `app/dashboard.py` `TABS` tab except `logs` and `runs`) — plus two for the work that fits
  no single board:
  `board:all` (affects every data board) and `board:repo-wide` (store, serving, providers, test
  harness). An `area:*` label says which part of the code; a `board:*` label says which screen.
  So "what is open on the Relatedness board" is
  `is:issue is:open label:board:relatedness` on GitHub, and nothing in this repository has to be
  kept in step for that question to stay answerable.
- There used to be a second copy of this mapping: a checked-in `docs/open_issues.json` that the
  dashboard shell read and rendered as an "Open issues" group above every board. It was removed on
  5 Nov 2026, on the owner's words ("O json kalksin ... suan openissue bilgileri dashboardlari
  kirletiyor"): the file had to be re-synced by hand to stay true, and the group crowded the boards.
  Do not reintroduce a registry file — the labels are the mapping now.

## Tests

- **Tests run only in GitHub Actions** (avo, 9 Nov 2026: "asla ve asla claude yerel makinasinda test kosma"). No
  Claude session runs pytest, not in a cloud container, not on homesrv, not one file, not "just to check": a local
  run is not deterministic and repeats what CI does. Push, open a **draft** PR into `main` at the first push (no PR,
  no CI), and read CI on the head SHA. Rendering a page in Chromium for screenshots is not a test and stays allowed;
  avo's screenshot approval gates "ready for review", not the draft.
- **Unit suite:** `python -m pytest -q`.
- **End-to-end tier:** `RC_E2E=1 python -m pytest module_testing/e2e -m e2e`.
- **Both are offline by construction.** The root `conftest.py` replaces the socket primitives and raises
  `NetworkAccessAttempted` on any real connection; the e2e tier is allowed loopback only, because it drives a real
  dashboard against a local mock-provider server. A Python child the suite starts gets the same guard
  (`module_testing/netguard/sitecustomize.py`, on its `PYTHONPATH`), with loopback open (#258). Mock at the HTTP boundary (the `mock_httpx` fixture), never at
  rule-math level.
- `conftest.py` also redirects **both data roots** (`RC_STORE_DIR`, `RC_CACHE_DIR` and the other artifact roots) to a
  per-process temp directory, and the autouse `isolate_rawstore` fixture gives **every** test its own
  store directory. Never make that fixture session-scoped: a shared DuckDB file would serialise on the single-writer
  lock. `rawstore_tmp_db` fills that file by **copying** a per-process template that `ensure_all_tables` built once
  (`rawstore_template`, never opened by a test), not by running the ~1 s apply per test. A test of the schema apply
  or a migration itself is marked `@pytest.mark.rawstore_schema_from_scratch` and gets the apply on its own file.
- CI (`.github/workflows/tests.yml`) runs both tiers on every pull request into `main` and on `main`. The unit tier
  runs as 6 parallel jobs (`unit (FULL) 0/6` ... `5/6`; `RC_SHARD` splits by test file, the measured ones by time from `scripts/test_durations.json`), each under
  `pytest -n auto --dist loadfile`, because a single pytest process is single-core bound. That table is rebuilt from
  several FULL runs' junit artifacts by `python scripts/durations.py <run id> ...`, never by hand, and because
  `loadfile` gives a whole file to one worker, **no test file may cost more than a shard's per-worker share**
  (`scripts/tests/test_durations_table.py` fails one that does; split it along its own sections instead).
  A push to a PR runs only the test files that import a changed file (`scripts/select_tests.py`; check names
  `unit (SELECTIVE)` / `e2e (SELECTIVE)`), and falls back to FULL when that is not safe to say. A change that stays
  inside board folders runs only those boards' e2e files and the shell's (`select_tests.E2E_BY_BOARD`). **The merge
  gate is a green `merge-gate` check on the current head** (it fails on purpose for a SELECTIVE run): label the PR
  `full-ci` at the **last** push. The label buys one FULL run and is removed when it finishes (job `full-ci-once`), so
  a later push is SELECTIVE again and needs the label once more. A push to `main` whose tree that PR run already
  tested green is skipped (`plan` mode SKIP); any other push to `main`, and a manual dispatch, run FULL. Each run
  uploads junit files with per-test times (`junit-unit-<shard>`, `junit-e2e`), and the venv is cached per ISO week
  (`.github/actions/python-deps`).
- **TDD, read in CI:** "seen red first" is the `red-on-base` job's result (the PR's new tests run against the
  merge-base), quoted in the PR report. It does not cover e2e tests: say "e2e: not checked". A mutation check is a
  commit: push the mutation, read the red run, push the revert; required only for money, store, identity and
  migration logic. Report honestly — "not done" is an acceptable answer, an implied "done" is not.
- **`red-on-base` copies the PR's test files onto the base source**, so a ceiling or guard test whose allowlist
  lives inside the test file can never be red on the base: the base's offender is already named by the PR's own
  list and the check passes there, proving nothing. Write such a rule over **source behaviour** instead of over
  allowlist membership — "a board file that imports a client library must also import `core.providers`" is red on
  the base, "a board file not in `PROVIDER_FILES` must not import a client library" is not (#1213, PR #1226).
- **A CI failure the diff cannot explain** is a flaky test. Fix it, or remove its host assumption, in the same
  branch; do not re-run until it passes.
- **Docs that state a value the code owns** (schema version, suite tiers, ports) are compared against the code by
  `core/tests/test_doc_constants.py`. A change to such a value updates the doc in the same commit.
- **Windows-only code** (the `os.name == "nt"` process-name branches in `core/procs.py` and `core/oom.py`) is
  tested through fakes, because CI runs on Linux. The Task Scheduler backend and the `.ps1`/`.bat`/`.pyw`
  launcher are gone (#1225).
- **Tests clean up their own scratch.** The root `conftest.py` redirects the store, cache, `edgar_docs`
  and SPX-Gamma roots at one `rc-pytest-*` directory per process and removes it in
  `pytest_sessionfinish`; `pytest.ini` sets `tmp_path_retention_policy = failed`, so a passing test's
  `tmp_path` goes with it and a failing one's is kept to look inside. **Not `none`:** on Windows that also
  removes the numbered basetemp root mid-session and every later `tmp_path` fails with `WinError 3`.
  A test that needs its scratch to outlive the run takes an explicit path, never the session root. Only the
  process that created a root removes it (`RC_PYTEST_SCRATCH_OWNER`), because under `pytest -n auto` every
  xdist worker inherits the controller's root and the first to finish would otherwise delete it for the rest.
  A killed run still leaves scratch behind: `./app.sh clean-scratch` reports it and `--apply` removes it,
  leaving alone anything written to in the last two hours **in its top two levels** — deep enough for
  `<root>/.store/boards/<board>.duckdb`, which is why the age is hours and not minutes. Measured 2026-10-23 before
  this landed: 917 leaked `rc-pytest-*` directories and 2.1 GB under pytest's own basetemp.

## Data safety

- **The durable store is `.store/boards/<board>.duckdb`**, one file per board (and `watchlists.duckdb`, avo's own
  lists); the market data the boards read is rcdata's serving layer under `RC_MARKET_DIR`. The old `raw.duckdb`,
  `edgar.duckdb`, `history.duckdb` and `.store/prices.duckdb` were removed with every code path to them (#860,
  15 Nov 2026), and `core/tests/test_no_old_store.py` fails any code that names one again. The regenerable caches
  are `.cache/`. Both are gitignored — this repository is **code only**, and no market data ships
  with it. `docs/data_architecture.md` is the contract.
- **Read-only inspection of a real store** needs `duckdb.connect(..., read_only=True)` **and** the environment
  variable `RC_STORE_AUTO_ENSURE=0`. Without the second one, application code applies the schema manifest on its
  first call and creates tables in the file you meant only to read.
- **A `_SCHEMA_VERSION` bump** needs a store checkpoint taken before the merge; there is no automation for it.
- **The dashboard holds the DuckDB writer** (`python -m revenuechaser.app.dashboard`, port 8000 by default), so
  start store-writing jobs through it rather than running a second writer:
  `curl -X POST -H "X-RC-Panel: cli" http://127.0.0.1:8000/run/<job>`, then poll `/api/job/<id>`.
  **Every non-`GET`/`HEAD`/`OPTIONS` request needs that header**; without it the dashboard answers
  `403 panel header required` and starts nothing. Any non-empty value works, except
  `POST /api/automations/<name>/<action>`, which needs exactly `X-RC-Panel: automations`.

## Keys and private material

- **No key belongs in this repository.** `.env` is gitignored; `.env.example` lists the variable names with empty
  values. Read credentials through `core/credentials.py`, never by printing or logging a value.
- `scripts/private_check.py` is the guard: it refuses a secret, a personal home path or mailbox, an account id and a
  private folder. Run it with `--all` over the tree, or `--staged` before a commit;
  `git config core.hooksPath scripts/hooks` wires it into a pre-commit hook.
- A paid provider call (the optional DeepSeek profile writer) is gated in its own code — a cost cap and an off-peak
  window, see `core/offpeak.py` — and never by a separate watcher process.

## Research scripts

Research and one-off measurement scripts are **not part of this repository**. A measurement is run once, its
number is recorded in the issue or the doc that needed it, and the script does not stay behind. So this tree
carries no `scripts/research/`, and no test drives one; `scripts/tests/` tests the real jobs in `scripts/`.
Outputs and raw caches belong in `.cache/research/<issue>/`, which is gitignored and regenerable.

A few docstrings in `core/` still credit the research script a number came from (`core/reaction_anchor.py`,
`core/rawstore.py`, `core/providers/openfigi.py`). Those names are provenance, not files in this tree.

## Feedback-thread workflow

When the owner wants problems or improvements collected (standing rule, all repos, 2026-10-24):

1. **Collect.** Open one feedback thread. The owner writes every item there; acknowledge each in one short line and fix nothing until the owner says the list is done.
2. **Reproduce.** Reproduce each item from the code or live data before promising a fix. Cite `file:line` or a measurement.
3. **Review.** Only when the owner says "Fable ile incele", never automatically: one Fable 5.1 review of the list against the code, using the `avo-architecture-review` and `design-suite` skills. It reports findings, order and risks; it implements nothing. Without that phrase, skip this step.
4. **Plan.** Write a plan file in `/mnt/project-files/<app>/` with ordered steps, risks, and the decisions only the owner can make. Ask only those.
5. **Build.** One branch, one pull request, one commit per step. Tests seen red first. A design mock first for anything new.
6. **Phone friendly.** Every UI works on a phone and in light and dark: single column, full-width cards, 44 px touch targets, charts scale to their container, tables stack instead of scrolling sideways.
7. **Hourly.** Scheduled jobs and monitors refresh hourly unless the owner says otherwise.
