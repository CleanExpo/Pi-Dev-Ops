"""
cron_store.py — Persistence for cron triggers (GROUP F).

Schedule definitions live in `.harness/cron-triggers.json` (committed to
git as the canonical schedule). RA-1439: per-trigger `last_fired_at` is
ALSO persisted to Supabase `cron_state` so Railway redeploys don't reset
it back to whatever's frozen in git — without durable state, every deploy
reverts to the committed last_fired_at and catch-up gets confused.

On load: JSON values for everything, then Supabase `cron_state` overlays
`last_fired_at` (Supabase wins).
On save: JSON gets the full schedule (atomic write-tmp-then-replace);
Supabase gets last_fired_at upserts (fire-and-forget).

Public API:
    list_triggers()         -> list[dict]
    create_trigger(...)     -> dict
    delete_trigger(tid)     -> bool
"""
import json
import logging
import os
import time
import uuid

_log = logging.getLogger("pi-ceo.cron_store")

_TRIGGERS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", ".harness", "cron-triggers.json"
)


def _load_triggers_from_disk() -> list[dict]:
    """Load schedule definitions from the committed JSON file."""
    try:
        with open(_TRIGGERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _load_triggers() -> list[dict]:
    """RA-1439 — Load triggers + overlay durable last_fired_at from Supabase.

    JSON file: canonical schedule (hour/minute/enabled/...).
    Supabase cron_state: durable last_fired_at, surviving Railway redeploys.

    Fail-soft on Supabase outage: falls back to JSON's last_fired_at value
    (which may be stale, but the system keeps running and catch-up still
    triggers because >8h-old timestamps remain >8h-old).
    """
    triggers = _load_triggers_from_disk()
    if not triggers:
        return triggers

    try:
        from . import supabase_log  # noqa: PLC0415
        state = supabase_log.load_cron_state()
    except Exception as exc:
        _log.warning("RA-1439 cron_state overlay failed (using JSON values): %s", exc)
        state = {}

    if state:
        for t in triggers:
            tid = t.get("id", "")
            if tid in state:
                t["last_fired_at"] = state[tid]
    return triggers


def _save_triggers(triggers: list[dict]) -> None:
    """Atomic JSON write of full schedule + Supabase upsert of last_fired_at.

    Both writes are best-effort. JSON failure logs and continues; Supabase
    failure is silent (per fire-and-forget mandate).
    """
    os.makedirs(os.path.dirname(_TRIGGERS_FILE), exist_ok=True)
    tmp = _TRIGGERS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(triggers, f, indent=2)
        os.replace(tmp, _TRIGGERS_FILE)
    except OSError:
        pass

    # RA-1439 — durable last_fired_at to Supabase so it survives redeploy.
    try:
        from . import supabase_log  # noqa: PLC0415
        for t in triggers:
            tid = t.get("id", "")
            last = t.get("last_fired_at")
            if tid and last:
                supabase_log.save_cron_last_fired(tid, float(last))
    except Exception:
        pass  # never let observability crash the cron loop


def list_triggers() -> list[dict]:
    return _load_triggers()


def create_trigger(
    repo_url: str,
    brief: str,
    minute: int,
    hour: int | None = None,
    model: str = "sonnet",
) -> dict:
    trigger = {
        "id": uuid.uuid4().hex[:12],
        "repo_url": repo_url,
        "brief": brief,
        "model": model,
        "hour": hour,
        "minute": minute,
        "enabled": True,
        "created_at": time.time(),
        "last_fired_at": None,
    }
    triggers = _load_triggers()
    triggers.append(trigger)
    _save_triggers(triggers)
    return trigger


def delete_trigger(tid: str) -> bool:
    triggers = _load_triggers()
    before = len(triggers)
    triggers = [t for t in triggers if t.get("id") != tid]
    if len(triggers) == before:
        return False
    _save_triggers(triggers)
    return True
