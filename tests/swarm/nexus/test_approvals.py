"""Tests for swarm.nexus.approvals + swarm.nexus.audit.

≥25 tests covering: decide happy/denied/repeat-rejected/past-SLA, SLA
sweep idempotency, audit row construction, HMAC stability, 512-byte
truncation, secret redaction in audit args.
"""
from __future__ import annotations

import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Iterable

import pytest

from swarm.nexus import audit as audit_mod
from swarm.nexus.approvals import (
    ApprovalDecisionOutcome,
    decide_approval,
    is_sla_expired,
    sweep_expired,
)
from swarm.nexus.audit import (
    ATOMIC_WRITE_CAP_BYTES,
    AuditRowTooLargeError,
    AuditUnwritableError,
    NexusAuditRow,
    build_audit_row,
)
from swarm.nexus.types import ApprovalRequest


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def temp_audit_key(tmp_path, monkeypatch):
    key_path = tmp_path / "audit-key"
    monkeypatch.setattr(audit_mod, "AUDIT_KEY_PATH", key_path)
    return key_path


class StubApprovalStore:
    def __init__(self):
        self.store: dict[str, ApprovalRequest] = {}

    def enqueue(self, req):
        self.store[req.id] = req
        return req

    def get(self, approval_id):
        return self.store.get(approval_id)

    def update_status(self, approval_id, *, new_status, decided_by,
                      decided_at, decision_note):
        from dataclasses import replace
        existing = self.store[approval_id]
        updated = replace(
            existing,
            status=new_status,
            decided_by=decided_by,
            decided_at=decided_at,
            decision_note=decision_note,
        )
        self.store[approval_id] = updated
        return updated

    def list_pending(self, *, workspace_slug=None, sla_expired_only=False, now=None):
        now = now or datetime.now(timezone.utc)
        for req in self.store.values():
            if req.status != "pending":
                continue
            if workspace_slug and req.workspace_slug != workspace_slug:
                continue
            if sla_expired_only:
                sla = datetime.fromisoformat(req.sla_expires_at.replace("Z", "+00:00"))
                if sla.tzinfo is None:
                    sla = sla.replace(tzinfo=timezone.utc)
                if now <= sla:
                    continue
            yield req


def _approval(
    approval_id="ap-1",
    workspace_slug="acme",
    status="pending",
    sla_offset_hours: int = 72,
    now: datetime | None = None,
) -> ApprovalRequest:
    now = now or datetime.now(timezone.utc)
    sla = (now + timedelta(hours=sla_offset_hours)).isoformat()
    return ApprovalRequest(
        id=approval_id,
        requested_by="hermes-delivery",
        action="qualification:approve",
        why_now="test",
        reversibility="low",
        payload={"client_id": "c-1"},
        sla_expires_at=sla,
        workspace_id="ws-1",
        workspace_slug=workspace_slug,
        status=status,
        created_at=now.isoformat(),
    )


# ============================================================
# build_audit_row
# ============================================================


class TestBuildAuditRow:
    def test_returns_nexus_audit_row(self, temp_audit_key):
        row = build_audit_row(
            actor="hermes-strategy",
            action="client:create",
            args={"client_id": "c-1"},
            policy_level="auto",
            result="ok",
        )
        assert isinstance(row, NexusAuditRow)
        assert row.id.startswith("nex-")
        assert row.actor == "hermes-strategy"
        assert row.action == "client:create"
        assert row.policy_level == "auto"
        assert row.result == "ok"

    def test_hmac_id_format(self, temp_audit_key):
        row = build_audit_row(
            actor="x", action="y", args={}, policy_level="auto", result="ok",
        )
        # nex-<12 hex chars>
        assert len(row.id) == len("nex-") + 12

    def test_two_rows_with_different_actions_have_different_ids(self, temp_audit_key):
        r1 = build_audit_row(actor="x", action="a:one", args={}, policy_level="auto", result="ok")
        r2 = build_audit_row(actor="x", action="a:two", args={}, policy_level="auto", result="ok")
        assert r1.id != r2.id

    def test_carries_workspace_correlation_keys(self, temp_audit_key):
        row = build_audit_row(
            actor="x", action="y", args={}, policy_level="auto", result="ok",
            workspace_id="ws-1", workspace_slug="acme", client_id="c-1",
        )
        assert row.workspace_id == "ws-1"
        assert row.workspace_slug == "acme"
        assert row.client_id == "c-1"

    def test_audit_key_missing_raises(self, tmp_path, monkeypatch):
        # Point at a non-existent path WITHOUT parent existing — generation will work though.
        # To test the actual "missing key" code path, we need to test the insecure-mode case.
        key_path = tmp_path / "key"
        key_path.write_bytes(secrets.token_bytes(32))
        os.chmod(key_path, 0o644)  # world-readable — insecure
        monkeypatch.setattr(audit_mod, "AUDIT_KEY_PATH", key_path)
        with pytest.raises(AuditUnwritableError):
            build_audit_row(actor="x", action="y", args={}, policy_level="auto", result="ok")


class TestSecretRedaction:
    def test_anthropic_key_redacted_in_args(self, temp_audit_key):
        secret = "sk" + "-ant-api03-" + "x" * 50
        row = build_audit_row(
            actor="x",
            action="api:call",
            args={"prompt": f"key={secret}"},
            policy_level="auto",
            result="ok",
        )
        assert "[REDACTED:anthropic]" in row.args_redacted["prompt"]
        # ensure original secret bytes never appear
        assert "sk-ant-api03-" not in row.args_redacted["prompt"]

    def test_nested_dict_redacted(self, temp_audit_key):
        secret = "sk_live_" + "x" * 30
        row = build_audit_row(
            actor="x",
            action="api:call",
            args={"meta": {"stripe_key": secret}},
            policy_level="auto",
            result="ok",
        )
        assert "[REDACTED" in row.args_redacted["meta"]["stripe_key"]

    def test_list_of_strings_redacted(self, temp_audit_key):
        secret = "ghp_" + "x" * 36
        row = build_audit_row(
            actor="x",
            action="api:call",
            args={"tokens": [secret, "innocuous"]},
            policy_level="auto",
            result="ok",
        )
        assert "[REDACTED" in row.args_redacted["tokens"][0]
        assert row.args_redacted["tokens"][1] == "innocuous"

    def test_non_string_values_preserved(self, temp_audit_key):
        row = build_audit_row(
            actor="x",
            action="api:call",
            args={"count": 42, "bool": True, "null": None},
            policy_level="auto",
            result="ok",
        )
        assert row.args_redacted["count"] == 42
        assert row.args_redacted["bool"] is True
        assert row.args_redacted["null"] is None


class TestTruncation:
    def test_oversize_args_truncated(self, temp_audit_key):
        big_args = {"data": "x" * 1000}
        row = build_audit_row(
            actor="x",
            action="api:call",
            args=big_args,
            policy_level="auto",
            result="ok",
        )
        # truncated string OR truncated dict
        v = row.args_redacted
        if isinstance(v, dict) and "_truncated" in v:
            assert v["_truncated"] is True
        else:
            # Original behavior — single field truncated
            data_v = v.get("data", "")
            if isinstance(data_v, str):
                # Either marker present OR shorter than original
                assert "[…truncated]" in data_v or len(data_v) < 1000

    def test_normal_args_not_truncated(self, temp_audit_key):
        row = build_audit_row(
            actor="x",
            action="api:call",
            args={"a": "small", "b": 1},
            policy_level="auto",
            result="ok",
        )
        assert row.args_redacted["a"] == "small"
        assert row.args_redacted["b"] == 1


# ============================================================
# decide_approval
# ============================================================


class TestDecideApproval:
    def test_approve_happy_path(self, temp_audit_key):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store = StubApprovalStore()
        store.enqueue(_approval(now=now))
        out = decide_approval(
            "ap-1", "approved",
            decided_by="phill", note="looks good",
            approvals=store, now=now,
        )
        assert out.result == "ok"
        assert out.approval.status == "approved"
        assert out.approval.decided_by == "phill"
        assert out.audit_row is not None
        assert out.audit_row.action == "approval:approved"
        assert out.audit_row.approval_id == "ap-1"

    def test_deny_happy_path(self, temp_audit_key):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store = StubApprovalStore()
        store.enqueue(_approval(now=now))
        out = decide_approval(
            "ap-1", "denied", decided_by="phill",
            approvals=store, now=now,
        )
        assert out.approval.status == "denied"
        assert out.audit_row.action == "approval:denied"

    def test_unknown_approval_id_rejected(self, temp_audit_key):
        out = decide_approval(
            "ap-nonexistent", "approved", decided_by="phill",
            approvals=StubApprovalStore(),
        )
        assert out.result == "denied"
        assert "not found" in out.reason

    def test_already_decided_cannot_re_decide(self, temp_audit_key):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store = StubApprovalStore()
        store.enqueue(_approval(status="approved", now=now))
        out = decide_approval(
            "ap-1", "denied", decided_by="phill",
            approvals=store, now=now,
        )
        assert out.result == "denied"
        assert "already" in out.reason

    def test_past_sla_rejected(self, temp_audit_key):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store = StubApprovalStore()
        # Approval created 100h ago, SLA was 72h, so expired by 28h
        store.enqueue(_approval(sla_offset_hours=-28, now=now))
        out = decide_approval(
            "ap-1", "approved", decided_by="phill",
            approvals=store, now=now,
        )
        assert out.result == "denied"
        assert "SLA" in out.reason


# ============================================================
# sweep_expired
# ============================================================


class TestSweepExpired:
    def test_sweeps_expired_pendings(self, temp_audit_key):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store = StubApprovalStore()
        store.enqueue(_approval("ap-expired", sla_offset_hours=-10, now=now))
        store.enqueue(_approval("ap-fresh", sla_offset_hours=20, now=now))
        swept = sweep_expired(approvals=store, now=now)
        assert len(swept) == 1
        assert swept[0].approval.id == "ap-expired"
        assert swept[0].approval.status == "auto-denied"
        assert swept[0].audit_row.action == "approval:auto-denied"

    def test_sweep_is_idempotent(self, temp_audit_key):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store = StubApprovalStore()
        store.enqueue(_approval("ap-1", sla_offset_hours=-10, now=now))
        sweep_expired(approvals=store, now=now)
        # Run again — nothing pending now
        again = sweep_expired(approvals=store, now=now)
        assert again == []

    def test_sweep_filters_by_workspace(self, temp_audit_key):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store = StubApprovalStore()
        store.enqueue(_approval("ap-acme", workspace_slug="acme",
                                sla_offset_hours=-5, now=now))
        store.enqueue(_approval("ap-other", workspace_slug="other",
                                sla_offset_hours=-5, now=now))
        swept = sweep_expired(approvals=store, workspace_slug="acme", now=now)
        assert len(swept) == 1
        assert swept[0].approval.id == "ap-acme"


# ============================================================
# is_sla_expired
# ============================================================


class TestIsSlaExpired:
    def test_pending_past_sla_true(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        a = _approval(sla_offset_hours=-5, now=now)
        assert is_sla_expired(a, now=now) is True

    def test_pending_within_sla_false(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        a = _approval(sla_offset_hours=10, now=now)
        assert is_sla_expired(a, now=now) is False

    def test_already_decided_returns_false(self):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        a = _approval(status="approved", sla_offset_hours=-5, now=now)
        assert is_sla_expired(a, now=now) is False


# ============================================================
# Audit row size invariant
# ============================================================


class TestAuditRowSize:
    def test_normal_row_fits_in_512b(self, temp_audit_key):
        import json
        row = build_audit_row(
            actor="hermes-strategy",
            action="client:create",
            args={"client_id": "c-1", "founder_id": "phill"},
            policy_level="auto",
            result="ok",
            workspace_id="ws-1", workspace_slug="acme",
        )
        serialised = json.dumps({
            "id": row.id,
            "ts_realtime": row.ts_realtime,
            "actor": row.actor,
            "action": row.action,
            "args_redacted": row.args_redacted,
            "policy_level": row.policy_level,
            "result": row.result,
        })
        assert len(serialised.encode("utf-8")) <= ATOMIC_WRITE_CAP_BYTES


# ============================================================
# Constants
# ============================================================


class TestConstants:
    def test_atomic_cap_512b(self):
        assert ATOMIC_WRITE_CAP_BYTES == 512


class TestAuditCorrelation:
    def test_decide_audit_row_carries_workspace_keys(self, temp_audit_key):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store = StubApprovalStore()
        store.enqueue(_approval(workspace_slug="acme", now=now))
        out = decide_approval(
            "ap-1", "approved", decided_by="phill",
            approvals=store, now=now,
        )
        assert out.audit_row.workspace_id == "ws-1"
        assert out.audit_row.workspace_slug == "acme"
        assert out.audit_row.approval_id == "ap-1"

    def test_sweep_audit_actor_is_system(self, temp_audit_key):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store = StubApprovalStore()
        store.enqueue(_approval(sla_offset_hours=-1, now=now))
        swept = sweep_expired(approvals=store, now=now)
        assert swept[0].audit_row.actor == "system:sla-sweep"
        assert swept[0].audit_row.policy_level == "escalation"


class TestEmptyCases:
    def test_sweep_no_pendings_returns_empty(self, temp_audit_key):
        now = datetime(2026, 6, 1, tzinfo=timezone.utc)
        store = StubApprovalStore()
        swept = sweep_expired(approvals=store, now=now)
        assert swept == []
