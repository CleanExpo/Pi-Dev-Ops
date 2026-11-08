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
from .goal_analyze import _MAX_TOKENS, _SYSTEM, cleaned_drafts, render_analyze_prompt
from .goal_analyze_fields import analysis_overlay, parse_analyze_payload
from .goal_projects import get_project
from .spec_pipeline import llm

log = logging.getLogger("pi-ceo.goal_analysis_worker")

HEARTBEAT_S = 20.0  # well under the 60 s claim
RECOVERY_S = 30.0
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

    def __init__(self, job_id: str, attempt: int, server: str, interval: float) -> None:
        self.job_id, self.attempt, self.server, self.interval = job_id, attempt, server, interval
        self.stop = threading.Event()
        self.lost = False

    def give_up(self) -> None:
        self.lost = True
        self.stop.set()


async def _beat(lease: _Lease) -> None:
    misses = 0
    while True:
        await asyncio.sleep(lease.interval)
        try:
            ok = await asyncio.to_thread(jobs.heartbeat, lease.job_id, lease.attempt, lease.server)
            misses = 0
        except jobs.GoalJobStoreError:
            misses += 1  # one failed round-trip leaves slack in the 60 s claim; two do not
            ok = misses < 2
        if not ok:
            log.warning("goal job %s attempt %s lost its claim; stopping", lease.job_id, lease.attempt)
            lease.give_up()
            return


async def _analyse(lease: _Lease, complete_fn: Callable[..., Awaitable[Any]] | None) -> dict[str, Any]:
    job = await asyncio.to_thread(jobs.get, lease.job_id)
    if job is None:
        raise RuntimeError("the job row is missing")
    project = await asyncio.to_thread(get_project, job["project_id"])
    if not project:
        raise RuntimeError("the project brief is missing")
    goal, acceptance = job["goal"], job["acceptance"]
    call = functools.partial(complete_fn or llm.complete, stop=lease.stop)
    try:
        text, cost = await asyncio.wait_for(
            call(prompt=render_analyze_prompt(goal, acceptance, project), system=_SYSTEM,
                 role="goal_analyst", max_tokens=_MAX_TOKENS),
            timeout=_MODEL_BUDGET_S)
    except TimeoutError:
        lease.stop.set()
        raise RuntimeError("the model call ran past its time budget") from None
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
                  heartbeat_s: float = HEARTBEAT_S) -> str:
    """Run one claimed attempt. Returns finished, failed, abandoned, unrecorded or not_claimed."""
    server = server or SERVER_ID
    attempt = await asyncio.to_thread(jobs.claim, job_id, server)
    if attempt is None:
        return "not_claimed"
    lease = _Lease(job_id, attempt, server, heartbeat_s)
    beat = asyncio.create_task(_beat(lease))
    try:
        try:
            result = await _analyse(lease, complete_fn)
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


def launch(job_id: str) -> None:
    """Start run_job in the background. A second launch for the same job loses the claim."""
    task = asyncio.get_running_loop().create_task(run_job(job_id))
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)


async def recover_once() -> None:
    for job_id in await asyncio.to_thread(jobs.recover_expired):
        log.warning("goal job %s was interrupted or failed by recovery", job_id)
    for job_id in await asyncio.to_thread(jobs.runnable_ids):
        launch(job_id)


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
