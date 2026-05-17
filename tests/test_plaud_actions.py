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
