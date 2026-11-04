"""Readiness must reflect the Claude subscription login, not only config and the binary.

Production /health said {"status": "ok"} for four weeks while every generate was
refused with "subscription_only: active supported subscription login not verified",
because generation_readiness() never asked `claude auth status`. These tests stub
that command; they never run the real CLI.
"""

import asyncio
import json
import subprocess
import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from app.server import provider_policy as policy
from app.server import sdk_execution_boundary as sdk

# Fields the real command prints that must never reach /health. Obvious fixtures.
PRIVATE = {"email": "fixture-owner@example.invalid", "orgId": "org-fixture-not-real",
           "orgName": "Fixture Org"}
LIVE = {"loggedIn": True, "authMethod": "claude.ai", "apiProvider": "firstParty",
        "subscriptionType": "max"}
EXPOSED = {"loggedIn", "authMethod", "apiProvider", "subscriptionType", "checked_at"}


def _status(**payload):
    return Mock(returncode=0, stdout=json.dumps({**PRIVATE, **payload}), stderr="")


@pytest.fixture
def probe(monkeypatch):
    """The real probe with its background refresh enabled, or None before the fix."""
    monkeypatch.setattr(sdk.sys, "platform", "darwin")
    monkeypatch.setattr(sdk.shutil, "which", lambda name: sys.executable)
    for name in policy.CLAUDE_ROUTING_ENV:
        monkeypatch.delenv(name, raising=False)
    try:
        from app.server import claude_auth_probe
    except ImportError:  # code under test predates the probe: readiness must still fail
        yield None
        return
    claude_auth_probe.reset()
    monkeypatch.setattr(claude_auth_probe, "_schedule", claude_auth_probe._start_refresh)
    yield claude_auth_probe
    claude_auth_probe.wait_for_refresh(5)
    claude_auth_probe.reset()


def _settled(probe):
    sdk.generation_readiness()  # first call may only schedule the probe
    if probe is not None:
        assert probe.wait_for_refresh(5), "probe refresh did not finish"
    return sdk.generation_readiness()


def _authed_health():
    from app.server.auth import create_session_token
    from app.server.routes.health import health
    headers = {"Authorization": f"Bearer {create_session_token()}"}
    response = asyncio.run(health(SimpleNamespace(headers=headers, cookies={})))
    return response.status_code, response.body.decode()


@pytest.mark.parametrize("dead", [
    {**LIVE, "loggedIn": False},
    {"loggedIn": False, "authMethod": "none", "apiProvider": "firstParty"},
    {**LIVE, "authMethod": "none"},
    {**LIVE, "subscriptionType": None},
])
def test_dead_login_blocks_readiness_and_health_shows_it(monkeypatch, probe, dead):
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**dead)))
    report = _settled(probe)
    assert report["status"] == "blocked"
    assert report["ready"] is False
    assert report["auth_verified"] is False
    assert any("subscription_only" in b for b in report["blockers"])
    code, body = _authed_health()
    payload = json.loads(body)
    # Liveness stays 200/"ok": Railway restarts on a failing /health, and a restart
    # cannot log the CLI back in. Readiness is reported, not used to kill the box.
    assert code == 200 and payload["status"] == "ok"
    assert payload["generation"]["status"] == "blocked"
    assert payload["generation"]["auth"]["loggedIn"] is dead["loggedIn"]
    for value in PRIVATE.values():
        assert value not in body


@pytest.mark.parametrize("failure", [
    subprocess.TimeoutExpired(cmd="claude auth status", timeout=10),
    OSError("claude: not executable"),
    Mock(returncode=1, stdout="", stderr="boom"),
    Mock(returncode=0, stdout="not json", stderr=""),
])
def test_errored_or_timed_out_status_is_never_ready(monkeypatch, probe, failure):
    run = Mock(side_effect=failure) if isinstance(failure, BaseException) else Mock(return_value=failure)
    monkeypatch.setattr(policy.subprocess, "run", run)
    report = _settled(probe)
    assert report["status"] == "blocked"
    assert report["ready"] is False
    assert report["auth_verified"] is False


def test_live_max_login_stays_unblocked_and_exposes_only_safe_fields(monkeypatch, probe):
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**LIVE)))
    report = _settled(probe)
    assert report["status"] != "blocked"
    assert report["blockers"] == []
    assert report["auth_verified"] is True
    assert set(report["auth"]) == EXPOSED
    assert {k: report["auth"][k] for k in LIVE} == LIVE
    assert report["auth"]["checked_at"]
    assert not set(PRIVATE) & set(report["auth"])
    assert "cost_verified" in report and report["cost_verified"] is False


def test_probe_runs_the_dispatch_check_with_the_dispatch_cli_and_env(monkeypatch, probe):
    run = Mock(return_value=_status(**LIVE))
    monkeypatch.setattr(policy.subprocess, "run", run)
    _settled(probe)
    args, kwargs = run.call_args
    assert args[0][1:] == ["auth", "status"]
    assert args[0][0] == sdk._execution_cli()
    assert kwargs["env"] == sdk._child_environment()
    assert kwargs["timeout"] <= 10


def test_readiness_never_runs_the_probe_inline_and_caches_it(monkeypatch, probe):
    assert probe is not None, "cached auth probe is missing"
    run = Mock(return_value=_status(**LIVE))
    monkeypatch.setattr(policy.subprocess, "run", run)
    scheduled = Mock()
    monkeypatch.setattr(probe, "_schedule", scheduled)
    sdk.generation_readiness()
    run.assert_not_called()  # /health and the poller never wait on the CLI
    scheduled.assert_called_once_with()
    probe.refresh()
    probed = run.call_count
    assert probed >= 1
    scheduled.reset_mock()
    for _ in range(5):
        assert sdk.generation_readiness()["auth_verified"] is True
    scheduled.assert_not_called()  # fresh snapshot: no new probe for ~5 minutes
    assert run.call_count == probed


def test_stale_snapshot_is_refreshed_and_cannot_stay_verified(monkeypatch, probe):
    assert probe is not None, "cached auth probe is missing"
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**LIVE)))
    probe.refresh()
    scheduled = Mock()
    monkeypatch.setattr(probe, "_schedule", scheduled)
    now = probe._clock()
    monkeypatch.setattr(probe, "_clock", lambda: now + probe.TTL_S + 1)
    assert sdk.generation_readiness()["auth_verified"] is True  # last good result, refreshing
    scheduled.assert_called_once_with()
    monkeypatch.setattr(probe, "_clock", lambda: now + probe.MAX_AGE_S + 1)
    report = sdk.generation_readiness()
    assert report["status"] == "blocked" and report["auth_verified"] is False
