"""Focused tests for swarm.nexus.ingest.workspace_resolver + parser fallback."""
from __future__ import annotations

from datetime import datetime, timezone

from swarm.nexus.ingest import (
    linear as ingest_linear,
    stripe as ingest_stripe,
    vercel as ingest_vercel,
)
from swarm.nexus.ingest.workspace_resolver import (
    InMemoryWorkspaceLookup,
    resolve_workspace,
)

NOW = datetime(2026, 5, 27, 6, 0, 0, tzinfo=timezone.utc).isoformat()


# ============================================================
# resolve_workspace — provider routing
# ============================================================


class TestResolveWorkspace:
    def test_stripe_lookup_hit(self):
        lookup = InMemoryWorkspaceLookup(stripe={"cus_123": ("ws-1", "acme")})
        assert resolve_workspace("stripe", "cus_123", lookup) == ("ws-1", "acme")

    def test_vercel_lookup_hit(self):
        lookup = InMemoryWorkspaceLookup(vercel={"prj_xyz": ("ws-2", "beta")})
        assert resolve_workspace("vercel", "prj_xyz", lookup) == ("ws-2", "beta")

    def test_linear_lookup_hit(self):
        lookup = InMemoryWorkspaceLookup(linear={"ENG": ("ws-3", "gamma")})
        assert resolve_workspace("linear", "ENG", lookup) == ("ws-3", "gamma")

    def test_lookup_miss_returns_none(self):
        lookup = InMemoryWorkspaceLookup()
        assert resolve_workspace("stripe", "cus_unknown", lookup) is None

    def test_empty_hint_returns_none(self):
        lookup = InMemoryWorkspaceLookup(stripe={"cus_x": ("ws", "x")})
        assert resolve_workspace("stripe", None, lookup) is None
        assert resolve_workspace("stripe", "", lookup) is None

    def test_non_string_hint_returns_none(self):
        lookup = InMemoryWorkspaceLookup()
        # type: ignore[arg-type] — deliberate bad input
        assert resolve_workspace("stripe", 123, lookup) is None  # type: ignore[arg-type]


# ============================================================
# Stripe parser fallback via resolver
# ============================================================


class TestStripeParserFallback:
    def _body(self, with_metadata=True, customer="cus_123"):
        metadata = {"workspace_slug": "acme", "workspace_id": "ws-1"} if with_metadata else {}
        return {
            "id": "evt_1",
            "type": "invoice.paid",
            "data": {"object": {
                "metadata": metadata,
                "customer": customer,
                "amount_paid": 19900,
            }},
        }

    def test_metadata_path_unchanged_no_lookup(self):
        """Existing payloads with metadata work without lookup."""
        r = ingest_stripe.parse(self._body(), captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome.workspace_slug == "acme"

    def test_resolver_fallback_when_metadata_missing(self):
        lookup = InMemoryWorkspaceLookup(stripe={"cus_123": ("ws-7", "synthex")})
        r = ingest_stripe.parse(
            self._body(with_metadata=False),
            captured_at=NOW,
            lookup=lookup,
        )
        assert r.result == "ok"
        assert r.outcome.workspace_slug == "synthex"
        assert r.outcome.workspace_id == "ws-7"

    def test_resolver_miss_returns_malformed(self):
        lookup = InMemoryWorkspaceLookup(stripe={})  # no match
        r = ingest_stripe.parse(
            self._body(with_metadata=False),
            captured_at=NOW,
            lookup=lookup,
        )
        assert r.result == "malformed"
        assert "workspace attribution missing" in r.reason

    def test_no_lookup_returns_malformed_when_metadata_missing(self):
        """Backward-compat: no lookup + no metadata → malformed (as before)."""
        r = ingest_stripe.parse(
            self._body(with_metadata=False),
            captured_at=NOW,
        )
        assert r.result == "malformed"


# ============================================================
# Vercel parser fallback
# ============================================================


class TestVercelParserFallback:
    def _body(self, with_metadata=True, project_id="prj_xyz"):
        payload = {
            "deployment": {"url": "https://example.vercel.app"},
            "project": {"id": project_id},
        }
        if with_metadata:
            payload["workspace_slug"] = "acme"
            payload["workspace_id"] = "ws-1"
        return {"id": "vdep_1", "type": "deployment.succeeded", "payload": payload}

    def test_metadata_path_unchanged(self):
        r = ingest_vercel.parse(self._body(), captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome.workspace_slug == "acme"

    def test_resolver_fallback(self):
        lookup = InMemoryWorkspaceLookup(vercel={"prj_xyz": ("ws-9", "carsi")})
        r = ingest_vercel.parse(
            self._body(with_metadata=False),
            captured_at=NOW,
            lookup=lookup,
        )
        assert r.result == "ok"
        assert r.outcome.workspace_slug == "carsi"

    def test_resolver_miss_malformed(self):
        lookup = InMemoryWorkspaceLookup(vercel={})
        r = ingest_vercel.parse(
            self._body(with_metadata=False),
            captured_at=NOW,
            lookup=lookup,
        )
        assert r.result == "malformed"


# ============================================================
# Linear parser fallback
# ============================================================


class TestLinearParserFallback:
    def _body(self, with_metadata=True, team_key="ENG"):
        body = {
            "deliveryId": "lin_1",
            "type": "Issue",
            "action": "update",
            "data": {
                "id": "iss-1",
                "title": "fix login",
                "team": {"key": team_key},
                "state": {"type": "completed"},
            },
        }
        if with_metadata:
            body["workspace_slug"] = "acme"
            body["workspace_id"] = "ws-1"
        return body

    def test_metadata_path_unchanged(self):
        r = ingest_linear.parse(self._body(), captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome.workspace_slug == "acme"

    def test_resolver_fallback(self):
        lookup = InMemoryWorkspaceLookup(linear={"ENG": ("ws-4", "dr-nrp-onboarding")})
        r = ingest_linear.parse(
            self._body(with_metadata=False),
            captured_at=NOW,
            lookup=lookup,
        )
        assert r.result == "ok"
        assert r.outcome.workspace_slug == "dr-nrp-onboarding"

    def test_resolver_miss_malformed(self):
        lookup = InMemoryWorkspaceLookup(linear={})
        r = ingest_linear.parse(
            self._body(with_metadata=False),
            captured_at=NOW,
            lookup=lookup,
        )
        assert r.result == "malformed"
