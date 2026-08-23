"""Shared primitives for Senior Harness contract compilation and validation."""
from __future__ import annotations

import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
REPO_ROOT = Path(__file__).resolve().parents[3]


class ContractError(ValueError):
    """Raised when a Senior Harness contract fails closed."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(canonical_json(value)).hexdigest()


def skill_folder_digest() -> str:
    skill_root = Path(__file__).resolve().parents[1]
    hasher = hashlib.sha256()
    for path in sorted(skill_root.rglob("*")):
        if not path.is_file() or "__pycache__" in path.parts or path.suffix == ".pyc":
            continue
        hasher.update(path.relative_to(skill_root).as_posix().encode("utf-8"))
        hasher.update(b"\0")
        hasher.update(path.read_bytes())
        hasher.update(b"\0")
    return "sha256:" + hasher.hexdigest()


def attempt_fingerprint(attempt: dict[str, Any]) -> str:
    """Fingerprint the pathway, excluding results that arrive after execution."""
    sources = attempt.get("source_set")
    if isinstance(sources, list) and all(isinstance(source, str) for source in sources):
        sources = sorted(set(source.strip() for source in sources))
    pathway = {
        "route_id": attempt.get("route_id"),
        "input_sha256": attempt.get("input_sha256"),
        "problem_id": attempt.get("problem_id"),
        "method": attempt.get("method"),
        "tool_path": attempt.get("tool_path"),
        "source_set": sources,
        "model_class": attempt.get("model_class"),
    }
    return digest(pathway)


def bind_attempt(contract: dict[str, Any], attempt: dict[str, Any]) -> dict[str, Any]:
    """Bind an attempt to the frozen task and a stable harness route handle."""
    bound = dict(attempt)
    input_sha = digest(
        {
            "task_id": contract.get("task_id"),
            "literal_request": contract.get("literal_request"),
            "problem_id": attempt.get("problem_id"),
        }
    )
    bound["input_sha256"] = input_sha
    bound["route_id"] = digest(
        {
            "input_sha256": input_sha,
            "model_class": attempt.get("model_class"),
            "tool_path": attempt.get("tool_path"),
        }
    )
    bound["fingerprint"] = attempt_fingerprint(bound)
    return bound


def parse_timestamp(value: Any, label: str, errors: list[str]) -> datetime | None:
    if not isinstance(value, str) or not value:
        errors.append(f"{label} must be a timezone-aware ISO timestamp")
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        errors.append(f"{label} must be a timezone-aware ISO timestamp")
        return None
    if parsed.tzinfo is None:
        errors.append(f"{label} must include a timezone")
        return None
    return parsed


def require_mapping(value: Any, label: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    return value


def require_nonempty(value: Any, label: str, errors: list[str]) -> None:
    if value is None or value == "" or value == [] or value == {}:
        errors.append(f"{label} must be non-empty")


def intake(task: str, horizon_required: bool) -> dict[str, Any]:
    if not task.strip():
        raise ContractError(["task must be non-empty"])
    return {
        "schema_version": SCHEMA_VERSION,
        "stage": "intake",
        "task_id": digest({"task": task})[7:23],
        "literal_request": task,
        "authorized_scope": [task],
        "inferred_outcomes": [],
        "classification": {
            "horizon_required": horizon_required,
            "rationale": "operator-selected" if horizon_required else "routine-default",
        },
        "limits": {
            "max_parallel_workers": 4,
            "max_nodes": 40,
            "max_branch_width": 4,
            "max_same_path_attempts": 2,
            "max_minutes_without_new_authoritative_evidence": 5,
            "max_cost_usd": None,
        },
        "required_skills": ["model-router", "unlazy"],
        "discovery_runs": [],
        "forecasts": [],
        "move_graph": [],
        "attempts": [],
        "uncertainty_cases": [],
    }
