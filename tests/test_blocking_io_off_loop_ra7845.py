"""RA-7845: the two blocking calls the loop-lag monitor caught in production
(09:45 UTC, 29 Sept 2026) now run on a worker thread, not the event loop."""
import asyncio
import threading

import pytest

from app.server import autonomy, config as server_config, cron_scheduler


class _Stop(Exception):
    pass


def test_orphan_recovery_runs_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, int] = {}

    async def fake_recovery(api_key: str) -> None:
        seen["recovery"] = threading.get_ident()

    monkeypatch.setattr(autonomy, "_orphan_recovery", fake_recovery)
    monkeypatch.setattr(autonomy, "fetch_todo_issues", lambda key: [])
    monkeypatch.setattr(autonomy, "_log_event", lambda event: None)
    cfg = server_config
    monkeypatch.setattr(cfg, "AUTONOMY_ENABLED", True)
    monkeypatch.setattr(cfg, "LINEAR_API_KEY", "test-key")

    async def run() -> bool:
        seen["loop"] = threading.get_ident()
        return await autonomy._run_poller_iteration(cfg, None, False)

    assert asyncio.run(run()) is True
    assert "recovery" in seen, "orphan recovery never ran"
    assert seen["recovery"] != seen["loop"]


def test_cron_trigger_store_io_runs_off_the_event_loop(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, int] = {}
    sleeps = {"n": 0}

    def fake_load() -> list:
        seen["load"] = threading.get_ident()
        return [{"id": "t1"}]

    def fake_save(triggers: list) -> None:
        seen["save"] = threading.get_ident()

    async def fake_fire(trigger: dict, log: object) -> None:
        return None

    async def fake_sleep(seconds: float) -> None:
        sleeps["n"] += 1
        if sleeps["n"] > 1:  # stop at the main loop's first 60 s wait
            raise _Stop

    monkeypatch.setattr(cron_scheduler, "_load_triggers", fake_load)
    monkeypatch.setattr(cron_scheduler, "_save_triggers", fake_save)
    monkeypatch.setattr(cron_scheduler, "should_fire_on_boot", lambda t: True)
    monkeypatch.setattr(cron_scheduler, "_fire_trigger", fake_fire)
    monkeypatch.setattr(cron_scheduler.asyncio, "sleep", fake_sleep)

    async def run() -> None:
        seen["loop"] = threading.get_ident()
        await cron_scheduler.cron_loop()

    with pytest.raises(_Stop):
        asyncio.run(run())
    assert {"load", "save"} <= seen.keys(), seen
    assert seen["load"] != seen["loop"]
    assert seen["save"] != seen["loop"]
