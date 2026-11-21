# Fincept Terminal: what RevenueChaser v2 can learn from it

Notes kept on the owner's request (20 Nov 2026): "data sourcelari da ilginç, onlarin hepsinin notunu tutalim",
"Sadece GUI değil, data improvementlari da hersekilde fincept den ogrenmek ve uygulamak istiyorum revenue chaserv2
da". They are reference notes, not a plan; no code in this repository changes because of them.

**What was read.** FinceptTerminal (`github.com/Fincept-Corporation/FinceptTerminal`) at commit `914134d`, release
4.5.3, licence AGPL-3.0. Our side: RevenueChaser-public `main` at `7bfbec1`.

**How it was read.** The source tree, its own `docs/ARCHITECTURE.md` and `fincept-qt/docs/DATAHUB_TOPICS.md`, the
connector catalogue `fincept-qt/resources/data_connectors.json`, and the 20 screenshots in `images/`. The Linux
package was unpacked and started on a virtual screen in a cloud container on 20 Nov 2026: the first-run setup
finished in 15 s and all 53 screens constructed in its own `--smoke-test` walk. **The screens themselves could not be
looked at live:** after setup the application shows a sign-in screen, an account (e-mail or Google) is required and
there is no guest entry, so every live picture is the sign-in screen. Nothing below is a statement about how fast or
how good Fincept is in use.

**Reading marks.** `[READ]` the statement is in a file that was opened, and the file is named. `[INFERRED]` a
conclusion drawn from what was read. `[NOT CHECKED]` nobody looked.

**Licence.** Fincept is AGPL-3.0. Ideas, layouts and the list of public data sources are free to learn from; its
code, its Python scripts and its screen files are not copied into this repository.

| File | What it holds |
|---|---|
| [`data-sources.md`](data-sources.md) | All 204 connectors of Fincept's catalogue: what each is, key or no key, and whether we use the same source |
| [`source-usage.md`](source-usage.md) | Which screen calls which source, and what the free and the paid sources are used for |
| [`data-layer.md`](data-layer.md) | How Fincept fetches, caches, refreshes and recovers, beside how we do it, and what to take for v2 |
| [`comparison.md`](comparison.md) | Feature by feature: do we have it, which is better and why, is it worth having |
| [`ui-structure.md`](ui-structure.md) | The visual structure the owner wants taken one to one (colours excepted) |
