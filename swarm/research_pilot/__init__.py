"""RA-7522 read-only research swarm pilot — contract, validators, dry-run.

Composes the Unlazy Mission Control node states
(``pending → ready → running → verifying → passed|blocked``) and the
existing disjoint-ownership / cancellation rules. This package never
dispatches an agent and never admits a write-capable lane.
"""

from .contract import (
    DESTRUCTIVE_TOOLS,
    MC_STATES,
    RESEARCH_TOOLS,
    STOP_RULES,
    WRITE_LANE_ADMITTED,
    WRITE_LANE_GATE,
    DryRunReceipt,
    PilotContractError,
    PilotPlan,
    evidence_digest,
    sample_pilot_request,
)
from .dry_run import dry_run_pilot
from .validate import validate_pilot

__all__ = [
    "DESTRUCTIVE_TOOLS",
    "MC_STATES",
    "RESEARCH_TOOLS",
    "STOP_RULES",
    "WRITE_LANE_ADMITTED",
    "WRITE_LANE_GATE",
    "DryRunReceipt",
    "PilotContractError",
    "PilotPlan",
    "dry_run_pilot",
    "evidence_digest",
    "sample_pilot_request",
    "validate_pilot",
]
