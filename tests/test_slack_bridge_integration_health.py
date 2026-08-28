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
    """Disabled configuration must fail clearly before any Slack API call."""
    _clear_bridge_env(monkeypatch)

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("Slack API must not be called for disabled bridge")

    monkeypatch.setattr(health, "_slack_api_probe", fail_if_called)
    assert health._probe_slack_bridge() == (False, "bridge_disabled")


def test_slack_bridge_probe_reports_ready_without_exposing_secrets(monkeypatch):
    """Healthy configuration reports only readiness text, never credentials."""
    token = "xoxb-do-not-print-this"
    signing = "do-not-print-signing-secret"
    monkeypatch.setenv("SLACK_TELEGRAM_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("SLACK_BOT_TOKEN", token)
    monkeypatch.setenv("SLACK_SIGNING_SECRET", signing)
    monkeypatch.setenv("SLACK_MARGOT_STRENGTHENING_CHANNEL", "C123")

    calls: list[tuple[str, dict[str, str] | None]] = []

    def healthy_probe(_token, method, payload=None):
        calls.append((method, payload))
        return True, "ok"

    monkeypatch.setattr(health, "_slack_api_probe", healthy_probe)
    result = health._probe_slack_bridge()

    assert result == (True, "ready")
    assert calls == [
        ("auth.test", None),
        ("conversations.info", {"channel": "C123"}),
    ]
    rendered = repr(result)
    assert token not in rendered
    assert signing not in rendered


def test_slack_bridge_probe_reports_private_channel_access_failure(monkeypatch):
    """A valid bot outside the private room is surfaced as channel_inaccessible."""
    monkeypatch.setenv("SLACK_TELEGRAM_BRIDGE_ENABLED", "1")
    monkeypatch.setenv("SLACK_BOT_TOKEN", "xoxb-test")
    monkeypatch.setenv("SLACK_SIGNING_SECRET", "signing-test")
    monkeypatch.setenv("SLACK_MARGOT_STRENGTHENING_CHANNEL", "C123")

    def probe(_token, method, payload=None):
        if method == "auth.test":
            return True, "ok"
        return False, "channel_not_found"

    monkeypatch.setattr(health, "_slack_api_probe", probe)
    assert health._probe_slack_bridge() == (
        False,
        "channel_inaccessible:channel_not_found",
    )
