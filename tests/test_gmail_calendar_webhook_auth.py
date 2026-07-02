"""RA-6899 — Gmail + Calendar push-intake webhook authentication."""
from __future__ import annotations

import base64
import json
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.server import config as app_config
from app.server.routes import webhooks


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(app_config, "GMAIL_WEBHOOK_SECRET", "gmail-secret")
    monkeypatch.setattr(app_config, "CALENDAR_WEBHOOK_SECRET", "cal-secret")
    monkeypatch.setattr(app_config, "GMAIL_PUBSUB_AUDIENCE", "")
    monkeypatch.setattr(webhooks.config, "GMAIL_WEBHOOK_SECRET", "gmail-secret")
    monkeypatch.setattr(webhooks.config, "CALENDAR_WEBHOOK_SECRET", "cal-secret")
    monkeypatch.setattr(webhooks.config, "GMAIL_PUBSUB_AUDIENCE", "")
    monkeypatch.setattr(webhooks, "_GMAIL_INTAKE_LOG", tmp_path / "gmail.jsonl")
    monkeypatch.setattr(webhooks, "_CALENDAR_INTAKE_LOG", tmp_path / "cal.jsonl")
    app = FastAPI()
    app.include_router(webhooks.router)
    return TestClient(app)


def _gmail_body() -> dict:
    inner = json.dumps({"emailAddress": "a@b.com", "historyId": "99"})
    return {
        "message": {
            "data": base64.b64encode(inner.encode()).decode(),
            "messageId": "m1",
        },
        "subscription": "projects/x/subscriptions/y",
    }


def test_gmail_no_auth_returns_401(client):
    r = client.post("/api/webhook/gmail", json=_gmail_body())
    assert r.status_code == 401


def test_gmail_wrong_secret_returns_401(client):
    r = client.post(
        "/api/webhook/gmail",
        headers={"X-Gmail-Webhook-Secret": "wrong"},
        json=_gmail_body(),
    )
    assert r.status_code == 401


def test_gmail_happy_path(client):
    r = client.post(
        "/api/webhook/gmail",
        headers={"X-Gmail-Webhook-Secret": "gmail-secret"},
        json=_gmail_body(),
    )
    assert r.status_code == 200, r.text
    assert r.json()["ok"] is True


def test_gmail_unconfigured_secret_returns_503(client, monkeypatch):
    monkeypatch.setattr(webhooks.config, "GMAIL_WEBHOOK_SECRET", "")
    r = client.post(
        "/api/webhook/gmail",
        headers={"X-Gmail-Webhook-Secret": "anything"},
        json=_gmail_body(),
    )
    assert r.status_code == 503


def test_gmail_oidc_bearer_accepted_when_valid(client, monkeypatch):
    monkeypatch.setattr(webhooks.config, "GMAIL_PUBSUB_AUDIENCE", "https://example.com/hook")
    with patch.object(webhooks, "_verify_google_pubsub_oidc", return_value=True):
        r = client.post(
            "/api/webhook/gmail",
            headers={"Authorization": "Bearer fake-jwt"},
            json=_gmail_body(),
        )
    assert r.status_code == 200


def test_calendar_no_auth_returns_401(client):
    r = client.post(
        "/api/webhook/calendar",
        headers={"X-Goog-Channel-Id": "c1", "X-Goog-Resource-State": "exists"},
    )
    assert r.status_code == 401


def test_calendar_channel_token_happy_path(client):
    r = client.post(
        "/api/webhook/calendar",
        headers={
            "X-Goog-Channel-Id": "c1",
            "X-Goog-Resource-State": "exists",
            "X-Goog-Channel-Token": "cal-secret",
        },
    )
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "exists"


def test_calendar_wrong_token_returns_401(client):
    r = client.post(
        "/api/webhook/calendar",
        headers={
            "X-Goog-Channel-Id": "c1",
            "X-Goog-Resource-State": "sync",
            "X-Goog-Channel-Token": "wrong",
        },
    )
    assert r.status_code == 401
