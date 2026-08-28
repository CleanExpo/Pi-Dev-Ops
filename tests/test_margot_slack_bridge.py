"""Regression tests for the Margot Slack <-> Telegram strengthening bridge."""
from __future__ import annotations

import asyncio
import hashlib
import hmac
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.server.routes import slack_bridge as slack_route
from swarm import margot_bot
from swarm import margot_slack_bridge as bridge


def _enable_bridge(monkeypatch) -> None:
    """Enable the bridge with isolated test-only Slack configuration."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_TELEGRAM_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("SLACK_MARGOT_STRENGTHENING_CHANNEL", "C123")


def test_bridge_requires_explicit_enable(monkeypatch):
    """A token alone must not activate the cross-surface bridge."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.delenv("SLACK_TELEGRAM_BRIDGE_ENABLED", raising=False)
    assert bridge.bridge_enabled() is False


def test_mirror_telegram_turn_creates_one_thread(monkeypatch):
    """A Telegram turn becomes one Slack parent plus one Margot thread reply."""
    _enable_bridge(monkeypatch)
    calls = []

    def fake_post(**kwargs):
        """Capture synchronous Slack posts without network I/O."""
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
    """Slack strengthening shares chat memory but is not promoted to founder authority."""
    _enable_bridge(monkeypatch)
    parent = {
        "metadata": {
            "event_type": bridge.BRIDGE_EVENT_TYPE,
            "event_payload": {"chat_id": "8792816988", "turn_id": "mt-origin"},
        },
    }
    monkeypatch.setattr(bridge, "_thread_parent", lambda **_: parent)

    async def not_duplicate(*_args, **_kwargs):
        """Keep this test focused on routing rather than persistence."""
        return False

    monkeypatch.setattr(bridge, "_already_processed", not_duplicate)
    captured = {}

    async def fake_handle_turn(**kwargs):
        """Capture the shared Margot call and return a deterministic reply."""
        captured.update(kwargs)
        return SimpleNamespace(margot_text="Strengthened answer")

    monkeypatch.setattr(margot_bot, "handle_turn", fake_handle_turn)
    posts = []
    monkeypatch.setattr(
        bridge, "_post_message",
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
    assert "review context only" in captured["user_text"]
    assert captured["user_text"].endswith("Check this against the original goal")
    assert captured["message_id"] == "slack:111.444"
    assert captured["_send"] is True
    assert posts[-1]["thread_ts"] == "111.222"
    assert "Strengthened answer" in posts[-1]["text"]


def test_slack_bridge_ignores_top_level_bot_and_nonhuman_messages(monkeypatch):
    """Only human replies in a bridge thread may enter the shared Margot brain."""
    _enable_bridge(monkeypatch)
    top = asyncio.run(bridge.handle_slack_message_event({
        "type": "message", "channel": "C123", "user": "U1", "text": "hello",
    }))
    bot = asyncio.run(bridge.handle_slack_message_event({
        "type": "message", "channel": "C123", "thread_ts": "1.2",
        "text": "bot echo", "bot_id": "B123",
    }))
    nonhuman = asyncio.run(bridge.handle_slack_message_event({
        "type": "message", "channel": "C123", "thread_ts": "1.2",
        "text": "missing user",
    }))

    assert top == "ignored:not_thread_reply"
    assert bot == "ignored:bot_or_subtype"
    assert nonhuman == "ignored:not_human"


def test_durable_history_suppresses_replayed_slack_turn(monkeypatch):
    """A persisted Slack message ID suppresses a duplicate after process restart."""
    monkeypatch.setattr(
        margot_bot,
        "load_history",
        lambda *_args, **_kwargs: [SimpleNamespace(user_message_id="slack:111.444")],
    )
    duplicate = asyncio.run(bridge._already_processed("8792816988", "slack:111.444"))
    assert duplicate is True


def test_failed_event_reservation_can_be_retried():
    """Failed background processing releases its in-process event reservation."""
    event_id = "Ev-hardening-test"
    slack_route._release_failed_event(event_id)
    assert slack_route._mark_event_once(event_id) is True
    assert slack_route._mark_event_once(event_id) is False
    slack_route._release_failed_event(event_id)
    assert slack_route._mark_event_once(event_id) is True
    slack_route._release_failed_event(event_id)


def test_slack_signature_verification(monkeypatch):
    """Valid HMACs pass while stale and incorrect Slack signatures fail."""
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "secret")
    body = b'{"type":"event_callback"}'
    timestamp = "1000"
    base = b"v0:" + timestamp.encode() + b":" + body
    signature = "v0=" + hmac.new(b"secret", base, hashlib.sha256).hexdigest()

    assert slack_route._verify_signature(
        raw_body=body, timestamp=timestamp, signature=signature, now=1100,
    ) is True
    assert slack_route._verify_signature(
        raw_body=body, timestamp=timestamp, signature=signature, now=1401,
    ) is False
    assert slack_route._verify_signature(
        raw_body=body, timestamp=timestamp, signature="v0=bad", now=1100,
    ) is False


class _ChunkedRequest:
    """Minimal Request-like object for exercising chunked body limits."""

    def __init__(self, chunks: list[bytes], headers: dict[str, str] | None = None):
        self._chunks = chunks
        self.headers = headers or {}

    async def stream(self):
        """Yield configured chunks as an ASGI request body would."""
        for chunk in self._chunks:
            yield chunk


def test_chunked_slack_body_is_bounded_without_content_length():
    """Chunked requests cannot bypass the Slack webhook's one-MiB body cap."""
    request = _ChunkedRequest([
        b"a" * slack_route._MAX_SLACK_REQUEST_BODY,
        b"b",
    ])
    with pytest.raises(HTTPException) as exc:
        asyncio.run(slack_route._read_limited_body(request))
    assert exc.value.status_code == 413


def test_small_chunked_slack_body_is_preserved():
    """Bodies under the cap are reassembled exactly for signature validation."""
    request = _ChunkedRequest([b'{"type":', b'"event_callback"}'])
    body = asyncio.run(slack_route._read_limited_body(request))
    assert body == b'{"type":"event_callback"}'
