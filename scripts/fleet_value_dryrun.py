#!/usr/bin/env python3
"""RA-6908 dry-run CLI — monthly fleet utilisation + sample routing table.

Usage:
  python scripts/fleet_value_dryrun.py
  python scripts/fleet_value_dryrun.py --roles planner,generator,margot.casual
  python scripts/fleet_value_dryrun.py --json

Never sets TAO_FLEET_OPTIMIZER_MODE=live. Founder must approve live routing
after reviewing this output (see RA-6908 acceptance criteria).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from swarm.fleet_value_optimizer import (  # noqa: E402
    format_report,
    is_dry_run,
    monthly_utilization_report,
    recommend_plan,
)

_DEFAULT_ROLES = (
    "planner",
    "orchestrator",
    "generator",
    "evaluator",
    "margot.casual",
    "margot.truth_check",
    "monitor",
)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fleet value optimizer dry-run (RA-6908)")
    parser.add_argument(
        "--roles",
        default=",".join(_DEFAULT_ROLES),
        help="Comma-separated roles to simulate routing for",
    )
    parser.add_argument("--json", action="store_true", help="Emit machine-readable JSON")
    args = parser.parse_args()

    report = monthly_utilization_report()
    roles = [r.strip() for r in args.roles.split(",") if r.strip()]
    decisions = [
        {
            "role": role,
            "recommended_plan": d.recommended_plan,
            "provider": d.provider,
            "model_id": d.model_id,
            "utilization_pct": d.utilization_pct,
            "reason": d.reason,
            "dry_run": d.dry_run,
        }
        for role in roles
        for d in [recommend_plan(role)]
    ]

    payload = {
        "dry_run": is_dry_run(),
        "utilization": report,
        "routing_table": decisions,
        "codex_loop_usage": sum(
            1 for d in decisions
            if d["recommended_plan"] == "codex"
            and d["role"] in {"generator", "evaluator", "monitor"}
        ),
    }

    if args.json:
        print(json.dumps(payload, indent=2))
    else:
        print(format_report(report))
        print("\n--- routing recommendations (dry-run) ---")
        for row in decisions:
            print(
                f"{row['role']:22} -> {row['recommended_plan']:14} "
                f"({row['provider']}:{row['model_id']}) "
                f"[{row['utilization_pct']}% util]"
            )
        print(f"\ncodex autonomous-loop violations: {payload['codex_loop_usage']}")
        if payload["codex_loop_usage"]:
            print("FAIL: Codex must not serve autonomous loops", file=sys.stderr)
            return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
