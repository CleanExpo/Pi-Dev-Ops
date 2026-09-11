"""Hide a Goal brief from the picker. Linear tickets are not touched."""
from __future__ import annotations

import json
from typing import Any

from .goal_projects import (
    GoalProjectStoreError,
    _TableMissing,
    _atomic_write,
    _request,
    _use_file,
    get_project,
    store_path,
)

_ARCHIVE_PREFIX = "goal_project_archived:"


def _file_payload() -> dict[str, Any]:
    path = store_path()
    if not path.is_file():
        return {"projects": [], "archived": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"projects": [], "archived": []}
    if not isinstance(data, dict):
        return {"projects": [], "archived": []}
    projects = data.get("projects") if isinstance(data.get("projects"), list) else []
    archived = [str(item) for item in (data.get("archived") or []) if str(item).strip()]
    return {"projects": projects, "archived": archived}


def _archived_from_settings() -> set[str]:
    from .supabase_log import _q

    try:
        body = _request("GET", f"settings?key=like.{_q(_ARCHIVE_PREFIX)}*&select=key,value")
    except (GoalProjectStoreError, _TableMissing):
        return set()
    if not isinstance(body, list):
        return set()
    ids: set[str] = set()
    for item in body:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or "")
        if key.startswith(_ARCHIVE_PREFIX):
            ids.add(key[len(_ARCHIVE_PREFIX) :])
    return {item for item in ids if item}


def archived_ids() -> set[str]:
    if _use_file():
        return {item for item in _file_payload()["archived"] if item}
    return _archived_from_settings()


def visible_projects(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    hidden = archived_ids()
    return [row for row in rows if row.get("id") not in hidden]


def archive_project(project_id: str) -> dict[str, str]:
    wanted = (project_id or "").strip()
    if not wanted:
        raise GoalProjectStoreError("unknown_project", "Create a brief first, then select it.")
    row = get_project(wanted)
    if not row:
        raise GoalProjectStoreError("unknown_project", "Create a brief first, then select it.")
    if _use_file():
        payload = _file_payload()
        if wanted not in payload["archived"]:
            payload["archived"].append(wanted)
        _atomic_write(store_path(), payload)
        return {"id": wanted, "archived": "true"}
    from datetime import datetime, timezone

    _request(
        "POST",
        "settings",
        {
            "key": f"{_ARCHIVE_PREFIX}{wanted}",
            "value": "1",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        },
    )
    return {"id": wanted, "archived": "true"}
