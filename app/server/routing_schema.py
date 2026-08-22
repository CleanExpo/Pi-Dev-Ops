"""Provider-neutral contracts for deterministic task routing.

These contracts describe capability floors and execution constraints only.  Concrete
provider/model resolution remains owned by :mod:`app.server.provider_router`.
"""
from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


TaskClass = Literal["mechanical", "bounded", "deep", "high_stakes", "long_horizon"]
WorkerRole = Literal["driver", "senior", "worker", "verifier"]
QualityFloor = Literal["cheap", "mid", "top"]
ExecutionLocation = Literal["local_only", "remote_allowed"]
RouteAction = Literal["inline", "delegate", "fanout", "bailout"]

HARNESSES = {"claude-code", "codex", "vscode-openrouter"}
DETERMINISM = {"high", "medium", "low"}
AMBIGUITY = {"low", "medium", "high"}
SCOPES = {"inline", "bounded", "multi-file", "subsystem", "project"}
REASONING_DEPTH = {"shallow", "normal", "deep"}
SENSITIVITY = {"public", "internal", "confidential", "client"}
QUALITY_FLOORS = {"cheap", "mid", "top"}
STAKES = {
    "none", "customer", "auth", "payment", "privacy", "security",
    "legal", "release", "migration",
}


class RoutingValidationError(ValueError):
    """Raised when a routing request cannot be trusted."""


def _choice(value: Any, allowed: set[str], field_name: str) -> str:
    text = str(value or "")
    if text not in allowed:
        raise RoutingValidationError(
            f"{field_name} must be one of {sorted(allowed)}; got {text!r}"
        )
    return text


def _non_negative_int(value: Any, field_name: str) -> int:
    # Only a genuine int is an integer here. Coercing via int() truncated
    # fractional values (0.9 -> 0), which silently suppressed monotonic
    # failure escalation, and accepted numeric strings the contract rejects.
    if isinstance(value, bool) or not isinstance(value, int):
        raise RoutingValidationError(f"{field_name} must be an integer")
    if value < 0:
        raise RoutingValidationError(f"{field_name} must be non-negative")
    return value


def _boolean(value: Any, field_name: str) -> bool:
    if type(value) is not bool:
        raise RoutingValidationError(f"{field_name} must be a boolean")
    return value


@dataclass(frozen=True)
class RoutingSignals:
    determinism: str
    ambiguity: str
    scope: str
    dependency_count: int
    reasoning_depth: str
    stakes: tuple[str, ...]
    volume: int
    expected_minutes: int
    context_tokens_estimate: int
    modalities: tuple[str, ...]
    required_tools: tuple[str, ...]
    sensitivity: str
    prior_failures: int
    ownership_disjoint: bool

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RoutingSignals":
        stakes = tuple(str(item) for item in raw.get("stakes", ["none"]))
        unknown_stakes = sorted(set(stakes) - STAKES)
        if unknown_stakes:
            raise RoutingValidationError(f"signals.stakes has unknown values: {unknown_stakes}")
        return cls(
            determinism=_choice(raw.get("determinism"), DETERMINISM, "signals.determinism"),
            ambiguity=_choice(raw.get("ambiguity"), AMBIGUITY, "signals.ambiguity"),
            scope=_choice(raw.get("scope"), SCOPES, "signals.scope"),
            dependency_count=_non_negative_int(raw.get("dependency_count", 0), "signals.dependency_count"),
            reasoning_depth=_choice(raw.get("reasoning_depth"), REASONING_DEPTH, "signals.reasoning_depth"),
            stakes=stakes,
            volume=max(1, _non_negative_int(raw.get("volume", 1), "signals.volume")),
            expected_minutes=_non_negative_int(raw.get("expected_minutes", 0), "signals.expected_minutes"),
            context_tokens_estimate=_non_negative_int(
                raw.get("context_tokens_estimate", 0), "signals.context_tokens_estimate"
            ),
            modalities=tuple(str(item) for item in raw.get("modalities", ["text"])),
            required_tools=tuple(str(item) for item in raw.get("required_tools", [])),
            sensitivity=_choice(raw.get("sensitivity"), SENSITIVITY, "signals.sensitivity"),
            prior_failures=_non_negative_int(raw.get("prior_failures", 0), "signals.prior_failures"),
            ownership_disjoint=_boolean(
                raw.get("ownership_disjoint", False), "signals.ownership_disjoint"
            ),
        )


@dataclass(frozen=True)
class RoutingLimits:
    max_cost_usd: float | None
    max_quota_units: float | None
    deadline_seconds: int
    max_parallel_workers: int

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RoutingLimits":
        def optional_number(name: str) -> float | None:
            value = raw.get(name)
            if value is None:
                return None
            if isinstance(value, bool):
                raise RoutingValidationError(f"limits.{name} must be numeric or null")
            try:
                parsed = float(value)
            except (TypeError, ValueError) as exc:
                raise RoutingValidationError(f"limits.{name} must be numeric or null") from exc
            if not math.isfinite(parsed):
                raise RoutingValidationError(f"limits.{name} must be finite")
            if parsed < 0:
                raise RoutingValidationError(f"limits.{name} must be non-negative")
            return parsed

        workers = _non_negative_int(raw.get("max_parallel_workers", 1), "limits.max_parallel_workers")
        if not 1 <= workers <= 16:
            raise RoutingValidationError("limits.max_parallel_workers must be between 1 and 16")
        return cls(
            max_cost_usd=optional_number("max_cost_usd"),
            max_quota_units=optional_number("max_quota_units"),
            deadline_seconds=_non_negative_int(raw.get("deadline_seconds", 0), "limits.deadline_seconds"),
            max_parallel_workers=workers,
        )


@dataclass(frozen=True)
class HarnessCapabilities:
    local_quality_floors: tuple[str, ...] = field(default_factory=tuple)
    supports_parallel: bool = False
    supports_model_override: bool = False
    supports_cancellation: bool = False

    @classmethod
    def from_dict(cls, raw: dict[str, Any] | None) -> "HarnessCapabilities":
        raw = raw or {}
        floors = tuple(str(item) for item in raw.get("local_quality_floors", []))
        unknown = sorted(set(floors) - QUALITY_FLOORS)
        if unknown:
            raise RoutingValidationError(f"capabilities.local_quality_floors has unknown values: {unknown}")
        return cls(
            local_quality_floors=floors,
            supports_parallel=_boolean(
                raw.get("supports_parallel", False), "capabilities.supports_parallel"
            ),
            supports_model_override=_boolean(
                raw.get("supports_model_override", False),
                "capabilities.supports_model_override",
            ),
            supports_cancellation=_boolean(
                raw.get("supports_cancellation", False),
                "capabilities.supports_cancellation",
            ),
        )


@dataclass(frozen=True)
class RoutingRequest:
    schema_version: str
    request_id: str
    task: str
    harness: str
    signals: RoutingSignals
    limits: RoutingLimits
    capabilities: HarnessCapabilities

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> "RoutingRequest":
        if raw.get("schema_version") != "1.0":
            raise RoutingValidationError("schema_version must be '1.0'")
        request_id = str(raw.get("request_id") or "").strip()
        task = str(raw.get("task") or "").strip()
        if not request_id or not task:
            raise RoutingValidationError("request_id and task are required")
        signals = raw.get("signals")
        limits = raw.get("limits")
        if not isinstance(signals, dict) or not isinstance(limits, dict):
            raise RoutingValidationError("signals and limits must be objects")
        return cls(
            schema_version="1.0",
            request_id=request_id,
            task=task,
            harness=_choice(raw.get("harness"), HARNESSES, "harness"),
            signals=RoutingSignals.from_dict(signals),
            limits=RoutingLimits.from_dict(limits),
            capabilities=HarnessCapabilities.from_dict(raw.get("capabilities")),
        )


@dataclass(frozen=True)
class RouteDecision:
    schema_version: str
    route_id: str
    policy_version: str
    action: RouteAction
    task_class: TaskClass
    worker_role: WorkerRole
    quality_floor: QualityFloor
    execution_location: ExecutionLocation
    reasoning_effort: Literal["low", "medium", "high", "xhigh"]
    confidence: float
    reasons: tuple[str, ...]
    privacy: dict[str, Any]
    execution: dict[str, Any]
    budget: dict[str, Any]
    verifier: dict[str, Any]
    escalation_on: tuple[str, ...]
    fallback: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
