"""Startup tasks that write to Linear, Telegram or Supabase.

app_factory.on_startup starts each of these through
production_gate.run_if_production_allowed, so a Railway preview never runs them.
They live here, not in app_factory, to keep that file under its length limit.
`resilient` is app_factory._resilient, passed in because importing it would be circular.
"""
from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import Callable


def recover_sessions_from_supabase(log: logging.Logger) -> None:
    """RA-1407 PR 2: cross-deploy recovery of interrupted sessions from Supabase."""
    try:
        from .session_model import recover_interrupted_sessions_from_supabase  # noqa: PLC0415
        recovered = recover_interrupted_sessions_from_supabase()
        if recovered:
            log.info("RA-1407 startup: scheduled %d session(s) for resume from Supabase", recovered)
    except Exception as exc:
        log.warning("RA-1407 startup recovery failed (non-fatal): %s", exc)


def start_swarm_orchestrator(resilient: Callable, log: logging.Logger) -> None:
    """RA-1869: run swarm/orchestrator.py:run() in its own thread, restarted on crash.

    Gated on TAO_SWARM_ENABLED so it is reversible. TAO_SWARM_INTERNAL_DISABLE=1 lets a
    host disable the in-process swarm when an external launchd-managed swarm already runs
    on the same machine (avoids duplicate cycles and duplicate Telegram alerts).
    """
    if os.environ.get("TAO_SWARM_ENABLED") != "1" or os.environ.get("TAO_SWARM_INTERNAL_DISABLE") == "1":
        log.info("Swarm orchestrator NOT started (TAO_SWARM_ENABLED != 1)")
        return
    try:
        from swarm import orchestrator as _swarm_orchestrator  # noqa: PLC0415

        async def _run_swarm() -> None:
            await asyncio.to_thread(_swarm_orchestrator.run)

        asyncio.create_task(resilient(_run_swarm, "swarm_orchestrator"))
        log.info("Swarm orchestrator scheduled (TAO_SWARM_ENABLED=1)")
    except Exception as exc:
        log.warning("Swarm orchestrator startup failed (non-fatal, FastAPI continues): %s", exc)


def start_nexus_scheduler(resilient: Callable, log: logging.Logger) -> None:
    """Nexus Phase B.5/B8: once-a-day loop at NEXUS_SCHEDULER_HOUR (default 06).

    Opt in with NEXUS_SCHEDULER_ENABLED=1; NEXUS_SCHEDULER_DRY_RUN=1 logs only;
    NEXUS_SCHEDULER_WORKSPACES=a,b names the workspaces.
    """
    if os.environ.get("NEXUS_SCHEDULER_ENABLED") != "1":
        log.info("nexus scheduler NOT started (set NEXUS_SCHEDULER_ENABLED=1 to enable)")
        return
    try:
        from swarm.nexus.scheduler_daemon import nexus_scheduler_loop  # noqa: PLC0415
        asyncio.create_task(resilient(nexus_scheduler_loop, "nexus_scheduler"))
        log.info("nexus scheduler scheduled (NEXUS_SCHEDULER_ENABLED=1)")
    except Exception as exc:
        log.warning("nexus scheduler startup failed (non-fatal): %s", exc)
