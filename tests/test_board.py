"""tests/test_board.py — Pi-CEO Board (Layer 2) deliberation kernel smoke."""
from __future__ import annotations

import asyncio
import json
import sys
import types
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import board as B  # noqa: E402
from swarm.bots import board as board_bot  # noqa: E402


# ── Helpers ────────────────────────────────────────────────────────────────


def _stub_sdk(monkeypatch, *, text: str, rc: int = 0,
               cost: float = 0.123, raises: bool = False):
    """Replace _call_ceo_board_sdk with a deterministic stub."""
    async def fake(*, prompt, timeout_s, workspace, session_id):
        if raises:
            return 1, "", 0.0, "sdk_call_raised: boom"
        return rc, text, cost, None
    monkeypatch.setattr(B, "_call_ceo_board_sdk", fake)


_VALID_DELIBERATION = """## Deliberation

CEO: We should pursue X.
Revenue: Concur, but conditioned on margin.
Product Strategist: ...
Technical Architect: ...
Contrarian: I disagree — this exposes platform risk.
Compounder: ...
Custom Oracle: ...
Market Strategist: ...
Moonshot: ...

## Minutes summary

The Board recommends conditional approval. Margin must stay above 80%
during the trial. Contrarian's platform-risk concern is noted; CTO
should run a failover dry-run within 14 days.

## Directives

```json
{
  "directives": [
    {
      "target_role": "CMO",
      "action": "Run a 4-week trial with the new channel",
      "rationale": "Board approves with margin ceiling",
      "deadline": "2026-06-01",
      "success_criteria": "Margin stays above 80% AND LTV:CAC > 3.0"
    },
    {
      "target_role": "CTO",
      "action": "Run AWS region failover dry-run",
      "rationale": "Contrarian flagged platform-risk exposure",
      "deadline": "2026-05-17",
      "success_criteria": "Successful failover within 5 minutes"
    }
  ],
  "hitl_required": false,
  "hitl_question": null
}
```
"""


# ── BoardBrief / Directive / BoardSession round-trip ───────────────────────


def test_brief_default_session_id_format():
    b = B.BoardBrief(
        topic="x", triggered_by="senior-bot",
        triggering_actor="CMO", material_input="...",
    )
    assert b.session_id.startswith("brd-")
    assert len(b.session_id) == 14


# ── assemble_brief ──────────────────────────────────────────────────────────


def test_assemble_brief_includes_topic_and_decisions():
    b = B.BoardBrief(
        topic="Launch new LinkedIn channel",
        triggered_by="senior-bot",
        triggering_actor="CMO",
        material_input="Current channel HHI is 0.92; LinkedIn would diversify",
        requested_decisions=["Approve trial?", "What budget?"],
    )
    out = B.assemble_brief(b)
    assert "Launch new LinkedIn channel" in out
    assert "CMO" in out
    assert "HHI is 0.92" in out
    assert "Approve trial?" in out
    assert "What budget?" in out
    assert "anthropic-skills:ceo-board" in out


def test_assemble_brief_empty_decisions_renders_placeholder():
    b = B.BoardBrief(
        topic="x", triggered_by="founder",
        triggering_actor="founder", material_input="...",
    )
    out = B.assemble_brief(b)
    assert "(none specified)" in out


# ── Directive parsing ──────────────────────────────────────────────────────


def test_parse_directives_happy_path():
    directives, hitl, q = B._parse_directives(
        _VALID_DELIBERATION, session_id="brd-test",
    )
    assert len(directives) == 2
    assert directives[0].target_role == "CMO"
    assert directives[0].deadline == "2026-06-01"
    assert directives[0].session_id == "brd-test"
    assert directives[1].target_role == "CTO"
    assert hitl is False
    assert q is None


def test_parse_directives_handles_hitl_request():
    text = """## Directives

```json
{
  "directives": [],
  "hitl_required": true,
  "hitl_question": "Are we comfortable with the $50k commitment?"
}
```
"""
    directives, hitl, q = B._parse_directives(text, session_id="brd-x")
    assert directives == []
    assert hitl is True
    assert q == "Are we comfortable with the $50k commitment?"


def test_parse_directives_uses_last_fenced_block():
    """Deliberation may cite an example JSON; only the LAST block counts."""
    text = """The format looks like:

```json
{"directives": [{"target_role": "FAKE"}], "hitl_required": false}
```

[then the actual deliberation]

```json
{
  "directives": [
    {"target_role": "CFO", "action": "do x", "rationale": "y"}
  ],
  "hitl_required": false
}
```
"""
    directives, _, _ = B._parse_directives(text, session_id="brd-x")
    assert len(directives) == 1
    assert directives[0].target_role == "CFO"


def test_parse_directives_no_fence_returns_empty():
    text = "Just a plain deliberation with no JSON block."
    directives, hitl, q = B._parse_directives(text, session_id="brd-x")
    assert directives == []
    assert hitl is False
    assert q is None


def test_parse_directives_malformed_json_returns_empty():
    text = """## Directives

```json
{ "directives": [ this is not valid JSON
```
"""
    directives, hitl, q = B._parse_directives(text, session_id="brd-x")
    assert directives == []
    assert hitl is False


def test_parse_directives_skips_malformed_directive_keeps_others():
    text = """```json
{
  "directives": [
    {"target_role": "CMO", "action": "ok"},
    "not-a-dict",
    {"target_role": "CTO", "action": "ok2"}
  ],
  "hitl_required": false
}
```"""
    # Note: json.loads will succeed; "not-a-dict" string survives, our
    # parser must skip it without crashing.
    directives, _, _ = B._parse_directives(text, session_id="brd-x")
    assert len(directives) == 2
    assert directives[0].target_role == "CMO"
    assert directives[1].target_role == "CTO"


# ── Minutes summary extraction ──────────────────────────────────────────────


def test_extract_minutes_summary_finds_section():
    out = B._extract_minutes_summary(_VALID_DELIBERATION)
    assert "conditional approval" in out
    assert "Margin must stay above 80%" in out
    # Should NOT include the directives JSON
    assert '"target_role"' not in out


def test_extract_minutes_summary_falls_back_to_first_chars():
    text = "No section heading at all, just prose."
    out = B._extract_minutes_summary(text)
    assert out == text.strip()


# ── request_deliberation queues correctly ──────────────────────────────────


def test_request_deliberation_persists_pending(tmp_path):
    brief = B.BoardBrief(
        topic="Test deliberation", triggered_by="senior-bot",
        triggering_actor="CMO", material_input="x",
    )
    sid = B.request_deliberation(brief, repo_root=tmp_path)
    assert sid == brief.session_id
    pending = tmp_path / B.PENDING_DIR_REL / f"{sid}.json"
    assert pending.exists()
    data = json.loads(pending.read_text())
    assert data["brief"]["topic"] == "Test deliberation"
    assert "queued_at" in data


def test_get_pending_lists_queued_sessions(tmp_path):
    for i in range(3):
        brief = B.BoardBrief(
            topic=f"topic {i}", triggered_by="founder",
            triggering_actor="founder", material_input="x",
        )
        B.request_deliberation(brief, repo_root=tmp_path)
    pending = B.get_pending(repo_root=tmp_path)
    assert len(pending) == 3


# ── deliberate (full sync flow) ─────────────────────────────────────────────


def test_deliberate_happy_path(tmp_path, monkeypatch):
    _stub_sdk(monkeypatch, text=_VALID_DELIBERATION, rc=0, cost=0.456)

    brief = B.BoardBrief(
        topic="Approve LinkedIn trial",
        triggered_by="senior-bot", triggering_actor="CMO",
        material_input="Channel mix is over-concentrated.",
        requested_decisions=["Go/no-go?"],
    )
    session = asyncio.run(B.deliberate(brief, repo_root=tmp_path))

    assert session.succeeded()
    assert session.cost_usd == 0.456
    assert len(session.directives) == 2
    assert session.hitl_required is False
    assert "conditional approval" in session.minutes_summary

    # Persisted to all three locations
    sess_path = tmp_path / B.SESSIONS_DIR_REL / f"{brief.session_id}.json"
    assert sess_path.exists()

    direct_path = tmp_path / B.DIRECTIVES_DIR_REL / f"{brief.session_id}.jsonl"
    assert direct_path.exists()
    lines = direct_path.read_text().splitlines()
    assert len(lines) == 2

    # Pending file removed after processing
    pending_path = tmp_path / B.PENDING_DIR_REL / f"{brief.session_id}.json"
    assert not pending_path.exists()

    # Minutes file written with date-prefixed filename
    minutes = list((tmp_path / B.MEETINGS_DIR_REL).glob("*-approve-*.md"))
    assert len(minutes) == 1
    body = minutes[0].read_text()
    assert "Board minutes" in body
    assert "Approve LinkedIn trial" in body
    assert "→ CMO" in body
    assert "→ CTO" in body


def test_deliberate_sdk_failure_persists_failed_session(tmp_path, monkeypatch):
    _stub_sdk(monkeypatch, text="", rc=1, raises=True)

    brief = B.BoardBrief(
        topic="x", triggered_by="founder",
        triggering_actor="founder", material_input="x",
    )
    session = asyncio.run(B.deliberate(brief, repo_root=tmp_path))

    assert not session.succeeded()
    assert session.error and "boom" in session.error
    assert session.directives == []
    assert "Deliberation failed" in session.minutes_summary

    # Session still persisted (so we can audit failures)
    sess_path = tmp_path / B.SESSIONS_DIR_REL / f"{brief.session_id}.json"
    assert sess_path.exists()


def test_deliberate_hitl_request_persisted(tmp_path, monkeypatch):
    _stub_sdk(monkeypatch, text="""## Minutes summary

The Board cannot decide without founder input.

## Directives

```json
{
  "directives": [],
  "hitl_required": true,
  "hitl_question": "Are you comfortable committing $50k?"
}
```
""")

    brief = B.BoardBrief(
        topic="hitl test", triggered_by="senior-bot",
        triggering_actor="CFO", material_input="x",
    )
    session = asyncio.run(B.deliberate(brief, repo_root=tmp_path))

    assert session.succeeded()
    assert session.hitl_required is True
    assert "$50k" in (session.hitl_question or "")
    # Minutes mention the HITL request
    minutes = list((tmp_path / B.MEETINGS_DIR_REL).glob("*hitl-test*.md"))
    body = minutes[0].read_text()
    assert "HITL request" in body
    assert "$50k" in body


# ── process_pending ────────────────────────────────────────────────────────


def test_process_pending_runs_one_by_default(tmp_path, monkeypatch):
    _stub_sdk(monkeypatch, text=_VALID_DELIBERATION)

    for i in range(3):
        brief = B.BoardBrief(
            topic=f"queue test {i}", triggered_by="founder",
            triggering_actor="founder", material_input="x",
        )
        B.request_deliberation(brief, repo_root=tmp_path)

    sessions = asyncio.run(B.process_pending(repo_root=tmp_path, limit=1))
    assert len(sessions) == 1
    # Two pending remain
    remaining = B.get_pending(repo_root=tmp_path)
    assert len(remaining) == 2


def test_process_pending_handles_empty_queue(tmp_path):
    out = asyncio.run(B.process_pending(repo_root=tmp_path))
    assert out == []


def test_process_pending_skips_corrupt_pending(tmp_path, monkeypatch):
    _stub_sdk(monkeypatch, text=_VALID_DELIBERATION)
    pending_dir = tmp_path / B.PENDING_DIR_REL
    pending_dir.mkdir(parents=True, exist_ok=True)
    (pending_dir / "corrupt.json").write_text("{not json")

    out = asyncio.run(B.process_pending(repo_root=tmp_path))
    assert out == []  # corrupt one skipped, no others to process


# ── get_completed / get_directives_for_role ────────────────────────────────


def test_get_completed_after_deliberate(tmp_path, monkeypatch):
    _stub_sdk(monkeypatch, text=_VALID_DELIBERATION)
    brief = B.BoardBrief(
        topic="x", triggered_by="founder",
        triggering_actor="founder", material_input="x",
    )
    session = asyncio.run(B.deliberate(brief, repo_root=tmp_path))

    loaded = B.get_completed(brief.session_id, repo_root=tmp_path)
    assert loaded is not None
    assert loaded.session_id == brief.session_id
    assert len(loaded.directives) == 2


def test_get_completed_unknown_returns_none(tmp_path):
    assert B.get_completed("brd-nope", repo_root=tmp_path) is None


def test_get_directives_for_role_filters_by_target(tmp_path, monkeypatch):
    _stub_sdk(monkeypatch, text=_VALID_DELIBERATION)
    brief = B.BoardBrief(
        topic="x", triggered_by="founder",
        triggering_actor="founder", material_input="x",
    )
    asyncio.run(B.deliberate(brief, repo_root=tmp_path))

    cmo = B.get_directives_for_role("CMO", repo_root=tmp_path)
    cto = B.get_directives_for_role("CTO", repo_root=tmp_path)
    cfo = B.get_directives_for_role("CFO", repo_root=tmp_path)

    assert len(cmo) == 1 and cmo[0].target_role == "CMO"
    assert len(cto) == 1 and cto[0].target_role == "CTO"
    assert cfo == []


# ── Bot wrapper trigger surfaces ────────────────────────────────────────────


def test_escalate_creates_pending_with_sb_trigger(tmp_path, monkeypatch):
    monkeypatch.setattr(board_bot, "REPO_ROOT", tmp_path)
    sid = board_bot.escalate(
        role="CMO",
        action="launch new LinkedIn channel",
        justification="Channel concentration > 90% on google-ads",
    )
    pending = tmp_path / B.PENDING_DIR_REL / f"{sid}.json"
    assert pending.exists()
    data = json.loads(pending.read_text())
    assert data["brief"]["triggered_by"] == "senior-bot"
    assert data["brief"]["triggering_actor"] == "CMO"
    assert "LinkedIn" in data["brief"]["topic"]


def test_from_margot_includes_citations(tmp_path, monkeypatch):
    monkeypatch.setattr(board_bot, "REPO_ROOT", tmp_path)
    sid = board_bot.from_margot(
        topic="Competitor X raised series B",
        insight="Implies aggressive expansion in ANZ market",
        citations=[
            {"url": "https://example.com/x", "retrieved_at": "2026-05-03",
             "source_tier": "tier-A"},
        ],
    )
    data = json.loads(
        (tmp_path / B.PENDING_DIR_REL / f"{sid}.json").read_text()
    )
    assert data["brief"]["triggered_by"] == "margot"
    assert "Citations:" in data["brief"]["material_input"]
    assert "tier-A" in data["brief"]["material_input"]


def test_from_founder_records_intent(tmp_path, monkeypatch):
    monkeypatch.setattr(board_bot, "REPO_ROOT", tmp_path)
    sid = board_bot.from_founder(
        prompt="Should we accept the offer from Acme Corp?",
    )
    data = json.loads(
        (tmp_path / B.PENDING_DIR_REL / f"{sid}.json").read_text()
    )
    assert data["brief"]["triggered_by"] == "founder"
    assert "Acme Corp" in data["brief"]["material_input"]


def test_queue_depth_and_list_pending(tmp_path, monkeypatch):
    monkeypatch.setattr(board_bot, "REPO_ROOT", tmp_path)
    for i in range(2):
        board_bot.from_founder(prompt=f"test {i}")
    assert board_bot.queue_depth() == 2
    assert len(board_bot.list_pending()) == 2
