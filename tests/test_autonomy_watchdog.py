"""tests/test_autonomy_watchdog.py — RA-1973.

Covers:
  * watchdog: poller iteration crash → loop survives, counter increments,
    last-error captured, Telegram alert fires on first failure (and only
    when env vars are set).
  * per-team orphan recovery state lookup: RA → 'Pi-Dev: Blocked',
    DR-NRPG/SYN/GP/UNI → 'Todo', unknown UUID → 'Todo'.
  * env override: TAO_ORPHAN_RECOVERY_STATES JSON parses + applies.
  * orphan recovery does not crash when the target state is missing on a
    team's workflow.
"""
from __future__ import annotations

import asyncio
import importlib
from typing import Any
from unittest.mock import patch

import pytest


def _fresh_autonomy(monkeypatch: pytest.MonkeyPatch, **env: str | None) -> Any:
    """Reload `app.server.autonomy` with a clean env so module-level state
    (counter, error ring, state-map) starts empty per test."""
    for k, v in env.items():
        if v is None:
            monkeypatch.delenv(k, raising=False)
        else:
            monkeypatch.setenv(k, str(v))
    import app.server.autonomy as a
    return importlib.reload(a)


class _FakeConfig:
    AUTONOMY_ENABLED = True
    LINEAR_API_KEY   = "test-key"


# ---------------------------------------------------------------------------
# Watchdog tests — Part C / Part A
# ---------------------------------------------------------------------------

def test_poller_iteration_continues_on_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Iteration body raising → counter increments, _last_iteration_error set,
    loop survives (next call still works)."""
    a = _fresh_autonomy(
        monkeypatch,
        TELEGRAM_BOT_TOKEN=None,
        TELEGRAM_ALERT_CHAT_ID=None,
    )
    assert a._poller_iteration_errors == 0
    assert a._last_iteration_error is None

    async def boom(*args, **kwargs):
        raise RuntimeError("simulated poll failure")

    # Patch the iteration body and exercise the watchdog directly.
    a._record_iteration_error(RuntimeError("simulated poll failure"))

    assert a._poller_iteration_errors == 1
    assert a._last_iteration_error is not None
    assert a._last_iteration_error["error"] == "simulated poll failure"
    assert a._last_iteration_error["type"] == "RuntimeError"
    # Event ring captured the failure.
    actions = [e.get("action") for e in a._recent_events]
    assert "poller_iteration_error" in actions

    # Second crash bumps the counter; loop still alive.
    a._record_iteration_error(ValueError("another failure"))
    assert a._poller_iteration_errors == 2


def test_poller_telegram_alert_on_first_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """First crash with TELEGRAM_* env set → exactly one urlopen call."""
    a = _fresh_autonomy(
        monkeypatch,
        TELEGRAM_BOT_TOKEN="bot-token-123",
        TELEGRAM_ALERT_CHAT_ID="999",
    )
    with patch("app.server.autonomy.urllib.request.urlopen") as mock_urlopen:
        mock_urlopen.return_value.__enter__ = lambda s: s
        mock_urlopen.return_value.__exit__ = lambda s, *a: None
        mock_urlopen.return_value.close = lambda: None
        a._record_iteration_error(RuntimeError("kaboom"))

    assert mock_urlopen.call_count == 1
    call_args = mock_urlopen.call_args
    req = call_args[0][0]
    assert "api.telegram.org/botbot-token-123/sendMessage" in req.full_url


def test_poller_no_telegram_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    """No TELEGRAM env → urlopen never called."""
    a = _fresh_autonomy(
        monkeypatch,
        TELEGRAM_BOT_TOKEN=None,
        TELEGRAM_ALERT_CHAT_ID=None,
    )
    with patch("app.server.autonomy.urllib.request.urlopen") as mock_urlopen:
        a._record_iteration_error(RuntimeError("silent"))
    assert mock_urlopen.call_count == 0


# ---------------------------------------------------------------------------
# Per-team state lookup tests — Part B
# ---------------------------------------------------------------------------

def test_recovery_state_for_known_teams(monkeypatch: pytest.MonkeyPatch) -> None:
    a = _fresh_autonomy(monkeypatch, TAO_ORPHAN_RECOVERY_STATES=None)
    # RA preserves the original choice
    assert a._recovery_state_for(a._RA_TEAM_ID) == "Pi-Dev: Blocked"
    # All other team UUIDs default to "Todo"
    assert a._recovery_state_for(a._DR_NRPG_TEAM_ID) == "Todo"
    assert a._recovery_state_for(a._SYN_TEAM_ID) == "Todo"
    assert a._recovery_state_for(a._GP_TEAM_ID) == "Todo"
    assert a._recovery_state_for(a._UNI_TEAM_ID) == "Todo"


def test_recovery_state_unknown_team_falls_back_to_todo(monkeypatch: pytest.MonkeyPatch) -> None:
    a = _fresh_autonomy(monkeypatch, TAO_ORPHAN_RECOVERY_STATES=None)
    assert a._recovery_state_for("00000000-0000-0000-0000-000000000000") == "Todo"


def test_recovery_state_env_override_parses(monkeypatch: pytest.MonkeyPatch) -> None:
    """TAO_ORPHAN_RECOVERY_STATES JSON → applied at module load."""
    a = _fresh_autonomy(
        monkeypatch,
        TAO_ORPHAN_RECOVERY_STATES='{"43811130-ac12-47d3-9433-330320a76205": "Backlog"}',
    )
    assert a._recovery_state_for(a._DR_NRPG_TEAM_ID) == "Backlog"
    # RA default still preserved (partial override)
    assert a._recovery_state_for(a._RA_TEAM_ID) == "Pi-Dev: Blocked"


def test_recovery_state_env_invalid_falls_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    a = _fresh_autonomy(monkeypatch, TAO_ORPHAN_RECOVERY_STATES="not-json")
    assert a._recovery_state_for(a._DR_NRPG_TEAM_ID) == "Todo"


def test_orphan_recovery_state_missing_does_not_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    """transition_issue raises 'not found' RuntimeError → recovery routine
    skips that ticket, continues, records a state-missing event, does NOT
    propagate the exception."""
    a = _fresh_autonomy(monkeypatch, TAO_ORPHAN_RECOVERY_STATES=None)

    fake_issue = {
        "id":         "issue-1",
        "identifier": "DR-465",
        "comments":   {"nodes": [{"body": "Session ID: `abc12345abcd`"}]},
    }
    fake_project = {"project_id": "p1", "team_id": a._DR_NRPG_TEAM_ID, "repo_url": "x", "name": "DR"}

    def fake_gql(api_key, query, variables=None):
        if "InProgressPiCeo" in query or "issues(filter" in query:
            return {"project": {"issues": {"nodes": [fake_issue]}}}
        return {}

    def fake_transition(api_key, issue_id, state_name, team_id=None):
        raise RuntimeError(f"State '{state_name}' not found in team {team_id} workflow")

    monkeypatch.setattr(a, "_load_portfolio_projects", lambda: [fake_project])
    monkeypatch.setattr(a, "_gql", fake_gql)
    monkeypatch.setattr(a, "transition_issue", fake_transition)

    # _is_pi_ceo_orphan needs an empty live-session set to flag the ticket.
    fake_sessions: dict = {}
    import sys
    fake_mod = type(sys)("app.server.sessions")
    fake_mod._sessions = fake_sessions
    monkeypatch.setitem(sys.modules, "app.server.sessions", fake_mod)

    asyncio.run(a._orphan_recovery("test-key"))
    actions = [e.get("action") for e in a._recent_events]
    assert "orphan_recovery_state_missing" in actions
    # Did not propagate / did not crash the loop.


def test_orphan_recovery_routes_per_team_state(monkeypatch: pytest.MonkeyPatch) -> None:
    """RA-team ticket → 'Pi-Dev: Blocked'; DR-team ticket → 'Todo'."""
    a = _fresh_autonomy(monkeypatch, TAO_ORPHAN_RECOVERY_STATES=None)

    transitions: list[tuple[str, str, str]] = []

    def fake_transition(api_key, issue_id, state_name, team_id=None):
        transitions.append((issue_id, state_name, team_id or ""))

    def issue(team_label: str) -> dict:
        return {
            "id":         f"issue-{team_label}",
            "identifier": f"{team_label}-1",
            "comments":   {"nodes": [{"body": "Session ID: `abc12345abcd`"}]},
        }

    ra_proj = {"project_id": "ra",   "team_id": a._RA_TEAM_ID,      "repo_url": "x", "name": "RA"}
    dr_proj = {"project_id": "drnp", "team_id": a._DR_NRPG_TEAM_ID, "repo_url": "x", "name": "DR"}

    def fake_gql(api_key, query, variables=None):
        team_id = (variables or {}).get("teamId") or ""
        project_id = (variables or {}).get("projectId") or ""
        if project_id == "ra":
            return {"project": {"issues": {"nodes": [issue("RA")]}}}
        if project_id == "drnp":
            return {"project": {"issues": {"nodes": [issue("DR")]}}}
        return {}

    monkeypatch.setattr(a, "_load_portfolio_projects", lambda: [ra_proj, dr_proj])
    monkeypatch.setattr(a, "_gql", fake_gql)
    monkeypatch.setattr(a, "transition_issue", fake_transition)
    monkeypatch.setattr(a, "add_label_to_issue", lambda *args, **kwargs: True)
    monkeypatch.setattr(a, "comment_on_issue", lambda *args, **kwargs: None)

    import sys
    fake_mod = type(sys)("app.server.sessions")
    fake_mod._sessions = {}
    monkeypatch.setitem(sys.modules, "app.server.sessions", fake_mod)

    asyncio.run(a._orphan_recovery("test-key"))

    by_issue = {iid: state for (iid, state, _team) in transitions}
    assert by_issue.get("issue-RA") == "Pi-Dev: Blocked"
    assert by_issue.get("issue-DR") == "Todo"
