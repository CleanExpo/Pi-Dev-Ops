#!/usr/bin/env python3
"""UNI-2236 — run marketing skill bridge once (cron / manual).

Requires TAO_FOUNDER_USER_ID (or FOUNDER_USER_ID) — must match Unite-Hub
FOUNDER_USER_ID so /api/cron/social-publisher drains seeded rows.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from swarm.marketing_skill_bridge import run_scheduled_bridge  # noqa: E402


def main() -> int:
    result = run_scheduled_bridge()
    print(json.dumps({
        "rows_written": result.rows_written,
        "rows_skipped": result.rows_skipped,
        "post_ids": result.post_ids,
        "errors": result.errors,
    }, indent=2))
    return 1 if result.errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
