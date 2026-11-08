"""Review round 1 fixes: model ends before retry, loop never blocked, concurrency limit (UNI-3306)."""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest

from app.server import goal_analysis_jobs as jobs, goal_analysis_worker as worker
from app.server.routes import goal_ticket_async
from app.server.spec_pipeline import llm
from tests import goal_worker_helpers as h
from tests.goal_jobs_helpers import CLAIM, MARGIN, FakeRest
from tests.goal_worker_helpers import ACCEPT, GOAL, PLAN, PROJECT, Model, _queued, _row

# fixtures are taken by assignment, not import (ruff F811)
_fresh_slots, rest, launched, async_on = h._fresh_slots, h.rest, h.launched, h.async_on

# ---- review round 1 fixes ----------------------------------------------------------------

async def _until(cond: Any, timeout: float = 3.0) -> None:
    deadline = time.monotonic() + timeout
    while not cond():
        assert time.monotonic() < deadline, "condition never became true"
        await asyncio.sleep(0.01)


class Threaded(Model):
    """A model call that, like a provider thread, ends ONLY when stop is set, and is not
    cancellable by the task that awaits it. `alive` counts calls still running."""

    alive = 0
    alive_at_start: list[int] = []

    def __init__(self) -> None:
        super().__init__()
        self.alive_at_start = []
        self.ended = 0

    async def __call__(self, *, prompt: str, system: str, role: str, max_tokens: int,
                       stop: threading.Event) -> tuple[str, float]:
        self.alive_at_start.append(Threaded.alive - self.ended)
        Threaded.alive += 1
        try:
            while not stop.is_set():
                await asyncio.sleep(0.01)
        finally:
            self.ended += 1
        raise llm.Stopped("stopped")


async def test_kill_stops_the_model_before_the_retry_attempt_starts(
        rest: FakeRest, launched: list[str]) -> None:
    Threaded.alive = 0
    model = Threaded()
    job_id = _queued()
    task = asyncio.create_task(worker.run_job(job_id, complete_fn=model, heartbeat_s=1000))
    await _until(lambda: len(model.alive_at_start) == 1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert model.ended == 1  # the model call ended BEFORE the cancelled run returned
    rest.advance(CLAIM + MARGIN + 1)
    await worker.recover_once()
    retry = asyncio.create_task(worker.run_job(job_id, complete_fn=model, heartbeat_s=1000))
    await _until(lambda: len(model.alive_at_start) == 2)
    assert model.alive_at_start == [0, 0]  # nothing from attempt 1 was alive when attempt 2 began
    retry.cancel()
    with pytest.raises(asyncio.CancelledError):
        await retry


class SlowRest(FakeRest):
    """Every store call blocks its thread for 200 ms, like a slow Supabase round trip."""

    def __call__(self, method: str, path: str, data: dict[str, Any] | None = None) -> bytes:
        time.sleep(0.2)
        return super().__call__(method, path, data)


async def _worst_loop_delay(work: Any) -> float:
    worst, stop = 0.0, asyncio.Event()

    async def ticker() -> None:
        nonlocal worst
        last = time.monotonic()
        while not stop.is_set():
            await asyncio.sleep(0.01)
            now = time.monotonic()
            worst, last = max(worst, now - last - 0.01), now

    tick = asyncio.create_task(ticker())
    await asyncio.sleep(0.03)
    await work()
    stop.set()
    await tick
    return worst


async def test_submit_and_worker_store_calls_do_not_block_the_event_loop(
        monkeypatch: pytest.MonkeyPatch, async_on: None, launched: list[str]) -> None:
    slow = SlowRest()
    monkeypatch.setattr(jobs, "_request", slow)
    monkeypatch.setattr(worker, "get_project", lambda pid: PROJECT)
    monkeypatch.setattr(goal_ticket_async, "get_project", lambda pid: PROJECT)

    async def work() -> None:
        job = await goal_ticket_async.submit_job(GOAL, ACCEPT, "ra", "key-0001")
        assert await worker.run_job(job["id"], complete_fn=Model(), heartbeat_s=1000) == "finished"
        await worker.recover_once()

    assert await _worst_loop_delay(work) < 0.1  # seconds of store I/O ran, the loop barely moved


class Gate(Model):
    """Holds every call until released; records the most running at once."""

    def __init__(self) -> None:
        super().__init__()
        self.open, self.running, self.peak = asyncio.Event(), 0, 0

    async def __call__(self, *, prompt: str, system: str, role: str, max_tokens: int,
                       stop: threading.Event) -> tuple[str, float]:
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:
            await self.open.wait()
        finally:
            self.running -= 1
        return PLAN, 0.0


async def test_backlog_above_the_limit_runs_at_most_n_and_defers_the_rest(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOAL_ANALYZE_MAX_CONCURRENT", "2")
    gate = Gate()
    monkeypatch.setattr(llm, "complete", gate)
    ids = [jobs.submit("ra", f"Finalise stage {n} of RestoreAssist", ACCEPT, f"key-000{n}")["id"] for n in range(5)]
    await worker.recover_once()
    await _until(lambda: gate.running == 2)
    await asyncio.sleep(0.2)  # time for a wrongly launched third call to show itself
    states = [_row(rest, i)["status"] for i in ids]
    assert gate.peak == 2 and states.count("running") == 2
    assert states.count("queued") == 3 and all(_row(rest, i)["attempt"] == 0 for i in ids if _row(rest, i)["status"] == "queued")
    gate.open.set()
    for _ in range(5):  # later recovery passes pick the deferred jobs up
        await asyncio.gather(*worker._tasks)
        await worker.recover_once()
    await asyncio.gather(*worker._tasks)
    assert [_row(rest, i)["status"] for i in ids] == ["finished"] * 5
    assert gate.peak == 2 and worker._running == 0
