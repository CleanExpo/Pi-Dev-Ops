"""tests/test_fire_trigger_dispatch.py — _fire_trigger dispatcher contract.

Pins the post-Hermes-audit behaviour: unknown trigger types raise
``ValueError`` instead of silently routing to ``create_session`` and
KeyErroring on a missing ``repo_url``. The old footgun let
plan-discovery-daily-0300 fail invisibly for months.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server.cron_triggers import _fire_trigger  # noqa: E402
import app.server.cron_triggers as cron_triggers  # noqa: E402


class _NullLog:
    def info(self, *a, **kw): pass
    def warning(self, *a, **kw): pass
    def error(self, *a, **kw): pass


def test_fire_trigger_raises_on_unknown_type():
    trigger = {
        "id": "fake-trigger",
        "type": "no_such_handler",
        "hour": 3, "minute": 0,
        "enabled": True,
    }
    with pytest.raises(ValueError, match="unknown trigger type 'no_such_handler'"):
        asyncio.run(_fire_trigger(trigger, _NullLog()))


def test_fire_trigger_routes_plan_discovery(monkeypatch):
    calls: list[str] = []

    async def fake_plan_discovery(trigger, log):
        calls.append(trigger["id"])

    import app.server.plan_discovery_cron as pdc  # noqa: E402
    monkeypatch.setattr(pdc, "_fire_plan_discovery_trigger", fake_plan_discovery)

    trigger = {
        "id": "plan-discovery-daily-0300",
        "type": "plan_discovery",
        "hour": 3,
        "minute": 0,
        "enabled": True,
    }
    asyncio.run(_fire_trigger(trigger, _NullLog()))
    assert calls == ["plan-discovery-daily-0300"]


def test_fire_trigger_routes_capability_loop_to_script_runner(monkeypatch):
    calls = []

    async def fake_script_runner(trigger, log):
        calls.append((trigger["id"], trigger["type"]))

    monkeypatch.setattr(cron_triggers, "_fire_script_trigger", fake_script_runner)

    trigger = {
        "id": "capability-loop-daily-0530",
        "type": "capability_loop",
        "script": "scripts/run_capability_loop.py --json",
        "hour": 5,
        "minute": 30,
        "enabled": True,
    }

    asyncio.run(_fire_trigger(trigger, _NullLog()))

    assert calls == [("capability-loop-daily-0530", "capability_loop")]
