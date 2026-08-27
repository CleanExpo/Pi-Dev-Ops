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
_SETTINGS = "settings"
_PREFIX = "goal_project:"


class GoalProjectStoreError(Exception):
    def __init__(self, code: str, hint: str) -> None:
        super().__init__(hint)
        self.code = code
        self.hint = hint


class _TableMissing(Exception):
    pass


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


def _db_configured() -> bool:
    from .supabase_log import _cfg

    url, key = _cfg()
    return bool(url and key)


def _creds() -> tuple[str, str]:
    from .supabase_log import _cfg

    url, key = _cfg()
    if not url or not key:
        raise GoalProjectStoreError(
            "supabase_not_configured",
            "Supabase is not configured, so the project was not stored.",
        )
    return url, key


def _request(method: str, path: str, data: dict[str, Any] | None = None) -> Any:
    url, key = _creds()
    req = Request(
        f"{url}/rest/v1/{path}",
        data=json.dumps(data).encode() if data is not None else None,
        method=method,
        headers={
            "Content-Type": "application/json",
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Prefer": "return=representation",
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(req, timeout=8) as resp:
            return json.loads(resp.read() or b"[]")
    except HTTPError as exc:
        if exc.code == 404:
            raise _TableMissing from exc
        raise GoalProjectStoreError(
            "supabase_write_failed" if method != "GET" else "supabase_read_failed",
            "Project was not stored in the database."
            if method != "GET"
            else "Projects could not be loaded from the database.",
        ) from exc
    except OSError as exc:
        raise GoalProjectStoreError(
            "supabase_write_failed" if method != "GET" else "supabase_read_failed",
            "Project was not stored in the database."
            if method != "GET"
            else "Projects could not be loaded from the database.",
        ) from exc


def _from_dedicated(body: Any) -> list[dict[str, str]]:
    rows = body if isinstance(body, list) else [body] if isinstance(body, dict) else []
    return [_as_row(row) for row in rows if isinstance(row, dict) and row.get("id")]


def _from_setting(item: dict[str, Any]) -> dict[str, str] | None:
    try:
        parsed = json.loads(str(item.get("value") or ""))
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict) and parsed.get("id"):
        return _as_row(parsed)
    return None


def _settings_list() -> list[dict[str, str]]:
    from .supabase_log import _q

    body = _request("GET", f"{_SETTINGS}?key=like.{_q(_PREFIX)}*&select=key,value")
    if not isinstance(body, list):
        return []
    rows = [_from_setting(item) for item in body if isinstance(item, dict)]
    return [row for row in rows if row]


def _settings_get(project_id: str) -> dict[str, str] | None:
    from .supabase_log import _q

    body = _request("GET", f"{_SETTINGS}?key=eq.{_q(_PREFIX + project_id)}&select=key,value")
    if not isinstance(body, list):
        return None
    for item in body:
        if isinstance(item, dict):
            row = _from_setting(item)
            if row:
                return row
    return None


def _settings_insert(row: dict[str, str]) -> dict[str, str]:
    _request(
        "POST",
        _SETTINGS,
        {"key": f"{_PREFIX}{row['id']}", "value": json.dumps(row), "updated_at": row["created_at"]},
    )
    return row


def _db_insert(row: dict[str, str]) -> dict[str, str]:
    try:
        saved = _from_dedicated(_request("POST", _TABLE, row))
        if saved:
            return saved[0]
    except _TableMissing:
        pass
    try:
        return _settings_insert(row)
    except _TableMissing as exc:
        raise GoalProjectStoreError(
            "supabase_write_failed",
            "Project was not stored in the database.",
        ) from exc


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
    try:
        rows = _from_dedicated(_request("GET", f"{_TABLE}?select=*&order=created_at.desc"))
    except _TableMissing:
        return _settings_list()
    seen = {row["id"] for row in rows}
    rows.extend(extra for extra in _settings_list() if extra["id"] not in seen)
    return rows


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

    try:
        rows = _from_dedicated(_request("GET", f"{_TABLE}?id=eq.{_q(wanted)}&select=*"))
        if rows:
            return rows[0]
    except _TableMissing:
        pass
    return _settings_get(wanted)


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
