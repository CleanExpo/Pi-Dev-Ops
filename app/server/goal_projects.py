"""Operator-created project briefs for Goal → Linear. Stored in Supabase."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen

_MIN = 8
_FIELDS = (
    "title",
    "description",
    "audience",
    "problem",
    "users",
    "outcomes",
    "constraints",
    "out_of_scope",
)
_TABLE = "goal_projects"


class GoalProjectStoreError(Exception):
    def __init__(self, code: str, hint: str) -> None:
        super().__init__(hint)
        self.code = code
        self.hint = hint


def store_path() -> Path:
    override = (os.environ.get("GOAL_PROJECTS_PATH") or "").strip()
    if override:
        return Path(override)
    raise GoalProjectStoreError(
        "file_store_disabled",
        "GOAL_PROJECTS_PATH is only for tests. Live projects are stored in Supabase.",
    )


def _use_file() -> bool:
    return bool((os.environ.get("GOAL_PROJECTS_PATH") or "").strip())


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def _as_row(raw: dict[str, Any]) -> dict[str, str]:
    return {key: str(raw.get(key) or "") for key in ("id", *_FIELDS, "created_at")}


def _new_row(body: dict[str, Any]) -> dict[str, str]:
    row = {key: str(body.get(key) or "").strip() for key in _FIELDS}
    row["id"] = str(uuid.uuid4())
    row["created_at"] = datetime.now(timezone.utc).isoformat()
    return row


def validate_brief(body: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in ("title", "description", "audience"):
        if len(str(body.get(key) or "").strip()) < _MIN:
            missing.append(key)
    return missing


def _db_headers(key: str, *, prefer: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json",
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Prefer": prefer,
        "Accept": "application/json",
    }


def _db_configured() -> bool:
    from .supabase_log import _cfg

    url, key = _cfg()
    return bool(url and key)


def _db_insert(row: dict[str, str]) -> dict[str, str]:
    from .supabase_log import _cfg

    url, key = _cfg()
    if not url or not key:
        raise GoalProjectStoreError(
            "supabase_not_configured",
            "Supabase is not configured, so the project was not stored.",
        )
    req = Request(
        f"{url}/rest/v1/{_TABLE}",
        data=json.dumps(row).encode(),
        method="POST",
        headers=_db_headers(key, prefer="return=representation"),
    )
    try:
        with urlopen(req, timeout=8) as resp:
            body = json.loads(resp.read() or b"[]")
    except HTTPError as exc:
        hint = (
            "The goal_projects table is missing. Apply the migration."
            if exc.code == 404
            else "Project was not stored in the database."
        )
        raise GoalProjectStoreError("supabase_write_failed", hint) from exc
    except OSError as exc:
        raise GoalProjectStoreError(
            "supabase_write_failed",
            "Project was not stored in the database.",
        ) from exc
    if isinstance(body, list) and body and isinstance(body[0], dict):
        return _as_row(body[0])
    if isinstance(body, dict) and body.get("id"):
        return _as_row(body)
    raise GoalProjectStoreError(
        "supabase_write_failed",
        "Project was not stored in the database.",
    )


def _db_select(params: str) -> list[dict[str, str]]:
    from .supabase_log import _cfg

    url, key = _cfg()
    if not url or not key:
        raise GoalProjectStoreError(
            "supabase_not_configured",
            "Supabase is not configured, so projects cannot be loaded.",
        )
    req = Request(
        f"{url}/rest/v1/{_TABLE}?{params}",
        method="GET",
        headers=_db_headers(key, prefer="return=representation"),
    )
    try:
        with urlopen(req, timeout=8) as resp:
            rows = json.loads(resp.read() or b"[]")
    except (HTTPError, OSError) as exc:
        raise GoalProjectStoreError(
            "supabase_read_failed",
            "Projects could not be loaded from the database.",
        ) from exc
    if not isinstance(rows, list):
        return []
    return [_as_row(row) for row in rows if isinstance(row, dict) and row.get("id")]


def _load_file() -> list[dict[str, str]]:
    path = store_path()
    if not path.is_file():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    rows = data.get("projects") if isinstance(data, dict) else data
    if not isinstance(rows, list):
        return []
    return [_as_row(row) for row in rows if isinstance(row, dict) and row.get("id")]


def load_projects() -> list[dict[str, str]]:
    if _use_file():
        return _load_file()
    return _db_select("select=*&order=created_at.desc")


def get_project(project_id: str) -> dict[str, str] | None:
    wanted = (project_id or "").strip()
    if not wanted:
        return None
    if _use_file():
        for row in _load_file():
            if row["id"] == wanted:
                return row
        return None
    from .supabase_log import _q

    rows = _db_select(f"id=eq.{_q(wanted)}&select=*")
    return rows[0] if rows else None


def create_project(body: dict[str, Any]) -> dict[str, str]:
    missing = validate_brief(body)
    if missing:
        raise ValueError(",".join(missing))
    row = _new_row(body)
    if _use_file():
        rows = _load_file()
        rows.append(row)
        _atomic_write(store_path(), {"projects": rows})
        return row
    return _db_insert(row)


def format_brief(project: dict[str, str]) -> str:
    lines = [
        f"Title: {project.get('title') or ''}",
        f"Description: {project.get('description') or ''}",
        f"Main audience: {project.get('audience') or ''}",
    ]
    extras = (
        ("Problem", "problem"),
        ("Users", "users"),
        ("Outcomes", "outcomes"),
        ("Constraints", "constraints"),
        ("Out of scope", "out_of_scope"),
    )
    for label, key in extras:
        value = (project.get(key) or "").strip()
        if value:
            lines.append(f"{label}: {value}")
    return "\n".join(lines)
