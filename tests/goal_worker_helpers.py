"""Shared fakes for the goal analysis worker tests (UNI-3306 PR 2)."""
from __future__ import annotations

import asyncio
import threading
import time

from typing import Any

import pytest

from app.server import goal_analysis_jobs as jobs, goal_analysis_slots as slots, goal_analysis_worker as worker
from app.server.routes import goal_ticket_async
from app.server.spec_pipeline import llm
from tests.goal_jobs_helpers import FakeRest

PROJECT = {"id": "ra", "title": "RestoreAssist", "description": "d", "audience": "a"}
GOAL, ACCEPT = "Finalise RestoreAssist for Stage 1", "Tickets are drafted for review"
PLAN = (
    '{"summary":"One hop.","split_reason":"atomic","tickets":[{"title":"Finish stage one",'
    '"expected_behaviour":"Stage one work is split into tickets","acceptance":"Each ticket has a test.",'
    '"context":"RA","current_behaviour":"Open.","technical_requirements":"None.",'
    '"testing":"Run the suite.","rationale":"single"}]}'
)


class Model:
    """The fake model call. `hold` makes it wait for the stop signal like a real subprocess."""

    def __init__(self, text: str = PLAN, hold: bool = False, forever: bool = False) -> None:
        self.text, self.hold, self.forever = text, hold, forever
        self.calls = 0
        self.stop_seen_at: float | None = None

    async def __call__(self, *, prompt: str, system: str, role: str, max_tokens: int,
                       stop: threading.Event) -> tuple[str, float]:
        self.calls += 1
        if self.forever:  # like a provider thread: only the stop signal ends it
            while not stop.is_set():
                await asyncio.sleep(0.01)
            raise llm.Stopped("stopped by the worker")
        while self.hold and not stop.is_set():
            await asyncio.sleep(0.01)
        if self.hold:
            self.stop_seen_at = time.monotonic()
            raise llm.Stopped("stopped by the worker")
        return self.text, 0.01


@pytest.fixture(autouse=True)
def _fresh_slots(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(slots, "_running", 0)
    monkeypatch.setattr(slots, "_live", set())
    monkeypatch.setattr(worker, "_tasks", set())


@pytest.fixture
def rest(monkeypatch: pytest.MonkeyPatch) -> FakeRest:
    fake = FakeRest()
    monkeypatch.setattr(jobs, "_request", fake)
    monkeypatch.setattr(worker, "get_project", lambda pid: PROJECT if pid == "ra" else None)
    monkeypatch.setattr(goal_ticket_async, "get_project", lambda pid: PROJECT if pid == "ra" else None)
    return fake


@pytest.fixture
def launched(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    ids: list[str] = []
    monkeypatch.setattr(worker, "launch", ids.append)
    return ids


@pytest.fixture
def async_on(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GOAL_ANALYZE_ASYNC", "1")
    monkeypatch.setitem(worker._state, "available", True)
    monkeypatch.setitem(worker._state, "reason", "")


def _queued(key: str = "key-0001") -> str:
    return jobs.submit("ra", GOAL, ACCEPT, key)["id"]


def _row(rest: FakeRest, job_id: str) -> dict[str, Any]:
    return next(r for r in rest.rows if r["id"] == job_id)
