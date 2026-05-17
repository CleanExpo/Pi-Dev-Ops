"""Margot voice packet normalization for ElevenLabs post-call webhooks."""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FALLBACK_ROOT = Path(".harness/margot/voice")

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"Bearer\s+[A-Za-z0-9._\-]{8,}", re.I),
    re.compile(r"postgres://\S+", re.I),
    re.compile(r"SUPABASE_[A-Z0-9_]+\s*=\s*\S+", re.I),
]

HIGH_RISK_KEYWORDS = {
    "production": "production",
    "deploy": "production",
    "publish": "publishing",
    "spend": "spend",
    "ads": "spend",
    "ad budget": "spend",
    "credential": "credential",
    "password": "credential",
    "api key": "credential",
    "secret": "credential",
    "endpoint": "endpoint",
    "workflow": "workflow routing",
    "company direction": "strategy",
    "strategy": "strategy",
    "external commitment": "external commitment",
}

MARKETING_KEYWORDS = {
    "campaign",
    "linkedin",
    "seo",
    "marketing",
    "ad copy",
    "campaign copy",
    "marketing copy",
    "ad creative",
    "content calendar",
    "brand voice",
}

REPO_KEYWORDS = {
    "restoreassist": "restoreassist",
    "ato": "ato",
    "dr-nrpg": "dr-nrpg",
    "nrpg": "dr-nrpg",
    "ccw": "ccw",
    "carsi": "carsi",
    "disaster recovery": "disaster-recovery",
}


@dataclass
class RouteDecision:
    route: str
    business_context: str
    risk_level: str
    approval_required: bool
    approval_reason: str = ""


@dataclass
class VoicePacket:
    packet_id: str
    source: str
    speaker: str
    crm_user_id: str
    crm_user_email: str
    conversation_id: str
    transcript_text: str
    summary: str
    requested_outcome: str
    business_context: str
    route: str
    risk_level: str
    approval_required: bool
    approval_reason: str
    actions: list[dict[str, Any]] = field(default_factory=list)
    evidence_refs: dict[str, str] = field(default_factory=dict)
    sync_status: str = "new"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


def redact_secret_like_values(text: str) -> str:
    clean = text or ""
    for pattern in SECRET_PATTERNS:
        clean = pattern.sub("[REDACTED]", clean)
    return clean


def _safe_text(value: Any) -> str:
    return redact_secret_like_values(str(value or "").strip())


def classify_route(transcript_text: str) -> RouteDecision:
    text = transcript_text.lower()
    reasons = sorted({label for key, label in HIGH_RISK_KEYWORDS.items() if key in text})
    if reasons:
        return RouteDecision(
            route="approval_required",
            business_context="unite-group",
            risk_level="high",
            approval_required=True,
            approval_reason=", ".join(reasons),
        )
    if any(key in text for key in MARKETING_KEYWORDS):
        return RouteDecision(
            route="synthex",
            business_context="synthex",
            risk_level="low",
            approval_required=False,
        )
    for key, context in REPO_KEYWORDS.items():
        if key in text:
            return RouteDecision(
                route="repo_execution",
                business_context=context,
                risk_level="low",
                approval_required=False,
            )
    return RouteDecision(
        route="unite_crm",
        business_context="unite-group",
        risk_level="low",
        approval_required=False,
    )


def _transcript_text(event: dict[str, Any]) -> str:
    transcript = ((event.get("data") or {}).get("transcript") or [])
    lines: list[str] = []
    for item in transcript:
        role = _safe_text(item.get("role"))
        message = _safe_text(item.get("message"))
        if message:
            lines.append(f"{role}: {message}" if role else message)
    return "\n".join(lines).strip()


def _dynamic_vars(event: dict[str, Any]) -> dict[str, Any]:
    data = event.get("data") or {}
    init = data.get("conversation_initiation_client_data") or {}
    return init.get("dynamic_variables") or {}


def _packet_id(conversation_id: str, transcript_text: str) -> str:
    raw = f"{conversation_id}:{transcript_text}".encode("utf-8")
    return "voice_" + hashlib.sha256(raw).hexdigest()[:16]


def build_packet_from_elevenlabs_event(event: dict[str, Any]) -> VoicePacket:
    data = event.get("data") or {}
    dynamic = _dynamic_vars(event)
    conversation_id = _safe_text(data.get("conversation_id"))
    transcript_text = _transcript_text(event)
    analysis = data.get("analysis") or {}
    summary = _safe_text(analysis.get("transcript_summary")) or transcript_text[:240]
    decision = classify_route(transcript_text)
    packet_id = _packet_id(conversation_id, transcript_text)
    action_status = "approval_required" if decision.approval_required else "pending"
    action_type = "request_approval" if decision.approval_required else "create_crm_task"
    return VoicePacket(
        packet_id=packet_id,
        source="elevenlabs_voice",
        speaker="phill",
        crm_user_id=_safe_text(dynamic.get("crm_user_id")),
        crm_user_email=_safe_text(dynamic.get("crm_user_email")),
        conversation_id=conversation_id,
        transcript_text=transcript_text,
        summary=summary,
        requested_outcome=summary,
        business_context=decision.business_context,
        route=decision.route,
        risk_level=decision.risk_level,
        approval_required=decision.approval_required,
        approval_reason=decision.approval_reason,
        actions=[{"type": action_type, "status": action_status, "evidence_ref": ""}],
        evidence_refs={"elevenlabs_conversation_id": conversation_id},
    )


def packet_to_dict(packet: VoicePacket) -> dict[str, Any]:
    return asdict(packet)


def persist_fallback_packet(packet: VoicePacket, *, root: Path = FALLBACK_ROOT) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    packet.sync_status = "fallback"
    final = root / f"{packet.packet_id}.json"
    payload = json.dumps(packet_to_dict(packet), indent=2, sort_keys=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=root, prefix=".tmp-", suffix=".json") as fh:
        fh.write(payload)
        tmp = Path(fh.name)
    tmp.replace(final)
    return final
