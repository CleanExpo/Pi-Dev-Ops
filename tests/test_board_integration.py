"""tests/test_board_integration.py — directive consumer + 6-pager Board section."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import board as B  # noqa: E402
from swarm import board_directive_consumer as DC  # noqa: E402
from swarm import six_pager  # noqa: E402


def _seed_directives(tmp_path: Path, *,
                       session_id: str,
                       directives: list[dict]) -> None:
    """Write a directives jsonl file (without going through deliberate)."""
    (tmp_path / B.DIRECTIVES_DIR_REL).mkdir(parents=True, exist_ok=True)
    p = tmp_path / B.DIRECTIVES_DIR_REL / f"{session_id}.jsonl"
    with p.open("w", encoding="utf-8") as f:
        for d in directives:
            d["session_id"] = session_id
            f.write(json.dumps(d) + "\n")


def _seed_session(tmp_path: Path, *, session_id: str,
                    topic: str = "test",
                    directives: list[dict] | None = None,
                    hitl_required: bool = False,
                    hitl_question: str | None = None) -> None:
    """Write a completed-session JSON file."""
    (tmp_path / B.SESSIONS_DIR_REL).mkdir(parents=True, exist_ok=True)
    p = tmp_path / B.SESSIONS_DIR_REL / f"{session_id}.json"
    data = {
        "session_id": session_id,
        "brief": {
            "topic": topic, "triggered_by": "founder",
            "triggering_actor": "founder", "material_input": "x",
            "requested_decisions": [], "timeout_s": 300,
            "workspace": None, "session_id": session_id,
        },
        "deliberation_text": "...",
        "minutes_summary": "...",
        "directives": directives or [],
        "hitl_required": hitl_required,
        "hitl_question": hitl_question,
        "started_at": "2026-05-03T06:00:00Z",
        "ended_at": "2026-05-03T06:01:00Z",
        "cost_usd": 0.123,
        "rc": 0,
        "error": None,
    }
    p.write_text(json.dumps(data, indent=2))


# ── Directive consumer ─────────────────────────────────────────────────────


def test_consume_for_returns_new_directives(tmp_path):
    _seed_directives(tmp_path, session_id="brd-1", directives=[
        {"target_role": "CMO", "action": "do x", "rationale": "y",
         "deadline": None, "success_criteria": None},
    ])
    state: dict = {}
    out = DC.consume_for("CMO", state=state, repo_root=tmp_path)
    assert len(out) == 1
    assert out[0].action == "do x"


def test_consume_for_does_not_reissue(tmp_path):
    """Second call returns no directives — cursor moved past brd-1."""
    _seed_directives(tmp_path, session_id="brd-1", directives=[
        {"target_role": "CMO", "action": "do x", "rationale": "y",
         "deadline": None, "success_criteria": None},
    ])
    state: dict = {}
    first = DC.consume_for("CMO", state=state, repo_root=tmp_path)
    second = DC.consume_for("CMO", state=state, repo_root=tmp_path)
    assert len(first) == 1
    assert second == []


def test_consume_for_returns_only_new_after_partial(tmp_path):
    """First call sees brd-1; brd-2 added; second call sees only brd-2."""
    _seed_directives(tmp_path, session_id="brd-1", directives=[
        {"target_role": "CFO", "action": "spend up", "rationale": "y",
         "deadline": None, "success_criteria": None},
    ])
    state: dict = {}
    DC.consume_for("CFO", state=state, repo_root=tmp_path)

    _seed_directives(tmp_path, session_id="brd-2", directives=[
        {"target_role": "CFO", "action": "spend down", "rationale": "y",
         "deadline": None, "success_criteria": None},
    ])
    out = DC.consume_for("CFO", state=state, repo_root=tmp_path)
    assert len(out) == 1
    assert out[0].action == "spend down"


def test_consume_for_filters_by_role(tmp_path):
    _seed_directives(tmp_path, session_id="brd-mixed", directives=[
        {"target_role": "CMO", "action": "x", "rationale": "y",
         "deadline": None, "success_criteria": None},
        {"target_role": "CTO", "action": "z", "rationale": "y",
         "deadline": None, "success_criteria": None},
    ])
    cmo_state: dict = {}
    cto_state: dict = {}
    cmo = DC.consume_for("CMO", state=cmo_state, repo_root=tmp_path)
    cto = DC.consume_for("CTO", state=cto_state, repo_root=tmp_path)
    assert len(cmo) == 1 and cmo[0].target_role == "CMO"
    assert len(cto) == 1 and cto[0].target_role == "CTO"


def test_consume_for_no_state_returns_all(tmp_path):
    _seed_directives(tmp_path, session_id="brd-1", directives=[
        {"target_role": "CMO", "action": "x", "rationale": "y",
         "deadline": None, "success_criteria": None},
    ])
    out = DC.consume_for("CMO", state=None, repo_root=tmp_path)
    assert len(out) == 1


def test_consume_for_empty_returns_empty(tmp_path):
    out = DC.consume_for("CMO", state={}, repo_root=tmp_path)
    assert out == []


def test_acknowledge_marks_consumed(tmp_path):
    _seed_directives(tmp_path, session_id="brd-1", directives=[
        {"target_role": "CMO", "action": "x", "rationale": "y",
         "deadline": None, "success_criteria": None},
    ])
    state: dict = {}
    DC.acknowledge("CMO", "brd-1", state=state)
    out = DC.consume_for("CMO", state=state, repo_root=tmp_path)
    assert out == []


def test_pending_count_for(tmp_path):
    _seed_directives(tmp_path, session_id="brd-1", directives=[
        {"target_role": "CFO", "action": "x", "rationale": "y",
         "deadline": None, "success_criteria": None},
    ])
    _seed_directives(tmp_path, session_id="brd-2", directives=[
        {"target_role": "CFO", "action": "z", "rationale": "y",
         "deadline": None, "success_criteria": None},
    ])
    state: dict = {}
    assert DC.pending_count_for("CFO", state=state, repo_root=tmp_path) == 2
    DC.consume_for("CFO", state=state, repo_root=tmp_path)
    assert DC.pending_count_for("CFO", state=state, repo_root=tmp_path) == 0


def test_all_pending_counts_returns_dict(tmp_path):
    _seed_directives(tmp_path, session_id="brd-1", directives=[
        {"target_role": "CMO", "action": "x", "rationale": "y",
         "deadline": None, "success_criteria": None},
    ])
    counts = DC.all_pending_counts(state={}, repo_root=tmp_path)
    assert counts == {"CFO": 0, "CMO": 1, "CTO": 0, "CS": 0}


# ── 6-pager Board section ──────────────────────────────────────────────────


def test_six_pager_shows_board_section_with_no_activity(tmp_path):
    out = six_pager.assemble_six_pager(repo_root=tmp_path)
    assert "🏛 Board — 0 pending · 0 recent sessions" in out
    assert "7. " in out  # Section 7 present


def test_six_pager_board_section_shows_pending(tmp_path):
    brief = B.BoardBrief(
        topic="test pending", triggered_by="founder",
        triggering_actor="founder", material_input="x",
    )
    B.request_deliberation(brief, repo_root=tmp_path)
    out = six_pager.assemble_six_pager(repo_root=tmp_path)
    assert "1 pending" in out
    assert "Pending deliberations:" in out
    assert brief.session_id in out


def test_six_pager_board_section_shows_open_hitl(tmp_path):
    _seed_session(
        tmp_path, session_id="brd-hitl",
        topic="$50k commitment",
        hitl_required=True,
        hitl_question="Are you comfortable?",
    )
    out = six_pager.assemble_six_pager(repo_root=tmp_path)
    assert "1 HITL" in out
    assert "⏳ Awaiting founder decision" in out
    assert "Are you comfortable?" in out


def test_six_pager_board_section_shows_recent_decisions(tmp_path):
    _seed_session(
        tmp_path, session_id="brd-done-1",
        topic="LinkedIn channel trial",
        directives=[
            {"target_role": "CMO", "action": "trial",
             "rationale": "y", "deadline": None,
             "success_criteria": None, "session_id": "brd-done-1"},
        ],
    )
    out = six_pager.assemble_six_pager(repo_root=tmp_path)
    assert "Recent decisions" in out
    assert "LinkedIn channel trial" in out
    assert "1 directive" in out


def test_six_pager_board_section_chunks_safely(tmp_path):
    """Adding section 7 keeps chunks under the Telegram budget."""
    # Seed a Board section with realistic content
    for i in range(3):
        brief = B.BoardBrief(
            topic=f"deliberation {i}", triggered_by="founder",
            triggering_actor="founder", material_input="x",
        )
        B.request_deliberation(brief, repo_root=tmp_path)

    out = six_pager.assemble_six_pager(repo_root=tmp_path)
    chunks = six_pager.chunk_for_telegram(out)
    assert all(len(c) <= six_pager.TELEGRAM_CHUNK_BUDGET for c in chunks)
