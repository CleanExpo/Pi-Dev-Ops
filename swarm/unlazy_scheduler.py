"""Validated dependency plans and a deterministic rolling-ready scheduler.

The scheduler never launches a provider itself.  It returns the safe ready set for the
active harness, which preserves provider resolution in the existing routing seam.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


NODE_TYPES = {"root", "branch", "leaf"}
NODE_STATES = {"pending", "ready", "running", "verifying", "passed", "blocked", "cancelled"}
WILDCARDS = re.compile(r"[*?\[\]{}]")
GIT_SHA = re.compile(r"[0-9a-f]{40}")
SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
TRUSTED_GATE_RUNNER_VERSION = "nexus-unlazy-gate-v3"
TRUSTED_GATE_RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "unlazy-gate-check.mjs"


class PlanValidationError(ValueError):
    """One or more plan invariants failed."""

    def __init__(self, errors: Iterable[str]):
        self.errors = tuple(errors)
        super().__init__("; ".join(self.errors))


@dataclass(frozen=True)
class PlanNode:
    id: str
    type: str
    purpose: str
    owns: tuple[str, ...]
    needs: tuple[str, ...]
    exports: tuple[str, ...]
    route_ref: str
    worker_id: str
    gates: str
    state: str
    attempt: int
    verification_receipt: dict[str, Any] | None

    @classmethod
    def from_dict(cls, raw: dict[str, Any], index: int) -> "PlanNode":
        node_id = str(raw.get("id") or "").strip()
        node_type = str(raw.get("type") or "").strip()
        state = str(raw.get("state") or "pending").strip()
        errors: list[str] = []
        if not node_id:
            errors.append(f"nodes[{index}].id is required")
        if node_type not in NODE_TYPES:
            errors.append(f"node {node_id or index} type must be one of {sorted(NODE_TYPES)}")
        if state not in NODE_STATES:
            errors.append(f"node {node_id or index} state must be one of {sorted(NODE_STATES)}")
        attempt = raw.get("attempt", 0)
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt < 0:
            errors.append(f"node {node_id or index} attempt must be a non-negative integer")
        for field_name in ("owns", "needs", "exports"):
            if not isinstance(raw.get(field_name, []), list):
                errors.append(f"node {node_id or index} {field_name} must be a list")
        if errors:
            raise PlanValidationError(errors)
        owns: list[str] = []
        for item in raw.get("owns", []):
            canonical = _normalise_path(str(item), node_id or str(index), errors)
            if canonical is not None:
                owns.append(canonical)
        if errors:
            raise PlanValidationError(errors)
        return cls(
            id=node_id,
            type=node_type,
            purpose=str(raw.get("purpose") or "").strip(),
            owns=tuple(owns),
            needs=tuple(str(item) for item in raw.get("needs", [])),
            exports=tuple(str(item) for item in raw.get("exports", [])),
            route_ref=str(raw.get("route_ref") or "").strip(),
            worker_id=str(raw.get("worker_id") or "").strip(),
            gates=str(raw.get("gates") or "").strip(),
            state=state,
            attempt=attempt,
            verification_receipt=copy.deepcopy(raw.get("verification_receipt"))
            if isinstance(raw.get("verification_receipt"), dict)
            else None,
        )


@dataclass(frozen=True)
class UnlazyPlan:
    schema_version: str
    plan_id: str
    task: str
    requested_depth: int
    effective_depth: int
    adjustment_reason: str
    base_sha: str
    worktree: str
    max_parallel_workers: int
    nodes: tuple[PlanNode, ...]

    @property
    def by_id(self) -> dict[str, PlanNode]:
        return {node.id: node for node in self.nodes}


def _verification_receipt_errors(
    plan_id: str,
    base_sha: str,
    plan_worktree: str,
    node: PlanNode,
    receipt: dict[str, Any] | None,
    *,
    passed: bool,
) -> list[str]:
    if not isinstance(receipt, dict):
        return ["verification receipt is required"]
    errors: list[str] = []
    if receipt.get("schema_version") != "1.0":
        errors.append("verification receipt schema_version must be '1.0'")
    if receipt.get("plan_id") != plan_id:
        errors.append("verification receipt plan_id does not match plan")
    if receipt.get("node_id") != node.id:
        errors.append("verification receipt node_id does not match node")
    if receipt.get("worker_id") != node.worker_id:
        errors.append("verification receipt worker_id does not match node")
    verifier_id = receipt.get("verifier_id")
    if not isinstance(verifier_id, str) or not verifier_id.strip():
        errors.append("verification receipt verifier_id is required")
    if verifier_id == node.worker_id or receipt.get("independent_verifier") is not True:
        errors.append("verification receipt must attest an independent verifier")
    if receipt.get("mode") != "run" or receipt.get("verified") is not True:
        errors.append("verification receipt must be a verified run")
    if receipt.get("worktree_clean_before_run") is not True:
        errors.append("verification receipt must bind a clean worktree")
    runner_version = receipt.get("runner_version")
    if not isinstance(runner_version, str) or not runner_version.strip():
        errors.append("verification receipt runner_version is required")
    elif runner_version != TRUSTED_GATE_RUNNER_VERSION:
        errors.append("verification receipt runner_version is not trusted")
    candidate_sha = receipt.get("candidate_sha")
    if not isinstance(candidate_sha, str) or not GIT_SHA.fullmatch(candidate_sha):
        errors.append("verification receipt candidate_sha must be a full Git SHA")
    if base_sha and receipt.get("base_sha") != base_sha:
        errors.append("verification receipt base_sha does not match plan")
    for digest_field in ("environment_digest", "relevant_input_digest"):
        digest = receipt.get(digest_field)
        if not isinstance(digest, str) or not SHA256_DIGEST.fullmatch(digest):
            errors.append(f"verification receipt {digest_field} must be a sha256 digest")
    gate_files = receipt.get("gate_files")
    gate_match = False
    if isinstance(gate_files, list):
        gate_match = any(
            isinstance(item, dict)
            and item.get("path") == node.gates
            and isinstance(item.get("digest"), str)
            and SHA256_DIGEST.fullmatch(item["digest"])
            for item in gate_files
        )
    if not gate_match:
        errors.append("verification receipt must include the node gate file and digest")
    summary = receipt.get("summary")
    count_names = ("passed", "failed", "pending", "abandoned", "runner_errors")
    counts: dict[str, int] = {}
    if not isinstance(summary, dict):
        errors.append("verification receipt summary is required")
    else:
        for name in count_names:
            value = summary.get(name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                errors.append(f"verification receipt summary.{name} must be non-negative")
            else:
                counts[name] = value
    if len(counts) == len(count_names):
        non_passing = sum(counts[name] for name in count_names if name != "passed")
        if passed and (counts["passed"] < 1 or non_passing != 0):
            errors.append("passed requires strict gate counts at zero")
        if not passed and non_passing == 0:
            errors.append("blocked requires a non-passing gate count")
    errors.extend(_runtime_receipt_errors(plan_worktree, node, receipt, passed=passed))
    return errors


def _git_value(worktree: Path, *args: str) -> str | None:
    result = subprocess.run(
        ["git", "-C", str(worktree), *args],
        text=True,
        capture_output=True,
        check=False,
    )
    return result.stdout.strip() if result.returncode == 0 else None


def _file_digest(path: Path) -> str:
    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()


def _safe_bound_file(worktree: Path, relative_path: Any) -> Path | None:
    if not isinstance(relative_path, str) or not relative_path:
        return None
    candidate = (worktree / relative_path).resolve()
    try:
        candidate.relative_to(worktree)
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


REPLAY_TOP_FIELDS = (
    "schema_version", "mode", "verified", "runner_version", "plan_id", "node_id",
    "worker_id", "verifier_id", "independent_verifier", "base_sha", "candidate_sha",
    "worktree_clean_before_run", "cwd", "environment_keys", "environment_digest",
    "relevant_inputs", "relevant_input_digest", "gate_files", "summary",
)
REPLAY_GATE_FIELDS = (
    "file", "line", "checked", "id", "outcome", "check", "exits", "expect", "timeout",
    "evidence", "abandoned", "parseError", "state", "exitCode", "timedOut", "runnerError",
    "commandDigest", "relevantInputDigest", "expectMatched", "stdoutDigest", "stderrDigest",
    "safeSummary",
)


def _replay_evidence(receipt: dict[str, Any]) -> dict[str, Any]:
    evidence = {field: receipt.get(field) for field in REPLAY_TOP_FIELDS}
    gates = receipt.get("gates")
    evidence["gates"] = [
        {field: gate.get(field) for field in REPLAY_GATE_FIELDS}
        for gate in gates
        if isinstance(gate, dict)
    ] if isinstance(gates, list) else None
    return evidence


def _trusted_replay_errors(
    worktree: Path,
    node: PlanNode,
    receipt: dict[str, Any],
    *,
    passed: bool,
) -> list[str]:
    relevant_entries = receipt.get("relevant_inputs")
    environment_keys = receipt.get("environment_keys")
    verifier_id = receipt.get("verifier_id")
    if (
        not TRUSTED_GATE_RUNNER.is_file()
        or not isinstance(relevant_entries, list)
        or not isinstance(environment_keys, list)
        or not isinstance(verifier_id, str)
    ):
        return ["verification receipt cannot be replayed by the trusted gate runner"]

    command = [
        "node", str(TRUSTED_GATE_RUNNER), "--json", "--cwd", str(worktree),
        "--plan-id", str(receipt.get("plan_id", "")),
        "--node-id", node.id,
        "--worker-id", node.worker_id,
        "--verifier-id", verifier_id,
    ]
    for key in environment_keys:
        command.extend(("--env", key))
    for item in relevant_entries:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            return ["verification receipt cannot be replayed by the trusted gate runner"]
        command.extend(("--relevant-input", item["path"]))
    command.append(node.gates)

    gates = receipt.get("gates")
    declared_timeout = sum(
        gate.get("timeout", 60)
        for gate in gates
        if isinstance(gate, dict) and isinstance(gate.get("timeout", 60), int)
    ) if isinstance(gates, list) else 60
    replay_timeout = min(7200, max(30, declared_timeout + 30))
    try:
        replay = subprocess.run(
            command,
            cwd=worktree,
            text=True,
            capture_output=True,
            check=False,
            timeout=replay_timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return ["verification receipt trusted gate replay failed"]

    expected_returncode = 0 if passed else 1
    if replay.returncode != expected_returncode:
        return ["verification receipt does not reproduce under trusted gate runner"]
    try:
        reproduced = json.loads(replay.stdout)
    except json.JSONDecodeError:
        return ["verification receipt trusted gate replay returned invalid JSON"]
    if not isinstance(reproduced, dict) or _replay_evidence(receipt) != _replay_evidence(reproduced):
        return ["verification receipt does not reproduce under trusted gate runner"]
    return []


def _runtime_receipt_errors(
    plan_worktree: str,
    node: PlanNode,
    receipt: dict[str, Any],
    *,
    passed: bool,
) -> list[str]:
    errors: list[str] = []
    cwd_value = receipt.get("cwd")
    if not isinstance(cwd_value, str) or not plan_worktree:
        return ["verification receipt cwd and plan worktree are required"]
    cwd = Path(cwd_value).resolve()
    worktree = Path(plan_worktree).resolve()
    if not worktree.is_dir():
        return ["verification receipt worktree is not available"]
    actual_root = _git_value(cwd, "rev-parse", "--show-toplevel")
    if actual_root is None or Path(actual_root).resolve() != worktree:
        return ["verification receipt cwd does not belong to the plan worktree"]
    actual_head = _git_value(worktree, "rev-parse", "HEAD")
    if actual_head != receipt.get("candidate_sha"):
        errors.append("verification receipt candidate_sha does not match actual worktree HEAD")
    actual_status = _git_value(worktree, "status", "--porcelain=v1", "--untracked-files=all")
    if actual_status is None or actual_status:
        errors.append("verification receipt worktree is not actually clean")
    actual_base = _git_value(worktree, "merge-base", "origin/main", "HEAD")
    if actual_base != receipt.get("base_sha"):
        errors.append("verification receipt base_sha does not match actual merge base")

    gate_file = _safe_bound_file(worktree, node.gates)
    gate_entries = receipt.get("gate_files")
    gate_entry = next(
        (
            item for item in gate_entries
            if isinstance(item, dict) and item.get("path") == node.gates
        ),
        None,
    ) if isinstance(gate_entries, list) else None
    if gate_file is None or gate_entry is None or gate_entry.get("digest") != _file_digest(gate_file):
        errors.append("verification receipt node gate digest does not match runtime content")

    relevant_entries = receipt.get("relevant_inputs")
    recomputed: list[tuple[str, str]] = []
    if not isinstance(relevant_entries, list) or not relevant_entries:
        errors.append("verification receipt relevant_inputs are required")
    else:
        for item in relevant_entries:
            path_text = item.get("path") if isinstance(item, dict) else None
            bound_file = _safe_bound_file(worktree, path_text)
            if bound_file is None:
                errors.append("verification receipt relevant input is unavailable or unsafe")
                continue
            actual_digest = _file_digest(bound_file)
            if item.get("digest") != actual_digest:
                errors.append("verification receipt relevant input digest does not match runtime content")
            recomputed.append((path_text, actual_digest))
    recomputed.sort(key=lambda item: item[0])
    relevant_payload = "\0".join(f"{path}\0{digest}" for path, digest in recomputed)
    actual_relevant_digest = "sha256:" + hashlib.sha256(relevant_payload.encode()).hexdigest()
    if receipt.get("relevant_input_digest") != actual_relevant_digest:
        errors.append("verification receipt relevant_input_digest does not match runtime content")

    environment_keys = receipt.get("environment_keys")
    if not isinstance(environment_keys, list) or any(
        not isinstance(key, str) or not key for key in environment_keys
    ):
        errors.append("verification receipt environment_keys are invalid")
    else:
        environment_payload = "\0".join(
            f"{key}={os.environ.get(key, '<unset>')}" for key in sorted(set(environment_keys))
        )
        actual_environment = "sha256:" + hashlib.sha256(environment_payload.encode()).hexdigest()
        if receipt.get("environment_digest") != actual_environment:
            errors.append("verification receipt environment_digest does not match runtime environment")

    gates = receipt.get("gates")
    if isinstance(gates, list):
        actual_summary = {"passed": 0, "failed": 0, "pending": 0, "abandoned": 0, "runner_errors": 0}
        for gate in gates:
            state = gate.get("state") if isinstance(gate, dict) else None
            if state == "runner_error":
                actual_summary["runner_errors"] += 1
            elif state in actual_summary:
                actual_summary[state] += 1
            else:
                errors.append("verification receipt contains an invalid gate state")
        if receipt.get("summary") != actual_summary:
            errors.append("verification receipt summary does not match gate results")
    else:
        errors.append("verification receipt gates are required")
    if not errors:
        errors.extend(_trusted_replay_errors(worktree, node, receipt, passed=passed))
    return errors


def _depth(value: Any, name: str, errors: list[str], *, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        errors.append(f"{name} must be a positive integer")
        return 1
    if maximum is not None and value > maximum:
        errors.append(f"{name} must be <= {maximum}")
    return value


def _normalise_path(path: str, node_id: str, errors: list[str]) -> str | None:
    candidate = path.strip().replace("\\", "/")
    pure = PurePosixPath(candidate)
    if not candidate or pure.is_absolute() or ".." in pure.parts:
        errors.append(f"node {node_id} owns unsafe path {path!r}")
        return None
    if WILDCARDS.search(candidate):
        errors.append(f"node {node_id} owns unresolved wildcard path {path!r}")
        return None
    return pure.as_posix().rstrip("/")


def paths_overlap(left: str, right: str) -> bool:
    """Return True for exact or parent/child ownership overlap."""
    a = PurePosixPath(left).parts
    b = PurePosixPath(right).parts
    common = min(len(a), len(b))
    return a[:common] == b[:common]


def path_is_owned(candidate: str, owned: str) -> bool:
    """Return True when candidate is the owned path or one of its descendants."""
    candidate_parts = PurePosixPath(candidate).parts
    owned_parts = PurePosixPath(owned).parts
    return len(candidate_parts) >= len(owned_parts) and (
        candidate_parts[: len(owned_parts)] == owned_parts
    )


def _has_cycle(nodes: dict[str, PlanNode]) -> bool:
    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(node_id: str) -> bool:
        if node_id in visiting:
            return True
        if node_id in visited:
            return False
        visiting.add(node_id)
        for dependency in nodes[node_id].needs:
            if dependency in nodes and visit(dependency):
                return True
        visiting.remove(node_id)
        visited.add(node_id)
        return False

    return any(visit(node_id) for node_id in nodes)


def validate_plan(raw: dict[str, Any]) -> UnlazyPlan:
    """Validate schema, DAG, depth, and exclusive ownership before dispatch."""
    errors: list[str] = []
    if raw.get("schema_version") != "1.0":
        errors.append("schema_version must be '1.0'")
    task = str(raw.get("task") or "").strip()
    plan_id = str(raw.get("plan_id") or "").strip()
    if not task:
        errors.append("task is required")
    if not plan_id:
        errors.append("plan_id is required")
    requested = _depth(raw.get("requested_depth"), "requested_depth", errors)
    effective = _depth(raw.get("effective_depth"), "effective_depth", errors, maximum=7)
    adjustment_reason = str(raw.get("adjustment_reason") or "").strip()
    if effective > requested:
        errors.append("effective_depth cannot exceed requested_depth")
    if effective != requested and not adjustment_reason:
        errors.append("adjustment_reason is required when effective_depth differs")
    workers = raw.get("max_parallel_workers", 3)
    if isinstance(workers, bool) or not isinstance(workers, int) or not 1 <= workers <= 16:
        errors.append("max_parallel_workers must be an integer between 1 and 16")
        workers = 1

    raw_nodes = raw.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        errors.append("nodes must be a non-empty list")
        raw_nodes = []
    nodes: list[PlanNode] = []
    for index, entry in enumerate(raw_nodes):
        if not isinstance(entry, dict):
            errors.append(f"nodes[{index}] must be an object")
            continue
        try:
            nodes.append(PlanNode.from_dict(entry, index))
        except PlanValidationError as exc:
            errors.extend(exc.errors)

    ids = [node.id for node in nodes]
    if len(ids) != len(set(ids)):
        errors.append("node ids must be unique")
    by_id = {node.id: node for node in nodes}
    root_count = sum(node.type == "root" for node in nodes)
    if root_count != 1:
        errors.append("plan must contain exactly one root node")
    for node in nodes:
        if node.id in node.needs:
            errors.append(f"node {node.id} cannot depend on itself")
        missing = sorted(set(node.needs) - set(by_id))
        if missing:
            errors.append(f"node {node.id} needs unknown nodes {missing}")
        if node.type == "leaf" and not node.owns:
            errors.append(f"leaf {node.id} must own at least one path")
        if node.type == "leaf" and not node.gates:
            errors.append(f"leaf {node.id} must name a gate file")
        if node.type == "leaf" and not node.route_ref:
            errors.append(f"leaf {node.id} must name a route_ref")
        if node.type == "leaf" and not node.worker_id:
            errors.append(f"leaf {node.id} must name a worker_id")
        if node.gates:
            gate_path = PurePosixPath(node.gates.replace("\\", "/"))
            if gate_path.is_absolute() or ".." in gate_path.parts or gate_path.suffix != ".md":
                errors.append(f"node {node.id} has unsafe gate path {node.gates!r}")
        if node.type == "leaf" and node.state in {"passed", "blocked"}:
            errors.extend(
                _verification_receipt_errors(
                    plan_id,
                    str(raw.get("base_sha") or "").strip(),
                    str(raw.get("worktree") or "").strip(),
                    node,
                    node.verification_receipt,
                    passed=node.state == "passed",
                )
            )
    if by_id and _has_cycle(by_id):
        errors.append("dependency graph contains a cycle")
    roots = [node for node in nodes if node.type == "root"]
    if len(roots) == 1:
        reachable: set[str] = set()
        stack = list(roots[0].needs)
        while stack:
            current = stack.pop()
            if current in reachable or current not in by_id:
                continue
            reachable.add(current)
            stack.extend(by_id[current].needs)
        unreachable = sorted(set(by_id) - {roots[0].id} - reachable)
        if unreachable:
            errors.append(f"nodes are not reachable from root dependencies: {unreachable}")

    ownership: list[tuple[str, str]] = []
    for node in nodes:
        for raw_path in node.owns:
            path = _normalise_path(raw_path, node.id, errors)
            if path:
                for owner, owned in ownership:
                    if owner != node.id and paths_overlap(path, owned):
                        errors.append(
                            f"ownership collision: {node.id}:{path} overlaps {owner}:{owned}"
                        )
                ownership.append((node.id, path))

    if errors:
        raise PlanValidationError(errors)
    return UnlazyPlan(
        schema_version="1.0",
        plan_id=plan_id,
        task=task,
        requested_depth=requested,
        effective_depth=effective,
        adjustment_reason=adjustment_reason,
        base_sha=str(raw.get("base_sha") or "").strip(),
        worktree=str(raw.get("worktree") or "").strip(),
        max_parallel_workers=workers,
        nodes=tuple(nodes),
    )


def _node_collides(node: PlanNode, others: Iterable[PlanNode]) -> bool:
    return any(
        paths_overlap(candidate, owned)
        for candidate in node.owns
        for other in others
        for owned in other.owns
    )


def ready_nodes(raw: dict[str, Any] | UnlazyPlan, active_ids: Iterable[str] = ()) -> tuple[PlanNode, ...]:
    """Select the next deterministic rolling batch after every completed return."""
    plan = raw if isinstance(raw, UnlazyPlan) else validate_plan(raw)
    by_id = plan.by_id
    active = [by_id[node_id] for node_id in active_ids if node_id in by_id]
    active.extend(node for node in plan.nodes if node.state in {"running", "verifying"} and node not in active)
    slots = max(0, plan.max_parallel_workers - len(active))
    selected: list[PlanNode] = []
    for node in sorted(plan.nodes, key=lambda item: item.id):
        if slots == 0:
            break
        if node.type != "leaf" or node.state not in {"pending", "ready"}:
            continue
        if not all(by_id[dependency].state == "passed" for dependency in node.needs):
            continue
        if _node_collides(node, (*active, *selected)):
            continue
        selected.append(node)
        slots -= 1
    return tuple(selected)


def record_result(
    raw: dict[str, Any],
    node_id: str,
    *,
    passed: bool,
    changed_paths: Iterable[str],
    verification_receipt: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return a copied plan with one terminal leaf result, rejecting contract drift."""
    plan = validate_plan(raw)
    if node_id not in plan.by_id:
        raise PlanValidationError([f"unknown node {node_id}"])
    node = plan.by_id[node_id]
    if node.type != "leaf":
        raise PlanValidationError([f"node {node_id} is not a leaf"])
    if node.state != "verifying":
        raise PlanValidationError([f"node {node_id} must be verifying before a terminal result"])
    if type(passed) is not bool:
        raise PlanValidationError(["passed must be a boolean"])
    receipt_errors = _verification_receipt_errors(
        plan.plan_id,
        plan.base_sha,
        plan.worktree,
        node,
        verification_receipt,
        passed=passed,
    )
    if receipt_errors:
        raise PlanValidationError(receipt_errors)
    path_errors: list[str] = []
    canonical_changed: list[str] = []
    for raw_path in changed_paths:
        canonical = _normalise_path(str(raw_path), node_id, path_errors)
        if canonical is not None:
            canonical_changed.append(canonical)
    if path_errors:
        raise PlanValidationError(path_errors)
    outside = [
        path
        for path in canonical_changed
        if not any(path_is_owned(path, owned) for owned in node.owns)
    ]
    if outside:
        raise PlanValidationError([f"node {node_id} changed paths outside ownership: {sorted(outside)}"])
    updated = copy.deepcopy(raw)
    for entry in updated["nodes"]:
        if entry.get("id") == node_id:
            entry["state"] = "passed" if passed else "blocked"
            entry["attempt"] = int(entry.get("attempt", 0)) + 1
            entry["verification_receipt"] = copy.deepcopy(verification_receipt)
            break
    validate_plan(updated)
    return updated


def plan_template(task: str, requested_depth: int, *, max_workers: int = 3) -> dict[str, Any]:
    """Return a minimal plan shell; the driver must replace the placeholder leaf."""
    effective = min(max(requested_depth, 1), 7)
    return {
        "schema_version": "1.0",
        "plan_id": str(uuid.uuid4()),
        "task": task,
        "requested_depth": requested_depth,
        "effective_depth": effective,
        "adjustment_reason": "capped-at-seven" if requested_depth > 7 else "",
        "base_sha": "",
        "worktree": "",
        "max_parallel_workers": max_workers,
        "nodes": [
            {
                "id": "1",
                "type": "root",
                "purpose": "integrate and verify the task",
                "owns": [],
                "needs": ["1.1"],
                "exports": [],
                "route_ref": "",
                "worker_id": "",
                "gates": "gates/root.md",
                "state": "pending",
                "attempt": 0,
            },
            {
                "id": "1.1",
                "type": "leaf",
                "purpose": "replace with one natural deliverable",
                "owns": ["REPLACE_ME"],
                "needs": [],
                "exports": [],
                "route_ref": "",
                "worker_id": "REPLACE_ME",
                "gates": "gates/leaf-1.1.md",
                "state": "pending",
                "attempt": 0,
            },
        ],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Lint Unlazy plans and emit rolling-ready leaves")
    sub = parser.add_subparsers(dest="action", required=True)
    lint = sub.add_parser("lint")
    lint.add_argument("plan")
    ready = sub.add_parser("ready")
    ready.add_argument("plan")
    ready.add_argument("--active", action="append", default=[])
    template = sub.add_parser("template")
    template.add_argument("task")
    template.add_argument("--tree", type=int, default=3)
    template.add_argument("--max-workers", type=int, default=3)
    args = parser.parse_args(argv)
    try:
        if args.action == "template":
            if args.tree < 1:
                raise PlanValidationError(["tree depth must be positive"])
            print(json.dumps(plan_template(args.task, args.tree, max_workers=args.max_workers), indent=2))
            return 0
        raw = json.loads(Path(args.plan).read_text())
        plan = validate_plan(raw)
        if args.action == "lint":
            print(json.dumps({"status": "valid", "plan_id": plan.plan_id, "nodes": len(plan.nodes)}))
        else:
            print(json.dumps({"ready": [node.id for node in ready_nodes(plan, args.active)]}))
        return 0
    except (OSError, json.JSONDecodeError, PlanValidationError) as exc:
        errors = exc.errors if isinstance(exc, PlanValidationError) else [str(exc)]
        print(json.dumps({"status": "invalid", "errors": list(errors)}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
