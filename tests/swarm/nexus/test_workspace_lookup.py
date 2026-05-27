"""Focused tests for SupabaseWorkspaceLookup (C6) + webhook handler wiring."""
from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request

from swarm.nexus.store_factory import SupabaseWorkspaceLookup, build_production_stores


class _StubUrlopen:
    def __init__(self, *, body: bytes = b"[]", raise_exc: Exception | None = None):
        self.calls: list[urllib.request.Request] = []
        self._body = body
        self._raise = raise_exc

    def __call__(self, req: urllib.request.Request, timeout: int = 0):
        self.calls.append(req)
        if self._raise:
            raise self._raise

        class _Resp:
            def __init__(self_inner, b):
                self_inner._b = b

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return None

            def read(self_inner):
                return self_inner._b

        return _Resp(self._body)


# ============================================================
# SupabaseWorkspaceLookup
# ============================================================


class TestSupabaseWorkspaceLookup:
    def test_stripe_customer_hit(self, monkeypatch):
        stub = _StubUrlopen(body=b'[{"id":"ws-ccw-crm","slug":"ccw-crm"}]')
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        lookup = SupabaseWorkspaceLookup(
            url="https://example.supabase.co", service_role_key="k",
        )
        assert lookup.by_stripe_customer("cus_123") == ("ws-ccw-crm", "ccw-crm")
        assert "stripe_customer_id=eq.cus_123" in stub.calls[0].full_url

    def test_vercel_project_hit(self, monkeypatch):
        stub = _StubUrlopen(body=b'[{"id":"ws-synthex","slug":"synthex"}]')
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        lookup = SupabaseWorkspaceLookup(
            url="https://example.supabase.co", service_role_key="k",
        )
        assert lookup.by_vercel_project("prj_abc") == ("ws-synthex", "synthex")
        assert "vercel_project=eq.prj_abc" in stub.calls[0].full_url

    def test_linear_team_hit(self, monkeypatch):
        stub = _StubUrlopen(body=b'[{"id":"ws-restoreassist","slug":"restoreassist"}]')
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        lookup = SupabaseWorkspaceLookup(
            url="https://example.supabase.co", service_role_key="k",
        )
        assert lookup.by_linear_team("RA") == ("ws-restoreassist", "restoreassist")
        assert "linear_team_id=eq.RA" in stub.calls[0].full_url

    def test_empty_value_returns_none_without_query(self, monkeypatch):
        stub = _StubUrlopen()
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        lookup = SupabaseWorkspaceLookup(
            url="https://example.supabase.co", service_role_key="k",
        )
        assert lookup.by_stripe_customer("") is None
        assert lookup.by_stripe_customer(None) is None  # type: ignore[arg-type]
        # urlopen should not have been called for empty inputs
        assert stub.calls == []

    def test_lookup_miss_returns_none(self, monkeypatch):
        stub = _StubUrlopen(body=b"[]")  # no matching row
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        lookup = SupabaseWorkspaceLookup(
            url="https://example.supabase.co", service_role_key="k",
        )
        assert lookup.by_stripe_customer("cus_does_not_exist") is None

    def test_http_error_returns_none(self, monkeypatch):
        stub = _StubUrlopen(raise_exc=urllib.error.URLError("DNS failure"))
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        lookup = SupabaseWorkspaceLookup(
            url="https://example.supabase.co", service_role_key="k",
        )
        assert lookup.by_stripe_customer("cus_x") is None
        # Did NOT raise — caller can safely fall through to 'malformed'.

    def test_malformed_response_returns_none(self, monkeypatch):
        # Server returned an object instead of a list
        stub = _StubUrlopen(body=b'{"oops": "wrong shape"}')
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        lookup = SupabaseWorkspaceLookup(
            url="https://example.supabase.co", service_role_key="k",
        )
        assert lookup.by_stripe_customer("cus_x") is None


# ============================================================
# Factory wiring
# ============================================================


class TestFactoryIncludesWorkspaceLookup:
    def test_in_memory_fallback_includes_workspace_lookup(self):
        from swarm.nexus.ingest.workspace_resolver import InMemoryWorkspaceLookup
        stores = build_production_stores(supabase_url=None, service_role_key=None)
        assert "workspace_lookup" in stores
        assert isinstance(stores["workspace_lookup"], InMemoryWorkspaceLookup)

    def test_creds_present_returns_supabase_workspace_lookup(self):
        stores = build_production_stores(
            supabase_url="https://example.supabase.co",
            service_role_key="key",
        )
        assert isinstance(stores["workspace_lookup"], SupabaseWorkspaceLookup)
        # Existing keys still present
        assert {"loops", "outcomes", "audit", "llm"}.issubset(stores.keys())


# ============================================================
# Webhook handler now passes lookup → parser
# ============================================================


class TestWebhookPassesLookup:
    """End-to-end via FastAPI TestClient: webhook handler MUST pass lookup
    to the parser so the resolver fallback path is reachable.
    """

    def test_stripe_webhook_uses_lookup_when_metadata_missing(self, monkeypatch):
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from app.server.routes.nexus import (
            require_auth, router as nexus_router, webhooks_router,
        )
        from swarm.nexus.ingest.workspace_resolver import InMemoryWorkspaceLookup
        from tests.swarm.nexus.test_api import (
            StubApprovalStore, StubAuditStore, StubChannelStore, StubClientStore,
            StubLLM, StubLoopStore, StubOutcomesStore, StubWorkspaceStore,
        )

        app = FastAPI()
        app.include_router(nexus_router)
        app.include_router(webhooks_router)
        app.dependency_overrides[require_auth] = lambda: {"sub": "test"}

        outcomes = StubOutcomesStore()
        lookup = InMemoryWorkspaceLookup(stripe={
            "cus_ccw_test": ("ws-ccw-crm", "ccw-crm"),
        })
        app.state.nexus_stores = {
            "clients": StubClientStore(),
            "workspaces": StubWorkspaceStore(),
            "channels": StubChannelStore(),
            "loops": StubLoopStore(),
            "approvals": StubApprovalStore(),
            "audit": StubAuditStore(),
            "outcomes": outcomes,
            "workspace_lookup": lookup,
            "llm": StubLLM(),
        }

        monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "test-secret")
        body = json.dumps({
            "id": "evt_lookup_1",
            "type": "invoice.paid",
            "data": {"object": {
                # No metadata.workspace_slug! Will fall through to lookup.
                "metadata": {},
                "customer": "cus_ccw_test",
                "amount_paid": 49900,
            }},
        }).encode()
        sig = hmac.new(b"test-secret", body, hashlib.sha256).hexdigest()

        client = TestClient(app)
        r = client.post(
            "/webhooks/stripe",
            content=body,
            headers={"X-Webhook-Signature": sig, "Content-Type": "application/json"},
        )
        assert r.status_code == 200
        assert r.json()["result"] == "ok"
        # Outcome row was attributed via lookup, not metadata
        rows = outcomes.list()
        assert len(rows) == 1
        assert rows[0].workspace_slug == "ccw-crm"
        assert rows[0].workspace_id == "ws-ccw-crm"
