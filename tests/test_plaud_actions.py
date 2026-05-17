"""Tests for scripts/plaud_actions.py."""
import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import plaud_actions


def test_action_dataclass_defaults():
    a = plaud_actions.Action(title="x", description="y", priority=2)
    assert a.title == "x"
    assert a.priority == 2


def test_action_extraction_dataclass():
    ex = plaud_actions.ActionExtraction(
        portfolio="ccw-crm", confidence=0.92,
        reasoning="mentions CCW",
        actions=[plaud_actions.Action(title="t", description="d", priority=3)],
    )
    assert ex.portfolio == "ccw-crm"
    assert len(ex.actions) == 1


def test_batch_result_dataclass():
    br = plaud_actions.BatchResult(
        plaud_id="abc", title="Acme Q2",
        wiki_path="plaud/2026-05-17-acme-q2",
        portfolio="ccw-crm",
        tickets=[],
        status="no_actions",
    )
    assert br.status == "no_actions"


def test_linear_route_namedtuple():
    r = plaud_actions.LinearRoute(team_id="t", project_id="p", status="matched")
    assert r.team_id == "t"
    assert r.status == "matched"


def test_resolve_linear_route_known_portfolio(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "ccw-crm", "linear_team_id": "uni-team-uuid", "linear_project_id": "ccw-proj-uuid"},
        {"id": "pi-dev-ops", "linear_team_id": "ra-team-uuid", "linear_project_id": "pidev-proj-uuid"},
    ]}))
    r = plaud_actions.resolve_linear_route("ccw-crm", projects_json_path=pj)
    assert r.team_id == "uni-team-uuid"
    assert r.project_id == "ccw-proj-uuid"
    assert r.status == "matched"


def test_resolve_linear_route_unknown_falls_back_to_pi_dev_ops(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "pi-dev-ops", "linear_team_id": "ra-team-uuid", "linear_project_id": "pidev-proj-uuid"},
    ]}))
    r = plaud_actions.resolve_linear_route("unknown", projects_json_path=pj)
    assert r.team_id == "ra-team-uuid"
    assert r.project_id == "pidev-proj-uuid"
    assert r.status == "fallback_unknown"


def test_resolve_linear_route_missing_portfolio_falls_back(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "pi-dev-ops", "linear_team_id": "ra", "linear_project_id": "pi"},
    ]}))
    r = plaud_actions.resolve_linear_route("imaginary-portfolio", projects_json_path=pj)
    assert r.status == "fallback_unknown"


def test_resolve_linear_route_missing_projects_json_raises(tmp_path):
    pj = tmp_path / "does_not_exist.json"
    with pytest.raises(FileNotFoundError):
        plaud_actions.resolve_linear_route("ccw-crm", projects_json_path=pj)


def test_resolve_linear_route_no_default_in_registry_raises(tmp_path):
    pj = tmp_path / "projects.json"
    pj.write_text(json.dumps({"projects": [
        {"id": "ccw-crm", "linear_team_id": "u", "linear_project_id": "c"},
    ]}))
    with pytest.raises(RuntimeError, match="pi-dev-ops"):
        plaud_actions.resolve_linear_route("unknown", projects_json_path=pj)


def _anthropic_tool_use_response(portfolio, confidence, reasoning, actions):
    return {
        "id": "msg_1",
        "type": "message",
        "role": "assistant",
        "content": [{
            "type": "tool_use",
            "id": "toolu_1",
            "name": "report_actions",
            "input": {
                "portfolio": portfolio,
                "confidence": confidence,
                "reasoning": reasoning,
                "actions": actions,
            }
        }],
        "stop_reason": "tool_use",
    }


def _anthropic_mock_urlopen(payload, status=200):
    m = MagicMock()
    m.__enter__.return_value.read.return_value = json.dumps(payload).encode()
    m.__enter__.return_value.status = status
    return m


def test_extract_actions_meeting_yields_actions():
    response = _anthropic_tool_use_response(
        portfolio="ccw-crm", confidence=0.92, reasoning="Mentions CCW",
        actions=[
            {"title": "Follow up Toby", "description": "by Friday", "priority": 2},
            {"title": "Update Q2 numbers", "description": "in Linear", "priority": 3},
        ],
    )
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(
            page_md="dummy meeting content",
            anthropic_api_key="sk-ant-test",
        )
    assert ex is not None
    assert ex.portfolio == "ccw-crm"
    assert len(ex.actions) == 2
    assert ex.actions[0].title == "Follow up Toby"
    assert ex.actions[0].priority == 2


def test_extract_actions_voice_memo_zero_actions():
    response = _anthropic_tool_use_response(
        portfolio="synthex", confidence=0.85,
        reasoning="Thinking out loud", actions=[],
    )
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(page_md="rambling memo",
            anthropic_api_key="sk-ant-test")
    assert ex is not None
    assert ex.actions == []


def test_extract_actions_no_tool_use_in_response_returns_none():
    response = {"content": [{"type": "text", "text": "I refuse to answer"}]}
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex is None


def test_extract_actions_http_401_returns_auth_error():
    import urllib.error
    err = urllib.error.HTTPError("url", 401, "Unauthorized", {}, None)
    with patch("plaud_actions.urllib.request.urlopen", side_effect=err):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert isinstance(ex, plaud_actions._AuthError)


def test_extract_actions_http_429_retries_once_then_succeeds():
    import urllib.error
    err = urllib.error.HTTPError("url", 429, "Too Many", {}, None)
    success = _anthropic_tool_use_response("synthex", 0.9, "", [])
    side_effects = [err, _anthropic_mock_urlopen(success)]
    with patch("plaud_actions.urllib.request.urlopen", side_effect=side_effects), \
         patch("plaud_actions.time.sleep") as mock_sleep:
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex is not None
    mock_sleep.assert_called_once()


def test_extract_actions_http_429_twice_returns_none():
    import urllib.error
    err = urllib.error.HTTPError("url", 429, "Too Many", {}, None)
    with patch("plaud_actions.urllib.request.urlopen", side_effect=err), \
         patch("plaud_actions.time.sleep"):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex is None


def test_extract_actions_low_confidence_preserved():
    response = _anthropic_tool_use_response(
        portfolio="unknown", confidence=0.3,
        reasoning="Ambiguous", actions=[
            {"title": "Some action", "description": "x", "priority": 3},
        ],
    )
    with patch("plaud_actions.urllib.request.urlopen",
               return_value=_anthropic_mock_urlopen(response)):
        ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="k")
    assert ex.portfolio == "unknown"
    assert ex.confidence == 0.3


def test_extract_actions_missing_key_returns_auth_error():
    ex = plaud_actions.extract_actions(page_md="x", anthropic_api_key="")
    assert isinstance(ex, plaud_actions._AuthError)


def test_create_linear_tickets_happy_path():
    actions = [
        plaud_actions.Action(title="Action 1", description="desc 1", priority=2),
        plaud_actions.Action(title="Action 2", description="desc 2", priority=3),
    ]
    refs = [
        plaud_actions.TicketRef(id="i1", identifier="CCW-247", url="u1"),
        plaud_actions.TicketRef(id="i2", identifier="CCW-248", url="u2"),
    ]
    with patch("plaud_actions.create_linear_issue", side_effect=refs):
        result = plaud_actions.create_linear_tickets(
            actions=actions, team_id="t", project_id="p",
            wiki_link="https://wiki/plaud/x.md",
            linear_api_key="lin_api_xxx",
        )
    assert len(result) == 2
    assert result[0].identifier == "CCW-247"


def test_create_linear_tickets_partial_failure():
    actions = [
        plaud_actions.Action(title="A", description="d1", priority=3),
        plaud_actions.Action(title="B", description="d2", priority=3),
        plaud_actions.Action(title="C", description="d3", priority=3),
    ]
    side_effects = [
        plaud_actions.TicketRef(id="i1", identifier="X-1", url=""),
        None,
        plaud_actions.TicketRef(id="i3", identifier="X-3", url=""),
    ]
    with patch("plaud_actions.create_linear_issue", side_effect=side_effects):
        result = plaud_actions.create_linear_tickets(
            actions=actions, team_id="t", project_id="p",
            wiki_link="https://wiki/p", linear_api_key="k",
        )
    assert len(result) == 2
    assert [r.identifier for r in result] == ["X-1", "X-3"]


def test_create_linear_tickets_appends_wiki_backlink_to_description():
    actions = [plaud_actions.Action(title="A", description="original body", priority=3)]
    seen_descriptions: list[str] = []
    def fake_create(**kw):
        seen_descriptions.append(kw["description"])
        return plaud_actions.TicketRef(id="i", identifier="X-1", url="")

    with patch("plaud_actions.create_linear_issue", side_effect=fake_create):
        plaud_actions.create_linear_tickets(
            actions=actions, team_id="t", project_id="p",
            wiki_link="https://wiki/plaud/test-slug.md", linear_api_key="k",
        )
    assert "original body" in seen_descriptions[0]
    assert "https://wiki/plaud/test-slug.md" in seen_descriptions[0]
    assert "Source" in seen_descriptions[0]
