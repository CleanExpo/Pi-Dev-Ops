"""Durable JSON store for the synthetic Nexus One pilot.

Atomic write-then-replace, matching ``app.server.persistence``. IDs are
sanitised before any path use. SYNTHETIC: local fixture root only; never
Supabase or production session storage.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

from .types import MethodAttempt, Receipt, TaskContract

_SAFE = re.compile(r"[^a-zA-Z0-9._-]")


def _safe_id(value: str) -> str:
    cleaned = _SAFE.sub("", value)
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"unsafe id: {value!r}")
    return cleaned


def atomic_write(path: Path, payload: dict[str, Any]) -> Path:
    """Write JSON via a unique tmp file then ``os.replace``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return path


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


class SyntheticStore:
    """On-disk maps for contracts, attempts, checkpoints, and receipts."""

    def __init__(self, root: Path) -> None:
        self.root = Path(root)
        for name in ("tasks", "fingerprints", "attempts", "checkpoints", "receipts"):
            (self.root / name).mkdir(parents=True, exist_ok=True)

    def _task_path(self, task_id: str) -> Path:
        return self.root / "tasks" / f"{_safe_id(task_id)}.json"

    def put_task(self, task: TaskContract) -> None:
        atomic_write(self._task_path(task.task_id), task.to_dict())
        fp_path = self.root / "fingerprints" / f"{_safe_id(task.input_fingerprint)}.json"
        atomic_write(fp_path, {"task_id": task.task_id})

    def get_task(self, task_id: str) -> TaskContract | None:
        raw = _read_json(self._task_path(task_id))
        return None if raw is None else TaskContract(**raw)

    def get_by_fingerprint(self, fingerprint: str) -> TaskContract | None:
        raw = _read_json(self.root / "fingerprints" / f"{_safe_id(fingerprint)}.json")
        if raw is None:
            return None
        return self.get_task(str(raw["task_id"]))

    def record_attempt(self, task_id: str, attempt: MethodAttempt) -> None:
        path = self.root / "attempts" / f"{_safe_id(task_id)}.json"
        existing = _read_json(path) or {"attempts": []}
        rows = list(existing.get("attempts") or [])
        rows.append(attempt.to_dict())
        atomic_write(path, {"attempts": rows})

    def list_attempts(self, task_id: str) -> list[MethodAttempt]:
        raw = _read_json(self.root / "attempts" / f"{_safe_id(task_id)}.json")
        if raw is None:
            return []
        return [MethodAttempt(**row) for row in raw.get("attempts") or []]

    def failed_fingerprints(self, task_id: str) -> set[str]:
        return {
            item.fingerprint
            for item in self.list_attempts(task_id)
            if item.outcome == "failed"
        }

    def write_checkpoint(self, task_id: str, payload: dict[str, Any]) -> Path:
        return atomic_write(
            self.root / "checkpoints" / f"{_safe_id(task_id)}.json", payload
        )

    def load_checkpoint(self, task_id: str) -> dict[str, Any] | None:
        return _read_json(self.root / "checkpoints" / f"{_safe_id(task_id)}.json")

    def write_receipt(self, receipt: Receipt) -> Path:
        path = self.root / "receipts" / f"{_safe_id(receipt.receipt_id)}.json"
        return atomic_write(path, receipt.to_dict())

    def load_receipt(self, receipt_id: str) -> dict[str, Any] | None:
        return _read_json(self.root / "receipts" / f"{_safe_id(receipt_id)}.json")
