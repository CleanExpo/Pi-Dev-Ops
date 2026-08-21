#!/usr/bin/env python3
"""Deterministic contract gate for the portable Senior Harness entry skill."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict, deque
from datetime import datetime
from pathlib import Path
from typing import Any


SCHEMA_VERSION = "1.0"
MOVE_FIELDS = {
    "move_id",
    "parents",
    "plane",
    "kind",
    "state_delta",
    "owner",
    "prerequisites",
    "evidence_ids",
    "confidence",
    "counter_case",
    "value",
    "cost",
    "reversibility",
    "trigger",
    "expiry",
    "status",
    "authority_required",
    "authorization_status",
}
ALLOWED_PLANES = {"horizon", "delivery", "verification", "learning"}
ALLOWED_AUTHORIZATION = {"proposal", "approved", "not-required"}
ALLOWED_STATUSES = {"proposed", "admitted", "ready", "active", "blocked", "passed", "failed"}
PLANE_KINDS = {
    "horizon": {"observe", "discover", "challenge", "model", "forecast", "propose"},
    "delivery": {
        "admit",
        "route",
        "decompose",
        "guard",
        "escalate",
        "specify",
        "execute",
        "deploy",
        "migrate",
        "publish",
        "purchase",
        "delete",
        "write-files",
        "push",
        "send-message",
        "run-command",
        "edit",
        "commit",
        "merge",
        "provision",
        "configure",
    },
    "verification": {"test", "verify", "arbitrate"},
    "learning": {"promote", "replay", "harden", "revalidate"},
}
MUTATING_KINDS = {
    "execute",
    "deploy",
    "migrate",
    "publish",
    "purchase",
    "delete",
    "write-files",
    "push",
    "send-message",
    "run-command",
    "edit",
    "commit",
    "merge",
    "provision",
    "configure",
}
REQUIRED_SKILLS = {"model-router", "unlazy"}
MAX_NODES = 500
MAX_BRANCH_WIDTH = 20
MAX_PARALLEL_WORKERS = 100
FAILURE_STATUSES = {"failed", "runner-error", "blocked", "timed-out"}
ATTEMPT_STATUSES = {"planned", "active", "passed", "failed", "runner-error", "blocked", "timed-out", "cancelled"}
REPO_ROOT = Path(__file__).resolve().parents[3]


class ContractError(ValueError):
    """Raised when a Senior Harness contract fails closed."""

    def __init__(self, errors: list[str]):
        super().__init__("; ".join(errors))
        self.errors = errors


def _canonical_json(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def digest(value: Any) -> str:
    return "sha256:" + hashlib.sha256(_canonical_json(value)).hexdigest()


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
    route_id = digest(
        {
            "input_sha256": input_sha,
            "model_class": attempt.get("model_class"),
            "tool_path": attempt.get("tool_path"),
        }
    )
    bound["input_sha256"] = input_sha
    bound["route_id"] = route_id
    bound["fingerprint"] = attempt_fingerprint(bound)
    return bound


def _parse_timestamp(value: Any, label: str, errors: list[str]) -> datetime | None:
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


def _require_mapping(value: Any, label: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label} must be an object")
        return {}
    return value


def _require_nonempty(value: Any, label: str, errors: list[str]) -> None:
    if value is None or value == "" or value == [] or value == {}:
        errors.append(f"{label} must be non-empty")


def _validate_authority(contract: dict[str, Any], moves: list[dict[str, Any]], errors: list[str]) -> None:
    literal_request = contract.get("literal_request")
    _require_nonempty(literal_request, "literal_request", errors)
    scope = contract.get("authorized_scope")
    if scope != [literal_request]:
        errors.append("authorized_scope must contain only the literal_request in schema v1")

    raw_grants = contract.get("authority_grants")
    if raw_grants != []:
        errors.append("schema v1 cannot authenticate authority grants; authority_grants must remain empty")

    outcomes = contract.get("inferred_outcomes", [])
    if not isinstance(outcomes, list):
        errors.append("inferred_outcomes must be a list")
    else:
        for index, outcome in enumerate(outcomes):
            item = _require_mapping(outcome, f"inferred_outcomes[{index}]", errors)
            for field in ("statement", "provenance", "confidence", "authorization_status"):
                _require_nonempty(item.get(field), f"inferred_outcomes[{index}].{field}", errors)
            confidence = item.get("confidence")
            if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
                errors.append(f"inferred_outcomes[{index}].confidence must be between 0 and 1")
            if item.get("authorization_status") != "proposal":
                errors.append(f"inferred_outcomes[{index}] must remain a proposal")

    for move in moves:
        auth = move.get("authorization_status")
        if auth not in ALLOWED_AUTHORIZATION:
            errors.append(f"move {move.get('move_id')} has invalid authorization_status")
        if move.get("authority_required") == "none" and auth != "not-required":
            errors.append(f"move {move.get('move_id')} requires authorization_status=not-required")
        if move.get("kind") in MUTATING_KINDS:
            if move.get("authority_required") == "none":
                errors.append(f"mutating move {move.get('move_id')} must name its authority requirement")
            if auth != "proposal":
                errors.append(
                    f"move {move.get('move_id')} must remain a proposal until an external trusted runtime authenticates authority"
                )
            if move.get("authority_source_id") is not None:
                errors.append(f"move {move.get('move_id')} cannot claim an authority source in schema v1")


def _validate_moves(contract: dict[str, Any], errors: list[str]) -> tuple[list[dict[str, Any]], int]:
    raw_moves = contract.get("move_graph")
    if not isinstance(raw_moves, list) or not raw_moves:
        errors.append("move_graph must be a non-empty list")
        return [], 0

    moves: list[dict[str, Any]] = []
    ids: list[str] = []
    state_deltas: list[str] = []
    for index, raw in enumerate(raw_moves):
        move = _require_mapping(raw, f"move_graph[{index}]", errors)
        moves.append(move)
        missing = sorted(MOVE_FIELDS - set(move))
        if missing:
            errors.append(f"move_graph[{index}] missing fields: {', '.join(missing)}")
        move_id = move.get("move_id")
        _require_nonempty(move_id, f"move_graph[{index}].move_id", errors)
        if isinstance(move_id, str):
            ids.append(move_id)
        if move.get("plane") not in ALLOWED_PLANES:
            errors.append(f"move {move_id} has invalid plane")
        elif move.get("kind") not in PLANE_KINDS[move["plane"]]:
            errors.append(f"move {move_id} kind {move.get('kind')} is not allowed on plane {move['plane']}")
        if move.get("status") not in ALLOWED_STATUSES:
            errors.append(f"move {move_id} has invalid status")
        if not isinstance(move.get("parents"), list):
            errors.append(f"move {move_id}.parents must be a list")
        if not isinstance(move.get("prerequisites"), list):
            errors.append(f"move {move_id}.prerequisites must be a list")
        elif any(not isinstance(item, str) for item in move["prerequisites"]):
            errors.append(f"move {move_id}.prerequisites must contain move ids")
        if not isinstance(move.get("evidence_ids"), list):
            errors.append(f"move {move_id}.evidence_ids must be a list")
        elif not move["evidence_ids"] or any(not isinstance(item, str) or not item for item in move["evidence_ids"]):
            errors.append(f"move {move_id}.evidence_ids must contain at least one evidence id")
        for field in ("kind", "state_delta", "owner", "counter_case", "value", "cost", "reversibility", "trigger", "expiry", "authority_required"):
            _require_nonempty(move.get(field), f"move {move_id}.{field}", errors)
        confidence = move.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            errors.append(f"move {move_id}.confidence must be between 0 and 1")
        if isinstance(move.get("state_delta"), str):
            state_deltas.append(" ".join(move["state_delta"].lower().split()))
    duplicate_ids = sorted(item for item, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate move ids: {', '.join(duplicate_ids)}")
    duplicate_deltas = sorted(item for item, count in Counter(state_deltas).items() if count > 1)
    if duplicate_deltas:
        errors.append("duplicate state_delta values are not structurally distinct moves")

    by_id = {move.get("move_id"): move for move in moves if isinstance(move.get("move_id"), str)}
    children: dict[str, list[str]] = defaultdict(list)
    indegree = {move_id: 0 for move_id in by_id}
    for move_id, move in by_id.items():
        prerequisites = move.get("prerequisites") if isinstance(move.get("prerequisites"), list) else []
        for prerequisite in prerequisites:
            if isinstance(prerequisite, str) and prerequisite not in by_id:
                errors.append(f"move {move_id} references missing prerequisite {prerequisite}")
        parents = move.get("parents") if isinstance(move.get("parents"), list) else []
        for parent in parents:
            if not isinstance(parent, str):
                errors.append(f"move {move_id} parent ids must be strings")
                continue
            if parent not in by_id:
                errors.append(f"move {move_id} references missing parent {parent}")
                continue
            children[parent].append(move_id)
            indegree[move_id] += 1
            if by_id[parent].get("plane") == "horizon" and move.get("plane") == "delivery" and move.get("kind") != "admit":
                errors.append(f"move {move_id} bypasses admission from Horizon to delivery")

    limits = _require_mapping(contract.get("limits"), "limits", errors)
    max_nodes = limits.get("max_nodes")
    max_width = limits.get("max_branch_width")
    max_workers = limits.get("max_parallel_workers")
    max_cost = limits.get("max_cost_usd")
    if isinstance(max_nodes, bool) or not isinstance(max_nodes, int) or not 1 <= max_nodes <= MAX_NODES:
        errors.append(f"limits.max_nodes must be between 1 and {MAX_NODES}")
    elif len(moves) > max_nodes:
        errors.append(f"move_graph exceeds max_nodes={max_nodes}")
    if isinstance(max_width, bool) or not isinstance(max_width, int) or not 1 <= max_width <= MAX_BRANCH_WIDTH:
        errors.append(f"limits.max_branch_width must be between 1 and {MAX_BRANCH_WIDTH}")
    else:
        for parent, child_ids in children.items():
            if len(child_ids) > max_width:
                errors.append(f"move {parent} exceeds max_branch_width={max_width}")
    if isinstance(max_workers, bool) or not isinstance(max_workers, int) or not 1 <= max_workers <= MAX_PARALLEL_WORKERS:
        errors.append(f"limits.max_parallel_workers must be between 1 and {MAX_PARALLEL_WORKERS}")
    if isinstance(max_cost, bool) or not isinstance(max_cost, (int, float)) or max_cost < 0:
        errors.append("limits.max_cost_usd must be a non-negative number for a delivery contract")

    queue = deque(move_id for move_id, degree in indegree.items() if degree == 0)
    distances = {move_id: 1 for move_id in queue}
    ancestors: dict[str, set[str]] = {move_id: set() for move_id in by_id}
    visited = 0
    while queue:
        move_id = queue.popleft()
        visited += 1
        for child in children[move_id]:
            distances[child] = max(distances.get(child, 1), distances[move_id] + 1)
            ancestors[child].update(ancestors[move_id] | {move_id})
            indegree[child] -= 1
            if indegree[child] == 0:
                queue.append(child)
    if visited != len(by_id):
        errors.append("move_graph contains a cycle")
    admission_ids = {move_id for move_id, move in by_id.items() if move.get("plane") == "delivery" and move.get("kind") == "admit"}
    for move_id, move in by_id.items():
        if move.get("plane") == "delivery" and move.get("kind") != "admit":
            if not (ancestors[move_id] & admission_ids):
                errors.append(f"delivery move {move_id} has no admitted ancestor")
    longest_path = max(distances.values(), default=0)

    classification = _require_mapping(contract.get("classification"), "classification", errors)
    horizon_required = classification.get("horizon_required")
    if not isinstance(horizon_required, bool):
        errors.append("classification.horizon_required must be a boolean")
    elif horizon_required and not 15 <= longest_path <= 20:
        errors.append(f"horizon path must contain 15-20 distinct state-bearing moves; found {longest_path}")
    if horizon_required:
        roots = [move for move_id, move in by_id.items() if not move.get("parents")]
        if not roots or any(move.get("plane") != "horizon" for move in roots):
            errors.append("every horizon-bearing graph root must be on the Horizon plane")
    return moves, longest_path


def _validate_discovery_and_forecasts(
    contract: dict[str, Any], moves: list[dict[str, Any]], errors: list[str]
) -> None:
    runs = contract.get("discovery_runs")
    raw_classification = contract.get("classification")
    horizon_required = raw_classification.get("horizon_required") if isinstance(raw_classification, dict) else None
    if not isinstance(runs, list):
        errors.append("discovery_runs must be a list")
        runs = []
    if horizon_required and not runs:
        errors.append("horizon-bearing work requires at least one bounded discovery run")
    discovery_cost = 0.0
    for index, raw in enumerate(runs):
        run = _require_mapping(raw, f"discovery_runs[{index}]", errors)
        for field in ("question", "source_allowlist", "privacy_allowlist", "max_minutes", "max_cost_usd", "retention_days", "value_of_information_threshold", "stop_conditions"):
            _require_nonempty(run.get(field), f"discovery_runs[{index}].{field}", errors)
        for field in ("source_allowlist", "privacy_allowlist", "stop_conditions"):
            if not isinstance(run.get(field), list):
                errors.append(f"discovery_runs[{index}].{field} must be a list")
            elif not run[field] or any(not isinstance(item, str) or not item for item in run[field]):
                errors.append(f"discovery_runs[{index}].{field} must contain non-empty strings")
        max_minutes = run.get("max_minutes")
        if isinstance(max_minutes, bool) or not isinstance(max_minutes, (int, float)) or max_minutes <= 0:
            errors.append(f"discovery_runs[{index}].max_minutes must be positive")
        max_cost = run.get("max_cost_usd")
        if isinstance(max_cost, bool) or not isinstance(max_cost, (int, float)) or max_cost < 0:
            errors.append(f"discovery_runs[{index}].max_cost_usd must be non-negative")
        else:
            discovery_cost += float(max_cost)
        retention = run.get("retention_days")
        if isinstance(retention, bool) or not isinstance(retention, int) or retention < 0:
            errors.append(f"discovery_runs[{index}].retention_days must be a non-negative integer")
        threshold = run.get("value_of_information_threshold")
        if isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
            errors.append(f"discovery_runs[{index}].value_of_information_threshold must be between 0 and 1")
    raw_limits = contract.get("limits")
    total_cost = raw_limits.get("max_cost_usd") if isinstance(raw_limits, dict) else None
    if isinstance(total_cost, (int, float)) and not isinstance(total_cost, bool) and discovery_cost > total_cost:
        errors.append("discovery run budgets exceed limits.max_cost_usd")

    forecasts = contract.get("forecasts")
    if not isinstance(forecasts, list):
        errors.append("forecasts must be a list")
        forecasts = []
    if any(move.get("kind") == "forecast" for move in moves) and not forecasts:
        errors.append("forecast moves require a ForecastContract")
    for index, raw in enumerate(forecasts):
        forecast = _require_mapping(raw, f"forecasts[{index}]", errors)
        for field in ("forecast_id", "mutual_exclusivity_rationale", "resolution_criterion", "resolution_source", "resolution_date", "scoring_rule_version", "freeze_time"):
            _require_nonempty(forecast.get(field), f"forecasts[{index}].{field}", errors)
        outcomes = forecast.get("outcomes")
        if not isinstance(outcomes, list) or len(outcomes) < 2:
            errors.append(f"forecasts[{index}].outcomes must contain at least two outcomes")
            continue
        names: list[str] = []
        probabilities: list[float] = []
        for outcome_index, raw_outcome in enumerate(outcomes):
            outcome = _require_mapping(raw_outcome, f"forecasts[{index}].outcomes[{outcome_index}]", errors)
            _require_nonempty(outcome.get("name"), f"forecasts[{index}].outcomes[{outcome_index}].name", errors)
            probability = outcome.get("probability")
            if isinstance(probability, bool) or not isinstance(probability, (int, float)) or not 0 <= probability <= 1:
                errors.append(f"forecasts[{index}].outcomes[{outcome_index}].probability must be between 0 and 1")
            else:
                probabilities.append(float(probability))
            if isinstance(outcome.get("name"), str):
                names.append(outcome["name"])
        if len(names) != len(set(names)):
            errors.append(f"forecasts[{index}] outcome names must be unique")
        if len(probabilities) == len(outcomes) and abs(sum(probabilities) - 1.0) > 1e-9:
            errors.append(f"forecasts[{index}] probabilities must sum to 1")


def _validate_routing_and_verification(contract: dict[str, Any], errors: list[str]) -> None:
    skills = contract.get("required_skills")
    if (
        not isinstance(skills, list)
        or any(not isinstance(skill, str) for skill in skills)
        or not REQUIRED_SKILLS.issubset(set(skills))
    ):
        errors.append("required_skills must include model-router and unlazy")

    verification = _require_mapping(contract.get("verification"), "verification", errors)
    builder = verification.get("builder_id")
    verifier = verification.get("verifier_id")
    arbiter = verification.get("arbiter_id")
    for field, value in (("builder_id", builder), ("verifier_id", verifier), ("arbiter_id", arbiter)):
        _require_nonempty(value, f"verification.{field}", errors)
    if builder and verifier and builder == verifier:
        errors.append("verifier_id must be independent from builder_id")
    if arbiter and arbiter in {builder, verifier}:
        errors.append("arbiter_id must be independent from builder_id and verifier_id")
    receipt_types = verification.get("required_receipt_types")
    if (
        not isinstance(receipt_types, list)
        or not receipt_types
        or any(not isinstance(item, str) or not item for item in receipt_types)
    ):
        errors.append("verification.required_receipt_types must be a non-empty list of strings")
    receipts = verification.get("receipts")
    if receipts != []:
        errors.append("schema v1 cannot authenticate receipts; verification.receipts must remain empty")


def _validate_repository(contract: dict[str, Any], errors: list[str]) -> None:
    repository = _require_mapping(contract.get("repository"), "repository", errors)
    base_sha = repository.get("base_sha")
    candidate_sha = repository.get("candidate_sha")
    if not isinstance(base_sha, str) or len(base_sha) != 40 or any(char not in "0123456789abcdef" for char in base_sha):
        errors.append("repository.base_sha must be a 40-character lowercase Git SHA")
    if candidate_sha is not None and (
        not isinstance(candidate_sha, str)
        or len(candidate_sha) != 40
        or any(char not in "0123456789abcdef" for char in candidate_sha)
    ):
        errors.append("repository.candidate_sha must be null or a 40-character lowercase Git SHA")
    worktree = repository.get("worktree")
    if not isinstance(worktree, str) or not Path(worktree).is_absolute():
        errors.append("repository.worktree must be an absolute path")
        return
    worktree_path = Path(worktree)
    if not worktree_path.is_dir():
        errors.append("repository.worktree must exist and be a directory")
        return
    try:
        top_level = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=worktree_path,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        errors.append(f"repository.worktree could not be checked: {exc}")
        return
    if top_level.returncode != 0:
        errors.append("repository.worktree must be a Git checkout")
        return
    try:
        declared_root = worktree_path.resolve(strict=True)
        actual_root = Path(top_level.stdout.strip()).resolve(strict=True)
    except OSError as exc:
        errors.append(f"repository.worktree could not be resolved: {exc}")
        return
    if declared_root != actual_root:
        errors.append("repository.worktree must name the Git checkout root")
    for label, sha in (("base_sha", base_sha), ("candidate_sha", candidate_sha)):
        if not isinstance(sha, str) or len(sha) != 40:
            continue
        try:
            result = subprocess.run(
                ["git", "cat-file", "-e", f"{sha}^{{commit}}"],
                cwd=actual_root,
                text=True,
                capture_output=True,
                check=False,
            )
        except OSError as exc:
            errors.append(f"repository.{label} could not be checked: {exc}")
            continue
        if result.returncode != 0:
            errors.append(f"repository.{label} does not resolve to a commit in repository.worktree")
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=actual_root,
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError as exc:
        errors.append(f"repository HEAD could not be checked: {exc}")
        return
    if head.returncode != 0:
        errors.append("repository.worktree HEAD could not be resolved")
        return
    head_sha = head.stdout.strip()
    if isinstance(candidate_sha, str) and len(candidate_sha) == 40 and candidate_sha != head_sha:
        errors.append("repository.candidate_sha must equal repository.worktree HEAD")
    ancestry_tip = candidate_sha if isinstance(candidate_sha, str) and len(candidate_sha) == 40 else head_sha
    if isinstance(base_sha, str) and len(base_sha) == 40:
        ancestry_env = os.environ.copy()
        ancestry_env["GIT_NO_REPLACE_OBJECTS"] = "1"
        ancestry_env["GIT_GRAFT_FILE"] = os.devnull
        ancestry = subprocess.run(
            ["git", "merge-base", "--is-ancestor", base_sha, ancestry_tip],
            cwd=actual_root,
            text=True,
            capture_output=True,
            check=False,
            env=ancestry_env,
        )
        if ancestry.returncode != 0:
            errors.append("repository.base_sha must be an ancestor of the checked candidate or worktree HEAD")


def _validate_attempts(contract: dict[str, Any], errors: list[str]) -> None:
    limits = _require_mapping(contract.get("limits"), "limits", errors)
    max_attempts = limits.get("max_same_path_attempts")
    max_minutes = limits.get("max_minutes_without_new_authoritative_evidence")
    if max_attempts != 2:
        errors.append("limits.max_same_path_attempts must be 2")
    if isinstance(max_minutes, bool) or not isinstance(max_minutes, (int, float)) or not 0 < max_minutes <= 5:
        errors.append("limits.max_minutes_without_new_authoritative_evidence must be between 0 and 5")
    observed_at = _parse_timestamp(contract.get("observed_at"), "observed_at", errors)

    attempts = contract.get("attempts", [])
    if not isinstance(attempts, list):
        errors.append("attempts must be a list")
        return
    seen: set[str] = set()
    failures: Counter[str] = Counter()
    stale_problems: set[str] = set()
    for index, raw in enumerate(attempts):
        attempt = _require_mapping(raw, f"attempts[{index}]", errors)
        for field in ("route_id", "input_sha256", "problem_id", "hypothesis", "method", "tool_path", "source_set", "model_class", "status", "started_at", "last_authoritative_evidence_at"):
            _require_nonempty(attempt.get(field), f"attempts[{index}].{field}", errors)
        input_sha = attempt.get("input_sha256")
        if (
            not isinstance(input_sha, str)
            or not input_sha.startswith("sha256:")
            or len(input_sha) != 71
            or any(char not in "0123456789abcdef" for char in input_sha[7:])
        ):
            errors.append(f"attempts[{index}].input_sha256 must be a canonical sha256 digest")
        if not isinstance(attempt.get("source_set"), list):
            errors.append(f"attempts[{index}].source_set must be a list")
        elif any(not isinstance(item, str) or not item for item in attempt["source_set"]):
            errors.append(f"attempts[{index}].source_set must contain non-empty strings")
        evidence_delta = attempt.get("new_authoritative_evidence_ids")
        if not isinstance(evidence_delta, list) or any(not isinstance(item, str) or not item for item in evidence_delta):
            errors.append(f"attempts[{index}].new_authoritative_evidence_ids must be a list of evidence ids")
        if attempt.get("status") not in ATTEMPT_STATUSES:
            errors.append(f"attempts[{index}].status is invalid")
        started_at = _parse_timestamp(attempt.get("started_at"), f"attempts[{index}].started_at", errors)
        last_evidence = _parse_timestamp(
            attempt.get("last_authoritative_evidence_at"),
            f"attempts[{index}].last_authoritative_evidence_at",
            errors,
        )
        if started_at and last_evidence and last_evidence < started_at:
            errors.append(f"attempts[{index}] evidence timestamp cannot predate the attempt")
        if observed_at and started_at and started_at > observed_at:
            errors.append(f"attempts[{index}].started_at cannot be later than observed_at")
        if observed_at and last_evidence and last_evidence > observed_at:
            errors.append(f"attempts[{index}].last_authoritative_evidence_at cannot be later than observed_at")
        expected_binding = bind_attempt(contract, attempt)
        if attempt.get("input_sha256") != expected_binding["input_sha256"]:
            errors.append(f"attempts[{index}].input_sha256 is not bound to the frozen task")
        if attempt.get("route_id") != expected_binding["route_id"]:
            errors.append(f"attempts[{index}].route_id is not bound to the frozen route handle")
        if (
            observed_at
            and last_evidence
            and isinstance(max_minutes, (int, float))
            and not isinstance(max_minutes, bool)
            and attempt.get("status") not in {"passed", "cancelled"}
            and (observed_at - last_evidence).total_seconds() > max_minutes * 60
            and isinstance(attempt.get("problem_id"), str)
        ):
            stale_problems.add(attempt["problem_id"])
        supplied = attempt.get("fingerprint")
        expected = attempt_fingerprint(attempt)
        if supplied != expected:
            errors.append(f"attempts[{index}].fingerprint does not match its pathway")
        if isinstance(supplied, str) and supplied in seen:
            errors.append(f"attempts[{index}] repeats an already attempted pathway")
        if isinstance(supplied, str) and supplied:
            seen.add(supplied)
        if attempt.get("status") in FAILURE_STATUSES and isinstance(attempt.get("problem_id"), str):
            failures[attempt["problem_id"]] += 1

    cases = contract.get("uncertainty_cases", [])
    if not isinstance(cases, list):
        errors.append("uncertainty_cases must be a list")
        return
    open_problems: set[str] = set()
    for index, raw in enumerate(cases):
        case = _require_mapping(raw, f"uncertainty_cases[{index}]", errors)
        for field in ("problem_id", "status", "stop_current_path", "specialist_ids", "arbiter_id", "evidence_ids", "experiment", "resolution_criterion"):
            _require_nonempty(case.get(field), f"uncertainty_cases[{index}].{field}", errors)
        specialists = case.get("specialist_ids")
        if not isinstance(specialists, list) or any(not isinstance(item, str) for item in specialists):
            errors.append(f"uncertainty_cases[{index}].specialist_ids must be a list of strings")
            continue
        unique_specialists = set(specialists)
        if len(unique_specialists) < 2:
            errors.append(f"uncertainty_cases[{index}] requires at least two independent specialists")
        arbiter_id = case.get("arbiter_id")
        if not isinstance(arbiter_id, str) or not arbiter_id:
            errors.append(f"uncertainty_cases[{index}].arbiter_id must be a non-empty string")
        elif arbiter_id in unique_specialists:
            errors.append(f"uncertainty_cases[{index}].arbiter_id must be independent")
        evidence_ids = case.get("evidence_ids")
        if not isinstance(evidence_ids, list) or not evidence_ids or any(not isinstance(item, str) or not item for item in evidence_ids):
            errors.append(f"uncertainty_cases[{index}].evidence_ids must contain evidence ids")
        if case.get("status") not in {"open", "resolved"}:
            errors.append(f"uncertainty_cases[{index}].status must be open or resolved")
        if case.get("status") == "open" and case.get("stop_current_path") is not True:
            errors.append(f"uncertainty_cases[{index}] must stop the current path while open")
        if (
            isinstance(case.get("problem_id"), str)
            and case.get("status") == "open"
            and case.get("stop_current_path") is True
            and len(unique_specialists) >= 2
            and isinstance(arbiter_id, str)
            and arbiter_id not in unique_specialists
            and isinstance(evidence_ids, list)
            and bool(evidence_ids)
        ):
            open_problems.add(case["problem_id"])
    for problem_id, count in failures.items():
        if count >= 2 and problem_id not in open_problems:
            errors.append(f"problem {problem_id} requires an open independent uncertainty case after two failures")
    for problem_id in stale_problems:
        if problem_id not in open_problems:
            errors.append(f"problem {problem_id} requires an open uncertainty case after evidence freshness expired")


def _validate_capability_pack(contract: dict[str, Any], errors: list[str]) -> None:
    pack = _require_mapping(contract.get("capability_pack"), "capability_pack", errors)
    _require_nonempty(pack.get("pack_id"), "capability_pack.pack_id", errors)
    if pack.get("status") != "candidate":
        errors.append("schema v1 accepts candidate packs only; promotion requires a trusted signed exact-SHA adapter")
    if pack.get("independent_verification_receipt") is not None or pack.get("qualified_replay_receipt") is not None:
        errors.append("candidate packs cannot claim verification or replay receipts")
    if not isinstance(pack.get("revalidate_on"), list) or not pack.get("revalidate_on"):
        errors.append("capability_pack.revalidate_on must be a non-empty list")


def validate_contract(contract: dict[str, Any]) -> dict[str, Any]:
    errors: list[str] = []
    if contract.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    if contract.get("stage") != "delivery-contract":
        errors.append("stage must be delivery-contract")
    expected_task_id = digest({"task": contract.get("literal_request")})[7:23]
    if contract.get("task_id") != expected_task_id:
        errors.append("task_id must be derived from the exact literal_request")
    moves, longest_path = _validate_moves(contract, errors)
    _validate_authority(contract, moves, errors)
    _validate_discovery_and_forecasts(contract, moves, errors)
    _validate_repository(contract, errors)
    _validate_routing_and_verification(contract, errors)
    _validate_attempts(contract, errors)
    _validate_capability_pack(contract, errors)
    if errors:
        raise ContractError(errors)
    return {
        "status": "valid",
        "schema_version": SCHEMA_VERSION,
        "task_id": contract["task_id"],
        "contract_digest": digest(contract),
        "move_count": len(moves),
        "longest_path": longest_path,
        "horizon_required": contract["classification"]["horizon_required"],
    }


def ready_moves(contract: dict[str, Any]) -> list[str]:
    validate_contract(contract)
    moves = {move["move_id"]: move for move in contract["move_graph"]}
    terminal = {move_id for move_id, move in moves.items() if move["status"] == "passed"}
    ready = [
        move_id
        for move_id, move in moves.items()
        if move["plane"] == "delivery"
        and move["kind"] != "admit"
        and move["kind"] not in MUTATING_KINDS
        and move["status"] in {"admitted", "ready"}
        and all(parent in terminal for parent in move["parents"])
        and all(prerequisite in terminal for prerequisite in move["prerequisites"])
    ]
    return ready[: contract["limits"]["max_parallel_workers"]]


def _read_json(path: str | None) -> dict[str, Any]:
    try:
        raw = sys.stdin.read() if not path or path == "-" else Path(path).read_text(encoding="utf-8")
        value = json.loads(raw)
    except (json.JSONDecodeError, OSError) as exc:
        raise ContractError([f"unable to read JSON: {exc}"]) from exc
    if not isinstance(value, dict):
        raise ContractError(["top-level JSON must be an object"])
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compile and gate Senior Harness task contracts.")
    sub = parser.add_subparsers(dest="command", required=True)
    intake_parser = sub.add_parser("intake", help="Create a bounded intake envelope from a literal request.")
    intake_parser.add_argument("task")
    intake_parser.add_argument("--horizon-required", action="store_true")
    sub.add_parser("where", help="Show the physical canonical skill and Pi-Dev-Ops source paths.")
    bind_parser = sub.add_parser("bind-attempt", help="Bind an attempt to a frozen task before fingerprinting.")
    bind_parser.add_argument("contract_path")
    bind_parser.add_argument("attempt_path")
    for command in ("lint", "ready", "fingerprint"):
        child = sub.add_parser(command)
        child.add_argument("path", nargs="?", default="-")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "intake":
            result: Any = intake(args.task, args.horizon_required)
        elif args.command == "where":
            result = {
                "skill_root": str(Path(__file__).resolve().parents[1]),
                "skill_folder_digest": skill_folder_digest(),
                "repository_root": str(REPO_ROOT),
                "model_router": str(REPO_ROOT / "skills" / "model-router" / "SKILL.md"),
                "unlazy": str(REPO_ROOT / "skills" / "unlazy" / "SKILL.md"),
            }
        elif args.command == "bind-attempt":
            result = bind_attempt(_read_json(args.contract_path), _read_json(args.attempt_path))
        else:
            payload = _read_json(args.path)
            if args.command == "lint":
                result = validate_contract(payload)
            elif args.command == "ready":
                result = {"status": "valid", "ready": ready_moves(payload)}
            else:
                result = {"fingerprint": attempt_fingerprint(payload)}
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    except ContractError as exc:
        print(json.dumps({"status": "invalid", "errors": exc.errors}, sort_keys=True), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
