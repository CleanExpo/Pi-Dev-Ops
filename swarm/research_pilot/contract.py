"""Frozen shapes for the RA-7522 read-only research swarm pilot."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any, Literal

SCHEMA_VERSION = "1.0"
MIN_RESEARCH_NODES = 2
MAX_RESEARCH_NODES = 3
WRITE_LANE_ADMITTED = False
WRITE_LANE_GATE = (
    "write-capable lanes require human board approval (RA-7522); "
    "this pilot does not admit them"
)

MCState = Literal["pending", "ready", "running", "verifying", "passed", "blocked"]
MC_STATES: tuple[str, ...] = (
    "pending",
    "ready",
    "running",
    "verifying",
    "passed",
    "blocked",
)
PASSED_TRAJECTORY: tuple[str, ...] = (
    "pending",
    "ready",
    "running",
    "verifying",
    "passed",
)

RESEARCH_TOOLS = frozenset(
    {"read", "grep", "glob", "web.search", "docs.fetch", "notebooklm.query"}
)
DESTRUCTIVE_TOOLS = frozenset(
    {
        "crm.update",
        "crm.write",
        "db.drop",
        "git.commit",
        "git.push",
        "git.rebase",
        "github.create_pr",
        "github.merge",
        "linear.create_issue",
        "linear.update_issue",
        "railway.deploy",
        "railway.up",
        "shell.rm",
        "supabase.migrate",
        "terraform.apply",
        "vercel.deploy",
    }
)

REASON_OVERLAP = "overlapping-ownership"
REASON_CAPS = "missing-caps"
REASON_USAGE = "unknown-usage"
REASON_CANCEL = "missing-cancellation"
REASON_TOOLS = "production-destructive-tools"
REASON_EVIDENCE = "stale-or-mismatched-evidence"
REASON_WRITE_LANE = "write-lane-requires-board-approval"
REASON_NODE_COUNT = "node-count-out-of-range"

STOP_RULES: tuple[str, ...] = (
    "token_budget: stop launching when reserved tokens would exceed max_tokens",
    "time_budget: stop launching when reserved seconds would exceed max_seconds",
    "reservation_headroom: stop launching new work at 80% of token or time budget",
    "unknown_usage: unknown usage is not treated as zero and blocks further dispatch",
    "context: nodes may not share ownership or dispatch other workers",
    "mutations=false: no repository, Linear, CRM, or production writes",
    "write_lane: write-capable lanes require human board approval and are not admitted",
    "billing: Max plan only — API credit lanes are refused",
)


class PilotContractError(ValueError):
    """Raised when a research-pilot request cannot be trusted."""

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        super().__init__(detail or reason)


@dataclass(frozen=True)
class ResearchNode:
    node_id: str
    purpose: str
    owns: tuple[str, ...]
    tools: tuple[str, ...]
    worker_id: str


@dataclass(frozen=True)
class PilotBudget:
    max_tokens: int
    max_seconds: int


@dataclass(frozen=True)
class PilotCapabilities:
    mutations: bool
    supports_cancellation: bool
    write_lane: bool


@dataclass(frozen=True)
class PilotUsage:
    status: str
    tokens: int
    seconds: int


@dataclass(frozen=True)
class PilotEvidence:
    plan_id: str
    source_state: str
    verifier: str
    verifier_result: str
    handoff_id: str
    digest: str


@dataclass(frozen=True)
class PilotPlan:
    plan_id: str
    task: str
    source_state: str
    verifier: str
    nodes: tuple[ResearchNode, ...]
    budget: PilotBudget
    capabilities: PilotCapabilities
    usage: PilotUsage
    evidence: PilotEvidence


@dataclass(frozen=True)
class DryRunReceipt:
    plan_id: str
    dispatched: bool
    mutated: tuple[str, ...]
    mutations: bool
    source_state: str
    usage: PilotUsage
    verifier: str
    verifier_result: str
    handoff_id: str
    projected_states: tuple[dict[str, Any], ...]
    final_states: dict[str, str]
    stop_rules: tuple[str, ...]
    operator_stop_rules: dict[str, Any]
    billing: str
    write_lane_admitted: bool


def evidence_digest(
    *,
    plan_id: str,
    source_state: str,
    verifier: str,
    handoff_id: str,
) -> str:
    payload = f"{plan_id}|{source_state}|{verifier}|{handoff_id}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def sample_pilot_request() -> dict[str, Any]:
    """Valid two-node dry-run fixture. No live systems, no write lane."""
    plan_id = "ra-7522-dry-run-sample"
    source_state = "fixture:ra-7522:v1"
    verifier = "research-verifier"
    handoff_id = "handoff-ra-7522-sample"
    return {
        "schema_version": SCHEMA_VERSION,
        "plan_id": plan_id,
        "task": "Compare two bounded research scopes without mutating systems",
        "source_state": source_state,
        "verifier": verifier,
        "nodes": _sample_nodes(),
        "budget": {"max_tokens": 8000, "max_seconds": 120},
        "capabilities": {
            "mutations": False,
            "supports_cancellation": True,
            "write_lane": False,
        },
        "usage": {"status": "known", "tokens": 0, "seconds": 0},
        "evidence": {
            "plan_id": plan_id,
            "source_state": source_state,
            "verifier": verifier,
            "verifier_result": "projected-pass",
            "handoff_id": handoff_id,
            "digest": evidence_digest(
                plan_id=plan_id,
                source_state=source_state,
                verifier=verifier,
                handoff_id=handoff_id,
            ),
        },
    }


def _sample_nodes() -> list[dict[str, Any]]:
    return [
        {
            "id": "r1",
            "purpose": "Survey existing swarm dry-run paths",
            "owns": ["swarm/flow_engine.py", "swarm/closed_loop.py"],
            "tools": ["read", "grep"],
            "worker_id": "researcher-a",
        },
        {
            "id": "r2",
            "purpose": "Survey Unlazy orchestration contract",
            "owns": ["skills/unlazy/references/orchestration.md"],
            "tools": ["read", "docs.fetch"],
            "worker_id": "researcher-b",
        },
    ]
