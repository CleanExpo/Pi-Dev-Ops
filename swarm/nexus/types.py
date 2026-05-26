"""Frozen dataclasses for the Nexus onboarding pipeline.

These mirror the schema in `supabase/migrations/20260601_nexus_v1.sql`.
DB I/O happens in adapter modules (PR-NEXUS-5 wiring); this file is
pure data shapes.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


# ============================================================
# Lifecycle enums (kept as Literals so type-checking enforces values)
# ============================================================

ClientStatus = Literal[
    "intake",
    "qualified",
    "workspace_created",
    "wired",
    "in_loop",
    "paused",
    "off_boarded",
]

WorkspaceStatus = Literal["active", "paused", "archived"]
ProjectStatus = Literal["discovery", "active", "done", "cancelled"]
ApprovalPolicy = Literal["creator_only", "majority", "custom"]
ChannelKind = Literal["telegram_chat", "telegram_bot", "slack", "email"]
ChannelStatus = Literal["active", "paused", "archived", "pending"]
InboundRoute = Literal["margot", "support", "ops-only"]
LoopKind = Literal["discovery", "content", "kpi", "geo", "support", "compliance"]
ApprovalStatus = Literal["pending", "approved", "denied", "auto-denied", "expired"]
Reversibility = Literal["reversible", "low", "medium", "high", "irreversible"]
IntakeSource = Literal["voice", "form", "manual", "referral"]
OutcomeSource = Literal["stripe", "vercel", "posthog", "sentry", "linear", "manual"]
PolicyLevel = Literal["auto", "approval", "escalation"]
TransitionResult = Literal["ok", "denied", "error", "timeout"]


# ============================================================
# Client / qualification
# ============================================================

@dataclass(frozen=True)
class Client:
    """Pre-workspace intake record."""
    id: str
    founder_id: str
    legal_name: str
    display_name: str
    status: ClientStatus = "intake"
    industry: str | None = None
    primary_contact_name: str | None = None
    primary_contact_email: str | None = None
    intake_source: IntakeSource | None = None
    intake_recorded_at: str | None = None  # ISO 8601
    qualification: dict | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Qualification:
    """Output of qualify_client(). Stored in clients.qualification JSONB."""
    industry: str
    scope_summary: str
    estimated_budget_aud: int | None
    compliance_flags: tuple[str, ...]
    qualified: bool
    rationale: str
    requires_approval: bool
    approval_reason: str | None = None


# ============================================================
# Workspace + downstream
# ============================================================

@dataclass(frozen=True)
class Workspace:
    id: str
    client_id: str
    slug: str
    display_name: str
    linear_team_id: str
    github_org: str | None = None
    github_repo: str | None = None
    vercel_project: str | None = None
    supabase_project: str | None = None
    linear_project_id: str | None = None
    status: WorkspaceStatus = "active"
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True)
class Channel:
    id: str
    workspace_id: str
    workspace_slug: str
    kind: ChannelKind
    external_id: str
    display_name: str
    inbound_route: InboundRoute
    bot_token_env_name: str | None = None
    authorized_chat_ids: tuple[str, ...] = ()
    status: ChannelStatus = "pending"
    provisioned_at: str | None = None
    created_at: str = ""


@dataclass(frozen=True)
class Loop:
    id: str
    workspace_id: str
    workspace_slug: str
    loop_kind: LoopKind
    cadence: str
    enabled: bool = True
    config: dict = field(default_factory=dict)
    last_run_at: str | None = None
    next_run_at: str | None = None
    created_at: str = ""


# ============================================================
# Approval queue
# ============================================================

@dataclass(frozen=True)
class ApprovalRequest:
    id: str
    requested_by: str
    action: str
    why_now: str
    reversibility: Reversibility
    payload: dict
    sla_expires_at: str
    workspace_id: str | None = None
    workspace_slug: str | None = None
    risk_if_yes: str | None = None
    risk_if_no: str | None = None
    status: ApprovalStatus = "pending"
    decided_by: str | None = None
    decided_at: str | None = None
    decision_note: str | None = None
    created_at: str = ""


# ============================================================
# Outcomes — feedback-loop signals attributed to workspace/project/persona
# ============================================================

DeltaWindow = Literal["24h", "7d", "30d"]


@dataclass(frozen=True)
class Outcome:
    id: str
    workspace_id: str
    workspace_slug: str
    source: OutcomeSource
    metric: str
    captured_at: str
    project_id: str | None = None
    persona_attribution: str | None = None
    value_numeric: float | None = None
    value_text: str | None = None
    delta_window: DeltaWindow | None = None
    raw_payload: dict = field(default_factory=dict)
    created_at: str = ""


# ============================================================
# Transition outcome
# ============================================================

@dataclass(frozen=True)
class TransitionOutcome:
    result: TransitionResult
    new_status: ClientStatus | None
    reason: str
    workspace_id: str | None = None
    approval_id: str | None = None
    audit_payload: dict = field(default_factory=dict)
