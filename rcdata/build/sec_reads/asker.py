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


def _ask_one(ctx: base.RunContext, job: Job, started: float, lock: threading.Lock) -> Reply | None:
    """One company's chunks, in order; None when the run's slice ran out before it started.

    The pause and the day cap are read before every call, as ``base.Paused`` promises. A stop after some chunks
    were answered returns them with the stop (``Reply.stop``), so what was paid for is stored. The slice is read
    per company only: a company that started finishes its chunks.
    """
    if ctx.clock() - started > SLICE_S:
        return None
    q = job.question
    client = CLIENTS[q.provider]
    parts: list[dict] = []
    raws: list[str] = []
    missing: list[int] = []
    chunks = q.chunks(job.input.text)
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
            if not isinstance(e, (base.Paused, base.CapReached)):
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
            parts.append(parsed)
    if not parts:
        return Reply(job, EMPTY, None, raws, missing, **sent)
    return Reply(job, PARTIAL if missing else OK, q.merge(parts), raws, missing, **sent)


def ask(ctx: base.RunContext, jobs: list[Job]) -> tuple[list[Reply], BaseException | None, int]:
    """Ask every job: ``(replies, the error that stopped the run or None, jobs left unasked)``.

    The replies that came back before a stop are returned with it, so the caller stores them before it raises: a
    paid answer is never thrown away.
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
    started = ctx.clock()
    lock = threading.Lock()
    replies: list[Reply] = []
    stop: BaseException | None = None
    by_provider: dict[str, list[Job]] = {}
    for j in jobs:
        by_provider.setdefault(j.question.provider, []).append(j)
    pools = {p: ThreadPoolExecutor(max_workers=POOLS[p]) for p in by_provider}
    try:
        futs = [pools[p].submit(_ask_one, ctx, j, started, lock) for p, js in by_provider.items() for j in js]
        for f in as_completed(futs):
            try:
                r = f.result()
            except BaseException as e:  # noqa: BLE001 - Paused, CapReached and the provider stops end the run
                stop = stop or e
                for g in futs:
                    g.cancel()
                continue
            if r is not None:
                replies.append(r)
                if r.stop is not None:
                    stop = stop or r.stop
                    for g in futs:
                        g.cancel()
    finally:
        for pool in pools.values():
            pool.shutdown(wait=True, cancel_futures=True)
    return replies, stop, total - len(replies)
