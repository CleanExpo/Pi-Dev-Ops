"""
cron_store.py — JSON persistence for cron triggers (GROUP F).

Stores triggers in .harness/cron-triggers.json using atomic write-tmp-then-replace.

Public API:
    list_triggers()         -> list[dict]
    create_trigger(...)     -> dict
    delete_trigger(tid)     -> bool
"""
import json
import os
import time
import uuid

_TRIGGERS_FILE = os.path.join(
    os.path.dirname(__file__), "..", "..", ".harness", "cron-triggers.json"
)


def _load_triggers() -> list[dict]:
    try:
        with open(_TRIGGERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return []


def _save_triggers(triggers: list[dict]) -> None:
    os.makedirs(os.path.dirname(_TRIGGERS_FILE), exist_ok=True)
    tmp = _TRIGGERS_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(triggers, f, indent=2)
        os.replace(tmp, _TRIGGERS_FILE)
    except OSError:
        pass


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
