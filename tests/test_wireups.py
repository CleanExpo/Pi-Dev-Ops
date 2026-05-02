"""tests/test_wireups.py — Track 1 wire-up smoke (RA-1858 follow-up).

Covers:
1. debate_runner.run_debate emits a kanban card on success
2. debate_runner does NOT emit a kanban card on abort
3. six_pager_dispatcher.maybe_fire_daily fires inside its window
4. six_pager_dispatcher debounces within 23h
5. six_pager_dispatcher does not fire outside its window
6. Orchestrator imports cleanly with all 4 senior-bot modules
"""
from __future__ import annotations

import asyncio
import json
import sys
import types
from datetime import datetime, timezone
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import debate_runner as DR  # noqa: E402
from swarm import six_pager_dispatcher as SPD  # noqa: E402


# ── Helpers (reused from test_debate_runner with light copy) ────────────────


class _FakeKill:
    def __init__(self, on=False):
        self.on = on

    def is_active(self):
        return self.on


def _install_fake_kill(monkeypatch, fake):
    import swarm.kill_switch as ks
    monkeypatch.setattr(ks, "is_active", fake.is_active)


def _install_fake_sdk(monkeypatch, *, drafter="DRAFT", redteam="CRIT",
                       d_rc=0, r_rc=0, d_raises=False, r_raises=False):
    async def fake_sdk(*, prompt, model, workspace, timeout, session_id,
                       phase, thinking):
        if phase == "drafter":
            if d_raises:
                raise RuntimeError("drafter exploded")
            await asyncio.sleep(0.01)
            return d_rc, drafter, 0.001
        if r_raises:
            raise RuntimeError("redteam exploded")
        await asyncio.sleep(0.01)
        return r_rc, redteam, 0.001

    fake_session_sdk = types.SimpleNamespace(_run_claude_via_sdk=fake_sdk)
    fake_model_policy = types.SimpleNamespace(
        select_model=lambda role, requested=None: "sonnet",
        resolve_to_id=lambda s: "claude-sonnet-4-6",
        assert_model_allowed=lambda *a, **k: None,
    )
    monkeypatch.setitem(sys.modules, "app.server.session_sdk", fake_session_sdk)
    monkeypatch.setitem(sys.modules, "app.server.model_policy", fake_model_policy)


# ── 1.1: debate_runner emits kanban card on success ─────────────────────────


def test_debate_emits_kanban_card_on_success(monkeypatch, tmp_path):
    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")
    _install_fake_kill(monkeypatch, _FakeKill(on=False))
    _install_fake_sdk(monkeypatch)

    captured: dict = {}

    def fake_emit(**kwargs):
        captured.update(kwargs)
        return "k-fake-1"

    from swarm import kanban_adapter as KA
    monkeypatch.setattr(KA, "emit_debate_card", fake_emit)

    inp = DR.DebateInput(topic="ship CFO brief", role="CFO",
                         business_id="restoreassist")
    result = asyncio.run(DR.run_debate(inp))

    assert result.both_succeeded()
    assert captured.get("debate_id") == inp.debate_id
    assert captured.get("role") == "CFO"
    assert captured.get("business_id") == "restoreassist"
    assert captured.get("drafter_artifact") == "DRAFT"
    assert captured.get("redteam_artifact") == "CRIT"


def test_debate_does_not_emit_kanban_on_abort(monkeypatch, tmp_path):
    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")
    _install_fake_kill(monkeypatch, _FakeKill(on=True))  # kill-switch ON

    called = [False]

    def fake_emit(**kwargs):
        called[0] = True
        return "k-should-not-be-emitted"

    from swarm import kanban_adapter as KA
    monkeypatch.setattr(KA, "emit_debate_card", fake_emit)

    inp = DR.DebateInput(topic="x", role="CFO", business_id="bid")
    result = asyncio.run(DR.run_debate(inp))

    assert result.aborted
    assert called[0] is False


def test_debate_does_not_emit_kanban_on_one_side_fail(monkeypatch, tmp_path):
    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")
    _install_fake_kill(monkeypatch, _FakeKill(on=False))
    _install_fake_sdk(monkeypatch, r_raises=True)

    called = [False]

    def fake_emit(**kwargs):
        called[0] = True
        return "k-should-not-be-emitted"

    from swarm import kanban_adapter as KA
    monkeypatch.setattr(KA, "emit_debate_card", fake_emit)

    inp = DR.DebateInput(topic="x", role="CFO", business_id="bid")
    result = asyncio.run(DR.run_debate(inp))

    assert not result.both_succeeded()
    assert called[0] is False


# ── 1.3: six_pager_dispatcher window + dispatch logic ───────────────────────


def _stub_draft_review(monkeypatch, *, raise_on_post=False,
                        captured: dict | None = None):
    fake = types.SimpleNamespace()

    def post_draft(*, draft_text, destination_chat_id,
                    drafted_by_role, originating_intent_id):
        if captured is not None:
            captured.update({
                "draft_text": draft_text,
                "destination_chat_id": destination_chat_id,
                "drafted_by_role": drafted_by_role,
                "originating_intent_id": originating_intent_id,
            })
        if raise_on_post:
            raise RuntimeError("draft_review unavailable")
        return {"draft_id": "drft-spd-001"}

    fake.post_draft = post_draft
    monkeypatch.setitem(sys.modules, "swarm.draft_review", fake)


def _stub_pii_redactor(monkeypatch):
    fake = types.SimpleNamespace(redact=lambda text: text)
    monkeypatch.setitem(sys.modules, "swarm.pii_redactor", fake)


def test_dispatcher_fires_inside_window(monkeypatch, tmp_path):
    monkeypatch.setenv("TAO_SIX_PAGER_HOUR_UTC", "6")
    monkeypatch.delenv("ELEVENLABS_API_KEY", raising=False)
    captured: dict = {}
    _stub_draft_review(monkeypatch, captured=captured)
    _stub_pii_redactor(monkeypatch)

    state: dict = {}
    fake_now = datetime(2026, 5, 3, 6, 0, 0, tzinfo=timezone.utc)
    fired = SPD.maybe_fire_daily(state, repo_root=tmp_path, now=fake_now)

    assert fired is True
    assert "Pi-CEO daily 6-pager" in captured["draft_text"]
    assert captured["drafted_by_role"] == "CoS"
    assert state[SPD.STATE_KEY] == fake_now.isoformat()


def test_dispatcher_debounces_within_23h(monkeypatch, tmp_path):
    monkeypatch.setenv("TAO_SIX_PAGER_HOUR_UTC", "6")
    _stub_draft_review(monkeypatch)
    _stub_pii_redactor(monkeypatch)

    fake_now = datetime(2026, 5, 3, 6, 0, 0, tzinfo=timezone.utc)
    state: dict = {SPD.STATE_KEY: fake_now.isoformat()}

    fired = SPD.maybe_fire_daily(state, repo_root=tmp_path, now=fake_now)
    assert fired is False  # already fired


def test_dispatcher_outside_window_does_not_fire(monkeypatch, tmp_path):
    monkeypatch.setenv("TAO_SIX_PAGER_HOUR_UTC", "6")
    _stub_draft_review(monkeypatch)
    _stub_pii_redactor(monkeypatch)

    state: dict = {}
    fake_now = datetime(2026, 5, 3, 12, 0, 0, tzinfo=timezone.utc)  # not 6
    fired = SPD.maybe_fire_daily(state, repo_root=tmp_path, now=fake_now)
    assert fired is False


def test_dispatcher_draft_review_failure_does_not_crash(monkeypatch, tmp_path):
    monkeypatch.setenv("TAO_SIX_PAGER_HOUR_UTC", "6")
    monkeypatch.setenv("TAO_DRAFT_REVIEW_TEST", "1")
    _stub_draft_review(monkeypatch, raise_on_post=True)
    _stub_pii_redactor(monkeypatch)

    state: dict = {}
    fake_now = datetime(2026, 5, 3, 6, 0, 0, tzinfo=timezone.utc)
    fired = SPD.maybe_fire_daily(state, repo_root=tmp_path, now=fake_now)
    assert fired is False
    assert SPD.STATE_KEY not in state  # no stamp on failure


# ── 1.2: orchestrator imports cleanly ───────────────────────────────────────


def test_orchestrator_imports_with_all_four_senior_bots():
    """Smoke: import the bots module path the orchestrator uses."""
    from swarm.bots import (  # noqa: F401
        chief_of_staff, cfo, cmo, cto, cs,
    )
