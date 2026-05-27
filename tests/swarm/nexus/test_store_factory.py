"""Focused tests for swarm.nexus.store_factory — production wiring.

No real Supabase. urlopen is monkeypatched everywhere the REST writers
are exercised so we can assert request shapes + simulate failures
without network calls.
"""
from __future__ import annotations

import threading
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any

from swarm.nexus.store_factory import (
    SupabaseAuditStore,
    SupabaseLoopsStore,
    WorkingTierLLM,
    _InMemoryAuditStore,
    _InMemoryLoopsStore,
    build_production_stores,
)
from swarm.nexus.audit import build_audit_row
from swarm.nexus.types import Loop


# ============================================================
# Stub urlopen
# ============================================================


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
            def __init__(self_inner, body):
                self_inner._b = body

            def __enter__(self_inner):
                return self_inner

            def __exit__(self_inner, *a):
                return None

            def read(self_inner):
                return self_inner._b

        return _Resp(self._body)


# ============================================================
# SupabaseLoopsStore
# ============================================================


class TestSupabaseLoopsStore:
    def test_list_due_returns_parsed_loops(self, monkeypatch):
        body = (
            b'[{"id":"lp-1","workspace_id":"ws-1","workspace_slug":"acme",'
            b'"loop_kind":"discovery","cadence":"7d","enabled":true,'
            b'"config":{},"last_run_at":null,"next_run_at":null,'
            b'"created_at":"2026-05-20T00:00:00Z"}]'
        )
        stub = _StubUrlopen(body=body)
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        store = SupabaseLoopsStore(url="https://example.supabase.co", service_role_key="k")
        rows = store.list_due(now=datetime(2026, 5, 27, 6, 0, tzinfo=timezone.utc))
        assert len(rows) == 1
        assert rows[0].id == "lp-1"
        assert rows[0].loop_kind == "discovery"
        assert rows[0].enabled is True

    def test_list_due_returns_empty_on_http_error(self, monkeypatch):
        stub = _StubUrlopen(raise_exc=urllib.error.URLError("DNS failure"))
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        store = SupabaseLoopsStore(url="https://example.supabase.co", service_role_key="k")
        assert store.list_due(now=datetime.now(timezone.utc)) == []

    def test_save_uses_merge_duplicates_prefer_header(self, monkeypatch):
        stub = _StubUrlopen()
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        store = SupabaseLoopsStore(url="https://example.supabase.co", service_role_key="k")
        loop = Loop(
            id="lp-1", workspace_id="ws-1", workspace_slug="acme",
            loop_kind="discovery", cadence="7d", enabled=True,
        )
        store.save(loop)
        assert len(stub.calls) == 1
        prefer = stub.calls[0].get_header("Prefer")
        assert "resolution=merge-duplicates" in prefer

    def test_save_swallows_http_error(self, monkeypatch):
        stub = _StubUrlopen(raise_exc=urllib.error.HTTPError(
            "u", 503, "service unavailable", {}, None,  # type: ignore[arg-type]
        ))
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        store = SupabaseLoopsStore(url="https://example.supabase.co", service_role_key="k")
        loop = Loop(
            id="lp-1", workspace_id="ws-1", workspace_slug="acme",
            loop_kind="discovery", cadence="7d",
        )
        # MUST NOT raise.
        result = store.save(loop)
        assert result == loop


# ============================================================
# SupabaseAuditStore — fire-and-forget
# ============================================================


class TestSupabaseAuditStore:
    def test_append_is_non_blocking(self, monkeypatch, tmp_path):
        # Isolate audit key path so build_audit_row succeeds in tests.
        from swarm.nexus import audit as audit_mod
        monkeypatch.setattr(audit_mod, "AUDIT_KEY_PATH", tmp_path / "audit-key")

        stub = _StubUrlopen()
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        store = SupabaseAuditStore(url="https://example.supabase.co", service_role_key="k")
        row = build_audit_row(
            actor="test", action="test.event",
            args={"foo": "bar"}, policy_level="auto", result="ok",
        )
        returned_id = store.append(row)
        assert returned_id == row.id
        # Wait briefly for the daemon thread:
        for t in threading.enumerate():
            if t.name == "nexus-audit-write":
                t.join(timeout=2)
        assert len(stub.calls) == 1

    def test_append_swallows_http_error(self, monkeypatch, tmp_path):
        from swarm.nexus import audit as audit_mod
        monkeypatch.setattr(audit_mod, "AUDIT_KEY_PATH", tmp_path / "audit-key")

        stub = _StubUrlopen(raise_exc=urllib.error.HTTPError(
            "u", 500, "boom", {}, None,  # type: ignore[arg-type]
        ))
        monkeypatch.setattr(
            "swarm.nexus.store_factory.urllib.request.urlopen", stub,
        )
        store = SupabaseAuditStore(url="https://example.supabase.co", service_role_key="k")
        row = build_audit_row(
            actor="test", action="test.event",
            args={}, policy_level="auto", result="ok",
        )
        # Must return without raising
        store.append(row)
        for t in threading.enumerate():
            if t.name == "nexus-audit-write":
                t.join(timeout=2)


# ============================================================
# Factory
# ============================================================


class TestFactory:
    def test_in_memory_fallback_when_creds_missing(self, caplog):
        with caplog.at_level("WARNING"):
            stores = build_production_stores(supabase_url=None, service_role_key=None)
        assert isinstance(stores["loops"], _InMemoryLoopsStore)
        assert isinstance(stores["audit"], _InMemoryAuditStore)
        assert any("falling back to in-memory" in r.message for r in caplog.records)

    def test_creds_present_returns_supabase_adapters(self):
        stores = build_production_stores(
            supabase_url="https://example.supabase.co",
            service_role_key="key",
        )
        assert isinstance(stores["loops"], SupabaseLoopsStore)
        assert isinstance(stores["audit"], SupabaseAuditStore)
        assert isinstance(stores["llm"], WorkingTierLLM)
        # outcomes already covered by B1's tests but verify the slot is filled:
        assert stores["outcomes"] is not None

    def test_factory_dict_satisfies_daemon_resolve_stores_contract(self):
        """B8's _resolve_stores requires keys loops, outcomes, audit, llm."""
        stores = build_production_stores(supabase_url=None, service_role_key=None)
        # Mimics the daemon's check:
        loops = stores.get("loops")
        outcomes = stores.get("outcomes")
        audit = stores.get("audit")
        llm = stores.get("llm")
        assert loops and outcomes  # the gate in scheduler_daemon._resolve_stores
        assert audit is not None
        assert llm is not None


# ============================================================
# WorkingTierLLM (smoke — no real model call)
# ============================================================


class TestWorkingTierLLM:
    def test_complete_delegates_to_model_router(self, monkeypatch):
        """Verify the adapter calls swarm.model_router.get_client(Tier.WORKING)."""
        captured: dict[str, Any] = {}

        class _StubClient:
            tier = "working"

            def complete(self, **kw):
                captured["kwargs"] = kw

                class _Resp:
                    text = "ok"

                return _Resp()

        def _stub_get_client(tier):
            captured["tier"] = tier
            return _StubClient()

        monkeypatch.setattr("swarm.model_router.get_client", _stub_get_client)
        adapter = WorkingTierLLM()
        out = adapter.complete(system="s", user="u")
        assert out == "ok"
        from swarm.model_router import Tier
        assert captured["tier"] == Tier.WORKING
        assert captured["kwargs"]["system"] == "s"
