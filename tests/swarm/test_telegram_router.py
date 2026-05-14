"""Tests for swarm/telegram_router.py — RA-2232 multi-bot Telegram router.

Verifies channel resolution (general / research / dev / ops / marketing),
env-var precedence (TELEGRAM_HOME_CHANNEL > TELEGRAM_ALERT_CHAT_ID for
back-compat), fallback-to-general behaviour with the "[fallback from X]"
prefix, the API URL the router posts to, and the back-compat shim in
telegram_alerts.send.

All network is stubbed via monkeypatch on ``urllib.request.urlopen`` —
the swarm uses urllib not requests, so this matches reality.
"""
from __future__ import annotations

import json
from io import BytesIO
from typing import Any
from unittest.mock import patch

import pytest

from swarm import telegram_router as tr


# ─── Helpers ───────────────────────────────────────────────────────────────


class _FakeResponse:
    """Stand-in for ``urllib.request.urlopen`` return value."""

    def __init__(self, body: bytes = b'{"ok": true}'):
        self._body = body

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body


@pytest.fixture
def captured_posts(monkeypatch):
    """Capture every POST the router makes without touching the network.

    Returns a list — each entry is the dict that was JSON-encoded into the
    request body, plus the request URL. Test assertions read from this list.
    """
    calls: list[dict[str, Any]] = []

    def _fake_urlopen(req, timeout=10):  # noqa: ARG001
        body = req.data.decode() if req.data else "{}"
        calls.append({"url": req.full_url, "payload": json.loads(body)})
        return _FakeResponse()

    monkeypatch.setattr("swarm.telegram_router.urllib.request.urlopen", _fake_urlopen)
    return calls


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Strip every TELEGRAM_* env var so each test starts from a blank slate."""
    for var in (
        "TELEGRAM_BOT_TOKEN",
        "TELEGRAM_HOME_CHANNEL",
        "TELEGRAM_ALERT_CHAT_ID",
        "TELEGRAM_BOT_TOKEN_RESEARCH",
        "TELEGRAM_CHAT_ID_RESEARCH",
        "TELEGRAM_BOT_TOKEN_DEV",
        "TELEGRAM_CHAT_ID_DEV",
        "TELEGRAM_BOT_TOKEN_OPS",
        "TELEGRAM_CHAT_ID_OPS",
        "TELEGRAM_BOT_TOKEN_MARKETING",
        "TELEGRAM_CHAT_ID_MARKETING",
    ):
        monkeypatch.delenv(var, raising=False)


# ─── Tests ─────────────────────────────────────────────────────────────────


def test_load_channel_general_reads_legacy_env_vars(monkeypatch):
    """'general' resolves the existing TELEGRAM_BOT_TOKEN + TELEGRAM_HOME_CHANNEL.

    TELEGRAM_HOME_CHANNEL is the new name; TELEGRAM_ALERT_CHAT_ID is the
    legacy name. The router must prefer the new name when both are set
    (Phill can migrate at his leisure).
    """
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "111:legacy-token")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "999")
    monkeypatch.setenv("TELEGRAM_ALERT_CHAT_ID", "888")  # legacy — should be overridden

    cfg = tr._load_channel("general")

    assert cfg.name == "general"
    assert cfg.token == "111:legacy-token"
    assert cfg.chat_id == "999"  # new name wins
    assert cfg.configured is True


def test_load_channel_general_falls_back_to_legacy_alert_chat_id(monkeypatch):
    """When TELEGRAM_HOME_CHANNEL is absent, the legacy TELEGRAM_ALERT_CHAT_ID
    still resolves — existing single-bot deploys keep working untouched."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "111:legacy-token")
    monkeypatch.setenv("TELEGRAM_ALERT_CHAT_ID", "888")

    cfg = tr._load_channel("general")

    assert cfg.token == "111:legacy-token"
    assert cfg.chat_id == "888"
    assert cfg.configured is True


def test_load_channel_dev_reads_specialist_env_vars(monkeypatch):
    """'dev' resolves TELEGRAM_BOT_TOKEN_DEV + TELEGRAM_CHAT_ID_DEV."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_DEV", "222:dev-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID_DEV", "-100777")

    cfg = tr._load_channel("dev")

    assert cfg.name == "dev"
    assert cfg.token == "222:dev-token"
    assert cfg.chat_id == "-100777"
    assert cfg.configured is True


def test_send_falls_back_to_general_with_prefix(monkeypatch, captured_posts):
    """When a specialist channel isn't configured but general is, the message
    routes to general with a '[fallback from <channel>]' tag in the body."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "111:general")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "999")
    # No TELEGRAM_BOT_TOKEN_MARKETING / CHAT_ID_MARKETING set.

    ok = tr.send(
        "Brand-guardian violation: voice off",
        channel="marketing",
        severity="high",
        bot_name="BrandGuardian",
    )

    assert ok is True
    assert len(captured_posts) == 1
    sent = captured_posts[0]
    # Routed to the general bot's API URL.
    assert "111:general" in sent["url"]
    # Landed in general's chat.
    assert sent["payload"]["chat_id"] == "999"
    # Fallback tag present in the body so Phill can see which bot is missing.
    assert "[fallback from marketing]" in sent["payload"]["text"]
    # Original message preserved.
    assert "Brand-guardian violation: voice off" in sent["payload"]["text"]


def test_send_returns_false_when_general_also_missing(monkeypatch, captured_posts):
    """If neither the requested channel nor general is configured, return
    False (the caller sees the failure) and post nothing."""
    # No env vars at all (autouse clear_env fixture stripped them).
    ok = tr.send("anything", channel="dev")

    assert ok is False
    assert captured_posts == []


def test_send_posts_to_correct_telegram_api_url(monkeypatch, captured_posts):
    """When the dev channel is configured, the router POSTs to
    api.telegram.org/bot<DEV_TOKEN>/sendMessage with the dev chat_id."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_DEV", "222:dev-token")
    monkeypatch.setenv("TELEGRAM_CHAT_ID_DEV", "-100777")

    ok = tr.send(
        "PR opened: feature_orchestrator → IDD-3 → RA-4180",
        channel="dev",
        severity="info",
        bot_name="FeatureOrchestrator",
    )

    assert ok is True
    assert len(captured_posts) == 1
    sent = captured_posts[0]
    assert sent["url"] == "https://api.telegram.org/bot222:dev-token/sendMessage"
    assert sent["payload"]["chat_id"] == "-100777"
    assert sent["payload"]["parse_mode"] == "HTML"
    # No fallback tag — this hit the dev bot directly.
    assert "[fallback from" not in sent["payload"]["text"]
    # AGENT OUTPUT prefix mirrors telegram_alerts formatting.
    assert "[AGENT OUTPUT]" in sent["payload"]["text"]
    assert "FeatureOrchestrator" in sent["payload"]["text"]


def test_configured_channels_reflects_env_subset(monkeypatch):
    """configured_channels() returns exactly the channels with both token
    + chat_id set — used by the health-check to show Phill what's live."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "111:gen")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "999")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_DEV", "222:dev")
    monkeypatch.setenv("TELEGRAM_CHAT_ID_DEV", "777")
    # ops has token but no chat_id — must NOT be reported configured
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN_OPS", "333:ops")

    live = tr.configured_channels()

    assert set(live) == {"general", "dev"}
    assert "ops" not in live
    assert "research" not in live
    assert "marketing" not in live


def test_telegram_alerts_send_routes_to_general(monkeypatch, captured_posts):
    """Back-compat: swarm.telegram_alerts.send still works and routes to
    general — every existing call site (orchestrator, bots/*) keeps firing."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "111:gen")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "999")

    from swarm import telegram_alerts as ta

    ok = ta.send("legacy caller payload", severity="info", bot_name="Guardian")

    assert ok is True
    assert len(captured_posts) == 1
    sent = captured_posts[0]
    # Hit the general bot.
    assert "111:gen" in sent["url"]
    assert sent["payload"]["chat_id"] == "999"
    # No fallback tag — general was configured.
    assert "[fallback from" not in sent["payload"]["text"]
    # Severity glyph + bot_name carried through.
    assert "💬 INFO" in sent["payload"]["text"]
    assert "Guardian" in sent["payload"]["text"]


def test_send_swallows_network_errors(monkeypatch):
    """Network errors return False (fire-and-forget) — never raise."""
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "111:gen")
    monkeypatch.setenv("TELEGRAM_HOME_CHANNEL", "999")

    def _boom(req, timeout=10):  # noqa: ARG001
        raise ConnectionError("network down")

    monkeypatch.setattr("swarm.telegram_router.urllib.request.urlopen", _boom)

    ok = tr.send("will fail", channel="general")
    assert ok is False  # logged at WARNING, not raised
