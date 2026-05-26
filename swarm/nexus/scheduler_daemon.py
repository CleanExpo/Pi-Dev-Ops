"""Always-on Nexus scheduler daemon — fires once per local day.

Phase B.5 / B8. Wraps `swarm.nexus.scheduler.run_nexus_cycle` in an
async loop that sleeps until the next NEXUS_SCHEDULER_HOUR local. The
loop is registered by app/server/app_factory.py's startup hook when
NEXUS_SCHEDULER_ENABLED=1.

Production wiring is deliberately minimal — workspaces to BRA are
read from NEXUS_SCHEDULER_WORKSPACES (csv); store factories are
imported lazily so this module can be unit-tested without booting
the full FastAPI app.

Side-effects: NONE until the operator sets NEXUS_SCHEDULER_ENABLED=1.
DRY_RUN: set NEXUS_SCHEDULER_DRY_RUN=1 — audits + idempotency marker
are still written, but no LLM calls and no outcomes writes.
"""
from __future__ import annotations

import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .scheduler import run_nexus_cycle

log = logging.getLogger("pi-ceo.nexus.scheduler_daemon")

DEFAULT_SCHEDULER_HOUR = 6
MARKER_DEFAULT_PATH = Path(".harness/nexus-scheduler-last-run.txt")


# ============================================================
# RealClock (timezone-aware UTC)
# ============================================================


class RealClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


def _scheduler_hour() -> int:
    try:
        return int(os.environ.get("NEXUS_SCHEDULER_HOUR", DEFAULT_SCHEDULER_HOUR))
    except ValueError:
        return DEFAULT_SCHEDULER_HOUR


def _workspaces() -> list[str]:
    raw = os.environ.get("NEXUS_SCHEDULER_WORKSPACES", "")
    return [w.strip() for w in raw.split(",") if w.strip()]


def _next_fire_seconds(now: datetime, hour: int) -> float:
    """Seconds until the next `hour`:00:00 UTC strictly after `now`."""
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return (target - now).total_seconds()


# ============================================================
# The loop
# ============================================================


async def nexus_scheduler_loop() -> None:
    """Main loop — sleep until next fire window, run one cycle, repeat.

    Failures inside run_nexus_cycle never raise (the pure-logic function
    swallows everything). If we somehow do raise here, the parent
    `_resilient(...)` wrapper in app_factory will restart us.
    """
    hour = _scheduler_hour()
    log.info("nexus_scheduler_loop online: fires daily at %02d:00 UTC", hour)

    while True:
        clock = RealClock()
        sleep_s = _next_fire_seconds(clock.now(), hour)
        log.info("nexus_scheduler sleeping %.0fs until next fire window", sleep_s)
        await asyncio.sleep(sleep_s)

        dry_run = os.environ.get("NEXUS_SCHEDULER_DRY_RUN", "1") == "1"
        workspaces = _workspaces()
        marker_path = Path(os.environ.get(
            "NEXUS_SCHEDULER_MARKER_PATH", str(MARKER_DEFAULT_PATH),
        ))

        try:
            stores = _resolve_stores()
            if stores is None:
                log.warning("nexus_scheduler skipped — stores unresolved")
                continue
            loops_store, outcomes_store, audit_store, llm = stores

            summary = run_nexus_cycle(
                workspace_slugs=workspaces,
                loops_store=loops_store,
                outcomes_store=outcomes_store,
                llm=llm,
                clock=clock,
                audit_store=audit_store,
                last_run_marker_path=marker_path,
                dry_run=dry_run,
            )
            log.info(
                "nexus_scheduler cycle done window=%s dry_run=%s "
                "bras=%d failed=%d",
                summary.window_key, dry_run,
                len(summary.bra_reports), len(summary.workspaces_failed),
            )
        except Exception as exc:  # noqa: BLE001 — defensive; never crash the daemon
            log.warning("nexus_scheduler cycle exception (non-fatal): %s", exc)


def _resolve_stores():
    """Lazy resolver — returns None when production stores aren't wired
    yet (B1 only ships the outcomes store; loops + audit follow in
    later PRs). Daemon then logs + skips the cycle gracefully.
    """
    try:
        from app.server import app_factory  # noqa: PLC0415
        nexus_stores = getattr(app_factory.app.state, "nexus_stores", None)
        if not nexus_stores:
            return None
        loops_store = nexus_stores.get("loops")
        outcomes_store = nexus_stores.get("outcomes")
        audit_store = nexus_stores.get("audit")
        llm = nexus_stores.get("llm")
        if not (loops_store and outcomes_store):
            return None
        return loops_store, outcomes_store, audit_store, llm
    except Exception as exc:  # noqa: BLE001
        log.warning("nexus_scheduler store resolution failed: %s", exc)
        return None


__all__ = [
    "DEFAULT_SCHEDULER_HOUR",
    "MARKER_DEFAULT_PATH",
    "RealClock",
    "nexus_scheduler_loop",
]
