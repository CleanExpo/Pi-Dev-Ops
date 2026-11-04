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
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, patch

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
    claude_auth_probe.reset()  # stops and joins the refresher


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


def _probe_threads():
    return [t for t in threading.enumerate() if t.name == "claude-auth-probe"]


def test_readiness_never_waits_on_a_stuck_cli_and_keeps_one_refresher(monkeypatch, probe):
    assert probe is not None, "cached auth probe is missing"
    release = threading.Event()

    def stuck_cli(*_args, **_kwargs):
        release.wait(10)
        return _status(**LIVE)

    run = Mock(side_effect=stuck_cli)
    monkeypatch.setattr(policy.subprocess, "run", run)
    started = time.monotonic()
    for _ in range(5):
        report = sdk.generation_readiness()
    assert time.monotonic() - started < 2  # /health and the poller never wait on the CLI
    assert report["status"] == "blocked" and report["auth_verified"] is False  # not yet checked
    assert any("not yet verified" in b for b in report["blockers"])
    assert len(_probe_threads()) == 1  # single-flight
    release.set()
    assert probe.wait_for_refresh(5)
    calls = run.call_count
    for _ in range(5):
        assert sdk.generation_readiness()["auth_verified"] is True
    assert run.call_count == calls  # cached: no extra CLI runs per request


def test_refresh_lands_before_trust_expires():
    from app.server import claude_auth_probe as probe
    assert probe.REFRESH_S + 2 * 10 < probe.TTL_S <= 300


def test_cached_success_expires_at_the_ttl_and_a_dead_refresh_blocks_at_once(monkeypatch, probe):
    assert probe is not None, "cached auth probe is missing"
    monkeypatch.setattr(probe, "_schedule", Mock())  # faked clock: no real refresher racing it
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**LIVE)))
    probe.refresh()
    now = probe._clock()
    monkeypatch.setattr(probe, "_clock", lambda: now + probe.TTL_S - 1)
    assert sdk.generation_readiness()["auth_verified"] is True
    monkeypatch.setattr(probe, "_clock", lambda: now + probe.TTL_S)
    report = sdk.generation_readiness()
    assert report["status"] == "blocked" and report["auth_verified"] is False
    monkeypatch.setattr(probe, "_clock", lambda: now)
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**{**LIVE, "loggedIn": False})))
    probe.refresh()  # login died after a good probe: the next refresh blocks immediately
    report = sdk.generation_readiness()
    assert report["status"] == "blocked" and report["auth"]["loggedIn"] is False


def test_refresher_that_cannot_start_blocks_without_breaking_health(monkeypatch, probe):
    assert probe is not None, "cached auth probe is missing"
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**LIVE)))
    with patch.object(threading.Thread, "start", side_effect=RuntimeError("can't start new thread")):
        report = sdk.generation_readiness()
        code, body = _authed_health()
    assert report["status"] == "blocked" and report["auth_verified"] is False
    assert code == 200 and json.loads(body)["status"] == "ok"
    assert json.loads(body)["generation"]["status"] == "blocked"


def test_reset_discards_a_refresh_that_was_in_flight(monkeypatch, probe):
    assert probe is not None, "cached auth probe is missing"
    entered, release = threading.Event(), threading.Event()

    def slow_cli(*_args, **_kwargs):
        entered.set()
        release.wait(10)
        return _status(**LIVE)

    monkeypatch.setattr(policy.subprocess, "run", Mock(side_effect=slow_cli))
    worker = threading.Thread(target=probe.refresh)
    worker.start()
    assert entered.wait(5)
    probe.reset()
    release.set()
    worker.join(5)
    snap = probe.snapshot()  # the pre-reset (verified) result was not published
    assert snap["verified"] is False and "not yet verified" in snap["error"]


def test_a_display_read_that_contradicts_the_verdict_blocks(monkeypatch, probe):
    """Codex round 2: frozen check passes on read 1, display read 2 says logged out."""
    assert probe is not None, "cached auth probe is missing"
    run = Mock(side_effect=[_status(**LIVE), _status(**{**LIVE, "loggedIn": False})])
    monkeypatch.setattr(policy.subprocess, "run", run)
    probe.refresh()
    report = sdk.generation_readiness()
    assert run.call_count == 2
    assert report["status"] == "blocked" and report["auth_verified"] is False
    assert report["auth"]["loggedIn"] is False


@pytest.mark.parametrize("key", ["authMethod", "apiProvider", "subscriptionType"])
@pytest.mark.parametrize("value", ["private@example.invalid", "sk-ant-fixture-not-a-real-token",
                                   ["max"], {"nested": "x"}, 731994655])
def test_unknown_field_values_never_leave_verbatim(monkeypatch, probe, key, value):
    assert probe is not None, "cached auth probe is missing"
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**{**LIVE, key: value})))
    probe.refresh()
    report = sdk.generation_readiness()
    assert report["auth"][key] == "other"
    assert report["status"] == "blocked"
    _code, body = _authed_health()
    assert json.dumps(value) not in body and str(value) not in body


_DRIFT_TABLE = [
    LIVE,
    *({**LIVE, "subscriptionType": s} for s in ("pro", "team", "enterprise", "free", None)),
    *({**LIVE, "authMethod": a} for a in ("none", "api_key", "oauth_token", "console")),
    *({**LIVE, "apiProvider": p} for p in ("bedrock", "vertex", None)),
    {**LIVE, "loggedIn": False}, {**LIVE, "loggedIn": "true"}, {},
]


@pytest.mark.parametrize("payload", _DRIFT_TABLE)
def test_agreement_check_matches_the_frozen_rule(monkeypatch, payload):
    """_agrees() may only AND with provider_policy; pin it so drift cannot hide."""
    from app.server import claude_auth_probe as probe
    monkeypatch.setattr(policy.subprocess, "run", Mock(return_value=_status(**payload)))
    try:
        policy.require_transport("anthropic_agent_sdk", cli_path=sys.executable, env={})
        frozen = True
    except policy.ProviderPolicyError:
        frozen = False
    assert probe._agrees(probe._public(payload)) is frozen
