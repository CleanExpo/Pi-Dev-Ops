"""Regression tests for the Margot Slack <-> Telegram bridge."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from types import SimpleNamespace

from app.server.routes import slack_bridge as slack_route
from swarm import margot_bot
from swarm import margot_slack_bridge as bridge


def test_mirror_telegram_turn_creates_one_thread(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_MARGOT_STRENGTHENING_CHANNEL", "C123")
    calls = []

    def fake_post(**kwargs):
        calls.append(kwargs)
        return "111.222" if not kwargs.get("thread_ts") else "111.333"

    monkeypatch.setattr(bridge, "_post_message", fake_post)
    turn = SimpleNamespace(
        chat_id="8792816988",
        turn_id="mt-abc",
        user_text="Status of Mission Control?",
        margot_text="Build is moving.",
    )

    parent_ts = bridge.mirror_telegram_turn(turn)

    assert parent_ts == "111.222"
    assert len(calls) == 2
    assert calls[0]["channel"] == "C123"
    assert calls[0]["metadata"]["event_type"] == bridge.BRIDGE_EVENT_TYPE
    assert calls[0]["metadata"]["event_payload"]["chat_id"] == "8792816988"
    assert calls[1]["thread_ts"] == "111.222"
    assert "Build is moving." in calls[1]["text"]


def test_slack_thread_reply_reenters_same_margot_chat(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_MARGOT_STRENGTHENING_CHANNEL", "C123")
    parent = {
        "metadata": {
            "event_type": bridge.BRIDGE_EVENT_TYPE,
            "event_payload": {
                "chat_id": "8792816988",
                "turn_id": "mt-origin",
            },
        },
    }
    monkeypatch.setattr(bridge, "_thread_parent", lambda **_: parent)

    captured = {}

    async def fake_handle_turn(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(margot_text="Strengthened answer")

    monkeypatch.setattr(margot_bot, "handle_turn", fake_handle_turn)
    posts = []
    monkeypatch.setattr(
        bridge,
        "_post_message",
        lambda **kwargs: posts.append(kwargs) or "200.300",
    )

    result = asyncio.run(bridge.handle_slack_message_event({
        "type": "message",
        "channel": "C123",
        "thread_ts": "111.222",
        "event_ts": "111.444",
        "user": "U123",
        "text": "<@UBOT> Check this against the original goal",
    }))

    assert result == "ok"
    assert captured["chat_id"] == "8792816988"
    assert captured["user_text"] == "Check this against the original goal"
    assert captured["message_id"] == "slack:111.444"
    assert captured["_send"] is True
    assert posts[-1]["thread_ts"] == "111.222"
    assert "Strengthened answer" in posts[-1]["text"]


def test_slack_bridge_ignores_top_level_and_bot_messages(monkeypatch):
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_MARGOT_STRENGTHENING_CHANNEL", "C123")

    top = asyncio.run(bridge.handle_slack_message_event({
        "type": "message", "channel": "C123", "text": "hello",
    }))
    bot = asyncio.run(bridge.handle_slack_message_event({
        "type": "message", "channel": "C123", "thread_ts": "1.2",
        "text": "bot echo", "bot_id": "B123",
    }))

    assert top == "ignored:not_thread_reply"
    assert bot == "ignored:bot_or_subtype"


def test_slack_signature_verification(monkeypatch):
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "secret")
    body = b'{"type":"event_callback"}'
    timestamp = "1000"
    base = b"v0:" + timestamp.encode() + b":" + body
    signature = "v0=" + hmac.new(
        b"secret", base, hashlib.sha256,
    ).hexdigest()

    assert slack_route._verify_signature(
        raw_body=body,
        timestamp=timestamp,
        signature=signature,
        now=1100,
    ) is True
    assert slack_route._verify_signature(
        raw_body=body,
        timestamp=timestamp,
        signature=signature,
        now=1401,
    ) is False
    assert slack_route._verify_signature(
        raw_body=body,
        timestamp=timestamp,
        signature="v0=bad",
        now=1100,
    ) is False
