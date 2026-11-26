"""``sec/reads``: a model's answers to the registered questions, the one dataset of the ``sec_reads`` kind.

Its ``fetch`` asks (:mod:`asker`), the answers are Parquet, one partition per question
(``parquet/sec/reads/question=<id>/answers.parquet``), and the build loads them into ``read_answer``. Boards read it
through ``rcdata.read.sec_reads`` and the need ``sec.read``. Nothing of it lives in a board.

**Never asked twice.** One row per (question, prompt version, company, filing, document, input hash, provider,
model). A company is asked when its current text (question, prompt version, company, input hash) has no ``ok`` row
by any writer and fewer than :data:`MAX_ATTEMPTS` attempts: a new text (its hash) or a new prompt version is asked,
a new filing that carries the same text is not, and a second writer is not asked for a text one writer answered.

**No mass re-read without the owner's word** (avo, 15 Nov 2026 18:53; :func:`stale_reason`). A run asks by itself
only a company's new filing and a retry. A DeepSeek question is asked at most :data:`DAY_CAP` companies a day; past
the cap it stops and goes on the next day (avo, 15 Nov 23:48). EVREN has no quota, so an EVREN question has no day
cap and reads every new filing as it comes (avo, 16 Nov 2026 09:38). Everything else that is stale (a changed prompt, a re-cut text, a question's
first pass) waits for a request that says ``"reread": true`` (the CLI's ``--reread``), which asks all of it, or
``"reread": [question ids]`` (``--reread debt.note``), which asks all of those questions and only the usual rest of
the others.

**The attempts rule** (from ``module_relatedness.engine``): an unusable reply is counted on its key, three of them
and the company waits for a new filing, a new prompt or :data:`RETRY_AFTER_S`, and a ``partial`` answer is never
replaced by an ``empty`` one. A run whose first replies are all unusable stops and stores none
(``asker.UNUSABLE_STOP``).

**Nothing is asked when the Parquet tree is behind the live table** (:func:`tree_behind`): a lost partition must
not read as "nothing answered".

**A writer that is down does not fail the run** (:func:`outage`): its questions are skipped, every company stays
stale for the next pass, and the note says which writer and how it failed. A rejected key, a wrong endpoint (the
five-unusable stop), a pause and the owner's cap still fail it.

**The raw replies** are kept with the answer (``raw``) and in one raw file per run and question, written before the run
can stop, so an answer that was paid for is stored even when the run ends on a pause or a provider error. The
Parquet tree is the durable copy of the answers (plan risk R4: it must be in the backup set before the first real
run).

**The daily check runs at night** (avo, 16 Nov 2026 09:51): the hourly pass of 01:05 Amsterdam, once the US session
is over (:data:`DUE_FROM_NY`). It still ``starts_by_hand`` (plan risk R7: not before a first run a person started),
its file's automation is off until someone switches it on, and no real question is registered in step 1.
"""
from __future__ import annotations

import json
import os
import time
from datetime import date, time as clock_time, timedelta
from pathlib import Path

import duckdb

from ... import serving
from ....core import job_lock
from ....core.providers import deepseek
from .. import base
from ..fundamentals import common
from . import KIND, asker
from .questions import QUESTIONS, Question

NAME = "sec/reads"
TABLE = "read_answer"
PARTITION = "answers.parquet"
#: Unusable replies on one key before the company waits for a new filing or prompt (the Relatedness rule).
MAX_ATTEMPTS = 3
#: ...or this long: a key at its attempts is tried once more after it, so nothing a passing fault caused (a gate
#: down for three runs) is parked until next year's filing. A filing that can never be read costs one call a month.
RETRY_AFTER_S = 30 * 86400.0
#: Why a company is stale. A run asks the first two by itself; the other two need the request's ``reread``.
NEW_FILING, RETRY, CHANGED, FIRST, NEW_COMPANY = "new_filing", "retry", "changed", "first", "new_company"
AUTOMATIC = (NEW_FILING, RETRY, NEW_COMPANY)
#: The most companies with no answer at all one run asks by itself. A company that enters the universe is asked like
#: a new filing; more than this many at once is a change of scope, which waits for the owner's word like any mass
#: read (avo, 16 Nov 2026: "a scope change must not count as a new filing").
NEW_COMPANY_LIMIT = int(os.environ.get("RC_SEC_READS_NEW_COMPANY_LIMIT", "100"))
#: Companies one DeepSeek question is asked in a day without ``reread`` (a paid call is capped in its own code).
#: Provisional: the number is the owner's. An EVREN question has none: EVREN has no quota (avo, 16 Nov 2026).
DAY_CAP = int(os.environ.get("RC_SEC_READS_DAY_CAP", "200"))
UNCAPPED = ("evren",)
#: The check's day starts at 19:00 New York, so the first hourly pass that finds it due is 19:05 New York: 01:05
#: Amsterdam (00:05 in the few weeks a year the two clocks change apart). ``due.is_due`` reads it through
#: ``default_as_of``, the Settings page and the Grafana board through ``due_from_ny``.
DUE_FROM_NY = clock_time(19, 0)

KEY = ["question", "prompt_version", "cik", "accession", "document", "input_hash", "provider", "model"]
#: ``fetched_at`` is when the answer was asked; ``answer`` is the parsed JSON, ``raw`` the replies (JSON list, one
#: per chunk) and ``missing_chunks`` the chunks that stayed unusable (comma separated).
SCHEMA = [("question", "TEXT"), ("prompt_version", "TEXT"), ("cik", "TEXT"), ("accession", "TEXT"),
          ("document", "TEXT"), ("filing_date", "DATE"), ("input_hash", "TEXT"), ("provider", "TEXT"),
          ("model", "TEXT"), ("status", "TEXT"), ("attempts", "INTEGER"), ("answer", "TEXT"), ("raw", "TEXT"),
          ("missing_chunks", "TEXT"), ("rules_version", "TEXT"), ("fetched_at", "DOUBLE"), ("run_id", "TEXT"),
          # Serving version 2: what was read, what it cost, and how the last unusable call failed -- or, on a
          # ``no_text`` row, which has no call, why the question found no text for the company (#1419).
          ("form", "TEXT"), ("input_kind", "TEXT"), ("calls", "INTEGER"), ("tokens_in", "INTEGER"),
          ("tokens_out", "INTEGER"), ("error", "TEXT"),
          # Serving version 3: the period the filing reports on (``filing_section.report_date``).
          ("report_date", "DATE")]
SCHEMAS = {TABLE: SCHEMA}
STATUSES = (asker.OK, asker.PARTIAL, asker.EMPTY, asker.NO_TEXT)


def outage(e: BaseException) -> bool:
    """Whether ``e`` is the writer being down and nothing else: a 429 after the client's own retries, a 5xx, a
    capacity refusal waited out, a network failure (``DeepSeekTransientError``, and EVREN's subclass of it).

    Such a run leaves every company stale and the next pass asks it again, so it is not the step's failure: the
    questions of the writer that is down are skipped, the note says so, and the run ends green. It is why one
    writer's outage no longer fails the whole night: a failed ``sec/reads`` exits 1 and the chain behind it (Value
    Chain) does not run (Fable report F6, 19 Nov 2026). Everything else still fails the run: a rejected key
    (``DeepSeekAuthError``), the five-unusable stop (a wrong endpoint or model), a pause and the owner's cap.
    """
    return isinstance(e, deepseek.DeepSeekTransientError) and not isinstance(e, deepseek.DeepSeekAuthError)


def partition_path(question: str) -> Path:
    return common.parquet_dir(NAME) / f"question={question}" / PARTITION


def raw_path(run_id: str) -> Path:
    return base.raw_root().joinpath(*NAME.split("/")) / f"{run_id}.json.gz"


def _key(row: dict) -> tuple:
    return tuple(row[k] for k in KEY)


def _text_key(key: tuple) -> tuple:
    """``key`` without the filing and the writer: (question, prompt version, company, input hash). An ``ok`` answer
    on it is current whoever wrote it and whichever accession carried the text (avo, 11 Nov 2026: a profile stays
    current when the writer changes), so changing a question's writer asks nothing again."""
    return key[0], key[1], key[2], key[5]


def _job_key(j: asker.Job) -> tuple:
    q = j.question
    return (q.id, q.prompt_version, j.cik, j.input.accession, j.input.document, j.input_hash, q.provider,
            q.writer_model)


def held(question: str) -> dict[tuple, dict]:
    """The stored rows of ``question`` by key."""
    path = partition_path(question)
    if not path.exists():
        return {}
    con = base.scratch_con()
    try:
        cur = con.execute(f"SELECT * FROM read_parquet({base.sql_path(path)})")
        cols = [d[0] for d in cur.description]
        return {_key(r): r for r in (dict(zip(cols, t)) for t in cur.fetchall())}
    finally:
        con.close()


def _plan(q: Question, ctx: base.RunContext) -> tuple[list[asker.Job], dict[tuple, dict], list[dict]]:
    """``(jobs to ask, their stored rows by key, new no_text rows)`` for one question."""
    ciks = sorted({common.norm_cik(c) for c in q.scope()} - {None, ""}, key=int)
    if not ciks:
        return [], {}, []
    have = held(q.id)
    behind = tree_behind(q, have)
    if behind:
        raise base.SourceError(behind)
    inputs, whys = q.read_inputs(ciks)
    answered = {_text_key(k) for k, r in have.items() if r["status"] == asker.OK}
    textless = {(k[0], k[1], k[2]) for k, r in have.items() if r["status"] == asker.NO_TEXT}   # by any writer
    by_cik: dict[str, list[dict]] = {}
    for r in have.values():
        if r["status"] != asker.NO_TEXT:
            by_cik.setdefault(r["cik"], []).append(r)
    begun = any(r["prompt_version"] == q.prompt_version and r["status"] == asker.OK for r in have.values())
    reread = ctx.reread is True or q.id in (ctx.reread or ())
    waiting: dict[str, int] = {}
    jobs, prior, no_text, new = [], {}, [], 0
    for cik in ciks:
        inp = inputs.get(cik)
        if inp is None or not (inp.text or inp.hash):
            row = {"question": q.id, "prompt_version": q.prompt_version, "cik": cik, "accession": "",
                   "document": "", "input_hash": "", "provider": q.provider, "model": q.writer_model}
            # The question's own reason, when it named one (#1419): without it the row says only that there was
            # no text, and a coverage figure cannot be explained or its reasons counted. A row that is already
            # stored without a reason, or with a reason that is no longer the one it would be given, is written
            # once more with it, at no call: otherwise every company skipped before this change would keep an
            # empty reason until its prompt version moved, and a company whose reason changed would keep the
            # first one. Only a row of this writer's own key is corrected; one written by another writer is left
            # alone rather than doubled. The row's ``fetched_at`` and ``run_id`` stay as filed, because the
            # observation has not changed, only the words for it.
            old_row = have.get(_key(row))
            why = whys.get(cik) or None
            if old_row is not None:
                if why and old_row["status"] == asker.NO_TEXT and (old_row.get("error") or "") != why:
                    no_text.append({**old_row, "error": why})
            elif (q.id, q.prompt_version, cik) not in textless:
                no_text.append({**row, "status": asker.NO_TEXT, "attempts": 0, "fetched_at": time.time(),
                                "run_id": ctx.run_id, "error": why})
            continue
        job = asker.Job(q, cik, inp, q.input_hash(inp))
        old = have.get(_job_key(job))
        if _text_key(_job_key(job)) in answered or (
                old is not None and old["attempts"] >= MAX_ATTEMPTS
                and time.time() - (old["fetched_at"] or 0) < RETRY_AFTER_S):
            continue
        why = stale_reason(job, by_cik.get(cik, []), begun)
        if why not in AUTOMATIC and not reread:
            waiting[why] = waiting.get(why, 0) + 1
            continue
        jobs.append(job)
        prior[_job_key(job)] = old
        new += why == NEW_COMPANY
    if new > NEW_COMPANY_LIMIT and not reread:
        # A change of scope, not a company's first report: none of them is asked without the owner's word.
        waiting[NEW_COMPANY] = new
        jobs = [j for j in jobs if by_cik.get(j.cik)]
        prior = {_job_key(j): prior[_job_key(j)] for j in jobs}
    if waiting:
        ctx.notes.append(f"{q.id}: {sum(waiting.values())} wait for the owner's word, a request with reread ("
                         + ", ".join(f"{w} {n}" for w, n in sorted(waiting.items())) + ")")
    if not reread and q.provider not in UNCAPPED:
        day = _now() - 86400.0
        today = len({r["cik"] for rows in by_cik.values() for r in rows if (r["fetched_at"] or 0) > day})
        room = max(0, DAY_CAP - today)
        if len(jobs) > room:
            ctx.notes.append(f"{q.id}: the day cap of {DAY_CAP} companies is reached ({today} asked in the last "
                             f"24 hours); {len(jobs) - room} wait for tomorrow")
            jobs = jobs[:room]
            prior = {_job_key(j): prior[_job_key(j)] for j in jobs}
    return jobs, prior, no_text


def plan_counts(reread: bool | tuple[str, ...] = False) -> dict:
    """``{"would_ask": {question: companies}, "notes": [...]}``: what a run would ask now, with no call and nothing
    written (``python -m revenuechaser.rcdata.build.sec_reads --plan [--reread [question ...]]``). A question that
    reads another's answers (the profile reads the locator's) is planned on what is stored now."""
    ctx = base.RunContext(run_id="plan", dataset=NAME, reread=reread)
    return {"would_ask": {q.id: len(_plan(q, ctx)[0]) for q in QUESTIONS.values()}, "notes": ctx.notes}


def _now() -> float:
    return time.time()


def stale_reason(job: asker.Job, rows: list[dict], begun: bool) -> str:
    """Why ``job``'s company is asked: ``rows`` are its stored answers to the question (every prompt version),
    ``begun`` whether the question has an ``ok`` answer under its current prompt version at all.

    - ``retry``: this text under this prompt was asked before and has no ``ok`` answer;
    - ``new_filing``: a filing the company has no row for, when it was read under this prompt before;
    - ``new_company``: a company with no row at all once the question's first pass has begun (its first report);
      asked by itself up to ``NEW_COMPANY_LIMIT`` a run (``_plan``);
    - ``first``: no row, and the question has no answer under this prompt yet (its first pass);
    - ``changed``: the rest, the same filing with another text (a re-cut) or a prompt version the company was not
      read under.
    """
    q = job.question
    if any(r["prompt_version"] == q.prompt_version and r["input_hash"] == job.input_hash for r in rows):
        return RETRY
    if not rows:
        return NEW_COMPANY if begun else FIRST
    known = {r["accession"] for r in rows}
    if job.input.accession not in known and any(r["prompt_version"] == q.prompt_version for r in rows):
        return NEW_FILING
    return CHANGED


def tree_behind(q: Question, have: dict[tuple, dict]) -> str | None:
    """Why ``q`` must not be asked: the live table holds more ``ok`` answers than the Parquet tree, or None.

    What is answered is read from Parquet, which has no backup; a lost or older partition would read as "nothing
    answered" and the run would re-read every company by itself. The live file is the witness that it is the tree
    that is behind, so the run stops and asks nothing."""
    try:
        con = serving.open_read(KIND)
    except serving.ServingFileMissing:
        return None
    try:
        n = con.execute(f"SELECT count(*) FROM {TABLE} WHERE question = ? AND status = ?",
                        [q.id, asker.OK]).fetchone()[0]
    except duckdb.Error:                # a live file from before the table existed holds no answers
        return None
    finally:
        con.close()
    held_ok = sum(1 for r in have.values() if r["status"] == asker.OK)
    if n > held_ok:
        return (f"{q.id}: the live table holds {n} ok answers and the Parquet tree {held_ok}; the tree is behind "
                f"(lost or restored older), so nothing is asked until it is rebuilt from {KIND}.duckdb")
    return None


def _count(missing_chunks: str | None) -> int:
    return len([c for c in (missing_chunks or "").split(",") if c])


def row_of(ctx: base.RunContext, reply: asker.Reply, old: dict | None) -> dict:
    """The stored row for ``reply``; a ``partial`` answer stays unless the new reply answered more chunks."""
    j, q = reply.job, reply.job.question
    row = {"question": q.id, "prompt_version": q.prompt_version, "cik": j.cik, "accession": j.input.accession,
           "document": j.input.document,
           "filing_date": j.input.filing_date.isoformat() if j.input.filing_date else None,
           "input_hash": j.input_hash, "provider": q.provider, "model": q.writer_model,
           # A reply cut short by a pause, the day cap or a provider stop is not an attempt: nothing was unusable.
           "status": reply.status, "attempts": (old["attempts"] if old else 0) + (0 if reply.stop else 1),
           "answer": None if reply.answer is None else json.dumps(reply.answer, sort_keys=True),
           "raw": json.dumps(reply.raws), "missing_chunks": ",".join(map(str, reply.missing)),
           "rules_version": j.input.rules_version, "fetched_at": time.time(), "run_id": ctx.run_id,
           "form": j.input.form, "input_kind": j.input.kind, "error": reply.error or None,
           "report_date": j.input.report_date.isoformat() if j.input.report_date else None,
           # What the key has cost in all, over every attempt.
           **{c: ((old or {}).get(c) or 0) + getattr(reply, c) for c in ("calls", "tokens_in", "tokens_out")}}
    if old is not None and old["status"] == asker.PARTIAL and len(reply.missing) >= _count(old["missing_chunks"]):
        row.update({c: old[c] for c in ("status", "answer", "raw", "missing_chunks")})
    return row


class Reads:
    name = NAME
    kind = KIND
    providers = ("evren", "deepseek")
    tables: tuple[str, ...] = (TABLE,)
    cadence = "daily"
    backfill_needs_from = False
    starts_by_hand = True
    #: One fetch asks the model for up to ``asker.SLICE_S``, so it never fetches inside the builder lock: it
    #: collects fetch-only (``--no-duckdb``) and a build pass writes the serving file (``base.long_read``, #1532,
    #: the build-lock split, option A, avo 25 Nov 2026).
    long_read = True
    due_from_ny = DUE_FROM_NY
    #: Shown beside the dataset on the Settings page and the Grafana board.
    limits = f"EVREN: no day cap · DeepSeek: {DAY_CAP} companies a day"

    def default_as_of(self) -> date:
        """The New York day whose :data:`DUE_FROM_NY` has passed: the session the night's check is for."""
        from ....core import calendar
        return (calendar.now_ny() - timedelta(hours=DUE_FROM_NY.hour, minutes=DUE_FROM_NY.minute)).date()

    def fetch(self, ctx: base.RunContext, as_of: date) -> list[Path]:
        """Ask every registered question what is stale, one question after the other; one raw file per question.

        **One asker at a time** (:data:`asker.ASK_LOCK`), whoever started the run: a run that does not get the lock
        asks nothing and stages nothing, and its build still loads what the other run has written.

        **Nothing is handed back to the builder**: every answer is written and converted inside the lock, and the
        run returns no raw file, so the builder's own conversion after ``fetch`` (outside the lock) cannot write a
        partition another asker is writing.

        **A writer that is down skips its questions, and the run does not fail** (:func:`outage`): with every
        question on one writer, a transient outage would otherwise end the whole step as failed.

        **A question is finished before the next is planned**: its answers are in Parquet when the next question
        builds its inputs, so a question that reads another's answer (the business section the locator found,
        for the profile) never runs on the text it would have had without it. Registration order is run order.
        """
        if not QUESTIONS:
            ctx.notes.append("no question registered")
            return []
        with job_lock.acquire(asker.ASK_LOCK) as got:
            if not got:
                ctx.notes.append("another SEC read is asking: nothing asked by this run")
                return []
            return self._ask_all(ctx)

    def _ask_all(self, ctx: base.RunContext) -> list[Path]:
        started = ctx.clock()
        raws: list[Path] = []
        asked = left_all = 0
        by_status: dict[str, int] = {}
        stop: BaseException | None = None
        down: dict[str, str] = {}               # a writer that is down in this run, and how it failed
        for q in QUESTIONS.values():
            if q.provider in down:
                ctx.notes.append(f"{q.id}: not asked, {q.provider} is down in this run ({down[q.provider]})")
                continue
            ctx.check_pause()
            jobs, prior, rows = _plan(q, ctx)
            replies, stop, left = asker.ask(ctx, jobs, started)
            rows += [row_of(ctx, r, prior[_job_key(r.job)]) for r in replies]
            asked += len(jobs)
            left_all += left
            for r in rows:
                by_status[r["status"]] = by_status.get(r["status"], 0) + 1
            if rows:
                # Written and converted before the next question (and before a stop), so nothing paid for is lost.
                raw = base.write_raw_json(raw_path(f"{ctx.run_id}.{q.id}"), {"run_id": ctx.run_id, "rows": rows})
                self.to_parquet_all(ctx, [raw])
                raws.append(raw)
            if stop is not None and outage(stop):
                down[q.provider] = f"{type(stop).__name__}: {stop}"[:200]
                ctx.notes.append(f"{q.id}: {q.provider} is down ({down[q.provider]}); {left} companies stay "
                                 f"stale for the next run and the run does not fail on it")
                stop = None
                continue
            if stop is not None:
                break
        ctx.notes.append(f"{asked} to ask over {len(QUESTIONS)} question(s); "
                         + (", ".join(f"{s} {n}" for s, n in sorted(by_status.items())) or "nothing new")
                         + (f"; {left_all} left for the next run" if left_all else ""))
        if stop is not None:
            raise stop
        return []

    def backfill(self, ctx: base.RunContext, start: date | None, end: date) -> None:
        raise base.SourceError(f"{NAME} has no backfill: a run asks what is stale")

    def to_parquet(self, ctx: base.RunContext, raw: Path) -> list[Path]:
        return self.to_parquet_all(ctx, [raw])

    def to_parquet_all(self, ctx: base.RunContext, raws: list[Path]) -> list[Path]:
        by_q: dict[str, list[dict]] = {}
        for raw in raws:
            for r in base.read_raw_json(raw)["rows"]:
                by_q.setdefault(r["question"], []).append(r)
        return [base.upsert_partition(rows, SCHEMA, KEY, partition_path(q)) for q, rows in sorted(by_q.items())]

    def build(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict[str, int]:
        con.execute("CREATE TABLE {} ({})".format(TABLE, ", ".join(f'"{c}" {t}' for c, t in SCHEMA)))
        files = sorted(common.parquet_dir(NAME).glob(f"question=*/{PARTITION}"))
        if files:
            cols = ", ".join(f'"{c}"' for c, _ in SCHEMA)
            src = f"read_parquet([{', '.join(base.sql_path(f) for f in files)}], union_by_name = true)"
            con.execute(f"INSERT INTO {TABLE} SELECT {cols} FROM {base.with_all(con, SCHEMA, src)} "
                        f"ORDER BY question, cik, fetched_at")
        return {TABLE: con.execute(f"SELECT count(*) FROM {TABLE}").fetchone()[0]}

    def check(self, ctx: base.RunContext, con: duckdb.DuckDBPyConnection) -> dict:
        """Rows per question and status go in the note (a ``dataset_check`` row carries only its own fields)."""
        added, removed = base.compare_with_live(con, KIND, TABLE, KEY + ["status", "attempts"])
        counts = con.execute(f"SELECT question, status, count(*) FROM {TABLE} GROUP BY 1, 2 ORDER BY 1, 2").fetchall()
        rows = sum(n for _, _, n in counts)
        note = "; ".join(f"{q} {s} {n}" for q, s, n in counts) or "no answers yet"
        return {"dataset": NAME, "result": "changed" if added or removed else "unchanged",
                "source_as_of": (ctx.as_of or self.default_as_of()).isoformat(), "rows": rows,
                "added": added, "removed": removed, "note": note}


DATASET = Reads()
