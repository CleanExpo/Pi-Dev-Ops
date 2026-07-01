"""tests/test_closed_loop_llm_plan.py — UNI-2214: LLM-authored multi-move plan.

Proves the double-gate (CLOSED_LOOP_LLM_PLAN on AND live cycle) so the LLM plan
never spends in production until explicitly enabled, that a malformed or
invalid LLM plan always falls back to the deterministic plan, and that the JSON
parser is strict.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import closed_loop as CL  # noqa: E402
from swarm import config as CFG  # noqa: E402


@pytest.fixture
def loop_root(tmp_path):
    """repo_root with real skills/ so the forward-planner validator loads."""
    (tmp_path / "skills").symlink_to(REPO_ROOT / "skills")
    return tmp_path


@pytest.fixture
def spy_llm(monkeypatch):
    """Record whether _llm_plan is invoked and control what it returns."""
    calls = {"n": 0, "ret": None}

    def _fake(intent_payload):
        calls["n"] += 1
        return calls["ret"]

    monkeypatch.setattr(CL, "_llm_plan", _fake)
    return calls


PAYLOAD = {"intent": "research", "fields": {"topic": "AU DR market"},
           "raw_message": "research the AU disaster-recovery market"}


def _valid_llm_plan() -> dict:
    return {
        "project_id": "pi-dev-ops",
        "goal": "Size the AU disaster-recovery market",
        "win_condition": [{"id": "wc-1", "statement": "Market size delivered with sources"}],
        "moves": [
            {"id": "m1", "summary": "Gather sources", "depends_on": [],
             "satisfies": ["wc-1"], "linear": {"project_id": "pi-dev-ops"},
             "verify": "5+ credible sources"},
            {"id": "m2", "summary": "Synthesise estimate", "depends_on": ["m1"],
             "satisfies": ["wc-1"], "linear": {"project_id": "pi-dev-ops"},
             "verify": "estimate with confidence range"},
        ],
    }


def test_default_dry_run_uses_deterministic_and_never_calls_llm(spy_llm):
    plan = CL._build_plan(PAYLOAD, dry_run=True)
    assert plan["moves"][0]["id"] == "move-1"   # deterministic shape
    assert spy_llm["n"] == 0


def test_flag_off_live_uses_deterministic(monkeypatch, spy_llm):
    monkeypatch.setattr(CFG, "CLOSED_LOOP_LLM_PLAN", False)
    plan = CL._build_plan(PAYLOAD, dry_run=False)
    assert plan["moves"][0]["id"] == "move-1"
    assert spy_llm["n"] == 0


def test_flag_on_but_dry_run_never_spends(monkeypatch, spy_llm):
    monkeypatch.setattr(CFG, "CLOSED_LOOP_LLM_PLAN", True)
    plan = CL._build_plan(PAYLOAD, dry_run=True)
    assert plan["moves"][0]["id"] == "move-1"
    assert spy_llm["n"] == 0   # dry_run wins — no LLM call, no spend


def test_flag_on_live_valid_plan_is_used(monkeypatch, spy_llm, loop_root):
    monkeypatch.setattr(CFG, "CLOSED_LOOP_LLM_PLAN", True)
    spy_llm["ret"] = _valid_llm_plan()
    plan = CL._build_plan(PAYLOAD, dry_run=False, repo_root=loop_root)
    assert [m["id"] for m in plan["moves"]] == ["m1", "m2"]
    assert spy_llm["n"] == 1


def test_flag_on_live_llm_none_falls_back(monkeypatch, spy_llm, loop_root):
    monkeypatch.setattr(CFG, "CLOSED_LOOP_LLM_PLAN", True)
    spy_llm["ret"] = None   # generation failed
    plan = CL._build_plan(PAYLOAD, dry_run=False, repo_root=loop_root)
    assert plan["moves"][0]["id"] == "move-1"


def test_flag_on_live_invalid_plan_falls_back(monkeypatch, spy_llm, loop_root):
    monkeypatch.setattr(CFG, "CLOSED_LOOP_LLM_PLAN", True)
    bad = _valid_llm_plan()
    bad["moves"][0]["satisfies"] = ["wc-DOES-NOT-EXIST"]  # validator error
    spy_llm["ret"] = bad
    plan = CL._build_plan(PAYLOAD, dry_run=False, repo_root=loop_root)
    assert plan["moves"][0]["id"] == "move-1"   # fell back


# ── parser ────────────────────────────────────────────────────────────────────

def test_parse_plan_json_bare():
    assert CL._parse_plan_json('{"project_id":"x","goal":"g","win_condition":[],"moves":[{"id":"m1"}]}')


def test_parse_plan_json_fenced():
    fenced = '```json\n{"project_id":"x","goal":"g","win_condition":[],"moves":[{"id":"m1"}]}\n```'
    assert CL._parse_plan_json(fenced)


def test_parse_plan_json_rejects_garbage():
    assert CL._parse_plan_json("not json at all") is None


def test_parse_plan_json_rejects_missing_keys():
    assert CL._parse_plan_json('{"project_id":"x","goal":"g"}') is None


def test_parse_plan_json_rejects_empty_moves():
    assert CL._parse_plan_json('{"project_id":"x","goal":"g","win_condition":[],"moves":[]}') is None
