"""Autonomous reversibility-driven approval policy.

Replaces the *human* approval gate with an *autonomous* one for reversible
work. Maps an ``ApprovalRequest.reversibility`` to a ``PolicyLevel`` and, for
the auto tier, decides the approval WITHOUT a human — writing the same kind of
audit row a human decision would. Medium/high reversibility still route to the
existing HITL gate (``decide_approval`` over Telegram); irreversible escalates
to founder-only.

Honours the locked ``feedback-autonomy`` directive — "pause only for
destructive/irreversible". The human is removed from the loop for everything
reversible; the gate remains (now autonomous) for the rest. This module is the
policy layer ONLY — pure logic, no I/O (mirrors ``app/server/kill_switch.py``).
Two things sit ABOVE it and are deliberately out of scope here:

  * the ``TAO_HARD_STOP`` kill-switch (``app/server/kill_switch.py`` /
    ``swarm/kill_switch.py``) — the ultimate operator stop, still in force;
  * edge-triggered Telegram notification (notify, not ask) — emitted by the
    caller using the ``autonomy._send_watchdog_telegram`` pattern, only on a
    state change (a new escalation), never per-cycle.

Policy matrix (spec §6, now automated):

    reversible | low      -> auto        (auto-approve, audit-only, no human)
    medium     | high     -> approval    (route to HITL / Telegram)
    irreversible          -> escalation  (founder-only; never auto)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from swarm.nexus.audit import NexusAuditRow, build_audit_row
from swarm.nexus.approvals import ApprovalStore
from swarm.nexus.types import ApprovalRequest, PolicyLevel, Reversibility


# ============================================================
# Policy matrix
# ============================================================

REVERSIBILITY_POLICY: dict[Reversibility, PolicyLevel] = {
    "reversible": "auto",
    "low": "auto",
    "medium": "approval",
    "high": "approval",
    "irreversible": "escalation",
}


def classify_policy(reversibility: Reversibility) -> PolicyLevel:
    """Map a reversibility class to its autonomous policy level.

    Unknown values fail closed to ``escalation`` (never silently auto-run).
    """
    return REVERSIBILITY_POLICY.get(reversibility, "escalation")


# ============================================================
# Result shape
# ============================================================

@dataclass(frozen=True)
class PolicyDecision:
    policy_level: PolicyLevel
    auto_decided: bool          # True only when the gate approved with no human
    approval: ApprovalRequest   # updated (status=approved) for auto; unchanged otherwise
    audit_row: NexusAuditRow
    reason: str


# ============================================================
# The gate
# ============================================================

def auto_gate(
    request: ApprovalRequest,
    *,
    approvals: ApprovalStore,
    actor: str = "autonomous-gate",
    now: datetime | None = None,
) -> PolicyDecision:
    """Apply the autonomous reversibility policy to a pending approval.

    * ``auto``        — approve in-process, audit-only, no human in the loop.
    * ``approval``    — leave pending; caller routes to the Telegram HITL gate.
    * ``escalation``  — leave pending; founder-only. Never auto-approved.

    Fails closed: a non-pending request is never re-decided, and an unknown
    reversibility class escalates rather than auto-running. Every path writes
    an audit row so the trail is identical to a human decision.
    """
    now = now or datetime.now(timezone.utc)
    level = classify_policy(request.reversibility)

    base_args = {
        "original_action": request.action,
        "reversibility": request.reversibility,
        "why_now": request.why_now,
    }

    # Fail closed on anything not pending — do not re-decide.
    if request.status != "pending":
        audit_row = build_audit_row(
            actor=actor,
            action="gate:skipped",
            args={**base_args, "status": request.status},
            policy_level=level,
            result="denied",
            workspace_id=request.workspace_id,
            workspace_slug=request.workspace_slug,
            approval_id=request.id,
            now=now,
        )
        return PolicyDecision(
            policy_level=level,
            auto_decided=False,
            approval=request,
            audit_row=audit_row,
            reason=f"approval already {request.status!r}; gate not applied",
        )

    if level == "auto":
        updated = approvals.update_status(
            request.id,
            new_status="approved",
            decided_by=actor,
            decided_at=now.isoformat(),
            decision_note="auto-approved by reversibility policy",
        )
        audit_row = build_audit_row(
            actor=actor,
            action="approval:auto-approved",
            args=base_args,
            policy_level="auto",
            result="ok",
            workspace_id=request.workspace_id,
            workspace_slug=request.workspace_slug,
            approval_id=request.id,
            now=now,
        )
        return PolicyDecision(
            policy_level="auto",
            auto_decided=True,
            approval=updated,
            audit_row=audit_row,
            reason=f"reversibility={request.reversibility!r} -> auto-approved (no human)",
        )

    # medium/high -> route to HITL; irreversible -> escalate. Leave pending.
    action = "gate:routed-to-approval" if level == "approval" else "gate:escalated"
    reason = (
        f"reversibility={request.reversibility!r} -> {level}; "
        f"{'routed to HITL/Telegram' if level == 'approval' else 'founder-only escalation'}"
    )
    audit_row = build_audit_row(
        actor=actor,
        action=action,
        args=base_args,
        policy_level=level,
        result="ok",
        workspace_id=request.workspace_id,
        workspace_slug=request.workspace_slug,
        approval_id=request.id,
        now=now,
    )
    return PolicyDecision(
        policy_level=level,
        auto_decided=False,
        approval=request,
        audit_row=audit_row,
        reason=reason,
    )
