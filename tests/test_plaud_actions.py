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
