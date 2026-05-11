"""Disable plan-discovery-daily-0300 — Hermes audit follow-up 2026-05-11.

Idempotent. Flips ``enabled: false`` on the trigger so the silent
KeyError loop stops, until a real ``_fire_plan_discovery_trigger``
handler is implemented (see Linear ticket /
Wiki/hermes-agent-sprinkle-audit-2026-05-11.md § plan-discovery
investigation).

Why a script instead of a direct .harness/cron-triggers.json edit:
the JSON file is hybrid tracked-but-runtime-mutated state, owned by
the cron loop. ``cron_store.update_trigger`` (new in this branch)
goes through the same atomic write + Supabase upsert path the cron
loop uses, so the runtime is left in a coherent state.

Run once:

    python scripts/disable-plan-discovery-2026-05-11.py
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from app.server import cron_store  # noqa: E402

TRIGGER_ID = "plan-discovery-daily-0300"


def main() -> int:
    triggers = {t.get("id"): t for t in cron_store.list_triggers()}
    current = triggers.get(TRIGGER_ID)
    if current is None:
        print(f"[skip] {TRIGGER_ID} not present — nothing to do")
        return 0
    if current.get("enabled") is False:
        print(f"[noop] {TRIGGER_ID} already disabled")
        return 0
    updated = cron_store.update_trigger(TRIGGER_ID, enabled=False)
    print(f"[ok]   {TRIGGER_ID} disabled (enabled={updated.get('enabled')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
