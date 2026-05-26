"""Focused tests for swarm.nexus.ingest.* parsers (Stripe / Vercel / PostHog / Sentry / Linear).

5 modules × 5 cases each = 25 tests.

Each module tested for:
  1. valid event → outcome row with deterministic id
  2. malformed body → ParseResult(malformed)
  3. unknown / unhandled event → ParseResult(ignored)
  4. missing workspace attribution → ParseResult(malformed)
  5. provider-specific edge case
"""
from __future__ import annotations

from datetime import datetime, timezone

from swarm.nexus.ingest import make_outcome_id
from swarm.nexus.ingest import (
    linear as ingest_linear,
    posthog as ingest_posthog,
    sentry as ingest_sentry,
    stripe as ingest_stripe,
    vercel as ingest_vercel,
)

NOW = datetime(2026, 5, 26, 12, 0, 0, tzinfo=timezone.utc).isoformat()


# ============================================================
# Stripe
# ============================================================


class TestStripeParser:
    def _body(self, **kw):
        base = {
            "id": "evt_1",
            "type": "invoice.paid",
            "data": {"object": {
                "metadata": {"workspace_slug": "acme", "workspace_id": "ws-1"},
                "amount_paid": 19900,
            }},
        }
        base.update(kw)
        return base

    def test_invoice_paid_produces_mrr_outcome(self):
        r = ingest_stripe.parse(self._body(), captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome is not None
        assert r.outcome.metric == "invoice_paid"
        assert r.outcome.value_numeric == 199.00
        assert r.outcome.id == make_outcome_id("stripe", "evt_1")

    def test_malformed_body_returns_malformed(self):
        r = ingest_stripe.parse([], captured_at=NOW)  # type: ignore[arg-type]
        assert r.result == "malformed"

    def test_unknown_event_type_returns_ignored(self):
        body = self._body(type="charge.refunded")
        r = ingest_stripe.parse(body, captured_at=NOW)
        assert r.result == "ignored"

    def test_missing_workspace_metadata_returns_malformed(self):
        body = self._body()
        body["data"]["object"]["metadata"] = {}
        r = ingest_stripe.parse(body, captured_at=NOW)
        assert r.result == "malformed"

    def test_subscription_created_estimates_mrr(self):
        body = {
            "id": "evt_2",
            "type": "customer.subscription.created",
            "data": {"object": {
                "metadata": {"workspace_slug": "acme", "workspace_id": "ws-1"},
                "items": {"data": [{
                    "price": {"unit_amount": 4900},
                    "quantity": 3,
                }]},
            }},
        }
        r = ingest_stripe.parse(body, captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome.value_numeric == 49.00 * 3


# ============================================================
# Vercel
# ============================================================


class TestVercelParser:
    def _body(self, **kw):
        base = {
            "id": "vdep_1",
            "type": "deployment.succeeded",
            "payload": {
                "workspace_slug": "acme",
                "workspace_id": "ws-1",
                "deployment": {"url": "https://acme.vercel.app"},
            },
        }
        base.update(kw)
        return base

    def test_deployment_succeeded_creates_outcome(self):
        r = ingest_vercel.parse(self._body(), captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome.metric == "deploy_success"
        assert r.outcome.value_text == "https://acme.vercel.app"

    def test_malformed_body(self):
        r = ingest_vercel.parse("not a dict", captured_at=NOW)  # type: ignore[arg-type]
        assert r.result == "malformed"

    def test_unhandled_event_type(self):
        r = ingest_vercel.parse(self._body(type="domain.created"), captured_at=NOW)
        assert r.result == "ignored"

    def test_missing_workspace(self):
        body = self._body()
        body["payload"] = {"deployment": {}}
        r = ingest_vercel.parse(body, captured_at=NOW)
        assert r.result == "malformed"

    def test_deployment_error_creates_error_outcome(self):
        r = ingest_vercel.parse(self._body(type="deployment.error"), captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome.metric == "deploy_error"


# ============================================================
# PostHog
# ============================================================


class TestPostHogParser:
    def _body(self, **kw):
        base = {
            "id": "ph_1",
            "event": "funnel_completed",
            "properties": {
                "workspace_slug": "acme",
                "workspace_id": "ws-1",
                "funnel_name": "Signup",
                "conversion_rate": 0.42,
            },
        }
        base.update(kw)
        return base

    def test_funnel_completed_outcome(self):
        r = ingest_posthog.parse(self._body(), captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome.value_numeric == 0.42

    def test_malformed(self):
        r = ingest_posthog.parse(None, captured_at=NOW)  # type: ignore[arg-type]
        assert r.result == "malformed"

    def test_unhandled_event(self):
        r = ingest_posthog.parse(self._body(event="pageview"), captured_at=NOW)
        assert r.result == "ignored"

    def test_missing_workspace(self):
        body = self._body()
        body["properties"].pop("workspace_slug")
        r = ingest_posthog.parse(body, captured_at=NOW)
        assert r.result == "malformed"

    def test_value_text_captures_funnel_name(self):
        r = ingest_posthog.parse(self._body(), captured_at=NOW)
        assert r.outcome.value_text == "Signup"


# ============================================================
# Sentry
# ============================================================


class TestSentryParser:
    def _body(self, **kw):
        base = {
            "id": "sentry_1",
            "action": "created",
            "data": {"issue": {
                "id": "iss_1",
                "title": "TypeError in app.server",
                "level": "error",
                "metadata": {"workspace_slug": "acme", "workspace_id": "ws-1"},
            }},
        }
        base.update(kw)
        return base

    def test_issue_created_outcome(self):
        r = ingest_sentry.parse(self._body(), captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome.metric == "error_rate_spike"
        assert r.outcome.delta_window == "24h"

    def test_malformed(self):
        r = ingest_sentry.parse(123, captured_at=NOW)  # type: ignore[arg-type]
        assert r.result == "malformed"

    def test_unhandled_action(self):
        r = ingest_sentry.parse(self._body(action="assigned"), captured_at=NOW)
        assert r.result == "ignored"

    def test_missing_workspace(self):
        body = self._body()
        body["data"]["issue"].pop("metadata")
        r = ingest_sentry.parse(body, captured_at=NOW)
        assert r.result == "malformed"

    def test_resolved_action_creates_error_resolved_metric(self):
        r = ingest_sentry.parse(self._body(action="resolved"), captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome.metric == "error_resolved"


# ============================================================
# Linear
# ============================================================


class TestLinearParser:
    def _body(self, **kw):
        base = {
            "deliveryId": "lin_1",
            "type": "Issue",
            "action": "update",
            "workspace_slug": "acme",
            "workspace_id": "ws-1",
            "data": {
                "id": "iss-1",
                "title": "Fix login redirect",
                "state": {"type": "completed"},
            },
        }
        base.update(kw)
        return base

    def test_issue_completed_outcome(self):
        r = ingest_linear.parse(self._body(), captured_at=NOW)
        assert r.result == "ok"
        assert r.outcome.metric == "issue_completion"

    def test_malformed(self):
        r = ingest_linear.parse(["not", "a", "dict"], captured_at=NOW)  # type: ignore[arg-type]
        assert r.result == "malformed"

    def test_non_completed_state_is_ignored(self):
        body = self._body()
        body["data"]["state"]["type"] = "started"
        r = ingest_linear.parse(body, captured_at=NOW)
        assert r.result == "ignored"

    def test_missing_workspace(self):
        body = self._body()
        body.pop("workspace_slug")
        r = ingest_linear.parse(body, captured_at=NOW)
        assert r.result == "malformed"

    def test_idempotent_outcome_id(self):
        r1 = ingest_linear.parse(self._body(), captured_at=NOW)
        r2 = ingest_linear.parse(self._body(), captured_at=NOW)
        assert r1.outcome.id == r2.outcome.id
