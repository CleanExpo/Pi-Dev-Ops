from __future__ import annotations

import json
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))


def _event(message: str = "Create a low risk Unite CRM portfolio task") -> dict:
    return {
        "type": "post_call_transcription",
        "event_timestamp": 1789459200,
        "data": {
            "agent_id": "agent_margot",
            "conversation_id": "conv_route",
            "status": "done",
            "user_id": "phill",
            "transcript": [{"role": "user", "message": message}],
            "analysis": {"transcript_summary": message, "call_successful": "success"},
            "conversation_initiation_client_data": {
                "dynamic_variables": {
                    "crm_user_id": "crm-user-1",
                    "crm_user_email": "phill.mcgurk@gmail.com",
                }
            },
        },
    }


def _client(
    monkeypatch,
    *,
    construct_event=None,
    crm_status=200,
    crm_body=None,
    kanban_id="k-voice",
):
    from app.server.routes import elevenlabs

    monkeypatch.setenv("ELEVENLABS_API_KEY", "xi-test")
    monkeypatch.setenv("ELEVENLABS_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setenv("UNITE_CRM_API_URL", "https://unite-group.in")
    monkeypatch.setenv("UNITE_CRM_INGEST_TOKEN", "ingest-test")
    monkeypatch.setenv("HERMES_KANBAN_BOARD", "unite-group-portfolio-ops")
    monkeypatch.setattr(
        elevenlabs,
        "_construct_event",
        construct_event or (lambda raw, sig, secret: json.loads(raw)),
    )

    class FakeResponse:
        status_code = crm_status

        def json(self):
            return crm_body or {
                "ok": True,
                "crm_task_id": "task-1",
                "crm_session_id": "session-1",
                "task_title": "Task",
            }

        @property
        def text(self):
            return json.dumps(self.json())

    class FakeHttp:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def post(self, url, json, headers):
            self.url = url
            self.payload = json
            self.headers = headers
            return FakeResponse()

    fake_http = FakeHttp()
    monkeypatch.setattr(elevenlabs.httpx, "Client", lambda timeout: fake_http)
    monkeypatch.setattr(elevenlabs.kanban_adapter, "create_card", lambda **kwargs: kanban_id)

    app = FastAPI()
    app.include_router(elevenlabs.router)
    return TestClient(app)


def test_webhook_rejects_bad_signature(monkeypatch):
    def explode(raw, sig, secret):
        raise ValueError("invalid")

    client = _client(monkeypatch, construct_event=explode)
    res = client.post(
        "/api/elevenlabs/margot/post-call",
        content=json.dumps(_event()),
        headers={"ElevenLabs-Signature": "bad"},
    )
    assert res.status_code == 401


def test_webhook_rejects_missing_signature_before_config(monkeypatch):
    from app.server.routes import elevenlabs

    monkeypatch.delenv("ELEVENLABS_WEBHOOK_SECRET", raising=False)
    app = FastAPI()
    app.include_router(elevenlabs.router)
    client = TestClient(app)

    res = client.post("/api/elevenlabs/margot/post-call", content=json.dumps(_event()))

    assert res.status_code == 401


def test_webhook_creates_crm_task_and_kanban_card(monkeypatch):
    client = _client(monkeypatch)
    res = client.post(
        "/api/elevenlabs/margot/post-call",
        content=json.dumps(_event()),
        headers={"ElevenLabs-Signature": "sig"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "green"
    assert body["crm_task_id"] == "task-1"
    assert body["kanban_task_id"] == "k-voice"
    assert body["fallback_path"] is None


def test_webhook_persists_fallback_when_crm_fails(monkeypatch, tmp_path):
    from app.server.routes import elevenlabs

    monkeypatch.setattr(elevenlabs, "FALLBACK_ROOT", tmp_path)
    client = _client(monkeypatch, crm_status=503, kanban_id="k-fallback")
    res = client.post(
        "/api/elevenlabs/margot/post-call",
        content=json.dumps(_event()),
        headers={"ElevenLabs-Signature": "sig"},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["status"] == "yellow"
    assert body["crm_task_id"] is None
    assert body["kanban_task_id"] == "k-fallback"
    assert Path(body["fallback_path"]).exists()
