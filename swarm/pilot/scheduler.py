"""Pilot scheduler — cadence-cron entry point.

Per ADR 003: checks pause_state before emitting. Expired paused-until
auto-resumes. Per ADR 003 scope-separation: L4 digest is a SEPARATE cron
that does NOT pass through this function.
"""
import os
from datetime import datetime, timezone
from typing import Literal

from swarm.pilot import memory, suggester, composer, dispatcher


def in_active_window(now: datetime) -> bool:
    """08:00–22:00 AEST = 22:00–12:00 UTC (rough — no DST correction)."""
    hour = now.hour
    return 22 <= hour or hour < 12


def _pause_blocks_emission(pause_state: str) -> bool:
    if pause_state == "active":
        return False
    if pause_state == "paused-hard":
        return True
    if pause_state.startswith("paused-until-"):
        ts_str = pause_state[len("paused-until-"):]
        try:
            ts = datetime.fromisoformat(ts_str)
        except ValueError:
            return True  # malformed → safe-default to paused
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < ts
    return True  # unknown → safe-default to paused


def run_cycle() -> Literal["disabled", "off_hours", "paused", "halt_gate", "no_suggestion", "sent"]:
    if os.getenv("PILOT_DISABLED", "0") == "1":
        return "disabled"
    if not in_active_window(datetime.now(timezone.utc)):
        return "off_hours"
    mem = memory.Memory()
    tenant_slug = os.environ.get("PILOT_TENANT_SLUG", "phill")
    if _pause_blocks_emission(mem.get_pause_state(tenant_slug)):
        return "paused"
    sug = suggester.pick_top(mem)
    if sug is None:
        return "no_suggestion"
    dispatcher.send(composer.format(sug), sug, mem)
    return "sent"
