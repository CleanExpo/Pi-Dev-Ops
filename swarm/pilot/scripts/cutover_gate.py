"""Cutover precondition gate — blocks production scheduler before agreed window.

Cutover window: 2026-05-19T08:00Z (= 19 May 2026 18:00 AEST, UTC+10).
Per [[feedback-substrate-change-discipline]] Discipline 5: no production
cutover before the agreed date. Timestamp is HARD-BINDING.

Usage (LaunchAgent pre-condition):
    python -m swarm.pilot.scripts.cutover_gate && python -m swarm.pilot.cli scheduler

Exit codes:
    0 — gate open, safe to launch
    1 — gate closed (before cutover window)
"""
import sys
from datetime import datetime, timezone

# 19 May 2026 18:00 AEST = 19 May 2026 08:00 UTC (AEST is UTC+10, subtract 10h)
CUTOVER_AT = datetime(2026, 5, 19, 8, 0, tzinfo=timezone.utc)


def is_open() -> bool:
    """Return True if the cutover window has been reached."""
    return datetime.now(timezone.utc) >= CUTOVER_AT


def main() -> int:
    if not is_open():
        remaining = CUTOVER_AT - datetime.now(timezone.utc)
        hours, rem = divmod(int(remaining.total_seconds()), 3600)
        mins = rem // 60
        print(
            f"BLOCKED — cutover gate closed until {CUTOVER_AT.isoformat()} "
            f"({hours}h {mins}m remaining). "
            "Production scheduler will not start before Tue 2026-05-19 18:00 AEST.",
            file=sys.stderr,
        )
        return 1
    print(
        f"OPEN — cutover gate passed (now >= {CUTOVER_AT.isoformat()}). "
        "Proceeding to production scheduler."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
