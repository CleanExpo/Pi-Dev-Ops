"""Approval queue logic — pure logic, no DB.

Implements the approval state machine + SLA expiry computation per spec
§6 (approval gate matrix). Caller-supplied `ApprovalStore` protocol does
the actual persistence.

State transitions:

    pending ─── decide(approved) ─→  approved
            ─── decide(denied)   ─→  denied
            ─── (sla_expires)    ─→  auto-denied

Audit row written via swarm.nexus.audit.build_audit_row for every
decision.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Iterable, Literal, Protocol

from swarm.nexus.audit import (
    AuditResult,
    NexusAuditRow,
    PolicyLevel,
    build_audit_row,
)
from swarm.nexus.onboarding import APPROVAL_SLA_HOURS
from swarm.nexus.types import ApprovalRequest, ApprovalStatus


# ============================================================
# Caller-supplied store
# ============================================================

class ApprovalStore(Protocol):
    def enqueue(self, req: ApprovalRequest) -> ApprovalRequest: ...
    def get(self, approval_id: str) -> ApprovalRequest | None: ...
    def update_status(
        self,
        approval_id: str,
        *,
        new_status: ApprovalStatus,
        decided_by: str | None,
        decided_at: str | None,
        decision_note: str | None,
    ) -> ApprovalRequest: ...
    def list_pending(
        self,
        *,
        workspace_slug: str | None = None,
        sla_expired_only: bool = False,
        now: datetime | None = None,
    ) -> Iterable[ApprovalRequest]: ...


# ============================================================
# Result shape
# ============================================================

@dataclass(frozen=True)
class ApprovalDecisionOutcome:
    result: AuditResult
    approval: ApprovalRequest | None
    audit_row: NexusAuditRow | None
    reason: str


# ============================================================
# Public API
# ============================================================

def decide_approval(
    approval_id: str,
    decision: Literal["approved", "denied"],
    *,
    decided_by: str,
    note: str | None = None,
    approvals: ApprovalStore,
    now: datetime | None = None,
) -> ApprovalDecisionOutcome:
    """Decide a pending approval. Writes the audit row in the same step.

    Fails closed if:
      - approval not found
      - approval not in 'pending' state
      - approval is past SLA expiry (caller should sweep auto-denies first)
    """
    now = now or datetime.now(timezone.utc)
    approval = approvals.get(approval_id)
    if approval is None:
        return ApprovalDecisionOutcome(
            result="denied",
            approval=None,
            audit_row=None,
            reason=f"approval {approval_id!r} not found",
        )
    if approval.status != "pending":
        return ApprovalDecisionOutcome(
            result="denied",
            approval=approval,
            audit_row=None,
            reason=f"approval already {approval.status!r}; cannot re-decide",
        )

    sla = datetime.fromisoformat(approval.sla_expires_at.replace("Z", "+00:00"))
    if sla.tzinfo is None:
        sla = sla.replace(tzinfo=timezone.utc)
    if now > sla:
        # Caller should auto-deny via sweep_expired before user decides
        return ApprovalDecisionOutcome(
            result="denied",
            approval=approval,
            audit_row=None,
            reason=f"approval past SLA ({approval.sla_expires_at}); use sweep_expired",
        )

    new_status: ApprovalStatus = "approved" if decision == "approved" else "denied"
    updated = approvals.update_status(
        approval_id,
        new_status=new_status,
        decided_by=decided_by,
        decided_at=now.isoformat(),
        decision_note=note,
    )

    audit_row = build_audit_row(
        actor=decided_by,
        action=f"approval:{new_status}",
        args={
            "approval_id": approval_id,
            "original_action": approval.action,
            "note": note or "",
        },
        policy_level="approval",
        result="ok",
        workspace_id=approval.workspace_id,
        workspace_slug=approval.workspace_slug,
        approval_id=approval_id,
        now=now,
    )

    return ApprovalDecisionOutcome(
        result="ok",
        approval=updated,
        audit_row=audit_row,
        reason=f"approval {new_status}",
    )


def sweep_expired(
    *,
    approvals: ApprovalStore,
    workspace_slug: str | None = None,
    now: datetime | None = None,
) -> list[ApprovalDecisionOutcome]:
    """Auto-deny every pending approval past its SLA. Returns one outcome
    per swept item with an audit row attached.

    Idempotent: re-running after a sweep is a noop (no pending past SLA).
    """
    now = now or datetime.now(timezone.utc)
    swept: list[ApprovalDecisionOutcome] = []
    for approval in approvals.list_pending(
        workspace_slug=workspace_slug,
        sla_expired_only=True,
        now=now,
    ):
        updated = approvals.update_status(
            approval.id,
            new_status="auto-denied",
            decided_by="system:sla-sweep",
            decided_at=now.isoformat(),
            decision_note="SLA expired (72h) without operator decision",
        )
        audit_row = build_audit_row(
            actor="system:sla-sweep",
            action="approval:auto-denied",
            args={
                "approval_id": approval.id,
                "original_action": approval.action,
                "sla_expired_at": approval.sla_expires_at,
            },
            policy_level="escalation",
            result="ok",
            workspace_id=approval.workspace_id,
            workspace_slug=approval.workspace_slug,
            approval_id=approval.id,
            now=now,
        )
        swept.append(
            ApprovalDecisionOutcome(
                result="ok",
                approval=updated,
                audit_row=audit_row,
                reason="SLA-auto-denied",
            )
        )
    return swept


def is_sla_expired(approval: ApprovalRequest, *, now: datetime | None = None) -> bool:
    """Pure helper: True if approval's SLA has passed."""
    now = now or datetime.now(timezone.utc)
    if approval.status != "pending":
        return False
    sla = datetime.fromisoformat(approval.sla_expires_at.replace("Z", "+00:00"))
    if sla.tzinfo is None:
        sla = sla.replace(tzinfo=timezone.utc)
    return now > sla
