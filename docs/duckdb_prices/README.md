# `duckdb_prices` — a working folder for the prices store

What we learn about `prices.duckdb` as we go: measurements with the method that produced them, traps that cost
someone time, and the seams a later change will need. Notes accumulate here instead of being re-derived.

One note per session or investigation, named `YYYY-MM-DD_<slug>.md`, newest listed first. A note records what was
measured and how, so a later reader can re-run it rather than trust it; what it explicitly does **not** claim
belongs in the note too.

| note | what it covers |
|---|---|
| [2026-11-22_store-and-checks.md](2026-11-22_store-and-checks.md) | What is served and by whom, where the data lives, what the comparison numbers actually mean, the read-only parquet method that replaces waiting for a build, why the fetch stops silently, the issue/metrics seams, and the delisted store that was never built |

## The one thing to read before touching this store

The comparison is SQL over tables the build stages *from parquet*, so it runs read-only with no build, no writer
turn and no swap — and it is faithful: counting CRSP against the served close from parquet reproduced the build's
own figures (25,656,198 sessions compared, 313,203 differing against its 313,202). A whole build is hours. Use
the parquet for anything exploratory and keep the build for what has to land.
