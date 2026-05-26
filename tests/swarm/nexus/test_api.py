"""Contract tests for app.server.routes.nexus — Pi-CEO FastAPI surface.

Uses FastAPI TestClient with stub stores injected via app.state. Bypasses
the real auth layer via dependency override.
"""
from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import replace
from typing import Iterable

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.routes.nexus import (
    router as nexus_router,
    webhooks_router,
)
from swarm.nexus.types import (
    ApprovalRequest,
    Channel,
    Client,
    Loop,
    Workspace,
)


# ============================================================
# Stub stores
# ============================================================


class StubClientStore:
    def __init__(self):
        self.by_id: dict[str, Client] = {}

    def save(self, client):
        self.by_id[client.id] = client
        return client

    def get(self, client_id):
        return self.by_id.get(client_id)


class StubWorkspaceStore:
    def __init__(self):
        self.by_id: dict[str, Workspace] = {}
        self.by_slug: dict[str, Workspace] = {}

    def save(self, ws):
        self.by_id[ws.id] = ws
        self.by_slug[ws.slug] = ws
        return ws

    def get(self, ws_id):
        return self.by_id.get(ws_id)

    def get_by_slug(self, slug):
        return self.by_slug.get(slug)

    def slug_taken(self, slug):
        return slug in self.by_slug


class StubChannelStore:
    def __init__(self):
        self.saved: list[Channel] = []

    def save(self, c):
        self.saved.append(c)
        return c

    def get(self, channel_id):
        for c in self.saved:
            if c.id == channel_id:
                return c
        return None

    def list_for_workspace(self, ws_id):
        return [c for c in self.saved if c.workspace_id == ws_id]

    def mark_active(self, channel_id, provisioned_at):
        for i, c in enumerate(self.saved):
            if c.id == channel_id:
                updated = replace(c, status="active", provisioned_at=provisioned_at)
                self.saved[i] = updated
                return updated
        raise KeyError(channel_id)


class StubLoopStore:
    def __init__(self):
        self.saved: list[Loop] = []

    def upsert(self, loop):
        self.saved.append(loop)
        return loop

    def list_for_workspace(self, ws_id):
        return [l for l in self.saved if l.workspace_id == ws_id]


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
            existing, status=new_status, decided_by=decided_by,
            decided_at=decided_at, decision_note=decision_note,
        )
        self.store[approval_id] = updated
        return updated

    def list_pending(self, *, workspace_slug=None, sla_expired_only=False, now=None):
        for req in self.store.values():
            if req.status != "pending":
                continue
            if workspace_slug and req.workspace_slug != workspace_slug:
                continue
            yield req

    def list_all(self, *, workspace_slug=None):
        for req in self.store.values():
            if workspace_slug and req.workspace_slug != workspace_slug:
                continue
            yield req


class StubAuditStore:
    def __init__(self):
        self.rows: list = []

    def append(self, row):
        self.rows.append(row)
        return row.id

    def list(self, *, workspace_id=None):
        return list(self.rows)


class StubOutcomesStore:
    def __init__(self):
        self.rows: list = []

    def list(self, *, workspace_id=None):
        return list(self.rows)


class StubLLM:
    def __init__(self, response: dict | None = None):
        self._payload = json.dumps(response or {
            "industry": "restoration",
            "scope_summary": "test",
            "estimated_budget_aud": 2000,
            "compliance_flags": [],
            "qualified": True,
            "rationale": "ok",
            "requires_approval": False,
            "approval_reason": None,
        })

    def complete(self, *, system, user, max_tokens=1024, temperature=0.3):
        return self._payload


# ============================================================
# Test app fixture
# ============================================================


@pytest.fixture
def app(tmp_path, monkeypatch):
    # Isolate audit key path so build_audit_row doesn't try to write ~/.hermes
    from swarm.nexus import audit as audit_mod
    monkeypatch.setattr(audit_mod, "AUDIT_KEY_PATH", tmp_path / "audit-key")

    app = FastAPI()
    app.include_router(nexus_router)
    app.include_router(webhooks_router)
    app.state.nexus_stores = {
        "clients": StubClientStore(),
        "workspaces": StubWorkspaceStore(),
        "channels": StubChannelStore(),
        "loops": StubLoopStore(),
        "approvals": StubApprovalStore(),
        "audit": StubAuditStore(),
        "outcomes": StubOutcomesStore(),
        "llm": StubLLM(),
    }
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


# ============================================================
# Health
# ============================================================


class TestHealth:
    def test_health_returns_ok(self, client):
        r = client.get("/api/nexus/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


# ============================================================
# Intake → qualify → approve → workspace flow
# ============================================================


class TestOnboardingFlow:
    def test_intake_creates_client(self, client, app):
        r = client.post("/api/nexus/clients/intake", json={
            "legal_name": "Acme Restoration Pty Ltd",
            "display_name": "Acme",
            "founder_id": "phill",
            "intake_source": "voice",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["status"] == "intake"
        assert data["client_id"].startswith("c-")
        # Stored
        store = app.state.nexus_stores["clients"]
        assert data["client_id"] in store.by_id

    def test_intake_rejects_invalid_intake_source(self, client):
        r = client.post("/api/nexus/clients/intake", json={
            "legal_name": "X", "display_name": "X",
            "founder_id": "phill",
            "intake_source": "carrier-pigeon",
        })
        assert r.status_code == 422

    def test_intake_rejects_missing_fields(self, client):
        r = client.post("/api/nexus/clients/intake", json={
            "legal_name": "X",
        })
        assert r.status_code == 422

    def test_qualify_unknown_client_404(self, client):
        r = client.post(
            "/api/nexus/clients/c-nonexistent/qualify",
            json={"force_rerun": False},
        )
        assert r.status_code == 404

    def test_qualify_happy_path(self, client, app):
        # 1. Create client
        r1 = client.post("/api/nexus/clients/intake", json={
            "legal_name": "Acme", "display_name": "Acme",
            "founder_id": "phill", "intake_source": "voice",
        })
        client_id = r1.json()["client_id"]
        # 2. Qualify
        r2 = client.post(
            f"/api/nexus/clients/{client_id}/qualify",
            json={"raw_intake_override": "IICRC restoration scope"},
        )
        assert r2.status_code == 200
        data = r2.json()
        assert data["status"] == "qualified"
        assert "qualification" in data
        assert data["requires_approval"] is False

    def test_approve_qualification_happy_path(self, client, app):
        store = app.state.nexus_stores["clients"]
        c = Client(
            id="c-1", founder_id="phill", legal_name="Acme",
            display_name="Acme", status="qualified",
        )
        store.save(c)
        r = client.post(
            "/api/nexus/clients/c-1/approve-qualification",
            json={"decision": "approved", "note": "looks good"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "qualified"

    def test_approve_qualification_denied_returns_intake(self, client, app):
        store = app.state.nexus_stores["clients"]
        store.save(Client(
            id="c-1", founder_id="phill", legal_name="Acme",
            display_name="Acme", status="qualified",
        ))
        r = client.post(
            "/api/nexus/clients/c-1/approve-qualification",
            json={"decision": "denied"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "intake"

    def test_create_workspace_happy_path(self, client, app):
        store = app.state.nexus_stores["clients"]
        store.save(Client(
            id="c-1", founder_id="phill", legal_name="Acme",
            display_name="Acme", status="qualified",
        ))
        r = client.post("/api/nexus/clients/c-1/workspace", json={
            "slug": "acme-restoration",
            "display_name": "Acme Restoration",
            "linear_team_id": "team-1",
        })
        assert r.status_code == 201
        assert r.json()["workspace_id"] == "ws-c-1"
        assert r.json()["slug"] == "acme-restoration"

    def test_create_workspace_slug_taken_422(self, client, app):
        ws_store = app.state.nexus_stores["workspaces"]
        ws_store.save(Workspace(
            id="ws-other", client_id="c-other",
            slug="acme-restoration", display_name="x",
            linear_team_id="t-1",
        ))
        c_store = app.state.nexus_stores["clients"]
        c_store.save(Client(
            id="c-1", founder_id="phill", legal_name="A",
            display_name="A", status="qualified",
        ))
        r = client.post("/api/nexus/clients/c-1/workspace", json={
            "slug": "acme-restoration",
            "display_name": "X",
            "linear_team_id": "t-1",
        })
        assert r.status_code == 422


# ============================================================
# Channels
# ============================================================


class TestChannels:
    def test_provision_unknown_workspace_404(self, client):
        r = client.post("/api/nexus/workspaces/ws-x/channels", json={
            "kind": "telegram_chat",
            "display_name": "x",
            "external_id": "123456789",
        })
        assert r.status_code == 404

    def test_provision_existing_chat_happy_path(self, client, app):
        ws_store = app.state.nexus_stores["workspaces"]
        ws_store.save(Workspace(
            id="ws-1", client_id="c-1", slug="acme",
            display_name="A", linear_team_id="t-1",
        ))
        r = client.post("/api/nexus/workspaces/ws-1/channels", json={
            "kind": "telegram_chat",
            "display_name": "Acme team",
            "external_id": "-1001234567890",
        })
        assert r.status_code == 201
        data = r.json()
        assert data["action"] == "map_existing_chat"

    def test_provision_invalid_external_id_422(self, client, app):
        ws_store = app.state.nexus_stores["workspaces"]
        ws_store.save(Workspace(
            id="ws-1", client_id="c-1", slug="acme",
            display_name="A", linear_team_id="t-1",
        ))
        r = client.post("/api/nexus/workspaces/ws-1/channels", json={
            "kind": "telegram_chat",
            "display_name": "x",
            "external_id": "not-a-number",
        })
        assert r.status_code == 422


# ============================================================
# Loops
# ============================================================


class TestLoops:
    def test_enable_unknown_loop_kind_422(self, client):
        r = client.post(
            "/api/nexus/workspaces/ws-1/loops/bogus-kind/enable",
            json={"cadence": "0 * * * *", "config": {}},
        )
        assert r.status_code == 422

    def test_enable_loop_unknown_workspace_404(self, client):
        r = client.post(
            "/api/nexus/workspaces/ws-nonexistent/loops/discovery/enable",
            json={"cadence": "0 * * * *", "config": {}},
        )
        assert r.status_code == 404

    def test_enable_loop_happy_path(self, client, app):
        c_store = app.state.nexus_stores["clients"]
        ws_store = app.state.nexus_stores["workspaces"]
        c_store.save(Client(
            id="c-1", founder_id="phill", legal_name="A",
            display_name="A", status="wired",
        ))
        ws_store.save(Workspace(
            id="ws-1", client_id="c-1", slug="acme",
            display_name="A", linear_team_id="t-1",
        ))
        r = client.post(
            "/api/nexus/workspaces/ws-1/loops/discovery/enable",
            json={"cadence": "0 */6 * * *", "config": {"persona": "restoreassist"}},
        )
        assert r.status_code == 201
        assert r.json()["loop_kind"] == "discovery"


# ============================================================
# Approvals
# ============================================================


class TestApprovalsList:
    def test_list_empty(self, client):
        r = client.get("/api/nexus/approvals")
        assert r.status_code == 200
        assert r.json() == {"approvals": [], "count": 0}

    def test_list_pending_filter(self, client, app):
        store = app.state.nexus_stores["approvals"]
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        store.enqueue(ApprovalRequest(
            id="ap-1", requested_by="x", action="qualification:approve",
            why_now="x", reversibility="low", payload={},
            sla_expires_at=(now + timedelta(hours=72)).isoformat(),
            workspace_slug="acme", status="pending",
        ))
        store.enqueue(ApprovalRequest(
            id="ap-2", requested_by="x", action="other",
            why_now="x", reversibility="low", payload={},
            sla_expires_at=(now + timedelta(hours=72)).isoformat(),
            workspace_slug="acme", status="approved",
        ))
        r = client.get("/api/nexus/approvals?status_filter=pending")
        assert r.status_code == 200
        data = r.json()
        assert data["count"] == 1
        assert data["approvals"][0]["id"] == "ap-1"


class TestApprovalDecide:
    def test_decide_unknown_approval_422(self, client):
        r = client.post(
            "/api/nexus/approvals/ap-x/decide",
            json={"decision": "approved"},
        )
        assert r.status_code == 422

    def test_decide_approved_happy_path(self, client, app):
        store = app.state.nexus_stores["approvals"]
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        store.enqueue(ApprovalRequest(
            id="ap-1", requested_by="x", action="qualification:approve",
            why_now="x", reversibility="low", payload={},
            sla_expires_at=(now + timedelta(hours=72)).isoformat(),
            workspace_slug="acme", status="pending",
        ))
        r = client.post(
            "/api/nexus/approvals/ap-1/decide",
            json={"decision": "approved", "note": "ok"},
        )
        assert r.status_code == 200
        assert r.json()["status"] == "approved"
        # Audit row was persisted
        assert len(app.state.nexus_stores["audit"].rows) == 1

    def test_decide_invalid_decision_422(self, client):
        r = client.post(
            "/api/nexus/approvals/ap-1/decide",
            json={"decision": "maybe"},
        )
        assert r.status_code == 422


# ============================================================
# Outcomes / audit reads
# ============================================================


class TestReads:
    def test_outcomes_empty(self, client):
        r = client.get("/api/nexus/outcomes")
        assert r.status_code == 200
        assert r.json() == {"outcomes": [], "count": 0}

    def test_audit_empty(self, client):
        r = client.get("/api/nexus/audit")
        assert r.status_code == 200
        assert r.json() == {"audit": [], "count": 0}


# ============================================================
# Webhooks
# ============================================================


class TestWebhooks:
    @pytest.mark.parametrize("path,env", [
        ("/webhooks/stripe", "STRIPE_WEBHOOK_SECRET"),
        ("/webhooks/vercel", "VERCEL_WEBHOOK_SECRET"),
        ("/webhooks/posthog", "POSTHOG_WEBHOOK_SECRET"),
        ("/webhooks/sentry", "SENTRY_WEBHOOK_SECRET"),
        ("/webhooks/linear", "LINEAR_WEBHOOK_SECRET"),
    ])
    def test_webhook_rejects_missing_signature(self, client, path, env, monkeypatch):
        monkeypatch.setenv(env, "test-secret")
        r = client.post(path, json={"event": "test"})
        assert r.status_code == 401

    def test_webhook_accepts_valid_signature(self, client, monkeypatch):
        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "test-secret")
        body = b'{"event":"invoice.paid"}'
        sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()
        r = client.post(
            "/webhooks/stripe",
            content=body,
            headers={"X-Webhook-Signature": sig, "Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert r.json()["source"] == "stripe"

    def test_webhook_no_secret_env_rejects(self, client, monkeypatch):
        monkeypatch.delenv("STRIPE_WEBHOOK_SECRET", raising=False)
        r = client.post("/webhooks/stripe", json={"event": "x"})
        assert r.status_code == 401
