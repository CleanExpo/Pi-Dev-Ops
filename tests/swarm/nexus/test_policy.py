"""Tests for swarm.nexus.policy — the autonomous reversibility gate.

Covers: the reversibility->policy matrix (incl. fail-closed on unknown),
auto-approval of reversible/low with no human, routing of medium/high to
HITL, escalation of irreversible, and fail-closed on non-pending requests.
Every path must write an audit row.
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timedelta, timezone

import pytest

from swarm.nexus import audit as audit_mod
from swarm.nexus.policy import (
    REVERSIBILITY_POLICY,
    PolicyDecision,
    auto_gate,
    classify_policy,
)
from swarm.nexus.types import ApprovalRequest


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
        return [r for r in self.store.values() if r.status == "pending"]


def _req(reversibility, *, status="pending", rid="ap-1"):
    now = datetime(2026, 6, 30, 12, 0, tzinfo=timezone.utc)
    return ApprovalRequest(
        id=rid,
        requested_by="swarm:cfo",
        action="spend:ad-budget",
        why_now="campaign window",
        reversibility=reversibility,
        payload={"amount_usd": 50},
        sla_expires_at=(now + timedelta(hours=72)).isoformat(),
        status=status,
    )


# ---- classify_policy matrix ----

@pytest.mark.parametrize("rev,expected", [
    ("reversible", "auto"),
    ("low", "auto"),
    ("medium", "approval"),
    ("high", "approval"),
    ("irreversible", "escalation"),
])
def test_classify_matrix(rev, expected):
    assert classify_policy(rev) == expected
    assert REVERSIBILITY_POLICY[rev] == expected


def test_classify_unknown_fails_closed():
    assert classify_policy("totally-unknown") == "escalation"


# ---- auto tier: auto-approve, no human ----

@pytest.mark.parametrize("rev", ["reversible", "low"])
def test_auto_tier_auto_approves(rev, temp_audit_key):
    store = StubApprovalStore()
    req = _req(rev)
    store.enqueue(req)
    d = auto_gate(req, approvals=store, actor="autonomous-gate")
    assert isinstance(d, PolicyDecision)
    assert d.policy_level == "auto"
    assert d.auto_decided is True
    assert d.approval.status == "approved"
    assert d.approval.decided_by == "autonomous-gate"
    assert store.get(req.id).status == "approved"
    assert d.audit_row is not None
    assert d.audit_row.policy_level == "auto"
    assert d.audit_row.result == "ok"


# ---- approval tier: route to HITL, leave pending ----

@pytest.mark.parametrize("rev", ["medium", "high"])
def test_approval_tier_routes_pending(rev, temp_audit_key):
    store = StubApprovalStore()
    req = _req(rev)
    store.enqueue(req)
    d = auto_gate(req, approvals=store)
    assert d.policy_level == "approval"
    assert d.auto_decided is False
    assert store.get(req.id).status == "pending"   # untouched — human still decides
    assert d.audit_row.policy_level == "approval"


# ---- escalation tier: never auto, leave pending ----

def test_irreversible_escalates(temp_audit_key):
    store = StubApprovalStore()
    req = _req("irreversible")
    store.enqueue(req)
    d = auto_gate(req, approvals=store)
    assert d.policy_level == "escalation"
    assert d.auto_decided is False
    assert store.get(req.id).status == "pending"
    assert d.audit_row.policy_level == "escalation"


# ---- fail closed on non-pending ----

def test_non_pending_not_redecided(temp_audit_key):
    store = StubApprovalStore()
    req = _req("reversible", status="approved")
    store.enqueue(req)
    d = auto_gate(req, approvals=store)
    assert d.auto_decided is False
    assert d.audit_row.result == "denied"
    assert "already" in d.reason
