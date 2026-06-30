"""tests/test_intake_webhook.py — UNI-2214 item 1 push-intake substrate.

The authenticated HTTP endpoint that lets any external producer (email-listener,
calendar-watcher, or any system holding content) feed the closed loop without
Phill driving. Proves the secret gate is fail-closed, payloads are validated,
the happy path enqueues with source provenance, and an enqueue failure surfaces
as 503 rather than a silent drop.
"""
from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server.routes import webhooks
from app.server import config as app_config


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(app_config, "INTAKE_WEBHOOK_SECRET", "s3cr3t")
    monkeypatch.setattr(webhooks.config, "INTAKE_WEBHOOK_SECRET", "s3cr3t")
    app = FastAPI()
    app.include_router(webhooks.router)
    return TestClient(app)


@pytest.fixture
def spy_enqueue(monkeypatch):
    calls: list[dict] = []
    from swarm import closed_loop
    monkeypatch.setattr(closed_loop, "enqueue_trigger",
                        lambda text, **kw: calls.append({"text": text, **kw}))
    return calls


def test_happy_path_enqueues_with_provenance(client, spy_enqueue):
    r = client.post("/api/webhook/intake",
                    headers={"X-Intake-Secret": "s3cr3t"},
                    json={"source": "email", "text": "Reply to Duncan re: invoice",
                          "chat_id": "123"})
    assert r.status_code == 200, r.text
    assert r.json() == {"ok": True, "queued": True, "source": "email"}
    assert len(spy_enqueue) == 1
    assert spy_enqueue[0]["text"] == "[email] Reply to Duncan re: invoice"
    assert spy_enqueue[0]["chat_id"] == "123"


def test_presented_secret_but_unconfigured_is_503(client, monkeypatch, spy_enqueue):
    # Header present but server can't validate (unconfigured) → 503, never accept.
    monkeypatch.setattr(webhooks.config, "INTAKE_WEBHOOK_SECRET", "")
    r = client.post("/api/webhook/intake",
                    headers={"X-Intake-Secret": "anything"},
                    json={"source": "email", "text": "x"})
    assert r.status_code == 503
    assert spy_enqueue == []


def test_no_header_is_401_even_when_unconfigured(client, monkeypatch, spy_enqueue):
    # The config-independent guarantee that keeps the smoke probe stable: an
    # unauthenticated request (no header) is always 401, configured or not.
    monkeypatch.setattr(webhooks.config, "INTAKE_WEBHOOK_SECRET", "")
    r = client.post("/api/webhook/intake",
                    json={"source": "email", "text": "x"})
    assert r.status_code == 401
    assert spy_enqueue == []


def test_wrong_secret_rejected(client, spy_enqueue):
    r = client.post("/api/webhook/intake",
                    headers={"X-Intake-Secret": "wrong"},
                    json={"source": "email", "text": "x"})
    assert r.status_code == 401
    assert spy_enqueue == []


def test_missing_secret_header_rejected(client, spy_enqueue):
    r = client.post("/api/webhook/intake",
                    json={"source": "email", "text": "x"})
    assert r.status_code == 401
    assert spy_enqueue == []


def test_invalid_source_rejected(client, spy_enqueue):
    r = client.post("/api/webhook/intake",
                    headers={"X-Intake-Secret": "s3cr3t"},
                    json={"source": "twitter", "text": "x"})
    assert r.status_code == 422
    assert spy_enqueue == []


def test_empty_text_rejected(client, spy_enqueue):
    r = client.post("/api/webhook/intake",
                    headers={"X-Intake-Secret": "s3cr3t"},
                    json={"source": "email", "text": "   "})
    assert r.status_code == 422
    assert spy_enqueue == []


def test_enqueue_failure_surfaces_503(client, monkeypatch):
    from swarm import closed_loop
    monkeypatch.setattr(closed_loop, "enqueue_trigger",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("disk full")))
    r = client.post("/api/webhook/intake",
                    headers={"X-Intake-Secret": "s3cr3t"},
                    json={"source": "calendar", "text": "Standup at 9"})
    assert r.status_code == 503
