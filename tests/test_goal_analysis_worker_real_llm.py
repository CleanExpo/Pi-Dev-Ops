"""The worker with the REAL spec_pipeline llm.complete (UNI-3306 PR 2): only the provider
transport is faked. The model call runs on the model thread's own event loop (asyncio.run in
slots.run_in_thread), receives the lease's stop signal, and a stop ends it as llm.Stopped."""
from __future__ import annotations

import asyncio
import threading
import time
from types import SimpleNamespace

import pytest

from app.server import goal_analysis_jobs as jobs, goal_analysis_worker as worker, provider_router
from app.server.provider_execution import STOPPED_RC
from app.server.provider_execution_types import ProviderExecution
from tests import goal_worker_helpers as h
from tests.goal_jobs_helpers import FakeRest
from tests.goal_worker_helpers import PLAN, _queued, _row

_fresh_slots, rest = h._fresh_slots, h.rest

PROVENANCE = {"auth_verified": True, "model_verified": True, "actual_model": "claude-test",
              "provider": "claude_print", "source": "fake transport"}


class Transport:
    """Stands in for provider_router.run_via_provider_with_evidence and records where it ran."""

    def __init__(self, hold: bool = False) -> None:
        self.hold = hold
        self.thread: threading.Thread | None = None
        self.loop: asyncio.AbstractEventLoop | None = None
        self.stop: threading.Event | None = None

    async def __call__(self, *, prompt: str, role: str, stop: threading.Event | None = None) -> ProviderExecution:
        self.thread, self.loop, self.stop = threading.current_thread(), asyncio.get_running_loop(), stop
        assert role == "goal_analyst"
        if self.hold:
            while stop is not None and not stop.is_set():
                await asyncio.sleep(0.01)
            return ProviderExecution(STOPPED_RC, "", None, "stopped", dict(PROVENANCE))
        return ProviderExecution(0, PLAN, None, None, dict(PROVENANCE))


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> Transport:
    monkeypatch.setattr(worker, "select_provider_model",
                        lambda role, record_observation=False: SimpleNamespace(provider="claude_print"))
    t = Transport()
    monkeypatch.setattr(provider_router, "run_via_provider_with_evidence", t)
    return t


async def test_real_llm_complete_runs_on_the_model_threads_own_loop(rest: FakeRest, transport: Transport) -> None:
    job_id = _queued()
    assert await worker.run_job(job_id, server="A", heartbeat_s=1000) == "finished"
    assert transport.thread is not None and transport.thread is not threading.main_thread()
    assert transport.loop is not None and transport.loop is not asyncio.get_running_loop()
    assert isinstance(transport.stop, threading.Event)  # the lease's stop reached the transport
    row = _row(rest, job_id)
    assert row["status"] == "finished" and row["result"]["tickets"]
    assert row["result"]["cost_usd"] is None  # unobserved subscription cost stays unknown


async def test_a_stopped_real_llm_call_is_abandoned_and_writes_nothing(
        rest: FakeRest, transport: Transport, monkeypatch: pytest.MonkeyPatch) -> None:
    transport.hold = True
    lost = threading.Event()
    monkeypatch.setattr(jobs, "heartbeat", lambda *a: not lost.is_set())
    job_id = _queued()
    run = asyncio.create_task(worker.run_job(job_id, server="A", heartbeat_s=0.01))
    end = time.monotonic() + 3
    while transport.stop is None:
        assert time.monotonic() < end, "the transport was never called"
        await asyncio.sleep(0.01)
    lost.set()  # the next heartbeat reports the claim gone; the lease sets stop
    assert await asyncio.wait_for(run, 5) == "abandoned"
    assert transport.stop.is_set()
    assert _row(rest, job_id)["status"] == "running"  # the stopped attempt wrote nothing
    end = time.monotonic() + 3  # the model thread returns right after delivering its outcome
    while any(t.name == "goal-analysis-model" for t in threading.enumerate()):
        assert time.monotonic() < end, "the model thread outlived its stopped call"
        await asyncio.sleep(0.01)

