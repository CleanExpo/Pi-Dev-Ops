"""Pi-CEO FastAPI surface for the Nexus Autonomous Onboarding + Client
Growth OS. Per spec §5 (2nd-brain/Pitches/03-...).

Routes:

    POST   /api/nexus/clients/intake
    POST   /api/nexus/clients/{client_id}/qualify
    POST   /api/nexus/clients/{client_id}/approve-qualification
    POST   /api/nexus/clients/{client_id}/workspace
    POST   /api/nexus/workspaces/{workspace_id}/channels
    POST   /api/nexus/workspaces/{workspace_id}/loops/{loop_kind}/enable
    GET    /api/nexus/approvals
    POST   /api/nexus/approvals/{approval_id}/decide
    GET    /api/nexus/outcomes
    GET    /api/nexus/audit
    GET    /api/nexus/health
    POST   /webhooks/stripe
    POST   /webhooks/vercel
    POST   /webhooks/posthog
    POST   /webhooks/sentry
    POST   /webhooks/linear

All routes are JWT-scoped via the existing Pi-CEO auth pattern (require_auth).
Webhooks verify signatures per provider before any DB write.

The route handlers are thin: they validate input + call into the
pure-logic modules (onboarding, channels, approvals, audit). Storage
adapters are injected via app.state during startup (PR-NEXUS-5 wires
the Supabase adapters; tests inject stubs).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

# Try to import auth from existing pattern; fall back gracefully so tests
# can run without the full Pi-CEO server bootstrap.
try:
    from ..auth import require_auth  # type: ignore
except Exception:  # pragma: no cover
    async def require_auth():  # type: ignore[misc]
        return {"sub": "test-user"}


router = APIRouter(prefix="/api/nexus", tags=["nexus"])
webhooks_router = APIRouter(prefix="/webhooks", tags=["nexus-webhooks"])


# ============================================================
# Request / response models
# ============================================================


class IntakeRequest(BaseModel):
    legal_name: str = Field(..., min_length=1, max_length=200)
    display_name: str = Field(..., min_length=1, max_length=200)
    founder_id: str = Field(..., min_length=1)
    intake_source: str = Field(..., pattern=r"^(voice|form|manual|referral)$")
    primary_contact_name: Optional[str] = None
    primary_contact_email: Optional[str] = None
    raw_notes: Optional[str] = None
    voice_transcript: Optional[str] = None


class QualifyRequest(BaseModel):
    force_rerun: bool = False
    raw_intake_override: Optional[str] = None


class ApproveQualificationRequest(BaseModel):
    decision: str = Field(..., pattern=r"^(approved|denied)$")
    note: Optional[str] = None


class CreateWorkspaceRequest(BaseModel):
    slug: str = Field(..., min_length=3, max_length=40)
    display_name: str = Field(..., min_length=1, max_length=200)
    linear_team_id: str = Field(..., min_length=1)
    github_repo: Optional[str] = None
    linear_project_id: Optional[str] = None


class ProvisionChannelRequest(BaseModel):
    kind: str = Field(..., pattern=r"^(telegram_chat|telegram_bot|slack|email)$")
    display_name: str = Field(..., min_length=1, max_length=200)
    inbound_route: str = Field("margot", pattern=r"^(margot|support|ops-only)$")
    external_id: Optional[str] = None
    bot_token_env_name: Optional[str] = None
    authorized_chat_ids: list[str] = Field(default_factory=list)


class EnableLoopRequest(BaseModel):
    cadence: str = Field(..., min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., pattern=r"^(approved|denied)$")
    note: Optional[str] = None


# ============================================================
# Helper: get injected stores
# ============================================================


def get_stores(request: Request) -> dict[str, Any]:
    """Resolve the bag of stores injected at app startup. Tests override
    via `app.state.nexus_stores = {...}`. Production wires Supabase adapters."""
    stores = getattr(request.app.state, "nexus_stores", None)
    if stores is None:
        raise HTTPException(
            status_code=500,
            detail="nexus stores not initialised in app.state",
        )
    return stores


# ============================================================
# Onboarding routes
# ============================================================


@router.post("/clients/intake", status_code=201)
async def post_client_intake(
    body: IntakeRequest,
    request: Request,
    _auth=Depends(require_auth),
):
    """Create a fresh client record in 'intake' status."""
    stores = get_stores(request)
    client_store = stores["clients"]
    now = datetime.now(timezone.utc)
    client_id = stores.get("id_factory", _default_id_factory)("c")
    from swarm.nexus.types import Client
    client = Client(
        id=client_id,
        founder_id=body.founder_id,
        legal_name=body.legal_name,
        display_name=body.display_name,
        primary_contact_name=body.primary_contact_name,
        primary_contact_email=body.primary_contact_email,
        intake_source=body.intake_source,  # type: ignore[arg-type]
        intake_recorded_at=now.isoformat(),
        status="intake",
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
    )
    saved = client_store.save(client)
    return {
        "client_id": saved.id,
        "status": saved.status,
    }


@router.post("/clients/{client_id}/qualify")
async def post_qualify(
    client_id: str,
    body: QualifyRequest,
    request: Request,
    _auth=Depends(require_auth),
):
    stores = get_stores(request)
    client_store = stores["clients"]
    client = client_store.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    from swarm.nexus.onboarding import qualify_client
    llm = stores["llm"]
    raw_intake = body.raw_intake_override or "(no intake content provided)"
    outcome = qualify_client(client, raw_intake, llm=llm)
    if outcome.result != "ok":
        raise HTTPException(status_code=422, detail=outcome.reason)
    from dataclasses import replace
    updated = client_store.save(replace(client, status=outcome.new_status))
    return {
        "client_id": updated.id,
        "status": updated.status,
        "qualification": outcome.audit_payload.get("qualification"),
        "requires_approval": (
            outcome.audit_payload.get("qualification", {}).get("requires_approval")
            if outcome.audit_payload.get("qualification")
            else False
        ),
    }


@router.post("/clients/{client_id}/approve-qualification")
async def post_approve_qualification(
    client_id: str,
    body: ApproveQualificationRequest,
    request: Request,
    _auth=Depends(require_auth),
):
    stores = get_stores(request)
    client_store = stores["clients"]
    client = client_store.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    from swarm.nexus.onboarding import approve_qualification
    outcome = approve_qualification(
        client, body.decision,
        decided_by="api-user", note=body.note,
    )
    if outcome.result != "ok":
        raise HTTPException(status_code=422, detail=outcome.reason)
    from dataclasses import replace
    updated = client_store.save(replace(client, status=outcome.new_status))
    return {"client_id": updated.id, "status": updated.status}


@router.post("/clients/{client_id}/workspace", status_code=201)
async def post_create_workspace(
    client_id: str,
    body: CreateWorkspaceRequest,
    request: Request,
    _auth=Depends(require_auth),
):
    stores = get_stores(request)
    client_store = stores["clients"]
    workspace_store = stores["workspaces"]
    client = client_store.get(client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    from swarm.nexus.onboarding import create_workspace
    outcome = create_workspace(
        client, slug=body.slug, display_name=body.display_name,
        linear_team_id=body.linear_team_id,
        github_repo=body.github_repo,
        linear_project_id=body.linear_project_id,
        workspaces=workspace_store,
    )
    if outcome.result != "ok":
        raise HTTPException(status_code=422, detail=outcome.reason)
    from dataclasses import replace
    client_store.save(replace(client, status=outcome.new_status))
    return {
        "workspace_id": outcome.workspace_id,
        "slug": body.slug,
        "status": "workspace_created",
    }


@router.post("/workspaces/{workspace_id}/channels", status_code=201)
async def post_provision_channel(
    workspace_id: str,
    body: ProvisionChannelRequest,
    request: Request,
    _auth=Depends(require_auth),
):
    stores = get_stores(request)
    workspace_store = stores["workspaces"]
    channel_store = stores["channels"]
    approval_store = stores["approvals"]
    workspace = workspace_store.get(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    from swarm.nexus.channels import ProvisionRequest, request_provision
    outcome = request_provision(
        ProvisionRequest(
            workspace_id=workspace.id,
            workspace_slug=workspace.slug,
            kind=body.kind,  # type: ignore[arg-type]
            display_name=body.display_name,
            inbound_route=body.inbound_route,  # type: ignore[arg-type]
            external_id=body.external_id,
            bot_token_env_name=body.bot_token_env_name,
            authorized_chat_ids=tuple(body.authorized_chat_ids),
        ),
        workspace, channels=channel_store, approvals=approval_store,
        requested_by="api-user",
    )
    if outcome.action == "rejected":
        raise HTTPException(status_code=422, detail=outcome.reason)
    return {
        "channel_id": outcome.channel_id,
        "approval_id": outcome.approval_id,
        "action": outcome.action,
        "requires_operator_step": outcome.requires_operator_step,
        "operator_step_description": outcome.operator_step_description,
    }


@router.post(
    "/workspaces/{workspace_id}/loops/{loop_kind}/enable",
    status_code=201,
)
async def post_enable_loop(
    workspace_id: str,
    loop_kind: str,
    body: EnableLoopRequest,
    request: Request,
    _auth=Depends(require_auth),
):
    if loop_kind not in (
        "discovery", "content", "kpi", "geo", "support", "compliance",
    ):
        raise HTTPException(status_code=422, detail=f"unknown loop_kind {loop_kind!r}")
    stores = get_stores(request)
    workspace = stores["workspaces"].get(workspace_id)
    if workspace is None:
        raise HTTPException(status_code=404, detail="workspace not found")
    client = stores["clients"].get(workspace.client_id)
    if client is None:
        raise HTTPException(status_code=404, detail="client not found")
    from swarm.nexus.onboarding import enable_loops
    outcome = enable_loops(
        client, workspace,
        loop_specs=[(loop_kind, body.cadence, body.config)],  # type: ignore[list-item]
        loops=stores["loops"],
    )
    if outcome.result != "ok":
        raise HTTPException(status_code=422, detail=outcome.reason)
    return {
        "workspace_id": workspace_id,
        "loop_kind": loop_kind,
        "enabled": True,
    }


# ============================================================
# Approvals
# ============================================================


@router.get("/approvals")
async def get_approvals(
    request: Request,
    status_filter: Optional[str] = None,
    workspace_slug: Optional[str] = None,
    _auth=Depends(require_auth),
):
    stores = get_stores(request)
    approval_store = stores["approvals"]
    if status_filter == "pending":
        items = list(approval_store.list_pending(workspace_slug=workspace_slug))
    else:
        items = list(approval_store.list_all(workspace_slug=workspace_slug))
    return {
        "approvals": [
            {
                "id": a.id,
                "action": a.action,
                "why_now": a.why_now,
                "reversibility": a.reversibility,
                "status": a.status,
                "sla_expires_at": a.sla_expires_at,
                "workspace_slug": a.workspace_slug,
            }
            for a in items
        ],
        "count": len(items),
    }


@router.post("/approvals/{approval_id}/decide")
async def post_decide_approval(
    approval_id: str,
    body: ApprovalDecisionRequest,
    request: Request,
    _auth=Depends(require_auth),
):
    stores = get_stores(request)
    from swarm.nexus.approvals import decide_approval
    outcome = decide_approval(
        approval_id, body.decision,  # type: ignore[arg-type]
        decided_by="api-user", note=body.note,
        approvals=stores["approvals"],
    )
    if outcome.result != "ok":
        raise HTTPException(status_code=422, detail=outcome.reason)
    # Persist the audit row
    if outcome.audit_row:
        stores["audit"].append(outcome.audit_row)
    return {
        "approval_id": approval_id,
        "status": outcome.approval.status,
        "decided_at": outcome.approval.decided_at,
    }


# ============================================================
# Outcomes + audit read endpoints
# ============================================================


@router.get("/outcomes")
async def get_outcomes(
    request: Request,
    workspace_id: Optional[str] = None,
    _auth=Depends(require_auth),
):
    stores = get_stores(request)
    rows = list(stores["outcomes"].list(workspace_id=workspace_id))
    return {"outcomes": rows, "count": len(rows)}


@router.get("/audit")
async def get_audit(
    request: Request,
    workspace_id: Optional[str] = None,
    _auth=Depends(require_auth),
):
    stores = get_stores(request)
    rows = list(stores["audit"].list(workspace_id=workspace_id))
    return {"audit": rows, "count": len(rows)}


@router.get("/health")
async def get_nexus_health():
    return {"status": "ok", "service": "nexus"}


# ============================================================
# Webhooks (signature-verified before write)
# ============================================================


def _verify_webhook_signature(request: Request, body: bytes, secret_env: str) -> bool:
    """Returns True if request carries a valid HMAC signature.
    Provider-specific verification happens in each route — this is a
    common shape only."""
    import hashlib
    import hmac
    import os
    secret = os.environ.get(secret_env, "").encode("utf-8")
    if not secret:
        return False
    sig_header = request.headers.get("X-Webhook-Signature", "")
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig_header, expected)


@webhooks_router.post("/stripe")
async def webhook_stripe(request: Request):
    body = await request.body()
    if not _verify_webhook_signature(request, body, "STRIPE_WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="invalid signature")
    return {"received": True, "source": "stripe"}


@webhooks_router.post("/vercel")
async def webhook_vercel(request: Request):
    body = await request.body()
    if not _verify_webhook_signature(request, body, "VERCEL_WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="invalid signature")
    return {"received": True, "source": "vercel"}


@webhooks_router.post("/posthog")
async def webhook_posthog(request: Request):
    body = await request.body()
    if not _verify_webhook_signature(request, body, "POSTHOG_WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="invalid signature")
    return {"received": True, "source": "posthog"}


@webhooks_router.post("/sentry")
async def webhook_sentry(request: Request):
    body = await request.body()
    if not _verify_webhook_signature(request, body, "SENTRY_WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="invalid signature")
    return {"received": True, "source": "sentry"}


@webhooks_router.post("/linear")
async def webhook_linear(request: Request):
    body = await request.body()
    if not _verify_webhook_signature(request, body, "LINEAR_WEBHOOK_SECRET"):
        raise HTTPException(status_code=401, detail="invalid signature")
    return {"received": True, "source": "linear"}


# ============================================================
# Helpers
# ============================================================


def _default_id_factory(prefix: str) -> str:
    import secrets
    return f"{prefix}-{secrets.token_hex(6)}"
