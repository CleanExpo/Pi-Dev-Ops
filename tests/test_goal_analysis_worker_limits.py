"""Review round 1 fixes: model ends before retry, loop never blocked, concurrency limit (UNI-3306)."""
from __future__ import annotations

import asyncio
import threading
import time
from typing import Any

import pytest

from app.server import goal_analysis_jobs as jobs, goal_analysis_slots as slots, goal_analysis_worker as worker
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
        self.open, self.running, self.peak = threading.Event(), 0, 0

    async def __call__(self, *, prompt: str, system: str, role: str, max_tokens: int,
                       stop: threading.Event) -> tuple[str, float]:
        self.running += 1
        self.peak = max(self.peak, self.running)
        try:  # runs on the model thread's own loop, so poll a thread event
            while not self.open.is_set():
                await asyncio.sleep(0.01)
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
    assert gate.peak == 2 and slots._running == 0


class Stubborn(Model):
    """A NON-cooperative model call: it ignores stop and blocks on an event the test controls,
    like a blocking provider thread (e.g. an HTTP provider that never forwards stop)."""

    def __init__(self) -> None:
        super().__init__()
        self.release, self.alive, self.peak = threading.Event(), 0, 0

    async def __call__(self, *, prompt: str, system: str, role: str, max_tokens: int,
                       stop: threading.Event) -> tuple[str, float]:
        self.calls += 1
        self.alive += 1
        self.peak = max(self.peak, self.alive)
        try:
            self.release.wait()  # blocks this model thread; stop is ignored on purpose
        finally:
            self.alive -= 1
        return PLAN, 0.0


async def test_kill_with_a_model_that_ignores_stop_never_overlaps_attempts(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(worker, "MODEL_END_S", 0.05)
    stubborn = Stubborn()
    monkeypatch.setattr(llm, "complete", stubborn)
    monkeypatch.setattr(worker, "_require_stoppable_provider", lambda: None)
    job_id = _queued()
    assert worker.launch(job_id)
    await _until(lambda: stubborn.calls == 1)
    for task in list(worker._tasks):  # kill attempt 1: the coroutine goes, the model thread cannot
        task.cancel()
    await asyncio.gather(*worker._tasks, return_exceptions=True)
    assert stubborn.alive == 1 and slots._running == 1 and slots.is_live(job_id)  # slot not released
    rest.advance(CLAIM + MARGIN + 1)
    await worker.recover_once()
    await asyncio.sleep(0.2)
    assert _row(rest, job_id)["status"] == "interrupted"  # recovery ran, but...
    assert stubborn.calls == 1 and stubborn.peak == 1  # ...attempt 2 did not start
    stubborn.release.set()  # thread 1 finally returns; only now may the job run again
    await _until(lambda: slots._running == 0 and not slots.is_live(job_id))
    await worker.recover_once()
    await asyncio.gather(*worker._tasks)
    row = _row(rest, job_id)
    assert row["status"] == "finished" and row["attempt"] == 2
    assert stubborn.calls == 2 and stubborn.peak == 1


async def test_async_analysis_refuses_a_provider_that_cannot_be_stopped(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    from app.server import provider_router
    monkeypatch.setattr(worker, "select_provider_model",
                        lambda role, **kw: provider_router.ProviderModel("ollama", "llama3", "cheap", role, "default"))
    job_id = _queued()
    assert await worker.run_job(job_id, heartbeat_s=1000) == "failed"
    reason = _row(rest, job_id)["failure_reason"]
    assert "cannot be stopped" in reason and "ollama" in reason


async def test_a_model_thread_that_cannot_start_gives_its_slot_back(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    """Review round 5: ownership of the slot moves to the model thread only if that thread
    exists. A thread start failure must free the slot and the job's live entry, and a later
    job must still run."""
    monkeypatch.setattr(llm, "complete", Model())
    real_start = threading.Thread.start

    def start(self: threading.Thread) -> None:
        if self.name == "goal-analysis-model":
            raise RuntimeError("can't start new thread")
        real_start(self)

    monkeypatch.setattr(threading.Thread, "start", start)
    first = _queued("key-0001")
    assert worker.launch(first)
    await asyncio.gather(*worker._tasks)
    assert slots._running == 0 and not slots.is_live(first)
    assert slots.take(first) is not None  # not stranded
    slots._running, slots._live = 0, set()

    monkeypatch.setattr(threading.Thread, "start", real_start)
    second = jobs.submit("ra", "Finalise stage 2 of RestoreAssist", ACCEPT, "key-0002")["id"]
    assert worker.launch(second)
    await asyncio.gather(*worker._tasks)
    assert _row(rest, second)["status"] == "finished" and slots._running == 0
