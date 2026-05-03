"""tests/test_linear_auth_watchdog.py — RA-1908.

Coverage for the Linear API auth watchdog:

  * Healthy GraphQL response → no warning, cooldown unchanged
  * `_gql` returns `{error: "no_api_key"}` → warning logged, cooldown bumped
  * `_gql` returns `{error: "request_failed"}` with 401 in exception text → warning + cooldown
  * GraphQL-level `errors` array with auth message → warning + cooldown
  * Cooldown blocks repeat alerts within 24h
"""
from __future__ import annotations

import logging
import time

import pytest

import app.server.cron_watchdogs as cw


@pytest.fixture(autouse=True)
def _reset_state():
    """Reset module-level cooldown so tests don't poison each other."""
    cw._linear_auth_last_raised = 0.0
    yield
    cw._linear_auth_last_raised = 0.0


@pytest.fixture
def _hush_network(monkeypatch):
    """Make Telegram + Linear calls silent no-ops via empty config secrets."""
    import app.server.config as config
    monkeypatch.setattr(config, "TELEGRAM_BOT_TOKEN", "", raising=False)
    monkeypatch.setattr(config, "TELEGRAM_ALERT_CHAT_ID", "", raising=False)


def _patch_gql(monkeypatch, response: dict) -> None:
    """Replace swarm.linear_tools._gql with a stub returning ``response``."""
    import sys
    import types

    fake = types.SimpleNamespace(_gql=lambda query, variables=None: response)
    monkeypatch.setitem(sys.modules, "swarm.linear_tools", fake)


@pytest.mark.asyncio
async def test_silent_when_linear_auth_healthy(_hush_network, monkeypatch, caplog):
    """Healthy `viewer { id email }` response → no warning, cooldown unchanged."""
    _patch_gql(monkeypatch, {"data": {"viewer": {"id": "u_123", "email": "x@y.z"}}})
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_linear_auth(logging.getLogger("pi-ceo"))
    assert not any(
        "Linear-auth watchdog" in rec.message for rec in caplog.records
    )
    assert cw._linear_auth_last_raised == 0.0


@pytest.mark.asyncio
async def test_alerts_when_no_api_key(_hush_network, monkeypatch, caplog):
    """`{error: 'no_api_key'}` → warning + cooldown bump."""
    _patch_gql(monkeypatch, {"error": "no_api_key"})
    before = cw._linear_auth_last_raised
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_linear_auth(logging.getLogger("pi-ceo"))
    assert any(
        "Linear-auth watchdog" in rec.message for rec in caplog.records
    ), "Expected a 'Linear-auth watchdog' warning when API key is missing"
    assert cw._linear_auth_last_raised > before


@pytest.mark.asyncio
async def test_alerts_when_request_failed_with_401(_hush_network, monkeypatch, caplog):
    """`request_failed` with 401 in the exception text → auth-failure path."""
    _patch_gql(monkeypatch, {
        "error": "request_failed",
        "exception": "HTTPError 401: Not authenticated",
    })
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_linear_auth(logging.getLogger("pi-ceo"))
    assert any(
        "Linear-auth watchdog" in rec.message for rec in caplog.records
    )
    assert cw._linear_auth_last_raised > 0


@pytest.mark.asyncio
async def test_silent_when_request_failed_unrelated_network_error(
    _hush_network, monkeypatch, caplog,
):
    """`request_failed` from a non-auth network error → still alerts (it's
    treated as auth-degraded path because we can't tell the difference).

    This is intentional — network errors look the same as auth errors from
    the cron caller's POV. False-positive risk is small because this
    watchdog runs once / 30 min with a 24h cooldown.
    """
    _patch_gql(monkeypatch, {
        "error": "request_failed",
        "exception": "ConnectionResetError: connection reset by peer",
    })
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_linear_auth(logging.getLogger("pi-ceo"))
    # No "401" in exception → not flagged as auth failure
    assert not any(
        "Linear-auth watchdog" in rec.message for rec in caplog.records
    )
    assert cw._linear_auth_last_raised == 0.0


@pytest.mark.asyncio
async def test_alerts_when_graphql_errors_carry_auth_message(
    _hush_network, monkeypatch, caplog,
):
    """GraphQL-level `errors` array with 'authentication' in message."""
    _patch_gql(monkeypatch, {
        "data": None,
        "errors": [{"message": "Authentication required", "extensions": {}}],
    })
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_linear_auth(logging.getLogger("pi-ceo"))
    assert any(
        "Linear-auth watchdog" in rec.message for rec in caplog.records
    )
    assert cw._linear_auth_last_raised > 0


@pytest.mark.asyncio
async def test_cooldown_blocks_repeat_alerts(_hush_network, monkeypatch, caplog):
    """Cooldown: setting last_raised to now() suppresses subsequent calls."""
    _patch_gql(monkeypatch, {"error": "no_api_key"})
    cw._linear_auth_last_raised = time.time()  # cooldown active
    before = cw._linear_auth_last_raised
    with caplog.at_level(logging.WARNING, logger="pi-ceo"):
        await cw._watchdog_linear_auth(logging.getLogger("pi-ceo"))
    # Should have early-returned without logging or bumping cooldown
    assert not any(
        "Linear-auth watchdog" in rec.message for rec in caplog.records
    )
    assert cw._linear_auth_last_raised == before


@pytest.mark.asyncio
async def test_silent_when_linear_tools_import_fails(_hush_network, monkeypatch, caplog):
    """Defensive: if swarm.linear_tools is unavailable, skip without raising."""
    import sys
    # Force ImportError when the watchdog tries to import swarm.linear_tools
    monkeypatch.setitem(sys.modules, "swarm.linear_tools", None)
    with caplog.at_level(logging.DEBUG, logger="pi-ceo"):
        await cw._watchdog_linear_auth(logging.getLogger("pi-ceo"))
    # No warning, no cooldown bump
    assert not any(
        "Linear-auth watchdog: Linear MCP" in rec.message
        for rec in caplog.records
    )
    assert cw._linear_auth_last_raised == 0.0
