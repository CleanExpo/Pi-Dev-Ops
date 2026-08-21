"""Validated dependency plans and a deterministic rolling-ready scheduler.

The scheduler never launches a provider itself.  It returns the safe ready set for the
active harness, which preserves provider resolution in the existing routing seam.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import hmac
import json
import math
import os
import re
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from app.server.task_routing import decide_route


NODE_TYPES = {"root", "branch", "leaf"}
NODE_STATES = {"pending", "ready", "running", "verifying", "passed", "blocked", "cancelled"}
WILDCARDS = re.compile(r"[*?\[\]{}]")
GIT_SHA = re.compile(r"[0-9a-f]{40}")
SHA256_DIGEST = re.compile(r"sha256:[0-9a-f]{64}")
SENSITIVE_ENV_KEY = re.compile(
    r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.IGNORECASE,
)
TRUSTED_GATE_RUNNER_VERSION = "nexus-unlazy-gate-v3"
TRUSTED_GATE_RUNNER = Path(__file__).resolve().parents[1] / "scripts" / "unlazy-gate-check.mjs"
TRUSTED_VERIFIER_ID = "unlazy-scheduler-trusted-replay-v1"
TRUSTED_VERIFICATION_AUTHORITY = "scheduler-controlled-replay-v1"
TRUSTED_DISPATCH_AUTHORITY = "scheduler-controlled-dispatch-v1"
FANOUT_CONTROL_OPERATIONS = frozenset({"dispatch", "wait", "verify", "cancel"})


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
    dispatch_receipt: dict[str, Any] | None
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
            dispatch_receipt=copy.deepcopy(raw.get("dispatch_receipt"))
            if isinstance(raw.get("dispatch_receipt"), dict)
            else None,
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
    runtime: bool = False,
    stored: bool = False,
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
    if verifier_id != TRUSTED_VERIFIER_ID:
        errors.append("verification receipt must use the trusted scheduler verifier")
    if stored and receipt.get("verification_authority") != TRUSTED_VERIFICATION_AUTHORITY:
        errors.append("verification receipt must have scheduler-controlled replay authority")
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
    environment_keys = receipt.get("environment_keys")
    if not isinstance(environment_keys, list) or any(
        not isinstance(key, str) or not key for key in environment_keys
    ):
        errors.append("verification receipt environment_keys are invalid")
    elif any(SENSITIVE_ENV_KEY.search(key) for key in environment_keys):
        errors.append("verification receipt cannot allow-list a sensitive environment key")
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
    gates = receipt.get("gates")
    if isinstance(gates, list) and gates:
        actual_summary = {
            "passed": 0, "failed": 0, "pending": 0, "abandoned": 0, "runner_errors": 0,
        }
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
    errors.extend(_receipt_timing_errors(receipt))
    if stored:
        errors.extend(
            _execution_metadata_errors(
                node, receipt.get("execution_controls"), receipt.get("usage"),
            )
        )
        errors.extend(_stored_receipt_authenticity_errors(receipt))
    if runtime:
        errors.extend(_runtime_receipt_errors(plan_worktree, node, receipt))
    return errors


def _receipt_hmac_key() -> bytes | None:
    value = os.environ.get("UNLAZY_RECEIPT_HMAC_KEY", "")
    encoded = value.encode()
    return encoded if len(encoded) >= 32 else None


def _receipt_mac(receipt: dict[str, Any], key: bytes) -> str:
    payload = {name: value for name, value in receipt.items() if name != "authority_mac"}
    canonical = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
    ).encode()
    return "hmac-sha256:" + hmac.new(key, canonical, hashlib.sha256).hexdigest()


def _stored_receipt_authenticity_errors(receipt: dict[str, Any]) -> list[str]:
    key = _receipt_hmac_key()
    if key is None:
        return ["UNLAZY_RECEIPT_HMAC_KEY must contain at least 32 bytes"]
    supplied = receipt.get("authority_mac")
    if not isinstance(supplied, str) or not hmac.compare_digest(supplied, _receipt_mac(receipt, key)):
        return ["verification receipt authenticity check failed"]
    return []


def _execution_metadata_errors(
    node: PlanNode,
    execution_controls: dict[str, Any] | None,
    usage: dict[str, Any] | None,
) -> list[str]:
    errors: list[str] = []
    if not isinstance(execution_controls, dict):
        errors.append("execution controls are required")
    else:
        if execution_controls.get("dispatch_executed") is not True:
            errors.append("execution controls must confirm dispatch_executed")
        if execution_controls.get("result_received") is not True:
            errors.append("execution controls must confirm result_received")
        if execution_controls.get("worker_context_id") != node.worker_id:
            errors.append("execution controls worker_context_id does not match node worker")
    if not isinstance(usage, dict) or usage.get("status") not in {"known", "unknown"}:
        errors.append("usage status must be known or unknown")
    elif usage["status"] == "unknown":
        if not isinstance(usage.get("reason"), str) or not usage["reason"].strip():
            errors.append("unknown usage requires a reason")
    else:
        metrics = [usage.get(name) for name in ("input_tokens", "output_tokens", "cost_usd")]
        reported = [value for value in metrics if value is not None]
        if not reported or any(
            isinstance(value, bool) or not isinstance(value, (int, float))
            or not math.isfinite(value) or value < 0
            for value in reported
        ):
            errors.append("known usage requires finite non-negative reported metrics")
    return errors


def _receipt_timing_errors(receipt: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    parsed: list[datetime] = []
    for field in ("started_at", "finished_at"):
        value = receipt.get(field)
        try:
            timestamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (AttributeError, TypeError, ValueError):
            errors.append(f"verification receipt {field} must be an ISO timestamp")
            continue
        if timestamp.tzinfo is None:
            errors.append(f"verification receipt {field} must include a timezone")
            continue
        parsed.append(timestamp.astimezone(timezone.utc))
    if len(parsed) != 2:
        return errors
    started_at, finished_at = parsed
    if finished_at < started_at:
        errors.append("verification receipt timing is reversed")
    if finished_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        errors.append("verification receipt timing is in the future")
    window_ms = max(0.0, (finished_at - started_at).total_seconds() * 1000)
    gates = receipt.get("gates")
    if isinstance(gates, list):
        for gate in gates:
            elapsed = gate.get("elapsedMs") if isinstance(gate, dict) else None
            if isinstance(elapsed, bool) or not isinstance(elapsed, (int, float)) or elapsed < 0:
                errors.append("verification receipt gate elapsedMs must be non-negative")
            elif elapsed > window_ms + 1000:
                errors.append("verification receipt gate elapsedMs exceeds receipt timing window")
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


def _trusted_replay(
    worktree: Path,
    node: PlanNode,
    receipt: dict[str, Any],
    *,
    passed: bool,
) -> tuple[list[str], dict[str, Any] | None]:
    relevant_entries = receipt.get("relevant_inputs")
    environment_keys = receipt.get("environment_keys")
    verifier_id = receipt.get("verifier_id")
    if (
        not TRUSTED_GATE_RUNNER.is_file()
        or not isinstance(relevant_entries, list)
        or not isinstance(environment_keys, list)
        or not isinstance(verifier_id, str)
    ):
        return ["verification receipt cannot be replayed by the trusted gate runner"], None

    command = [
        "node", str(TRUSTED_GATE_RUNNER), "--json", "--cwd", str(worktree),
        "--plan-id", str(receipt.get("plan_id", "")),
        "--node-id", node.id,
        "--worker-id", node.worker_id,
        "--verifier-id", TRUSTED_VERIFIER_ID,
    ]
    for key in environment_keys:
        command.extend(("--env", key))
    for item in relevant_entries:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            return ["verification receipt cannot be replayed by the trusted gate runner"], None
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
        return ["verification receipt trusted gate replay failed"], None

    expected_returncode = 0 if passed else 1
    if replay.returncode != expected_returncode:
        return ["verification receipt does not reproduce under trusted gate runner"], None
    try:
        reproduced = json.loads(replay.stdout)
    except json.JSONDecodeError:
        return ["verification receipt trusted gate replay returned invalid JSON"], None
    if not isinstance(reproduced, dict) or _replay_evidence(receipt) != _replay_evidence(reproduced):
        return ["verification receipt does not reproduce under trusted gate runner"], None
    reproduced["verification_authority"] = TRUSTED_VERIFICATION_AUTHORITY
    return [], reproduced


def _runtime_receipt_errors(
    plan_worktree: str,
    node: PlanNode,
    receipt: dict[str, Any],
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
                    stored=True,
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


def _node_dispatch_contract_digest(plan: UnlazyPlan, node: PlanNode) -> str:
    """Bind dispatch authority to immutable plan and leaf contract fields."""
    payload = {
        "plan_id": plan.plan_id,
        "task": plan.task,
        "base_sha": plan.base_sha,
        "worktree": plan.worktree,
        "node": {
            "id": node.id,
            "type": node.type,
            "purpose": node.purpose,
            "owns": list(node.owns),
            "needs": list(node.needs),
            "exports": list(node.exports),
            "route_ref": node.route_ref,
            "worker_id": node.worker_id,
            "gates": node.gates,
        },
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return "sha256:" + hashlib.sha256(encoded).hexdigest()


def _dispatch_receipt_errors(
    plan: UnlazyPlan,
    node: PlanNode,
    receipt: dict[str, Any] | None,
    route_decision: Any,
) -> list[str]:
    if not isinstance(receipt, dict):
        return [f"active node {node.id} lacks a scheduler dispatch receipt"]
    errors: list[str] = []
    expected = {
        "schema_version": "1.0",
        "authority": TRUSTED_DISPATCH_AUTHORITY,
        "plan_id": plan.plan_id,
        "node_id": node.id,
        "worker_id": node.worker_id,
        "route_id": route_decision.route_id,
        "policy_version": route_decision.policy_version,
        "base_sha": plan.base_sha,
        "worktree": plan.worktree,
        "node_contract_digest": _node_dispatch_contract_digest(plan, node),
    }
    for name, value in expected.items():
        if receipt.get(name) != value:
            errors.append(f"active node {node.id} dispatch receipt {name} is invalid")
    worker_context_id = receipt.get("worker_context_id")
    if not isinstance(worker_context_id, str) or not worker_context_id.strip():
        errors.append(f"active node {node.id} dispatch receipt worker_context_id is invalid")
    if receipt.get("reserved") is not True:
        errors.append(f"active node {node.id} dispatch receipt is not reserved")
    key = _receipt_hmac_key()
    if key is None:
        errors.append("UNLAZY_RECEIPT_HMAC_KEY must contain at least 32 bytes")
    else:
        supplied = receipt.get("authority_mac")
        if not isinstance(supplied, str) or not hmac.compare_digest(
            supplied, _receipt_mac(receipt, key),
        ):
            errors.append(f"active node {node.id} dispatch receipt authority_mac is invalid")
    return errors


def _trusted_active_nodes(
    plan: UnlazyPlan,
    route_decision: Any,
) -> tuple[PlanNode, ...]:
    active = tuple(node for node in plan.nodes if node.state in {"running", "verifying"})
    errors = [
        error
        for node in active
        for error in _dispatch_receipt_errors(plan, node, node.dispatch_receipt, route_decision)
    ]
    if errors:
        raise PlanValidationError(errors)
    return active


def _bound_route_decision(plan: UnlazyPlan, routing_request: dict[str, Any]) -> Any:
    """Recompute routing only after binding the request to the exact plan task."""
    if not isinstance(routing_request, dict) or routing_request.get("task") != plan.task:
        raise PlanValidationError(["routing request task does not match the Unlazy plan task"])
    return decide_route(routing_request)


def _ready_for_trusted_dispatch(
    plan: UnlazyPlan,
    active: Iterable[PlanNode],
    *,
    cap: int,
) -> tuple[PlanNode, ...]:
    by_id = plan.by_id
    trusted_active = tuple(active)
    slots = max(0, cap - len(trusted_active))
    selected: list[PlanNode] = []
    for node in sorted(plan.nodes, key=lambda item: item.id):
        if slots == 0:
            break
        if node.type != "leaf" or node.state not in {"pending", "ready"}:
            continue
        if not all(by_id[dependency].state == "passed" for dependency in node.needs):
            continue
        if _node_collides(node, (*trusted_active, *selected)):
            continue
        selected.append(node)
        slots -= 1
    return tuple(selected)


def guard_root_continuation(
    raw: dict[str, Any] | UnlazyPlan,
    routing_request: dict[str, Any],
    operation: str,
) -> dict[str, Any]:
    """Fail closed when a fanout route still requires root orchestration.

    Active work is derived only from authenticated scheduler reservations stored on
    running/verifying nodes.  There is deliberately no caller-supplied ``active_ids``
    escape hatch.
    """
    plan = raw if isinstance(raw, UnlazyPlan) else validate_plan(raw)
    route_decision = _bound_route_decision(plan, routing_request)
    active = _trusted_active_nodes(plan, route_decision)
    route_cap = int(route_decision.execution.get("max_parallel_workers", 1))
    cap = min(plan.max_parallel_workers, route_cap)
    ready = _ready_for_trusted_dispatch(plan, active, cap=cap)
    unresolved = tuple(
        node.id
        for node in plan.nodes
        if node.type == "leaf" and node.state in {"pending", "ready", "running", "verifying"}
    )
    fanout_in_flight = route_decision.action == "fanout" and bool(unresolved)
    normalized_operation = str(operation or "").strip().lower()
    if fanout_in_flight and normalized_operation not in FANOUT_CONTROL_OPERATIONS:
        ready_ids = [node.id for node in ready]
        active_ids = [node.id for node in active]
        raise PlanValidationError([
            "fanout-required: root continuation is limited to dispatch/wait/verify/cancel "
            f"while leaf work remains; ready={ready_ids}, active={active_ids}, cap={cap}"
        ])
    return {
        "status": "admitted",
        "operation": normalized_operation,
        "route_id": route_decision.route_id,
        "route_action": route_decision.action,
        "fanout_in_flight": fanout_in_flight,
        "ready": [node.id for node in ready],
        "active": [node.id for node in active],
        "capacity": max(0, cap - len(active)),
    }


def reserve_dispatch(
    raw: dict[str, Any],
    routing_request: dict[str, Any],
    node_id: str,
    *,
    worker_context_id: str,
) -> dict[str, Any]:
    """Atomically reserve one ready leaf and issue scheduler-authenticated authority."""
    plan = validate_plan(raw)
    route_decision = _bound_route_decision(plan, routing_request)
    if route_decision.action not in {"delegate", "fanout"}:
        raise PlanValidationError([
            f"route action {route_decision.action} does not authorize worker dispatch"
        ])
    active = _trusted_active_nodes(plan, route_decision)
    route_cap = int(route_decision.execution.get("max_parallel_workers", 1))
    cap = min(plan.max_parallel_workers, route_cap)
    ready = _ready_for_trusted_dispatch(plan, active, cap=cap)
    selected = next((node for node in ready if node.id == node_id), None)
    if selected is None:
        raise PlanValidationError([f"node {node_id} is not available for trusted dispatch"])
    context = str(worker_context_id or "").strip()
    if not context:
        raise PlanValidationError(["worker_context_id is required"])
    key = _receipt_hmac_key()
    if key is None:
        raise PlanValidationError(["UNLAZY_RECEIPT_HMAC_KEY must contain at least 32 bytes"])
    receipt: dict[str, Any] = {
        "schema_version": "1.0",
        "authority": TRUSTED_DISPATCH_AUTHORITY,
        "plan_id": plan.plan_id,
        "node_id": selected.id,
        "worker_id": selected.worker_id,
        "worker_context_id": context,
        "route_id": route_decision.route_id,
        "policy_version": route_decision.policy_version,
        "base_sha": plan.base_sha,
        "worktree": plan.worktree,
        "node_contract_digest": _node_dispatch_contract_digest(plan, selected),
        "reserved": True,
    }
    receipt["authority_mac"] = _receipt_mac(receipt, key)
    updated = copy.deepcopy(raw)
    for entry in updated["nodes"]:
        if entry.get("id") == node_id:
            entry["state"] = "running"
            entry["dispatch_receipt"] = receipt
            break
    validate_plan(updated)
    return updated


def begin_verification(
    raw: dict[str, Any],
    routing_request: dict[str, Any],
    node_id: str,
) -> dict[str, Any]:
    """Move one authenticated running leaf into scheduler-controlled verification."""
    plan = validate_plan(raw)
    route_decision = _bound_route_decision(plan, routing_request)
    active = _trusted_active_nodes(plan, route_decision)
    node = next((candidate for candidate in active if candidate.id == node_id), None)
    if node is None or node.state != "running":
        raise PlanValidationError([f"node {node_id} must be an authenticated running leaf"])
    updated = copy.deepcopy(raw)
    for entry in updated["nodes"]:
        if entry.get("id") == node_id:
            entry["state"] = "verifying"
            break
    validate_plan(updated)
    return updated


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
    execution_controls: dict[str, Any] | None = None,
    usage: dict[str, Any] | None = None,
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
        runtime=True,
    )
    if receipt_errors:
        raise PlanValidationError(receipt_errors)
    metadata_errors = _execution_metadata_errors(node, execution_controls, usage)
    if metadata_errors:
        raise PlanValidationError(metadata_errors)
    replay_errors, trusted_receipt = _trusted_replay(
        Path(plan.worktree).resolve(), node, verification_receipt, passed=passed,
    )
    if replay_errors or trusted_receipt is None:
        raise PlanValidationError(replay_errors or ["trusted gate replay did not issue a receipt"])
    key = _receipt_hmac_key()
    if key is None:
        raise PlanValidationError(["UNLAZY_RECEIPT_HMAC_KEY must contain at least 32 bytes"])
    trusted_receipt["execution_controls"] = copy.deepcopy(execution_controls)
    trusted_receipt["usage"] = copy.deepcopy(usage)
    trusted_receipt["authority_mac"] = _receipt_mac(trusted_receipt, key)
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
            entry["verification_receipt"] = copy.deepcopy(trusted_receipt)
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
