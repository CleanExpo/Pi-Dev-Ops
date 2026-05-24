"""Shadow-run driver — drive N scheduler cycles against a shadow tenant.

Per [[feedback-substrate-change-discipline]] Discipline 1: shadow-run before
cutover. Requires PILOT_SHADOW_MODE=1 + env pointing at a test bot (NOT
production). Uses tenant_slug='phill-shadow' isolated from real tenant data.

Records per-cycle outcomes to shadow_run_results.jsonl for parity diffing.

Usage:
    PILOT_SHADOW_MODE=1 PILOT_BOT_TOKEN=<test> python -m swarm.pilot.scripts.shadow_run
    PILOT_SHADOW_MODE=1 python -m swarm.pilot.scripts.shadow_run --cycles 50
"""
import argparse
import json
import os
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from swarm.pilot import scheduler

SHADOW_TENANT = "phill-shadow"
RESULTS_FILE = Path("shadow_run_results.jsonl")


def run(n: int = 10) -> dict:
    if os.environ.get("PILOT_SHADOW_MODE") != "1":
        raise RuntimeError(
            "PILOT_SHADOW_MODE=1 required — refusing to drive production scheduler"
        )

    os.environ.setdefault("PILOT_TENANT_SLUG", SHADOW_TENANT)
    if os.environ.get("PILOT_TENANT_SLUG") != SHADOW_TENANT:
        raise RuntimeError(
            f"PILOT_TENANT_SLUG must be '{SHADOW_TENANT}' in shadow mode — "
            f"got '{os.environ.get('PILOT_TENANT_SLUG')}'"
        )

    outcomes: Counter = Counter()
    errors: list[str] = []

    for i in range(n):
        try:
            result = scheduler.run_cycle()
            outcomes[result] += 1
        except Exception as exc:  # noqa: BLE001
            outcomes["error"] += 1
            errors.append(f"cycle {i}: {exc}")

    pillar_dist: dict = {}  # populated by real run when scheduler records pillars

    report = {
        "shadow_tenant": SHADOW_TENANT,
        "run_at": datetime.now(timezone.utc).isoformat(),
        "cycles": n,
        "sent": outcomes.get("sent", 0),
        "no_suggestion": outcomes.get("no_suggestion", 0),
        "paused": outcomes.get("paused", 0),
        "halt_gate": outcomes.get("halt_gate", 0),
        "off_hours": outcomes.get("off_hours", 0),
        "disabled": outcomes.get("disabled", 0),
        "error": outcomes.get("error", 0),
        "errors": errors,
        "pillar_distribution": pillar_dist,
        "dedup_rate": None,  # computed post-run in analysis
    }

    with RESULTS_FILE.open("a") as fh:
        fh.write(json.dumps(report) + "\n")

    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Pilot shadow-run driver")
    parser.add_argument("--cycles", type=int, default=10,
                        help="Number of scheduler cycles to run (default: 10)")
    args = parser.parse_args()
    report = run(n=args.cycles)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
