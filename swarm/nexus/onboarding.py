"""Onboarding state machine — pure logic, no DB / network.

Implements the state machine defined in
`2nd-brain/Pitches/03-nexus-autonomous-onboarding-and-growth-os-v1.md` §3:

  intake → qualified → workspace_created → wired → in_loop
                    └──→ paused / off_boarded (sensitive transitions)

All side effects are pushed to caller-supplied Protocols. The module
has zero DB / HTTP / subprocess calls so the test suite stubs every
boundary.

LLM access goes through `swarm.model_router.get_client(Tier.WORKING)`
in production but is injected as an `LLMClient` Protocol for tests.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Iterable, Protocol

from swarm.nexus.types import (
    ApprovalPolicy,
    ApprovalRequest,
    Channel,
    Client,
    ClientStatus,
    Loop,
    LoopKind,
    Qualification,
    Reversibility,
    TransitionOutcome,
    TransitionResult,
    Workspace,
)


# ============================================================
# Injected Protocols (concrete adapters land in PR-NEXUS-5)
# ============================================================

class LLMClient(Protocol):
    def complete(
        self,
        *,
        system: str,
        user: str,
        max_tokens: int = 1024,
        temperature: float = 0.3,
    ) -> str: ...


class ClientStore(Protocol):
    def get(self, client_id: str) -> Client | None: ...
    def save(self, client: Client) -> Client: ...


class WorkspaceStore(Protocol):
    def get(self, workspace_id: str) -> Workspace | None: ...
    def get_by_slug(self, slug: str) -> Workspace | None: ...
    def save(self, workspace: Workspace) -> Workspace: ...
    def slug_taken(self, slug: str) -> bool: ...


class ChannelStore(Protocol):
    def list_for_workspace(self, workspace_id: str) -> Iterable[Channel]: ...


class LoopStore(Protocol):
    def upsert(self, loop: Loop) -> Loop: ...
    def list_for_workspace(self, workspace_id: str) -> Iterable[Loop]: ...


class ApprovalStore(Protocol):
    def enqueue(self, req: ApprovalRequest) -> ApprovalRequest: ...
    def get(self, approval_id: str) -> ApprovalRequest | None: ...


# ============================================================
# Constants
# ============================================================

QUALIFY_BUDGET_APPROVAL_THRESHOLD_AUD = 5_000
APPROVAL_SLA_HOURS = 72
SLUG_PATTERN = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
MIN_SLUG_LEN = 3
MAX_SLUG_LEN = 40

QUALIFY_SYSTEM_PROMPT = """You are a qualification assistant for an
agentic operating system that onboards new clients.

Given a raw intake (notes + voice transcript), output STRICT JSON:

{
  "industry": "restoration" | "health" | "b2b-saas" | "ecommerce" | "professional-services" | "other",
  "scope_summary": "<one paragraph>",
  "estimated_budget_aud": <int or null>,
  "compliance_flags": ["IICRC", "NDIA", "HIPAA", "GDPR", "PCI", ...],
  "qualified": <bool>,
  "rationale": "<one sentence why qualified or not>",
  "requires_approval": <bool>,
  "approval_reason": "<one sentence or null>"
}

Set qualified=false if scope is too vague, industry unknown, or compliance
risk is unmanaged. Set requires_approval=true if budget > AUD 5000 OR
compliance_flags is non-empty OR the engagement involves contractual
commitments. Compliance_flags should always be a list (possibly empty).
Estimated_budget_aud is null if not derivable from the input.
"""


# ============================================================
# Transitions
# ============================================================

def qualify_client(
    client: Client,
    raw_intake: str,
    *,
    llm: LLMClient,
    now: datetime | None = None,
) -> TransitionOutcome:
    """intake → qualified.

    Calls the LLM to extract a structured Qualification; emits
    ApprovalRequest payload if requires_approval=true. Caller wires
    the actual approval enqueue in its adapter.
    """
    now = now or datetime.now(timezone.utc)
    if client.status != "intake":
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason=f"client must be in 'intake' to qualify, got {client.status!r}",
        )

    raw = llm.complete(
        system=QUALIFY_SYSTEM_PROMPT,
        user=raw_intake,
        max_tokens=800,
        temperature=0.0,
    )
    m = re.search(r"\{.*\}", raw, re.DOTALL)
    if not m:
        return TransitionOutcome(
            result="error",
            new_status=None,
            reason="LLM returned no JSON object",
        )
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError as exc:
        return TransitionOutcome(
            result="error",
            new_status=None,
            reason=f"LLM JSON parse failed: {exc}",
        )

    qual = Qualification(
        industry=str(data.get("industry", "other")),
        scope_summary=str(data.get("scope_summary", "")),
        estimated_budget_aud=(
            int(data["estimated_budget_aud"])
            if data.get("estimated_budget_aud") is not None
            else None
        ),
        compliance_flags=tuple(data.get("compliance_flags") or ()),
        qualified=bool(data.get("qualified", False)),
        rationale=str(data.get("rationale", "")),
        requires_approval=bool(data.get("requires_approval", False)),
        approval_reason=(
            str(data["approval_reason"])
            if data.get("approval_reason") is not None
            else None
        ),
    )

    # Belt-and-braces: budget threshold OR compliance flags force approval
    if (qual.estimated_budget_aud or 0) > QUALIFY_BUDGET_APPROVAL_THRESHOLD_AUD:
        qual = _force_approval(qual, "budget > AUD 5000")
    elif qual.compliance_flags:
        qual = _force_approval(
            qual,
            f"compliance flags present: {', '.join(qual.compliance_flags)}",
        )

    audit_payload = {
        "client_id": client.id,
        "qualification": qual.__dict__,
    }

    return TransitionOutcome(
        result="ok",
        new_status="qualified",
        reason=qual.rationale,
        audit_payload=audit_payload,
    )


def _force_approval(qual: Qualification, reason: str) -> Qualification:
    if qual.requires_approval:
        return qual
    return Qualification(
        industry=qual.industry,
        scope_summary=qual.scope_summary,
        estimated_budget_aud=qual.estimated_budget_aud,
        compliance_flags=qual.compliance_flags,
        qualified=qual.qualified,
        rationale=qual.rationale,
        requires_approval=True,
        approval_reason=reason,
    )


def approve_qualification(
    client: Client,
    decision: str,
    *,
    decided_by: str,
    note: str | None = None,
    now: datetime | None = None,
) -> TransitionOutcome:
    """qualified → workspace_created (gated on approval).

    `decision` ∈ {'approved', 'denied'}.
    """
    now = now or datetime.now(timezone.utc)
    if client.status != "qualified":
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason=f"client must be in 'qualified', got {client.status!r}",
        )
    if decision not in ("approved", "denied"):
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason=f"decision must be 'approved' or 'denied', got {decision!r}",
        )
    if decision == "denied":
        return TransitionOutcome(
            result="ok",
            new_status="intake",  # park back at intake; client can be requalified
            reason=note or "denied by operator",
            audit_payload={
                "client_id": client.id,
                "decision": "denied",
                "decided_by": decided_by,
            },
        )
    # decision == approved
    return TransitionOutcome(
        result="ok",
        new_status="qualified",  # state unchanged here; create_workspace advances
        reason=note or "qualification approved",
        audit_payload={
            "client_id": client.id,
            "decision": "approved",
            "decided_by": decided_by,
        },
    )


def create_workspace(
    client: Client,
    slug: str,
    display_name: str,
    linear_team_id: str,
    *,
    workspaces: WorkspaceStore,
    github_repo: str | None = None,
    linear_project_id: str | None = None,
    now: datetime | None = None,
) -> TransitionOutcome:
    """qualified → workspace_created."""
    now = now or datetime.now(timezone.utc)
    if client.status != "qualified":
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason=f"client must be in 'qualified', got {client.status!r}",
        )
    err = _validate_slug(slug)
    if err:
        return TransitionOutcome(result="denied", new_status=None, reason=err)
    if workspaces.slug_taken(slug):
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason=f"slug {slug!r} already taken",
        )
    workspace = Workspace(
        id=f"ws-{client.id}",
        client_id=client.id,
        slug=slug,
        display_name=display_name,
        linear_team_id=linear_team_id,
        github_repo=github_repo,
        linear_project_id=linear_project_id,
        status="active",
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )
    saved = workspaces.save(workspace)
    return TransitionOutcome(
        result="ok",
        new_status="workspace_created",
        reason="workspace created",
        workspace_id=saved.id,
        audit_payload={
            "client_id": client.id,
            "workspace_id": saved.id,
            "workspace_slug": saved.slug,
        },
    )


def wire_channels(
    client: Client,
    workspace: Workspace,
    *,
    channels: ChannelStore,
    now: datetime | None = None,
) -> TransitionOutcome:
    """workspace_created → wired (at least one channel must exist)."""
    if client.status != "workspace_created":
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason=f"client must be in 'workspace_created', got {client.status!r}",
        )
    found = list(channels.list_for_workspace(workspace.id))
    if not found:
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason="no channels mapped to workspace; provision at least one before wiring",
        )
    return TransitionOutcome(
        result="ok",
        new_status="wired",
        reason=f"{len(found)} channel(s) mapped",
        workspace_id=workspace.id,
        audit_payload={
            "client_id": client.id,
            "workspace_id": workspace.id,
            "channel_count": len(found),
        },
    )


def enable_loops(
    client: Client,
    workspace: Workspace,
    loop_specs: Iterable[tuple[LoopKind, str, dict]],
    *,
    loops: LoopStore,
    now: datetime | None = None,
) -> TransitionOutcome:
    """wired → in_loop.

    `loop_specs` is an iterable of `(loop_kind, cadence_cron, config_dict)`.
    """
    now = now or datetime.now(timezone.utc)
    if client.status != "wired":
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason=f"client must be in 'wired', got {client.status!r}",
        )
    enabled: list[Loop] = []
    for kind, cadence, cfg in loop_specs:
        loop = Loop(
            id=f"lp-{workspace.id}-{kind}",
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            loop_kind=kind,
            cadence=cadence,
            enabled=True,
            config=cfg or {},
            created_at=now.isoformat(),
        )
        enabled.append(loops.upsert(loop))
    if not enabled:
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason="loop_specs empty; at least one loop must be enabled to transition to in_loop",
        )
    return TransitionOutcome(
        result="ok",
        new_status="in_loop",
        reason=f"{len(enabled)} loop(s) enabled: {[l.loop_kind for l in enabled]}",
        workspace_id=workspace.id,
        audit_payload={
            "client_id": client.id,
            "workspace_id": workspace.id,
            "loops_enabled": [l.loop_kind for l in enabled],
        },
    )


def pause_workspace(
    client: Client,
    workspace: Workspace,
    reason: str,
    *,
    now: datetime | None = None,
) -> TransitionOutcome:
    """in_loop → paused (reversible)."""
    if client.status != "in_loop":
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason=f"client must be in 'in_loop' to pause, got {client.status!r}",
        )
    return TransitionOutcome(
        result="ok",
        new_status="paused",
        reason=reason,
        workspace_id=workspace.id,
        audit_payload={"client_id": client.id, "reason": reason},
    )


def resume_workspace(
    client: Client,
    workspace: Workspace,
    *,
    now: datetime | None = None,
) -> TransitionOutcome:
    """paused → in_loop (reversible)."""
    if client.status != "paused":
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason=f"client must be in 'paused' to resume, got {client.status!r}",
        )
    return TransitionOutcome(
        result="ok",
        new_status="in_loop",
        reason="resumed",
        workspace_id=workspace.id,
        audit_payload={"client_id": client.id},
    )


def off_board_client(
    client: Client,
    *,
    decided_by: str,
    explicit_ack: bool,
    now: datetime | None = None,
) -> TransitionOutcome:
    """Any non-off_boarded → off_boarded. IRREVERSIBLE.

    Requires `explicit_ack=True` — the caller asserts they've received
    operator confirmation. Fails closed if False.
    """
    if not explicit_ack:
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason="off-boarding requires explicit_ack=True (irreversible action)",
        )
    if client.status == "off_boarded":
        return TransitionOutcome(
            result="denied",
            new_status=None,
            reason="client already off-boarded",
        )
    return TransitionOutcome(
        result="ok",
        new_status="off_boarded",
        reason=f"off-boarded by {decided_by}",
        audit_payload={
            "client_id": client.id,
            "previous_status": client.status,
            "decided_by": decided_by,
            "irreversible": True,
        },
    )


# ============================================================
# Approval request construction
# ============================================================

def build_qualification_approval(
    client: Client,
    qual: Qualification,
    *,
    requested_by: str,
    now: datetime | None = None,
) -> ApprovalRequest:
    """Construct the ApprovalRequest payload for a qualified-but-gated client."""
    now = now or datetime.now(timezone.utc)
    sla = now + timedelta(hours=APPROVAL_SLA_HOURS)
    reversibility: Reversibility = (
        "low" if (qual.estimated_budget_aud or 0) <= QUALIFY_BUDGET_APPROVAL_THRESHOLD_AUD
        else "medium"
    )
    return ApprovalRequest(
        id=f"ap-qual-{client.id}",
        requested_by=requested_by,
        action="qualification:approve",
        why_now=qual.approval_reason or "qualification requires sign-off",
        reversibility=reversibility,
        payload={
            "client_id": client.id,
            "qualification": qual.__dict__,
        },
        sla_expires_at=sla.isoformat(),
        status="pending",
        created_at=now.isoformat(),
    )


# ============================================================
# Helpers
# ============================================================

def _validate_slug(slug: str) -> str | None:
    if not slug:
        return "slug cannot be empty"
    if len(slug) < MIN_SLUG_LEN:
        return f"slug too short (min {MIN_SLUG_LEN} chars)"
    if len(slug) > MAX_SLUG_LEN:
        return f"slug too long (max {MAX_SLUG_LEN} chars)"
    if not SLUG_PATTERN.match(slug):
        return "slug must be lowercase alphanumeric with hyphens only"
    if slug.startswith("-") or slug.endswith("-"):
        return "slug cannot start or end with hyphen"
    return None


def is_terminal(status: ClientStatus) -> bool:
    """off_boarded is terminal (irreversible)."""
    return status == "off_boarded"


def can_transition_to(current: ClientStatus, target: ClientStatus) -> bool:
    """Authoritative transition table."""
    table: dict[ClientStatus, set[ClientStatus]] = {
        "intake": {"qualified"},
        "qualified": {"workspace_created", "intake"},  # denied → back to intake
        "workspace_created": {"wired", "paused", "off_boarded"},
        "wired": {"in_loop", "paused", "off_boarded"},
        "in_loop": {"paused", "off_boarded"},
        "paused": {"in_loop", "off_boarded"},
        "off_boarded": set(),  # terminal
    }
    return target in table.get(current, set())
