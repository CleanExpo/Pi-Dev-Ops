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
