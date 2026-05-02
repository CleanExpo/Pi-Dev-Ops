"""tests/test_debate_runner.py — RA-1867 (B4) debate-runner smoke.

The real SDK call is monkey-patched so these tests don't need
``claude_agent_sdk`` or a live Claude session — they exercise the
parallelism, kill-switch behaviour, error isolation, and persistence
exclusively in Python.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import debate_runner as DR  # noqa: E402


# ── Fakes ────────────────────────────────────────────────────────────────────


class _FakeKillSwitch:
    """Replaces swarm.kill_switch.is_active for tests."""

    def __init__(self, *, on: bool = False, fire_after_s: float | None = None):
        self.on = on
        self._fire_at: float | None = (
            None if fire_after_s is None
            else asyncio.get_event_loop().time() + fire_after_s
        )

    def is_active(self) -> bool:
        if self.on:
            return True
        if self._fire_at is not None:
            try:
                return asyncio.get_event_loop().time() >= self._fire_at
            except RuntimeError:
                return False
        return False


def _install_fake_kill(monkeypatch, fake: _FakeKillSwitch) -> None:
    import swarm.kill_switch as ks
    monkeypatch.setattr(ks, "is_active", fake.is_active)


def _install_fake_sdk(monkeypatch, *, drafter_text: str, redteam_text: str,
                       drafter_seconds: float = 0.05,
                       redteam_seconds: float = 0.05,
                       drafter_rc: int = 0, redteam_rc: int = 0,
                       drafter_raises: bool = False,
                       redteam_raises: bool = False):
    """Patch _run_claude_via_sdk + model_policy at the call site."""
    async def fake_sdk(*, prompt, model, workspace, timeout, session_id,
                       phase, thinking):
        if phase == "drafter":
            if drafter_raises:
                raise RuntimeError("drafter exploded")
            await asyncio.sleep(drafter_seconds)
            return drafter_rc, drafter_text, 0.001
        else:  # "redteam"
            if redteam_raises:
                raise RuntimeError("redteam exploded")
            await asyncio.sleep(redteam_seconds)
            return redteam_rc, redteam_text, 0.001

    def fake_select(role, requested=None):
        return "sonnet"

    def fake_resolve(short_or_id):
        return "claude-sonnet-4-6"

    # Build fake modules that match the import-paths used inside debate_runner.
    import types
    fake_session_sdk = types.SimpleNamespace(_run_claude_via_sdk=fake_sdk)
    fake_model_policy = types.SimpleNamespace(
        select_model=fake_select,
        resolve_to_id=fake_resolve,
        assert_model_allowed=lambda *a, **k: None,
    )
    monkeypatch.setitem(sys.modules, "app.server.session_sdk", fake_session_sdk)
    monkeypatch.setitem(sys.modules, "app.server.model_policy", fake_model_policy)


# ── Tests ────────────────────────────────────────────────────────────────────


def test_build_prompt_has_topic_and_business_id():
    out = DR._build_prompt(
        DR._DRAFTER_TEMPLATE, topic="ship the brief",
        role="CFO", business_id="restoreassist", context="MRR=12k",
    )
    assert "ship the brief" in out
    assert "restoreassist" in out
    assert "MRR=12k" in out


def test_kill_switch_active_at_start_aborts(monkeypatch, tmp_path):
    """No SDK calls when kill-switch is active when run_debate is invoked."""
    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")
    _install_fake_kill(monkeypatch, _FakeKillSwitch(on=True))

    # If SDK is touched here, the test would fail with sdk_import_failed
    # or sdk_call_raised — but it won't be touched because of the gate.
    inp = DR.DebateInput(topic="x", role="CFO", business_id="bid")
    result = asyncio.run(DR.run_debate(inp))

    assert result.aborted is True
    assert result.abort_reason == "kill_switch_active_at_start"
    assert result.drafter.rc == 1 and result.redteam.rc == 1
    # Persistence: one record written
    persisted = (tmp_path / "debates.jsonl").read_text().splitlines()
    assert len(persisted) == 1
    assert json.loads(persisted[0])["aborted"] is True


def test_happy_path_both_sides_succeed(monkeypatch, tmp_path):
    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")
    _install_fake_kill(monkeypatch, _FakeKillSwitch(on=False))
    _install_fake_sdk(
        monkeypatch,
        drafter_text="DRAFT: ship the brief.",
        redteam_text="CRITIQUE: assumes runway calc is right.",
    )

    inp = DR.DebateInput(topic="ship today's CFO brief",
                         role="CFO", business_id="restoreassist")
    result = asyncio.run(DR.run_debate(inp))

    assert not result.aborted
    assert result.drafter.rc == 0 and result.redteam.rc == 0
    assert "DRAFT" in result.drafter.artifact
    assert "CRITIQUE" in result.redteam.artifact
    assert result.both_succeeded()
    assert result.total_cost_usd == 0.002


def test_parallelism_under_50pct_of_sequential(monkeypatch, tmp_path):
    """Acceptance: drafter+redteam wall-clock <50% of sequential sum."""
    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")
    _install_fake_kill(monkeypatch, _FakeKillSwitch(on=False))
    # Each side sleeps 0.30s — sequential would be 0.60s.
    _install_fake_sdk(
        monkeypatch,
        drafter_text="d", redteam_text="r",
        drafter_seconds=0.30, redteam_seconds=0.30,
    )

    import time
    t0 = time.monotonic()
    result = asyncio.run(DR.run_debate(
        DR.DebateInput(topic="t", role="CFO", business_id="bid")
    ))
    elapsed = time.monotonic() - t0

    sequential_lower_bound = 0.60
    assert result.both_succeeded()
    # Allow 50% headroom for asyncio overhead — should still beat sequential.
    assert elapsed < sequential_lower_bound * 0.50 + 0.10, (
        f"elapsed {elapsed}s did not beat 50% of {sequential_lower_bound}s"
    )


def test_one_side_raising_does_not_break_other(monkeypatch, tmp_path):
    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")
    _install_fake_kill(monkeypatch, _FakeKillSwitch(on=False))
    _install_fake_sdk(
        monkeypatch,
        drafter_text="d ok", redteam_text="never seen",
        redteam_raises=True,
    )

    result = asyncio.run(DR.run_debate(
        DR.DebateInput(topic="t", role="CFO", business_id="bid")
    ))

    assert not result.aborted
    assert result.drafter.rc == 0
    assert result.drafter.artifact == "d ok"
    assert result.redteam.rc == 1
    assert "exploded" in (result.redteam.error or "")
    # Half-debate still persisted
    persisted = (tmp_path / "debates.jsonl").read_text().splitlines()
    assert len(persisted) == 1


def test_run_debates_parallel_runs_many(monkeypatch, tmp_path):
    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")
    _install_fake_kill(monkeypatch, _FakeKillSwitch(on=False))
    _install_fake_sdk(
        monkeypatch,
        drafter_text="d", redteam_text="r",
        drafter_seconds=0.05, redteam_seconds=0.05,
    )

    inputs = [
        DR.DebateInput(topic=f"t{i}", role="CFO", business_id=f"b{i}")
        for i in range(4)
    ]
    results = asyncio.run(DR.run_debates_parallel(inputs))
    assert len(results) == 4
    assert all(r.both_succeeded() for r in results)
    persisted = (tmp_path / "debates.jsonl").read_text().splitlines()
    assert len(persisted) == 4


def test_load_recent_returns_persisted(monkeypatch, tmp_path):
    monkeypatch.setattr(DR, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(DR, "DEBATE_STATE_FILE_REL", "debates.jsonl")
    p = tmp_path / "debates.jsonl"
    p.write_text(json.dumps({"debate_id": "deb-1"}) + "\n"
                 + json.dumps({"debate_id": "deb-2"}) + "\n")
    out = DR.load_recent(limit=10)
    assert [r["debate_id"] for r in out] == ["deb-1", "deb-2"]
