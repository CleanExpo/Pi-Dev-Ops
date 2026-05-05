"""tests/test_margot_propose_idea.py — RA-2002 regression coverage.

Margot → Linear ideas bridge:

  * `[IDEA]` sentinel parsing extracts title/description/priority/project
    correctly from Margot's draft response, including default fallbacks.
  * `propose_idea()` payload shape matches Linear's IssueCreateInput
    contract (teamId, projectId, labelIds, priority, description footer).
  * `handle_turn` integration: when an [IDEA] sentinel appears in the
    LLM draft, the resulting MargotTurn.margot_text contains the
    "Filed as <ID>" confirmation footer and the raw sentinel is stripped.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from swarm import margot_bot, margot_tools  # noqa: E402


# ── Sentinel parser ──────────────────────────────────────────────────────────


def test_parse_idea_basic():
    text = (
        'Sure, that\'s a great idea.\n\n'
        '[IDEA title="Add a daily standup digest" priority="high"]\n'
        'Auto-generated 8am summary of yesterday\'s commits, open PRs, '
        'and Linear updates. Telegram delivery via existing bot_name='
        '"Pi-CEO" surface.\n'
        '[/IDEA]'
    )
    requests, cleaned = margot_bot.parse_idea_requests(text)
    assert len(requests) == 1
    r = requests[0]
    assert r.title == "Add a daily standup digest"
    assert r.priority == 2  # "high" → 2
    assert r.project == "Pi - Dev -Ops"  # default
    assert "8am summary" in r.description
    # Sentinel stripped from cleaned text
    assert "[IDEA" not in cleaned
    assert "[/IDEA]" not in cleaned
    assert "Sure, that's a great idea." in cleaned


def test_parse_idea_default_priority_and_project():
    text = (
        '[IDEA title="Tiny cleanup task"]\n'
        'Just a small cleanup.\n'
        '[/IDEA]'
    )
    requests, _ = margot_bot.parse_idea_requests(text)
    assert len(requests) == 1
    assert requests[0].priority == 3  # "medium" default
    assert requests[0].project == "Pi - Dev -Ops"


def test_parse_idea_explicit_project_override():
    text = (
        '[IDEA title="DR-side improvement" priority="low" project="DR-NRPG"]\n'
        'Body.\n'
        '[/IDEA]'
    )
    requests, _ = margot_bot.parse_idea_requests(text)
    assert requests[0].project == "DR-NRPG"
    assert requests[0].priority == 4  # "low" → 4


def test_parse_idea_missing_title_skipped():
    """A sentinel without a title is dropped silently — Margot model error."""
    text = '[IDEA priority="high"]\nNo title here\n[/IDEA]'
    requests, cleaned = margot_bot.parse_idea_requests(text)
    assert requests == []
    # Sentinel still stripped from cleaned text
    assert "[IDEA" not in cleaned


def test_parse_idea_multiple():
    text = (
        '[IDEA title="First idea"]\nBody one.\n[/IDEA]\n\n'
        'Some prose between.\n\n'
        '[IDEA title="Second idea" priority="urgent"]\nBody two.\n[/IDEA]'
    )
    requests, cleaned = margot_bot.parse_idea_requests(text)
    assert len(requests) == 2
    assert requests[0].title == "First idea"
    assert requests[0].priority == 3
    assert requests[1].title == "Second idea"
    assert requests[1].priority == 1  # "urgent" → 1
    assert "Some prose between." in cleaned


# ── propose_idea() payload shape ──────────────────────────────────────────────


def test_propose_idea_dry_run_returns_synthetic():
    out = margot_tools.propose_idea(
        title="Test idea", description="Body", dry_run=True,
    )
    assert out["status"] == "dry_run"
    assert out["title"] == "Test idea"
    assert out["label"] == margot_tools.MARGOT_IDEA_LABEL


def test_propose_idea_no_api_key_returns_error(monkeypatch):
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")  # bypass kill switch
    monkeypatch.delenv("LINEAR_API_KEY", raising=False)
    out = margot_tools.propose_idea(title="Test", description="x")
    # _resolve_team_id returns None when no API key → team_not_found
    # OR _linear_gql returns no_api_key → propagated up as 'error'
    assert "error" in out
    assert out.get("error") in ("no_api_key", "team_not_found")


def test_propose_idea_kill_switch_skips(monkeypatch):
    monkeypatch.setenv("TAO_SWARM_ENABLED", "0")  # kill switch ACTIVE
    out = margot_tools.propose_idea(title="Test", description="x")
    assert out == {"status": "skipped_kill_switch"}


def test_propose_idea_empty_title_rejected(monkeypatch):
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "fake-key")
    out = margot_tools.propose_idea(title="   ", description="body")
    assert out == {"error": "title_required"}


def test_propose_idea_payload_includes_label_and_project(monkeypatch):
    """Mock the GraphQL transport and verify the issueCreate input shape."""
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "fake-key")

    captured: list[dict] = []

    def _fake_gql(query, variables=None, **_):
        captured.append({"query": query, "variables": variables})
        if "teams(first: 100)" in query and "key name" in query:
            return {"data": {"teams": {"nodes": [
                {"id": "team-uuid", "key": "RA", "name": "RestoreAssist"},
            ]}}}
        if "projects(first: 100)" in query:
            return {"data": {"team": {"projects": {"nodes": [
                {"id": "project-uuid", "name": "Pi - Dev -Ops"},
            ]}}}}
        if "labels(first: 100)" in query:
            return {"data": {"team": {"labels": {"nodes": [
                {"id": "label-uuid", "name": "margot-idea"},
            ]}}}}
        if "issueCreate" in query:
            return {"data": {"issueCreate": {
                "success": True,
                "issue": {
                    "id": "issue-uuid", "identifier": "RA-9999",
                    "title": "My idea", "url": "https://linear.app/x/RA-9999",
                    "priority": 2,
                },
            }}}
        return {"error": "unexpected_query"}

    with patch.object(margot_tools, "_linear_gql", side_effect=_fake_gql):
        out = margot_tools.propose_idea(
            title="My idea", description="Reasoning here.",
            project="Pi - Dev -Ops", priority=2,
        )

    assert out["status"] == "created"
    assert out["identifier"] == "RA-9999"
    assert out["label"] == "margot-idea"

    # Verify the issueCreate variables include the right shape
    create_call = next(c for c in captured if "issueCreate" in c["query"])
    inp = create_call["variables"]["input"]
    assert inp["teamId"] == "team-uuid"
    assert inp["projectId"] == "project-uuid"
    assert inp["labelIds"] == ["label-uuid"]
    assert inp["priority"] == 2
    assert inp["title"] == "My idea"
    # Description has the attribution footer appended
    assert "Reasoning here." in inp["description"]
    assert "Captured by Margot via RA-2002" in inp["description"]


def test_propose_idea_creates_label_when_missing(monkeypatch):
    """First-time use: label doesn't exist yet, should auto-create."""
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")
    monkeypatch.setenv("LINEAR_API_KEY", "fake-key")

    create_called = {"flag": False}

    def _fake_gql(query, variables=None, **_):
        if "teams(first: 100)" in query:
            return {"data": {"teams": {"nodes": [
                {"id": "team-uuid", "key": "RA", "name": "RestoreAssist"},
            ]}}}
        if "projects(first: 100)" in query:
            return {"data": {"team": {"projects": {"nodes": []}}}}
        if "labels(first: 100)" in query:
            return {"data": {"team": {"labels": {"nodes": []}}}}  # no labels
        if "issueLabelCreate" in query:
            create_called["flag"] = True
            return {"data": {"issueLabelCreate": {
                "success": True,
                "issueLabel": {"id": "new-label-uuid", "name": "margot-idea"},
            }}}
        if "issueCreate" in query:
            return {"data": {"issueCreate": {
                "success": True,
                "issue": {
                    "id": "issue-uuid", "identifier": "RA-9999",
                    "title": "x", "url": "u", "priority": 3,
                },
            }}}
        return {"error": "unexpected"}

    with patch.object(margot_tools, "_linear_gql", side_effect=_fake_gql):
        out = margot_tools.propose_idea(title="x", description="y")

    assert create_called["flag"] is True
    assert out["status"] == "created"


# ── handle_turn integration ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_handle_turn_files_idea_and_appends_confirmation(
    monkeypatch, tmp_path,
):
    """End-to-end: LLM draft contains [IDEA], turn.margot_text contains
    "Filed as RA-XXXX" confirmation, sentinel is stripped."""
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")

    # Stub _call_llm to return a draft with an [IDEA] sentinel.
    async def _fake_call_llm(*, prompt, turn_id, role):
        return (0,
                'Got it. I\'ll capture that.\n\n'
                '[IDEA title="Add daily digest" priority="medium"]\n'
                'Auto-summary of yesterday at 8am.\n'
                '[/IDEA]',
                0.001, None)

    # Stub propose_idea so we don't hit Linear.
    def _fake_propose_idea(**kwargs):
        return {
            "status": "created", "identifier": "RA-9999",
            "id": "uuid", "title": kwargs["title"],
            "url": "https://linear.app/x/RA-9999", "priority": 3,
            "label": "margot-idea",
        }

    # Stub Telegram send so test doesn't hit the network.
    sent_messages: list[dict] = []

    def _fake_send(*, chat_id, text, reply_to_message_id=None,
                   audio_path=None):
        sent_messages.append({"chat_id": chat_id, "text": text})
        return True

    monkeypatch.setattr(margot_bot, "_call_llm", _fake_call_llm)
    monkeypatch.setattr(margot_tools, "propose_idea", _fake_propose_idea)
    monkeypatch.setattr(margot_bot, "_send_telegram", _fake_send)

    turn = await margot_bot.handle_turn(
        chat_id="12345", user_text="We should add a daily digest",
        repo_root=tmp_path, _send=False,
    )

    assert turn.error is None
    # Sentinel stripped from final text
    assert "[IDEA" not in turn.margot_text
    assert "[/IDEA]" not in turn.margot_text
    # Confirmation footer appended
    assert "Filed idea as RA-9999" in turn.margot_text
    assert "Add daily digest" in turn.margot_text
    # Original prose preserved
    assert "Got it." in turn.margot_text


@pytest.mark.asyncio
async def test_handle_turn_idea_failure_inlines_apology(monkeypatch, tmp_path):
    """If propose_idea returns an error, the user-facing reply contains a
    one-line apology so the conversation continues."""
    monkeypatch.setenv("TAO_SWARM_ENABLED", "1")

    async def _fake_call_llm(*, prompt, turn_id, role):
        return (0,
                'Sure.\n\n'
                '[IDEA title="Something"]\nbody\n[/IDEA]',
                0.001, None)

    def _fake_propose_idea(**kwargs):
        return {"error": "request_failed", "exception": "boom"}

    monkeypatch.setattr(margot_bot, "_call_llm", _fake_call_llm)
    monkeypatch.setattr(margot_tools, "propose_idea", _fake_propose_idea)
    monkeypatch.setattr(margot_bot, "_send_telegram", lambda **kw: True)

    turn = await margot_bot.handle_turn(
        chat_id="12345", user_text="add something",
        repo_root=tmp_path, _send=False,
    )

    assert "Couldn't file idea" in turn.margot_text
    assert "[IDEA" not in turn.margot_text


def _run(coro):
    """Helper for non-asyncio test runners."""
    return asyncio.get_event_loop().run_until_complete(coro)
