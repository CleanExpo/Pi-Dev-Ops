"""Deterministic, provider-neutral policy for model-router decisions."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import uuid
from pathlib import Path
from typing import Any

from app.server.routing_schema import RouteDecision, RoutingRequest, RoutingValidationError


POLICY_VERSION = "nexus-task-routing-v1"
HIGH_STAKES = {"auth", "payment", "privacy", "security", "legal", "release", "migration"}
QUALITY_ORDER = ("cheap", "mid", "top")


def _stable_route_id(request: RoutingRequest) -> str:
    payload = {
        "policy": POLICY_VERSION,
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
    text = f"{POLICY_VERSION}|{sorted(HIGH_STAKES)}|{QUALITY_ORDER}"
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def decide_route(raw: RoutingRequest | dict[str, Any]) -> RouteDecision:
    """Return one reproducible decision without resolving a provider or model ID."""
    request = raw if isinstance(raw, RoutingRequest) else RoutingRequest.from_dict(raw)
    signals = request.signals
    stake_set = set(signals.stakes) - {"none"}
    is_high_stakes = bool(stake_set & HIGH_STAKES)
    local_only = signals.sensitivity in {"confidential", "client"}
    reasons: list[str] = []

    if is_high_stakes:
        task_class = "high_stakes"
        role = "senior"
        floor = "top"
        effort = "xhigh"
        reasons.append("high-stakes-floor")
    elif signals.reasoning_depth == "deep":
        task_class = "deep"
        role = "senior"
        floor = "top"
        effort = "high"
        reasons.append("deep-reasoning")
    elif signals.scope in {"subsystem", "project"} or signals.expected_minutes >= 180:
        task_class = "long_horizon"
        role = "driver"
        floor = "top"
        effort = "high"
        reasons.append("long-horizon")
    elif signals.determinism == "high" and signals.reasoning_depth == "shallow":
        task_class = "mechanical"
        role = "worker"
        floor = "cheap"
        effort = "low"
        reasons.append("deterministic-mechanical")
    else:
        task_class = "bounded"
        role = "worker" if signals.ambiguity != "high" else "senior"
        floor = "mid"
        effort = "medium" if role == "worker" else "high"
        reasons.append("bounded-production")

    if signals.prior_failures:
        current = QUALITY_ORDER.index(floor)
        floor = QUALITY_ORDER[min(current + signals.prior_failures, len(QUALITY_ORDER) - 1)]
        effort = "high" if floor != "cheap" else effort
        reasons.append("monotonic-failure-escalation")

    location = "local_only" if local_only else "remote_allowed"
    if local_only:
        reasons.append("sensitive-data-local-only")

    local_floors = set(request.capabilities.local_quality_floors)
    required_rank = QUALITY_ORDER.index(floor)
    local_contract_missing = local_only and not any(
        QUALITY_ORDER.index(candidate) >= required_rank for candidate in local_floors
    )
    if local_contract_missing:
        action = "bailout"
        reasons.append("no-local-capability-at-required-floor")
    else:
        trivial_inline = (
            signals.scope == "inline"
            and signals.expected_minutes <= 10
            and signals.volume == 1
            and not stake_set
            and signals.ambiguity == "low"
        )
        parallel_work = (
            request.limits.max_parallel_workers > 1
            and request.capabilities.supports_parallel
            and signals.ownership_disjoint
            and signals.volume >= 2
            and signals.scope in {"multi-file", "subsystem", "project"}
        )
        if trivial_inline:
            action = "inline"
            reasons.append("delegation-overhead-exceeds-benefit")
        elif parallel_work:
            action = "fanout"
            reasons.append("disjoint-ready-work")
        else:
            action = "delegate"
            if signals.volume >= 2 and not request.capabilities.supports_parallel:
                reasons.append("harness-parallelism-unavailable")

    verifier_floor = "top" if is_high_stakes or floor == "top" else "mid"
    verifier_effort = "xhigh" if verifier_floor == "top" else "high"
    max_workers = request.limits.max_parallel_workers if action == "fanout" else 1
    fallback = tuple(QUALITY_ORDER[QUALITY_ORDER.index(floor) :]) + ("bailout",)
    confidence = 0.99 if action == "bailout" or is_high_stakes else 0.9

    return RouteDecision(
        schema_version="1.0",
        route_id=_stable_route_id(request),
        policy_version=_policy_digest(),
        action=action,  # type: ignore[arg-type]
        task_class=task_class,  # type: ignore[arg-type]
        worker_role=role,  # type: ignore[arg-type]
        quality_floor=floor,  # type: ignore[arg-type]
        execution_location=location,  # type: ignore[arg-type]
        reasoning_effort=effort,  # type: ignore[arg-type]
        confidence=confidence,
        reasons=tuple(reasons),
        privacy={
            "data_class": signals.sensitivity,
            "provider_constraints": ["local-only"] if local_only else [],
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
            "reasoning_effort": verifier_effort,
            "independent": True,
        },
        escalation_on=(
            "two-failed-attempts", "low-confidence", "contract-drift", "security-signal"
        ),
        fallback=fallback,
    )


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
