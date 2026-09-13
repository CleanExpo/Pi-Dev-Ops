"""Parse a research-pilot request into frozen dataclasses. No I/O."""

from __future__ import annotations

from typing import Any

from .contract import (
    DESTRUCTIVE_TOOLS,
    REASON_CANCEL,
    REASON_CAPS,
    REASON_EVIDENCE,
    REASON_OVERLAP,
    REASON_TOOLS,
    REASON_USAGE,
    REASON_WRITE_LANE,
    RESEARCH_TOOLS,
    SCHEMA_VERSION,
    PilotBudget,
    PilotCapabilities,
    PilotContractError,
    PilotEvidence,
    PilotPlan,
    PilotUsage,
    ResearchNode,
    evidence_digest,
)


def parse_plan(raw: dict[str, Any] | object) -> PilotPlan:
    if not isinstance(raw, dict):
        raise PilotContractError(REASON_CAPS, "plan must be an object")
    if raw.get("schema_version") != SCHEMA_VERSION:
        raise PilotContractError(REASON_CAPS, "schema_version must be '1.0'")
    plan_id = _nonempty(raw.get("plan_id"), "plan_id")
    verifier = _nonempty(raw.get("verifier"), "verifier")
    source_state = _nonempty(raw.get("source_state"), "source_state")
    return PilotPlan(
        plan_id=plan_id,
        task=_nonempty(raw.get("task"), "task"),
        source_state=source_state,
        verifier=verifier,
        nodes=_parse_nodes(raw.get("nodes")),
        budget=_parse_budget(raw.get("budget")),
        capabilities=_parse_capabilities(raw.get("capabilities")),
        usage=_parse_usage(raw.get("usage")),
        evidence=_parse_evidence(raw.get("evidence"), plan_id, source_state, verifier),
    )


def _nonempty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PilotContractError(REASON_CAPS, f"{field_name} is required")
    return value.strip()


def _parse_nodes(raw: object) -> tuple[ResearchNode, ...]:
    if not isinstance(raw, list) or not raw:
        raise PilotContractError(REASON_CAPS, "nodes must be a non-empty list")
    return tuple(_parse_node(item) for item in raw)


def _parse_node(raw: object) -> ResearchNode:
    if not isinstance(raw, dict):
        raise PilotContractError(REASON_CAPS, "node must be an object")
    return ResearchNode(
        node_id=_nonempty(raw.get("id"), "node.id"),
        purpose=_nonempty(raw.get("purpose"), "node.purpose"),
        owns=_parse_owns(raw.get("owns")),
        tools=_parse_tools(raw.get("tools")),
        worker_id=_nonempty(raw.get("worker_id"), "node.worker_id"),
    )


def _parse_owns(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise PilotContractError(REASON_OVERLAP, "node.owns must be a non-empty list")
    owns = tuple(_canonical_own(item) for item in raw)
    if len(set(owns)) != len(owns):
        raise PilotContractError(REASON_OVERLAP, "node.owns has internal duplicates")
    return owns


def _canonical_own(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PilotContractError(REASON_OVERLAP, "ownership path must be a string")
    text = value.strip().replace("\\", "/")
    while text.startswith("./"):
        text = text[2:]
    text = text.rstrip("/")
    parts = text.split("/")
    if not text or text.startswith(("/", "~")):
        raise PilotContractError(REASON_OVERLAP, f"ownership path not relative: {value!r}")
    if ".." in parts or any("*" in part or "?" in part for part in parts):
        raise PilotContractError(REASON_OVERLAP, f"ownership path not canonical: {value!r}")
    return text


def _parse_tools(raw: object) -> tuple[str, ...]:
    if not isinstance(raw, list) or not raw:
        raise PilotContractError(REASON_TOOLS, "node.tools must be a non-empty list")
    tools = tuple(_nonempty_tool(item) for item in raw)
    if any(tool in DESTRUCTIVE_TOOLS or tool not in RESEARCH_TOOLS for tool in tools):
        raise PilotContractError(REASON_TOOLS, f"forbidden or unknown tools: {tools}")
    return tools


def _nonempty_tool(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PilotContractError(REASON_TOOLS, "tool names must be non-empty strings")
    return value.strip()


def _parse_budget(raw: object) -> PilotBudget:
    if not isinstance(raw, dict):
        raise PilotContractError(REASON_CAPS, "budget is required")
    if _positive_cost(raw.get("max_cost_usd")) or _positive_cost(raw.get("max_quota_units")):
        raise PilotContractError(REASON_CAPS, "API credit budgets are not accepted")
    return PilotBudget(
        max_tokens=_positive_int(raw.get("max_tokens"), "budget.max_tokens"),
        max_seconds=_positive_int(raw.get("max_seconds"), "budget.max_seconds"),
    )


def _positive_cost(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise PilotContractError(REASON_CAPS, f"{field_name} must be a positive integer")
    return value


def _parse_capabilities(raw: object) -> PilotCapabilities:
    if not isinstance(raw, dict):
        raise PilotContractError(REASON_CAPS, "capabilities is required")
    mutations = raw.get("mutations")
    if mutations is not False:
        raise PilotContractError(REASON_CAPS, "capabilities.mutations must be false")
    cancellation = raw.get("supports_cancellation")
    if cancellation is not True:
        raise PilotContractError(REASON_CANCEL, "capabilities.supports_cancellation must be true")
    write_lane = raw.get("write_lane", False)
    if write_lane is True:
        raise PilotContractError(REASON_WRITE_LANE, "write lane is not admitted")
    if write_lane is not False:
        raise PilotContractError(REASON_CAPS, "capabilities.write_lane must be a boolean")
    return PilotCapabilities(False, True, False)


def _parse_usage(raw: object) -> PilotUsage:
    if not isinstance(raw, dict):
        raise PilotContractError(REASON_USAGE, "usage is required and must be known")
    if raw.get("status") == "unknown" or raw.get("status") != "known":
        raise PilotContractError(REASON_USAGE, "usage.status must be 'known', not unknown")
    tokens = raw.get("tokens")
    seconds = raw.get("seconds")
    if isinstance(tokens, bool) or not isinstance(tokens, int) or tokens < 0:
        raise PilotContractError(REASON_USAGE, "usage.tokens must be a known non-negative integer")
    if isinstance(seconds, bool) or not isinstance(seconds, int) or seconds < 0:
        raise PilotContractError(REASON_USAGE, "usage.seconds must be a known non-negative integer")
    return PilotUsage("known", tokens, seconds)


def _parse_evidence(
    raw: object, plan_id: str, source_state: str, verifier: str
) -> PilotEvidence:
    if not isinstance(raw, dict):
        raise PilotContractError(REASON_EVIDENCE, "evidence is required")
    handoff_id = raw.get("handoff_id")
    if not isinstance(handoff_id, str) or not handoff_id.strip():
        raise PilotContractError(REASON_EVIDENCE, "evidence.handoff_id is required")
    result = raw.get("verifier_result")
    if not isinstance(result, str) or not result.strip():
        raise PilotContractError(REASON_EVIDENCE, "evidence.verifier_result is required")
    expected = evidence_digest(
        plan_id=plan_id, source_state=source_state, verifier=verifier, handoff_id=handoff_id
    )
    return PilotEvidence(
        plan_id=str(raw.get("plan_id") or ""),
        source_state=str(raw.get("source_state") or ""),
        verifier=str(raw.get("verifier") or ""),
        verifier_result=result.strip(),
        handoff_id=handoff_id.strip(),
        digest=str(raw.get("digest") or expected),
    )
