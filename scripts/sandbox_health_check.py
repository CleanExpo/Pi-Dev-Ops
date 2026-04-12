#!/usr/bin/env python3
"""
RA-628 — Sandbox health check helper.

Greps .harness/build-logs/ for sandbox-related events in a configurable
time window and returns structured JSON.

Exit codes:
  0 — healthy or idle (no failures)
  1 — critical (sandbox verification failures found)

Usage:
  python3 scripts/sandbox_health_check.py [--hours N]
"""
import argparse
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HARNESS_ROOT = Path(__file__).parents[1] / ".harness"
BUILD_LOGS_DIR = HARNESS_ROOT / "build-logs"

# Patterns to match in build log files (RA-628)
PATTERNS: dict[str, re.Pattern] = {
    "verification_ok":   re.compile(r"Phase 3\.5:?\s*sandbox verification", re.IGNORECASE),
    "auto_reclone":      re.compile(r"auto\s*re-?clone\s+triggered",          re.IGNORECASE),
    "gc_mid_session":    re.compile(r"sandbox\s+GC'?d?\s+mid-?session",       re.IGNORECASE),
    "failure":           re.compile(r"sandbox\s+verification\s+failed",        re.IGNORECASE),
}

# Status badge used in the board meeting Executive Summary
STATUS_BADGE = {
    "critical": "🔴 CRITICAL — sandbox verification failure(s) detected",
    "degraded": "🟡 DEGRADED — auto-reclone events (GC pressure, not fatal)",
    "healthy":  "🟢 HEALTHY — sandbox verification passed",
    "idle":     "⚪ IDLE — no sandbox events in window (system quiet or logs absent)",
    "no_logs":  "⚠️  NO LOGS — .harness/build-logs/ not found",
}


def check_logs(window_hours: int = 6) -> dict:
    """
    Scan build-logs modified within `window_hours` for sandbox events.

    Returns:
        {
            "status": "healthy" | "degraded" | "critical" | "idle" | "no_logs",
            "badge": str,               # human-readable one-liner for Executive Summary
            "events_6h": {              # counts within the time window
                "verification_ok": int,
                "auto_reclone": int,
                "gc_mid_session": int,
                "failure": int,
            },
            "last_failure_at": str | None,   # ISO-8601 or None
            "re_clones_6h": int,
            "window_hours": int,
            "log_dir": str,
            "files_scanned": int,
        }
    """
    if not BUILD_LOGS_DIR.exists():
        result = {
            "status": "no_logs",
            "events_6h": {k: 0 for k in PATTERNS},
            "last_failure_at": None,
            "re_clones_6h": 0,
            "window_hours": window_hours,
            "log_dir": str(BUILD_LOGS_DIR),
            "files_scanned": 0,
        }
        result["badge"] = STATUS_BADGE["no_logs"]
        return result

    cutoff = datetime.now(tz=timezone.utc) - timedelta(hours=window_hours)
    events: dict[str, int] = {k: 0 for k in PATTERNS}
    last_failure_at: str | None = None
    files_scanned = 0

    for log_file in sorted(BUILD_LOGS_DIR.iterdir()):
        if not log_file.is_file():
            continue
        try:
            mtime = datetime.fromtimestamp(log_file.stat().st_mtime, tz=timezone.utc)
            if mtime < cutoff:
                continue
            text = log_file.read_text(errors="replace")
            files_scanned += 1
            for event_type, pattern in PATTERNS.items():
                count = len(pattern.findall(text))
                if count:
                    events[event_type] += count
                    if event_type == "failure":
                        # track most recent file modification time as proxy for failure time
                        if last_failure_at is None or mtime.isoformat() > last_failure_at:
                            last_failure_at = mtime.isoformat()
        except Exception:
            continue

    # Determine status (ordered by severity)
    if events["failure"] > 0:
        status = "critical"
    elif events["gc_mid_session"] > 0 or events["auto_reclone"] > 0:
        status = "degraded"
    elif events["verification_ok"] > 0:
        status = "healthy"
    else:
        status = "idle"

    return {
        "status": status,
        "badge": STATUS_BADGE[status],
        "events_6h": events,
        "last_failure_at": last_failure_at,
        "re_clones_6h": events["auto_reclone"],
        "window_hours": window_hours,
        "log_dir": str(BUILD_LOGS_DIR),
        "files_scanned": files_scanned,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Sandbox health check (RA-628)")
    parser.add_argument("--hours", type=int, default=6,
                        help="Look-back window in hours (default: 6)")
    parser.add_argument("--json", dest="output_json", action="store_true",
                        help="Output raw JSON only (for machine consumption)")
    args = parser.parse_args()

    result = check_logs(window_hours=args.hours)

    if args.output_json:
        print(json.dumps(result, indent=2))
    else:
        print(f"\n{'='*55}")
        print(f"  Pi-CEO Sandbox Health Check  (last {args.hours}h)")
        print(f"{'='*55}")
        print(f"  Status:         {result['badge']}")
        print(f"  Files scanned:  {result['files_scanned']}")
        print(f"  Verifications:  {result['events_6h']['verification_ok']}")
        print(f"  Auto-reclones:  {result['re_clones_6h']}")
        print(f"  GC mid-session: {result['events_6h']['gc_mid_session']}")
        print(f"  Failures:       {result['events_6h']['failure']}")
        if result["last_failure_at"]:
            print(f"  Last failure:   {result['last_failure_at']}")
        print(f"{'='*55}\n")

    # Non-zero exit on critical
    return 1 if result["status"] == "critical" else 0


if __name__ == "__main__":
    sys.exit(main())
