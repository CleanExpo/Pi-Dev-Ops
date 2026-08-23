"""Attempt-path binding, freshness, and uncertainty-case validation."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from senior_harness_core import (
    attempt_fingerprint,
    bind_attempt,
    parse_timestamp,
    require_mapping,
    require_nonempty,
)


FAILURE_STATUSES = {"failed", "runner-error", "blocked", "timed-out"}
ATTEMPT_STATUSES = {
    "planned", "active", "passed", "failed", "runner-error", "blocked",
    "timed-out", "cancelled",
}
ATTEMPT_FIELDS = (
    "route_id", "input_sha256", "problem_id", "hypothesis", "method", "tool_path",
    "source_set", "model_class", "status", "started_at", "last_authoritative_evidence_at",
)
CASE_FIELDS = (
    "problem_id", "status", "stop_current_path", "specialist_ids", "arbiter_id",
    "evidence_ids", "experiment", "resolution_criterion",
)


@dataclass
class AttemptSummary:
    seen: set[str] = field(default_factory=set)
    failures: Counter[str] = field(default_factory=Counter)
    stale_problems: set[str] = field(default_factory=set)


def _validate_attempt_shape(attempt: dict[str, Any], index: int, errors: list[str]) -> None:
    for name in ATTEMPT_FIELDS:
        require_nonempty(attempt.get(name), f"attempts[{index}].{name}", errors)
    input_sha = attempt.get("input_sha256")
    if (
        not isinstance(input_sha, str)
        or not input_sha.startswith("sha256:")
        or len(input_sha) != 71
        or any(character not in "0123456789abcdef" for character in input_sha[7:])
    ):
        errors.append(f"attempts[{index}].input_sha256 must be a canonical sha256 digest")
    sources = attempt.get("source_set")
    if not isinstance(sources, list):
        errors.append(f"attempts[{index}].source_set must be a list")
    elif any(not isinstance(item, str) or not item for item in sources):
        errors.append(f"attempts[{index}].source_set must contain non-empty strings")
    evidence_delta = attempt.get("new_authoritative_evidence_ids")
    if not isinstance(evidence_delta, list) or any(not isinstance(item, str) or not item for item in evidence_delta):
        errors.append(f"attempts[{index}].new_authoritative_evidence_ids must be a list of evidence ids")
    if attempt.get("status") not in ATTEMPT_STATUSES:
        errors.append(f"attempts[{index}].status is invalid")


def _validate_attempt_times(attempt: dict[str, Any], index: int, observed_at: datetime | None, errors: list[str]) -> tuple[datetime | None, datetime | None]:
    started_at = parse_timestamp(attempt.get("started_at"), f"attempts[{index}].started_at", errors)
    last_evidence = parse_timestamp(
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
    return started_at, last_evidence


def _validate_attempt_binding(contract: dict[str, Any], attempt: dict[str, Any], index: int, errors: list[str]) -> None:
    expected_binding = bind_attempt(contract, attempt)
    if attempt.get("input_sha256") != expected_binding["input_sha256"]:
        errors.append(f"attempts[{index}].input_sha256 is not bound to the frozen task")
    if attempt.get("route_id") != expected_binding["route_id"]:
        errors.append(f"attempts[{index}].route_id is not bound to the frozen route handle")


def _record_fingerprint(attempt: dict[str, Any], index: int, summary: AttemptSummary, errors: list[str]) -> None:
    supplied = attempt.get("fingerprint")
    if supplied != attempt_fingerprint(attempt):
        errors.append(f"attempts[{index}].fingerprint does not match its pathway")
    if isinstance(supplied, str) and supplied in summary.seen:
        errors.append(f"attempts[{index}] repeats an already attempted pathway")
    if isinstance(supplied, str) and supplied:
        summary.seen.add(supplied)
    problem_id = attempt.get("problem_id")
    if attempt.get("status") in FAILURE_STATUSES and isinstance(problem_id, str):
        summary.failures[problem_id] += 1


def _record_staleness(attempt: dict[str, Any], observed_at: datetime | None, last_evidence: datetime | None, max_minutes: Any, summary: AttemptSummary) -> None:
    problem_id = attempt.get("problem_id")
    stale = (
        observed_at
        and last_evidence
        and isinstance(max_minutes, (int, float))
        and not isinstance(max_minutes, bool)
        and attempt.get("status") not in {"passed", "cancelled"}
        and (observed_at - last_evidence).total_seconds() > max_minutes * 60
        and isinstance(problem_id, str)
    )
    if stale:
        summary.stale_problems.add(problem_id)


def _inspect_attempt(contract: dict[str, Any], raw: Any, index: int, observed_at: datetime | None, max_minutes: Any, summary: AttemptSummary, errors: list[str]) -> None:
    attempt = require_mapping(raw, f"attempts[{index}]", errors)
    _validate_attempt_shape(attempt, index, errors)
    _, last_evidence = _validate_attempt_times(attempt, index, observed_at, errors)
    _validate_attempt_binding(contract, attempt, index, errors)
    _record_staleness(attempt, observed_at, last_evidence, max_minutes, summary)
    _record_fingerprint(attempt, index, summary, errors)


def _validate_case(raw: Any, index: int, errors: list[str]) -> str | None:
    case = require_mapping(raw, f"uncertainty_cases[{index}]", errors)
    for name in CASE_FIELDS:
        require_nonempty(case.get(name), f"uncertainty_cases[{index}].{name}", errors)
    specialists = case.get("specialist_ids")
    if not isinstance(specialists, list) or any(not isinstance(item, str) for item in specialists):
        errors.append(f"uncertainty_cases[{index}].specialist_ids must be a list of strings")
        return None
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
    valid_open = (
        isinstance(case.get("problem_id"), str)
        and case.get("status") == "open"
        and case.get("stop_current_path") is True
        and len(unique_specialists) >= 2
        and isinstance(arbiter_id, str)
        and arbiter_id not in unique_specialists
        and isinstance(evidence_ids, list)
        and bool(evidence_ids)
    )
    return case["problem_id"] if valid_open else None


def _validate_cases(contract: dict[str, Any], summary: AttemptSummary, errors: list[str]) -> None:
    cases = contract.get("uncertainty_cases", [])
    if not isinstance(cases, list):
        errors.append("uncertainty_cases must be a list")
        return
    open_problems = {
        problem_id for index, raw in enumerate(cases)
        if (problem_id := _validate_case(raw, index, errors)) is not None
    }
    for problem_id, count in summary.failures.items():
        if count >= 2 and problem_id not in open_problems:
            errors.append(f"problem {problem_id} requires an open independent uncertainty case after two failures")
    for problem_id in summary.stale_problems:
        if problem_id not in open_problems:
            errors.append(f"problem {problem_id} requires an open uncertainty case after evidence freshness expired")


def validate_attempts(contract: dict[str, Any], errors: list[str]) -> None:
    limits = require_mapping(contract.get("limits"), "limits", errors)
    max_attempts = limits.get("max_same_path_attempts")
    max_minutes = limits.get("max_minutes_without_new_authoritative_evidence")
    if max_attempts != 2:
        errors.append("limits.max_same_path_attempts must be 2")
    if isinstance(max_minutes, bool) or not isinstance(max_minutes, (int, float)) or not 0 < max_minutes <= 5:
        errors.append("limits.max_minutes_without_new_authoritative_evidence must be between 0 and 5")
    observed_at = parse_timestamp(contract.get("observed_at"), "observed_at", errors)
    attempts = contract.get("attempts", [])
    if not isinstance(attempts, list):
        errors.append("attempts must be a list")
        return
    summary = AttemptSummary()
    for index, raw in enumerate(attempts):
        _inspect_attempt(contract, raw, index, observed_at, max_minutes, summary, errors)
    _validate_cases(contract, summary, errors)
