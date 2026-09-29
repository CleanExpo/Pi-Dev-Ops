"""RA-7845 — /api/mission-control/live must not block the event loop on Linear.

/live is polled every 5 s per open page. Its Linear reads are blocking urllib
calls; run inline they froze every request (production /health took 5-25 s)
and exhausted Linear's hourly quota. These tests pin the two properties the
fix provides: one refresh per TTL, and the read runs off the event loop.
"""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from app.server.routes import mission_control


@pytest.fixture(autouse=True)
def _empty_cache() -> None:
    mission_control._linear_cache.clear()


async def test_second_poll_within_ttl_does_not_call_linear_again() -> None:
    calls: list[int] = []

    def read() -> dict:
        calls.append(1)
        return {"n": len(calls)}

    first = await mission_control._cached_off_loop("queue", read)
    second = await mission_control._cached_off_loop("queue", read)
    assert calls == [1]
    assert first == second == {"n": 1}


async def test_read_refreshes_after_the_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def read() -> dict:
        calls.append(1)
        return {"n": len(calls)}

    await mission_control._cached_off_loop("queue", read)
    monkeypatch.setattr(mission_control, "_LINEAR_TTL_S", 0.0)
    assert await mission_control._cached_off_loop("queue", read) == {"n": 2}


async def test_read_runs_in_a_worker_thread_not_on_the_loop() -> None:
    seen: dict[str, bool] = {}

    def read() -> dict:
        seen["main"] = threading.current_thread() is threading.main_thread()
        return {}

    await mission_control._cached_off_loop("pulse", read)
    assert seen == {"main": False}


async def test_a_slow_linear_read_does_not_freeze_other_requests() -> None:
    ticks: list[float] = []

    def slow_read() -> dict:
        time.sleep(0.6)  # a blocking urllib call, as in production
        return {}

    async def other_request() -> None:
        for _ in range(5):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.05)

    await asyncio.gather(mission_control._cached_off_loop("queue", slow_read), other_request())
    # Inline, the loop is held for the whole 0.6 s and all five ticks queue behind it.
    assert len(ticks) == 5
    assert ticks[-1] - ticks[0] < 0.5


async def test_concurrent_polls_share_one_refresh() -> None:
    calls: list[int] = []

    def read() -> dict:
        calls.append(1)
        time.sleep(0.1)
        return {}

    await asyncio.gather(*(mission_control._cached_off_loop("queue", read) for _ in range(5)))
    assert calls == [1]
