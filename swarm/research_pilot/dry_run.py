"""Project a research-pilot plan. Never dispatches and never mutates."""

from __future__ import annotations

from typing import Any

from .contract import (
    MC_STATES,
    PASSED_TRAJECTORY,
    STOP_RULES,
    WRITE_LANE_ADMITTED,
    DryRunReceipt,
    PilotPlan,
)
from .validate import validate_pilot


def dry_run_pilot(raw: dict[str, Any] | object) -> DryRunReceipt:
    """Validate and project Mission Control states without live work.

    Does not import or call agent dispatch, Linear, CRM, git, or production
    clients. ``dispatched`` is always false.
    """
    plan = validate_pilot(raw)
    projected = _project_states(plan)
    return DryRunReceipt(
        plan_id=plan.plan_id,
        dispatched=False,
        mutated=(),
        mutations=False,
        source_state=plan.source_state,
        usage=plan.usage,
        verifier=plan.verifier,
        verifier_result=plan.evidence.verifier_result,
        handoff_id=plan.evidence.handoff_id,
        projected_states=projected,
        final_states={node.node_id: "passed" for node in plan.nodes},
        stop_rules=STOP_RULES,
        operator_stop_rules=_operator_stop_rules(plan),
        billing="max_plan_only",
        write_lane_admitted=WRITE_LANE_ADMITTED,
    )


def _project_states(plan: PilotPlan) -> tuple[dict[str, Any], ...]:
    phases: list[dict[str, Any]] = []
    for state in PASSED_TRAJECTORY:
        if state not in MC_STATES:
            raise RuntimeError(f"projected state {state!r} is not a Mission Control state")
        nodes = {node.node_id: state for node in plan.nodes}
        phases.append({"phase": state, "nodes": nodes})
    return tuple(phases)


def _operator_stop_rules(plan: PilotPlan) -> dict[str, Any]:
    tokens = plan.budget.max_tokens
    seconds = plan.budget.max_seconds
    return {
        "max_tokens": tokens,
        "max_seconds": seconds,
        "reserve_stop_tokens": (tokens * 80) // 100,
        "reserve_stop_seconds": (seconds * 80) // 100,
        "unknown_usage_blocks": True,
        "mutations": False,
        "write_lane_admitted": WRITE_LANE_ADMITTED,
        "billing": "max_plan_only",
        "context": "2-3 disjoint research nodes; verifier is not a worker",
        "rules": list(STOP_RULES),
    }
