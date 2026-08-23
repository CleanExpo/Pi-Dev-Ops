"""Move-graph structure and admission-path validation."""
from __future__ import annotations

from collections import Counter, defaultdict, deque
from typing import Any

from senior_harness_core import require_mapping, require_nonempty


MOVE_FIELDS = {
    "move_id", "parents", "plane", "kind", "state_delta", "owner", "prerequisites",
    "evidence_ids", "confidence", "counter_case", "value", "cost", "reversibility",
    "trigger", "expiry", "status", "authority_required", "authorization_status",
}
ALLOWED_PLANES = {"horizon", "delivery", "verification", "learning"}
ALLOWED_AUTHORIZATION = {"proposal", "approved", "not-required"}
ALLOWED_STATUSES = {"proposed", "admitted", "ready", "active", "blocked", "passed", "failed"}
PLANE_KINDS = {
    "horizon": {"observe", "discover", "challenge", "model", "forecast", "propose"},
    "delivery": {
        "admit", "route", "decompose", "guard", "escalate", "specify", "execute",
        "deploy", "migrate", "publish", "purchase", "delete", "write-files", "push",
        "send-message", "run-command", "edit", "commit", "merge", "provision", "configure",
    },
    "verification": {"test", "verify", "arbitrate"},
    "learning": {"promote", "replay", "harden", "revalidate"},
}
MUTATING_KINDS = {
    "execute", "deploy", "migrate", "publish", "purchase", "delete", "write-files",
    "push", "send-message", "run-command", "edit", "commit", "merge", "provision", "configure",
}
MAX_NODES = 500
MAX_BRANCH_WIDTH = 20
MAX_PARALLEL_WORKERS = 100


def _validate_move_lists(move: dict[str, Any], move_id: Any, errors: list[str]) -> None:
    if not isinstance(move.get("parents"), list):
        errors.append(f"move {move_id}.parents must be a list")
    prerequisites = move.get("prerequisites")
    if not isinstance(prerequisites, list):
        errors.append(f"move {move_id}.prerequisites must be a list")
    elif any(not isinstance(item, str) for item in prerequisites):
        errors.append(f"move {move_id}.prerequisites must contain move ids")
    evidence_ids = move.get("evidence_ids")
    if not isinstance(evidence_ids, list):
        errors.append(f"move {move_id}.evidence_ids must be a list")
    elif not evidence_ids or any(not isinstance(item, str) or not item for item in evidence_ids):
        errors.append(f"move {move_id}.evidence_ids must contain at least one evidence id")


def _validate_move_shape(move: dict[str, Any], index: int, errors: list[str]) -> tuple[str | None, str | None]:
    missing = sorted(MOVE_FIELDS - set(move))
    if missing:
        errors.append(f"move_graph[{index}] missing fields: {', '.join(missing)}")
    move_id = move.get("move_id")
    require_nonempty(move_id, f"move_graph[{index}].move_id", errors)
    plane = move.get("plane")
    if plane not in ALLOWED_PLANES:
        errors.append(f"move {move_id} has invalid plane")
    elif move.get("kind") not in PLANE_KINDS[plane]:
        errors.append(f"move {move_id} kind {move.get('kind')} is not allowed on plane {plane}")
    if move.get("status") not in ALLOWED_STATUSES:
        errors.append(f"move {move_id} has invalid status")
    _validate_move_lists(move, move_id, errors)
    fields = ("kind", "state_delta", "owner", "counter_case", "value", "cost", "reversibility", "trigger", "expiry", "authority_required")
    for field in fields:
        require_nonempty(move.get(field), f"move {move_id}.{field}", errors)
    confidence = move.get("confidence")
    if isinstance(confidence, bool) or not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
        errors.append(f"move {move_id}.confidence must be between 0 and 1")
    delta = " ".join(move["state_delta"].lower().split()) if isinstance(move.get("state_delta"), str) else None
    return move_id if isinstance(move_id, str) else None, delta


def _collect_moves(raw_moves: list[Any], errors: list[str]) -> list[dict[str, Any]]:
    moves: list[dict[str, Any]] = []
    ids: list[str] = []
    deltas: list[str] = []
    for index, raw in enumerate(raw_moves):
        move = require_mapping(raw, f"move_graph[{index}]", errors)
        moves.append(move)
        move_id, delta = _validate_move_shape(move, index, errors)
        if move_id is not None:
            ids.append(move_id)
        if delta is not None:
            deltas.append(delta)
    duplicate_ids = sorted(item for item, count in Counter(ids).items() if count > 1)
    if duplicate_ids:
        errors.append(f"duplicate move ids: {', '.join(duplicate_ids)}")
    if any(count > 1 for count in Counter(deltas).values()):
        errors.append("duplicate state_delta values are not structurally distinct moves")
    return moves


def _build_graph(moves: list[dict[str, Any]], errors: list[str]) -> tuple[dict[str, dict[str, Any]], dict[str, list[str]], dict[str, int]]:
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
            elif parent not in by_id:
                errors.append(f"move {move_id} references missing parent {parent}")
            else:
                children[parent].append(move_id)
                indegree[move_id] += 1
                if by_id[parent].get("plane") == "horizon" and move.get("plane") == "delivery" and move.get("kind") != "admit":
                    errors.append(f"move {move_id} bypasses admission from Horizon to delivery")
    return by_id, children, indegree


def _validate_limits(contract: dict[str, Any], moves: list[dict[str, Any]], children: dict[str, list[str]], errors: list[str]) -> None:
    limits = require_mapping(contract.get("limits"), "limits", errors)
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


def _walk_graph(by_id: dict[str, dict[str, Any]], children: dict[str, list[str]], indegree: dict[str, int], errors: list[str]) -> tuple[dict[str, set[str]], int]:
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
    return ancestors, max(distances.values(), default=0)


def _validate_admission_paths(by_id: dict[str, dict[str, Any]], ancestors: dict[str, set[str]], errors: list[str]) -> None:
    admission_ids = {
        move_id for move_id, move in by_id.items()
        if move.get("plane") == "delivery" and move.get("kind") == "admit"
    }
    for move_id, move in by_id.items():
        if move.get("plane") == "delivery" and move.get("kind") != "admit":
            if not (ancestors[move_id] & admission_ids):
                errors.append(f"delivery move {move_id} has no admitted ancestor")


def _validate_horizon(contract: dict[str, Any], by_id: dict[str, dict[str, Any]], longest_path: int, errors: list[str]) -> None:
    classification = require_mapping(contract.get("classification"), "classification", errors)
    horizon_required = classification.get("horizon_required")
    if not isinstance(horizon_required, bool):
        errors.append("classification.horizon_required must be a boolean")
    elif horizon_required and not 15 <= longest_path <= 20:
        errors.append(f"horizon path must contain 15-20 distinct state-bearing moves; found {longest_path}")
    if horizon_required:
        roots = [move for move in by_id.values() if not move.get("parents")]
        if not roots or any(move.get("plane") != "horizon" for move in roots):
            errors.append("every horizon-bearing graph root must be on the Horizon plane")


def validate_moves(contract: dict[str, Any], errors: list[str]) -> tuple[list[dict[str, Any]], int]:
    raw_moves = contract.get("move_graph")
    if not isinstance(raw_moves, list) or not raw_moves:
        errors.append("move_graph must be a non-empty list")
        return [], 0
    moves = _collect_moves(raw_moves, errors)
    by_id, children, indegree = _build_graph(moves, errors)
    _validate_limits(contract, moves, children, errors)
    ancestors, longest_path = _walk_graph(by_id, children, indegree, errors)
    _validate_admission_paths(by_id, ancestors, errors)
    _validate_horizon(contract, by_id, longest_path, errors)
    return moves, longest_path
