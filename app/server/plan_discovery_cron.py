"""Daily plan-discovery cron hook — backlog snapshot for planner context.

The `plan-discovery-daily-0300` trigger fires at 03:00 UTC and writes a
JSON manifest of the autonomy queue to `.harness/plan-discovery-backlog/`.
Downstream planner / board flows can read today's file without re-querying
Linear on every session start.
"""
from __future__ import annotations

import asyncio
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = _REPO_ROOT / "scripts" / "run_plan_discovery_backlog.py"


async def _fire_plan_discovery_trigger(trigger: dict, log_arg) -> None:
    """Cron dispatcher hook. trigger = {type: 'plan_discovery', ...}."""
    if not _SCRIPT.is_file():
        raise FileNotFoundError(f"plan discovery script missing: {_SCRIPT}")

    log_arg.info("Firing plan_discovery trigger id=%s", trigger.get("id"))
    started = time.monotonic()
    proc = await asyncio.create_subprocess_exec(
        "python3",
        str(_SCRIPT),
        "--json",
        cwd=str(_REPO_ROOT),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=300)
    elapsed = round(time.monotonic() - started, 2)

    if proc.returncode != 0:
        err = stderr.decode("utf-8", errors="replace")[:500]
        log_arg.error(
            "plan_discovery id=%s failed rc=%d in %.2fs: %s",
            trigger.get("id"), proc.returncode, elapsed, err,
        )
        raise RuntimeError(f"plan_discovery script exited {proc.returncode}")

    summary = stdout.decode("utf-8", errors="replace").strip()[:300]
    log_arg.info(
        "plan_discovery id=%s done in %.2fs: %s",
        trigger.get("id"), elapsed, summary,
    )


__all__ = ["_fire_plan_discovery_trigger"]
