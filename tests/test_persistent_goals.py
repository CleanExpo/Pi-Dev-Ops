"""tests/test_persistent_goals.py — Ralph-loop substrate smoke."""
from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import persistent_goals as PG  # noqa: E402


# ── Create / list / get round-trip ──────────────────────────────────────────


def test_create_goal_persists_meta_and_index(tmp_path):
    g = PG.create_goal(
        role="CFO", business_id="portfolio",
        topic="raise runway above 18 months",
        cadence_cycles=24,
        resolution_predicate="cfo.runway_at_least_18",
        repo_root=tmp_path,
    )
    assert g.goal_id.startswith("goal-")
    assert g.status == "active"
    # Meta file written
    meta_p = tmp_path / PG.GOALS_DIR_REL / f"{g.goal_id}.meta.json"
    assert meta_p.exists()
    # Index file written + entry present
    index_p = tmp_path / PG.GOALS_DIR_REL / PG.INDEX_FILE_NAME
    idx = json.loads(index_p.read_text())
    assert g.goal_id in idx


def test_list_goals_filters_by_status(tmp_path):
    g_active = PG.create_goal(
        role="CFO", business_id="portfolio", topic="active goal",
        repo_root=tmp_path,
    )
    g_resolved = PG.create_goal(
        role="CMO", business_id="portfolio", topic="will resolve",
        repo_root=tmp_path,
    )
    PG.resolve_goal(g_resolved.goal_id, "done", repo_root=tmp_path)

    actives = PG.list_goals(status="active", repo_root=tmp_path)
    resolveds = PG.list_goals(status="resolved", repo_root=tmp_path)
    assert {g.goal_id for g in actives} == {g_active.goal_id}
    assert {g.goal_id for g in resolveds} == {g_resolved.goal_id}


def test_get_goal_round_trip(tmp_path):
    g = PG.create_goal(
        role="CFO", business_id="portfolio", topic="x",
        metadata={"min_runway_months": 24.0},
        repo_root=tmp_path,
    )
    loaded = PG.get_goal(g.goal_id, repo_root=tmp_path)
    assert loaded is not None
    assert loaded.metadata["min_runway_months"] == 24.0


# ── advance_goal appends turns ──────────────────────────────────────────────


def test_advance_goal_appends_jsonl(tmp_path):
    g = PG.create_goal(role="CFO", business_id="x", topic="t",
                        repo_root=tmp_path)
    t1 = PG.advance_goal(g.goal_id, drafter_text="d1",
                         redteam_text="r1", repo_root=tmp_path)
    t2 = PG.advance_goal(g.goal_id, drafter_text="d2",
                         redteam_text="r2", repo_root=tmp_path)
    assert t1 is not None and t2 is not None

    p = tmp_path / PG.GOALS_DIR_REL / f"{g.goal_id}.jsonl"
    lines = p.read_text().splitlines()
    assert len(lines) == 2

    # turns_count incremented
    g_loaded = PG.get_goal(g.goal_id, repo_root=tmp_path)
    assert g_loaded.turns_count == 2


def test_advance_goal_resolved_skips(tmp_path):
    g = PG.create_goal(role="CFO", business_id="x", topic="t",
                        repo_root=tmp_path)
    PG.resolve_goal(g.goal_id, "done", repo_root=tmp_path)
    out = PG.advance_goal(g.goal_id, drafter_text="d",
                            redteam_text="r", repo_root=tmp_path)
    assert out is None


def test_advance_goal_unknown_returns_none(tmp_path):
    out = PG.advance_goal("goal-nope", drafter_text="d",
                            redteam_text="r", repo_root=tmp_path)
    assert out is None


def test_read_recent_turns(tmp_path):
    g = PG.create_goal(role="CFO", business_id="x", topic="t",
                        repo_root=tmp_path)
    for i in range(7):
        PG.advance_goal(g.goal_id, drafter_text=f"d{i}",
                         redteam_text=f"r{i}", repo_root=tmp_path)
    recent = PG.read_recent_turns(g.goal_id, limit=3, repo_root=tmp_path)
    assert len(recent) == 3
    assert recent[-1].drafter_text == "d6"


# ── Resolution predicates ───────────────────────────────────────────────────


def test_cfo_runway_predicate_pass():
    g = PG.Goal(
        goal_id="g", role="CFO", business_id="portfolio", topic="t",
        cadence_cycles=12, resolution_predicate="cfo.runway_at_least_18",
        metadata={"min_runway_months": 18.0},
    )
    snapshots = {"cfo": [
        {"runway_months": 24}, {"runway_months": 19},
    ]}
    assert PG._runway_at_least_18(snapshots, g) is True


def test_cfo_runway_predicate_fail_one_below():
    g = PG.Goal(
        goal_id="g", role="CFO", business_id="portfolio", topic="t",
        cadence_cycles=12, resolution_predicate="cfo.runway_at_least_18",
        metadata={},
    )
    snapshots = {"cfo": [
        {"runway_months": 24}, {"runway_months": 12},  # below 18
    ]}
    assert PG._runway_at_least_18(snapshots, g) is False


def test_cmo_channel_share_predicate():
    g = PG.Goal(
        goal_id="g", role="CMO", business_id="x", topic="t",
        cadence_cycles=12,
        resolution_predicate="cmo.channel_top_share_below_70",
        metadata={},
    )
    snapshots = {"cmo": [
        {"top_channel_share": 0.40}, {"top_channel_share": 0.65},
    ]}
    assert PG._channel_top_share_below_70(snapshots, g) is True
    snapshots["cmo"][1]["top_channel_share"] = 0.85
    assert PG._channel_top_share_below_70(snapshots, g) is False


def test_cto_dora_predicate():
    g = PG.Goal(
        goal_id="g", role="CTO", business_id="x", topic="t",
        cadence_cycles=12,
        resolution_predicate="cto.dora_band_at_least_high",
        metadata={},
    )
    snapshots = {"cto": [
        {"dora_band": "high"}, {"dora_band": "elite"},
    ]}
    assert PG._dora_band_at_least_high(snapshots, g) is True
    snapshots["cto"][0]["dora_band"] = "medium"
    assert PG._dora_band_at_least_high(snapshots, g) is False


def test_check_resolution_auto_resolves(tmp_path):
    g = PG.create_goal(
        role="CFO", business_id="portfolio", topic="raise runway",
        resolution_predicate="cfo.runway_at_least_18",
        repo_root=tmp_path,
    )
    snapshots = {"cfo": [{"runway_months": 24}]}
    ok = PG.check_resolution(g, snapshots, repo_root=tmp_path)
    assert ok is True
    g_after = PG.get_goal(g.goal_id, repo_root=tmp_path)
    assert g_after.status == "resolved"


def test_check_resolution_keeps_active_when_predicate_false(tmp_path):
    g = PG.create_goal(
        role="CFO", business_id="portfolio", topic="t",
        resolution_predicate="cfo.runway_at_least_18",
        repo_root=tmp_path,
    )
    snapshots = {"cfo": [{"runway_months": 5}]}
    assert PG.check_resolution(g, snapshots, repo_root=tmp_path) is False
    g_after = PG.get_goal(g.goal_id, repo_root=tmp_path)
    assert g_after.status == "active"


def test_check_resolution_skips_unknown_predicate(tmp_path):
    g = PG.create_goal(
        role="CFO", business_id="x", topic="t",
        resolution_predicate="nope.does.not.exist",
        repo_root=tmp_path,
    )
    assert PG.check_resolution(g, {}) is False


# ── cycle_due ───────────────────────────────────────────────────────────────


def test_cycle_due_first_advance_fires_immediately():
    g = PG.Goal(
        goal_id="g", role="CFO", business_id="x", topic="t",
        cadence_cycles=10, last_advance_cycle=0, status="active",
        resolution_predicate=None,
    )
    assert PG.cycle_due(g, current_cycle=1) is True


def test_cycle_due_within_cadence_skips():
    g = PG.Goal(
        goal_id="g", role="CFO", business_id="x", topic="t",
        cadence_cycles=10, last_advance_cycle=5, status="active",
        resolution_predicate=None,
    )
    assert PG.cycle_due(g, current_cycle=10) is False


def test_cycle_due_past_cadence_fires():
    g = PG.Goal(
        goal_id="g", role="CFO", business_id="x", topic="t",
        cadence_cycles=10, last_advance_cycle=5, status="active",
        resolution_predicate=None,
    )
    assert PG.cycle_due(g, current_cycle=15) is True


def test_cycle_due_resolved_skips():
    g = PG.Goal(
        goal_id="g", role="CFO", business_id="x", topic="t",
        cadence_cycles=10, last_advance_cycle=0, status="resolved",
        resolution_predicate=None,
    )
    assert PG.cycle_due(g, current_cycle=999) is False


# ── debate_runner integration ───────────────────────────────────────────────


def test_debate_runner_advances_goal_on_success(tmp_path, monkeypatch):
    """run_debate with goal_id set advances the goal after both sides succeed."""
    from swarm import debate_runner as DR

    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")

    # Stub kill-switch + SDK
    import swarm.kill_switch as ks
    monkeypatch.setattr(ks, "is_active", lambda: False)

    async def fake_sdk(*, prompt, model, workspace, timeout, session_id,
                       phase, thinking):
        await asyncio.sleep(0.001)
        text = "DRAFT" if phase == "drafter" else "CRIT"
        return 0, text, 0.001

    fake_sdk_mod = types.SimpleNamespace(_run_claude_via_sdk=fake_sdk)
    fake_mp = types.SimpleNamespace(
        select_model=lambda r, requested=None: "sonnet",
        resolve_to_id=lambda s: "claude-sonnet-4-6",
        assert_model_allowed=lambda *a, **k: None,
    )
    monkeypatch.setitem(sys.modules, "app.server.session_sdk", fake_sdk_mod)
    monkeypatch.setitem(sys.modules, "app.server.model_policy", fake_mp)

    # Patch persistent_goals.repo_root resolution to use tmp_path
    monkeypatch.setattr(
        PG, "_goal_file",
        lambda rr, gid: tmp_path / PG.GOALS_DIR_REL / f"{gid}.jsonl",
    )
    monkeypatch.setattr(
        PG, "_goal_meta_file",
        lambda rr, gid: tmp_path / PG.GOALS_DIR_REL / f"{gid}.meta.json",
    )
    monkeypatch.setattr(PG, "_index_path",
                         lambda rr: tmp_path / PG.GOALS_DIR_REL / PG.INDEX_FILE_NAME)
    monkeypatch.setattr(PG, "_goals_dir",
                         lambda rr: (tmp_path / PG.GOALS_DIR_REL))

    # Stub kanban so we don't need a real hermes binary
    from swarm import kanban_adapter as KA
    monkeypatch.setattr(KA, "emit_debate_card", lambda **kw: None)

    g = PG.create_goal(role="CFO", business_id="x", topic="raise runway",
                        repo_root=tmp_path)

    inp = DR.DebateInput(topic="raise runway",
                         role="CFO", business_id="x",
                         goal_id=g.goal_id)
    result = asyncio.run(DR.run_debate(inp))
    assert result.both_succeeded()

    # Goal advanced — turns_count == 1 + jsonl exists
    g_after = PG.get_goal(g.goal_id, repo_root=tmp_path)
    assert g_after.turns_count == 1
    p = tmp_path / PG.GOALS_DIR_REL / f"{g.goal_id}.jsonl"
    assert p.exists()


def test_debate_runner_no_goal_id_does_not_advance(tmp_path, monkeypatch):
    """Without goal_id, no advance call is made."""
    from swarm import debate_runner as DR
    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")
    import swarm.kill_switch as ks
    monkeypatch.setattr(ks, "is_active", lambda: False)

    async def fake_sdk(*, prompt, model, workspace, timeout, session_id,
                       phase, thinking):
        return 0, "DRAFT" if phase == "drafter" else "CRIT", 0.001

    fake_sdk_mod = types.SimpleNamespace(_run_claude_via_sdk=fake_sdk)
    fake_mp = types.SimpleNamespace(
        select_model=lambda r, requested=None: "sonnet",
        resolve_to_id=lambda s: "claude-sonnet-4-6",
        assert_model_allowed=lambda *a, **k: None,
    )
    monkeypatch.setitem(sys.modules, "app.server.session_sdk", fake_sdk_mod)
    monkeypatch.setitem(sys.modules, "app.server.model_policy", fake_mp)

    from swarm import kanban_adapter as KA
    monkeypatch.setattr(KA, "emit_debate_card", lambda **kw: None)

    called = [False]

    def boom(*args, **kwargs):
        called[0] = True
        return None

    monkeypatch.setattr(PG, "advance_goal", boom)

    inp = DR.DebateInput(topic="t", role="CFO", business_id="x")
    result = asyncio.run(DR.run_debate(inp))
    assert result.both_succeeded()
    assert called[0] is False
