"""Deterministic, provider-neutral policy for model-router decisions."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from app.server import routing_schema as routing_schema_module
from app.server.routing_schema import RouteDecision, RoutingRequest, RoutingValidationError


POLICY_VERSION = "nexus-task-routing-v2"
HIGH_STAKES = {"auth", "payment", "privacy", "security", "legal", "release", "migration"}
QUALITY_ORDER = ("cheap", "mid", "top")
EFFORT_ORDER = ("low", "medium", "high", "xhigh")


def _stable_route_id(request: RoutingRequest) -> str:
    payload = {
        "policy": _policy_digest(),
        "request_id": request.request_id,
        "task": request.task,
        "harness": request.harness,
        "signals": request.signals.__dict__,
        "limits": request.limits.__dict__,
        "capabilities": request.capabilities.__dict__,
    }
    digest = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=list)
    return str(uuid.uuid5(uuid.NAMESPACE_URL, digest))


def _policy_digest() -> str:
    """Bind receipts to all executable router and validation source semantics."""
    source_paths = (
        Path(__file__).resolve(),
        Path(routing_schema_module.__file__).resolve(),
    )
    digest = hashlib.sha256()
    for path in sorted(source_paths, key=lambda item: item.name):
        digest.update(path.name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "sha256:" + digest.hexdigest()


def _classify_task(signals: Any) -> tuple[tuple[str, str, str, str, bool], set[str], list[str]]:
    stake_set = set(signals.stakes) - {"none"}
    high_stakes = bool(stake_set & HIGH_STAKES)
    if high_stakes:
        profile = ("high_stakes", "senior", "top", "xhigh", True)
        return profile, stake_set, ["high-stakes-floor"]
    if signals.reasoning_depth == "deep":
        profile = ("deep", "senior", "top", "high", False)
        return profile, stake_set, ["deep-reasoning"]
    if signals.scope in {"subsystem", "project"} or signals.expected_minutes >= 180:
        profile = ("long_horizon", "driver", "top", "high", False)
        return profile, stake_set, ["long-horizon"]
    if signals.determinism == "high" and signals.reasoning_depth == "shallow":
        profile = ("mechanical", "worker", "cheap", "low", False)
        return profile, stake_set, ["deterministic-mechanical"]
    role = "worker" if signals.ambiguity != "high" else "senior"
    effort = "medium" if role == "worker" else "high"
    return ("bounded", role, "mid", effort, False), stake_set, ["bounded-production"]


def _apply_failure_escalation(
    profile: tuple[str, str, str, str, bool], prior_failures: int,
    failure_feedback: tuple[str, ...],
) -> tuple[tuple[str, str, str, str, bool], bool, list[str]]:
    if not prior_failures:
        return profile, False, []
    if not failure_feedback:
        return profile, True, ["failure-feedback-missing"]
    task_class, role, floor, effort, high_stakes = profile
    escalation_steps = max(0, prior_failures - 1)
    if not escalation_steps:
        return profile, False, ["same-floor-retry-with-gate-feedback"]
    target_rank = QUALITY_ORDER.index(floor) + escalation_steps
    exhausted = target_rank >= len(QUALITY_ORDER)
    floor = QUALITY_ORDER[min(target_rank, len(QUALITY_ORDER) - 1)]
    minimum_effort = "high" if floor != "cheap" else effort
    if EFFORT_ORDER.index(effort) < EFFORT_ORDER.index(minimum_effort):
        effort = minimum_effort
    reasons = ["monotonic-failure-escalation"]
    if exhausted:
        reasons.append("failure-escalation-exhausted")
    return (task_class, role, floor, effort, high_stakes), exhausted, reasons


def _base_action(
    request: RoutingRequest, floor: str, stake_set: set[str], exhausted: bool
) -> tuple[str, list[str]]:
    signals = request.signals
    local_only = signals.sensitivity in {"confidential", "client"}
    local_floors = set(request.capabilities.local_quality_floors)
    required_rank = QUALITY_ORDER.index(floor)
    has_local_floor = any(QUALITY_ORDER.index(item) >= required_rank for item in local_floors)
    if exhausted:
        return "bailout", []
    if local_only and not has_local_floor:
        return "bailout", ["no-local-capability-at-required-floor"]
    trivial_inline = (
        signals.scope == "inline" and signals.expected_minutes <= 10
        and signals.volume == 1 and not stake_set
        and signals.ambiguity == "low" and floor != "top"
    )
    parallel_work = (
        request.limits.max_parallel_workers > 1
        and request.capabilities.supports_parallel and signals.ownership_disjoint
        and signals.volume >= 2 and signals.scope in {"multi-file", "subsystem", "project"}
    )
    if trivial_inline:
        return "inline", ["delegation-overhead-exceeds-benefit"]
    if parallel_work:
        return "fanout", ["disjoint-ready-work"]
    reasons = (
        ["harness-parallelism-unavailable"]
        if signals.volume >= 2 and not request.capabilities.supports_parallel
        else []
    )
    return "delegate", reasons


def _apply_dispatch_limits(action: str, request: RoutingRequest) -> tuple[str, list[str]]:
    if action not in {"delegate", "fanout"}:
        return action, []
    zero_limits = (
        ("zero-cost-budget", request.limits.max_cost_usd == 0),
        ("zero-quota-budget", request.limits.max_quota_units == 0),
        ("zero-deadline", request.limits.deadline_seconds == 0),
    )
    blocked_reasons = [reason for reason, blocked in zero_limits if blocked]
    if blocked_reasons:
        return "bailout", blocked_reasons
    if action == "fanout" and not request.capabilities.supports_cancellation:
        return "delegate", ["harness-cancellation-unavailable"]
    return action, []


def _parallel_capacity(action: str, request: RoutingRequest) -> tuple[int, list[str]]:
    signals = request.signals
    reservable = (
        request.capabilities.supports_parallel and request.capabilities.supports_cancellation
        and signals.volume >= 2 and signals.scope in {"multi-file", "subsystem", "project"}
    )
    if action == "fanout":
        return request.limits.max_parallel_workers, []
    if action != "delegate" or not reservable:
        return 1, []
    reason = [] if signals.ownership_disjoint else ["parallel-first-capacity-pending-disjoint-proof"]
    return request.limits.max_parallel_workers, reason


def _build_decision(
    request: RoutingRequest, profile: tuple[str, str, str, str, bool], action: str,
    location: str, max_workers: int, reasons: list[str],
) -> RouteDecision:
    task_class, role, floor, effort, high_stakes = profile
    verifier_floor = "top" if high_stakes or floor == "top" else "mid"
    return RouteDecision(
        schema_version="1.0", route_id=_stable_route_id(request), policy_version=_policy_digest(),
        action=action, task_class=task_class, worker_role=role, quality_floor=floor,  # type: ignore[arg-type]
        execution_location=location, reasoning_effort=effort,  # type: ignore[arg-type]
        confidence=0.99 if action == "bailout" or high_stakes else 0.9,
        reasons=tuple(reasons),
        privacy={
            "data_class": request.signals.sensitivity,
            "provider_constraints": ["local-only"] if location == "local_only" else [],
        },
        execution={
            "max_parallel_workers": max_workers,
            "timeout_seconds": request.limits.deadline_seconds,
            "max_attempts": 2,
            "owns": [],
            "needs": [],
        },
        budget={
            "max_cost_usd": request.limits.max_cost_usd,
            "max_quota_units": request.limits.max_quota_units,
            "reservation_required": action in {"delegate", "fanout"},
        },
        verifier={
            "quality_floor": verifier_floor,
            "reasoning_effort": "xhigh" if verifier_floor == "top" else "high",
            "independent": True,
        },
        escalation_on=("two-failed-attempts", "low-confidence", "contract-drift", "security-signal"),
        fallback=tuple(QUALITY_ORDER[QUALITY_ORDER.index(floor) :]) + ("bailout",),
    )


def decide_route(raw: RoutingRequest | dict[str, Any]) -> RouteDecision:
    """Return one reproducible decision without resolving a provider or model ID."""
    request = raw if isinstance(raw, RoutingRequest) else RoutingRequest.from_dict(raw)
    profile, stake_set, reasons = _classify_task(request.signals)
    profile, exhausted, escalation_reasons = _apply_failure_escalation(
        profile, request.signals.prior_failures, request.signals.failure_feedback
    )
    reasons.extend(escalation_reasons)
    location = (
        "local_only"
        if request.signals.sensitivity in {"confidential", "client"}
        else "remote_allowed"
    )
    if location == "local_only":
        reasons.append("sensitive-data-local-only")
    action, action_reasons = _base_action(request, profile[2], stake_set, exhausted)
    reasons.extend(action_reasons)
    action, limit_reasons = _apply_dispatch_limits(action, request)
    reasons.extend(limit_reasons)
    max_workers, capacity_reasons = _parallel_capacity(action, request)
    reasons.extend(capacity_reasons)
    return _build_decision(request, profile, action, location, max_workers, reasons)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Emit one provider-neutral RouteDecision JSON")
    parser.add_argument("request", nargs="?", help="request JSON file; defaults to stdin")
    args = parser.parse_args(argv)
    try:
        text = Path(args.request).read_text() if args.request else sys.stdin.read()
        decision = decide_route(json.loads(text))
    except (OSError, json.JSONDecodeError, RoutingValidationError) as exc:
        print(json.dumps({"error": str(exc), "status": "invalid_request"}, sort_keys=True), file=sys.stderr)
        return 2
    print(json.dumps(decision.to_dict(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
