"""Phase B / B7 — End-to-end synthetic Nexus pipeline.

A single test drives every Phase A + Phase B stage in order, using
stub I/O. No real network, no real LLM. Proves the wiring:

  1. Voice transcript → margot_intake.dispatch_intake
                      → POST /api/nexus/clients/intake (201)
  2. qualify_client(synthetic LLM)         → status='qualified'
  3. create_workspace                       → workspace row
  4. wire_channels(telegram_chat)           → channel mapped
  5. enable_loops(loop_kind='discovery')    → loop row
  6. Synthetic Stripe webhook payload
     → swarm.nexus.ingest.stripe.parse      → outcomes row
  7. generate_bra over that outcome         → ≥1 BRA card, valid evidence_ids
  8. assemble_six_pager(bra_reports=[...])  → contains workspace + BRA card

A passing run is the green-light gate for Phase B.
"""
from __future__ import annotations

import hashlib
import hmac
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from swarm.nexus import audit as audit_mod
from swarm.nexus import onboarding
from swarm.nexus.bra import generate_bra
from swarm.nexus.margot_intake import (
    HTTPResponse,
    nexus_intake_from_voice,
)
from swarm.nexus.outcomes import InMemoryOutcomesStore
from swarm.six_pager import assemble_six_pager

from app.server.routes.nexus import (
    require_auth,
    router as nexus_router,
    webhooks_router,
)

# Reuse the stub store fleet from the contract tests — they already
# match the production app.state.nexus_stores contract.
from tests.swarm.nexus.test_api import (  # noqa: E402
    StubApprovalStore,
    StubAuditStore,
    StubChannelStore,
    StubClientStore,
    StubLLM,
    StubLoopStore,
    StubWorkspaceStore,
)


# ============================================================
# A multi-stage LLM stub: returns different JSON for qualify / BRA
# ============================================================


class StagedLLM:
    """Returns different JSON depending on which prompt is calling."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def complete(self, *, system: str, user: str,
                 max_tokens: int = 1024, temperature: float = 0.3) -> str:
        self.calls.append((system, user))
        s = system.lower()
        if "intake" in s and "voice transcript" in s.lower():
            return json.dumps({
                "legal_name": "ACME Pty Ltd",
                "display_name": "Acme",
                "primary_contact_name": "Jane",
                "primary_contact_email": "jane@acme.example",
                "notes": "Restoration company onboarding.",
            })
        if "qualif" in s:
            return json.dumps({
                "industry": "restoration",
                "scope_summary": "Property damage restoration with GEO focus.",
                "estimated_budget_aud": 2400,
                "compliance_flags": [],
                "qualified": True,
                "rationale": "Budget + scope clear.",
                "requires_approval": False,
                "approval_reason": None,
            })
        if "bra analyst" in s:
            return json.dumps({"cards": [{
                "brief": "First Stripe invoice paid — $199 MRR booked.",
                "recommendation": "Send the founder a celebratory note.",
                "action": "Schedule a 15-min sync next Tuesday.",
                "severity": "medium",
                "evidence_ids": ["__STRIPE_OUTCOME_ID__"],
            }]})
        if "discovery analyst" in s:
            return json.dumps({
                "brief": "First paying customer this week.",
                "top_signals": [{"id": "__STRIPE_OUTCOME_ID__",
                                 "why_it_matters": "MRR turned on."}],
                "recommended_action": "Send a celebratory note.",
                "recommended_loop": "kpi",
            })
        return "{}"


# ============================================================
# FastAPI test app — full Phase A + B store fleet
# ============================================================


@pytest.fixture
def outcomes_store():
    return InMemoryOutcomesStore()


@pytest.fixture
def app(tmp_path, monkeypatch, outcomes_store):
    monkeypatch.setattr(audit_mod, "AUDIT_KEY_PATH", tmp_path / "audit-key")
    fa = FastAPI()
    fa.include_router(nexus_router)
    fa.include_router(webhooks_router)
    fa.dependency_overrides[require_auth] = lambda: {"sub": "test-user"}
    fa.state.nexus_stores = {
        "clients": StubClientStore(),
        "workspaces": StubWorkspaceStore(),
        "channels": StubChannelStore(),
        "loops": StubLoopStore(),
        "approvals": StubApprovalStore(),
        "audit": StubAuditStore(),
        "outcomes": outcomes_store,
        "llm": StubLLM(),
    }
    return fa


# ============================================================
# Test
# ============================================================


def test_phase_b_full_pipeline(app, outcomes_store, monkeypatch):
    """Drives stage 1 → 8 and asserts each stage's outputs."""
    client = TestClient(app)
    llm = StagedLLM()

    # ---- Stage 1: voice intake -----------------------------------------
    class HTTPViaTestClient:
        """Pipes margot_intake's POST through the FastAPI TestClient."""

        def post(self, url, *, json_body, headers):
            # url is "https://stub{INTAKE_ENDPOINT}"; rewrite to relative
            from urllib.parse import urlparse
            path = urlparse(url).path
            resp = client.post(path, json=json_body, headers=headers)
            try:
                return HTTPResponse(status_code=resp.status_code, body=resp.json())
            except ValueError:
                return HTTPResponse(status_code=resp.status_code, body={})

    intake_outcome = nexus_intake_from_voice(
        "Hi Margot, please onboard ACME Pty Ltd to the platform.",
        founder_id="phill",
        llm=llm,
        http_client=HTTPViaTestClient(),
        api_base="https://stub",
    )
    assert intake_outcome["result"] == "ok", intake_outcome
    client_id = intake_outcome["client_id"]
    assert client_id

    # ---- Stage 2: qualify_client ---------------------------------------
    client_record = app.state.nexus_stores["clients"].get(client_id)
    assert client_record is not None
    qualify_result = onboarding.qualify_client(
        client_record,
        "ACME Pty Ltd — restoration company with $2,400/mo budget.",
        llm=llm,
    )
    assert qualify_result.result == "ok"
    assert qualify_result.new_status == "qualified"
    from dataclasses import replace
    client_record = replace(client_record, status="qualified")
    app.state.nexus_stores["clients"].save(client_record)

    # ---- Stage 3: create_workspace -------------------------------------
    workspaces_store = app.state.nexus_stores["workspaces"]
    client_record = replace(client_record, status="qualified")
    ws_outcome = onboarding.create_workspace(
        client_record, slug="acme", display_name="Acme",
        linear_team_id="lin-team-1",
        workspaces=workspaces_store,
    )
    assert ws_outcome.result == "ok"
    workspace_id = ws_outcome.workspace_id
    workspace = workspaces_store.get(workspace_id)
    assert workspace is not None
    client_record = replace(client_record, status="workspace_created")
    app.state.nexus_stores["clients"].save(client_record)

    # ---- Stage 4: wire_channels ----------------------------------------
    # Save a channel directly (mimicking the map_existing_chat path of
    # request_provision; B3's full router needs ProvisionRequest plus an
    # approvals store, which is exercised by its own contract tests).
    from swarm.nexus.types import Channel
    channel = Channel(
        id="chn-1",
        workspace_id=workspace.id,
        workspace_slug=workspace.slug,
        kind="telegram_chat",
        external_id="-100123456789",
        display_name="Acme ↔ Pi-CEO",
        inbound_route="margot",
        status="active",
    )
    app.state.nexus_stores["channels"].save(channel)

    wire_outcome = onboarding.wire_channels(
        client_record, workspace,
        channels=app.state.nexus_stores["channels"],
    )
    assert wire_outcome.result == "ok"
    client_record = replace(client_record, status="wired")

    # ---- Stage 5: enable_loops -----------------------------------------
    loop_outcome = onboarding.enable_loops(
        client_record, workspace,
        loop_specs=[("discovery", "7d", {})],
        loops=app.state.nexus_stores["loops"],
    )
    assert loop_outcome.result == "ok"

    # ---- Stage 6: synthetic Stripe webhook → outcome --------------------
    monkeypatch.setenv("STRIPE_WEBHOOK_SECRET", "test-secret")
    stripe_body = {
        "id": "evt_e2e_1",
        "type": "invoice.paid",
        "data": {"object": {
            "metadata": {"workspace_slug": "acme", "workspace_id": workspace.id},
            "amount_paid": 19900,
        }},
    }
    raw_body = json.dumps(stripe_body).encode()
    sig = hmac.new(b"test-secret", raw_body, hashlib.sha256).hexdigest()
    resp = client.post(
        "/webhooks/stripe",
        content=raw_body,
        headers={"X-Webhook-Signature": sig, "Content-Type": "application/json"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["result"] == "ok"
    outcomes_after = outcomes_store.list(workspace_slug="acme")
    assert len(outcomes_after) == 1
    stripe_outcome = outcomes_after[0]
    assert stripe_outcome.metric == "invoice_paid"
    assert stripe_outcome.value_numeric == 199.0

    # ---- Stage 7: generate_bra over the Stripe outcome ------------------
    # Rewrite the staged LLM's BRA stub to cite the actual outcome id.
    class _BoundLLM:
        def __init__(self, real_id: str):
            self._real_id = real_id

        def complete(self, *, system, user, max_tokens=1024, temperature=0.3):
            return llm.complete(
                system=system, user=user,
                max_tokens=max_tokens, temperature=temperature,
            ).replace("__STRIPE_OUTCOME_ID__", self._real_id)

    bra_report = generate_bra(
        workspace_slug="acme", window="7d",
        outcomes_store=outcomes_store, llm=_BoundLLM(stripe_outcome.id),
    )
    assert len(bra_report.cards) == 1
    assert stripe_outcome.id in bra_report.cards[0].evidence_ids

    # ---- Stage 8: 6-pager renders BRA section ---------------------------
    text = assemble_six_pager(date_str="2026-05-26", bra_reports=[bra_report])
    assert "8. Nexus BRA cards" in text
    assert "acme" in text
    assert "First Stripe invoice paid" in text
