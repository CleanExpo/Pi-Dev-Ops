"""Operator-created project briefs for Goal → Linear. Not GitHub repos."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

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


def store_path() -> Path:
    override = (os.environ.get("GOAL_PROJECTS_PATH") or "").strip()
    if override:
        return Path(override)
    logs = (os.environ.get("TAO_LOGS") or "").strip()
    if logs:
        return Path(logs) / "goal-projects.json"
    return Path(__file__).resolve().parents[2] / ".harness" / "goal-projects.json"


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    os.replace(tmp, path)


def load_projects() -> list[dict[str, str]]:
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
    return [row for row in rows if isinstance(row, dict) and row.get("id")]


def get_project(project_id: str) -> dict[str, str] | None:
    wanted = (project_id or "").strip()
    if not wanted:
        return None
    for row in load_projects():
        if str(row.get("id")) == wanted:
            return {key: str(row.get(key) or "") for key in ("id", *_FIELDS, "created_at")}
    return None


def validate_brief(body: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for key in ("title", "description", "audience"):
        if len(str(body.get(key) or "").strip()) < _MIN:
            missing.append(key)
    return missing


def create_project(body: dict[str, Any]) -> dict[str, str]:
    missing = validate_brief(body)
    if missing:
        raise ValueError(",".join(missing))
    row = {key: str(body.get(key) or "").strip() for key in _FIELDS}
    row["id"] = str(uuid.uuid4())
    row["created_at"] = datetime.now(timezone.utc).isoformat()
    rows = load_projects()
    rows.append(row)
    _atomic_write(store_path(), {"projects": rows})
    return row


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
