"""RA-7845: the loop-lag monitor names the code that froze the event loop."""
import asyncio
import logging
import threading
import time

import pytest

from app.server import loop_lag
from app.server.loop_lag import LoopLagMonitor, start_loop_lag_monitor


def _blocking_handler_for_test() -> None:
    time.sleep(0.8)  # a synchronous call inside async code: what froze production


async def _run_with_monitor(body) -> None:
    monitor = LoopLagMonitor(threshold_s=0.3, interval_s=0.1)
    task = asyncio.get_running_loop().create_task(monitor.heartbeat())
    watcher = threading.Thread(target=monitor.watch, daemon=True)
    await asyncio.sleep(0.15)
    watcher.start()
    try:
        await body()
        await asyncio.sleep(0.4)  # let the heartbeat resume so recovery is logged
    finally:
        monitor.stop()
        task.cancel()
        watcher.join(timeout=1)


def test_stall_logs_the_blocking_function(caplog: pytest.LogCaptureFixture) -> None:
    async def body() -> None:
        _blocking_handler_for_test()

    with caplog.at_level(logging.INFO, logger="pi-ceo.loop_lag"):
        asyncio.run(_run_with_monitor(body))
    stalls = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(stalls) == 1, stalls
    assert "_blocking_handler_for_test" in stalls[0]
    assert "time.sleep(0.8)" in stalls[0]
    assert any("recovered after" in r.getMessage() for r in caplog.records)


def test_healthy_loop_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    async def body() -> None:
        for _ in range(6):
            await asyncio.sleep(0.1)

    with caplog.at_level(logging.INFO, logger="pi-ceo.loop_lag"):
        asyncio.run(_run_with_monitor(body))
    assert not [r for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("env", [{"TAO_LOOP_LAG_ENABLED": "0"},
                                 {"TAO_LOOP_LAG_THRESHOLD_S": "abc"},
                                 {"TAO_LOOP_LAG_THRESHOLD_S": "0"}])
def test_disabled_or_bad_config_starts_nothing(monkeypatch: pytest.MonkeyPatch, env: dict) -> None:
    for key, value in env.items():
        monkeypatch.setenv(key, value)

    async def start() -> object:
        return start_loop_lag_monitor()

    assert asyncio.run(start()) is None


def test_start_runs_heartbeat_and_watcher(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("TAO_LOOP_LAG_ENABLED", raising=False)
    monkeypatch.delenv("TAO_LOOP_LAG_THRESHOLD_S", raising=False)

    async def start() -> tuple:
        monitor = start_loop_lag_monitor()
        before = monitor._beat
        await asyncio.sleep(1.1)
        monitor.stop()
        return monitor, before

    monitor, before = asyncio.run(start())
    assert isinstance(monitor, loop_lag.LoopLagMonitor)
    assert monitor.threshold_s == 2.0
    assert monitor._beat > before  # the heartbeat task really ran on the loop
