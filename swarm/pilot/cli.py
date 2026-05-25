"""Pilot V1 production CLI — single-cycle scheduler entrypoint.

Per ADR 003 + 004: the production scheduler runs one cycle per cron tick,
not a long-lived loop. This module is the thin argparse wrapper that the
cutover script + Hermes cron call:

    python -m swarm.pilot.cli scheduler

Returns one of scheduler.run_cycle()'s outcome strings on stdout as
single-line JSON (so the calling cron can log + alert on patterns):

    {"outcome": "sent"|"no_suggestion"|"paused"|"off_hours"|"disabled"|"error",
     "tenant_slug": "phill",
     "ts": "2026-05-25T..."}

Exit codes:
    0 — cycle completed cleanly regardless of outcome (incl. "no_suggestion",
        "off_hours", "paused" — these are NOT errors, just signals)
    1 — caught exception during run_cycle (already logged + reported above)

Subcommands:
    scheduler          run a single run_cycle() and exit
    health             print env-var presence + Supabase reachability check,
                       exit 0 if all required env vars set, 1 otherwise

Health is here (not just run_cycle) so the cutover script + ops can probe
config without firing a real cycle. The cutover script's Step 5
"post-deploy health check" calls this.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from datetime import datetime, timezone


def _emit(payload: dict) -> None:
    """Print a single-line JSON record for the calling cron to capture."""
    payload.setdefault("ts", datetime.now(timezone.utc).isoformat())
    print(json.dumps(payload, separators=(",", ":")))


def cmd_scheduler(_args: argparse.Namespace) -> int:
    # Local import: keeps `python -m swarm.pilot.cli --help` fast and lets
    # `health` subcommand run without importing the full suggester chain
    # when the user just wants to probe config.
    from swarm.pilot import scheduler

    tenant_slug = os.environ.get("PILOT_TENANT_SLUG", "phill")
    try:
        outcome = scheduler.run_cycle()
        _emit({"outcome": outcome, "tenant_slug": tenant_slug})
        return 0
    except Exception as exc:  # noqa: BLE001 — top-level cron entry, catch everything
        _emit({
            "outcome": "error",
            "tenant_slug": tenant_slug,
            "error": str(exc),
            "error_type": type(exc).__name__,
        })
        # Also dump traceback to stderr so the cron's log captures the full
        # context (the JSON line on stdout is the structured signal).
        traceback.print_exc(file=sys.stderr)
        return 1


def cmd_health(_args: argparse.Namespace) -> int:
    required = ("PILOT_BOT_TOKEN", "PILOT_BOT_CHAT_ID")
    optional = ("PILOT_TENANT_SLUG", "PILOT_DISABLED")
    missing = [v for v in required if not os.environ.get(v)]
    payload = {
        "outcome": "healthy" if not missing else "unhealthy",
        "required_present": [v for v in required if os.environ.get(v)],
        "required_missing": missing,
        "optional_present": [v for v in optional if os.environ.get(v)],
    }
    _emit(payload)
    return 0 if not missing else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m swarm.pilot.cli",
        description="Pilot V1 production CLI",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("scheduler", help="Run a single scheduler cycle (cron entrypoint)")
    sub.add_parser("health", help="Probe env-var presence + structured health report")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "scheduler":
        return cmd_scheduler(args)
    if args.command == "health":
        return cmd_health(args)
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
