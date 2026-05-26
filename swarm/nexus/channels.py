"""Telegram channel provisioning request layer — pure logic, no I/O.

The actual BotFather step is human-only (Telegram restricts bot creation
to humans). This module's job is to:

  1. Generate the structured provisioning REQUEST (channel placeholder
     row + approval queue row) so an operator can act on it.
  2. Validate the request against the workspace + tenant invariants
     before queuing.
  3. Mark the channel as `pending` in the channel store until the
     operator marks it `active` after the bot is provisioned manually.

Per spec §4 (2nd-brain/Pitches/03-...):
  - One operator bot `@UniteGroupOps` (shared)
  - Per-client bots `@<client-slug>-Nexus` (lazy-provisioned)

Anti-spoofing: this module NEVER reads bot tokens directly. Tokens live
on Railway env vars; the channel row stores the env-var NAME, not the
secret. Same pattern as CIP `intake_client_bots.bot_token_env_name`.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable, Literal, Protocol

from swarm.nexus.onboarding import APPROVAL_SLA_HOURS
from swarm.nexus.types import (
    ApprovalRequest,
    Channel,
    ChannelKind,
    InboundRoute,
    Workspace,
)


# ============================================================
# Caller-supplied Protocols
# ============================================================

class ChannelStore(Protocol):
    def save(self, channel: Channel) -> Channel: ...
    def get(self, channel_id: str) -> Channel | None: ...
    def list_for_workspace(self, workspace_id: str) -> Iterable[Channel]: ...
    def mark_active(self, channel_id: str, provisioned_at: str) -> Channel: ...


class ApprovalStore(Protocol):
    def enqueue(self, req: ApprovalRequest) -> ApprovalRequest: ...


# ============================================================
# Result shapes
# ============================================================

ProvisionAction = Literal[
    "queue_operator_bot_provision",   # @UniteGroupOps create (one-off per workspace)
    "queue_per_client_bot_provision", # @<slug>-Nexus create (BotFather human step)
    "map_existing_chat",              # operator already has bot + chat id
    "rejected",
]


@dataclass(frozen=True)
class ProvisionRequest:
    """What the caller asked for."""
    workspace_id: str
    workspace_slug: str
    kind: ChannelKind
    display_name: str
    inbound_route: InboundRoute = "margot"
    # For map_existing_chat path: caller supplies the Telegram chat id
    external_id: str | None = None
    # For per-client bot provision path: caller supplies the proposed env var name
    bot_token_env_name: str | None = None
    # For G3 anti-spoofing: caller may pre-populate the authorized chat ids
    authorized_chat_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class ProvisionOutcome:
    """What this module returns to the caller."""
    action: ProvisionAction
    reason: str
    channel_id: str | None = None
    approval_id: str | None = None
    requires_operator_step: bool = False
    operator_step_description: str | None = None
    audit_payload: dict = field(default_factory=dict)


# ============================================================
# Constants
# ============================================================

ENV_VAR_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")
SHARED_OPS_BOT_ENV = "UNITE_GROUP_OPS_BOT_TOKEN"
PER_CLIENT_BOT_ENV_PREFIX = "NEXUS_BOT_TOKEN_"
TELEGRAM_CHAT_ID_PATTERN = re.compile(r"^-?\d{6,15}$")


# ============================================================
# Validation helpers
# ============================================================

def _validate_env_var_name(name: str) -> str | None:
    if not name:
        return "bot_token_env_name cannot be empty"
    if not ENV_VAR_PATTERN.match(name):
        return f"bot_token_env_name {name!r} must be UPPER_SNAKE_CASE"
    return None


def _validate_external_id(kind: ChannelKind, external_id: str | None) -> str | None:
    if external_id is None:
        return None
    if kind in ("telegram_chat", "telegram_bot"):
        if not TELEGRAM_CHAT_ID_PATTERN.match(external_id):
            return (
                f"telegram external_id {external_id!r} must be a 6-15 digit "
                "integer (positive for private chats, negative for groups)"
            )
    if kind == "email":
        if "@" not in external_id:
            return f"email external_id {external_id!r} missing @"
    return None


def _is_per_client_bot_env(env_var: str) -> bool:
    return env_var.startswith(PER_CLIENT_BOT_ENV_PREFIX)


# ============================================================
# Main entry point
# ============================================================

def request_provision(
    req: ProvisionRequest,
    workspace: Workspace,
    *,
    channels: ChannelStore,
    approvals: ApprovalStore,
    requested_by: str,
    now: datetime | None = None,
) -> ProvisionOutcome:
    """Validate + route a provisioning request.

    Three paths:
      1. `map_existing_chat` — caller has both bot AND chat id already.
         Channel saved directly as `active`. No approval needed (the
         operator has already done the BotFather step).
      2. `queue_per_client_bot_provision` — caller wants a new per-client
         bot. We queue an approval + save channel placeholder as `pending`.
      3. `queue_operator_bot_provision` — caller wants the shared
         @UniteGroupOps bot mapped (first-time-per-workspace setup).
         Queue approval; save placeholder.
    """
    now = now or datetime.now(timezone.utc)

    # Workspace cross-check
    if workspace.id != req.workspace_id or workspace.slug != req.workspace_slug:
        return ProvisionOutcome(
            action="rejected",
            reason="workspace id/slug mismatch — refusing to provision channel "
                   "into a workspace it doesn't belong to",
        )

    # Validate external_id format if provided
    if err := _validate_external_id(req.kind, req.external_id):
        return ProvisionOutcome(action="rejected", reason=err)

    # Validate env var name if provided
    if req.bot_token_env_name is not None:
        if err := _validate_env_var_name(req.bot_token_env_name):
            return ProvisionOutcome(action="rejected", reason=err)

    # ── Path 1: map_existing_chat ─────────────────────────────────
    if req.external_id and req.kind in ("telegram_chat", "telegram_bot"):
        # If kind is telegram_bot, env var name must also be supplied
        if req.kind == "telegram_bot" and not req.bot_token_env_name:
            return ProvisionOutcome(
                action="rejected",
                reason="telegram_bot kind requires bot_token_env_name",
            )
        channel = Channel(
            id=f"ch-{workspace.slug}-{req.external_id}",
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            kind=req.kind,
            external_id=req.external_id,
            display_name=req.display_name,
            inbound_route=req.inbound_route,
            bot_token_env_name=req.bot_token_env_name,
            authorized_chat_ids=req.authorized_chat_ids,
            status="active",
            provisioned_at=now.isoformat(),
            created_at=now.isoformat(),
        )
        saved = channels.save(channel)
        return ProvisionOutcome(
            action="map_existing_chat",
            reason="existing chat id mapped to workspace",
            channel_id=saved.id,
            audit_payload={
                "workspace_slug": workspace.slug,
                "channel_id": saved.id,
                "kind": req.kind,
                "external_id": req.external_id,
            },
        )

    # ── Path 2: per-client bot provision (BotFather step) ───────────
    if req.kind == "telegram_bot" and not req.external_id:
        if not req.bot_token_env_name or not _is_per_client_bot_env(
            req.bot_token_env_name
        ):
            return ProvisionOutcome(
                action="rejected",
                reason=(
                    f"per-client bot env var must start with "
                    f"{PER_CLIENT_BOT_ENV_PREFIX} (got "
                    f"{req.bot_token_env_name!r})"
                ),
            )
        # Save placeholder
        channel = Channel(
            id=f"ch-{workspace.slug}-pending-bot",
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            kind="telegram_bot",
            external_id=f"pending-{workspace.slug}",
            display_name=req.display_name,
            inbound_route=req.inbound_route,
            bot_token_env_name=req.bot_token_env_name,
            status="pending",
            created_at=now.isoformat(),
        )
        saved = channels.save(channel)
        # Queue approval
        sla = now + timedelta(hours=APPROVAL_SLA_HOURS)
        approval = ApprovalRequest(
            id=f"ap-chan-{workspace.slug}-bot",
            requested_by=requested_by,
            action="channel:provision_telegram_bot",
            why_now=f"per-client bot @{workspace.slug}-Nexus required to dispatch outbound",
            reversibility="medium",
            payload={
                "workspace_slug": workspace.slug,
                "channel_id": saved.id,
                "bot_token_env_name": req.bot_token_env_name,
                "display_name": req.display_name,
            },
            sla_expires_at=sla.isoformat(),
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            status="pending",
            risk_if_yes="A new Telegram bot exists in the world and stores a token on Railway env",
            risk_if_no="Workspace cannot send Telegram outbound; manual messaging only",
            created_at=now.isoformat(),
        )
        saved_approval = approvals.enqueue(approval)
        return ProvisionOutcome(
            action="queue_per_client_bot_provision",
            reason="per-client bot provisioning queued for operator (BotFather step)",
            channel_id=saved.id,
            approval_id=saved_approval.id,
            requires_operator_step=True,
            operator_step_description=(
                f"1) Open @BotFather in Telegram, run `/newbot`, name it "
                f"`@{workspace.slug}-Nexus`. "
                f"2) Copy the token to Railway env var "
                f"`{req.bot_token_env_name}`. "
                f"3) Approve approval {saved_approval.id}. "
                f"4) Hermes will then call channels.mark_active({saved.id})."
            ),
            audit_payload={
                "workspace_slug": workspace.slug,
                "channel_id": saved.id,
                "approval_id": saved_approval.id,
                "env_var": req.bot_token_env_name,
            },
        )

    # ── Path 3: shared ops bot mapping ──────────────────────────────
    if req.kind == "telegram_chat" and not req.external_id:
        # Map @UniteGroupOps bot's chat to the workspace
        channel = Channel(
            id=f"ch-{workspace.slug}-ops",
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            kind="telegram_chat",
            external_id=f"pending-ops-{workspace.slug}",
            display_name=req.display_name or "Unite-Group Ops",
            inbound_route=req.inbound_route,
            bot_token_env_name=SHARED_OPS_BOT_ENV,
            status="pending",
            created_at=now.isoformat(),
        )
        saved = channels.save(channel)
        sla = now + timedelta(hours=APPROVAL_SLA_HOURS)
        approval = ApprovalRequest(
            id=f"ap-chan-{workspace.slug}-ops",
            requested_by=requested_by,
            action="channel:map_ops_chat",
            why_now=f"operator chat for workspace {workspace.slug} not yet mapped",
            reversibility="reversible",
            payload={
                "workspace_slug": workspace.slug,
                "channel_id": saved.id,
            },
            sla_expires_at=sla.isoformat(),
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            status="pending",
            risk_if_no="Ops chat for this workspace remains unmapped; founder-level notifications must be routed elsewhere",
            created_at=now.isoformat(),
        )
        saved_approval = approvals.enqueue(approval)
        return ProvisionOutcome(
            action="queue_operator_bot_provision",
            reason="ops chat mapping queued for operator confirmation",
            channel_id=saved.id,
            approval_id=saved_approval.id,
            requires_operator_step=True,
            operator_step_description=(
                f"1) In @UniteGroupOps, capture the Telegram chat_id you want "
                f"to use for this workspace's ops notifications. "
                f"2) Approve approval {saved_approval.id} with the chat_id "
                f"in the decision_note. "
                f"3) Hermes will then call channels.mark_active({saved.id}) "
                f"with the captured chat_id."
            ),
            audit_payload={
                "workspace_slug": workspace.slug,
                "channel_id": saved.id,
                "approval_id": saved_approval.id,
            },
        )

    # Anything else: rejected
    return ProvisionOutcome(
        action="rejected",
        reason=(
            f"unsupported provisioning request: kind={req.kind!r}, "
            f"external_id={req.external_id!r}"
        ),
    )


# ============================================================
# Activation (after operator step completes)
# ============================================================

def activate_pending_channel(
    channel_id: str,
    *,
    external_id: str,
    channels: ChannelStore,
    now: datetime | None = None,
) -> ProvisionOutcome:
    """Mark a `pending` channel as `active` after the operator step
    (BotFather create or chat id capture) is complete."""
    now = now or datetime.now(timezone.utc)
    channel = channels.get(channel_id)
    if channel is None:
        return ProvisionOutcome(
            action="rejected",
            reason=f"channel {channel_id!r} not found",
        )
    if channel.status != "pending":
        return ProvisionOutcome(
            action="rejected",
            reason=f"channel must be in 'pending' to activate, got {channel.status!r}",
        )
    if err := _validate_external_id(channel.kind, external_id):
        return ProvisionOutcome(action="rejected", reason=err)
    updated = channels.mark_active(channel_id, now.isoformat())
    return ProvisionOutcome(
        action="map_existing_chat",
        reason="channel activated post-operator-step",
        channel_id=updated.id,
        audit_payload={
            "channel_id": updated.id,
            "activated_external_id": external_id,
            "provisioned_at": now.isoformat(),
        },
    )
