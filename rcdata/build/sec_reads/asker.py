"""The one asker: every question's calls go out here, with one pool per provider.

**Caps.** EVREN 1 request at a time (``evren.MAX_WORKERS``, avo 15 Nov 2026 11:22 and 11:32), the DeepSeek API 8
(avo 10:44; coordinator PR #716). On homesrv LiteLLM keeps the same limits for every caller together (plan §3.4);
these pools keep them without the gate too, so a run behaves the same either way. The gate is a unit setting, not
code: both clients read their base URL from the environment (``RC_EVREN_BASE``, ``RC_DEEPSEEK_BASE``).

**The HTTP clients** are ``core/providers``' own, called with ``use_cache=False``: the tool keeps the answer itself
(``read_answer``), so ``llm_cache`` gets no rows from it. DeepSeek's off-peak gate is in its client
(``deepseek.peak_blocked``) and is read here once before the first call.

**One model job at a time** (plan §4, risk R2): while the Relatedness board's own model job holds its lock, the tool
refuses to start, because two askers against EVREN's cap of 1 is the HTTP 429 seen on 15 Nov 10:41 and 11:15.

**The builder lock** (plan risk R1). A run asks for at most :data:`SLICE_S` seconds and leaves the rest stale for the
next run, so a queued pass never holds the builder lock for hours. A long read runs fetch-only instead
(``python -m RevenueChaser.rcdata.build run --dataset sec/reads --no-duckdb``): that takes only its own
``rcdata_fetch_sec_reads`` lock, and the build proper is then seconds long.
"""
from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from ....core import job_lock, offpeak
from ....core.providers import deepseek, evren
from ... import ops
from .. import base
from .questions import Input, Question

#: Requests at a time, per provider.
POOLS = {"evren": evren.MAX_WORKERS, "deepseek": 8}
CLIENTS = {"evren": evren, "deepseek": deepseek}
#: The longest a run asks before it stops and leaves the rest for the next run (R1).
SLICE_S = 15 * 60.0
#: One worker reads its company's text at a time: the eight workers share one DuckDB instance and its read memory
#: limit, and eight text reads at once ran out of 1 GiB and 3 GiB (rc-sec-read, 16-17 Nov 2026). A read takes well
#: under a second; the model call it feeds takes tens of seconds, so the run is not slower.
FILL_LOCK = threading.Lock()
#: Companies whose reply was unusable, with no usable one yet in the run, before the run is called the endpoint's
#: fault and stopped with none of them stored (the Relatedness rule, ``module_relatedness.config.UNUSABLE_STOP``).
UNUSABLE_STOP = 5
#: Companies a run gives up on for a transient error (a timeout, a 5xx, a 429 after its retries) before the run
#: itself stops: one slow company must not end every hourly run at the same place (the board's own five,
#: ``module_relatedness.engine``). A company given up on is no attempt and is asked again by the next run.
TRANSIENT_STOP = 5
#: The one lock every asking run holds, whoever started it (the builder's pass, the service's own unit, a Fetch
#: press, a command by hand): two askers would break EVREN's one request and rewrite one Parquet partition.
ASK_LOCK = "sec_reads_ask"
#: The Relatedness board's own model job (``module_relatedness.engine``); one model job at a time until it moves here.
RELATEDNESS_LOCK = "relatedness"
OK, PARTIAL, EMPTY, NO_TEXT = "ok", "partial", "empty", "no_text"
#: The errors that stop the whole run: the next call cannot do better.
_STOP = (deepseek.PeakHoursError, deepseek.DeepSeekAuthError, deepseek.DeepSeekTransientError)


@dataclass
class Job:
    question: Question
    cik: str
    input: Input
    input_hash: str


@dataclass
class Reply:
    job: Job
    status: str
    answer: dict | None
    raws: list[str] = field(default_factory=list)
    missing: list[int] = field(default_factory=list)
    #: The error that stopped the run during this company's chunks: the chunks before it are still stored.
    stop: BaseException | None = None
    #: Calls made and the provider's own token counts, summed over the chunks.
    calls: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    #: Why the last unusable chunk was unusable (the error's name and words, or ``unusable reply``); "" when none.
    error: str = ""
    #: ``stop`` was a transient error the run tolerates: the company was cut short, the run goes on.
    go_on: bool = False


def busy_problem() -> str | None:
    """Why no model read may start now (another model job runs), or None."""
    held = [pid for name, pid in job_lock.holders() if name == RELATEDNESS_LOCK]
    if held:
        return f"a Relatedness model job runs (pid {held[0]}): one model job at a time"
    return None


def _why(e: BaseException) -> str:
    """An error as the request log keeps it: its class and its own words, cut short."""
    return f"{type(e).__name__}: {e}"[:300]


def _parse(q: Question, reply: str) -> dict | None:
    try:
        return q.parse(reply)
    except Exception:  # noqa: BLE001 - a reply the parser cannot read is an unusable reply, not a failed run
        return None


def _ask_one(ctx: base.RunContext, job: Job, started: float, lock: threading.Lock, run: dict) -> Reply | None:
    """:func:`_ask_filled`, with the company's text read just before it is asked when the question has a ``fill``:
    the job holds that text only while its calls are out, so a run never holds every company's text."""
    q = job.question
    if q.fill is None:
        return _ask_filled(ctx, job, started, lock, run)
    with lock:
        if run["halt"] or ctx.clock() - started > SLICE_S:
            return None
    kept = job.input
    with FILL_LOCK:
        job.input = q.fill(job.cik, kept)
    try:
        return _ask_filled(ctx, job, started, lock, run)
    finally:
        job.input = kept


def _ask_filled(ctx: base.RunContext, job: Job, started: float, lock: threading.Lock, run: dict) -> Reply | None:
    """One company's chunks, in order; None when the run's slice ran out, or the run was halted, before it started.

    ``run`` is the run's shared count of companies with and without a usable reply (read and written under
    ``lock``): the worker itself halts the run at :data:`UNUSABLE_STOP`, so no further company is sent while the
    caller is still reading the last reply.

    The pause and the day cap are read before every call, as ``base.Paused`` promises. A stop after some chunks
    were answered returns them with the stop (``Reply.stop``), so what was paid for is stored. The slice is read
    per company only: a company that started finishes its chunks.

    A transient error gives up on this company only (what it answered so far is kept, no attempt is counted) until
    :data:`TRANSIENT_STOP` companies of the run have had one; then the error stops the run as before. A question's
    ``max_calls`` is read here too: a company whose messages would pass it is left for the next run.
    """
    q = job.question
    n = len(q.messages(job.input))
    with lock:
        if run["halt"] or ctx.clock() - started > SLICE_S:
            return None
        # Reserved before sending, so eight workers together never pass the cap.
        # shortcut: a company with more messages than max_calls is never asked, raise the cap when the note names it
        if q.max_calls is not None and run["calls"].get(q.id, 0) + n > q.max_calls:
            if q.id not in run["capped"]:
                run["capped"].add(q.id)
                ctx.notes.append(f"{q.id}: this run's cap of {q.max_calls} calls is reached "
                                 f"(cik {job.cik} needs {n}); the rest waits for the next run")
            return None
        run["calls"][q.id] = run["calls"].get(q.id, 0) + n
    try:
        reply = _ask_chunks(ctx, job, lock)
    except deepseek.DeepSeekTransientError:
        with lock:
            run["calls"][q.id] -= n     # nothing was answered: the reservation goes back to the run
            run["transient"] += 1
            if run["transient"] >= TRANSIENT_STOP:
                run["halt"] = True      # no further company is sent while the caller reads this stop
                raise
        return None
    with lock:
        if isinstance(reply.stop, deepseek.DeepSeekTransientError):
            run["transient"] += 1
            reply.go_on = run["transient"] < TRANSIENT_STOP
            run["halt"] = run["halt"] or not reply.go_on
        run["usable" if reply.status != EMPTY else "unusable"] += 1
        run["halt"] = run["halt"] or (not run["usable"] and run["unusable"] >= UNUSABLE_STOP)
    return reply


def _ask_chunks(ctx: base.RunContext, job: Job, lock: threading.Lock) -> Reply:
    q = job.question
    client = CLIENTS[q.provider]
    parts: list[tuple[dict, int]] = []      # each usable answer with the length of the message it answered
    raws: list[str] = []
    missing: list[int] = []
    chunks = q.messages(job.input)
    sent = {"calls": 0, "tokens_in": 0, "tokens_out": 0, "error": ""}

    def log(i: int, result: str, t0: float) -> None:
        """One request-log row per call (avo, 15 Nov 2026: every failure is kept with how it failed)."""
        ops.log_call(q.provider, f"{q.id} cik {job.cik} chunk {i + 1}/{len(chunks)}", dataset=ctx.dataset,
                     result=result, ms=(time.monotonic() - t0) * 1000)
        if result != OK:
            sent["error"] = result

    for i, chunk in enumerate(chunks):
        failed, usage, t0 = 0, {}, time.monotonic()
        try:
            with lock:
                ctx.check_cap(q.provider)
            reply = client.complete(q.system, chunk, model=q.writer_model, max_tokens=q.max_tokens,
                                    use_cache=False, cik=job.cik, prompt_version=q.prompt_version, usage=usage)
        except (base.Paused, base.CapReached, *_STOP) as e:
            if not isinstance(e, (base.Paused, base.CapReached, deepseek.PeakHoursError)):   # these sent nothing
                with lock:
                    ctx.count(q.provider, calls=1, failures=1, logged=True)
                    log(i, _why(e), t0)
                sent["calls"] += 1
            if not parts:
                raise
            return Reply(job, PARTIAL, q.merge(parts), raws, missing + list(range(i, len(chunks))), stop=e, **sent)
        except deepseek.DeepSeekError as e:     # EVREN's errors are its subclasses: no content, a bad status
            reply, failed = "", 1
            with lock:
                log(i, _why(e), t0)
        sent["calls"] += 1
        sent["tokens_in"] += int(usage.get("prompt_tokens") or 0)
        sent["tokens_out"] += int(usage.get("completion_tokens") or 0)
        raws.append(reply)
        parsed = _parse(q, reply) if reply else None
        with lock:
            ctx.count(q.provider, calls=1, failures=failed, logged=True)
            if not failed:
                log(i, OK if parsed is not None else "unusable reply", t0)
        if parsed is None:
            missing.append(i)
        else:
            parts.append((parsed, len(chunk)))
    if not parts:
        return Reply(job, EMPTY, None, raws, missing, **sent)
    return Reply(job, PARTIAL if missing else OK, q.merge(parts), raws, missing, **sent)


def ask(ctx: base.RunContext, jobs: list[Job],
        started: float | None = None) -> tuple[list[Reply], BaseException | None, int]:
    """Ask every job: ``(replies, the error that stopped the run or None, jobs left unasked)``.

    The replies that came back before a stop are returned with it, so the caller stores them before it raises: a
    paid answer is never thrown away. ``started`` is the run's clock when one run asks several questions, so the
    slice is the run's and not each question's.

    **A wrong endpoint costs five calls and no attempt.** While no company has had a usable reply, the unusable
    ones are held back; :data:`UNUSABLE_STOP` of them stop the run as failed and none is stored, so a renamed
    model or a changed reply shape cannot count an attempt on every waiting company. A usable reply, or the end of
    a shorter run, stores them as the attempts they are.
    """
    if not jobs:
        return [], None, 0
    total = len(jobs)
    busy = busy_problem()
    if busy:
        raise base.SourceError(busy)
    if any(j.question.provider == "deepseek" for j in jobs) and deepseek.peak_blocked():
        # Only DeepSeek's questions wait for its window; the EVREN ones are asked now.
        ctx.notes.append(f"DeepSeek is off-peak only: its questions wait for "
                         f"{offpeak.next_off_peak():%Y-%m-%d %H:%M} UTC")
        jobs = [j for j in jobs if j.question.provider != "deepseek"]
    started = ctx.clock() if started is None else started
    lock = threading.Lock()
    replies: list[Reply] = []
    held_back: list[Reply] = []         # unusable, and no usable reply yet in this run
    usable = False
    gave_up = False                     # the five-unusable stop fired: its held-back replies are never stored
    stop: BaseException | None = None
    by_provider: dict[str, list[Job]] = {}
    for j in jobs:
        by_provider.setdefault(j.question.provider, []).append(j)
    pools = {p: ThreadPoolExecutor(max_workers=POOLS[p]) for p in by_provider}
    try:
        run = {"usable": 0, "unusable": 0, "halt": False, "transient": 0, "calls": {}, "capped": set()}
        futs = [pools[p].submit(_ask_one, ctx, j, started, lock, run)
                for p, js in by_provider.items() for j in js]
        for f in as_completed(futs):
            try:
                r = f.result()
            except BaseException as e:  # noqa: BLE001 - Paused, CapReached and the provider stops end the run
                stop = stop or e
                for g in futs:
                    g.cancel()
                continue
            if r is None:
                continue
            if gave_up and r.status == EMPTY:
                continue                # in flight when the run gave up: dropped like the five, no attempt
            usable = usable or r.status != EMPTY
            (replies if usable else held_back).append(r)
            if r.stop is None and len(held_back) >= UNUSABLE_STOP and not usable and stop is None:
                gave_up = True
                r.stop = base.SourceError(
                    f"the first {UNUSABLE_STOP} replies of this run were all unusable (last: {r.error or '?'}); "
                    f"check the endpoint and the model ({r.job.question.writer_model}). None was stored")
            if r.stop is not None and not r.go_on:
                stop = stop or r.stop
                for g in futs:
                    g.cancel()
    finally:
        for pool in pools.values():
            pool.shutdown(wait=True, cancel_futures=True)
    if not gave_up:                     # a usable reply landing after the stop (eight workers) does not store them
        replies += held_back
    return replies, stop, total - len(replies)
