"""Atomic packet store under .harness/idea-pipeline/."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .constants import STORE_DIRNAME

_SAFE_ID = re.compile(r"[^a-zA-Z0-9-]")


def default_store_dir(repo_root: Path) -> Path:
    return repo_root / ".harness" / STORE_DIRNAME


def safe_idea_id(idea_id: str) -> str:
    cleaned = _SAFE_ID.sub("", idea_id or "")
    if not cleaned.startswith("idea-") or len(cleaned) < 8:
        raise ValueError("invalid idea id")
    return cleaned


def _path(store_dir: Path, idea_id: str) -> Path:
    return store_dir / f"{safe_idea_id(idea_id)}.json"


def write_packet(store_dir: Path, packet: dict[str, Any]) -> Path:
    store_dir.mkdir(parents=True, exist_ok=True)
    path = _path(store_dir, str(packet["idea_id"]))
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(packet, indent=2), encoding="utf-8")
    os.replace(tmp, path)
    return path


def read_packet(store_dir: Path, idea_id: str) -> dict[str, Any] | None:
    path = _path(store_dir, idea_id)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else None


def list_packets(store_dir: Path) -> list[dict[str, Any]]:
    if not store_dir.is_dir():
        return []
    packets: list[dict[str, Any]] = []
    for path in sorted(store_dir.glob("idea-*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, dict) and data.get("idea_id"):
            packets.append(data)
    packets.sort(key=lambda row: str(row.get("created_at") or ""), reverse=True)
    return packets
