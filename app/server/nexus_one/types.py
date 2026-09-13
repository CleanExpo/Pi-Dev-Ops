"""Frozen shapes for the Nexus One synthetic vertical pilot.

SYNTHETIC: labelled fixture only. Not a production control plane, lease,
or Mission Control admission record. Evidence produced here is excluded
from real acceptance.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

LINEAGE = "SYNTHETIC"
SYNTHETIC_MARKER = "[SYNTHETIC]"
SYNTHETIC_FIXTURE_ID = "nexus-one-vertical-pilot-synthetic-20260913"
MAX_LANE = "claude_max_subscription"
MAX_RUNTIME = "claude_cli"
API_LANE = "anthropic_api"

TaskStatus = Literal[
    "admitted",
    "dispatched",
    "accepted",
    "failed",
    "checkpointed",
    "refused",
]
AttemptOutcome = Literal["passed", "failed", "rejected_duplicate"]
ReviewVerdict = Literal["pass", "incomplete", "rejected"]


@dataclass(frozen=True)
class TaskContract:
    """One canonical contract revision for a synthetic Margot input."""

    task_id: str
    founder_id: str
    objective: str
    input_fingerprint: str
    revision: int
    lineage: str = LINEAGE
    status: TaskStatus = "admitted"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class WorkerDecision:
    """Broker naming of the eligible runtime. Never an API-credit path."""

    eligible: bool
    lane: str
    runtime: str
    platform: str
    cost_usd: float
    billing: str
    reason: str
    platform_role: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class MethodAttempt:
    fingerprint: str
    method: str
    hypothesis: str
    tool_path: str
    outcome: AttemptOutcome

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class IndependentReview:
    """Judge hook result. Builder family must not equal review family."""

    invoked: bool
    independent: bool
    family: str
    builder_family: str
    verdict: ReviewVerdict
    score: int
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Receipt:
    receipt_id: str
    task_id: str
    lineage: str
    excluded_from_real_acceptance: bool
    evidence: tuple[str, ...]
    checkpoint_sha256: str
    accepted: bool
    worker: WorkerDecision
    review: IndependentReview
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evidence"] = list(self.evidence)
        return data


def receipt_from_dict(raw: dict[str, Any]) -> Receipt:
    return Receipt(
        receipt_id=str(raw["receipt_id"]),
        task_id=str(raw["task_id"]),
        lineage=str(raw["lineage"]),
        excluded_from_real_acceptance=bool(raw["excluded_from_real_acceptance"]),
        evidence=tuple(raw.get("evidence") or ()),
        checkpoint_sha256=str(raw["checkpoint_sha256"]),
        accepted=bool(raw["accepted"]),
        worker=WorkerDecision(**raw["worker"]),
        review=IndependentReview(**raw["review"]),
        path=str(raw.get("path") or ""),
    )


@dataclass(frozen=True)
class JourneyResult:
    task: TaskContract
    duplicate: bool
    resumed: bool
    dispatched: bool
    accepted: bool
    worker: WorkerDecision
    attempts: tuple[MethodAttempt, ...] = ()
    review: IndependentReview | None = None
    receipt: Receipt | None = None
    checkpoint_path: str = ""
    evidence: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task": self.task.to_dict(),
            "duplicate": self.duplicate,
            "resumed": self.resumed,
            "dispatched": self.dispatched,
            "accepted": self.accepted,
            "worker": self.worker.to_dict(),
            "attempts": [a.to_dict() for a in self.attempts],
            "review": None if self.review is None else self.review.to_dict(),
            "receipt": None if self.receipt is None else self.receipt.to_dict(),
            "checkpoint_path": self.checkpoint_path,
            "evidence": list(self.evidence),
        }
