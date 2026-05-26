"""Tests for swarm.nexus.channels — Telegram provisioning request layer.

≥15 tests covering: every provisioning path (map_existing / per-client /
shared ops), validation rejections, env-var format enforcement, workspace
mismatch refusal, approval queue interactions, activation post-step.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

import pytest

from swarm.nexus.channels import (
    PER_CLIENT_BOT_ENV_PREFIX,
    SHARED_OPS_BOT_ENV,
    ProvisionRequest,
    activate_pending_channel,
    request_provision,
)
from swarm.nexus.types import ApprovalRequest, Channel, Workspace


class StubChannelStore:
    def __init__(self):
        self.saved: list[Channel] = []
        self.activated: list[tuple[str, str]] = []

    def save(self, channel):
        self.saved.append(channel)
        return channel

    def get(self, channel_id):
        for c in self.saved:
            if c.id == channel_id:
                return c
        return None

    def list_for_workspace(self, workspace_id):
        return [c for c in self.saved if c.workspace_id == workspace_id]

    def mark_active(self, channel_id, provisioned_at):
        self.activated.append((channel_id, provisioned_at))
        for i, c in enumerate(self.saved):
            if c.id == channel_id:
                from dataclasses import replace
                updated = replace(c, status="active", provisioned_at=provisioned_at)
                self.saved[i] = updated
                return updated
        raise KeyError(channel_id)


class StubApprovalStore:
    def __init__(self):
        self.enqueued: list[ApprovalRequest] = []

    def enqueue(self, req):
        self.enqueued.append(req)
        return req


def _workspace(slug="acme-restoration") -> Workspace:
    return Workspace(
        id=f"ws-{slug}",
        client_id=f"c-{slug}",
        slug=slug,
        display_name="Acme",
        linear_team_id="team-1",
    )


# ============================================================
# Path 1: map_existing_chat
# ============================================================

class TestMapExistingChat:
    def test_telegram_chat_with_external_id_saves_active(self):
        ws = _workspace()
        chs, aps = StubChannelStore(), StubApprovalStore()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_chat", display_name="Acme team",
                external_id="-1001234567890",
            ),
            ws, channels=chs, approvals=aps, requested_by="hermes-delivery",
        )
        assert out.action == "map_existing_chat"
        assert out.channel_id is not None
        assert len(chs.saved) == 1
        assert chs.saved[0].status == "active"
        assert chs.saved[0].external_id == "-1001234567890"
        assert len(aps.enqueued) == 0  # no approval needed when already set up

    def test_telegram_bot_with_existing_id_requires_env_var(self):
        ws = _workspace()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_bot", display_name="bot",
                external_id="123456789",
                # missing bot_token_env_name
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="hermes-delivery",
        )
        assert out.action == "rejected"
        assert "bot_token_env_name" in out.reason

    def test_telegram_bot_with_existing_id_and_env_var_saves_active(self):
        ws = _workspace()
        chs, aps = StubChannelStore(), StubApprovalStore()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_bot", display_name="bot",
                external_id="123456789",
                bot_token_env_name=f"{PER_CLIENT_BOT_ENV_PREFIX}ACME",
            ),
            ws, channels=chs, approvals=aps, requested_by="hermes-delivery",
        )
        assert out.action == "map_existing_chat"
        assert chs.saved[0].status == "active"


# ============================================================
# Path 2: per-client bot provision (BotFather step queued)
# ============================================================

class TestPerClientBotProvision:
    def test_queues_approval_and_saves_pending(self):
        ws = _workspace()
        chs, aps = StubChannelStore(), StubApprovalStore()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_bot", display_name="Acme Nexus",
                bot_token_env_name=f"{PER_CLIENT_BOT_ENV_PREFIX}ACME",
            ),
            ws, channels=chs, approvals=aps, requested_by="hermes-delivery",
        )
        assert out.action == "queue_per_client_bot_provision"
        assert out.requires_operator_step is True
        assert "BotFather" in (out.operator_step_description or "")
        assert chs.saved[0].status == "pending"
        assert len(aps.enqueued) == 1
        assert aps.enqueued[0].action == "channel:provision_telegram_bot"
        assert aps.enqueued[0].status == "pending"

    def test_missing_env_var_name_rejected(self):
        ws = _workspace()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_bot", display_name="x",
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.action == "rejected"

    def test_wrong_env_var_prefix_rejected(self):
        ws = _workspace()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_bot", display_name="x",
                bot_token_env_name="GENERIC_TOKEN",  # missing NEXUS_BOT_TOKEN_ prefix
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.action == "rejected"
        assert PER_CLIENT_BOT_ENV_PREFIX in out.reason

    def test_invalid_env_var_format_rejected(self):
        ws = _workspace()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_bot", display_name="x",
                bot_token_env_name="lowercase_var",
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.action == "rejected"
        assert "UPPER_SNAKE_CASE" in out.reason


# ============================================================
# Path 3: shared ops bot mapping
# ============================================================

class TestSharedOpsBotMapping:
    def test_queues_for_chat_id_capture(self):
        ws = _workspace()
        chs, aps = StubChannelStore(), StubApprovalStore()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_chat", display_name="Acme Ops",
            ),
            ws, channels=chs, approvals=aps, requested_by="hermes-delivery",
        )
        assert out.action == "queue_operator_bot_provision"
        assert chs.saved[0].bot_token_env_name == SHARED_OPS_BOT_ENV
        assert chs.saved[0].status == "pending"
        assert len(aps.enqueued) == 1
        assert aps.enqueued[0].action == "channel:map_ops_chat"


# ============================================================
# Workspace cross-check (anti-spoofing)
# ============================================================

class TestWorkspaceCrosscheck:
    def test_id_mismatch_rejected(self):
        ws = _workspace("acme")
        out = request_provision(
            ProvisionRequest(
                workspace_id="ws-wrong",  # mismatch
                workspace_slug="acme",
                kind="telegram_chat",
                display_name="x",
                external_id="123456789",
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.action == "rejected"
        assert "mismatch" in out.reason

    def test_slug_mismatch_rejected(self):
        ws = _workspace("acme")
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id,
                workspace_slug="evil-slug",
                kind="telegram_chat",
                display_name="x",
                external_id="123456789",
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.action == "rejected"


# ============================================================
# Telegram chat id format validation
# ============================================================

class TestExternalIdValidation:
    @pytest.mark.parametrize("good_id", [
        "1234567",          # positive private chat
        "-1001234567890",   # group/supergroup
        "1234567890",
    ])
    def test_accepts_good_telegram_id(self, good_id):
        ws = _workspace()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_chat", display_name="x",
                external_id=good_id,
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.action == "map_existing_chat"

    @pytest.mark.parametrize("bad_id", [
        "abc",
        "12345",  # too short (5 digits)
        "1234567890123456",  # too long (16 digits)
        "-abc",
        "12.34",
    ])
    def test_rejects_bad_telegram_id(self, bad_id):
        ws = _workspace()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_chat", display_name="x",
                external_id=bad_id,
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.action == "rejected"

    def test_explicit_no_external_id_routes_to_shared_ops(self):
        """external_id=None (the truly-missing case) routes to shared ops bot path."""
        ws = _workspace()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_chat", display_name="x",
                external_id=None,
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.action == "queue_operator_bot_provision"

    def test_email_kind_requires_at_sign(self):
        ws = _workspace()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="email", display_name="x",
                external_id="not-an-email",
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.action == "rejected"
        assert "@" in out.reason


# ============================================================
# activate_pending_channel
# ============================================================

class TestActivatePending:
    def test_happy_path_pending_to_active(self):
        ws = _workspace()
        chs, aps = StubChannelStore(), StubApprovalStore()
        # First, queue a pending bot
        request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_bot", display_name="bot",
                bot_token_env_name=f"{PER_CLIENT_BOT_ENV_PREFIX}ACME",
            ),
            ws, channels=chs, approvals=aps, requested_by="x",
        )
        channel_id = chs.saved[0].id
        # Now activate it with the freshly captured external id
        out = activate_pending_channel(
            channel_id,
            external_id="987654321",
            channels=chs,
        )
        assert out.action == "map_existing_chat"
        assert chs.saved[0].status == "active"
        assert chs.activated == [(channel_id, chs.saved[0].provisioned_at)]

    def test_unknown_channel_rejected(self):
        out = activate_pending_channel(
            "ch-nonexistent",
            external_id="123456789",
            channels=StubChannelStore(),
        )
        assert out.action == "rejected"
        assert "not found" in out.reason

    def test_already_active_channel_rejected(self):
        chs = StubChannelStore()
        ws = _workspace()
        # Insert an already-active channel
        already_active = Channel(
            id="ch-already",
            workspace_id=ws.id, workspace_slug=ws.slug,
            kind="telegram_chat", external_id="123456789",
            display_name="x", inbound_route="margot",
            status="active",
        )
        chs.saved.append(already_active)
        out = activate_pending_channel(
            "ch-already",
            external_id="123456789",
            channels=chs,
        )
        assert out.action == "rejected"
        assert "pending" in out.reason

    def test_activate_with_bad_external_id_rejected(self):
        chs = StubChannelStore()
        ws = _workspace()
        pending = Channel(
            id="ch-pending",
            workspace_id=ws.id, workspace_slug=ws.slug,
            kind="telegram_chat", external_id="pending-acme",
            display_name="x", inbound_route="margot",
            status="pending",
        )
        chs.saved.append(pending)
        out = activate_pending_channel(
            "ch-pending",
            external_id="not-a-chat-id",
            channels=chs,
        )
        assert out.action == "rejected"


# ============================================================
# Audit payload sanity
# ============================================================

class TestAuditPayload:
    def test_map_existing_carries_workspace_slug(self):
        ws = _workspace()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_chat", display_name="x",
                external_id="123456789",
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.audit_payload["workspace_slug"] == ws.slug
        assert out.audit_payload["kind"] == "telegram_chat"
        assert out.audit_payload["external_id"] == "123456789"

    def test_per_client_bot_audit_includes_env_var(self):
        ws = _workspace()
        out = request_provision(
            ProvisionRequest(
                workspace_id=ws.id, workspace_slug=ws.slug,
                kind="telegram_bot", display_name="x",
                bot_token_env_name=f"{PER_CLIENT_BOT_ENV_PREFIX}ACME",
            ),
            ws, channels=StubChannelStore(), approvals=StubApprovalStore(),
            requested_by="x",
        )
        assert out.audit_payload["env_var"] == f"{PER_CLIENT_BOT_ENV_PREFIX}ACME"


# ============================================================
# Constants smoke
# ============================================================

def test_per_client_env_prefix_constant():
    assert PER_CLIENT_BOT_ENV_PREFIX == "NEXUS_BOT_TOKEN_"


def test_shared_ops_env_constant():
    assert SHARED_OPS_BOT_ENV == "UNITE_GROUP_OPS_BOT_TOKEN"
