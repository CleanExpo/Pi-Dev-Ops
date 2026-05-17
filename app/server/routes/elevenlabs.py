"""ElevenLabs post-call webhook routes for Margot voice intake."""
from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import httpx
from fastapi import APIRouter, Header, HTTPException, Request
from pydantic import BaseModel

from app.server.margot_voice_packet import (
    FALLBACK_ROOT,
    VoicePacket,
    build_packet_from_elevenlabs_event,
    packet_to_dict,
    persist_fallback_packet,
)
from swarm import kanban_adapter

log = logging.getLogger("pi-ceo.routes.elevenlabs")
router = APIRouter()


class MargotVoiceWebhookResponse(BaseModel):
    status: str
    packet_id: str
    crm_task_id: str | None
    crm_session_id: str | None
    kanban_task_id: str | None
    fallback_path: str | None
    approval_required: bool
    route: str
    risk_level: str


def _construct_event(
    raw_body: str,
    sig_header: str | None,
    secret: str,
) -> dict[str, Any]:
    if not sig_header:
        raise ValueError("missing ElevenLabs-Signature")
    from elevenlabs.client import ElevenLabs  # noqa: PLC0415

    api_key = os.environ.get("ELEVENLABS_API_KEY", "").strip()
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY missing")
    client = ElevenLabs(api_key=api_key)
    event = client.webhooks.construct_event(
        rawBody=raw_body,
        sig_header=sig_header,
        secret=secret,
    )
    if not isinstance(event, dict):
        raise ValueError("ElevenLabs webhook parser did not return a dict")
    return event


def _crm_endpoint() -> tuple[str, str] | None:
    api_url = os.environ.get("UNITE_CRM_API_URL", "").strip().rstrip("/")
    token = os.environ.get("UNITE_CRM_INGEST_TOKEN", "").strip()
    if not api_url or not token:
        return None
    return f"{api_url}/api/pi-ceo/margot-voice/task", token


def _create_crm_task(packet: VoicePacket) -> dict[str, Any] | None:
    endpoint = _crm_endpoint()
    if endpoint is None:
        return None
    url, token = endpoint
    try:
        with httpx.Client(timeout=12.0) as client:
            res = client.post(
                url,
                json=packet_to_dict(packet),
                headers={"Authorization": f"Bearer {token}"},
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("margot voice CRM write failed: %s", exc)
        return None
    if res.status_code >= 400:
        log.warning("margot voice CRM write HTTP %s: %s", res.status_code, res.text[:200])
        return None
    try:
        data = res.json()
    except Exception:
        return None
    return data if data.get("ok") else None


def _kanban_body(
    packet: VoicePacket,
    *,
    crm: dict[str, Any] | None,
    fallback_path: Path | None,
) -> str:
    lines = [
        f"Summary: {packet.summary}",
        f"Requested outcome: {packet.requested_outcome}",
        f"Route: {packet.route}",
        f"Business context: {packet.business_context}",
        f"Risk: {packet.risk_level}",
        f"Approval required: {'yes' if packet.approval_required else 'no'}",
    ]
    if packet.approval_reason:
        lines.append(f"Approval reason: {packet.approval_reason}")
    if crm:
        lines.append(f"CRM task: {crm.get('crm_task_id')}")
        lines.append(f"CRM voice session: {crm.get('crm_session_id')}")
    if fallback_path:
        lines.append(f"Fallback packet: {fallback_path}")
    lines.append(f"ElevenLabs conversation: {packet.conversation_id}")
    return "\n".join(lines)


def _create_kanban_card(
    packet: VoicePacket,
    *,
    crm: dict[str, Any] | None,
    fallback_path: Path | None,
) -> str | None:
    board = os.environ.get("HERMES_KANBAN_BOARD", "unite-group-portfolio-ops").strip() or None
    title_prefix = "APPROVAL" if packet.approval_required else "VOICE"
    title = f"[{title_prefix}@{packet.business_context}] {packet.summary[:90]}"
    return kanban_adapter.create_card(
        title=title,
        body=_kanban_body(packet, crm=crm, fallback_path=fallback_path),
        tenant="pi-ceo",
        priority=100 if packet.approval_required else 80,
        idempotency_key=packet.packet_id,
        board=board,
        triage=packet.approval_required,
    )


@router.post(
    "/api/elevenlabs/margot/post-call",
    response_model=MargotVoiceWebhookResponse,
)
async def margot_post_call(
    request: Request,
    elevenlabs_signature: str | None = Header(default=None, alias="ElevenLabs-Signature"),
) -> MargotVoiceWebhookResponse:
    secret = os.environ.get("ELEVENLABS_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(503, "ELEVENLABS_WEBHOOK_SECRET not configured")

    raw = (await request.body()).decode("utf-8")
    try:
        event = _construct_event(raw, elevenlabs_signature, secret)
    except Exception as exc:
        log.warning("invalid ElevenLabs webhook signature: %s", exc)
        raise HTTPException(401, "invalid ElevenLabs webhook signature") from exc

    if event.get("type") != "post_call_transcription":
        return MargotVoiceWebhookResponse(
            status="ignored",
            packet_id="",
            crm_task_id=None,
            crm_session_id=None,
            kanban_task_id=None,
            fallback_path=None,
            approval_required=False,
            route="ignored",
            risk_level="low",
        )

    packet = build_packet_from_elevenlabs_event(event)
    crm = _create_crm_task(packet)
    fallback_path: Path | None = None
    status = "green"
    if crm is None:
        fallback_path = persist_fallback_packet(packet, root=FALLBACK_ROOT)
        status = "yellow"

    kanban_id = _create_kanban_card(packet, crm=crm, fallback_path=fallback_path)
    if kanban_id is None:
        status = "yellow"

    return MargotVoiceWebhookResponse(
        status=status,
        packet_id=packet.packet_id,
        crm_task_id=str(crm.get("crm_task_id")) if crm else None,
        crm_session_id=str(crm.get("crm_session_id")) if crm else None,
        kanban_task_id=kanban_id,
        fallback_path=str(fallback_path) if fallback_path else None,
        approval_required=packet.approval_required,
        route=packet.route,
        risk_level=packet.risk_level,
    )
