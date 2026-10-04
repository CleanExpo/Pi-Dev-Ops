"""RA-7845 — repeated live polls share off-loop Linear reads."""
from __future__ import annotations

import asyncio
import threading
import time

import pytest

from app.server.routes import mission_control


@pytest.fixture(autouse=True)
def _empty_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LINEAR_API_KEY", "test-key")
    monkeypatch.setattr(mission_control, "_queue_cache", None)
    monkeypatch.setattr(mission_control, "_pulse_cache", None)


def test_second_poll_within_ttl_does_not_call_linear_again(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def read() -> dict:
        calls.append(1)
        return {"n": len(calls)}

    monkeypatch.setattr(mission_control, "_queue_snapshot", read)
    assert mission_control._cached_queue_snapshot() == {"n": 1}
    assert mission_control._cached_queue_snapshot() == {"n": 1}
    assert calls == [1]


def test_read_refreshes_after_the_ttl(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def read() -> dict:
        calls.append(1)
        return {"n": len(calls)}

    monkeypatch.setattr(mission_control, "_queue_snapshot", read)
    monkeypatch.setattr(mission_control, "_QUEUE_CACHE_SECONDS", 0)
    assert mission_control._cached_queue_snapshot() == {"n": 1}
    assert mission_control._cached_queue_snapshot() == {"n": 2}


def _stub_live_dependencies(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("_hourly_throughput_24h", "_active_sessions", "_recent_completions"):
        monkeypatch.setattr(mission_control, name, lambda: [])
    monkeypatch.setattr(mission_control, "_nexus_one_status", lambda: {})
    monkeypatch.setattr(mission_control, "_idea_pipeline_snapshot", lambda *_: {})
    monkeypatch.setattr(mission_control, "_pulse_status", lambda: {})
    async def observability() -> dict:
        return {}
    monkeypatch.setattr(mission_control, "_observability_snapshot", observability)


async def test_read_runs_in_a_worker_thread_not_on_the_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_live_dependencies(monkeypatch)
    seen: list[bool] = []

    def read() -> dict:
        seen.append(threading.current_thread() is threading.main_thread())
        return {}

    monkeypatch.setattr(mission_control, "_queue_snapshot", read)
    await mission_control.mission_control_live()
    assert seen == [False]


async def test_a_slow_linear_read_does_not_freeze_other_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    _stub_live_dependencies(monkeypatch)
    monkeypatch.setattr(mission_control, "_queue_snapshot", lambda: (time.sleep(0.6), {})[1])
    ticks: list[float] = []

    async def other_request() -> None:
        for _ in range(5):
            ticks.append(time.monotonic())
            await asyncio.sleep(0.05)

    await asyncio.gather(mission_control.mission_control_live(), other_request())
    assert len(ticks) == 5
    assert ticks[-1] - ticks[0] < 0.5


async def test_concurrent_polls_share_one_refresh(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[int] = []

    def read() -> dict:
        calls.append(1)
        time.sleep(0.1)
        return {}

    monkeypatch.setattr(mission_control, "_queue_snapshot", read)
    await asyncio.gather(*(asyncio.to_thread(mission_control._cached_queue_snapshot) for _ in range(5)))
    assert calls == [1]
