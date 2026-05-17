from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from app.server.margot_voice_packet import (
    build_packet_from_elevenlabs_event,
    classify_route,
    persist_fallback_packet,
    redact_secret_like_values,
)


def _event(message: str, *, summary: str = "Captured portfolio task.") -> dict:
    return {
        "type": "post_call_transcription",
        "event_timestamp": 1789459200,
        "data": {
            "agent_id": "agent_margot",
            "agent_name": "Margot",
            "conversation_id": "conv_123",
            "status": "done",
            "user_id": "phill",
            "transcript": [
                {"role": "agent", "message": "How can I help?"},
                {"role": "user", "message": message},
            ],
            "analysis": {"transcript_summary": summary, "call_successful": "success"},
            "conversation_initiation_client_data": {
                "dynamic_variables": {
                    "crm_user_id": "crm-user-1",
                    "crm_user_email": "phill.mcgurk@gmail.com",
                }
            },
        },
    }


def test_low_risk_portfolio_task_routes_to_unite_crm():
    decision = classify_route("Create a portfolio task to update the Unite CRM dashboard copy")
    assert decision.route == "unite_crm"
    assert decision.business_context == "unite-group"
    assert decision.risk_level == "low"
    assert decision.approval_required is False


def test_marketing_request_routes_to_synthex_after_crm_anchor():
    decision = classify_route("Ask Synthex to prepare a LinkedIn launch campaign")
    assert decision.route == "synthex"
    assert decision.business_context == "synthex"
    assert decision.risk_level == "low"
    assert decision.approval_required is False


def test_deploy_spend_credentials_require_approval():
    decision = classify_route("Deploy production and increase ad spend with the API key")
    assert decision.route == "approval_required"
    assert decision.risk_level == "high"
    assert decision.approval_required is True
    assert "production" in decision.approval_reason
    assert "spend" in decision.approval_reason
    assert "credential" in decision.approval_reason


def test_build_packet_extracts_transcript_summary_and_actions():
    packet = build_packet_from_elevenlabs_event(_event("Create a low risk CRM task"))
    assert packet.source == "elevenlabs_voice"
    assert packet.speaker == "phill"
    assert packet.conversation_id == "conv_123"
    assert "Create a low risk CRM task" in packet.transcript_text
    assert packet.summary == "Captured portfolio task."
    assert packet.actions[0]["type"] == "create_crm_task"
    assert packet.approval_required is False


def test_redaction_removes_secret_like_values():
    text = "Use sk-abc123456789 and Bearer tokenhere and postgres://user:pass@host/db"
    clean = redact_secret_like_values(text)
    assert "sk-abc" not in clean
    assert "Bearer tokenhere" not in clean
    assert "postgres://" not in clean
    assert "[REDACTED]" in clean


def test_fallback_packet_is_written_atomically(tmp_path):
    packet = build_packet_from_elevenlabs_event(_event("Create a CRM task"))
    path = persist_fallback_packet(packet, root=tmp_path)
    assert path.exists()
    data = json.loads(path.read_text())
    assert data["packet_id"] == packet.packet_id
    assert data["sync_status"] == "fallback"
