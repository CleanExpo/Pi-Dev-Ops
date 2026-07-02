#!/usr/bin/env python3
"""Autonomous-mode health probe — RA-6892.

Prints JSON summary (no secrets). Exit 0 when autonomy is enabled,
machine-ship is ready, and the Linear queue fetch succeeds.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def _load_app_env_local() -> None:
    """Load app/.env.local — always wins over inherited shell env (local dev SSOT)."""
    path = _ROOT / "app" / ".env.local"
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if value.startswith("op://"):
            continue
        os.environ[key] = value


def _autonomy_enabled() -> bool:
    return os.environ.get("TAO_AUTONOMY_ENABLED", "1").strip() != "0"


def main() -> int:
    _load_app_env_local()
    # Local standby forces machine-ship on after sourcing app/.env.local.
    if os.environ.get("TAO_MACHINE_SHIP_MODE", "0").strip() != "1":
        os.environ["TAO_MACHINE_SHIP_MODE"] = "1"

    from app.server.autonomy import _gql, _load_portfolio_projects, fetch_todo_issues
    from app.server.machine_ship_readiness import machine_ship_readiness

    blockers: list[str] = []
    autonomy_on = _autonomy_enabled()
    if not autonomy_on:
        blockers.append("TAO_AUTONOMY_ENABLED=0")

    ship = machine_ship_readiness()
    blockers.extend(ship["blockers"])

    projects = _load_portfolio_projects()
    queue_depth = 0
    queue_ok = False
    api_key = (os.environ.get("LINEAR_API_KEY") or "").strip()
    if not api_key or api_key.startswith("op://"):
        blockers.append("LINEAR_API_KEY unset or unresolved op:// ref")
    else:
        try:
            _gql(api_key, "query { viewer { id } }")
            queue_ok = True
            queue_depth = len(fetch_todo_issues(api_key))
        except Exception as exc:  # noqa: BLE001
            blockers.append(f"Linear API check failed: {exc}")

    report = {
        "ok": autonomy_on and ship["ready"] and queue_ok,
        "autonomy_enabled": autonomy_on,
        "machine_ship": ship,
        "portfolio_projects": len(projects),
        "queue_depth": queue_depth,
        "blockers": blockers,
    }
    print(json.dumps(report, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
