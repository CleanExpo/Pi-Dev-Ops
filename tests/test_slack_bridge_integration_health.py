"""Regression coverage for Slack bridge integration health."""
from __future__ import annotations

from app.server import integration_health as health


def _clear_bridge_env(monkeypatch) -> None:
    """Remove bridge configuration so each test starts from a known state."""
    for key in (
        "SLACK_TELEGRAM_BRIDGE_ENABLED",
        "SLACK_BOT_TOKEN",
        "SLACK_SIGNING_SECRET",
        "SLACK_MARGOT_STRENGTHENING_CHANNEL",
    ):
        monkeypatch.delenv(key, raising=False)


def test_slack_bridge_probe_reports_disabled_without_network(monkeypatch):
    """Disabled config reports presence flags before any Slack network call."""
    _clear_bridge_env(monkeypatch)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Slack API must not be called for disabled bridge")

    monkeypatch.setattr(health, "_slack_api_json", fail_if_called)
    assert health._probe_slack_bridge() == (
        False,
        "bridge_disabled;enabled=0;token=missing;signing=missing;channel=missing",
    )


def test_disabled_probe_still_reports_existing_secret_presence(monkeypatch):
    """A disabled flag does not hide whether the required variables already exist."""
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-existing")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "existing-signing")
    monkeypatch.setenv("SLACK_MARGOT_STRENGTHENING_CHANNEL", "C123")
    monkeypatch.delenv("SLACK_TELEGRAM_BRIDGE_ENABLED", raising=False)

    ok, detail = health._probe_slack_bridge()

    assert ok is False
    assert detail == (
        "bridge_disabled;enabled=0;token=present;signing=present;channel=present"
    )
    assert "xoxb-existing" not in detail
    assert "existing-signing" not in detail


def test_slack_bridge_probe_reports_ready_without_exposing_secrets(monkeypatch):
    """Healthy configuration reports bot identity but never credentials."""
    token = "xoxb-do-not-print-this"
    signing = "do-not-print-signing-secret"
    bot_user = "U0BOT12345"
    monkeypatch.setenv("SLACK_TELEGRAM_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("SLACK_BOT_TOKEN", token)
    monkeypatch.setenv("SLACK_SIGNING_SECRET", signing)
    monkeypatch.setenv("SLACK_MARGOT_STRENGTHENING_CHANNEL", "C123")

    calls: list[tuple[str, dict[str, str] | None]] = []

    def healthy_probe(_token, method, payload=None):
        calls.append((method, payload))
        if method == "auth.test":
            return {"ok": True, "error": "", "user_id": bot_user}
        return {"ok": True, "error": "", "user_id": ""}

    monkeypatch.setattr(health, "_slack_api_json", healthy_probe)
    result = health._probe_slack_bridge()

    assert result == (
        True,
        f"ready;bot_user={bot_user};enabled=1;token=present;signing=present;channel=present",
    )
    assert calls == [
        ("auth.test", None),
        ("conversations.info", {"channel": "C123"}),
    ]
    rendered = repr(result)
    assert token not in rendered
    assert signing not in rendered


def test_slack_bridge_probe_reports_private_channel_access_failure(monkeypatch):
    """A valid bot outside the private room exposes only its safe user ID and error."""
    bot_user = "U0BOT12345"
    monkeypatch.setenv("SLACK_TELEGRAM_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing-test")
    monkeypatch.setenv("SLACK_MARGOT_STRENGTHENING_CHANNEL", "C123")

    def probe(_token, method, payload=None):
        if method == "auth.test":
            return {"ok": True, "error": "", "user_id": bot_user}
        return {"ok": False, "error": "channel_not_found", "user_id": ""}

    monkeypatch.setattr(health, "_slack_api_json", probe)
    assert health._probe_slack_bridge() == (
        False,
        f"channel_inaccessible:channel_not_found;bot_user={bot_user};"
        "enabled=1;token=present;signing=present;channel=present",
    )


def test_unknown_slack_error_is_never_forwarded():
    """Provider-controlled text is collapsed to a fixed safe code."""
    malicious = "token=xoxb-leak-me&redirect=https://evil.example"
    assert health._safe_slack_error("channel_not_found") == "channel_not_found"
    assert health._safe_slack_error(malicious) == "slack_error"
    assert malicious not in health._safe_slack_error(malicious)


def test_slack_user_id_is_strictly_normalized():
    """Only Slack-shaped user identifiers may reach the public health detail."""
    assert health._safe_slack_user_id("U0BOT12345") == "U0BOT12345"
    assert health._safe_slack_user_id("not-a-user-id") == ""
    assert health._safe_slack_user_id("U123;secret=oops") == ""


def test_slack_redirect_handler_refuses_all_redirects():
    """A Slack probe must never carry its Authorization header through a redirect."""
    handler = health._NoSlackRedirect()
    assert handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example") is None
