"""Self-fencing lease (UNI-3306 PR 2, review r3): an attempt stops its own model before the
database claim can expire, even when its heartbeat never succeeds, so a second server's
attempt can never overlap it. Two servers share one fake store and one fake database clock;
the monotonic clock the watchdog reads is stepped in lockstep with that database clock."""
from __future__ import annotations

import asyncio
import re
import threading
from pathlib import Path
from typing import Any

import pytest

from app.server import goal_analysis_jobs as jobs, goal_analysis_slots as slots, goal_analysis_worker as worker
from app.server.spec_pipeline import llm
from tests import goal_worker_helpers as h
from tests.goal_jobs_helpers import CLAIM, MARGIN, FakeRest
from tests.goal_worker_helpers import PLAN, _queued, _row

_fresh_slots, rest = h._fresh_slots, h.rest

MIGRATION = Path(__file__).parents[1] / "supabase/migrations/20261108T010000_goal_analysis_job_functions.sql"


def test_claim_length_is_pinned_to_the_sql_functions() -> None:
    lengths = set(re.findall(r"claim_expires_at = v_at \+ interval '(\d+) seconds'", MIGRATION.read_text()))
    assert lengths == {str(int(slots.CLAIM_S))} and CLAIM == slots.CLAIM_S


def test_fence_constants_prove_stop_completes_before_the_claim_can_expire() -> None:
    fence_after = slots.CLAIM_S - slots.FENCE_SAFETY_S
    stop_done = fence_after + slots.WATCH_POLL_S + slots.STOP_BOUND_S
    assert stop_done < slots.CLAIM_S  # stop is complete before the claim can expire
    assert 2 * worker.HEARTBEAT_S < fence_after  # a healthy attempt tolerates two lost beats
    assert worker.MODEL_END_S >= slots.STOP_BOUND_S
    assert worker._MODEL_BUDGET_S + slots.FENCE_SAFETY_S < 300  # inside the SQL attempt deadline


class Coop:
    """A cooperative model shared by both servers: ends when stop is set, counts live calls."""

    def __init__(self) -> None:
        self.calls = self.alive = self.peak = 0
        self.finish = threading.Event()

    async def __call__(self, *, prompt: str, system: str, role: str, max_tokens: int,
                       stop: threading.Event) -> tuple[str, float]:
        self.calls += 1
        self.alive += 1
        self.peak = max(self.peak, self.alive)
        try:
            while not stop.is_set() and not self.finish.is_set():
                await asyncio.sleep(0.005)
        finally:
            self.alive -= 1
        if stop.is_set():
            raise llm.Stopped("stopped")
        return PLAN, 0.0


async def _until(cond: Any, timeout: float = 3.0) -> None:
    end = asyncio.get_running_loop().time() + timeout
    while not cond():
        assert asyncio.get_running_loop().time() < end, "condition never became true"
        await asyncio.sleep(0.005)


async def test_stalled_heartbeat_server_stops_its_model_before_the_claim_expires(
        rest: FakeRest, monkeypatch: pytest.MonkeyPatch) -> None:
    mono = [1000.0]
    monkeypatch.setattr(slots, "_now", lambda: mono[0])
    monkeypatch.setattr(slots, "WATCH_POLL_S", 0.005)
    hang = threading.Event()  # server A's heartbeat call hangs and never succeeds
    monkeypatch.setattr(jobs, "heartbeat", lambda *a: hang.wait() and False)
    coop = Coop()
    job_id = _queued()
    server_a = asyncio.create_task(worker.run_job(job_id, server="A", complete_fn=coop, heartbeat_s=0.01))
    try:
        await _until(lambda: coop.alive == 1)

        async def step(seconds: int) -> None:  # one fake second on BOTH clocks
            for _ in range(seconds):
                mono[0] += 1
                rest.advance(1)
                await asyncio.sleep(0.03)

        await step(40)
        assert coop.alive == 1  # not fenced early: the lease is still inside its window
        await step(CLAIM - 40 - 3)  # t = 57 s, three seconds BEFORE the claim expires
        assert rest.now < _row_expiry(rest, job_id)
        assert coop.alive == 0, "server A's model must have ended before the claim could expire"
        assert await asyncio.wait_for(server_a, 5) == "abandoned"
        assert _row(rest, job_id)["status"] == "running"  # it wrote nothing
        await step(CLAIM + MARGIN + 1 - 57)  # claim expired; recovery may interrupt
        assert await asyncio.to_thread(jobs.recover_expired) == [job_id]
        coop.finish.set()
        assert await worker.run_job(job_id, server="B", complete_fn=coop, heartbeat_s=1000) == "finished"
        row = _row(rest, job_id)
        assert row["status"] == "finished" and row["attempt"] == 2 and row["claimed_by"] == "B"
        assert coop.calls == 2 and coop.peak == 1  # never two model calls at once, across both servers
    finally:
        hang.set()
        server_a.cancel()
        await asyncio.gather(server_a, return_exceptions=True)


def _row_expiry(rest: FakeRest, job_id: str) -> Any:
    from datetime import datetime
    return datetime.fromisoformat(str(_row(rest, job_id)["claim_expires_at"]))
