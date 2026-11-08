"""Background worker for submit-then-check goal analysis (UNI-3306 PR 2).

Rules, from the plan and the store (goal_analysis_jobs.py):
- run_job claims a job, then heartbeats every HEARTBEAT_S (the claim lasts 60 s). EVERY
  heartbeat, finish and fail return value is checked. False means the claim is gone:
  the stop signal is set so the model call ends, and the attempt is abandoned. A write
  that returned False is never retried.
- The stop event goes to llm.complete(stop=...), so a lost claim reaches the model call.
- No placeholder fallback: a failed analysis is recorded failed, with a reason.
- recovery_loop runs recover_expired() and re-launches runnable jobs, so a server kill
  mid-run (or before the claim) ends in one retry, then a recorded failure.
- The model call runs in a thread owned by goal_analysis_slots; the concurrency slot and
  the live-job registry are released only when that thread's call returns (read that
  module's docstring). Named limit: provider_execution does not forward stop to HTTP
  providers such as Ollama, so only claude_print and codex can be stopped. Async analysis
  refuses to run on any other provider and records the job failed with that reason; a
  call that ignores stop still keeps its slot until it returns and recovery waits for it.
- Self-fencing lease (goal_analysis_slots.Fence): a watchdog thread stops the model at
  last-successful-heartbeat-SENT + CLAIM_S - FENCE_SAFETY_S, whatever the event loop or the
  heartbeat call is doing, so the stop is complete before the database claim can expire.
  Named limits: a frozen or SIGSTOPped process cannot fence itself. After a hard kill an
  orphaned CLI child may keep running (provider_execution starts it in its own session and
  nothing ties it to the parent); its writes are refused by attempt fencing, so the cost is
  model time, not data.
- Startup probes table_present(). If the table is missing, async stays unavailable.
"""
from __future__ import annotations

import asyncio
import functools
import logging
import os
import socket
import threading
from typing import Any, Awaitable, Callable

from . import goal_analysis_jobs as jobs
from . import goal_analysis_slots as slots
from .goal_analyze import _MAX_TOKENS, _SYSTEM, cleaned_drafts, render_analyze_prompt
from .goal_analyze_fields import analysis_overlay, parse_analyze_payload
from .goal_projects import get_project
from .spec_pipeline import llm
from .provider_router import select_provider_model

log = logging.getLogger("pi-ceo.goal_analysis_worker")

HEARTBEAT_S = 20.0  # well under the 60 s claim
RECOVERY_S = 30.0
MODEL_END_S = 10.0  # how long an attempt waits for a stopped model call to end
_MODEL_BUDGET_S = 240.0  # inside the 300 s attempt deadline
SERVER_ID = f"{socket.gethostname()}:{os.getpid()}"
_state = {"available": False, "reason": "async goal analysis has not been probed yet"}
_tasks: set[asyncio.Task[Any]] = set()


def enabled() -> bool:
    """The off switch. Read live, default OFF; it lives here because config.py is over its size cap."""
    return os.environ.get("GOAL_ANALYZE_ASYNC", "0") == "1"


def availability() -> tuple[bool, str]:
    """(usable, reason). Off, or on without the table, is never reported as usable."""
    if not enabled():
        return False, "async goal analysis is switched off"
    return bool(_state["available"]), str(_state["reason"])


class _Lease:
    """The running attempt. `lost` is set when a heartbeat says the claim is gone."""

    def __init__(self, job_id: str, attempt: int, server: str, interval: float, claim_sent: float) -> None:
        self.job_id, self.attempt, self.server, self.interval = job_id, attempt, server, interval
        self.fence = slots.Fence(claim_sent, self.give_up)
        self.stop = threading.Event()
        self.lost = False

    def give_up(self) -> None:
        self.lost = True
        self.stop.set()


async def _beat(lease: _Lease) -> None:
    misses = 0
    while True:
        await asyncio.sleep(lease.interval)
        sent = slots._now()  # the lease is measured from when the beat was SENT
        try:
            ok = await asyncio.to_thread(jobs.heartbeat, lease.job_id, lease.attempt, lease.server)
            misses = 0
        except jobs.GoalJobStoreError:
            misses += 1  # one failed round-trip leaves slack in the 60 s claim; two do not
            ok = misses < 2
        else:
            if ok:
                lease.fence.advance(sent)  # only a SUCCESSFUL heartbeat extends the lease
        if not ok:
            log.warning("goal job %s attempt %s lost its claim; stopping", lease.job_id, lease.attempt)
            lease.give_up()
            return


async def _end_model(lease: _Lease, model: asyncio.Future[Any]) -> None:
    """Every exit path (done, failed, timed out, cancelled): set stop, then wait up to
    MODEL_END_S for the model call. The wait may give up; the slot and the job's registry
    entry stay with the model thread until it returns, so giving up releases nothing."""
    if not model.done():
        lease.stop.set()
        await asyncio.wait({model}, timeout=MODEL_END_S)
    if not model.done():
        log.error("goal job %s: the model call ignored stop for %.0f s; its slot stays held until it returns",
                  lease.job_id, MODEL_END_S)
    elif not model.cancelled():
        model.exception()  # retrieved so a Stopped result is never logged as unretrieved


def _require_stoppable_provider() -> None:
    """Named limit: refuse a provider whose call cannot be stopped (Ollama and other HTTP transports)."""
    provider = select_provider_model("goal_analyst", record_observation=False).provider
    if provider not in ("claude_print", "codex"):
        raise RuntimeError(f"provider {provider} cannot be stopped; async goal analysis needs claude_print or codex")


async def _analyse(lease: _Lease, complete_fn: Callable[..., Awaitable[Any]] | None,
                   slot: slots.Slot | None = None) -> dict[str, Any]:
    job = await asyncio.to_thread(jobs.get, lease.job_id)
    if job is None:
        raise RuntimeError("the job row is missing")
    project = await asyncio.to_thread(get_project, job["project_id"])
    if not project:
        raise RuntimeError("the project brief is missing")
    if complete_fn is None:
        await asyncio.to_thread(_require_stoppable_provider)
    goal, acceptance = job["goal"], job["acceptance"]
    call = functools.partial(complete_fn or llm.complete, stop=lease.stop)
    model = slots.run_in_thread(lambda: call(
        prompt=render_analyze_prompt(goal, acceptance, project), system=_SYSTEM,
        role="goal_analyst", max_tokens=_MAX_TOKENS), slot, asyncio.get_running_loop())
    try:
        text, cost = await asyncio.wait_for(asyncio.shield(model), timeout=_MODEL_BUDGET_S)
    except TimeoutError:
        raise RuntimeError("the model call ran past its time budget") from None
    finally:
        await _end_model(lease, model)
    payload = parse_analyze_payload(text)
    if payload is None:
        raise RuntimeError("the model did not return a usable ticket plan")
    tickets = cleaned_drafts(payload, goal, acceptance)
    if not tickets:
        raise RuntimeError("the model plan had no implementable tickets")
    return {"status": "proposed", "filed": False, "fallback": False, "code_inspected": False,
            "code_limitation": "", "cost_usd": cost, "project_id": project["id"],
            "project_title": project["title"], "tickets": tickets, **analysis_overlay(payload)}


async def _write(lease: _Lease, what: str, fn: Callable[..., bool], *args: Any) -> str:
    """One finish or fail write. Not retried, whatever it returns."""
    try:
        done = await asyncio.to_thread(fn, lease.job_id, lease.attempt, *args)
    except jobs.GoalJobStoreError as exc:
        log.error("goal job %s: %s write failed (%s); recovery will handle it", lease.job_id, what, exc.code)
        return "unrecorded"
    if not done:
        log.warning("goal job %s attempt %s: %s refused, claim is gone; abandoning", lease.job_id, lease.attempt, what)
        return "abandoned"
    return what


async def run_job(job_id: str, *, server: str | None = None,
                  complete_fn: Callable[..., Awaitable[Any]] | None = None,
                  heartbeat_s: float = HEARTBEAT_S, slot: slots.Slot | None = None) -> str:
    """Run one claimed attempt. Returns finished, failed, abandoned, unrecorded or not_claimed."""
    server = server or SERVER_ID
    claim_sent = slots._now()
    attempt = await asyncio.to_thread(jobs.claim, job_id, server)
    if attempt is None:
        return "not_claimed"
    lease = _Lease(job_id, attempt, server, heartbeat_s, claim_sent)
    lease.fence.start()
    beat = asyncio.create_task(_beat(lease))
    try:
        try:
            result = await _analyse(lease, complete_fn, slot)
        except Exception as exc:  # llm.Stopped included; CancelledError is a kill and writes nothing
            if lease.lost:
                return "abandoned"
            log.warning("goal job %s failed: %s", job_id, type(exc).__name__)
            return await _write(lease, "failed", jobs.fail, f"{type(exc).__name__}: {exc}"[:500])
        if lease.lost:
            return "abandoned"
        return await _write(lease, "finished", jobs.finish, result, [])
    finally:
        beat.cancel()
        lease.fence.close()


def launch(job_id: str) -> bool:
    """Start run_job in the background if a slot is free and the job has no live model
    thread. The slot is taken BEFORE the claim, so a deferred job stays queued (unclaimed,
    so it cannot expire) until a later recovery pass. False means not started."""
    slot = slots.take(job_id)
    if slot is None:
        return False

    async def held() -> None:
        try:
            await run_job(job_id, slot=slot)
        finally:
            slot.release_if_not_handed_off()  # never the model thread's slot

    task = asyncio.get_running_loop().create_task(held())
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return True


async def recover_once() -> None:
    for job_id in await asyncio.to_thread(jobs.recover_expired):
        log.warning("goal job %s was interrupted or failed by recovery", job_id)
    for job_id in await asyncio.to_thread(jobs.runnable_ids):
        if slots.is_live(job_id):
            continue  # its model thread has not returned: never start another attempt
        if not launch(job_id):
            break  # no free slot: the rest stay queued for the next pass


async def recovery_loop() -> None:
    while True:
        await recover_once()  # a store error raises, and _resilient restarts the loop
        await asyncio.sleep(RECOVERY_S)


async def start(resilient: Callable[..., Awaitable[Any]]) -> None:
    """Startup hook. With the switch off nothing starts; with the table missing, async stays off."""
    if not enabled():
        return
    try:
        present = await asyncio.to_thread(jobs.table_present)
    except jobs.GoalJobStoreError as exc:
        present, _state["reason"] = False, f"the job table could not be probed ({exc.code})"
    else:
        _state["reason"] = "" if present else "the goal_analysis_jobs table or functions are missing"
    _state["available"] = present
    if not present:
        log.error("GOAL_ANALYZE_ASYNC is on but async analysis is UNAVAILABLE: %s", _state["reason"])
        return
    asyncio.create_task(resilient(recovery_loop, "goal_analysis_recovery"))
    log.info("async goal analysis is available")
