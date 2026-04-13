#!/usr/bin/env python3
"""
run_parallel_board.py — Run board meetings in parallel: existing system + Managed Agents API

Compares both systems side-by-side and logs metrics for the 14-day PoC evaluation.

Usage:
    python scripts/run_parallel_board.py [--dry-run] [--cycle N]

Environment:
    ANTHROPIC_API_KEY — required for Managed Agents API
    AGENT_ID — optional, reuse existing agent (skip creation)
    ENV_ID — optional, reuse existing environment (skip creation)

Kill criteria (abort PoC if any triggered):
    1. Session lifecycle incompatible with 6h cron (idle timeout < 6h)
    2. MCP connectivity fails from within SDK container
    3. Cost > 5x raw API baseline
"""
from __future__ import annotations

import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger("pi-ceo.parallel-board")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
METRICS_DIR = PROJECT_ROOT / ".harness" / "poc-metrics"


def run_existing_system(cycle: int) -> dict:
    """Run board meeting via the existing scheduled task system.

    This is a stub that records timing. The actual board meeting runs
    via the Claude Desktop scheduled task (every 6h).
    """
    log.info("[EXISTING] Board meeting cycle %d — checking last run", cycle)
    board_dir = PROJECT_ROOT / ".harness" / "board-meetings"
    minutes_files = sorted(board_dir.glob("*.md")) if board_dir.exists() else []

    if minutes_files:
        latest = minutes_files[-1]
        return {
            "system": "existing",
            "cycle": cycle,
            "latest_minutes": latest.name,
            "minutes_size": latest.stat().st_size,
            "status": "found",
        }
    return {
        "system": "existing",
        "cycle": cycle,
        "status": "no_minutes_found",
    }


def run_managed_agents(cycle: int, dry_run: bool = False) -> dict:
    """Run board meeting via the Managed Agents API."""
    try:
        from anthropic import Anthropic

        sys.path.insert(0, str(PROJECT_ROOT))
        from app.server.agents.board_meeting import (
            create_agent,
            create_environment,
            run_board_meeting,
        )
    except ImportError as e:
        log.error("[MANAGED] Import failed: %s", e)
        return {"system": "managed_agents", "cycle": cycle, "status": "import_error", "error": str(e)}

    client = Anthropic()

    agent_id = os.environ.get("AGENT_ID")
    env_id = os.environ.get("ENV_ID")

    try:
        if not agent_id:
            agent_info = create_agent(client)
            agent_id = agent_info["id"]

        if not env_id:
            env_id = create_environment(client)

        result = run_board_meeting(
            client=client,
            agent_id=agent_id,
            environment_id=env_id,
            cycle=cycle,
            dry_run=dry_run,
        )
        return {
            "system": "managed_agents",
            "agent_id": agent_id,
            "env_id": env_id,
            **{k: v for k, v in result.items() if k != "minutes"},
            "status": "success" if not dry_run else "dry_run",
        }
    except Exception as e:
        log.error("[MANAGED] Failed: %s", e, exc_info=True)
        return {
            "system": "managed_agents",
            "cycle": cycle,
            "status": "error",
            "error": str(e),
        }


def save_metrics(existing: dict, managed: dict, cycle: int) -> Path:
    """Save comparison metrics to .harness/poc-metrics/."""
    METRICS_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    filename = f"cycle-{cycle:04d}-{now.strftime('%Y%m%d-%H%M')}.json"
    filepath = METRICS_DIR / filename

    metrics = {
        "timestamp": now.isoformat(),
        "cycle": cycle,
        "existing_system": existing,
        "managed_agents": managed,
        "comparison": {
            "managed_duration_s": managed.get("duration_s", 0),
            "managed_events": managed.get("events_count", 0),
            "managed_tools": len(managed.get("tools_used", [])),
            "managed_status": managed.get("status"),
            "existing_status": existing.get("status"),
        },
    }

    filepath.write_text(json.dumps(metrics, indent=2, default=str))
    log.info("Metrics saved: %s", filepath)
    return filepath


def check_kill_criteria(metrics_dir: Path) -> list[str]:
    """Check PoC kill criteria against accumulated metrics."""
    violations: list[str] = []
    metric_files = sorted(metrics_dir.glob("cycle-*.json"))

    consecutive_errors = 0
    for f in metric_files[-14:]:
        data = json.loads(f.read_text())
        managed = data.get("managed_agents", {})
        if managed.get("status") == "error":
            consecutive_errors += 1
        else:
            consecutive_errors = 0

    if consecutive_errors >= 3:
        violations.append(f"KILL: {consecutive_errors} consecutive managed agent errors")

    return violations


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Run parallel board meetings (existing + Managed Agents)")
    parser.add_argument("--dry-run", action="store_true", help="Don't execute Managed Agents session")
    parser.add_argument("--cycle", type=int, help="Override cycle number")
    args = parser.parse_args()

    now = datetime.now(timezone.utc)
    cycle = args.cycle or int(now.timestamp() // (6 * 3600))

    log.info("=== Parallel Board Meeting — Cycle %d ===", cycle)

    # Run both systems
    existing_result = run_existing_system(cycle)
    managed_result = run_managed_agents(cycle, dry_run=args.dry_run)

    # Save metrics
    metrics_path = save_metrics(existing_result, managed_result, cycle)

    # Check kill criteria
    violations = check_kill_criteria(METRICS_DIR)
    if violations:
        log.warning("KILL CRITERIA TRIGGERED:")
        for v in violations:
            log.warning("  %s", v)

    # Summary
    print("\n=== PARALLEL BOARD MEETING SUMMARY ===")
    print(f"Cycle: {cycle}")
    print(f"Existing system: {existing_result.get('status')}")
    print(f"Managed Agents:  {managed_result.get('status')}")
    if managed_result.get("duration_s"):
        print(f"  Duration: {managed_result['duration_s']}s")
        print(f"  Events:   {managed_result.get('events_count', 0)}")
        print(f"  Tools:    {len(managed_result.get('tools_used', []))}")
    print(f"Metrics saved: {metrics_path}")
    if violations:
        print(f"\nKILL CRITERIA: {len(violations)} violation(s)")
        for v in violations:
            print(f"  {v}")


if __name__ == "__main__":
    main()
