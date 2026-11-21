# Third-party notices

## Code bundled in this repository

| Component | Version | Licence | Notice |
|---|---|---|---|
| [plotly.js](https://github.com/plotly/plotly.js) | 2.35.2 | MIT | [`app/static/vendor/plotly.min.js.LICENSE.txt`](app/static/vendor/plotly.min.js.LICENSE.txt) |
| [Tabler Icons](https://github.com/tabler/tabler-icons) | outline paths, as drawn in the v28 design | MIT | the source icons of the Settings / Data board (`module_settings/control.py`, `ICONS`); Copyright (c) 2020-2024 Paweł Kuna, MIT licence |
| [edgartools](https://github.com/dgunning/edgartools) | `edgar/reference/data/successor_registrants.csv` at `479d350` | MIT | copied column for column as [`rcdata/build/successor_ciks.csv`](rcdata/build/successor_ciks.csv): ten hand-reviewed predecessor/successor SEC CIK pairs, read by `rcdata/build/cik_history.py` (#749); Copyright (c) Dwight Gunning, MIT licence |

Everything else in this repository is the project's own code, under the MIT
licence in [`LICENSE`](LICENSE).

## Node dependencies (the v2 web app)

`v2/web/` is built from npm packages, pinned exactly in `v2/web/package.json` with
`package-lock.json` committed; none is vendored here. The rule is `v2/README.md`
decision 1: **MIT, Apache-2.0, BSD-2/3-Clause, ISC or 0BSD only, nothing AGPL,
GPL or commercial**, and `v2/web/tools/check-licences.mjs` fails the `web` CI job
on a production dependency outside that allowlist.

| Package | Licence | Shipped to the browser? |
|---|---|---|
| [react](https://github.com/facebook/react), [react-dom](https://github.com/facebook/react), scheduler | MIT | yes |
| [uplot](https://github.com/leeoniya/uPlot) | MIT | yes — the chart renderer of design contract §10, ~50 kB against the 4.56 MB plotly.js the old pages carry |
| [@fontsource-variable/inter](https://github.com/fontsource/font-files) | OFL-1.1 (the font files); the package's own wrapper is MIT | yes — two woff2 subsets, latin and latin-ext |
| [vite](https://github.com/vitejs/vite), [vitest](https://github.com/vitest-dev/vitest) | MIT | no (build and test only) |
| [typescript](https://github.com/microsoft/TypeScript), [@playwright/test](https://github.com/microsoft/playwright) | Apache-2.0 | no (build and test only) |
| [jsdom](https://github.com/jsdom/jsdom), [@testing-library/react](https://github.com/testing-library/react-testing-library), [@testing-library/dom](https://github.com/testing-library/dom-testing-library) | MIT | no (the unit tier's component tests) |

Fonts are the one other licence family: Inter is SIL OFL-1.1, which allows
embedding, and is served from the app itself — never from a font host, because
v2 runs on a tailnet with no guaranteed outbound internet. The rule is enforced,
not only stated: `v2/web/src/theme/fonts.css` is the only `@font-face` in the
tree, `v2/web/src/theme/fonts.test.ts` fails a rule whose file is not on disk or
whose `url()` names a host, and the `web` tier's browser test fails any request
the page makes off its own origin.

## Python dependencies

The packages in `requirements.txt` are installed from PyPI, not vendored here.
Each keeps its own licence; none is redistributed by this repository.

The **v2 door** has a second, smaller list, `v2/door/requirements.txt`, and it is
the only one its container image installs (`v2/door/Dockerfile`). Every package
on it is inside the `v2/README.md` decision 1 allowlist:

| Package | Licence | In the image because |
|---|---|---|
| [fastapi](https://github.com/fastapi/fastapi) | MIT | the door's `/api/v1` |
| [pydantic](https://github.com/pydantic/pydantic) | MIT | FastAPI's own dependency |
| [starlette](https://github.com/encode/starlette) | BSD-3-Clause | FastAPI's own dependency; the Host allowlist and the static mount |
| [uvicorn](https://github.com/encode/uvicorn) | BSD-3-Clause | the server that runs it |
| [python-dotenv](https://github.com/theskumar/python-dotenv) | BSD-3-Clause | `core/config.py` reads `.env` through it |
| [redis](https://github.com/redis/redis-py) | MIT | the health probe, and the write side of step 7 |

## Data sources

This repository contains **code only**. It ships no market data, and the
durable store (`.store/`) and the regenerable caches (`.cache/`) are
gitignored. A few small, hand-trimmed response samples live under
`*/tests/fixtures/` so the offline test suite has something to parse; they are
there to exercise parsers, not to republish a data set.

The code can call the following services. Each has its own terms, and using
this code against them is the operator's own responsibility, under their own
account and key:

| Service | Used for | Key needed |
|---|---|---|
| [Unusual Whales](https://unusualwhales.com/api) | options flow, screener, earnings calendar | yes |
| [SEC EDGAR](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) | company facts (XBRL), 13F filings | no (a User-Agent is required) |
| [FRED](https://fred.stlouisfed.org/docs/api/fred/) | macro series | yes |
| [yfinance](https://github.com/ranaroussi/yfinance) | free price and profile fallbacks | no |
| [OpenFIGI](https://www.openfigi.com/api) | CUSIP to ticker mapping | optional |
| [DeepSeek](https://platform.deepseek.com/) | optional LLM profile extraction | yes |

No key is stored in this repository. `.env` is gitignored; `.env.example`
lists the variable names with empty values.
