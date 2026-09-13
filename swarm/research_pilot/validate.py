"""Reject research-pilot requests that violate the RA-7522 contract."""

from __future__ import annotations

from typing import Any

from .contract import (
    MAX_RESEARCH_NODES,
    MIN_RESEARCH_NODES,
    REASON_CAPS,
    REASON_EVIDENCE,
    REASON_NODE_COUNT,
    REASON_OVERLAP,
    WRITE_LANE_ADMITTED,
    WRITE_LANE_GATE,
    PilotContractError,
    PilotPlan,
    evidence_digest,
)
from .parse import parse_plan


def validate_pilot(raw: dict[str, Any] | object) -> PilotPlan:
    """Parse and reject every listed bad case. Pure — no I/O, no dispatch."""
    plan = parse_plan(raw)
    _reject_node_count(plan)
    _reject_overlap(plan)
    _reject_caps(plan)
    _reject_verifier_identity(plan)
    _reject_evidence(plan)
    if WRITE_LANE_ADMITTED:
        raise PilotContractError(WRITE_LANE_GATE, WRITE_LANE_GATE)
    return plan


def _reject_node_count(plan: PilotPlan) -> None:
    count = len(plan.nodes)
    if not MIN_RESEARCH_NODES <= count <= MAX_RESEARCH_NODES:
        raise PilotContractError(
            REASON_NODE_COUNT,
            f"research nodes must be {MIN_RESEARCH_NODES} or {MAX_RESEARCH_NODES}, got {count}",
        )
    ids = [node.node_id for node in plan.nodes]
    if len(set(ids)) != len(ids):
        raise PilotContractError(REASON_OVERLAP, "node ids must be unique")


def _reject_overlap(plan: PilotPlan) -> None:
    owned: list[tuple[str, str]] = []
    for node in plan.nodes:
        for path in node.owns:
            for other_id, other_path in owned:
                if other_id == node.node_id:
                    continue
                if _paths_overlap(path, other_path):
                    raise PilotContractError(
                        REASON_OVERLAP,
                        f"{node.node_id} owns {path!r} which overlaps {other_id}:{other_path!r}",
                    )
            owned.append((node.node_id, path))


def _paths_overlap(left: str, right: str) -> bool:
    return left == right or left.startswith(right + "/") or right.startswith(left + "/")


def _reject_caps(plan: PilotPlan) -> None:
    if plan.usage.tokens > plan.budget.max_tokens:
        raise PilotContractError(REASON_CAPS, "usage.tokens exceeds budget.max_tokens")
    if plan.usage.seconds > plan.budget.max_seconds:
        raise PilotContractError(REASON_CAPS, "usage.seconds exceeds budget.max_seconds")
    if plan.capabilities.mutations is not False:
        raise PilotContractError(REASON_CAPS, "mutations=false is hard")


def _reject_verifier_identity(plan: PilotPlan) -> None:
    workers = {node.worker_id for node in plan.nodes}
    if plan.verifier in workers:
        raise PilotContractError(REASON_CAPS, "verifier must be distinct from every worker_id")


def _reject_evidence(plan: PilotPlan) -> None:
    evidence = plan.evidence
    expected = evidence_digest(
        plan_id=plan.plan_id,
        source_state=plan.source_state,
        verifier=plan.verifier,
        handoff_id=evidence.handoff_id,
    )
    mismatches = [
        evidence.plan_id != plan.plan_id,
        evidence.source_state != plan.source_state,
        evidence.verifier != plan.verifier,
        evidence.digest != expected,
    ]
    if any(mismatches):
        raise PilotContractError(REASON_EVIDENCE, "evidence does not bind this plan")
