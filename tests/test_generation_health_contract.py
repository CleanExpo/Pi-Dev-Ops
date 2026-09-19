"""Configuration health must expose generation limits without running a model."""

import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest


@pytest.mark.parametrize("status,ready,blockers", [
    ("blocked", False, ["execution_blocked: isolation unavailable"]),
    ("unverified", None, []),
])
def test_health_includes_generation_preflight(monkeypatch, status, ready, blockers):
    from app.server import session_sdk
    from app.server.routes.health import health

    report = {"transport": "anthropic_agent_sdk", "status": status,
              "ready": ready, "blockers": blockers, "auth_verified": False,
              "cost_verified": False}
    probe = Mock(return_value=report)
    monkeypatch.setattr(session_sdk, "generation_readiness", probe, raising=False)
    monkeypatch.delenv("TAO_PASSWORD", raising=False)
    response = asyncio.run(health(SimpleNamespace(headers={}, cookies={})))
    assert json.loads(response.body)["generation"] == report
    probe.assert_called_once_with()


def test_autonomy_reports_the_same_generation_contract(monkeypatch):
    from app.server import autonomy, session_sdk

    report = {"status": "blocked", "ready": False, "blockers": ["isolation unavailable"]}
    monkeypatch.setattr(session_sdk, "generation_readiness", lambda: report, raising=False)
    monkeypatch.setattr(autonomy, "_planner_runtime_status", lambda: {})
    monkeypatch.setattr("app.server.machine_ship_readiness.machine_ship_readiness", lambda: {})
    assert autonomy.autonomy_status()["generation"] == report


@pytest.mark.parametrize("machine_ship", [False, True])
@pytest.mark.parametrize("status", ["blocked", "unverified"])
def test_autonomy_checks_generation_before_claiming_ticket(monkeypatch, machine_ship, status):
    from app.server import autonomy, session_sdk

    report = {"status": status, "blockers": ["isolation unavailable"] if status == "blocked" else []}
    monkeypatch.setattr(session_sdk, "generation_readiness", lambda: report)
    monkeypatch.setattr(autonomy, "_should_skip_no_code", lambda _: (False, ""))
    transition = Mock(return_value=None)
    events = Mock()
    create = AsyncMock()
    monkeypatch.setattr(autonomy, "_transition_to_in_progress", transition)
    monkeypatch.setattr(autonomy, "_log_event", events)
    monkeypatch.setenv("TAO_MACHINE_SHIP_MODE", "1" if machine_ship else "0")
    issue = {"id": "ticket-1", "identifier": "TEST-1", "title": "Repair test build",
             "description": "https://github.com/example/test", "labels": {"nodes": []}}
    if machine_ship:
        issue["labels"]["nodes"].append({"name": autonomy._MACHINE_SHIP_LABEL})
    asyncio.run(autonomy._process_autonomy_issue(SimpleNamespace(), create, issue))
    create.assert_not_called()
    if status == "blocked":
        transition.assert_not_called()
        assert events.call_args.args[0]["action"] == "session_blocked"
        assert events.call_args.args[0]["blockers"] == report["blockers"]
    else:
        transition.assert_called_once()
