"""RA-7962: the session-start hook must not pull a ticket out of the Pi-Dev lane."""
from __future__ import annotations

import importlib
import json
from unittest.mock import MagicMock, patch


def _fake_urlopen(responses: list[dict]):
    it = iter(responses)
    calls: list[str] = []

    def _side(req, timeout=15):  # noqa: ARG001
        calls.append(json.loads(req.data)["query"])
        resp = MagicMock()
        resp.read.return_value = json.dumps(next(it)).encode()
        resp.__enter__.return_value = resp
        return resp

    _side.calls = calls  # type: ignore[attr-defined]
    return _side


def _issue_resp(state_name: str) -> dict:
    return {"data": {"issue": {"team": {"id": "team-1"}, "state": {"name": state_name}}}}


_STATES = {"data": {"team": {"states": {"nodes": [
    {"id": "s-pdip", "name": "Pi-Dev: In Progress", "type": "started"},
    {"id": "s-ip", "name": "In Progress", "type": "started"},
]}}}}
_MUTATION = {"data": {"issueUpdate": {"success": True, "issue": {"id": "i", "title": "t", "state": {"name": "x"}}}}}


def _notify_with_state(monkeypatch, current_state: str) -> list[str]:
    monkeypatch.setenv("LINEAR_OUTBOUND_SYNC", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "lin_api_test_key")
    import app.server.session_linear as sl
    importlib.reload(sl)
    session = MagicMock()
    session.linear_issue_id = "issue-ra7962"
    fake = _fake_urlopen([_issue_resp(current_state), _STATES, _MUTATION])
    with patch("urllib.request.urlopen", side_effect=fake):
        sl._notify_linear_session_started(session)
    return fake.calls


def test_pi_dev_state_is_left_alone(monkeypatch):
    assert not any("issueUpdate" in q for q in _notify_with_state(monkeypatch, "Pi-Dev: In Progress"))


def test_todo_ticket_still_moves_to_in_progress(monkeypatch):
    assert any("issueUpdate" in q for q in _notify_with_state(monkeypatch, "Todo"))
