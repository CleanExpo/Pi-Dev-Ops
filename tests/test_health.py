"""
test_health.py — Unit tests for /health endpoint payload fields.

Verifies that the /health response includes the fields mandated by CLAUDE.md:
  - linear_api_key (bool) — canonical field name for dashboard and monitoring
  - autonomy.last_tick (ISO8601 UTC str or null) — "timestamp of last successful tick"
  - autonomy.armed (bool) — "boolean confirming the loop will fire on next tick"
"""
import asyncio
import datetime
import json
import time
from unittest.mock import MagicMock

import pytest


@pytest.mark.parametrize("revision", ["a" * 40, "not-a-sha", "", "a" * 7])
def test_health_reports_only_full_deployment_revision(monkeypatch, revision):
    monkeypatch.setenv("RAILWAY_GIT_COMMIT_SHA", revision)
    monkeypatch.delenv("BUILD_REVISION", raising=False)
    data = _call_health(monkeypatch)
    assert data["revision"] == (revision if len(revision) == 40 else None)


def test_health_uses_explicit_build_revision_without_railway(monkeypatch):
    monkeypatch.delenv("RAILWAY_GIT_COMMIT_SHA", raising=False)
    monkeypatch.setenv("BUILD_REVISION", "b" * 40)
    assert _call_health(monkeypatch)["revision"] == "b" * 40


def _call_health(monkeypatch, *, linear_api_key: str = "", last_poll_at: float = 0.0,
                 poll_count: int = 0) -> dict:
    """Call the /health async handler directly and return the parsed JSON payload.

    Monkeypatches config + autonomy globals so tests are hermetic.
    Authenticated with a session-token Bearer: /health fails closed otherwise.
    """
    from app.server import config, autonomy as _autonomy
    monkeypatch.setattr(config, "LINEAR_API_KEY", linear_api_key)
    monkeypatch.setattr(_autonomy, "_last_poll_at", last_poll_at)
    monkeypatch.setattr(_autonomy, "_poll_count", poll_count)

    from starlette.datastructures import Headers
    from app.server.auth import create_session_token
    mock_req = MagicMock()
    mock_req.headers = Headers({"Authorization": f"Bearer {create_session_token()}"})

    from app.server.routes.health import health as health_fn
    response = asyncio.run(health_fn(mock_req))
    return json.loads(response.body)


def test_health_linear_api_key_true(monkeypatch):
    """linear_api_key is True when LINEAR_API_KEY is non-empty."""
    data = _call_health(monkeypatch, linear_api_key="lin_api_test_key")
    assert "linear_api_key" in data, "linear_api_key missing from /health payload"
    assert data["linear_api_key"] is True


def test_health_linear_api_key_false(monkeypatch):
    """linear_api_key is False when LINEAR_API_KEY is absent."""
    data = _call_health(monkeypatch, linear_api_key="")
    assert "linear_api_key" in data, "linear_api_key missing from /health payload"
    assert data["linear_api_key"] is False


def test_health_backward_compat_linear_key(monkeypatch):
    """legacy linear_key field is still present (dashboard CeoHealthPanel.tsx depends on it)."""
    data = _call_health(monkeypatch, linear_api_key="lin_api_test_key")
    assert "linear_key" in data, "linear_key must remain for dashboard backward-compat"
    assert data["linear_key"] is True


def test_health_autonomy_last_tick_null_when_no_poll(monkeypatch):
    """autonomy.last_tick is null when the poller has never fired (_last_poll_at=0)."""
    data = _call_health(monkeypatch, last_poll_at=0.0, poll_count=0)
    assert "autonomy" in data
    assert data["autonomy"]["last_tick"] is None


def test_health_autonomy_last_tick_iso8601_after_poll(monkeypatch):
    """autonomy.last_tick is a timezone-aware ISO8601 string after at least one poll."""
    poll_ts = time.time() - 30  # simulated: last poll was 30 s ago
    data = _call_health(monkeypatch, linear_api_key="lin_key", last_poll_at=poll_ts, poll_count=1)
    last_tick = data["autonomy"]["last_tick"]
    assert last_tick is not None, "last_tick must not be None after a poll"
    # Must parse as ISO8601
    parsed = datetime.datetime.fromisoformat(last_tick)
    assert parsed.tzinfo is not None, "last_tick must be timezone-aware (UTC)"
    # Sanity: timestamp is in the past but within the last hour
    delta = datetime.datetime.now(tz=datetime.timezone.utc) - parsed
    assert 0 < delta.total_seconds() < 3600, "last_tick should be recent"


def test_health_autonomy_armed_true_when_enabled_and_key(monkeypatch):
    """autonomy.armed is True when AUTONOMY_ENABLED and LINEAR_API_KEY are both set."""
    from app.server import config
    monkeypatch.setattr(config, "AUTONOMY_ENABLED", True)
    data = _call_health(monkeypatch, linear_api_key="lin_key")
    assert data["autonomy"]["armed"] is True


def test_health_autonomy_armed_false_when_no_key(monkeypatch):
    """autonomy.armed is False when LINEAR_API_KEY is absent even if AUTONOMY_ENABLED."""
    from app.server import config
    monkeypatch.setattr(config, "AUTONOMY_ENABLED", True)
    data = _call_health(monkeypatch, linear_api_key="")
    assert data["autonomy"]["armed"] is False


@pytest.mark.parametrize("enabled_env,shadow_env,want", [
    (None, None, (False, True)),   # unset: the orchestrator does not start; bots run in shadow
    ("1", None, (True, True)),
    ("1", "0", (True, False)),
    ("0", "0", (False, False)),
    ("true", None, (False, True)),  # app_factory starts the swarm only for exactly "1"
])
def test_health_swarm_flags_match_the_runtime_gates(monkeypatch, enabled_env, shadow_env, want):
    """RA-7849: /health defaulted TAO_SWARM_ENABLED to on and TAO_SWARM_SHADOW to off, the
    opposite of app_factory and swarm/config, so the sidebar could show "Swarm Active" while
    production logged "Swarm orchestrator NOT started"."""
    for name, value in (("TAO_SWARM_ENABLED", enabled_env), ("TAO_SWARM_SHADOW", shadow_env)):
        if value is None:
            monkeypatch.delenv(name, raising=False)
        else:
            monkeypatch.setenv(name, value)
    data = _call_health(monkeypatch)
    assert (data["swarm_enabled"], data["swarm_shadow"]) == want
