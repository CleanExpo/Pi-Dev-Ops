"""Atomic artifact writes for spec pipeline runs."""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
PIPELINES_ROOT = REPO_ROOT / ".harness" / "spec-pipelines"


def new_pipeline_id() -> str:
    return f"spec-{uuid.uuid4().hex[:12]}"


def pipeline_dir(pipeline_id: str) -> Path:
    return PIPELINES_ROOT / pipeline_id


def ensure_dir(pipeline_id: str) -> Path:
    d = pipeline_dir(pipeline_id)
    d.mkdir(parents=True, exist_ok=True)
    return d


def write_text(pipeline_id: str, name: str, content: str) -> Path:
    path = ensure_dir(pipeline_id) / name
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8")
    os.replace(tmp, path)
    return path


def write_json(pipeline_id: str, name: str, data: Any) -> Path:
    return write_text(pipeline_id, name, json.dumps(data, indent=2, sort_keys=True) + "\n")


def append_jsonl(pipeline_id: str, name: str, row: dict[str, Any]) -> None:
    path = ensure_dir(pipeline_id) / name
    line = json.dumps({**row, "ts": datetime.now(timezone.utc).isoformat()}) + "\n"
    with path.open("a", encoding="utf-8") as f:
        f.write(line)


def read_json(pipeline_id: str, name: str) -> dict[str, Any] | None:
    path = pipeline_dir(pipeline_id) / name
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def list_pipelines(limit: int = 20) -> list[dict[str, Any]]:
    if not PIPELINES_ROOT.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for d in sorted(PIPELINES_ROOT.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True):
        if not d.is_dir():
            continue
        meta = read_json(d.name, "meta.json") or {}
        rows.append({
            "pipeline_id": d.name,
            "status": meta.get("status", "unknown"),
            "proposal": (meta.get("proposal") or "")[:120],
            "updated_at": meta.get("updated_at"),
        })
        if len(rows) >= limit:
            break
    return rows
